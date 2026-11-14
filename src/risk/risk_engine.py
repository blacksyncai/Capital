"""
Risk Engine

Central risk management engine that coordinates all risk checks.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List, Any, Callable, Union, Set, Tuple
import logging

from ..brokers.base_broker import BaseBroker, AccountInfo, Position, TickData
from ..core.config import get_config
from ..core.logging import get_logger
from ..core.database import get_database
from ..models.risk_violations import RiskViolation as RiskViolationModel
from ..execution.order_manager import OrderManager
from ..execution.trade_state import TradeStateManager, TradeState
from .types import RiskSeverity, RiskViolation, RiskCheckResult
from .risk_checks import (
    RiskCheck,
    MaxLossCheck,
    MaxDailyLossCheck,
    MaxExposureCheck,
    MaxHoldingTimeCheck,
    MinMarginCheck,
    MaxSpreadCheck,
    MaxSlippageCheck,
    PositionMismatchCheck,
    EmergencyStopCheck,
)


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class PreflightCheckResult:
    """Result of preflight checks."""
    all_passed: bool
    checks: Dict[str, RiskCheckResult] = field(default_factory=dict)
    violations: List[RiskViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "all_passed": self.all_passed,
            "checks": {name: check.to_dict() for name, check in self.checks.items()},
            "violations": [v.to_dict() for v in self.violations],
            "warnings": self.warnings,
        }


class RiskEngine:
    """
    Central risk management engine.
    
    Coordinates all risk checks and provides:
    - Preflight checks before trading
    - Runtime risk monitoring
    - Emergency stop functionality
    - Risk violation tracking
    """
    
    def __init__(self):
        """Initialize the risk engine."""
        self.logger = get_logger("risk.engine")
        self.db = get_database()
        self.order_manager = OrderManager()
        self.trade_state_manager = TradeStateManager()
        
        # Risk checks
        self.checks: Dict[str, RiskCheck] = {}
        self._initialize_checks()
        
        # State
        self.manual_kill_switch = False
        self.emergency_stop_triggered = False
        self.violations: Dict[str, RiskViolation] = {}
        self.warnings: List[str] = []
        
        # Configuration
        self._load_configuration()
        
        self._initialized = False
    
    def _initialize_checks(self) -> None:
        """Initialize all risk checks."""
        config = get_config()
        risk_config = config.risk_config if config.risk_config else {}
        
        # Create checks with configuration
        self.checks["max_loss_per_cycle"] = MaxLossCheck(
            max_loss_usd=risk_config.get("risk", {}).get("max_loss_per_cycle_usd", 10.0)
        )
        
        self.checks["max_daily_loss"] = MaxDailyLossCheck(
            max_daily_loss_usd=risk_config.get("risk", {}).get("max_daily_loss_usd", 50.0)
        )
        
        self.checks["max_exposure"] = MaxExposureCheck(
            max_exposure_usd=risk_config.get("risk", {}).get("max_open_exposure_usd", 100.0)
        )
        
        self.checks["max_holding_time"] = MaxHoldingTimeCheck(
            max_holding_hours=risk_config.get("risk", {}).get("max_holding_time_hours", 24.0)
        )
        
        self.checks["min_margin"] = MinMarginCheck(
            min_margin_percent=risk_config.get("risk", {}).get("min_free_margin_percent", 50.0)
        )
        
        self.checks["max_spread"] = MaxSpreadCheck(
            max_spread_points=risk_config.get("risk", {}).get("max_spread_points", 10.0)
        )
        
        self.checks["max_slippage"] = MaxSlippageCheck(
            max_slippage_points=risk_config.get("risk", {}).get("max_slippage_points", 5.0)
        )
        
        self.checks["position_mismatch"] = PositionMismatchCheck(
            tolerance=risk_config.get("risk", {}).get("position_mismatch_tolerance", 0.001)
        )
        
        self.checks["emergency_stop"] = EmergencyStopCheck()
    
    def _load_configuration(self) -> None:
        """Load configuration from config files."""
        config = get_config()
        risk_config = config.risk_config if config.risk_config else {}
        
        # Load overrides
        overrides = risk_config.get("overrides", {})
        self.manual_kill_switch = overrides.get("manual_kill_switch", False)
        self.emergency_stop_triggered = False
    
    def initialize(self) -> None:
        """Initialize the risk engine."""
        if self._initialized:
            return
        
        self.order_manager.initialize()
        self.order_manager.connect_all()
        self.trade_state_manager.initialize()
        
        self._initialized = True
        self.logger.info("Risk engine initialized")
    
    def check_all(self, context: Optional[Dict[str, Any]] = None) -> List[RiskCheckResult]:
        """
        Run all risk checks.
        
        Args:
            context: Optional context for checks
            
        Returns:
            List of check results
        """
        results = []
        
        for check_name, check in self.checks.items():
            try:
                result = check.run(context or {})
                results.append(result)
                
                if result.violation:
                    self._record_violation(result.violation)
                
                for warning in result.warnings:
                    self._record_warning(warning)
                    
            except Exception as e:
                self.logger.error(f"Error running check {check_name}: {e}")
                results.append(RiskCheckResult(
                    check_name=check_name,
                    passed=False,
                    violation=RiskViolation(
                        violation_id=f"err_{uuid.uuid4().hex[:8]}",
                        check_name=check_name,
                        severity=RiskSeverity.CRITICAL,
                        message=f"Check failed with error: {e}",
                        timestamp=datetime.utcnow()
                    )
                ))
        
        return results
    
    def check_before_trade(
        self,
        instrument: str,
        lot_size: float,
        direction: str = "BUY_SELL",
        broker_id: Optional[str] = None
    ) -> RiskCheckResult:
        """
        Run checks before opening a new trade.
        
        Args:
            instrument: Trading instrument
            lot_size: Lot size
            direction: Trade direction
            broker_id: Specific broker (optional)
            
        Returns:
            Combined check result
        """
        context = {
            "instrument": instrument,
            "lot_size": lot_size,
            "direction": direction,
            "broker_id": broker_id,
            "action": "open_trade"
        }
        
        # Run all checks
        results = self.check_all(context)
        
        # Find blocking violations
        blocking_violations = [
            r.violation for r in results
            if r.violation and r.violation.is_blocking
        ]
        
        if blocking_violations:
            # Return first blocking violation
            return RiskCheckResult(
                check_name="pre_trade",
                passed=False,
                violation=blocking_violations[0],
                warnings=[r.violation.message for r in results if r.violation and not r.violation.is_blocking]
            )
        
        # All checks passed
        return RiskCheckResult(
            check_name="pre_trade",
            passed=True,
            warnings=[w for r in results for w in r.warnings]
        )
    
    def check_before_close(self, cycle_id: str) -> RiskCheckResult:
        """
        Run checks before closing a trade.
        
        Args:
            cycle_id: Cycle ID
            
        Returns:
            Check result
        """
        context = {
            "cycle_id": cycle_id,
            "action": "close_trade"
        }
        
        # Run relevant checks
        relevant_checks = [
            "max_loss_per_cycle",
            "max_holding_time",
            "emergency_stop"
        ]
        
        results = []
        for check_name in relevant_checks:
            if check_name in self.checks:
                try:
                    result = self.checks[check_name].run(context)
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"Error running check {check_name}: {e}")
        
        # Find blocking violations
        blocking_violations = [
            r.violation for r in results
            if r.violation and r.violation.is_blocking
        ]
        
        if blocking_violations:
            return RiskCheckResult(
                check_name="pre_close",
                passed=False,
                violation=blocking_violations[0]
            )
        
        return RiskCheckResult(
            check_name="pre_close",
            passed=True
        )
    
    def run_preflight_checks(self) -> PreflightCheckResult:
        """
        Run all preflight checks before enabling live trading.
        
        Returns:
            Preflight check result
        """
        result = PreflightCheckResult(all_passed=True)
        
        # Check configuration
        config = get_config()
        if config.is_live_trading_enabled():
            result.warnings.append("Live trading is already enabled")
        
        # Check broker connections
        connections = self.order_manager.connect_all()
        for broker_id, success in connections.items():
            if not success:
                result.all_passed = False
                result.violations.append(RiskViolation(
                    violation_id=f"conn_{broker_id}",
                    check_name="broker_connection",
                    severity=RiskSeverity.CRITICAL,
                    message=f"Failed to connect to broker: {broker_id}",
                    timestamp=datetime.utcnow(),
                    broker_id=broker_id
                ))
        
        # Check account balances
        for broker_id in connections:
            if connections[broker_id]:
                try:
                    account_info = self.order_manager.get_account_info(broker_id)
                    if account_info:
                        # Check minimum balance
                        min_balance = config.get("risk", "risk.min_balance_usd", 10.0)
                        if account_info.balance < min_balance:
                            result.all_passed = False
                            result.violations.append(RiskViolation(
                                violation_id=f"bal_{broker_id}",
                                check_name="minimum_balance",
                                severity=RiskSeverity.HIGH,
                                message=f"Account balance too low: {account_info.balance} < {min_balance}",
                                timestamp=datetime.utcnow(),
                                broker_id=broker_id,
                                current_value=account_info.balance,
                                threshold_value=min_balance
                            ))
                except Exception as e:
                    result.all_passed = False
                    result.violations.append(RiskViolation(
                        violation_id=f"acc_{broker_id}",
                        check_name="account_info",
                        severity=RiskSeverity.HIGH,
                        message=f"Failed to get account info for {broker_id}: {e}",
                        timestamp=datetime.utcnow(),
                        broker_id=broker_id
                    ))
        
        # Check contract specifications
        for broker_id in connections:
            if connections[broker_id]:
                try:
                    broker = self.order_manager.get_broker(broker_id)
                    primary_instrument = config.get_primary_instrument()
                    spec = broker.get_contract_spec(primary_instrument)
                    if spec is None:
                        result.all_passed = False
                        result.violations.append(RiskViolation(
                            violation_id=f"spec_{broker_id}",
                            check_name="contract_spec",
                            severity=RiskSeverity.HIGH,
                            message=f"No contract spec for {primary_instrument} on {broker_id}",
                            timestamp=datetime.utcnow(),
                            broker_id=broker_id
                        ))
                except Exception as e:
                    result.all_passed = False
                    result.violations.append(RiskViolation(
                        violation_id=f"spec_err_{broker_id}",
                        check_name="contract_spec",
                        severity=RiskSeverity.HIGH,
                        message=f"Error getting contract spec for {broker_id}: {e}",
                        timestamp=datetime.utcnow(),
                        broker_id=broker_id
                    ))
        
        # Run all risk checks
        check_results = self.check_all()
        for check_result in check_results:
            result.checks[check_result.check_name] = check_result
            if check_result.violation:
                result.violations.append(check_result.violation)
                result.all_passed = False
            result.warnings.extend(check_result.warnings)
        
        # Check emergency stop
        emergency_check = self.checks.get("emergency_stop")
        if emergency_check:
            emergency_result = emergency_check.run({})
            result.checks["emergency_stop"] = emergency_result
            if emergency_result.violation:
                result.violations.append(emergency_result.violation)
                result.all_passed = False
        
        return result
    
    def can_trade(self) -> Tuple[bool, List[str]]:
        """
        Check if trading is currently allowed.
        
        Returns:
            Tuple of (can_trade, list of reasons if not)
        """
        reasons = []
        
        # Check manual kill switch
        if self.manual_kill_switch:
            reasons.append("Manual kill switch is active")
        
        # Check emergency stop
        if self.emergency_stop_triggered:
            reasons.append("Emergency stop is triggered")
        
        # Check blocking violations
        blocking_violations = [
            v for v in self.violations.values()
            if v.is_blocking and not v.is_acknowledged
        ]
        for violation in blocking_violations:
            reasons.append(f"Risk violation: {violation.message}")
        
        # Check live trading enabled
        config = get_config()
        if not config.is_live_trading_enabled():
            reasons.append("Live trading is not enabled")
        
        can_trade = len(reasons) == 0
        return (can_trade, reasons)
    
    def trigger_emergency_stop(self, reason: str = "manual") -> None:
        """
        Trigger emergency stop.
        
        Args:
            reason: Reason for emergency stop
        """
        self.emergency_stop_triggered = True
        
        # Create violation
        violation = RiskViolation(
            violation_id=f"emergency_{uuid.uuid4().hex[:8]}",
            check_name="emergency_stop",
            severity=RiskSeverity.CRITICAL,
            message=f"Emergency stop triggered: {reason}",
            timestamp=datetime.utcnow(),
            is_blocking=True
        )
        
        self._record_violation(violation)
        
        # Close all active cycles
        self.trade_state_manager.emergency_close_all(f"Emergency stop: {reason}")
        
        self.logger.critical(f"EMERGENCY STOP TRIGGERED: {reason}")
    
    def clear_emergency_stop(self) -> None:
        """Clear emergency stop."""
        self.emergency_stop_triggered = False
        self.logger.info("Emergency stop cleared")
    
    def set_manual_kill_switch(self, enabled: bool) -> None:
        """
        Set manual kill switch.
        
        Args:
            enabled: True to enable, False to disable
        """
        self.manual_kill_switch = enabled
        if enabled:
            self.logger.warning("Manual kill switch ENABLED - all trading blocked")
        else:
            self.logger.info("Manual kill switch disabled")
    
    def acknowledge_violation(self, violation_id: str) -> bool:
        """
        Acknowledge a risk violation.
        
        Args:
            violation_id: Violation ID
            
        Returns:
            True if acknowledged
        """
        if violation_id in self.violations:
            self.violations[violation_id].is_acknowledged = True
            self._update_violation_in_db(violation_id)
            self.logger.info(f"Violation acknowledged: {violation_id}")
            return True
        return False
    
    def get_violations(self, severity: Optional[RiskSeverity] = None) -> List[RiskViolation]:
        """
        Get all risk violations.
        
        Args:
            severity: Filter by severity (optional)
            
        Returns:
            List of violations
        """
        if severity:
            return [v for v in self.violations.values() if v.severity == severity]
        return list(self.violations.values())
    
    def get_blocking_violations(self) -> List[RiskViolation]:
        """
        Get all blocking violations.
        
        Returns:
            List of blocking violations
        """
        return [v for v in self.violations.values() if v.is_blocking and not v.is_acknowledged]
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the risk engine.
        
        Returns:
            Status dictionary
        """
        can_trade, reasons = self.can_trade()
        
        return {
            "can_trade": can_trade,
            "cannot_trade_reasons": reasons,
            "manual_kill_switch": self.manual_kill_switch,
            "emergency_stop_triggered": self.emergency_stop_triggered,
            "active_violations": len(self.violations),
            "blocking_violations": len(self.get_blocking_violations()),
            "warnings": len(self.warnings),
            "checks": {name: check.get_status() for name, check in self.checks.items()}
        }
    
    def _record_violation(self, violation: RiskViolation) -> None:
        """
        Record a risk violation.
        
        Args:
            violation: Violation to record
        """
        self.violations[violation.violation_id] = violation
        
        # Save to database
        try:
            with self.db.get_session() as session:
                model = RiskViolationModel(
                    violation_id=violation.violation_id,
                    timestamp=violation.timestamp,
                    violation_type=violation.check_name,
                    severity=violation.severity.value,
                    message=violation.message,
                    broker_id=violation.broker_id,
                    cycle_id=violation.cycle_id,
                    trade_id=violation.trade_id,
                    position_id=violation.position_id,
                    order_id=violation.order_id,
                    context=violation.message,
                    is_resolved=False,
                    is_acknowledged=violation.is_acknowledged,
                    current_value=violation.current_value,
                    threshold_value=violation.threshold_value,
                    action_taken="recorded"
                )
                session.add(model)
                session.commit()
        except Exception as e:
            self.logger.error(f"Error saving violation to database: {e}")
    
    def _update_violation_in_db(self, violation_id: str) -> None:
        """
        Update a violation in the database.
        
        Args:
            violation_id: Violation ID
        """
        if violation_id not in self.violations:
            return
        
        violation = self.violations[violation_id]
        
        try:
            with self.db.get_session() as session:
                model = session.query(RiskViolationModel).filter_by(
                    violation_id=violation_id
                ).first()
                
                if model:
                    model.is_acknowledged = violation.is_acknowledged
                    model.is_resolved = violation.is_acknowledged
                    session.commit()
        except Exception as e:
            self.logger.error(f"Error updating violation in database: {e}")
    
    def _record_warning(self, warning: str) -> None:
        """
        Record a warning.
        
        Args:
            warning: Warning message
        """
        if warning not in self.warnings:
            self.warnings.append(warning)
            self.logger.warning(f"Risk warning: {warning}")


# Global risk engine instance
_risk_engine: Optional[RiskEngine] = None


def get_risk_engine() -> RiskEngine:
    """
    Get the global risk engine instance.
    
    Returns:
        RiskEngine instance
    """
    global _risk_engine
    if _risk_engine is None:
        _risk_engine = RiskEngine()
    return _risk_engine


def reset_risk_engine() -> None:
    """Reset the global risk engine instance."""
    global _risk_engine
    _risk_engine = None
