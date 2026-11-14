"""
Cross-Broker AI Trading & Strategy Research System

A comprehensive trading system for managing opposing CFD positions
across multiple brokers with AI-assisted strategy research.
"""

__version__ = "0.1.0"
__author__ = "Quantitative Development Team"
__description__ = "Cross-Broker CFD Trading System"

# System modules
from .core import config, database, logging
from .brokers import BaseBroker, VantageBroker, JustMarketsBroker
from .execution import OrderManager, TradeStateManager, ExecutionWorker
from .risk import RiskEngine
from .strategies import (
    BaseStrategy,
    PairedExitStrategy,
    ProtectedRunnerStrategy,
    MarketConditionExitsStrategy,
    AdaptiveHoldingStrategy,
    EntryOptimizationStrategy,
)
from .ai_research import DataAnalyzer, PatternDetector, ReportGenerator
from .models import (
    Trade,
    MarketData,
    Account,
    Position,
    Order,
    Rebate,
    TradeCycle,
)

__all__ = [
    # Core
    "config",
    "database",
    "logging",
    # Brokers
    "BaseBroker",
    "VantageBroker",
    "JustMarketsBroker",
    # Execution
    "OrderManager",
    "TradeStateManager",
    "ExecutionWorker",
    # Risk
    "RiskEngine",
    # Strategies
    "BaseStrategy",
    "PairedExitStrategy",
    "ProtectedRunnerStrategy",
    "MarketConditionExitsStrategy",
    "AdaptiveHoldingStrategy",
    "EntryOptimizationStrategy",
    # AI Research
    "DataAnalyzer",
    "PatternDetector",
    "ReportGenerator",
    # Models
    "Trade",
    "MarketData",
    "Account",
    "Position",
    "Order",
    "Rebate",
    "TradeCycle",
]
