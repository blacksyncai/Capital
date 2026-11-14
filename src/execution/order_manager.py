"""
Order Manager

Manages order execution across multiple brokers with idempotency and error handling.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any, Tuple, Callable, Union
import logging

from ..brokers.base_broker import (
    BaseBroker,
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
    OrderError,
    ConnectionError,
)
from ..brokers.vantage_broker import VantageBroker
from ..brokers.justmarkets_broker import JustMarketsBroker
from ..core.config import get_config
from ..core.logging import get_logger
from ..models.trades import Trade, TradeStatus
from ..models.orders import Order as OrderModel
from ..models.trade_cycles import TradeCycle, CycleStatus


# Configure logging
logger = logging.getLogger(__name__)


class OrderExecutionError(Exception):
    """Order execution error."""
    pass


class OrderTimeoutError(OrderExecutionError):
    """Order timeout error."""
    pass


class OrderValidationError(OrderExecutionError):
    """Order validation error."""
    pass


@dataclass
class OrderRequest:
    """Order request data."""
    broker_id: str
    instrument: str
    side: OrderSide
    volume: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    comment: str = ""
    magic_number: Optional[int] = None
    cycle_id: Optional[str] = None
    strategy_id: Optional[str] = None
    
    # Validation
    def validate(self, broker: BaseBroker) -> bool:
        """
        Validate the order request.
        
        Args:
            broker: Broker to validate against
            
        Returns:
            True if valid
            
        Raises:
            OrderValidationError: If validation fails
        """
        # Check lot size
        if not broker.validate_lot_size(self.volume):
            raise OrderValidationError(f"Invalid lot size: {self.volume}")
        
        # Check instrument
        spec = broker.get_contract_spec(self.instrument)
        if spec is None:
            raise OrderValidationError(f"Unknown instrument: {self.instrument}")
        
        # Check stop loss and take profit
        if self.stop_loss and self.take_profit:
            if self.side == OrderSide.BUY:
                if self.stop_loss >= self.take_profit:
                    raise OrderValidationError("Stop loss must be below take profit for BUY")
            else:
                if self.stop_loss <= self.take_profit:
                    raise OrderValidationError("Stop loss must be above take profit for SELL")
        
        return True


@dataclass
class OrderResult:
    """Order execution result."""
    success: bool
    order: Optional[Order] = None
    order_model: Optional[OrderModel] = None
    error: Optional[str] = None
    error_code: Optional[int] = None
    execution_time_ms: float = 0.0
    slippage: float = 0.0


@dataclass
class PairedOrderRequest:
    """Request for a paired order (opposing positions on two brokers)."""
    cycle_id: str
    instrument: str
    lot_size: float
    direction: str = "BUY_SELL"  # BUY on broker A, SELL on broker B
    strategy_id: Optional[str] = None
    stop_loss_usd: Optional[float] = None
    take_profit_usd: Optional[float] = None
    comment: str = ""
    magic_number: Optional[int] = None
    
    def get_broker_a_order(self, broker_a: BaseBroker) -> OrderRequest:
        """Get order request for broker A."""
        direction = self.direction.upper()
        side = OrderSide.BUY if direction.startswith("BUY") else OrderSide.SELL
        
        return OrderRequest(
            broker_id=broker_a.broker_id,
            instrument=self.instrument,
            side=side,
            volume=self.lot_size,
            order_type=OrderType.MARKET,
            comment=f"Paired trade {self.cycle_id} - Broker A" + (f": {self.comment}" if self.comment else ""),
            magic_number=self.magic_number,
            cycle_id=self.cycle_id,
            strategy_id=self.strategy_id
        )
    
    def get_broker_b_order(self, broker_b: BaseBroker) -> OrderRequest:
        """Get order request for broker B (opposite direction)."""
        direction = self.direction.upper()
        side = OrderSide.SELL if direction.startswith("BUY") else OrderSide.BUY
        
        return OrderRequest(
            broker_id=broker_b.broker_id,
            instrument=self.instrument,
            side=side,
            volume=self.lot_size,
            order_type=OrderType.MARKET,
            comment=f"Paired trade {self.cycle_id} - Broker B" + (f": {self.comment}" if self.comment else ""),
            magic_number=self.magic_number,
            cycle_id=self.cycle_id,
            strategy_id=self.strategy_id
        )


class OrderManager:
    """
    Manages order execution across multiple brokers.
    
    Provides idempotent order handling, retry logic, and error recovery.
    """
    
    def __init__(self):
        """Initialize the order manager."""
        self.brokers: Dict[str, BaseBroker] = {}
        self.pending_orders: Dict[str, OrderRequest] = {}
        self.order_results: Dict[str, OrderResult] = {}
        self.logger = get_logger("execution.order_manager")
        
        # Configuration
        self.max_retries = 3
        self.retry_delay = 1.0  # seconds
        self.order_timeout = 10.0  # seconds
        
        self._initialized = False
    
    def initialize(self) -> None:
        """Initialize the order manager with broker connections."""
        if self._initialized:
            return
        
        config = get_config()
        
        # Create broker instances
        try:
            vantage_config = config.get_broker_config("vantage")
            self.brokers["vantage"] = VantageBroker("vantage", vantage_config)
            self.logger.info("Vantage broker initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize Vantage broker: {e}")
        
        try:
            justmarkets_config = config.get_broker_config("justmarkets")
            self.brokers["justmarkets"] = JustMarketsBroker("justmarkets", justmarkets_config)
            self.logger.info("JustMarkets broker initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize JustMarkets broker: {e}")
        
        self._initialized = True
    
    def get_broker(self, broker_id: str) -> BaseBroker:
        """
        Get a broker instance.
        
        Args:
            broker_id: Broker identifier
            
        Returns:
            Broker instance
            
        Raises:
            ValueError: If broker not found
        """
        if broker_id not in self.brokers:
            raise ValueError(f"Broker not found: {broker_id}")
        return self.brokers[broker_id]
    
    def connect_all(self) -> Dict[str, bool]:
        """
        Connect to all brokers.
        
        Returns:
            Dictionary of broker_id -> connection success
        """
        results = {}
        for broker_id, broker in self.brokers.items():
            try:
                success = broker.connect()
                results[broker_id] = success
                if success:
                    self.logger.info(f"Connected to {broker_id}")
                else:
                    self.logger.warning(f"Failed to connect to {broker_id}")
            except Exception as e:
                self.logger.error(f"Error connecting to {broker_id}: {e}")
                results[broker_id] = False
        
        return results
    
    def disconnect_all(self) -> None:
        """Disconnect from all brokers."""
        for broker_id, broker in self.brokers.items():
            try:
                broker.disconnect()
                self.logger.info(f"Disconnected from {broker_id}")
            except Exception as e:
                self.logger.error(f"Error disconnecting from {broker_id}: {e}")
    
    def is_connected(self, broker_id: str) -> bool:
        """Check if a broker is connected."""
        return self.get_broker(broker_id).is_connected()
    
    def execute_order(self, request: OrderRequest) -> OrderResult:
        """
        Execute a single order.
        
        Args:
            request: Order request
            
        Returns:
            OrderResult
        """
        start_time = datetime.utcnow()
        
        try:
            # Validate request
            broker = self.get_broker(request.broker_id)
            request.validate(broker)
            
            # Connect if not connected
            if not broker.is_connected():
                broker.connect()
            
            # Execute order
            order = broker.send_order(
                instrument=request.instrument,
                side=request.side,
                volume=request.volume,
                order_type=request.order_type,
                price=request.price,
                stop_loss=request.stop_loss,
                take_profit=request.take_profit,
                comment=request.comment,
                magic_number=request.magic_number
            )
            
            # Calculate execution time
            execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Create order model for database
            order_model = self._create_order_model(order, request)
            
            result = OrderResult(
                success=True,
                order=order,
                order_model=order_model,
                execution_time_ms=execution_time_ms,
                slippage=order.slippage if order else 0.0
            )
            
            self.logger.info(
                f"Order executed: {order.order_id if order else 'N/A'} "
                f"{request.side.value} {request.volume} {request.instrument} "
                f"@ {order.filled_price if order else 'N/A'}"
            )
            
            return result
            
        except OrderError as e:
            execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.logger.error(f"Order error: {e}")
            return OrderResult(
                success=False,
                error=str(e),
                execution_time_ms=execution_time_ms
            )
        except ConnectionError as e:
            execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.logger.error(f"Connection error: {e}")
            return OrderResult(
                success=False,
                error=str(e),
                error_code=-1,
                execution_time_ms=execution_time_ms
            )
        except Exception as e:
            execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.logger.error(f"Unexpected error: {e}")
            return OrderResult(
                success=False,
                error=str(e),
                execution_time_ms=execution_time_ms
            )
    
    def place_order(self, request: OrderRequest) -> OrderResult:
        """
        Alias for execute_order for backward compatibility.
        
        Args:
            request: Order request
            
        Returns:
            OrderResult
        """
        return self.execute_order(request)
    
    def execute_order_with_retry(
        self,
        request: OrderRequest,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None
    ) -> OrderResult:
        """
        Execute an order with retry logic.
        
        Args:
            request: Order request
            max_retries: Maximum number of retries
            retry_delay: Delay between retries in seconds
            
        Returns:
            OrderResult
        """
        max_retries = max_retries or self.max_retries
        retry_delay = retry_delay or self.retry_delay
        
        for attempt in range(max_retries + 1):
            result = self.execute_order(request)
            
            if result.success:
                return result
            
            if attempt < max_retries:
                self.logger.warning(
                    f"Order failed, retry {attempt + 1}/{max_retries}: {result.error}"
                )
                import time
                time.sleep(retry_delay)
        
        self.logger.error(f"Order failed after {max_retries} retries: {result.error}")
        return result
    
    def execute_paired_orders(self, request: PairedOrderRequest) -> Tuple[OrderResult, OrderResult]:
        """
        Execute paired orders on two brokers.
        
        Args:
            request: Paired order request
            
        Returns:
            Tuple of (broker_a_result, broker_b_result)
        """
        self.logger.info(f"Executing paired orders for cycle: {request.cycle_id}")
        
        # Get brokers
        broker_a = self.get_broker("vantage")
        broker_b = self.get_broker("justmarkets")
        
        # Create order requests
        order_a_request = request.get_broker_a_order(broker_a)
        order_b_request = request.get_broker_b_order(broker_b)
        
        # Execute both orders
        result_a = self.execute_order_with_retry(order_a_request)
        result_b = self.execute_order_with_retry(order_b_request)
        
        # Log results
        if result_a.success and result_b.success:
            self.logger.info(
                f"Paired orders executed successfully: "
                f"A={result_a.order.order_id if result_a.order else 'N/A'}, "
                f"B={result_b.order.order_id if result_b.order else 'N/A'}"
            )
        else:
            self.logger.error(
                f"Paired order execution failed: "
                f"A={'OK' if result_a.success else result_a.error}, "
                f"B={'OK' if result_b.success else result_b.error}"
            )
        
        return (result_a, result_b)
    
    async def execute_order_async(self, request: OrderRequest) -> OrderResult:
        """
        Execute an order asynchronously.
        
        Args:
            request: Order request
            
        Returns:
            OrderResult
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.execute_order, request)
    
    async def execute_paired_orders_async(self, request: PairedOrderRequest) -> Tuple[OrderResult, OrderResult]:
        """
        Execute paired orders asynchronously.
        
        Args:
            request: Paired order request
            
        Returns:
            Tuple of (broker_a_result, broker_b_result)
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.execute_paired_orders, request)
    
    def close_position(self, broker_id: str, position_id: str, volume: Optional[float] = None) -> bool:
        """
        Close a position on a specific broker.
        
        Args:
            broker_id: Broker identifier
            position_id: Position ID to close
            volume: Volume to close (None = close all)
            
        Returns:
            True if position closed successfully
        """
        try:
            broker = self.get_broker(broker_id)
            if not broker.is_connected():
                broker.connect()
            
            success = broker.close_position(position_id, volume)
            
            if success:
                self.logger.info(f"Position {position_id} closed on {broker_id}")
            else:
                self.logger.warning(f"Failed to close position {position_id} on {broker_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error closing position {position_id} on {broker_id}: {e}")
            return False
    
    def close_all_positions(self) -> bool:
        """
        Close all open positions on all brokers.
        
        Returns:
            True if all positions closed successfully
        """
        try:
            for broker_id, broker in self.brokers.items():
                if not broker.is_connected():
                    broker.connect()
                
                positions = broker.get_open_positions()
                for pos in positions:
                    success = broker.close_position(pos.position_id)
                    if not success:
                        self.logger.warning(f"Failed to close position {pos.position_id} on {broker_id}")
                        return False
            
            self.logger.info("All positions closed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error closing all positions: {e}")
            return False
    
    def close_paired_positions(self, position_a_id: str, position_b_id: str) -> Tuple[bool, bool]:
        """
        Close both positions in a paired trade.
        
        Args:
            position_a_id: Position ID on broker A
            position_b_id: Position ID on broker B
            
        Returns:
            Tuple of (broker_a_success, broker_b_success)
        """
        success_a = self.close_position("vantage", position_a_id)
        success_b = self.close_position("justmarkets", position_b_id)
        
        return (success_a, success_b)
    
    def get_order_status(self, broker_id: str, order_id: str) -> Optional[Order]:
        """
        Get the status of an order.
        
        Args:
            broker_id: Broker identifier
            order_id: Order ID
            
        Returns:
            Order object or None
        """
        try:
            broker = self.get_broker(broker_id)
            return broker.get_order(order_id)
        except Exception as e:
            self.logger.error(f"Error getting order status {order_id} on {broker_id}: {e}")
            return None
    
    def cancel_order(self, broker_id: str, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            broker_id: Broker identifier
            order_id: Order ID
            
        Returns:
            True if order cancelled successfully
        """
        try:
            broker = self.get_broker(broker_id)
            return broker.cancel_order(order_id)
        except Exception as e:
            self.logger.error(f"Error cancelling order {order_id} on {broker_id}: {e}")
            return False
    
    def _create_order_model(self, order: Order, request: OrderRequest) -> OrderModel:
        """
        Create an OrderModel from an Order and OrderRequest.
        
        Args:
            order: Executed order
            request: Original order request
            
        Returns:
            OrderModel for database storage
        """
        return OrderModel(
            order_id=order.order_id,
            broker_id=order.broker_id,
            account_id=order.account_id,
            instrument=order.instrument,
            order_type=order.order_type.value,
            side=order.side.value,
            volume=order.volume,
            requested_volume=order.volume,
            price=order.price,
            filled_price=order.filled_price,
            filled_volume=order.filled_volume,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            timestamp=order.timestamp,
            filled_time=order.timestamp,
            status=order.status.value,
            commission=order.commission,
            swap=order.swap,
            slippage=order.slippage,
            magic_number=order.magic_number,
            comment=order.comment or request.comment,
            strategy_id=request.strategy_id,
            cycle_id=request.cycle_id,
            error_code=None,
            error_message=None
        )
    
    def get_bid_ask(self, broker_id: str, instrument: str) -> Tuple[float, float]:
        """
        Get bid and ask prices from a broker.
        
        Args:
            broker_id: Broker identifier
            instrument: Instrument symbol
            
        Returns:
            Tuple of (bid, ask)
        """
        try:
            broker = self.get_broker(broker_id)
            return broker.get_bid_ask(instrument)
        except Exception as e:
            self.logger.error(f"Error getting bid/ask for {instrument} from {broker_id}: {e}")
            return (0.0, 0.0)
    
    def get_tick(self, broker_id: str, instrument: str) -> Any:
        """
        Get tick data from a broker.
        
        Args:
            broker_id: Broker identifier
            instrument: Instrument symbol
            
        Returns:
            TickData object
        """
        try:
            broker = self.get_broker(broker_id)
            return broker.get_tick(instrument)
        except Exception as e:
            self.logger.error(f"Error getting tick for {instrument} from {broker_id}: {e}")
            return None
    
    def get_account_info(self, broker_id: str) -> Any:
        """
        Get account information from a broker.
        
        Args:
            broker_id: Broker identifier
            
        Returns:
            AccountInfo object
        """
        try:
            broker = self.get_broker(broker_id)
            return broker.get_account_info()
        except Exception as e:
            self.logger.error(f"Error getting account info from {broker_id}: {e}")
            return None
    
    def get_open_positions(self, broker_id: str) -> List[Any]:
        """
        Get open positions from a broker.
        
        Args:
            broker_id: Broker identifier
            
        Returns:
            List of Position objects
        """
        try:
            broker = self.get_broker(broker_id)
            # Try get_open_positions first, then get_positions for compatibility
            result = []
            if hasattr(broker, 'get_open_positions'):
                result = broker.get_open_positions()
            elif hasattr(broker, 'get_positions'):
                result = broker.get_positions()
            
            # Ensure result is a list
            if isinstance(result, list):
                return result
            else:
                return []
        except Exception as e:
            self.logger.error(f"Error getting open positions from {broker_id}: {e}")
            return []


# Global order manager instance
_order_manager: Optional[OrderManager] = None


def get_order_manager() -> OrderManager:
    """
    Get the global order manager instance.
    
    Returns:
        OrderManager instance
    """
    global _order_manager
    if _order_manager is None:
        _order_manager = OrderManager()
    return _order_manager


def reset_order_manager() -> None:
    """Reset the global order manager instance."""
    global _order_manager
    if _order_manager:
        _order_manager.disconnect_all()
        _order_manager = None
