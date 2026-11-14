"""
Strategies Module

Provides trading strategy implementations.
"""

from .base_strategy import BaseStrategy, StrategyError, get_strategy
from .strategy_a import PairedExitStrategy, get_paired_exit_strategy
from .strategy_b import ProtectedRunnerStrategy, get_protected_runner_strategy
from .strategy_c import MarketConditionExitsStrategy, get_market_condition_exits_strategy
from .strategy_d import AdaptiveHoldingStrategy, get_adaptive_holding_strategy
from .strategy_e import EntryOptimizationStrategy, get_entry_optimization_strategy

__all__ = [
    "BaseStrategy",
    "StrategyError",
    "get_strategy",
    "PairedExitStrategy",
    "get_paired_exit_strategy",
    "ProtectedRunnerStrategy",
    "get_protected_runner_strategy",
    "MarketConditionExitsStrategy",
    "get_market_condition_exits_strategy",
    "AdaptiveHoldingStrategy",
    "get_adaptive_holding_strategy",
    "EntryOptimizationStrategy",
    "get_entry_optimization_strategy",
]
