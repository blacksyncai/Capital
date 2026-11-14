"""
Strategy C: Market Condition Exits

Exit based on volatility, momentum, spread conditions, and market sessions.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, time
from typing import Optional, Dict, List, Any, Tuple
import logging
import math

from .base_strategy import BaseStrategy, StrategyConfig, TradeSignal, StrategyResult


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class MarketConditionConfig(StrategyConfig):
    """Configuration for Market Condition Exits strategy."""
    # Volatility conditions
    volatility_period_minutes: int = 15
    exit_on_high_volatility: bool = True
    high_volatility_threshold: float = 0.02  # 2% price movement
    exit_on_low_volatility: bool = False
    low_volatility_threshold: float = 0.001  # 0.1% price movement
    
    # Momentum conditions
    momentum_period_minutes: int = 30
    exit_on_strong_momentum: bool = True
    momentum_threshold: float = 0.01  # 1% price movement
    exit_on_weak_momentum: bool = False
    
    # Spread conditions
    exit_on_widening_spread: bool = True
    spread_widening_threshold_percent: float = 50
    exit_on_narrow_spread: bool = False
    narrow_spread_threshold_points: float = 1
    
    # Market session conditions
    london_open: str = "08:00"
    london_close: str = "17:00"
    new_york_open: str = "13:00"
    new_york_close: str = "22:00"
    asian_open: str = "00:00"
    asian_close: str = "09:00"
    exit_before_session_end_minutes: int = 30
    exit_at_session_end: bool = True
    
    # Price behavior
    exit_on_reversal: bool = True
    reversal_threshold_percent: float = 0.5
    exit_on_consolidation: bool = False
    consolidation_threshold_percent: float = 0.1


class MarketConditionExitsStrategy(BaseStrategy):
    """
    Market Condition Exits Strategy
    
    Exits trades based on market conditions including:
    - Volatility
    - Momentum
    - Spread conditions
    - Market sessions
    - Short-term price behavior
    """
    
    def __init__(self, strategy_id: str = "market_condition_exits", config: Optional[MarketConditionConfig] = None):
        """
        Initialize the Market Condition Exits strategy.
        
        Args:
            strategy_id: Strategy identifier
            config: Strategy configuration
        """
        if config is None:
            config = MarketConditionConfig(
                strategy_id=strategy_id,
                name="Market Condition Exits",
                description="Exit based on volatility, momentum, spread conditions, and market sessions"
            )
        
        super().__init__(strategy_id, config)
        self.config: MarketConditionConfig = config
        
        # State tracking
        self.price_history: Dict[str, List[Tuple[datetime, float]]] = {}
        self.spread_history: Dict[str, List[Tuple[datetime, float]]] = {}
    
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
        
        # Check market conditions for entry
        instrument = self.config.parameters.get("instrument", "XAUUSD")
        
        # Check if it's a good time to enter
        if not self._is_good_entry_time():
            return None
        
        # Check spread conditions
        if not self._is_good_spread_condition(instrument):
            return None
        
        # All conditions met
        lot_size = self.config.parameters.get("lot_size", 0.01)
        direction = self.config.parameters.get("direction", "BUY_SELL")
        
        return self._create_signal(
            action="OPEN",
            instrument=instrument,
            direction=direction,
            lot_size=lot_size
        )
    
    def should_close_cycle(self, cycle_id: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Determine if a cycle should be closed based on market conditions.
        
        Args:
            cycle_id: Cycle ID
            context: Context dictionary
            
        Returns:
            Tuple of (should_close, reason)
        """
        state = self.trade_state_manager.get_cycle_state(cycle_id)
        if state is None:
            return (False, "cycle_not_found")
        
        instrument = state.instrument
        
        # Check volatility
        if self.config.exit_on_high_volatility:
            if self._is_high_volatility(instrument):
                return (True, "high_volatility")
        
        # Check low volatility
        if self.config.exit_on_low_volatility:
            if self._is_low_volatility(instrument):
                return (True, "low_volatility")
        
        # Check momentum
        if self.config.exit_on_strong_momentum:
            if self._is_strong_momentum(instrument):
                return (True, "strong_momentum")
        
        # Check spread widening
        if self.config.exit_on_widening_spread:
            if self._is_spread_widening(instrument):
                return (True, "spread_widening")
        
        # Check narrow spread
        if self.config.exit_on_narrow_spread:
            if self._is_spread_narrow(instrument):
                return (True, "narrow_spread")
        
        # Check session end
        if self.config.exit_at_session_end:
            if self._is_near_session_end():
                return (True, "near_session_end")
        
        # Check price reversal
        if self.config.exit_on_reversal:
            if self._is_price_reversal(instrument):
                return (True, "price_reversal")
        
        # Check consolidation
        if self.config.exit_on_consolidation:
            if self._is_consolidation(instrument):
                return (True, "consolidation")
        
        return (False, "no_close_condition")
    
    def _is_good_entry_time(self) -> bool:
        """
        Check if it's a good time to enter a trade.
        
        Returns:
            True if good entry time
        """
        now = datetime.utcnow().time()
        
        # Parse session times
        london_open = self._parse_time(self.config.london_open)
        london_close = self._parse_time(self.config.london_close)
        
        # Check if we're in London session
        if london_open <= now <= london_close:
            return True
        
        # For now, just return True
        # In a production system, we would have more sophisticated logic
        return True
    
    def _is_good_spread_condition(self, instrument: str) -> bool:
        """
        Check if spread conditions are good for entry.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            True if spread conditions are good
        """
        try:
            for broker_id in ["vantage", "justmarkets"]:
                tick = self.order_manager.get_tick(broker_id, instrument)
                if tick and tick.spread > self.config.narrow_spread_threshold_points * 2:
                    return False
            return True
        except Exception as e:
            logger.error(f"Error checking spread condition: {e}")
            return True  # Assume good if we can't check
    
    def _is_high_volatility(self, instrument: str) -> bool:
        """
        Check if volatility is high.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            True if high volatility
        """
        try:
            bars = self.order_manager.get_bars(
                broker_id="vantage",
                instrument=instrument,
                timeframe="M1",
                count=self.config.volatility_period_minutes
            )
            
            if len(bars) < 2:
                return False
            
            prices = [bar.close for bar in bars]
            price_range = max(prices) - min(prices)
            mid_price = sum(prices) / len(prices)
            volatility = price_range / mid_price
            
            return volatility > self.config.high_volatility_threshold
            
        except Exception as e:
            logger.error(f"Error checking volatility: {e}")
            return False
    
    def _is_low_volatility(self, instrument: str) -> bool:
        """
        Check if volatility is low.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            True if low volatility
        """
        try:
            bars = self.order_manager.get_bars(
                broker_id="vantage",
                instrument=instrument,
                timeframe="M1",
                count=self.config.volatility_period_minutes
            )
            
            if len(bars) < 2:
                return False
            
            prices = [bar.close for bar in bars]
            price_range = max(prices) - min(prices)
            mid_price = sum(prices) / len(prices)
            volatility = price_range / mid_price
            
            return volatility < self.config.low_volatility_threshold
            
        except Exception as e:
            logger.error(f"Error checking low volatility: {e}")
            return False
    
    def _is_strong_momentum(self, instrument: str) -> bool:
        """
        Check if there is strong momentum.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            True if strong momentum
        """
        try:
            bars = self.order_manager.get_bars(
                broker_id="vantage",
                instrument=instrument,
                timeframe="M1",
                count=self.config.momentum_period_minutes
            )
            
            if len(bars) < 2:
                return False
            
            # Simple momentum: price change over period
            first_price = bars[0].close
            last_price = bars[-1].close
            momentum = abs(last_price - first_price) / first_price
            
            return momentum > self.config.momentum_threshold
            
        except Exception as e:
            logger.error(f"Error checking momentum: {e}")
            return False
    
    def _is_spread_widening(self, instrument: str) -> bool:
        """
        Check if spread is widening.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            True if spread is widening
        """
        try:
            # Get current spreads
            current_spreads = []
            for broker_id in ["vantage", "justmarkets"]:
                tick = self.order_manager.get_tick(broker_id, instrument)
                if tick:
                    current_spreads.append(tick.spread)
            
            if not current_spreads:
                return False
            
            # Compare with historical spreads
            # For now, just check if current spread is above threshold
            avg_spread = sum(current_spreads) / len(current_spreads)
            
            # Check if spread has increased significantly
            # This would require historical data tracking
            # For now, just return False
            return False
            
        except Exception as e:
            logger.error(f"Error checking spread widening: {e}")
            return False
    
    def _is_spread_narrow(self, instrument: str) -> bool:
        """
        Check if spread is narrow.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            True if spread is narrow
        """
        try:
            for broker_id in ["vantage", "justmarkets"]:
                tick = self.order_manager.get_tick(broker_id, instrument)
                if tick and tick.spread <= self.config.narrow_spread_threshold_points:
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking narrow spread: {e}")
            return False
    
    def _is_near_session_end(self) -> bool:
        """
        Check if we're near a session end.
        
        Returns:
            True if near session end
        """
        now = datetime.utcnow().time()
        
        # Parse session times
        london_close = self._parse_time(self.config.london_close)
        new_york_close = self._parse_time(self.config.new_york_close)
        
        # Check if we're within X minutes of session end
        minutes_before = self.config.exit_before_session_end_minutes
        
        # London session end
        if self._time_within_minutes(now, london_close, minutes_before):
            return True
        
        # New York session end
        if self._time_within_minutes(now, new_york_close, minutes_before):
            return True
        
        return False
    
    def _is_price_reversal(self, instrument: str) -> bool:
        """
        Check for price reversal.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            True if price reversal detected
        """
        try:
            # Get recent bars
            bars = self.order_manager.get_bars(
                broker_id="vantage",
                instrument=instrument,
                timeframe="M5",
                count=10
            )
            
            if len(bars) < 3:
                return False
            
            # Simple reversal detection: check if recent bars are moving opposite to trend
            # This is a simplified version
            prices = [bar.close for bar in bars]
            
            # Calculate recent trend
            recent_trend = prices[-1] - prices[-3]
            
            # Calculate earlier trend
            earlier_trend = prices[-3] - prices[-6] if len(prices) >= 6 else 0
            
            # Reversal if trends are opposite
            if earlier_trend != 0 and recent_trend / earlier_trend < -0.5:
                reversal_percent = abs(recent_trend) / prices[-3] * 100
                return reversal_percent > self.config.reversal_threshold_percent
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking price reversal: {e}")
            return False
    
    def _is_consolidation(self, instrument: str) -> bool:
        """
        Check for price consolidation.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            True if price is consolidating
        """
        try:
            # Get recent bars
            bars = self.order_manager.get_bars(
                broker_id="vantage",
                instrument=instrument,
                timeframe="M5",
                count=20
            )
            
            if len(bars) < 5:
                return False
            
            prices = [bar.close for bar in bars]
            price_range = max(prices) - min(prices)
            mid_price = sum(prices) / len(prices)
            
            # Consolidation if price range is small
            consolidation_percent = price_range / mid_price * 100
            return consolidation_percent < self.config.consolidation_threshold_percent
            
        except Exception as e:
            logger.error(f"Error checking consolidation: {e}")
            return False
    
    def _parse_time(self, time_str: str) -> time:
        """
        Parse time string to time object.
        
        Args:
            time_str: Time string in HH:MM format
            
        Returns:
            time object
        """
        try:
            hour, minute = map(int, time_str.split(":"))
            return time(hour, minute)
        except:
            return time(0, 0)
    
    def _time_within_minutes(self, now: time, target: time, minutes: int) -> bool:
        """
        Check if current time is within X minutes of target time.
        
        Args:
            now: Current time
            target: Target time
            minutes: Minutes threshold
            
        Returns:
            True if within threshold
        """
        # Convert to total minutes
        now_minutes = now.hour * 60 + now.minute
        target_minutes = target.hour * 60 + target.minute
        
        # Calculate difference
        diff = abs(now_minutes - target_minutes)
        
        # Handle wrap-around (e.g., 23:50 and 00:10)
        if diff > 720:  # 12 hours
            diff = 1440 - diff
        
        return diff <= minutes


# Register strategy
_strategy = MarketConditionExitsStrategy()


def get_market_condition_exits_strategy(config: Optional[MarketConditionConfig] = None) -> MarketConditionExitsStrategy:
    """
    Get the Market Condition Exits strategy instance.
    
    Args:
        config: Optional configuration
        
    Returns:
        MarketConditionExitsStrategy instance
    """
    return MarketConditionExitsStrategy("market_condition_exits", config)
