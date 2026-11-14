"""
Account Model

Database model for account information.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    Boolean,
    Index,
)

from .base import Base, BaseModel


class Account(BaseModel):
    """
    Account model for storing broker account information.
    
    Tracks account balances, equity, margin, and other
    account-level metrics over time.
    """
    
    __tablename__ = "accounts"
    
    # Account identification
    broker_id = Column(String(32), nullable=False, index=True)
    account_id = Column(String(32), nullable=False, index=True)
    
    # Account details
    account_name = Column(String(128), nullable=True)
    account_type = Column(String(16), nullable=False)  # DEMO, REAL
    currency = Column(String(8), nullable=False, default="USD")
    leverage = Column(Integer, nullable=False, default=1)
    
    # Balance information
    balance = Column(Float, nullable=False)
    equity = Column(Float, nullable=False)
    free_margin = Column(Float, nullable=False)
    margin = Column(Float, nullable=False)
    margin_level = Column(Float, nullable=False)
    
    # Timestamps
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    is_connected = Column(Boolean, nullable=False, default=False)
    
    # Additional metadata
    last_trade_time = Column(DateTime, nullable=True)
    total_trades = Column(Integer, nullable=False, default=0)
    total_volume = Column(Float, nullable=False, default=0.0)
    total_commission = Column(Float, nullable=False, default=0.0)
    total_swap = Column(Float, nullable=False, default=0.0)
    total_profit = Column(Float, nullable=False, default=0.0)
    
    # Indexes
    __table_args__ = (
        Index('idx_account_unique', 'broker_id', 'account_id', 'timestamp', unique=True),
        Index('idx_account_broker', 'broker_id', 'account_id'),
        Index('idx_account_time', 'timestamp'),
    )
    
    @property
    def margin_percent(self) -> float:
        """Calculate margin percentage."""
        if self.equity > 0:
            return (self.free_margin / self.equity) * 100
        return 0.0
    
    @property
    def used_margin(self) -> float:
        """Calculate used margin."""
        return self.equity - self.free_margin
    
    def to_dict(self) -> dict:
        """Convert to dictionary with additional computed fields."""
        data = super().to_dict()
        data.update({
            "margin_percent": self.margin_percent,
            "used_margin": self.used_margin,
        })
        return data


class AccountBalance(BaseModel):
    """
    Account balance snapshot model.
    
    Stores periodic snapshots of account balances for
    tracking changes over time.
    """
    
    __tablename__ = "account_balances"
    
    # Account identification
    broker_id = Column(String(32), nullable=False, index=True)
    account_id = Column(String(32), nullable=False, index=True)
    
    # Balance snapshot
    balance = Column(Float, nullable=False)
    equity = Column(Float, nullable=False)
    free_margin = Column(Float, nullable=False)
    margin = Column(Float, nullable=False)
    
    # Timestamps
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # Change from previous
    balance_change = Column(Float, nullable=True)
    equity_change = Column(Float, nullable=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_balance_unique', 'broker_id', 'account_id', 'timestamp', unique=True),
        Index('idx_balance_time', 'timestamp'),
    )
