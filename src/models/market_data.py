"""
Market Data Model

Database model for market data storage.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    BigInteger,
    Index,
)

from .base import Base, BaseModel


class MarketData(BaseModel):
    """
    Market data model for storing ticks and bars.
    
    Stores bid/ask prices, volumes, and timestamps for
    historical analysis and replay.
    """
    
    __tablename__ = "market_data"
    
    # Data identification
    broker_id = Column(String(32), nullable=False, index=True)
    instrument = Column(String(16), nullable=False, index=True)
    
    # Price data
    bid = Column(Float, nullable=False)
    ask = Column(Float, nullable=False)
    mid = Column(Float, nullable=True)
    spread = Column(Float, nullable=True)
    
    # Volume data
    volume = Column(Float, nullable=False, default=0.0)
    tick_volume = Column(BigInteger, nullable=False, default=0)
    
    # Timestamps
    timestamp = Column(DateTime, nullable=False, index=True)
    server_timestamp = Column(DateTime, nullable=True)
    received_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Bar data (for aggregated data)
    timeframe = Column(String(8), nullable=True)  # M1, M5, H1, etc.
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    is_bar = Column(Integer, nullable=False, default=0)  # 0 = tick, 1 = bar
    
    # Additional metadata
    data_source = Column(String(32), nullable=True)  # live, recorded, simulated
    quality = Column(Integer, nullable=True)  # 0-100, data quality score
    
    # Indexes
    __table_args__ = (
        Index('idx_market_data_unique', 'broker_id', 'instrument', 'timestamp', unique=True),
        Index('idx_market_data_instrument_time', 'instrument', 'timestamp'),
        Index('idx_market_data_broker_time', 'broker_id', 'timestamp'),
    )
    
    @property
    def spread_points(self) -> float:
        """Calculate spread in points."""
        if self.spread:
            return self.spread
        if self.ask and self.bid:
            return self.ask - self.bid
        return 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary with additional computed fields."""
        data = super().to_dict()
        data.update({
            "spread_points": self.spread_points,
        })
        return data
