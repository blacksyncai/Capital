"""
Strategy E: Entry Optimization

Delay entries until spreads and execution conditions improve.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
import logging
import time

from .base_strategy import BaseStrategy, StrategyConfig, TradeSignal, StrategyResult


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class EntryOptimizationConfig(StrategyConfig):
    """Configuration for Entry Optimization strategy."""
    # Spread conditions for entry
    max_entry_spread_points: float = 5
    ideal_spread_points: float = 1
    spread_wait_timeout_seconds: float = 30
    
    # Execution quality conditions
    max_execution_delay_ms: float = 500
    max_slippage_points: float = 2
    
    # Market stability conditions
    min_stability_period_seconds: float = 60
    max_price_volatility_percent: float = 0.5
    
    # Time-based entry windows
    entry_windows: List[Dict[str, str]] = field(default_factory=lambda: [
        {"start": "00:00", "end": "23:59", "priority": 1}
    ])
    
    # Queue management
    max_queued_orders: int = 10
    queue_timeout_seconds: float = 60
    
    # Early exit conditions
    exit_if_conditions_worsen: bool = True
    worsening_threshold_percent: float = 10


class EntryOptimizationStrategy(BaseStrategy):
    """
    Entry Optimization Strategy
    
    Delays entries until spreads and execution conditions improve.
    """
    
    def __init__(self, strategy_id: str = "entry_optimization", config: Optional[EntryOptimizationConfig] = None):
        """
        Initialize the Entry Optimization strategy.
        
        Args:
            strategy_id: Strategy identifier
            config: Strategy configuration
        """
        if config is None:
            config = EntryOptimizationConfig(
                strategy_id=strategy_id,
                name="Entry Optimization",
                description="Delay entries until spreads and execution conditions improve"
            )
        
        super().__init__(strategy_id, config)
        self.config: EntryOptimizationConfig = config
        
        # State tracking
        self.queued_signals: Dict[str, TradeSignal] = {}  # signal_id -> signal
        self.signal_timestamps: Dict[str, datetime] = {}  # signal_id -> timestamp
        self.last_spread_check: Dict[str, datetime] = {}  # instrument -> timestamp
        self.spread_history: Dict[str, List[float]] = {}  # instrument -> [spreads]
    
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
        
        # Check if we have active cycles
        active_cycles = self.trade_state_manager.get_active_cycles()
        for cycle_id, state in active_cycles.items():
            if state.strategy_id == self.strategy_id:
                return None  # Already have active cycle
        
        # Check if we have queued signals
        self._cleanup_queue()
        if self.queued_signals:
            # Check if conditions are good for queued signals
            for signal_id, signal in list(self.queued_signals.items()):
                if self._is_good_entry_condition(signal.instrument):
                    # Remove from queue and return
                    del self.queued_signals[signal_id]
                    del self.signal_timestamps[signal_id]
                    return signal
            
            # If we have queued signals but conditions aren't good, don't generate new ones
            return None
        
        # Generate new signal
        instrument = self.config.parameters.get("instrument", "XAUUSD")
        lot_size = self.config.parameters.get("lot_size", 0.01)
        direction = self.config.parameters.get("direction", "BUY_SELL")
        
        # Check if conditions are good for immediate entry
        if self._is_good_entry_condition(instrument):
            return self._create_signal(
                action="OPEN",
                instrument=instrument,
                direction=direction,
                lot_size=lot_size
            )
        else:
            # Queue the signal
            signal = self._create_signal(
                action="OPEN",
                instrument=instrument,
                direction=direction,
                lot_size=lot_size
            )
            self.queued_signals[signal.signal_id] = signal
            self.signal_timestamps[signal.signal_id] = datetime.utcnow()
            self.logger.info(f"Signal queued: {signal.signal_id}, waiting for better conditions")
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
        
        # Check if conditions have worsened significantly
        if self.config.exit_if_conditions_worsen:
            instrument = state.instrument
            if self._has_conditions_worsened(instrument):
                return (True, "conditions_worsened")
        
        # Check for stop loss
        pnl_info = self.trade_state_manager.get_cycle_pnl(cycle_id)
        if pnl_info:
            combined_pnl = pnl_info.get("combined_pnl", 0.0)
            stop_loss = self.config.risk_overrides.get("stop_loss_usd", 3.0)
            if combined_pnl <= -stop_loss:
                return (True, f"stop_loss_reached_{stop_loss}")
        
        # Check holding time
        if state.opened_time:
            holding_minutes = (datetime.utcnow() - state.opened_time).total_seconds() / 60
            max_holding = self.config.risk_overrides.get("max_holding_minutes", 1440)
            if holding_minutes >= max_holding:
                return (True, f"max_holding_time_reached_{max_holding}")
        
        return (False, "no_close_condition")
    
    def _is_good_entry_condition(self, instrument: str) -> bool:
        """
        Check if entry conditions are good.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            True if conditions are good
        """
        # Check spread
        if not self._is_spread_good(instrument):
            return False
        
        # Check market stability
        if not self._is_market_stable(instrument):
            return False
        
        # Check time window
        if not self._is_in_entry_window():
            return False
        
        return True
    
    def _is_spread_good(self, instrument: str) -> bool:
        """
        Check if spread is good for entry.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            True if spread is good
        """
        try:
            for broker_id in ["vantage", "justmarkets"]:
                tick = self.order_manager.get_tick(broker_id, instrument)
                if tick and tick.spread > self.config.max_entry_spread_points:
                    return False
            return True
        except Exception as e:
            logger.error(f"Error checking spread: {e}")
            return True  # Assume good if we can't check
    
    def _is_market_stable(self, instrument: str) -> bool:
        """
        Check if market is stable.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            True if market is stable
        """
        try:
            # Check price volatility
            bars = self.order_manager.get_bars(
                broker_id="vantage",
                instrument=instrument,
                timeframe="M1",
                count=5
            )
            
            if len(bars) < 2:
                return True  # Not enough data, assume stable
            
            prices = [bar.close for bar in bars]
            price_range = max(prices) - min(prices)
            mid_price = sum(prices) / len(prices)
            volatility = (price_range / mid_price) * 100
            
            return volatility <= self.config.max_price_volatility_percent
            
        except Exception as e:
            logger.error(f"Error checking market stability: {e}")
            return True
    
    def _is_in_entry_window(self) -> bool:
        """
        Check if current time is in an entry window.
        
        Returns:
            True if in entry window
        """
        now = datetime.utcnow().time()
        
        for window in self.config.entry_windows:
            start = self._parse_time(window.get("start", "00:00"))
            end = self._parse_time(window.get("end", "23:59"))
            
            if start <= now <= end:
                return True
        
        return False
    
    def _has_conditions_worsened(self, instrument: str) -> bool:
        """
        Check if conditions have worsened significantly.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            True if conditions have worsened
        """
        # Compare current spread with historical spread
        # This would require tracking historical spreads
        # For now, just return False
        return False
    
    def _cleanup_queue(self) -> None:
        """Clean up old queued signals."""
        now = datetime.utcnow()
        to_remove = []
        
        for signal_id, timestamp in self.signal_timestamps.items():
            if (now - timestamp).total_seconds() > self.config.queue_timeout_seconds:
                to_remove.append(signal_id)
        
        for signal_id in to_remove:
            del self.queued_signals[signal_id]
            del self.signal_timestamps[signal_id]
            self.logger.info(f"Removed expired signal from queue: {signal_id}")
    
    def _parse_time(self, time_str: str) -> Any:
        """
        Parse time string to time object.
        
        Args:
            time_str: Time string in HH:MM format
            
        Returns:
            time object
        """
        from datetime import time
        try:
            hour, minute = map(int, time_str.split(":"))
            return time(hour, minute)
        except:
            return time(0, 0)
    
    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get the status of the signal queue.
        
        Returns:
            Queue status dictionary
        """
        return {
            "queued_count": len(self.queued_signals),
            "max_queued": self.config.max_queued_orders,
            "oldest_signal_age_seconds": self._get_oldest_signal_age()
        }
    
    def _get_oldest_signal_age(self) -> float:
        """
        Get the age of the oldest queued signal.
        
        Returns:
            Age in seconds
        """
        if not self.signal_timestamps:
            return 0.0
        
        now = datetime.utcnow()
        oldest = min(self.signal_timestamps.values())
        return (now - oldest).total_seconds()


# Register strategy
_strategy = EntryOptimizationStrategy()


def get_entry_optimization_strategy(config: Optional[EntryOptimizationConfig] = None) -> EntryOptimizationStrategy:
    """
    Get the Entry Optimization strategy instance.
    
    Args:
        config: Optional configuration
        
    Returns:
        EntryOptimizationStrategy instance
    """
    return EntryOptimizationStrategy("entry_optimization", config)
