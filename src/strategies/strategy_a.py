"""
Strategy A: Paired Exit

Open opposing positions and close both when combined P&L reaches a target,
a stop condition, or a maximum holding period.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
import logging

from .base_strategy import BaseStrategy, StrategyConfig, TradeSignal, StrategyResult


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class PairedExitConfig(StrategyConfig):
    """Configuration for Paired Exit strategy."""
    take_profit_usd: float = 5.0
    stop_loss_usd: float = 3.0
    max_holding_minutes: float = 1440  # 24 hours
    time_check_interval_seconds: float = 60
    
    # Entry conditions
    max_entry_spread_points: float = 10
    min_spread_stability_seconds: float = 30
    
    # Exit conditions
    exit_on_target: bool = True
    exit_on_stop: bool = True
    exit_on_time: bool = True
    exit_on_margin_warning: bool = True


class PairedExitStrategy(BaseStrategy):
    """
    Paired Exit Strategy
    
    Opens opposing positions on two brokers and closes both when:
    - Combined P&L reaches take profit target
    - Combined P&L reaches stop loss
    - Maximum holding time is reached
    - Margin warning is triggered
    """
    
    def __init__(self, strategy_id: str = "paired_exit", config: Optional[PairedExitConfig] = None):
        """
        Initialize the Paired Exit strategy.
        
        Args:
            strategy_id: Strategy identifier
            config: Strategy configuration
        """
        if config is None:
            config = PairedExitConfig(
                strategy_id=strategy_id,
                name="Paired Exit",
                description="Open opposing positions and close both when combined P&L reaches target"
            )
        
        super().__init__(strategy_id, config)
        self.config: PairedExitConfig = config
        
        # State
        self.last_spread_check_time: Dict[str, datetime] = {}
        self.spread_history: Dict[str, List[float]] = {}
    
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
            self.logger.debug(f"Cannot trade: {reasons}")
            return None
        
        # Check if we have active cycles
        active_cycles = self.trade_state_manager.get_active_cycles()
        for cycle_id, state in active_cycles.items():
            if state.strategy_id == self.strategy_id:
                self.logger.debug(f"Already have active cycle: {cycle_id}")
                return None
        
        # Check spread conditions
        instrument = self.config.parameters.get("instrument", "XAUUSD")
        
        try:
            # Get spreads from both brokers
            broker_a_spread = self._get_spread("vantage", instrument)
            broker_b_spread = self._get_spread("justmarkets", instrument)
            
            if broker_a_spread is None or broker_b_spread is None:
                self.logger.debug("Cannot get spreads from both brokers")
                return None
            
            # Check if spreads are within limits
            if broker_a_spread > self.config.max_entry_spread_points:
                self.logger.debug(f"Broker A spread too wide: {broker_a_spread}")
                return None
            
            if broker_b_spread > self.config.max_entry_spread_points:
                self.logger.debug(f"Broker B spread too wide: {broker_b_spread}")
                return None
            
            # Check spread stability
            if not self._is_spread_stable(instrument):
                self.logger.debug(f"Spread not stable for {instrument}")
                return None
            
            # All conditions met, generate signal
            lot_size = self.config.parameters.get("lot_size", 0.01)
            direction = self.config.parameters.get("direction", "BUY_SELL")
            
            return self._create_signal(
                action="OPEN",
                instrument=instrument,
                direction=direction,
                lot_size=lot_size,
                confidence=1.0,
                priority=1
            )
            
        except Exception as e:
            self.logger.error(f"Error generating signal: {e}")
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
        
        # Check if already closing or closed
        if state.status.value not in ["OPEN", "OPENING"]:
            return (False, "already_closing_or_closed")
        
        # Get P&L
        pnl_info = self.trade_state_manager.get_cycle_pnl(cycle_id)
        if pnl_info is None:
            return (False, "pnl_not_available")
        
        combined_pnl = pnl_info.get("combined_pnl", 0.0)
        
        # Check take profit
        if self.config.exit_on_target and combined_pnl >= self.config.take_profit_usd:
            return (True, f"take_profit_reached_{self.config.take_profit_usd}")
        
        # Check stop loss
        if self.config.exit_on_stop and combined_pnl <= -self.config.stop_loss_usd:
            return (True, f"stop_loss_reached_{self.config.stop_loss_usd}")
        
        # Check holding time
        if self.config.exit_on_time and state.opened_time:
            holding_minutes = (datetime.utcnow() - state.opened_time).total_seconds() / 60
            if holding_minutes >= self.config.max_holding_minutes:
                return (True, f"max_holding_time_reached_{self.config.max_holding_minutes}")
        
        # Check margin warning
        if self.config.exit_on_margin_warning:
            for broker_id in ["vantage", "justmarkets"]:
                account_info = self.order_manager.get_account_info(broker_id)
                if account_info:
                    min_margin = self.config.risk_overrides.get("min_free_margin_percent", 50.0)
                    if account_info.margin_percent < min_margin:
                        return (True, f"margin_warning_{broker_id}")
        
        return (False, "no_close_condition")
    
    def _get_spread(self, broker_id: str, instrument: str) -> Optional[float]:
        """
        Get the current spread for an instrument from a broker.
        
        Args:
            broker_id: Broker identifier
            instrument: Instrument symbol
            
        Returns:
            Spread in points or None
        """
        try:
            tick = self.order_manager.get_tick(broker_id, instrument)
            if tick:
                return tick.spread
        except Exception as e:
            self.logger.error(f"Error getting spread from {broker_id}: {e}")
        return None
    
    def _is_spread_stable(self, instrument: str, window_seconds: float = 30) -> bool:
        """
        Check if the spread has been stable.
        
        Args:
            instrument: Instrument symbol
            window_seconds: Time window to check
            
        Returns:
            True if spread is stable
        """
        now = datetime.utcnow()
        
        # Get spreads from both brokers
        spreads = []
        for broker_id in ["vantage", "justmarkets"]:
            try:
                tick = self.order_manager.get_tick(broker_id, instrument)
                if tick:
                    spreads.append(tick.spread)
            except Exception as e:
                self.logger.error(f"Error getting spread for stability check: {e}")
        
        if not spreads:
            return False
        
        # Check if all spreads are within limits
        for spread in spreads:
            if spread > self.config.max_entry_spread_points:
                return False
        
        # For now, just check if spreads are reasonable
        # In a production system, we would track historical spreads
        return True
    
    def get_config(self) -> PairedExitConfig:
        """Get the configuration."""
        return self.config
    
    def set_config(self, config: PairedExitConfig) -> None:
        """Set the configuration."""
        self.config = config
        self.logger.info(f"Configuration updated: {config}")


# Register strategy
_strategy = PairedExitStrategy()


def get_paired_exit_strategy(config: Optional[PairedExitConfig] = None) -> PairedExitStrategy:
    """
    Get the Paired Exit strategy instance.
    
    Args:
        config: Optional configuration
        
    Returns:
        PairedExitStrategy instance
    """
    return PairedExitStrategy("paired_exit", config)
