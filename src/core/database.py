"""
Database Module

PostgreSQL database connectivity and ORM for the trading system.
Provides async and sync database operations.
"""

import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, List, Any, Union, AsyncGenerator
from contextlib import asynccontextmanager, contextmanager
import logging

from sqlalchemy import (
    create_engine,
    MetaData,
    Column,
    Integer,
    Float,
    String,
    Boolean,
    DateTime,
    Text,
    JSON,
    Index,
    func,
    select,
    insert,
    update,
    delete,
    and_,
    or_,
)
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    Session,
)
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    AsyncEngine,
)
from sqlalchemy.exc import SQLAlchemyError

from .config import get_config, DatabaseConnectionConfig


# Configure logging
logger = logging.getLogger(__name__)

# SQLAlchemy base. This must be the SAME Base every model (TradeCycle, Order,
# Position, Trade, RiskViolation, ...) actually subclasses - they all
# subclass models.base.Base, not a locally-declared one. Previously this
# module declared its own separate declarative_base() that no model ever
# used, so Database.create_tables()/drop_tables() operated on an empty
# metadata registry: calling create_tables() created zero tables for any
# real model, and persistence writes would fail against tables that were
# never created (that failure was, in turn, silently swallowed by callers -
# see trade_state.py).
from ..models.base import Base


class DatabaseError(Exception):
    """Database operation error."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Database connection error."""
    pass


class Database:
    """
    Synchronous database connection manager.
    
    Provides session management and basic CRUD operations.
    """
    
    def __init__(self, config: Optional[DatabaseConnectionConfig] = None):
        """
        Initialize database connection.
        
        Args:
            config: Database connection configuration
        """
        if config is None:
            config = get_config().get_database_connection_config()
        
        self.config = config
        self.engine = None
        self.Session = None
        self._initialized = False
    
    def _create_engine(self):
        """Create SQLAlchemy engine."""
        ssl_args = {}
        if self.config.ssl_enabled:
            ssl_args["sslmode"] = self.config.ssl_mode or "require"
        
        connection_string = (
            f"postgresql+psycopg2://"
            f"{self.config.user}:{self.config.password}@"
            f"{self.config.host}:{self.config.port}/{self.config.name}"
        )
        
        self.engine = create_engine(
            connection_string,
            pool_size=self.config.pool.max_size if hasattr(self.config, 'pool') else 10,
            max_overflow=self.config.pool.max_overflow if hasattr(self.config, 'pool') else 10,
            pool_timeout=self.config.pool.timeout_seconds if hasattr(self.config, 'pool') else 30,
            pool_recycle=self.config.pool.recycle_seconds if hasattr(self.config, 'pool') else 3600,
            **ssl_args
        )
        
        self.Session = sessionmaker(bind=self.engine)
        self._initialized = True
    
    def initialize(self) -> None:
        """Initialize database connection and create tables if needed."""
        if not self._initialized:
            self._create_engine()
        
        # Test connection
        try:
            with self.get_session() as session:
                from sqlalchemy import text
                session.execute(text("SELECT 1"))
            logger.info("Database connection established successfully")
        except Exception as e:
            logger.error(f"Failed to establish database connection: {e}")
            raise DatabaseConnectionError(f"Database connection failed: {e}")
    
    @contextmanager
    def get_session(self):
        """
        Get a database session.
        
        Yields:
            Database session
        """
        if not self._initialized:
            self.initialize()
        
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise DatabaseError(f"Database operation failed: {e}")
        finally:
            session.close()
    
    def create_tables(self) -> None:
        """Create all database tables."""
        if not self._initialized:
            self.initialize()
        
        try:
            Base.metadata.create_all(self.engine)
            logger.info("Database tables created/verified")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise DatabaseError(f"Table creation failed: {e}")
    
    def drop_tables(self) -> None:
        """Drop all database tables (DANGEROUS)."""
        if not self._initialized:
            self.initialize()
        
        try:
            Base.metadata.drop_all(self.engine)
            logger.warning("All database tables dropped")
        except Exception as e:
            logger.error(f"Failed to drop database tables: {e}")
            raise DatabaseError(f"Table drop failed: {e}")
    
    def execute(self, query: Any, params: Optional[Dict] = None) -> Any:
        """
        Execute a raw SQL query.
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            Query result
        """
        if not self._initialized:
            self.initialize()
        
        with self.get_session() as session:
            result = session.execute(query, params or {})
            return result
    
    def close(self) -> None:
        """Close database connection."""
        if self.engine:
            self.engine.dispose()
            self.engine = None
            self._initialized = False
            logger.info("Database connection closed")


class AsyncDatabase:
    """
    Asynchronous database connection manager.
    
    Provides async session management for high-performance operations.
    """
    
    def __init__(self, config: Optional[DatabaseConnectionConfig] = None):
        """
        Initialize async database connection.
        
        Args:
            config: Database connection configuration
        """
        if config is None:
            config = get_config().get_database_connection_config()
        
        self.config = config
        self.engine: Optional[AsyncEngine] = None
        self.async_session: Optional[sessionmaker] = None
        self._initialized = False
    
    async def _create_engine(self) -> None:
        """Create async SQLAlchemy engine."""
        ssl_args = {}
        if self.config.ssl_enabled:
            ssl_args["sslmode"] = self.config.ssl_mode or "require"
        
        connection_string = (
            f"postgresql+psycopg2://"
            f"{self.config.user}:{self.config.password}@"
            f"{self.config.host}:{self.config.port}/{self.config.name}"
        )
        
        # For async, we need to use asyncpg driver
        async_connection_string = connection_string.replace(
            "postgresql+psycopg2", "postgresql+asyncpg"
        )
        
        self.engine = create_async_engine(
            async_connection_string,
            pool_size=self.config.pool.max_size if hasattr(self.config, 'pool') else 10,
            max_overflow=self.config.pool.max_overflow if hasattr(self.config, 'pool') else 10,
            pool_timeout=self.config.pool.timeout_seconds if hasattr(self.config, 'pool') else 30,
            pool_recycle=self.config.pool.recycle_seconds if hasattr(self.config, 'pool') else 3600,
            **ssl_args
        )
        
        self.async_session = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        self._initialized = True
    
    async def initialize(self) -> None:
        """Initialize async database connection."""
        if not self._initialized:
            await self._create_engine()
        
        # Test connection
        try:
            async with self.get_session() as session:
                await session.execute("SELECT 1")
            logger.info("Async database connection established successfully")
        except Exception as e:
            logger.error(f"Failed to establish async database connection: {e}")
            raise DatabaseConnectionError(f"Async database connection failed: {e}")
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async database session.
        
        Yields:
            Async database session
        """
        if not self._initialized:
            await self.initialize()
        
        session = self.async_session()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Async database session error: {e}")
            raise DatabaseError(f"Async database operation failed: {e}")
        finally:
            await session.close()
    
    async def create_tables(self) -> None:
        """Create all database tables (async)."""
        if not self._initialized:
            await self.initialize()
        
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Async database tables created/verified")
        except Exception as e:
            logger.error(f"Failed to create async database tables: {e}")
            raise DatabaseError(f"Async table creation failed: {e}")
    
    async def drop_tables(self) -> None:
        """Drop all database tables (DANGEROUS - async)."""
        if not self._initialized:
            await self.initialize()
        
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            logger.warning("Async all database tables dropped")
        except Exception as e:
            logger.error(f"Failed to drop async database tables: {e}")
            raise DatabaseError(f"Async table drop failed: {e}")
    
    async def execute(self, query: Any, params: Optional[Dict] = None) -> Any:
        """
        Execute a raw SQL query (async).
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            Query result
        """
        if not self._initialized:
            await self.initialize()
        
        async with self.get_session() as session:
            result = await session.execute(query, params or {})
            return result
    
    async def close(self) -> None:
        """Close async database connection."""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self._initialized = False
            logger.info("Async database connection closed")


# Database connection managers
_sync_db: Optional[Database] = None
_async_db: Optional[AsyncDatabase] = None


def get_database() -> Database:
    """
    Get the global synchronous database instance.
    
    Returns:
        Database instance
    """
    global _sync_db
    if _sync_db is None:
        _sync_db = Database()
    return _sync_db


async def get_async_database() -> AsyncDatabase:
    """
    Get the global asynchronous database instance.
    
    Returns:
        AsyncDatabase instance
    """
    global _async_db
    if _async_db is None:
        _async_db = AsyncDatabase()
    return _async_db


def reset_database() -> None:
    """Reset the global database instances."""
    global _sync_db, _async_db
    if _sync_db:
        _sync_db.close()
        _sync_db = None
    _async_db = None


# Database models will be defined in src/models/
# Import them here for table creation
from ..models import (
    Trade,
    MarketData,
    Account,
    Position,
    Order,
    Rebate,
    TradeCycle,
    RiskViolation,
    ExecutionError,
    SystemLog,
)


def create_all_tables() -> None:
    """Create all database tables."""
    db = get_database()
    db.create_tables()


async def async_create_all_tables() -> None:
    """Create all database tables (async)."""
    db = await get_async_database()
    await db.create_tables()
