"""
Position Model

Database model for open and closed positions.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship

from .base import Base, BaseModel


class PositionStatus(str, Enum):
    """Position status enumeration."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CLOSING = "CLOSING"


class Position(BaseModel):
    """
    Position model representing open and closed positions.
    
    Tracks all position details including entry/exit prices,
    stop loss, take profit, and P&L.
    """
    
    __tablename__ = "positions"
    
    # Position identification
    position_id = Column(String(64), unique=True, nullable=False, index=True)
    broker_id = Column(String(32), nullable=False, index=True)
    account_id = Column(String(32), nullable=False, index=True)
    
    # Position details
    instrument = Column(String(16), nullable=False, index=True)
    side = Column(String(8), nullable=False)  # BUY or SELL
    volume = Column(Float, nullable=False)
    open_price = Column(Float, nullable=False)
    close_price = Column(Float, nullable=True)
    
    # Risk management
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    
    # Timestamps
    open_time = Column(DateTime, nullable=False, index=True)
    close_time = Column(DateTime, nullable=True, index=True)
    
    # Execution details
    order_id = Column(String(64), nullable=True)
    magic_number = Column(Integer, nullable=True)
    comment = Column(Text, nullable=True)
    
    # Status
    status = Column(String(16), nullable=False, default=PositionStatus.OPEN.value)
    
    # Costs and P&L
    commission = Column(Float, nullable=False, default=0.0)
    swap = Column(Float, nullable=False, default=0.0)
    profit = Column(Float, nullable=False, default=0.0)
    
    # Strategy information
    strategy_id = Column(String(32), nullable=True, index=True)
    strategy_name = Column(String(64), nullable=True)
    
    # Cycle information (for paired positions)
    cycle_id = Column(String(64), ForeignKey("trade_cycles.cycle_id"), nullable=True, index=True)
    cycle_role = Column(String(16), nullable=True)  # broker_a, broker_b, runner
    paired_position_id = Column(String(64), nullable=True)  # ID of paired position on other broker
    
    # Additional metadata
    bid_price = Column(Float, nullable=True)
    ask_price = Column(Float, nullable=True)
    spread_at_open = Column(Float, nullable=True)
    spread_at_close = Column(Float, nullable=True)
    
    # Relationships
    cycle = relationship("TradeCycle", back_populates="positions")
    
    # Indexes
    __table_args__ = (
        Index('idx_position_broker_instrument', 'broker_id', 'instrument'),
        Index('idx_position_status', 'status'),
        Index('idx_position_cycle', 'cycle_id'),
        Index('idx_position_time', 'open_time', 'close_time'),
        Index('idx_position_paired', 'paired_position_id'),
    )
    
    @property
    def is_open(self) -> bool:
        """Check if position is still open."""
        return self.status == PositionStatus.OPEN.value
    
    @property
    def is_closed(self) -> bool:
        """Check if position is closed."""
        return self.status == PositionStatus.CLOSED.value
    
    @property
    def holding_time_seconds(self) -> Optional[float]:
        """Calculate holding time in seconds."""
        if self.open_time and self.close_time:
            return (self.close_time - self.open_time).total_seconds()
        return None
    
    @property
    def holding_time_minutes(self) -> Optional[float]:
        """Calculate holding time in minutes."""
        seconds = self.holding_time_seconds
        if seconds is not None:
            return seconds / 60
        return None
    
    @property
    def total_cost(self) -> float:
        """Calculate total position cost."""
        return self.commission + abs(self.swap)
    
    @property
    def net_profit(self) -> float:
        """Calculate net profit (profit - costs)."""
        return self.profit - self.total_cost
    
    @property
    def unrealized_pnl(self) -> Optional[float]:
        """Calculate unrealized P&L if position is open."""
        if self.is_open and self.side and self.open_price:
            # This would need current price from market data
            # For now, return None as we don't have current price in the model
            return None
        return 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary with additional computed fields."""
        data = super().to_dict()
        data.update({
            "is_open": self.is_open,
            "is_closed": self.is_closed,
            "holding_time_seconds": self.holding_time_seconds,
            "holding_time_minutes": self.holding_time_minutes,
            "total_cost": self.total_cost,
            "net_profit": self.net_profit,
        })
        return data
