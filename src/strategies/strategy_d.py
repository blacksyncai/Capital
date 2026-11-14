"""
Strategy D: Adaptive Holding Periods

Compare different holding periods to optimize P&L and costs.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
import logging
import random

from .base_strategy import BaseStrategy, StrategyConfig, TradeSignal, StrategyResult


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class AdaptiveHoldingConfig(StrategyConfig):
    """Configuration for Adaptive Holding strategy."""
    # Holding period configurations to test
    holding_periods_minutes: List[float] = field(default_factory=lambda: [
        1, 5, 15, 30, 60, 120, 240, 480, 1440
    ])
    
    # Adaptive selection
    adaptive_selection: bool = True
    selection_criteria: str = "sharpe_ratio"  # Options: pnl, sharpe_ratio, win_rate, profit_factor
    selection_window_trades: int = 100
    
    # Performance metrics
    metrics_to_track: List[str] = field(default_factory=lambda: [
        "net_pnl",
        "win_rate",
        "profit_factor",
        "sharpe_ratio",
        "max_drawdown",
        "average_holding_time",
    ])
    
    # Cost consideration
    consider_swap_costs: bool = True
    consider_commission: bool = True
    consider_slippage: bool = True
    
    # Minimum and maximum holding times
    min_holding_minutes: float = 1
    max_holding_minutes: float = 1440


class AdaptiveHoldingStrategy(BaseStrategy):
    """
    Adaptive Holding Strategy
    
    Tests different holding periods and adapts to the best performing one.
    """
    
    def __init__(self, strategy_id: str = "adaptive_holding", config: Optional[AdaptiveHoldingConfig] = None):
        """
        Initialize the Adaptive Holding strategy.
        
        Args:
            strategy_id: Strategy identifier
            config: Strategy configuration
        """
        if config is None:
            config = AdaptiveHoldingConfig(
                strategy_id=strategy_id,
                name="Adaptive Holding",
                description="Compare different holding periods to optimize P&L and costs"
            )
        
        super().__init__(strategy_id, config)
        self.config: AdaptiveHoldingConfig = config
        
        # State tracking
        self.period_performance: Dict[float, Dict[str, float]] = {}
        self.current_period: float = self.config.holding_periods_minutes[0]
        self.trade_count: Dict[float, int] = {}
        self.selected_period: Optional[float] = None
        
        # Initialize performance tracking
        for period in self.config.holding_periods_minutes:
            self.period_performance[period] = {
                "net_pnl": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
            }
            self.trade_count[period] = 0
    
    def initialize(self) -> None:
        """Initialize the strategy."""
        super().initialize()
        
        # Select initial period
        if self.config.adaptive_selection:
            self._select_best_period()
        else:
            self.current_period = self.config.holding_periods_minutes[0]
    
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
        
        # Select holding period
        if self.config.adaptive_selection:
            self._select_best_period()
        
        # Generate signal with selected period
        instrument = self.config.parameters.get("instrument", "XAUUSD")
        lot_size = self.config.parameters.get("lot_size", 0.01)
        direction = self.config.parameters.get("direction", "BUY_SELL")
        
        return self._create_signal(
            action="OPEN",
            instrument=instrument,
            direction=direction,
            lot_size=lot_size,
            metadata={"holding_period_minutes": self.current_period}
        )
    
    def should_close_cycle(self, cycle_id: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Determine if a cycle should be closed based on holding period.
        
        Args:
            cycle_id: Cycle ID
            context: Context dictionary
            
        Returns:
            Tuple of (should_close, reason)
        """
        state = self.trade_state_manager.get_cycle_state(cycle_id)
        if state is None:
            return (False, "cycle_not_found")
        
        # Get the holding period for this cycle
        holding_period = self.current_period
        
        # Check if holding time has been reached
        if state.opened_time:
            holding_minutes = (datetime.utcnow() - state.opened_time).total_seconds() / 60
            if holding_minutes >= holding_period:
                return (True, f"holding_period_reached_{holding_period}m")
        
        # Also check for stop loss
        pnl_info = self.trade_state_manager.get_cycle_pnl(cycle_id)
        if pnl_info:
            combined_pnl = pnl_info.get("combined_pnl", 0.0)
            stop_loss = self.config.risk_overrides.get("stop_loss_usd", 5.0)
            if combined_pnl <= -stop_loss:
                return (True, f"stop_loss_reached_{stop_loss}")
        
        return (False, "no_close_condition")
    
    def _select_best_period(self) -> None:
        """Select the best performing holding period."""
        best_period = None
        best_score = float('-inf')
        
        for period, performance in self.period_performance.items():
            if self.trade_count[period] < 10:  # Minimum trades for selection
                continue
            
            score = self._calculate_score(performance)
            if score > best_score:
                best_score = score
                best_period = period
        
        if best_period:
            self.current_period = best_period
            self.selected_period = best_period
            self.logger.info(f"Selected best period: {best_period} minutes (score: {best_score:.4f})")
        else:
            # Not enough data, use default
            self.current_period = self.config.holding_periods_minutes[0]
    
    def _calculate_score(self, performance: Dict[str, float]) -> float:
        """
        Calculate a score for a holding period based on selection criteria.
        
        Args:
            performance: Performance metrics
            
        Returns:
            Score value
        """
        if self.config.selection_criteria == "pnl":
            return performance.get("net_pnl", 0.0)
        elif self.config.selection_criteria == "sharpe_ratio":
            return performance.get("sharpe_ratio", 0.0)
        elif self.config.selection_criteria == "win_rate":
            return performance.get("win_rate", 0.0)
        elif self.config.selection_criteria == "profit_factor":
            return performance.get("profit_factor", 0.0)
        else:
            # Default to net P&L
            return performance.get("net_pnl", 0.0)
    
    def on_cycle_closed(self, cycle_id: str, pnl: float) -> None:
        """
        Called when a cycle is closed.
        
        Args:
            cycle_id: Cycle ID
            pnl: Cycle P&L
        """
        state = self.trade_state_manager.get_cycle_state(cycle_id)
        if state is None:
            return
        
        # Get the holding period used for this cycle
        # This would need to be stored when the cycle was opened
        # For now, assume it's the current period
        period = self.current_period
        
        # Update performance
        if period in self.period_performance:
            perf = self.period_performance[period]
            perf["total_trades"] += 1
            
            if pnl > 0:
                perf["winning_trades"] += 1
            else:
                perf["losing_trades"] += 1
            
            perf["net_pnl"] += pnl
            
            # Update derived metrics
            total_trades = perf["total_trades"]
            winning_trades = perf["winning_trades"]
            losing_trades = perf["losing_trades"]
            
            if total_trades > 0:
                perf["win_rate"] = winning_trades / total_trades
            
            if losing_trades > 0:
                perf["profit_factor"] = (winning_trades / total_trades) / (losing_trades / total_trades)
            else:
                perf["profit_factor"] = float('inf')
        
        self.trade_count[period] += 1
    
    def get_period_performance(self) -> Dict[float, Dict[str, float]]:
        """
        Get performance for all holding periods.
        
        Returns:
            Dictionary of period -> performance metrics
        """
        return self.period_performance.copy()
    
    def get_selected_period(self) -> float:
        """
        Get the currently selected holding period.
        
        Returns:
            Selected holding period in minutes
        """
        return self.current_period


# Register strategy
_strategy = AdaptiveHoldingStrategy()


def get_adaptive_holding_strategy(config: Optional[AdaptiveHoldingConfig] = None) -> AdaptiveHoldingStrategy:
    """
    Get the Adaptive Holding strategy instance.
    
    Args:
        config: Optional configuration
        
    Returns:
        AdaptiveHoldingStrategy instance
    """
    return AdaptiveHoldingStrategy("adaptive_holding", config)
