"""
Trade Cycle Model

Database model for paired trade cycles.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    Boolean,
    Text,
    Index,
)
from sqlalchemy.orm import relationship

from .base import Base, BaseModel


class CycleStatus(str, Enum):
    """Cycle status enumeration."""
    INITIATED = "INITIATED"
    OPENING = "OPENING"
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class TradeCycle(BaseModel):
    """
    Trade cycle model representing a paired trading cycle.
    
    A cycle consists of two opposing positions on different brokers
    that are managed together.
    """
    
    __tablename__ = "trade_cycles"
    
    # Cycle identification
    cycle_id = Column(String(64), unique=True, nullable=False, index=True)
    
    # Cycle configuration
    strategy_id = Column(String(32), nullable=False, index=True)
    strategy_name = Column(String(64), nullable=False)
    instrument = Column(String(16), nullable=False, index=True)
    
    # Position configuration
    broker_a_id = Column(String(32), nullable=False)
    broker_b_id = Column(String(32), nullable=False)
    lot_size = Column(Float, nullable=False)
    direction = Column(String(16), nullable=False)  # BUY_SELL or SELL_BUY
    
    # Timestamps
    initiated_time = Column(DateTime, nullable=False, index=True)
    opened_time = Column(DateTime, nullable=True)
    closed_time = Column(DateTime, nullable=True)
    
    # Status
    status = Column(String(16), nullable=False, default=CycleStatus.INITIATED.value)
    
    # Position references
    position_a_id = Column(String(64), nullable=True)
    position_b_id = Column(String(64), nullable=True)
    trade_a_id = Column(String(64), nullable=True)
    trade_b_id = Column(String(64), nullable=True)
    
    # P&L tracking
    combined_pnl = Column(Float, nullable=False, default=0.0)
    broker_a_pnl = Column(Float, nullable=False, default=0.0)
    broker_b_pnl = Column(Float, nullable=False, default=0.0)
    
    # Costs
    total_commission = Column(Float, nullable=False, default=0.0)
    total_swap = Column(Float, nullable=False, default=0.0)
    total_slippage = Column(Float, nullable=False, default=0.0)
    
    # Rebates
    total_rebate_eligible = Column(Float, nullable=False, default=0.0)
    total_rebate_confirmed = Column(Float, nullable=False, default=0.0)
    
    # Exit conditions
    exit_reason = Column(String(64), nullable=True)  # target, stop_loss, time, manual, etc.
    exit_comment = Column(Text, nullable=True)
    
    # Risk management
    max_loss_reached = Column(Boolean, nullable=False, default=False)
    max_holding_time_reached = Column(Boolean, nullable=False, default=False)
    emergency_stop_triggered = Column(Boolean, nullable=False, default=False)
    
    # Additional metadata
    magic_number = Column(Integer, nullable=True)
    comment = Column(Text, nullable=True)
    
    # Relationships
    trades = relationship("Trade", back_populates="cycle", foreign_keys="[Trade.cycle_id]")
    positions = relationship("Position", back_populates="cycle", foreign_keys="[Position.cycle_id]")
    
    # Indexes
    __table_args__ = (
        Index('idx_cycle_status', 'status'),
        Index('idx_cycle_strategy', 'strategy_id', 'strategy_name'),
        Index('idx_cycle_time', 'initiated_time', 'opened_time', 'closed_time'),
        Index('idx_cycle_instrument', 'instrument'),
    )
    
    @property
    def is_open(self) -> bool:
        """Check if cycle is still open."""
        return self.status in [CycleStatus.OPEN.value, CycleStatus.OPENING.value, CycleStatus.CLOSING.value]
    
    @property
    def is_closed(self) -> bool:
        """Check if cycle is closed."""
        return self.status == CycleStatus.CLOSED.value
    
    @property
    def is_complete(self) -> bool:
        """Check if cycle is complete (both positions opened and closed)."""
        return (
            self.position_a_id is not None
            and self.position_b_id is not None
            and self.status == CycleStatus.CLOSED.value
        )
    
    @property
    def holding_time_seconds(self) -> Optional[float]:
        """Calculate holding time in seconds."""
        if self.opened_time and self.closed_time:
            return (self.closed_time - self.opened_time).total_seconds()
        return None
    
    @property
    def holding_time_minutes(self) -> Optional[float]:
        """Calculate holding time in minutes."""
        seconds = self.holding_time_seconds
        if seconds is not None:
            return seconds / 60
        return None
    
    @property
    def net_profit(self) -> float:
        """Calculate net profit including costs."""
        return self.combined_pnl - (self.total_commission + self.total_swap + self.total_slippage)
    
    @property
    def net_profit_with_rebates(self) -> float:
        """Calculate net profit including rebates."""
        return self.net_profit + self.total_rebate_confirmed
    
    @property
    def both_positions_opened(self) -> bool:
        """Check if both positions are opened."""
        return self.position_a_id is not None and self.position_b_id is not None
    
    @property
    def both_positions_closed(self) -> bool:
        """Check if both positions are closed."""
        return self.closed_time is not None and self.status == CycleStatus.CLOSED.value
    
    def get_broker_a_direction(self) -> str:
        """Get direction for broker A."""
        if self.direction == "BUY_SELL":
            return "BUY"
        else:
            return "SELL"
    
    def get_broker_b_direction(self) -> str:
        """Get direction for broker B."""
        if self.direction == "BUY_SELL":
            return "SELL"
        else:
            return "BUY"
    
    def to_dict(self) -> dict:
        """Convert to dictionary with additional computed fields."""
        data = super().to_dict()
        data.update({
            "is_open": self.is_open,
            "is_closed": self.is_closed,
            "is_complete": self.is_complete,
            "holding_time_seconds": self.holding_time_seconds,
            "holding_time_minutes": self.holding_time_minutes,
            "net_profit": self.net_profit,
            "net_profit_with_rebates": self.net_profit_with_rebates,
            "both_positions_opened": self.both_positions_opened,
            "both_positions_closed": self.both_positions_closed,
            "broker_a_direction": self.get_broker_a_direction(),
            "broker_b_direction": self.get_broker_b_direction(),
        })
        return data
