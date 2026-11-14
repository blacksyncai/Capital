"""
Risk Checks

Individual risk check implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List, Any, Tuple
import logging

from ..brokers.base_broker import BaseBroker, AccountInfo, Position, TickData
from ..core.config import get_config
from ..core.logging import get_logger
from ..execution.order_manager import OrderManager
from ..execution.trade_state import TradeStateManager, TradeState
from .types import RiskSeverity, RiskViolation, RiskCheckResult


# Configure logging
logger = logging.getLogger(__name__)


class RiskCheck(ABC):
    """
    Abstract base class for risk checks.
    
    All risk checks must inherit from this class and implement the run method.
    """
    
    def __init__(self, name: str = None):
        """
        Initialize the risk check.
        
        Args:
            name: Check name
        """
        self.name = name or self.__class__.__name__
        self.order_manager = OrderManager()
        self.trade_state_manager = TradeStateManager()
        self._initialized = False
    
    def initialize(self) -> None:
        """Initialize the risk check."""
        if not self._initialized:
            self.order_manager.initialize()
            self.trade_state_manager.initialize()
            self._initialized = True
    
    @abstractmethod
    def run(self, context: Dict[str, Any]) -> RiskCheckResult:
        """
        Run the risk check.
        
        Args:
            context: Context dictionary with relevant information
            
        Returns:
            RiskCheckResult
        """
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the check.
        
        Returns:
            Status dictionary
        """
        return {"name": self.name, "initialized": self._initialized}


class MaxLossCheck(RiskCheck):
    """
    Check if the maximum loss per cycle is exceeded.
    """
    
    def __init__(self, max_loss_usd: float = 10.0):
        """
        Initialize the max loss check.
        
        Args:
            max_loss_usd: Maximum loss per cycle in USD
        """
        super().__init__("max_loss_per_cycle")
        self.max_loss_usd = max_loss_usd
    
    def run(self, context: Dict[str, Any]) -> RiskCheckResult:
        """Run the max loss check."""
        self.initialize()
        
        cycle_id = context.get("cycle_id")
        
        if cycle_id:
            # Check specific cycle
            state = self.trade_state_manager.get_cycle_state(cycle_id)
            if state:
                pnl_info = self.trade_state_manager.get_cycle_pnl(cycle_id)
                if pnl_info:
                    combined_pnl = pnl_info.get("combined_pnl", 0.0)
                    if combined_pnl < -self.max_loss_usd:
                        return RiskCheckResult(
                            check_name=self.name,
                            passed=False,
                            violation=RiskViolation(
                                violation_id=f"max_loss_{cycle_id}",
                                check_name=self.name,
                                severity=RiskSeverity.HIGH,
                                message=f"Max loss exceeded: {combined_pnl:.2f} < -{self.max_loss_usd:.2f}",
                                timestamp=datetime.utcnow(),
                                cycle_id=cycle_id,
                                current_value=combined_pnl,
                                threshold_value=-self.max_loss_usd,
                                is_blocking=True
                            )
                        )
        else:
            # Check all active cycles
            active_cycles = self.trade_state_manager.get_active_cycles()
            for cycle_id, state in active_cycles.items():
                pnl_info = self.trade_state_manager.get_cycle_pnl(cycle_id)
                if pnl_info:
                    combined_pnl = pnl_info.get("combined_pnl", 0.0)
                    if combined_pnl < -self.max_loss_usd:
                        return RiskCheckResult(
                            check_name=self.name,
                            passed=False,
                            violation=RiskViolation(
                                violation_id=f"max_loss_{cycle_id}",
                                check_name=self.name,
                                severity=RiskSeverity.HIGH,
                                message=f"Max loss exceeded for cycle {cycle_id}: {combined_pnl:.2f} < -{self.max_loss_usd:.2f}",
                                timestamp=datetime.utcnow(),
                                cycle_id=cycle_id,
                                current_value=combined_pnl,
                                threshold_value=-self.max_loss_usd,
                                is_blocking=True
                            )
                        )
        
        return RiskCheckResult(
            check_name=self.name,
            passed=True
        )


class MaxDailyLossCheck(RiskCheck):
    """
    Check if the maximum daily loss is exceeded.
    """
    
    def __init__(self, max_daily_loss_usd: float = 50.0):
        """
        Initialize the max daily loss check.
        
        Args:
            max_daily_loss_usd: Maximum daily loss in USD
        """
        super().__init__("max_daily_loss")
        self.max_daily_loss_usd = max_daily_loss_usd
    
    def run(self, context: Dict[str, Any]) -> RiskCheckResult:
        """Run the max daily loss check."""
        self.initialize()
        
        # Calculate today's P&L
        today = datetime.utcnow().date()
        total_daily_loss = 0.0
        
        # Get all completed cycles from today
        completed_cycles = self.trade_state_manager.get_completed_cycles()
        for state in completed_cycles:
            if state.closed_time and state.closed_time.date() == today:
                pnl_info = self.trade_state_manager.get_cycle_pnl(state.cycle_id)
                if pnl_info:
                    combined_pnl = pnl_info.get("combined_pnl", 0.0)
                    if combined_pnl < 0:
                        total_daily_loss += abs(combined_pnl)
        
        # Check active cycles
        active_cycles = self.trade_state_manager.get_active_cycles()
        for cycle_id, state in active_cycles.items():
            pnl_info = self.trade_state_manager.get_cycle_pnl(cycle_id)
            if pnl_info:
                combined_pnl = pnl_info.get("combined_pnl", 0.0)
                if combined_pnl < 0:
                    total_daily_loss += abs(combined_pnl)
        
        if total_daily_loss > self.max_daily_loss_usd:
            return RiskCheckResult(
                check_name=self.name,
                passed=False,
                violation=RiskViolation(
                    violation_id=f"daily_loss_{today.isoformat()}",
                    check_name=self.name,
                    severity=RiskSeverity.CRITICAL,
                    message=f"Max daily loss exceeded: {total_daily_loss:.2f} > {self.max_daily_loss_usd:.2f}",
                    timestamp=datetime.utcnow(),
                    current_value=total_daily_loss,
                    threshold_value=self.max_daily_loss_usd,
                    is_blocking=True
                )
            )
        
        return RiskCheckResult(
            check_name=self.name,
            passed=True,
            warnings=[f"Daily loss: {total_daily_loss:.2f}/{self.max_daily_loss_usd:.2f}"]
        )


class MaxExposureCheck(RiskCheck):
    """
    Check if the maximum exposure is exceeded.
    """
    
    def __init__(self, max_exposure_usd: float = 100.0):
        """
        Initialize the max exposure check.
        
        Args:
            max_exposure_usd: Maximum exposure in USD
        """
        super().__init__("max_exposure")
        self.max_exposure_usd = max_exposure_usd
    
    def run(self, context: Dict[str, Any]) -> RiskCheckResult:
        """Run the max exposure check."""
        self.initialize()
        
        # Calculate total exposure
        total_exposure = 0.0
        
        # Get all active cycles
        active_cycles = self.trade_state_manager.get_active_cycles()
        
        for cycle_id, state in active_cycles.items():
            if state.both_positions_opened:
                # Get positions
                broker_a_pos = self.order_manager.get_position("vantage", state.broker_a_position_id) if state.broker_a_position_id else None
                broker_b_pos = self.order_manager.get_position("justmarkets", state.broker_b_position_id) if state.broker_b_position_id else None
                
                # Calculate exposure for each position
                if broker_a_pos:
                    try:
                        broker = self.order_manager.get_broker("vantage")
                        spec = broker.get_contract_spec(broker_a_pos.instrument)
                        if spec:
                            # Exposure = volume * contract_size * current_price
                            bid, ask = self.order_manager.get_bid_ask("vantage", broker_a_pos.instrument)
                            current_price = (bid + ask) / 2
                            exposure = broker_a_pos.volume * spec.contract_size * current_price
                            total_exposure += abs(exposure)
                    except Exception as e:
                        logger.error(f"Error calculating exposure for broker A: {e}")
                
                if broker_b_pos:
                    try:
                        broker = self.order_manager.get_broker("justmarkets")
                        spec = broker.get_contract_spec(broker_b_pos.instrument)
                        if spec:
                            bid, ask = self.order_manager.get_bid_ask("justmarkets", broker_b_pos.instrument)
                            current_price = (bid + ask) / 2
                            exposure = broker_b_pos.volume * spec.contract_size * current_price
                            total_exposure += abs(exposure)
                    except Exception as e:
                        logger.error(f"Error calculating exposure for broker B: {e}")
        
        if total_exposure > self.max_exposure_usd:
            return RiskCheckResult(
                check_name=self.name,
                passed=False,
                violation=RiskViolation(
                    violation_id=f"exposure_{datetime.utcnow().isoformat()}",
                    check_name=self.name,
                    severity=RiskSeverity.HIGH,
                    message=f"Max exposure exceeded: {total_exposure:.2f} > {self.max_exposure_usd:.2f}",
                    timestamp=datetime.utcnow(),
                    current_value=total_exposure,
                    threshold_value=self.max_exposure_usd,
                    is_blocking=True
                )
            )
        
        return RiskCheckResult(
            check_name=self.name,
            passed=True,
            warnings=[f"Current exposure: {total_exposure:.2f}/{self.max_exposure_usd:.2f}"]
        )


class MaxHoldingTimeCheck(RiskCheck):
    """
    Check if the maximum holding time is exceeded.
    """
    
    def __init__(self, max_holding_hours: float = 24.0):
        """
        Initialize the max holding time check.
        
        Args:
            max_holding_hours: Maximum holding time in hours
        """
        super().__init__("max_holding_time")
        self.max_holding_hours = max_holding_hours
    
    def run(self, context: Dict[str, Any]) -> RiskCheckResult:
        """Run the max holding time check."""
        self.initialize()
        
        cycle_id = context.get("cycle_id")
        
        if cycle_id:
            # Check specific cycle
            state = self.trade_state_manager.get_cycle_state(cycle_id)
            if state and state.opened_time:
                holding_hours = (datetime.utcnow() - state.opened_time).total_seconds() / 3600
                if holding_hours > self.max_holding_hours:
                    return RiskCheckResult(
                        check_name=self.name,
                        passed=False,
                        violation=RiskViolation(
                            violation_id=f"holding_time_{cycle_id}",
                            check_name=self.name,
                            severity=RiskSeverity.MEDIUM,
                            message=f"Max holding time exceeded: {holding_hours:.2f}h > {self.max_holding_hours:.2f}h",
                            timestamp=datetime.utcnow(),
                            cycle_id=cycle_id,
                            current_value=holding_hours,
                            threshold_value=self.max_holding_hours,
                            is_blocking=False  # Warning only
                        )
                    )
        else:
            # Check all active cycles
            active_cycles = self.trade_state_manager.get_active_cycles()
            for cycle_id, state in active_cycles.items():
                if state.opened_time:
                    holding_hours = (datetime.utcnow() - state.opened_time).total_seconds() / 3600
                    if holding_hours > self.max_holding_hours:
                        return RiskCheckResult(
                            check_name=self.name,
                            passed=False,
                            violation=RiskViolation(
                                violation_id=f"holding_time_{cycle_id}",
                                check_name=self.name,
                                severity=RiskSeverity.MEDIUM,
                                message=f"Max holding time exceeded for cycle {cycle_id}: {holding_hours:.2f}h > {self.max_holding_hours:.2f}h",
                                timestamp=datetime.utcnow(),
                                cycle_id=cycle_id,
                                current_value=holding_hours,
                                threshold_value=self.max_holding_hours,
                                is_blocking=False
                            )
                        )
        
        return RiskCheckResult(
            check_name=self.name,
            passed=True
        )


class MinMarginCheck(RiskCheck):
    """
    Check if the minimum margin requirement is met.
    """
    
    def __init__(self, min_margin_percent: float = 50.0):
        """
        Initialize the min margin check.
        
        Args:
            min_margin_percent: Minimum free margin percentage
        """
        super().__init__("min_margin")
        self.min_margin_percent = min_margin_percent
    
    def run(self, context: Dict[str, Any]) -> RiskCheckResult:
        """Run the min margin check."""
        self.initialize()
        
        violations = []
        warnings = []
        
        # Check both brokers
        for broker_id in ["vantage", "justmarkets"]:
            try:
                account_info = self.order_manager.get_account_info(broker_id)
                if account_info:
                    margin_percent = account_info.margin_percent
                    
                    if margin_percent < self.min_margin_percent:
                        violations.append(RiskViolation(
                            violation_id=f"margin_{broker_id}",
                            check_name=self.name,
                            severity=RiskSeverity.CRITICAL,
                            message=f"Low margin on {broker_id}: {margin_percent:.2f}% < {self.min_margin_percent:.2f}%",
                            timestamp=datetime.utcnow(),
                            broker_id=broker_id,
                            current_value=margin_percent,
                            threshold_value=self.min_margin_percent,
                            is_blocking=True
                        ))
                    elif margin_percent < self.min_margin_percent * 1.2:  # Warning threshold
                        warnings.append(f"Margin warning on {broker_id}: {margin_percent:.2f}%")
            except Exception as e:
                logger.error(f"Error checking margin for {broker_id}: {e}")
        
        if violations:
            return RiskCheckResult(
                check_name=self.name,
                passed=False,
                violation=violations[0],
                warnings=warnings
            )
        
        return RiskCheckResult(
            check_name=self.name,
            passed=True,
            warnings=warnings
        )


class MaxSpreadCheck(RiskCheck):
    """
    Check if the spread is too wide.
    """
    
    def __init__(self, max_spread_points: float = 10.0):
        """
        Initialize the max spread check.
        
        Args:
            max_spread_points: Maximum acceptable spread in points
        """
        super().__init__("max_spread")
        self.max_spread_points = max_spread_points
    
    def run(self, context: Dict[str, Any]) -> RiskCheckResult:
        """Run the max spread check."""
        self.initialize()
        
        instrument = context.get("instrument") or get_config().get_primary_instrument()
        
        violations = []
        
        # Check both brokers
        for broker_id in ["vantage", "justmarkets"]:
            try:
                tick = self.order_manager.get_tick(broker_id, instrument)
                if tick:
                    spread = tick.spread
                    if spread > self.max_spread_points:
                        violations.append(RiskViolation(
                            violation_id=f"spread_{broker_id}",
                            check_name=self.name,
                            severity=RiskSeverity.MEDIUM,
                            message=f"Wide spread on {broker_id}: {spread:.2f} > {self.max_spread_points:.2f}",
                            timestamp=datetime.utcnow(),
                            broker_id=broker_id,
                            current_value=spread,
                            threshold_value=self.max_spread_points,
                            is_blocking=False  # Warning only for spread
                        ))
            except Exception as e:
                logger.error(f"Error checking spread for {broker_id}: {e}")
        
        if violations:
            return RiskCheckResult(
                check_name=self.name,
                passed=False,
                violation=violations[0]
            )
        
        return RiskCheckResult(
            check_name=self.name,
            passed=True
        )


class MaxSlippageCheck(RiskCheck):
    """
    Check if the slippage is too high.
    """
    
    def __init__(self, max_slippage_points: float = 5.0):
        """
        Initialize the max slippage check.
        
        Args:
            max_slippage_points: Maximum acceptable slippage in points
        """
        super().__init__("max_slippage")
        self.max_slippage_points = max_slippage_points
    
    def run(self, context: Dict[str, Any]) -> RiskCheckResult:
        """Run the max slippage check."""
        self.initialize()
        
        # This check is typically run after order execution
        # For now, just return passed
        return RiskCheckResult(
            check_name=self.name,
            passed=True
        )


class PositionMismatchCheck(RiskCheck):
    """
    Check for position mismatches between brokers.
    """
    
    def __init__(self, tolerance: float = 0.001):
        """
        Initialize the position mismatch check.
        
        Args:
            tolerance: Tolerance for position matching
        """
        super().__init__("position_mismatch")
        self.tolerance = tolerance
    
    def run(self, context: Dict[str, Any]) -> RiskCheckResult:
        """Run the position mismatch check."""
        self.initialize()
        
        # Run reconciliation
        result = self.trade_state_manager.reconcile_positions()
        
        if not result.success and result.mismatches:
            return RiskCheckResult(
                check_name=self.name,
                passed=False,
                violation=RiskViolation(
                    violation_id=f"mismatch_{datetime.utcnow().isoformat()}",
                    check_name=self.name,
                    severity=RiskSeverity.HIGH,
                    message=f"Position mismatch detected: {result.mismatches[0]}",
                    timestamp=datetime.utcnow(),
                    is_blocking=True
                ),
                warnings=result.warnings
            )
        
        return RiskCheckResult(
            check_name=self.name,
            passed=True,
            warnings=result.warnings
        )


class EmergencyStopCheck(RiskCheck):
    """
    Check if emergency stop conditions are met.
    """
    
    def __init__(self):
        """Initialize the emergency stop check."""
        super().__init__("emergency_stop")
    
    def run(self, context: Dict[str, Any]) -> RiskCheckResult:
        """Run the emergency stop check."""
        self.initialize()
        
        # Check for critical violations
        from .risk_engine import get_risk_engine
        risk_engine = get_risk_engine()
        
        blocking_violations = risk_engine.get_blocking_violations()
        
        if blocking_violations:
            # Check if any are critical
            critical_violations = [v for v in blocking_violations if v.severity == RiskSeverity.CRITICAL]
            if critical_violations:
                return RiskCheckResult(
                    check_name=self.name,
                    passed=False,
                    violation=RiskViolation(
                        violation_id=f"emergency_{datetime.utcnow().isoformat()}",
                        check_name=self.name,
                        severity=RiskSeverity.CRITICAL,
                        message=f"Emergency stop triggered by critical violation: {critical_violations[0].message}",
                        timestamp=datetime.utcnow(),
                        is_blocking=True
                    )
                )
        
        return RiskCheckResult(
            check_name=self.name,
            passed=True
        )
