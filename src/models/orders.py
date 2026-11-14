"""
Order Model

Database model for order records.
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
    Text,
    Index,
)

from .base import Base, BaseModel


class OrderType(str, Enum):
    """Order type enumeration."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    """Order status enumeration."""
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class Order(BaseModel):
    """
    Order model representing all order types.
    
    Tracks order details, execution, and status changes.
    """
    
    __tablename__ = "orders"
    
    # Order identification
    order_id = Column(String(64), unique=True, nullable=False, index=True)
    broker_id = Column(String(32), nullable=False, index=True)
    account_id = Column(String(32), nullable=False, index=True)
    
    # Order details
    instrument = Column(String(16), nullable=False, index=True)
    order_type = Column(String(16), nullable=False)  # MARKET, LIMIT, STOP, STOP_LIMIT
    side = Column(String(8), nullable=False)  # BUY or SELL
    volume = Column(Float, nullable=False)
    requested_volume = Column(Float, nullable=False)
    
    # Prices
    price = Column(Float, nullable=True)  # For LIMIT orders
    filled_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    
    # Timestamps
    timestamp = Column(DateTime, nullable=False, index=True)
    filled_time = Column(DateTime, nullable=True)
    cancelled_time = Column(DateTime, nullable=True)
    expired_time = Column(DateTime, nullable=True)
    
    # Execution details
    status = Column(String(16), nullable=False, default=OrderStatus.PENDING.value)
    filled_volume = Column(Float, nullable=False, default=0.0)
    
    # Costs
    commission = Column(Float, nullable=False, default=0.0)
    swap = Column(Float, nullable=False, default=0.0)
    slippage = Column(Float, nullable=False, default=0.0)
    
    # Additional metadata
    magic_number = Column(Integer, nullable=True)
    comment = Column(Text, nullable=True)
    position_id = Column(String(64), nullable=True)
    
    # Strategy information
    strategy_id = Column(String(32), nullable=True, index=True)
    strategy_name = Column(String(64), nullable=True)
    
    # Cycle information
    cycle_id = Column(String(64), nullable=True, index=True)
    cycle_role = Column(String(16), nullable=True)
    
    # Error information
    error_code = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_order_broker_instrument', 'broker_id', 'instrument'),
        Index('idx_order_status', 'status'),
        Index('idx_order_time', 'timestamp', 'filled_time'),
        Index('idx_order_cycle', 'cycle_id'),
    )
    
    @property
    def is_pending(self) -> bool:
        """Check if order is still pending."""
        return self.status == OrderStatus.PENDING.value
    
    @property
    def is_filled(self) -> bool:
        """Check if order is filled."""
        return self.status == OrderStatus.FILLED.value
    
    @property
    def is_cancelled(self) -> bool:
        """Check if order is cancelled."""
        return self.status == OrderStatus.CANCELLED.value
    
    @property
    def is_rejected(self) -> bool:
        """Check if order is rejected."""
        return self.status == OrderStatus.REJECTED.value
    
    @property
    def execution_time_seconds(self) -> Optional[float]:
        """Calculate execution time in seconds."""
        if self.timestamp and self.filled_time:
            return (self.filled_time - self.timestamp).total_seconds()
        return None
    
    @property
    def remaining_volume(self) -> float:
        """Calculate remaining volume to be filled."""
        return self.requested_volume - self.filled_volume
    
    def to_dict(self) -> dict:
        """Convert to dictionary with additional computed fields."""
        data = super().to_dict()
        data.update({
            "is_pending": self.is_pending,
            "is_filled": self.is_filled,
            "is_cancelled": self.is_cancelled,
            "is_rejected": self.is_rejected,
            "execution_time_seconds": self.execution_time_seconds,
            "remaining_volume": self.remaining_volume,
        })
        return data
