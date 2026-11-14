"""
JustMarkets Broker Implementation

Concrete implementation of BaseBroker for JustMarkets.
Uses MetaTrader5 Python package for connectivity.
"""

import asyncio
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
import logging

from .base_broker import (
    BaseBroker,
    TickData,
    BarData,
    Order,
    Position,
    AccountInfo,
    ContractSpec,
    OrderType,
    OrderSide,
    PositionSide,
    OrderStatus,
    PositionStatus,
)
from .vantage_broker import VantageBroker


# Configure logging
logger = logging.getLogger(__name__)


class JustMarketsBroker(VantageBroker):
    """
    JustMarkets broker implementation.
    
    Extends VantageBroker since both use MT5, but with JustMarkets-specific
    configuration and contract specifications.
    """
    
    def __init__(self, broker_id: str = "justmarkets", config: Optional[Dict[str, Any]] = None):
        """
        Initialize JustMarkets broker.
        
        Args:
            broker_id: Broker identifier
            config: Broker configuration
        """
        # Call parent constructor with JustMarkets config
        if config is None:
            from ..core.config import get_config
            config = get_config().get_broker_config("justmarkets")
        
        super().__init__(broker_id, config)
        
        # Override broker-specific settings
        self.broker_id = "justmarkets"
        self._set_connection_parameters()
        
        # JustMarkets IB Rebate configuration
        self.ib_rebate_config = self.config.get("ib_rebate", {})
    
    def _set_connection_parameters(self) -> None:
        """Set connection parameters based on trading mode."""
        from ..core.config import get_config
        
        trading_mode = get_config().get_trading_mode()
        
        if trading_mode == "LIVE":
            live_config = self.config.get("live", {})
            self.server = live_config.get("server")
            self.login = live_config.get("login")
            self.password = live_config.get("password")
            self.account_type = live_config.get("account_type", "REAL")
        else:
            demo_config = self.config.get("demo", {})
            self.server = demo_config.get("server")
            self.login = demo_config.get("login")
            self.password = demo_config.get("password")
            self.account_type = demo_config.get("account_type", "DEMO")
    
    def connect(self) -> bool:
        """
        Connect to JustMarkets MT5 terminal.
        
        Returns:
            True if connection successful
        """
        logger.info(f"Connecting to JustMarkets MT5 terminal: {self.server}")
        return super().connect()
    
    def get_account_info(self) -> AccountInfo:
        """
        Get account information with JustMarkets-specific handling.
        
        Returns:
            AccountInfo object
        """
        account_info = super().get_account_info()
        account_info.broker_id = "justmarkets"
        return account_info
    
    # Override to use JustMarkets-specific contract specs
    def _load_contract_specs(self) -> None:
        """Load JustMarkets contract specifications."""
        specs = self.config.get("contract_specs", {})
        for instrument, spec_data in specs.items():
            self.contract_specs[instrument] = ContractSpec(
                instrument=instrument,
                contract_size=spec_data.get("contract_size", 1.0),
                tick_value=spec_data.get("tick_value", 0.01),
                tick_size=spec_data.get("tick_size", 0.01),
                margin_requirement_percent=spec_data.get("margin_requirement_percent", 1.0),
                swap_long=spec_data.get("swap_long", 0.0),
                swap_short=spec_data.get("swap_short", 0.0),
                trading_hours=spec_data.get("trading_hours", "00:00-23:59"),
                min_lot_size=spec_data.get("min_lot_size", 0.01),
                max_lot_size=spec_data.get("max_lot_size", 100.0),
                lot_size_step=spec_data.get("lot_size_step", 0.01),
            )
    
    # JustMarkets may have different instrument symbols
    def map_instrument(self, standard_symbol: str) -> str:
        """
        Map standard symbol to JustMarkets-specific symbol.
        
        Args:
            standard_symbol: Standard instrument symbol
            
        Returns:
            JustMarkets-specific symbol
        """
        # JustMarkets typically uses the same symbols as standard
        # But override if there are specific mappings
        mapping = self.config.get("instrument_mapping", {})
        return mapping.get(standard_symbol, standard_symbol)


# Factory function for creating JustMarkets broker
def create_justmarkets_broker(config: Optional[Dict[str, Any]] = None) -> JustMarketsBroker:
    """
    Factory function to create JustMarkets broker instance.
    
    Args:
        config: Optional configuration override
        
    Returns:
        JustMarketsBroker instance
    """
    return JustMarketsBroker("justmarkets", config)
