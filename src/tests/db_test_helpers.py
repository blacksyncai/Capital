"""
A real, working test database.

Trade-state persistence failures are no longer allowed to be silently
swallowed (see trade_state.py), which means any test that exercises
persistence needs a database that actually works, rather than relying on
a missing Postgres connection failing and being quietly ignored (which is
exactly the behavior that was removed). This gives tests a genuine,
in-memory SQLite-backed Database, built on the real model metadata, so
reads and writes are real instead of mocked away.
"""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.database import Database, DatabaseError
from src.models.base import Base
from src.models.trade_cycles import TradeCycle
from src.models.trades import Trade
from src.models.positions import Position as PositionModel
from src.models.orders import Order as OrderModel
from src.models.risk_violations import RiskViolation

# Only create tables for the models trade_state.py / risk_engine.py actually
# use. Importing the full src.models package (to get every model's table
# registered) pulls in system_logs.py, whose composite primary key isn't
# representable in SQLite - irrelevant to what these tests need anyway.
_TEST_TABLES = [
    TradeCycle.__table__,
    Trade.__table__,
    PositionModel.__table__,
    OrderModel.__table__,
    RiskViolation.__table__,
]


class SQLiteTestDatabase(Database):
    """
    Drop-in replacement for Database, backed by an in-memory SQLite
    database shared across sessions (StaticPool - a bare ":memory:" sqlite
    database is otherwise one-connection-only, so a second session would
    see an empty database).
    """

    def __init__(self):
        self.config = None
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.Session = sessionmaker(bind=self.engine)
        self._initialized = True
        Base.metadata.create_all(self.engine, tables=_TEST_TABLES)

    @contextmanager
    def get_session(self):
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise DatabaseError(f"Database operation failed: {e}")
        finally:
            session.close()
