"""
Trade Model

Database model for trade records.
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


class TradeStatus(str, Enum):
    """Trade status enumeration."""
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class Trade(BaseModel):
    """
    Trade model representing a single trade execution.
    
    Stores all trade details including execution information,
    costs, and P&L calculations.
    """
    
    __tablename__ = "trades"
    
    # Trade identification
    trade_id = Column(String(64), unique=True, nullable=False, index=True)
    broker_id = Column(String(32), nullable=False, index=True)
    account_id = Column(String(32), nullable=False, index=True)
    
    # Trade details
    instrument = Column(String(16), nullable=False, index=True)
    side = Column(String(8), nullable=False)  # BUY or SELL
    volume = Column(Float, nullable=False)
    open_price = Column(Float, nullable=False)
    close_price = Column(Float, nullable=True)
    
    # Timestamps
    open_time = Column(DateTime, nullable=False, index=True)
    close_time = Column(DateTime, nullable=True, index=True)
    
    # Execution details
    order_id = Column(String(64), nullable=True)
    position_id = Column(String(64), nullable=True)
    magic_number = Column(Integer, nullable=True)
    comment = Column(Text, nullable=True)
    
    # Status
    status = Column(String(16), nullable=False, default=TradeStatus.PENDING.value)
    
    # Costs and P&L
    commission = Column(Float, nullable=False, default=0.0)
    swap = Column(Float, nullable=False, default=0.0)
    slippage = Column(Float, nullable=False, default=0.0)
    profit = Column(Float, nullable=False, default=0.0)
    
    # Strategy information
    strategy_id = Column(String(32), nullable=True, index=True)
    strategy_name = Column(String(64), nullable=True)
    
    # Cycle information (for paired trades)
    cycle_id = Column(String(64), ForeignKey("trade_cycles.cycle_id"), nullable=True, index=True)
    cycle_role = Column(String(16), nullable=True)  # broker_a, broker_b, runner
    
    # Rebate tracking
    rebate_eligible = Column(Boolean, nullable=False, default=False)
    rebate_amount = Column(Float, nullable=False, default=0.0)
    rebate_status = Column(String(16), nullable=True)  # pending, confirmed, rejected
    
    # Additional metadata
    bid_price = Column(Float, nullable=True)
    ask_price = Column(Float, nullable=True)
    spread = Column(Float, nullable=True)
    execution_delay_ms = Column(Integer, nullable=True)
    
    # Relationships
    cycle = relationship("TradeCycle", back_populates="trades")
    
    # Indexes
    __table_args__ = (
        Index('idx_trade_broker_instrument', 'broker_id', 'instrument'),
        Index('idx_trade_status', 'status'),
        Index('idx_trade_cycle', 'cycle_id'),
        Index('idx_trade_time', 'open_time', 'close_time'),
    )
    
    @property
    def is_open(self) -> bool:
        """Check if trade is still open."""
        return self.status == TradeStatus.OPEN.value
    
    @property
    def is_closed(self) -> bool:
        """Check if trade is closed."""
        return self.status == TradeStatus.CLOSED.value
    
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
        """Calculate total trade cost."""
        return self.commission + abs(self.swap) + abs(self.slippage)
    
    @property
    def net_profit(self) -> float:
        """Calculate net profit (profit - costs)."""
        return self.profit - self.total_cost
    
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
