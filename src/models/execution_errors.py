"""
Execution Error Model

Database model for execution errors.
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
    Text,
    Index,
)

from .base import Base, BaseModel


class ExecutionError(BaseModel):
    """
    Execution error model for tracking all execution failures.
    
    Records order failures, connection issues, and other execution problems.
    """
    
    __tablename__ = "execution_errors"
    
    # Error identification
    error_id = Column(String(64), unique=True, nullable=False, index=True)
    
    # Timestamps
    timestamp = Column(DateTime, nullable=False, index=True)
    retry_timestamp = Column(DateTime, nullable=True)
    
    # Error details
    error_type = Column(String(64), nullable=False, index=True)
    error_code = Column(Integer, nullable=True)
    message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    
    # Related entities
    broker_id = Column(String(32), nullable=True)
    account_id = Column(String(32), nullable=True)
    cycle_id = Column(String(64), nullable=True, index=True)
    trade_id = Column(String(64), nullable=True)
    position_id = Column(String(64), nullable=True)
    order_id = Column(String(64), nullable=True)
    
    # Context
    operation = Column(String(64), nullable=True)  # send_order, close_position, etc.
    instrument = Column(String(16), nullable=True)
    volume = Column(Float, nullable=True)
    price = Column(Float, nullable=True)
    
    # Status
    is_retryable = Column(Boolean, nullable=False, default=False)
    retry_count = Column(Integer, nullable=False, default=0)
    is_resolved = Column(Boolean, nullable=False, default=False)
    
    # Resolution
    resolved_by = Column(String(64), nullable=True)
    resolution = Column(Text, nullable=True)
    
    # Impact
    financial_impact = Column(Float, nullable=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_error_type', 'error_type'),
        Index('idx_error_status', 'is_resolved', 'is_retryable'),
        Index('idx_error_time', 'timestamp'),
        Index('idx_error_cycle', 'cycle_id'),
    )
    
    @property
    def is_connection_error(self) -> bool:
        """Check if error is a connection error."""
        return "connection" in self.error_type.lower() or "connect" in self.error_type.lower()
    
    @property
    def is_order_error(self) -> bool:
        """Check if error is an order error."""
        return "order" in self.error_type.lower()
    
    @property
    def is_recoverable(self) -> bool:
        """Check if error is potentially recoverable."""
        return self.is_retryable and self.retry_count < 3
    
    def to_dict(self) -> dict:
        """Convert to dictionary with additional computed fields."""
        data = super().to_dict()
        data.update({
            "is_connection_error": self.is_connection_error,
            "is_order_error": self.is_order_error,
            "is_recoverable": self.is_recoverable,
        })
        return data
