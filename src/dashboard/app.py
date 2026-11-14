"""
Dashboard Application

FastAPI web application for the trading dashboard.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import AsyncIterator, Optional, Dict, Any
import logging
from pathlib import Path

from ..core.config import get_config
from ..core.logging import get_logger
from ..execution.execution_worker import start_execution_worker, stop_execution_worker
from ..execution.trade_state import TradeStatePersistenceError
from ..risk.risk_engine import get_risk_engine
from .routes import router as api_router


# Configure logging
logger = logging.getLogger(__name__)


# Global app instance
_app: Optional[FastAPI] = None


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Start/stop the background execution worker and risk engine with the
    app lifecycle.

    Without the execution-worker half, nothing ever calls
    ExecutionWorker.start(), so every call that goes through it
    (trade/open, trade/close, emergency/stop, system/reconcile) fails
    immediately with ExecutionError("Execution worker is not running").

    Without the risk-engine half, RiskEngine.initialize() was never called
    by anything either: its own order_manager was never connected and its
    own trade_state_manager never loaded active cycles from the database,
    so trigger_emergency_stop()'s "close everything" pass ran against an
    empty, disconnected copy of the world even while real trades were
    open elsewhere. Both now share the same underlying singletons (see
    RiskEngine.__init__ and ExecutionWorker.__init__), so initializing
    either one here wires up the one shared order_manager/trade_state
    the whole app actually uses.
    """
    start_execution_worker()
    logger.info("Execution worker started on application startup")
    try:
        get_risk_engine().initialize()
        logger.info("Risk engine initialized on application startup")
    except TradeStatePersistenceError as e:
        # Refuse to come up pretending trading is safe to start if we
        # can't even find out what cycles were already open.
        logger.critical(f"Risk engine failed to initialize: {e}")
        stop_execution_worker()
        raise
    try:
        yield
    finally:
        stop_execution_worker()
        logger.info("Execution worker stopped on application shutdown")


def create_app() -> FastAPI:
    """
    Create the FastAPI application.

    Returns:
        FastAPI application instance
    """
    global _app

    if _app is not None:
        return _app

    # Create app
    app = FastAPI(
        title="Cross-Broker Trading System",
        description="Web dashboard for monitoring the cross-broker CFD trading system",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan
    )
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Mount static files
    static_path = Path(__file__).parent / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=static_path), name="static")
    
    # Setup templates
    templates_path = Path(__file__).parent / "templates"
    if templates_path.exists():
        templates = Jinja2Templates(directory=str(templates_path))
    else:
        templates = None
    
    # Include API routes
    app.include_router(api_router, prefix="/api")

    # Root endpoint
    @app.get("/")
    async def root(request: Request):
        """Root endpoint."""
        return {"message": "Cross-Broker Trading System Dashboard"}
    
    # Health check
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "system": "cross_broker_trading",
            "version": "0.1.0"
        }
    
    # Dashboard page
    @app.get("/dashboard")
    async def dashboard(request: Request):
        """Dashboard page."""
        if templates:
            return templates.TemplateResponse("dashboard.html", {"request": request})
        else:
            raise HTTPException(status_code=404, detail="Dashboard not available")
    
    # Store app instance
    _app = app
    
    logger.info("Dashboard application created")
    
    return app


def get_app() -> FastAPI:
    """
    Get the global FastAPI application instance.
    
    Returns:
        FastAPI application instance
    """
    global _app
    if _app is None:
        _app = create_app()
    return _app


def reset_app() -> None:
    """Reset the global application instance."""
    global _app
    _app = None


# For running with uvicorn
if __name__ == "__main__":
    import uvicorn
    
    config = get_config()
    host = config.get("broker", "settings.dashboard_host", "localhost")
    port = int(config.get("broker", "settings.dashboard_port", 8000))
    
    uvicorn.run(
        "src.dashboard.app:create_app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )
