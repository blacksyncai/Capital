"""
Risk Violation Model

Database model for risk management violations.
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


class RiskViolation(BaseModel):
    """
    Risk violation model for tracking risk management events.
    
    Records all risk check failures, warnings, and emergency actions.
    """
    
    __tablename__ = "risk_violations"
    
    # Violation identification
    violation_id = Column(String(64), unique=True, nullable=False, index=True)
    
    # Timestamps
    timestamp = Column(DateTime, nullable=False, index=True)
    resolved_time = Column(DateTime, nullable=True)
    
    # Violation details
    violation_type = Column(String(64), nullable=False, index=True)
    severity = Column(String(16), nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    message = Column(Text, nullable=False)
    
    # Related entities
    broker_id = Column(String(32), nullable=True)
    account_id = Column(String(32), nullable=True)
    cycle_id = Column(String(64), nullable=True, index=True)
    trade_id = Column(String(64), nullable=True)
    position_id = Column(String(64), nullable=True)
    order_id = Column(String(64), nullable=True)
    
    # Context
    context = Column(Text, nullable=True)
    
    # Status
    is_resolved = Column(Boolean, nullable=False, default=False)
    is_acknowledged = Column(Boolean, nullable=False, default=False)
    
    # Impact
    affected_amount = Column(Float, nullable=True)
    current_value = Column(Float, nullable=True)
    threshold_value = Column(Float, nullable=True)
    
    # Action taken
    action_taken = Column(String(64), nullable=True)
    action_details = Column(Text, nullable=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_violation_type', 'violation_type'),
        Index('idx_violation_severity', 'severity'),
        Index('idx_violation_status', 'is_resolved', 'is_acknowledged'),
        Index('idx_violation_time', 'timestamp'),
        Index('idx_violation_cycle', 'cycle_id'),
    )
    
    @property
    def is_critical(self) -> bool:
        """Check if violation is critical."""
        return self.severity == "CRITICAL"
    
    @property
    def is_high(self) -> bool:
        """Check if violation is high severity."""
        return self.severity in ["CRITICAL", "HIGH"]
    
    @property
    def age_seconds(self) -> Optional[float]:
        """Calculate age in seconds."""
        if self.timestamp:
            return (datetime.utcnow() - self.timestamp).total_seconds()
        return None
    
    def to_dict(self) -> dict:
        """Convert to dictionary with additional computed fields."""
        data = super().to_dict()
        data.update({
            "is_critical": self.is_critical,
            "is_high": self.is_high,
            "age_seconds": self.age_seconds,
        })
        return data
