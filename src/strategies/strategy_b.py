"""
Strategy B: Protected Runner

Close one position and allow the remaining position to run with a protective stop.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
import logging

from .base_strategy import BaseStrategy, StrategyConfig, TradeSignal, StrategyResult


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class ProtectedRunnerConfig(StrategyConfig):
    """Configuration for Protected Runner strategy."""
    # Runner trigger conditions
    runner_trigger_pnl: float = 10.0  # Trigger when combined P&L reaches this
    runner_trigger_time_minutes: float = 60  # Or after this time
    runner_trigger_volatility: bool = True  # Or on high volatility
    
    # Which leg to close
    close_leg: str = "losing"  # Options: losing, winning, broker_a, broker_b
    
    # Protective stop for runner
    stop_loss_usd: float = 5.0
    trailing_stop_enabled: bool = True
    trailing_stop_distance_usd: float = 2.0
    trailing_stop_activation_usd: float = 3.0
    
    # Time limits
    max_runner_duration_minutes: float = 1440
    
    # Risk management
    max_unhedged_exposure_usd: float = 50.0
    max_drawdown_usd: float = 10.0


class ProtectedRunnerStrategy(BaseStrategy):
    """
    Protected Runner Strategy
    
    Under predefined conditions, closes one position and allows the remaining
    position to run with a protective stop.
    """
    
    def __init__(self, strategy_id: str = "protected_runner", config: Optional[ProtectedRunnerConfig] = None):
        """
        Initialize the Protected Runner strategy.
        
        Args:
            strategy_id: Strategy identifier
            config: Strategy configuration
        """
        if config is None:
            config = ProtectedRunnerConfig(
                strategy_id=strategy_id,
                name="Protected Runner",
                description="Close one position and allow the remaining to run with protective stop"
            )
        
        super().__init__(strategy_id, config)
        self.config: ProtectedRunnerConfig = config
        
        # State tracking
        self.runner_cycles: Dict[str, datetime] = {}  # cycle_id -> runner_start_time
    
    def generate_signal(self, context: Dict[str, Any]) -> Optional[TradeSignal]:
        """
        Generate a trade signal.
        
        Args:
            context: Context dictionary
            
        Returns:
            TradeSignal or None
        """
        # Check if we can trade
        can_trade, reasons = self.risk_engine.can_trade()
        if not can_trade:
            return None
        
        # Check if we have active cycles that need to be converted to runners
        active_cycles = self.trade_state_manager.get_active_cycles()
        
        for cycle_id, state in active_cycles.items():
            if state.strategy_id != self.strategy_id:
                continue
            
            # Check if this cycle should be converted to a runner
            should_convert, reason = self._should_convert_to_runner(cycle_id)
            
            if should_convert:
                # Generate signal to close one leg
                return self._create_conversion_signal(cycle_id, reason)
        
        # If no active cycles, generate new signal
        if not active_cycles:
            instrument = self.config.parameters.get("instrument", "XAUUSD")
            lot_size = self.config.parameters.get("lot_size", 0.01)
            direction = self.config.parameters.get("direction", "BUY_SELL")
            
            return self._create_signal(
                action="OPEN",
                instrument=instrument,
                direction=direction,
                lot_size=lot_size
            )
        
        return None
    
    def should_close_cycle(self, cycle_id: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Determine if a cycle should be closed.
        
        Args:
            cycle_id: Cycle ID
            context: Context dictionary
            
        Returns:
            Tuple of (should_close, reason)
        """
        state = self.trade_state_manager.get_cycle_state(cycle_id)
        if state is None:
            return (False, "cycle_not_found")
        
        # Check if this is a runner cycle
        if cycle_id in self.runner_cycles:
            return self._should_close_runner(cycle_id)
        
        # For non-runner cycles, use basic conditions
        pnl_info = self.trade_state_manager.get_cycle_pnl(cycle_id)
        if pnl_info is None:
            return (False, "pnl_not_available")
        
        combined_pnl = pnl_info.get("combined_pnl", 0.0)
        
        # Close if stop loss reached
        if combined_pnl <= -self.config.stop_loss_usd:
            return (True, f"stop_loss_reached_{self.config.stop_loss_usd}")
        
        # Close if max holding time reached
        if state.opened_time:
            holding_minutes = (datetime.utcnow() - state.opened_time).total_seconds() / 60
            max_holding = self.config.risk_overrides.get("max_holding_minutes", 1440)
            if holding_minutes >= max_holding:
                return (True, f"max_holding_time_reached_{max_holding}")
        
        return (False, "no_close_condition")
    
    def _should_convert_to_runner(self, cycle_id: str) -> Tuple[bool, str]:
        """
        Check if a cycle should be converted to a runner.
        
        Args:
            cycle_id: Cycle ID
            
        Returns:
            Tuple of (should_convert, reason)
        """
        state = self.trade_state_manager.get_cycle_state(cycle_id)
        if state is None:
            return (False, "cycle_not_found")
        
        # Already a runner
        if cycle_id in self.runner_cycles:
            return (False, "already_runner")
        
        pnl_info = self.trade_state_manager.get_cycle_pnl(cycle_id)
        if pnl_info is None:
            return (False, "pnl_not_available")
        
        combined_pnl = pnl_info.get("combined_pnl", 0.0)
        
        # Check P&L trigger
        if combined_pnl >= self.config.runner_trigger_pnl:
            return (True, f"pnl_trigger_{combined_pnl:.2f}")
        
        # Check time trigger
        if state.opened_time:
            holding_minutes = (datetime.utcnow() - state.opened_time).total_seconds() / 60
            if holding_minutes >= self.config.runner_trigger_time_minutes:
                return (True, f"time_trigger_{holding_minutes:.0f}m")
        
        # Check volatility trigger
        if self.config.runner_trigger_volatility:
            if self._is_high_volatility():
                return (True, "volatility_trigger")
        
        return (False, "no_trigger")
    
    def _should_close_runner(self, cycle_id: str) -> Tuple[bool, str]:
        """
        Check if a runner cycle should be closed.
        
        Args:
            cycle_id: Cycle ID
            
        Returns:
            Tuple of (should_close, reason)
        """
        # Check max runner duration
        if cycle_id in self.runner_cycles:
            runner_start = self.runner_cycles[cycle_id]
            holding_minutes = (datetime.utcnow() - runner_start).total_seconds() / 60
            
            if holding_minutes >= self.config.max_runner_duration_minutes:
                return (True, f"max_runner_duration_{holding_minutes:.0f}m")
        
        # Check stop loss for runner
        pnl_info = self.trade_state_manager.get_cycle_pnl(cycle_id)
        if pnl_info is None:
            return (False, "pnl_not_available")
        
        # For runner, we need to check the individual position P&L
        # This would require more detailed tracking
        # For now, just use combined P&L
        combined_pnl = pnl_info.get("combined_pnl", 0.0)
        
        # Check max drawdown
        if combined_pnl <= -self.config.max_drawdown_usd:
            return (True, f"max_drawdown_reached_{self.config.max_drawdown_usd}")
        
        return (False, "no_close_condition")
    
    def _create_conversion_signal(self, cycle_id: str, reason: str) -> TradeSignal:
        """
        Create a signal to convert a cycle to a runner.
        
        Args:
            cycle_id: Cycle ID
            reason: Reason for conversion
            
        Returns:
            TradeSignal to close one leg
        """
        state = self.trade_state_manager.get_cycle_state(cycle_id)
        if state is None:
            raise ValueError(f"Cycle not found: {cycle_id}")
        
        # Determine which leg to close
        leg_to_close = self._determine_leg_to_close(cycle_id)
        
        # Create signal to close that leg
        if leg_to_close == "broker_a":
            return self._create_signal(
                action="CLOSE",
                instrument=state.instrument,
                direction=state.direction,
                lot_size=state.lot_size,
                metadata={
                    "cycle_id": cycle_id,
                    "leg": "broker_a",
                    "reason": f"convert_to_runner_{reason}"
                }
            )
        else:
            return self._create_signal(
                action="CLOSE",
                instrument=state.instrument,
                direction=state.direction,
                lot_size=state.lot_size,
                metadata={
                    "cycle_id": cycle_id,
                    "leg": "broker_b",
                    "reason": f"convert_to_runner_{reason}"
                }
            )
    
    def _determine_leg_to_close(self, cycle_id: str) -> str:
        """
        Determine which leg to close when converting to runner.
        
        Args:
            cycle_id: Cycle ID
            
        Returns:
            "broker_a" or "broker_b"
        """
        pnl_info = self.trade_state_manager.get_cycle_pnl(cycle_id)
        if pnl_info is None:
            # Default to closing broker A
            return "broker_a"
        
        broker_a_pnl = pnl_info.get("broker_a_pnl", 0.0)
        broker_b_pnl = pnl_info.get("broker_b_pnl", 0.0)
        
        if self.config.close_leg == "losing":
            # Close the losing leg
            if broker_a_pnl < broker_b_pnl:
                return "broker_a"
            else:
                return "broker_b"
        elif self.config.close_leg == "winning":
            # Close the winning leg
            if broker_a_pnl > broker_b_pnl:
                return "broker_a"
            else:
                return "broker_b"
        else:
            # Use configured leg
            return self.config.close_leg
    
    def _is_high_volatility(self, window_minutes: float = 15) -> bool:
        """
        Check if there is high volatility.
        
        Args:
            window_minutes: Time window for volatility calculation
            
        Returns:
            True if high volatility
        """
        instrument = self.config.parameters.get("instrument", "XAUUSD")
        
        try:
            # Get historical data
            bars = self.order_manager.get_bars(
                broker_id="vantage",
                instrument=instrument,
                timeframe="M1",
                count=int(window_minutes)
            )
            
            if len(bars) < 2:
                return False
            
            # Calculate price range
            prices = [bar.close for bar in bars]
            price_range = max(prices) - min(prices)
            mid_price = sum(prices) / len(prices)
            
            # Calculate volatility as percentage
            volatility_percent = (price_range / mid_price) * 100
            
            # High volatility if > 1% in the window
            return volatility_percent > 1.0
            
        except Exception as e:
            self.logger.error(f"Error checking volatility: {e}")
            return False
    
    def on_cycle_converted(self, cycle_id: str) -> None:
        """
        Called when a cycle is converted to a runner.
        
        Args:
            cycle_id: Cycle ID
        """
        self.runner_cycles[cycle_id] = datetime.utcnow()
        self.logger.info(f"Cycle {cycle_id} converted to runner")
    
    def on_cycle_closed(self, cycle_id: str) -> None:
        """
        Called when a cycle is closed.
        
        Args:
            cycle_id: Cycle ID
        """
        self.runner_cycles.pop(cycle_id, None)


# Register strategy
_strategy = ProtectedRunnerStrategy()


def get_protected_runner_strategy(config: Optional[ProtectedRunnerConfig] = None) -> ProtectedRunnerStrategy:
    """
    Get the Protected Runner strategy instance.
    
    Args:
        config: Optional configuration
        
    Returns:
        ProtectedRunnerStrategy instance
    """
    return ProtectedRunnerStrategy("protected_runner", config)
