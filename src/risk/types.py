"""
Risk Types

Common types and data structures for the risk management module.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any


class RiskSeverity(str, Enum):
    """Risk violation severity levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class RiskViolation:
    """Represents a risk violation."""
    violation_id: str
    check_name: str
    severity: RiskSeverity
    message: str
    timestamp: datetime
    broker_id: Optional[str] = None
    cycle_id: Optional[str] = None
    trade_id: Optional[str] = None
    position_id: Optional[str] = None
    order_id: Optional[str] = None
    
    # Context
    current_value: Optional[float] = None
    threshold_value: Optional[float] = None
    
    # Status
    is_blocking: bool = True
    is_acknowledged: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "violation_id": self.violation_id,
            "check_name": self.check_name,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "broker_id": self.broker_id,
            "cycle_id": self.cycle_id,
            "trade_id": self.trade_id,
            "position_id": self.position_id,
            "order_id": self.order_id,
            "current_value": self.current_value,
            "threshold_value": self.threshold_value,
            "is_blocking": self.is_blocking,
            "is_acknowledged": self.is_acknowledged,
        }


@dataclass
class RiskCheckResult:
    """Result of a risk check."""
    check_name: str
    passed: bool
    violation: Optional[RiskViolation] = None
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "check_name": self.check_name,
            "passed": self.passed,
            "warnings": self.warnings,
        }
        if self.violation:
            result["violation"] = self.violation.to_dict()
        return result
