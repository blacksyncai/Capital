"""
Dashboard API Routes

REST API endpoints for the trading dashboard.
"""

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

from ..core.config import get_config
from ..core.logging import get_logger
from ..execution.order_manager import get_order_manager, OrderManager
from ..execution.trade_state import get_trade_state_manager, TradeStateManager
from ..execution.execution_worker import get_execution_worker, start_execution_worker
from ..risk.risk_engine import get_risk_engine, RiskEngine
from ..strategies import (
    get_paired_exit_strategy,
    get_protected_runner_strategy,
    get_market_condition_exits_strategy,
    get_adaptive_holding_strategy,
    get_entry_optimization_strategy,
)
from ..ai_research import get_data_analyzer, get_pattern_detector, get_report_generator


# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1", tags=["dashboard"])


# Dependency functions
def get_order_manager_dep() -> OrderManager:
    """Get order manager dependency."""
    return get_order_manager()


def get_trade_state_dep() -> TradeStateManager:
    """Get trade state manager dependency."""
    return get_trade_state_manager()


def get_execution_worker_dep() -> Any:
    """Get execution worker dependency."""
    return get_execution_worker()


def get_risk_engine_dep() -> RiskEngine:
    """Get risk engine dependency."""
    return get_risk_engine()


# System status endpoints
@router.get("/status")
async def get_system_status(
    order_manager: OrderManager = Depends(get_order_manager_dep),
    trade_state: TradeStateManager = Depends(get_trade_state_dep),
    execution_worker: Any = Depends(get_execution_worker_dep),
    risk_engine: RiskEngine = Depends(get_risk_engine_dep)
) -> Dict[str, Any]:
    """
    Get overall system status.
    
    Returns:
        System status dictionary
    """
    try:
        # Get broker connections
        broker_status = {}
        for broker_id in ["vantage", "justmarkets"]:
            try:
                connected = order_manager.is_connected(broker_id)
                broker_status[broker_id] = {
                    "connected": connected,
                    "account_info": order_manager.get_account_info(broker_id)
                }
            except Exception as e:
                broker_status[broker_id] = {"connected": False, "error": str(e)}
        
        # Get active cycles
        active_cycles = trade_state.get_active_cycles()
        
        # Get execution worker status
        worker_status = execution_worker.get_status() if hasattr(execution_worker, 'get_status') else {}
        
        # Get risk engine status
        risk_status = risk_engine.get_status()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "system": "cross_broker_trading",
            "version": "0.1.0",
            "brokers": broker_status,
            "execution": worker_status,
            "risk": risk_status,
            "active_cycles": len(active_cycles),
            "trading_mode": get_config().get_trading_mode(),
            "live_trading_enabled": get_config().is_live_trading_enabled()
        }
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/brokers")
async def get_broker_status(
    order_manager: OrderManager = Depends(get_order_manager_dep)
) -> Dict[str, Any]:
    """
    Get detailed broker status.
    
    Returns:
        Broker status dictionary
    """
    try:
        broker_status = {}
        
        for broker_id in ["vantage", "justmarkets"]:
            try:
                connected = order_manager.is_connected(broker_id)
                account_info = order_manager.get_account_info(broker_id)
                positions = order_manager.get_open_positions(broker_id)
                
                broker_status[broker_id] = {
                    "connected": connected,
                    "account": account_info.to_dict() if account_info else None,
                    "open_positions": len(positions),
                    "positions": [p.to_dict() for p in positions] if positions else []
                }
            except Exception as e:
                broker_status[broker_id] = {"connected": False, "error": str(e)}
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "brokers": broker_status
        }
    except Exception as e:
        logger.error(f"Error getting broker status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cycles")
async def get_cycles(
    limit: int = 100,
    status: Optional[str] = None,
    strategy: Optional[str] = None,
    trade_state: TradeStateManager = Depends(get_trade_state_dep)
) -> Dict[str, Any]:
    """
    Get trade cycles.
    
    Query Parameters:
        limit: Maximum number of cycles to return
        status: Filter by status (OPEN, CLOSED, etc.)
        strategy: Filter by strategy ID
        
    Returns:
        Dictionary with cycle list
    """
    try:
        # Get active cycles
        active_cycles = trade_state.get_active_cycles()
        
        # Get completed cycles
        completed_cycles = trade_state.get_completed_cycles(limit)
        
        # Filter by status
        if status:
            if status.upper() == "ACTIVE":
                cycles = list(active_cycles.values())
            elif status.upper() == "COMPLETED":
                cycles = completed_cycles
            else:
                cycles = []
        else:
            cycles = list(active_cycles.values()) + completed_cycles
        
        # Filter by strategy
        if strategy:
            cycles = [c for c in cycles if c.strategy_id == strategy]
        
        # Limit
        cycles = cycles[:limit]
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_active": len(active_cycles),
            "total_completed": len(completed_cycles),
            "returned": len(cycles),
            "cycles": [c.to_dict() for c in cycles]
        }
    except Exception as e:
        logger.error(f"Error getting cycles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cycles/{cycle_id}")
async def get_cycle(
    cycle_id: str,
    trade_state: TradeStateManager = Depends(get_trade_state_dep)
) -> Dict[str, Any]:
    """
    Get a specific trade cycle.
    
    Path Parameters:
        cycle_id: Cycle ID
        
    Returns:
        Cycle details
    """
    try:
        cycle = trade_state.get_cycle_state(cycle_id)
        
        if cycle is None:
            raise HTTPException(status_code=404, detail=f"Cycle {cycle_id} not found")
        
        # Get P&L
        pnl_info = trade_state.get_cycle_pnl(cycle_id)
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "cycle": cycle.to_dict(),
            "pnl": pnl_info
        }
    except Exception as e:
        logger.error(f"Error getting cycle {cycle_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pnl")
async def get_pnl(
    trade_state: TradeStateManager = Depends(get_trade_state_dep)
) -> Dict[str, Any]:
    """
    Get P&L for all active cycles.
    
    Returns:
        P&L information for all active cycles
    """
    try:
        pnl_data = trade_state.get_all_pnl()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_active_cycles": len(pnl_data),
            "pnl_data": pnl_data
        }
    except Exception as e:
        logger.error(f"Error getting P&L: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risk")
async def get_risk_status(
    risk_engine: RiskEngine = Depends(get_risk_engine_dep)
) -> Dict[str, Any]:
    """
    Get risk engine status.
    
    Returns:
        Risk engine status
    """
    try:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "risk_status": risk_engine.get_status()
        }
    except Exception as e:
        logger.error(f"Error getting risk status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risk/violations")
async def get_risk_violations(
    severity: Optional[str] = None,
    acknowledged: Optional[bool] = False,
    risk_engine: RiskEngine = Depends(get_risk_engine_dep)
) -> Dict[str, Any]:
    """
    Get risk violations.
    
    Query Parameters:
        severity: Filter by severity (LOW, MEDIUM, HIGH, CRITICAL)
        acknowledged: Filter by acknowledged status
        
    Returns:
        List of risk violations
    """
    try:
        violations = risk_engine.get_violations()
        
        # Filter
        if severity:
            violations = [v for v in violations if v.severity.value == severity.upper()]
        
        if acknowledged is not None:
            violations = [v for v in violations if v.is_acknowledged == acknowledged]
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_violations": len(violations),
            "violations": [v.to_dict() for v in violations]
        }
    except Exception as e:
        logger.error(f"Error getting risk violations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/risk/acknowledge/{violation_id}")
async def acknowledge_violation(
    violation_id: str,
    risk_engine: RiskEngine = Depends(get_risk_engine_dep)
) -> Dict[str, Any]:
    """
    Acknowledge a risk violation.
    
    Path Parameters:
        violation_id: Violation ID
        
    Returns:
        Acknowledgment status
    """
    try:
        success = risk_engine.acknowledge_violation(violation_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Violation {violation_id} not found")
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "violation_id": violation_id,
            "acknowledged": True
        }
    except Exception as e:
        logger.error(f"Error acknowledging violation {violation_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Trading control endpoints
@router.post("/trade/open")
async def open_trade(
    instrument: str = "XAUUSD",
    lot_size: float = 0.01,
    direction: str = "BUY_SELL",
    strategy: str = "paired_exit",
    execution_worker: Any = Depends(get_execution_worker_dep)
) -> Dict[str, Any]:
    """
    Open a new trade cycle.
    
    Query Parameters:
        instrument: Trading instrument
        lot_size: Lot size per broker
        direction: Trade direction (BUY_SELL or SELL_BUY)
        strategy: Strategy ID
        
    Returns:
        Cycle ID and status
    """
    try:
        # Check if live trading is enabled
        if not get_config().is_live_trading_enabled():
            raise HTTPException(
                status_code=403,
                detail="Live trading is not enabled. Set LIVE_TRADING_ENABLED=true and TRADING_MODE=LIVE in configuration."
            )
        
        # Open cycle
        cycle_id = execution_worker.open_cycle(
            instrument=instrument,
            lot_size=lot_size,
            direction=direction,
            strategy_id=strategy
        )
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "cycle_id": cycle_id,
            "status": "cycle_created",
            "message": f"Trade cycle {cycle_id} created and queued for execution"
        }
    except Exception as e:
        logger.error(f"Error opening trade: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trade/close/{cycle_id}")
async def close_trade(
    cycle_id: str,
    reason: str = "manual",
    comment: str = "",
    execution_worker: Any = Depends(get_execution_worker_dep)
) -> Dict[str, Any]:
    """
    Close a trade cycle.
    
    Path Parameters:
        cycle_id: Cycle ID
        
    Query Parameters:
        reason: Reason for closing
        comment: Additional comment
        
    Returns:
        Close status
    """
    try:
        execution_worker.close_cycle(cycle_id, reason, comment)
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "cycle_id": cycle_id,
            "status": "close_requested",
            "message": f"Close request submitted for cycle {cycle_id}"
        }
    except Exception as e:
        logger.error(f"Error closing trade {cycle_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emergency/stop")
async def emergency_stop(
    reason: str = "manual_trigger",
    execution_worker: Any = Depends(get_execution_worker_dep),
    risk_engine: RiskEngine = Depends(get_risk_engine_dep)
) -> Dict[str, Any]:
    """
    Trigger emergency stop.
    
    Query Parameters:
        reason: Reason for emergency stop
        
    Returns:
        Emergency stop status
    """
    try:
        # Trigger risk engine emergency stop
        risk_engine.trigger_emergency_stop(reason)
        
        # Trigger execution worker emergency stop
        execution_worker.emergency_stop(reason)
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "status": "emergency_stop_triggered",
            "message": f"Emergency stop triggered: {reason}",
            "warning": "All active positions will be closed"
        }
    except Exception as e:
        logger.error(f"Error triggering emergency stop: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emergency/clear")
async def clear_emergency(
    risk_engine: RiskEngine = Depends(get_risk_engine_dep)
) -> Dict[str, Any]:
    """
    Clear emergency stop.
    
    Returns:
        Clear status
    """
    try:
        risk_engine.clear_emergency_stop()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "status": "emergency_stop_cleared",
            "message": "Emergency stop has been cleared"
        }
    except Exception as e:
        logger.error(f"Error clearing emergency stop: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Strategy endpoints
@router.get("/strategies")
async def get_strategies() -> Dict[str, Any]:
    """
    Get list of available strategies.
    
    Returns:
        List of strategies
    """
    try:
        strategies = {
            "paired_exit": {
                "id": "paired_exit",
                "name": "Paired Exit",
                "description": "Open opposing positions and close both when combined P&L reaches target"
            },
            "protected_runner": {
                "id": "protected_runner",
                "name": "Protected Runner",
                "description": "Close one position and allow the remaining to run with protective stop"
            },
            "market_condition_exits": {
                "id": "market_condition_exits",
                "name": "Market Condition Exits",
                "description": "Exit based on volatility, momentum, spread conditions, and market sessions"
            },
            "adaptive_holding": {
                "id": "adaptive_holding",
                "name": "Adaptive Holding",
                "description": "Compare different holding periods to optimize P&L and costs"
            },
            "entry_optimization": {
                "id": "entry_optimization",
                "name": "Entry Optimization",
                "description": "Delay entries until spreads and execution conditions improve"
            }
        }
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "strategies": strategies
        }
    except Exception as e:
        logger.error(f"Error getting strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies/{strategy_id}")
async def get_strategy_status(strategy_id: str) -> Dict[str, Any]:
    """
    Get status of a specific strategy.
    
    Path Parameters:
        strategy_id: Strategy ID
        
    Returns:
        Strategy status
    """
    try:
        # Get strategy instance
        strategy_map = {
            "paired_exit": get_paired_exit_strategy,
            "protected_runner": get_protected_runner_strategy,
            "market_condition_exits": get_market_condition_exits_strategy,
            "adaptive_holding": get_adaptive_holding_strategy,
            "entry_optimization": get_entry_optimization_strategy,
        }
        
        if strategy_id not in strategy_map:
            raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
        
        strategy = strategy_map[strategy_id]()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "strategy_id": strategy_id,
            "status": strategy.get_status()
        }
    except Exception as e:
        logger.error(f"Error getting strategy {strategy_id} status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Analysis endpoints
@router.get("/analysis/performance/{strategy_id}")
async def get_strategy_performance(
    strategy_id: str,
    days: int = 30
) -> Dict[str, Any]:
    """
    Get performance analysis for a strategy.
    
    Path Parameters:
        strategy_id: Strategy ID
        
    Query Parameters:
        days: Number of days to analyze
        
    Returns:
        Performance analysis
    """
    try:
        data_analyzer = get_data_analyzer()
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        analysis = data_analyzer.analyze_strategy_performance(
            strategy_id, start_date=start_date
        )
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "analysis": analysis.to_dict()
        }
    except Exception as e:
        logger.error(f"Error getting strategy performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis/comparison")
async def get_strategy_comparison(
    strategy_ids: str = "paired_exit,protected_runner",
    days: int = 30
) -> Dict[str, Any]:
    """
    Compare multiple strategies.
    
    Query Parameters:
        strategy_ids: Comma-separated list of strategy IDs
        days: Number of days to analyze
        
    Returns:
        Strategy comparison
    """
    try:
        data_analyzer = get_data_analyzer()
        
        start_date = datetime.utcnow() - timedelta(days=days)
        strategy_list = [s.strip() for s in strategy_ids.split(",")]
        
        comparisons = data_analyzer.compare_strategies(
            strategy_list, start_date=start_date
        )
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "comparisons": [c.__dict__ for c in comparisons]
        }
    except Exception as e:
        logger.error(f"Error getting strategy comparison: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis/patterns/{strategy_id}")
async def get_patterns(
    strategy_id: str,
    days: int = 30
) -> Dict[str, Any]:
    """
    Get pattern analysis for a strategy.
    
    Path Parameters:
        strategy_id: Strategy ID
        
    Query Parameters:
        days: Number of days to analyze
        
    Returns:
        Pattern analysis
    """
    try:
        pattern_detector = get_pattern_detector()
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        patterns = pattern_detector.detect_all_patterns(
            strategy_id, start_date=start_date
        )
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "patterns": patterns.to_dict()
        }
    except Exception as e:
        logger.error(f"Error getting patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/generate")
async def generate_report(
    report_type: str = "strategy_performance",
    strategy_ids: str = "paired_exit",
    days: int = 30,
    format: str = "json"
) -> Dict[str, Any]:
    """
    Generate a report.
    
    Query Parameters:
        report_type: Type of report (strategy_performance, comparison, patterns, execution, comprehensive)
        strategy_ids: Comma-separated list of strategy IDs
        days: Number of days to analyze
        format: Output format (json, text, html, markdown)
        
    Returns:
        Generated report
    """
    try:
        report_generator = get_report_generator()
        
        start_date = datetime.utcnow() - timedelta(days=days)
        strategy_list = [s.strip() for s in strategy_ids.split(",")]
        
        if report_type == "strategy_performance" and strategy_list:
            report = report_generator.generate_strategy_report(
                strategy_list[0], start_date=start_date
            )
        elif report_type == "comparison":
            report = report_generator.generate_comparison_report(
                strategy_list, start_date=start_date
            )
        elif report_type == "patterns":
            report = report_generator.generate_pattern_report(start_date=start_date)
        elif report_type == "execution":
            report = report_generator.generate_execution_report(start_date=start_date)
        elif report_type == "comprehensive":
            report = report_generator.generate_comprehensive_report(
                strategy_list, start_date=start_date
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown report type: {report_type}"
            )
        
        # Format the report
        formatted = report_generator.format_report(report, format)
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "report_id": report.report_id,
            "report_type": report.report_type,
            "format": format,
            "content": formatted
        }
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Market data endpoints
@router.get("/market/tick/{instrument}")
async def get_tick(
    instrument: str,
    order_manager: OrderManager = Depends(get_order_manager_dep)
) -> Dict[str, Any]:
    """
    Get current tick data for an instrument.
    
    Path Parameters:
        instrument: Instrument symbol
        
    Returns:
        Tick data from both brokers
    """
    try:
        ticks = {}
        
        for broker_id in ["vantage", "justmarkets"]:
            try:
                tick = order_manager.get_tick(broker_id, instrument)
                if tick:
                    ticks[broker_id] = {
                        "bid": tick.bid,
                        "ask": tick.ask,
                        "spread": tick.spread,
                        "timestamp": tick.timestamp.isoformat() if hasattr(tick, 'timestamp') else None
                    }
            except Exception as e:
                ticks[broker_id] = {"error": str(e)}
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "instrument": instrument,
            "ticks": ticks
        }
    except Exception as e:
        logger.error(f"Error getting tick for {instrument}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/bars/{instrument}")
async def get_bars(
    instrument: str,
    timeframe: str = "M1",
    count: int = 100,
    order_manager: OrderManager = Depends(get_order_manager_dep)
) -> Dict[str, Any]:
    """
    Get historical bar data.
    
    Path Parameters:
        instrument: Instrument symbol
        
    Query Parameters:
        timeframe: Timeframe (M1, M5, H1, etc.)
        count: Number of bars
        
    Returns:
        Bar data from both brokers
    """
    try:
        bars = {}
        
        for broker_id in ["vantage", "justmarkets"]:
            try:
                broker_bars = order_manager.get_bars(
                    broker_id, instrument, timeframe, count
                )
                bars[broker_id] = [
                    {
                        "open_time": b.open_time.isoformat(),
                        "close_time": b.close_time.isoformat(),
                        "open": b.open,
                        "high": b.high,
                        "low": b.low,
                        "close": b.close,
                        "volume": b.volume
                    }
                    for b in broker_bars
                ]
            except Exception as e:
                bars[broker_id] = {"error": str(e)}
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "instrument": instrument,
            "timeframe": timeframe,
            "count": count,
            "bars": bars
        }
    except Exception as e:
        logger.error(f"Error getting bars for {instrument}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
