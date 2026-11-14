"""
Order Manager

Manages order execution across multiple brokers with idempotency and error handling.

Each broker's actual connection lives in its own OS process (see
broker_process.py) - this class only ever talks to those processes through
their BrokerProcessClient handles. It also keeps one small, never-connected
"spec" broker instance per broker purely to answer purely local questions
(contract specs, lot-size validation, margin/pip math) without any IPC.
"""

import asyncio
import time
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
from .broker_process import BrokerProcessClient, BrokerProcessUnavailableError


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


# Broker IDs this system knows how to run. (Keep in one place so adding a
# third broker later doesn't mean hunting down every "vantage"/"justmarkets"
# literal in this file.)
_KNOWN_BROKER_IDS = ("vantage", "justmarkets")


class OrderManager:
    """
    Manages order execution across multiple brokers.

    Provides idempotent order handling, retry logic, and error recovery.
    Each broker's live connection runs in its own OS process; this class
    drives those processes through BrokerProcessClient and never imports
    or talks to a broker's connection directly itself.
    """

    def __init__(self, broker_process_factory: Optional[Callable[[str], BrokerProcessClient]] = None):
        """Initialize the order manager.

        Args:
            broker_process_factory: Optional override for how BrokerProcessClient
                instances are constructed, one per broker_id. Exists for tests;
                production code should leave this as the default.
        """
        # Unconnected, config-only broker instances - used only for local,
        # no-I/O questions (contract specs, lot-size validation, margin math).
        self.brokers: Dict[str, BaseBroker] = {}
        # Live handles to each broker's own OS process.
        self.broker_processes: Dict[str, BrokerProcessClient] = {}
        self._broker_process_factory = broker_process_factory

        self.pending_orders: Dict[str, OrderRequest] = {}
        self.order_results: Dict[str, OrderResult] = {}
        self.logger = get_logger("execution.order_manager")

        # Configuration
        self.max_retries = 3
        self.retry_delay = 1.0  # seconds
        self.order_timeout = 10.0  # seconds, per single order round trip
        self.pair_submission_timeout = 15.0  # seconds, shared deadline for both legs of a paired order

        self._initialized = False

    def initialize(self) -> None:
        """Initialize the order manager with broker connections."""
        if self._initialized:
            return

        config = get_config()

        # Config-only broker instances, for local questions only - never connected.
        try:
            vantage_config = config.get_broker_config("vantage")
            self.brokers["vantage"] = VantageBroker("vantage", vantage_config)
            self.logger.info("Vantage broker spec loaded")
        except Exception as e:
            self.logger.error(f"Failed to load Vantage broker spec: {e}")

        try:
            justmarkets_config = config.get_broker_config("justmarkets")
            self.brokers["justmarkets"] = JustMarketsBroker("justmarkets", justmarkets_config)
            self.logger.info("JustMarkets broker spec loaded")
        except Exception as e:
            self.logger.error(f"Failed to load JustMarkets broker spec: {e}")

        for broker_id in _KNOWN_BROKER_IDS:
            if broker_id not in self.broker_processes:
                self.broker_processes[broker_id] = self._make_process_client(broker_id)

        self._initialized = True

    def _make_process_client(self, broker_id: str) -> BrokerProcessClient:
        if self._broker_process_factory is not None:
            return self._broker_process_factory(broker_id)
        return BrokerProcessClient(
            broker_id,
            connect_timeout=30.0,
            command_timeout=self.order_timeout,
        )

    def get_broker(self, broker_id: str) -> BaseBroker:
        """
        Get the local, unconnected "spec" broker instance for broker_id.

        This is for local-only questions (contract specs, lot-size
        validation) - it is never connected and never used to place orders.

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

    def _get_process(self, broker_id: str) -> BrokerProcessClient:
        if broker_id not in self.broker_processes:
            raise ValueError(f"Broker process not found: {broker_id}")
        return self.broker_processes[broker_id]

    def _ensure_alive(self, client: BrokerProcessClient) -> None:
        """Best-effort self-healing: if a broker's process has died, make one
        bounded attempt to bring it back before using it. Raises
        BrokerProcessUnavailableError if that attempt also fails."""
        if client.is_alive():
            return
        self.logger.warning(f"{client.broker_id} worker process is not alive, attempting restart")
        if not client.restart():
            raise BrokerProcessUnavailableError(
                f"{client.broker_id} worker process is unavailable: {client.last_status_error}"
            )

    def connect_all(self) -> Dict[str, bool]:
        """
        Start (or confirm already-running) each broker's worker process.

        Returns:
            Dictionary of broker_id -> connection success
        """
        results = {}
        for broker_id, client in self.broker_processes.items():
            try:
                if client.is_alive() and client.ready:
                    results[broker_id] = True
                    continue
                success = client.start()
                results[broker_id] = success
                if success:
                    self.logger.info(f"Connected to {broker_id} (account={client.last_known_account_id})")
                else:
                    self.logger.error(f"Failed to connect to {broker_id}: {client.last_status_error}")
            except Exception as e:
                self.logger.error(f"Error connecting to {broker_id}: {e}")
                results[broker_id] = False

        return results

    def disconnect_all(self) -> None:
        """Disconnect from all brokers (stops each worker process)."""
        for broker_id, client in self.broker_processes.items():
            try:
                client.stop()
                self.logger.info(f"Disconnected from {broker_id}")
            except Exception as e:
                self.logger.error(f"Error disconnecting from {broker_id}: {e}")

    def is_connected(self, broker_id: str) -> bool:
        """Check if a broker is connected."""
        client = self._get_process(broker_id)
        return client.is_alive() and client.ready

    @staticmethod
    def _order_payload(request: OrderRequest) -> Dict[str, Any]:
        return {
            "instrument": request.instrument,
            "side": request.side.value,
            "volume": request.volume,
            "order_type": request.order_type.value,
            "price": request.price,
            "stop_loss": request.stop_loss,
            "take_profit": request.take_profit,
            "comment": request.comment,
            "magic_number": request.magic_number,
        }

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
            # Validate request against the local, no-I/O spec broker.
            spec_broker = self.get_broker(request.broker_id)
            request.validate(spec_broker)

            client = self._get_process(request.broker_id)
            self._ensure_alive(client)

            cmd_result = client.call("send_order", self._order_payload(request), timeout=self.order_timeout)
            execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            if not cmd_result.success:
                self.logger.error(f"Order error on {request.broker_id}: {cmd_result.error}")
                return OrderResult(
                    success=False,
                    error=cmd_result.error,
                    execution_time_ms=execution_time_ms,
                )

            order = cmd_result.result
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

        except OrderValidationError as e:
            execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.logger.error(f"Order validation error: {e}")
            return OrderResult(success=False, error=str(e), execution_time_ms=execution_time_ms)
        except (BrokerProcessUnavailableError, TimeoutError) as e:
            execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.logger.error(f"Broker process error: {e}")
            return OrderResult(success=False, error=str(e), error_code=-1, execution_time_ms=execution_time_ms)
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
                time.sleep(retry_delay)

        self.logger.error(f"Order failed after {max_retries} retries: {result.error}")
        return result

    def _failed_result(self, error: Union[str, Exception], error_code: Optional[int] = None) -> OrderResult:
        return OrderResult(success=False, error=str(error), error_code=error_code)

    def _collect_leg(self, client: BrokerProcessClient, command_id: str, order_request: OrderRequest, deadline: float) -> OrderResult:
        """Wait for one leg's result up to a shared deadline. Never assumes an
        order failed just because we lost the response - a timeout or a
        crashed process still means "unknown", so it is reconciled against
        the broker's actual open positions before being reported either way."""
        start = time.monotonic()
        remaining = max(0.0, deadline - start)

        try:
            cmd_result = client.collect(command_id, timeout=remaining)
        except TimeoutError:
            exec_ms = (time.monotonic() - start) * 1000
            self.logger.error(
                f"Timed out waiting for {order_request.broker_id} fill confirmation "
                f"(cycle comment={order_request.comment!r}); reconciling against live positions"
            )
            reconciled = self._reconcile_unknown_order(client, order_request)
            if reconciled is not None:
                return OrderResult(
                    success=True, order=reconciled, execution_time_ms=exec_ms,
                    error="recovered via reconciliation after timeout",
                )
            return OrderResult(
                success=False,
                error="Timed out waiting for fill confirmation; outcome unknown and no matching position found on reconciliation",
                error_code=-2, execution_time_ms=exec_ms,
            )
        except BrokerProcessUnavailableError as e:
            exec_ms = (time.monotonic() - start) * 1000
            self.logger.error(f"{order_request.broker_id} process unavailable while awaiting fill: {e}")
            reconciled = self._reconcile_unknown_order(client, order_request)
            if reconciled is not None:
                return OrderResult(
                    success=True, order=reconciled, execution_time_ms=exec_ms,
                    error="recovered via reconciliation after process crash",
                )
            # Try to bring the process back for subsequent trades even though
            # this leg's own outcome stays "failed" (we actively checked and
            # found nothing, so treating it as not-filled is the safe default).
            client.restart()
            return OrderResult(success=False, error=f"Broker process unavailable: {e}", error_code=-1, execution_time_ms=exec_ms)

        exec_ms = (time.monotonic() - start) * 1000
        if cmd_result.success:
            order = cmd_result.result
            order_model = self._create_order_model(order, order_request) if order else None
            return OrderResult(
                success=True, order=order, order_model=order_model,
                execution_time_ms=exec_ms, slippage=getattr(order, "slippage", 0.0),
            )
        return OrderResult(success=False, error=cmd_result.error, error_code=-3, execution_time_ms=exec_ms)

    def _reconcile_unknown_order(self, client: BrokerProcessClient, order_request: OrderRequest) -> Optional[Order]:
        """After losing track of whether an order filled, actively check the
        broker's current open positions for one tagged with this order's
        comment, rather than assuming either outcome."""
        if not client.is_alive():
            self.logger.error(f"Cannot reconcile on {order_request.broker_id}: process is not running")
            return None
        try:
            cmd_result = client.call("get_open_positions", timeout=10.0)
        except Exception as e:
            self.logger.error(f"Reconciliation query failed for {order_request.broker_id}: {e}")
            return None
        if not cmd_result.success:
            self.logger.error(f"Reconciliation query failed for {order_request.broker_id}: {cmd_result.error}")
            return None

        positions = cmd_result.result or []
        tag = order_request.comment
        matches = [p for p in positions if tag and tag in (p.comment or "")]

        if len(matches) == 1:
            pos = matches[0]
            self.logger.warning(
                f"Reconciliation found the fill on {order_request.broker_id}: position {pos.position_id}"
            )
            return Order(
                order_id=f"reconciled_{pos.position_id}",
                broker_id=order_request.broker_id,
                account_id=pos.account_id,
                instrument=pos.instrument,
                order_type=OrderType.MARKET,
                side=order_request.side,
                volume=pos.volume,
                status=OrderStatus.FILLED,
                filled_volume=pos.volume,
                filled_price=pos.open_price,
                position_id=pos.position_id,
                comment=pos.comment,
            )
        if len(matches) > 1:
            self.logger.error(
                f"Reconciliation ambiguous on {order_request.broker_id}: "
                f"{len(matches)} open positions match comment {tag!r}; treating as unresolved"
            )
        return None

    def _flatten_lone_leg(self, broker_id: str, result: OrderResult, reason: str) -> None:
        """If one leg of a pair filled and the other did not, we are left
        with one-sided market exposure we never intended. Close it
        immediately rather than carry a naked position silently."""
        if not (result.success and result.order and result.order.position_id):
            return
        self.logger.warning(
            f"One-sided exposure detected on {broker_id}, position {result.order.position_id}: {reason}. Flattening now."
        )
        try:
            closed = self.close_position(broker_id, result.order.position_id)
            if not closed:
                self.logger.critical(
                    f"FAILED to flatten one-sided exposure on {broker_id} position "
                    f"{result.order.position_id} ({reason}). Manual intervention required."
                )
        except Exception as e:
            self.logger.critical(
                f"Exception while flattening one-sided exposure on {broker_id} position "
                f"{result.order.position_id} ({reason}): {e}"
            )

    def execute_paired_orders(self, request: PairedOrderRequest) -> Tuple[OrderResult, OrderResult]:
        """
        Execute paired orders on two brokers concurrently.

        Both legs are submitted to their own broker processes back-to-back
        (non-blocking), then awaited against a single shared deadline - the
        two brokers genuinely execute at the same time, in separate OS
        processes, rather than one after the other. A lost or late response
        is never read as "it failed": it is reconciled against the broker's
        actual open positions. If exactly one leg ends up filled, the filled
        leg is flattened immediately rather than left as one-sided exposure.

        Args:
            request: Paired order request

        Returns:
            Tuple of (broker_a_result, broker_b_result)
        """
        self.logger.info(f"Executing paired orders for cycle: {request.cycle_id}")

        broker_a = self.get_broker("vantage")
        broker_b = self.get_broker("justmarkets")

        order_a_request = request.get_broker_a_order(broker_a)
        order_b_request = request.get_broker_b_order(broker_b)

        # Fail fast if either leg is invalid - never submit one side of a
        # pair we already know can't be matched.
        order_a_request.validate(broker_a)
        order_b_request.validate(broker_b)

        client_a = self._get_process("vantage")
        client_b = self._get_process("justmarkets")

        self._ensure_alive(client_a)
        self._ensure_alive(client_b)

        submit_start = time.monotonic()
        deadline = submit_start + self.pair_submission_timeout

        try:
            id_a = client_a.submit("send_order", self._order_payload(order_a_request))
        except BrokerProcessUnavailableError as e:
            self.logger.error(f"Could not submit broker A leg for cycle {request.cycle_id}: {e}")
            return (
                self._failed_result(e, error_code=-1),
                self._failed_result("not submitted: broker A unavailable"),
            )

        try:
            id_b = client_b.submit("send_order", self._order_payload(order_b_request))
        except BrokerProcessUnavailableError as e:
            # A is already in flight on the real broker. We must find out what
            # happened to it rather than abandon it.
            self.logger.error(f"Could not submit broker B leg for cycle {request.cycle_id}: {e}")
            result_a = self._collect_leg(client_a, id_a, order_a_request, deadline)
            self._flatten_lone_leg("vantage", result_a, reason="broker B unavailable before submission")
            return result_a, self._failed_result(e, error_code=-1)

        result_a = self._collect_leg(client_a, id_a, order_a_request, deadline)
        result_b = self._collect_leg(client_b, id_b, order_b_request, deadline)

        if result_a.success and not result_b.success:
            self._flatten_lone_leg("vantage", result_a, reason=f"broker B leg failed: {result_b.error}")
        elif result_b.success and not result_a.success:
            self._flatten_lone_leg("justmarkets", result_b, reason=f"broker A leg failed: {result_a.error}")

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
            client = self._get_process(broker_id)
            self._ensure_alive(client)

            cmd_result = client.call("close_position", {"position_id": position_id, "volume": volume}, timeout=self.order_timeout)

            if not cmd_result.success:
                self.logger.warning(f"Failed to close position {position_id} on {broker_id}: {cmd_result.error}")
                return False

            self.logger.info(f"Position {position_id} closed on {broker_id}")
            return bool(cmd_result.result)

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
            for broker_id in self.broker_processes:
                positions = self.get_open_positions(broker_id)
                for pos in positions:
                    success = self.close_position(broker_id, pos.position_id)
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
            client = self._get_process(broker_id)
            cmd_result = client.call("get_order", {"order_id": order_id}, timeout=self.order_timeout)
            return cmd_result.result if cmd_result.success else None
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
            client = self._get_process(broker_id)
            self._ensure_alive(client)
            cmd_result = client.call("cancel_order", {"order_id": order_id}, timeout=self.order_timeout)
            return bool(cmd_result.success and cmd_result.result)
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
            client = self._get_process(broker_id)
            cmd_result = client.call("get_bid_ask", {"instrument": instrument}, timeout=self.order_timeout)
            return cmd_result.result if cmd_result.success else (0.0, 0.0)
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
            client = self._get_process(broker_id)
            cmd_result = client.call("get_tick", {"instrument": instrument}, timeout=self.order_timeout)
            return cmd_result.result if cmd_result.success else None
        except Exception as e:
            self.logger.error(f"Error getting tick for {instrument} from {broker_id}: {e}")
            return None

    def get_bars(
        self,
        broker_id: str,
        instrument: str,
        timeframe: str,
        count: int,
        start_time: Optional[datetime] = None,
    ) -> List[Any]:
        """
        Get historical bar data from a broker.

        (Previously missing entirely - strategies B, C and E call this, so
        without it they could never fetch bars. Restoring it does not change
        any strategy logic, only the plumbing it already relied on.)

        Args:
            broker_id: Broker identifier
            instrument: Instrument symbol
            timeframe: Timeframe (e.g. "M1", "H1")
            count: Number of bars to retrieve
            start_time: Optional start time

        Returns:
            List of BarData objects
        """
        try:
            client = self._get_process(broker_id)
            cmd_result = client.call(
                "get_bars",
                {"instrument": instrument, "timeframe": timeframe, "count": count, "start_time": start_time},
                timeout=self.order_timeout,
            )
            return cmd_result.result if cmd_result.success else []
        except Exception as e:
            self.logger.error(f"Error getting bars for {instrument} from {broker_id}: {e}")
            return []

    def get_account_info(self, broker_id: str) -> Any:
        """
        Get account information from a broker.

        Args:
            broker_id: Broker identifier

        Returns:
            AccountInfo object
        """
        try:
            client = self._get_process(broker_id)
            cmd_result = client.call("get_account_info", timeout=self.order_timeout)
            return cmd_result.result if cmd_result.success else None
        except Exception as e:
            self.logger.error(f"Error getting account info from {broker_id}: {e}")
            return None

    def get_position(self, broker_id: str, position_id: str) -> Optional[Any]:
        """
        Get a specific position from a broker.

        Args:
            broker_id: Broker identifier
            position_id: Position ID

        Returns:
            Position object or None if not found
        """
        try:
            client = self._get_process(broker_id)
            cmd_result = client.call("get_position", {"position_id": position_id}, timeout=self.order_timeout)
            return cmd_result.result if cmd_result.success else None
        except Exception as e:
            self.logger.error(f"Error getting position {position_id} from {broker_id}: {e}")
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
            client = self._get_process(broker_id)
            cmd_result = client.call("get_open_positions", timeout=self.order_timeout)
            if cmd_result.success and isinstance(cmd_result.result, list):
                return cmd_result.result
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
