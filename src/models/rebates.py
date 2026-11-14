"""
Rebate Model

Database model for IB rebate tracking.
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


class RebateStatus(str, Enum):
    """Rebate status enumeration."""
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    REVERSED = "REVERSED"


class Rebate(BaseModel):
    """
    Rebate model for tracking IB rebates.
    
    Tracks eligible trades, calculated rebates, and actual payouts.
    """
    
    __tablename__ = "ib_rebates"
    
    # Rebate identification
    rebate_id = Column(String(64), unique=True, nullable=False, index=True)
    
    # Related trade
    broker_id = Column(String(32), nullable=False, index=True)
    trade_id = Column(String(64), ForeignKey("trades.trade_id"), nullable=False, index=True)
    position_id = Column(String(64), nullable=True)
    
    # Trade details
    instrument = Column(String(16), nullable=False)
    volume = Column(Float, nullable=False)
    side = Column(String(8), nullable=False)
    
    # Timestamps
    trade_time = Column(DateTime, nullable=False)
    holding_time_minutes = Column(Float, nullable=False)
    calculated_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    confirmed_time = Column(DateTime, nullable=True)
    paid_time = Column(DateTime, nullable=True)
    
    # Rebate calculation
    rebate_per_lot = Column(Float, nullable=False)
    calculated_amount = Column(Float, nullable=False)
    confirmed_amount = Column(Float, nullable=True)
    paid_amount = Column(Float, nullable=True)
    currency = Column(String(8), nullable=False, default="USD")
    
    # Status
    status = Column(String(16), nullable=False, default=RebateStatus.PENDING.value)
    
    # Eligibility
    is_eligible = Column(Boolean, nullable=False, default=True)
    eligibility_reason = Column(Text, nullable=True)
    
    # Additional metadata
    cycle_id = Column(String(64), nullable=True, index=True)
    account_id = Column(String(32), nullable=True)
    magic_number = Column(Integer, nullable=True)
    
    # Relationships
    trade = relationship("Trade", viewonly=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_rebate_trade', 'broker_id', 'trade_id', unique=True),
        Index('idx_rebate_status', 'status'),
        Index('idx_rebate_time', 'trade_time', 'calculated_time'),
        Index('idx_rebate_cycle', 'cycle_id'),
    )
    
    @property
    def is_pending(self) -> bool:
        """Check if rebate is pending."""
        return self.status == RebateStatus.PENDING.value
    
    @property
    def is_confirmed(self) -> bool:
        """Check if rebate is confirmed."""
        return self.status == RebateStatus.CONFIRMED.value
    
    @property
    def is_paid(self) -> bool:
        """Check if rebate is paid."""
        return self.paid_amount is not None and self.paid_time is not None
    
    @property
    def standard_lots(self) -> float:
        """Calculate volume in standard lots."""
        return self.volume
    
    def to_dict(self) -> dict:
        """Convert to dictionary with additional computed fields."""
        data = super().to_dict()
        data.update({
            "is_pending": self.is_pending,
            "is_confirmed": self.is_confirmed,
            "is_paid": self.is_paid,
            "standard_lots": self.standard_lots,
        })
        return data
