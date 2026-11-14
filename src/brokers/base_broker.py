"""
Base Broker Module

Abstract base class for all broker implementations.
Defines the interface for broker connectivity, market data, and order execution.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any, Tuple, Union, Callable, AsyncGenerator
import logging

import pandas as pd
import numpy as np

from ..core.config import get_config, BrokerConfig
from ..core.logging import get_logger


# Configure logging
logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Order types."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderSide(Enum):
    """Order sides (BUY/SELL)."""
    BUY = "BUY"
    SELL = "SELL"


class PositionSide(Enum):
    """Position sides."""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    """Order status."""
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PositionStatus(Enum):
    """Position status."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CLOSING = "CLOSING"


class TradeType(Enum):
    """Trade types for paired trading."""
    PAIRED = "PAIRED"
    RUNNER = "RUNNER"
    SINGLE = "SINGLE"


@dataclass
class TickData:
    """Market tick data."""
    broker_id: str
    instrument: str
    bid: float
    ask: float
    timestamp: datetime
    server_timestamp: Optional[datetime] = None
    volume: float = 0.0
    
    @property
    def spread(self) -> float:
        """Calculate spread."""
        return self.ask - self.bid
    
    @property
    def mid(self) -> float:
        """Calculate mid price."""
        return (self.bid + self.ask) / 2


@dataclass
class BarData:
    """OHLCV bar data."""
    broker_id: str
    instrument: str
    timeframe: str  # e.g., "M1", "M5", "H1"
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    tick_volume: float = 0.0


@dataclass
class Order:
    """Order representation."""
    order_id: str
    broker_id: str
    account_id: str
    instrument: str
    order_type: OrderType
    side: OrderSide
    volume: float
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    timestamp: datetime = field(default_factory=datetime.utcnow)
    filled_volume: float = 0.0
    filled_price: Optional[float] = None
    commission: float = 0.0
    swap: float = 0.0
    slippage: float = 0.0
    comment: str = ""
    magic_number: Optional[int] = None
    position_id: Optional[str] = None


@dataclass
class Position:
    """Open position representation."""
    position_id: str
    broker_id: str
    account_id: str
    instrument: str
    side: PositionSide
    volume: float
    open_price: float
    open_time: datetime
    current_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    commission: float = 0.0
    swap: float = 0.0
    profit: float = 0.0
    magic_number: Optional[int] = None
    status: PositionStatus = PositionStatus.OPEN
    comment: str = ""
    comment: str = ""
    
    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized P&L."""
        if self.side == PositionSide.BUY:
            return (self.current_price - self.open_price) * self.volume
        else:
            return (self.open_price - self.current_price) * self.volume


@dataclass
class AccountInfo:
    """Account information."""
    broker_id: str
    account_id: str
    balance: float
    equity: float
    free_margin: float
    margin: float
    margin_level: float
    currency: str
    leverage: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def margin_percent(self) -> float:
        """Calculate margin percentage."""
        if self.equity > 0:
            return (self.free_margin / self.equity) * 100
        return 0.0


@dataclass
class ContractSpec:
    """Contract specifications for an instrument."""
    instrument: str
    contract_size: float
    tick_value: float
    tick_size: float
    margin_requirement_percent: float
    swap_long: float
    swap_short: float
    trading_hours: str
    min_lot_size: float = 0.01
    max_lot_size: float = 100.0
    lot_size_step: float = 0.01


class BrokerError(Exception):
    """Base broker error."""
    pass


class ConnectionError(BrokerError):
    """Broker connection error."""
    pass


class OrderError(BrokerError):
    """Order execution error."""
    pass


class PositionError(BrokerError):
    """Position management error."""
    pass


class MarketDataError(BrokerError):
    """Market data error."""
    pass


class BaseBroker(ABC):
    """
    Abstract base class for broker implementations.
    
    All broker implementations must inherit from this class and implement
    the required methods for connectivity, market data, and order execution.
    """
    
    def __init__(self, broker_id: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the broker.
        
        Args:
            broker_id: Unique broker identifier
            config: Broker configuration
        """
        self.broker_id = broker_id
        self.config = config or get_config().get_broker_config(broker_id)
        self.connected = False
        self.logger = get_logger(f"broker.{broker_id}")
        
        # Account information
        self.account_info: Optional[AccountInfo] = None
        
        # Instrument mapping
        self.instrument_mapping: Dict[str, str] = self.config.get("instrument_mapping", {})
        
        # Contract specifications
        self.contract_specs: Dict[str, ContractSpec] = {}
        self._load_contract_specs()
    
    def _load_contract_specs(self) -> None:
        """Load contract specifications from configuration."""
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
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Connect to the broker.
        
        Returns:
            True if connection successful, False otherwise
            
        Raises:
            ConnectionError: If connection fails
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the broker."""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if connected to the broker.
        
        Returns:
            True if connected, False otherwise
        """
        pass
    
    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        """
        Get account information.
        
        Returns:
            AccountInfo object
            
        Raises:
            ConnectionError: If not connected
        """
        pass
    
    @abstractmethod
    def get_tick(self, instrument: str) -> TickData:
        """
        Get current tick data for an instrument.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            TickData object
            
        Raises:
            MarketDataError: If tick data cannot be retrieved
        """
        pass
    
    @abstractmethod
    def get_bid_ask(self, instrument: str) -> Tuple[float, float]:
        """
        Get bid and ask prices for an instrument.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            Tuple of (bid, ask) prices
            
        Raises:
            MarketDataError: If prices cannot be retrieved
        """
        pass
    
    @abstractmethod
    def get_bars(
        self,
        instrument: str,
        timeframe: str,
        count: int,
        start_time: Optional[datetime] = None
    ) -> List[BarData]:
        """
        Get historical bar data.
        
        Args:
            instrument: Instrument symbol
            timeframe: Timeframe (e.g., "M1", "M5", "H1", "D1")
            count: Number of bars to retrieve
            start_time: Optional start time
            
        Returns:
            List of BarData objects
            
        Raises:
            MarketDataError: If bar data cannot be retrieved
        """
        pass
    
    @abstractmethod
    def get_open_positions(self) -> List[Position]:
        """
        Get all open positions.
        
        Returns:
            List of Position objects
            
        Raises:
            ConnectionError: If not connected
        """
        pass
    
    @abstractmethod
    def get_position(self, position_id: str) -> Optional[Position]:
        """
        Get a specific position by ID.
        
        Args:
            position_id: Position ID
            
        Returns:
            Position object or None if not found
        """
        pass
    
    @abstractmethod
    def send_order(
        self,
        instrument: str,
        side: OrderSide,
        volume: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        comment: str = "",
        magic_number: Optional[int] = None
    ) -> Order:
        """
        Send an order to the broker.
        
        Args:
            instrument: Instrument symbol
            side: Order side (BUY/SELL)
            volume: Order volume in lots
            order_type: Order type (MARKET, LIMIT, etc.)
            price: Price for LIMIT orders
            stop_loss: Stop loss price
            take_profit: Take profit price
            comment: Order comment
            magic_number: Magic number for EA identification
            
        Returns:
            Order object with order details
            
        Raises:
            OrderError: If order cannot be sent
            ConnectionError: If not connected
        """
        pass
    
    @abstractmethod
    def close_position(self, position_id: str, volume: Optional[float] = None) -> bool:
        """
        Close a position.
        
        Args:
            position_id: Position ID to close
            volume: Volume to close (None = close all)
            
        Returns:
            True if position closed successfully
            
        Raises:
            PositionError: If position cannot be closed
            ConnectionError: If not connected
        """
        pass
    
    @abstractmethod
    def modify_order(
        self,
        order_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> bool:
        """
        Modify an existing order.
        
        Args:
            order_id: Order ID to modify
            stop_loss: New stop loss price
            take_profit: New take profit price
            
        Returns:
            True if order modified successfully
            
        Raises:
            OrderError: If order cannot be modified
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if order cancelled successfully
            
        Raises:
            OrderError: If order cannot be cancelled
        """
        pass
    
    @abstractmethod
    def get_open_orders(self) -> List[Order]:
        """
        Get all open orders.
        
        Returns:
            List of Order objects
        """
        pass
    
    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get a specific order by ID.
        
        Args:
            order_id: Order ID
            
        Returns:
            Order object or None if not found
        """
        pass
    
    # Async methods
    @abstractmethod
    async def connect_async(self) -> bool:
        """
        Connect to the broker asynchronously.
        
        Returns:
            True if connection successful
        """
        pass
    
    @abstractmethod
    async def get_tick_async(self, instrument: str) -> TickData:
        """
        Get current tick data asynchronously.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            TickData object
        """
        pass
    
    @abstractmethod
    async def send_order_async(
        self,
        instrument: str,
        side: OrderSide,
        volume: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        comment: str = "",
        magic_number: Optional[int] = None
    ) -> Order:
        """
        Send an order asynchronously.
        
        Args:
            instrument: Instrument symbol
            side: Order side
            volume: Order volume
            order_type: Order type
            price: Price for LIMIT orders
            stop_loss: Stop loss price
            take_profit: Take profit price
            comment: Order comment
            magic_number: Magic number
            
        Returns:
            Order object
        """
        pass
    
    # Utility methods
    def map_instrument(self, standard_symbol: str) -> str:
        """
        Map standard symbol to broker-specific symbol.
        
        Args:
            standard_symbol: Standard instrument symbol
            
        Returns:
            Broker-specific symbol
        """
        return self.instrument_mapping.get(standard_symbol, standard_symbol)
    
    def get_contract_spec(self, instrument: str) -> Optional[ContractSpec]:
        """
        Get contract specifications for an instrument.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            ContractSpec object or None
        """
        return self.contract_specs.get(instrument)
    
    def calculate_margin(self, instrument: str, volume: float) -> float:
        """
        Calculate required margin for a position.
        
        Args:
            instrument: Instrument symbol
            volume: Position volume in lots
            
        Returns:
            Required margin in account currency
        """
        spec = self.get_contract_spec(instrument)
        if spec is None:
            raise ValueError(f"No contract spec for instrument: {instrument}")
        
        # For CFDs, margin = volume * contract_size * price * margin_requirement
        # We use current price approximation
        try:
            bid, ask = self.get_bid_ask(instrument)
            price = (bid + ask) / 2
        except:
            price = 1.0  # Default for calculation
        
        margin = volume * spec.contract_size * price * (spec.margin_requirement_percent / 100)
        return margin
    
    def calculate_pip_value(self, instrument: str, volume: float) -> float:
        """
        Calculate pip value for a position.
        
        Args:
            instrument: Instrument symbol
            volume: Position volume in lots
            
        Returns:
            Value per pip in account currency
        """
        spec = self.get_contract_spec(instrument)
        if spec is None:
            raise ValueError(f"No contract spec for instrument: {instrument}")
        
        return volume * spec.contract_size * spec.tick_value
    
    def validate_lot_size(self, volume: float) -> bool:
        """
        Validate lot size against broker requirements.
        
        Args:
            volume: Lot size to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Check against all contract specs
        for spec in self.contract_specs.values():
            if volume < spec.min_lot_size or volume > spec.max_lot_size:
                return False
            # Check if volume is multiple of step
            if (volume - spec.min_lot_size) % spec.lot_size_step != 0:
                return False
        return True


# Broker factory function
def create_broker(broker_id: str, config: Optional[Dict[str, Any]] = None) -> BaseBroker:
    """
    Factory function to create broker instances.
    
    Args:
        broker_id: Broker identifier (vantage, justmarkets)
        config: Optional configuration override
        
    Returns:
        Broker instance
    """
    broker_classes = {
        "vantage": "VantageBroker",
        "justmarkets": "JustMarketsBroker",
    }
    
    if broker_id not in broker_classes:
        raise ValueError(f"Unknown broker: {broker_id}")
    
    # Import dynamically to avoid circular imports
    module_name = broker_classes[broker_id].replace("Broker", "").lower()
    try:
        module = __import__(f"..{module_name}_broker", fromlist=[broker_classes[broker_id]])
        broker_class = getattr(module, broker_classes[broker_id])
        return broker_class(broker_id, config)
    except ImportError as e:
        raise ImportError(f"Cannot import broker module for {broker_id}: {e}")
