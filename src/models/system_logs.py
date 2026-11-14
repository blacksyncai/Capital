"""
System Log Model

Database model for system logs.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    Index,
)

from .base import Base, BaseModel


class SystemLog(BaseModel):
    """
    System log model for storing application logs in the database.
    
    Provides persistent logging for audit and debugging purposes.
    """
    
    __tablename__ = "system_logs"
    
    # Log identification
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Timestamps
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # Log details
    level = Column(String(16), nullable=False, index=True)  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    logger = Column(String(64), nullable=False, index=True)
    message = Column(Text, nullable=False)
    
    # Context
    component = Column(String(32), nullable=True)  # execution, risk, strategy, broker, etc.
    broker_id = Column(String(32), nullable=True)
    cycle_id = Column(String(64), nullable=True)
    trade_id = Column(String(64), nullable=True)
    
    # Additional data
    data = Column(Text, nullable=True)
    
    # Source
    source = Column(String(32), nullable=True)  # api, scheduler, manual, etc.
    
    # Indexes
    __table_args__ = (
        Index('idx_log_level', 'level'),
        Index('idx_log_logger', 'logger'),
        Index('idx_log_time', 'timestamp'),
        Index('idx_log_component', 'component'),
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = super().to_dict()
        return data
