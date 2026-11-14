"""
Broker Worker Process

Runs a single broker's MT5 connection in its own OS process.

Why a separate process: the official MetaTrader5 Python package keeps exactly
one global, process-wide IPC connection to whichever terminal was most
recently initialize()-d (import MetaTrader5 as mt5 always returns the same
cached module object within a process). Running Vantage and JustMarkets in
the same process means the second broker's connect() can silently repoint
calls made through the "first" broker's object at the second broker's
terminal - account identity assumptions then become nothing but false.
Giving each broker its own OS process gives each one its own, completely
independent MetaTrader5 module/connection.

Each worker process:
  - Constructs and connects its own broker instance.
  - Validates that the account it actually connected to matches the account
    configured for it (rejects the mismatch rather than trading on it).
  - Re-validates that identity before every order-affecting command, not just
    at startup, since a terminal can in principle be repointed later.
  - Processes commands from a queue and writes results to another queue,
    so it never shares broker objects (or their hidden global state) with
    the parent process or the other broker's worker.
"""

import logging
import multiprocessing
import queue
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


logger = logging.getLogger(__name__)


# Status messages a worker can report back on startup.
STATUS_READY = "READY"
STATUS_FAILED = "FAILED"

# Distinct process exit codes so a parent can tell a connection failure
# apart from an account-identity mismatch without parsing text.
EXIT_CONNECT_FAILED = 43
EXIT_IDENTITY_MISMATCH = 42

# Commands that place or cancel an order, or close/modify a position - these
# re-validate account identity immediately before executing, every time.
_MUTATING_COMMANDS = {"send_order", "close_position", "cancel_order", "modify_order"}


class AccountIdentityError(Exception):
    """Raised when the connected broker account does not match what was configured."""
    pass


class BrokerProcessUnavailableError(Exception):
    """Raised when a broker worker process is not running or has died."""
    pass


@dataclass
class BrokerCommand:
    """A single request sent to a broker worker process."""
    command_id: str
    command_type: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrokerCommandResult:
    """A single response from a broker worker process."""
    command_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None


def _default_broker_factory(broker_id: str):
    """Construct the real broker for broker_id. Imported lazily so this module
    itself has no hard dependency on the MetaTrader5 package (only the
    broker classes do, and only once actually constructed)."""
    from ..core.config import get_config

    config = get_config().get_broker_config(broker_id)

    if broker_id == "vantage":
        from ..brokers.vantage_broker import VantageBroker
        return VantageBroker(broker_id, config)
    elif broker_id == "justmarkets":
        from ..brokers.justmarkets_broker import JustMarketsBroker
        return JustMarketsBroker(broker_id, config)
    else:
        raise ValueError(f"Unknown broker_id: {broker_id}")


def _dispatch(broker: Any, command: BrokerCommand, validate_identity: Callable[[], None]) -> Any:
    """Execute a single command against the broker instance running in this
    process. Re-validates account identity first for anything that mutates
    orders or positions."""
    if command.command_type in _MUTATING_COMMANDS:
        validate_identity()

    p = command.payload

    if command.command_type == "send_order":
        from ..brokers.base_broker import OrderSide, OrderType
        return broker.send_order(
            instrument=p["instrument"],
            side=OrderSide(p["side"]),
            volume=p["volume"],
            order_type=OrderType(p.get("order_type", "MARKET")),
            price=p.get("price"),
            stop_loss=p.get("stop_loss"),
            take_profit=p.get("take_profit"),
            comment=p.get("comment", ""),
            magic_number=p.get("magic_number"),
        )
    if command.command_type == "close_position":
        return broker.close_position(p["position_id"], p.get("volume"))
    if command.command_type == "cancel_order":
        return broker.cancel_order(p["order_id"])
    if command.command_type == "modify_order":
        return broker.modify_order(p["order_id"], p.get("stop_loss"), p.get("take_profit"))
    if command.command_type == "get_position":
        return broker.get_position(p["position_id"])
    if command.command_type == "get_open_positions":
        return broker.get_open_positions()
    if command.command_type == "get_open_orders":
        return broker.get_open_orders()
    if command.command_type == "get_account_info":
        return broker.get_account_info()
    if command.command_type == "get_bid_ask":
        return broker.get_bid_ask(p["instrument"])
    if command.command_type == "get_tick":
        return broker.get_tick(p["instrument"])
    if command.command_type == "get_bars":
        return broker.get_bars(p["instrument"], p["timeframe"], p["count"], p.get("start_time"))
    if command.command_type == "get_order":
        return broker.get_order(p["order_id"])
    if command.command_type == "is_connected":
        return broker.is_connected()
    if command.command_type == "ping":
        return {"alive": True, "account_id": broker.get_account_info().account_id}

    raise ValueError(f"Unknown command type: {command.command_type}")


def _broker_worker_main(
    broker_id: str,
    command_queue: "multiprocessing.Queue",
    result_queue: "multiprocessing.Queue",
    status_queue: "multiprocessing.Queue",
    broker_factory: Optional[Callable[[str], Any]] = None,
    connect_retries: int = 3,
    connect_retry_delay: float = 2.0,
    poll_timeout: float = 1.0,
) -> None:
    """Entry point run inside the broker worker process. Never imports or
    touches the other broker's connection - this process only ever knows
    about its own `broker_id`."""
    worker_logger = logging.getLogger(f"broker_worker.{broker_id}")
    factory = broker_factory or _default_broker_factory

    try:
        broker = factory(broker_id)
    except Exception as e:  # pragma: no cover - construction failures are rare
        status_queue.put({"status": STATUS_FAILED, "broker_id": broker_id,
                           "error": f"Failed to construct broker: {e}"})
        sys.exit(EXIT_CONNECT_FAILED)

    connected = False
    last_error: Optional[str] = None
    for attempt in range(connect_retries):
        try:
            broker.connect()
            connected = True
            break
        except Exception as e:
            last_error = str(e)
            worker_logger.warning(f"Connect attempt {attempt + 1}/{connect_retries} failed: {e}")
            if attempt < connect_retries - 1:
                time.sleep(connect_retry_delay)

    if not connected:
        status_queue.put({
            "status": STATUS_FAILED, "broker_id": broker_id,
            "error": f"Could not connect after {connect_retries} attempts: {last_error}",
        })
        sys.exit(EXIT_CONNECT_FAILED)

    expected_login = str(getattr(broker, "login", None) or "")

    try:
        account_info = broker.get_account_info()
    except Exception as e:
        status_queue.put({"status": STATUS_FAILED, "broker_id": broker_id,
                           "error": f"Could not fetch account info after connect: {e}"})
        sys.exit(EXIT_CONNECT_FAILED)

    if not expected_login or account_info.account_id != expected_login:
        status_queue.put({
            "status": STATUS_FAILED, "broker_id": broker_id,
            "error": (
                f"Account identity mismatch: connected to account "
                f"'{account_info.account_id}', expected '{expected_login}'. Refusing to trade."
            ),
        })
        sys.exit(EXIT_IDENTITY_MISMATCH)

    def _validate_identity() -> None:
        info = broker.get_account_info()
        if info.account_id != expected_login:
            raise AccountIdentityError(
                f"Account identity changed mid-session: now '{info.account_id}', "
                f"expected '{expected_login}'. Order rejected."
            )

    status_queue.put({"status": STATUS_READY, "broker_id": broker_id, "account_id": account_info.account_id})
    worker_logger.info(f"Broker worker ready: {broker_id}, account={account_info.account_id}")

    running = True
    while running:
        try:
            command: BrokerCommand = command_queue.get(timeout=poll_timeout)
        except queue.Empty:
            continue
        except (EOFError, OSError):
            break

        if command is None:
            continue

        if command.command_type == "shutdown":
            running = False
            break

        try:
            value = _dispatch(broker, command, _validate_identity)
            result_queue.put(BrokerCommandResult(command_id=command.command_id, success=True, result=value))
        except AccountIdentityError as e:
            worker_logger.critical(str(e))
            result_queue.put(BrokerCommandResult(
                command_id=command.command_id, success=False, error=str(e), error_type="AccountIdentityError"
            ))
        except Exception as e:
            worker_logger.error(f"Command {command.command_type} failed: {e}")
            result_queue.put(BrokerCommandResult(
                command_id=command.command_id, success=False, error=str(e), error_type=type(e).__name__
            ))

    try:
        broker.disconnect()
    except Exception as e:  # pragma: no cover
        worker_logger.error(f"Error disconnecting during shutdown: {e}")
    worker_logger.info(f"Broker worker stopped: {broker_id}")


class BrokerProcessClient:
    """
    Parent-process handle to one broker's worker process.

    Owns the process plus its command/result/status queues, a background
    reader thread (so multiple threads in the parent can safely wait on
    different in-flight commands to the same broker), and process
    lifecycle (start/stop/restart, liveness check).
    """

    def __init__(
        self,
        broker_id: str,
        broker_factory: Optional[Callable[[str], Any]] = None,
        connect_timeout: float = 30.0,
        command_timeout: float = 10.0,
        mp_context: Optional[Any] = None,
    ):
        self.broker_id = broker_id
        self.broker_factory = broker_factory
        self.connect_timeout = connect_timeout
        self.command_timeout = command_timeout
        # Always use "spawn" (not the platform default, which is "fork" on
        # Linux): spawn is mandatory on Windows anyway, and using it
        # everywhere means dev/test behavior matches production and we never
        # fork a multi-threaded parent process (which can deadlock).
        self._ctx = mp_context or multiprocessing.get_context("spawn")
        self.logger = logging.getLogger(f"execution.broker_process.{broker_id}")

        self.process: Optional[Any] = None
        self.command_queue: Optional[Any] = None
        self.result_queue: Optional[Any] = None
        self.status_queue: Optional[Any] = None

        self.ready = False
        self.last_known_account_id: Optional[str] = None
        self.last_status_error: Optional[str] = None

        self._pending: Dict[str, BrokerCommandResult] = {}
        self._pending_lock = threading.Lock()
        self._pending_cv = threading.Condition(self._pending_lock)
        self._reader_thread: Optional[threading.Thread] = None
        self._reader_stop = threading.Event()

    # -- lifecycle -----------------------------------------------------

    def start(self) -> bool:
        """Start the worker process and block until it reports ready or failed."""
        self.command_queue = self._ctx.Queue()
        self.result_queue = self._ctx.Queue()
        self.status_queue = self._ctx.Queue()

        self.process = self._ctx.Process(
            target=_broker_worker_main,
            args=(self.broker_id, self.command_queue, self.result_queue, self.status_queue, self.broker_factory),
            name=f"broker-worker-{self.broker_id}",
            daemon=True,
        )
        self.process.start()

        try:
            status = self.status_queue.get(timeout=self.connect_timeout)
        except queue.Empty:
            self.ready = False
            self.last_status_error = f"Timed out after {self.connect_timeout}s waiting for {self.broker_id} worker to start"
            self.logger.error(self.last_status_error)
            return False

        if status.get("status") == STATUS_READY:
            self.ready = True
            self.last_known_account_id = status.get("account_id")
            self.last_status_error = None
            self._reader_stop.clear()
            self._reader_thread = threading.Thread(
                target=self._reader_loop, name=f"broker-reader-{self.broker_id}", daemon=True
            )
            self._reader_thread.start()
            self.logger.info(f"{self.broker_id} worker ready (account={self.last_known_account_id})")
            return True

        self.ready = False
        self.last_status_error = status.get("error", "unknown startup error")
        self.logger.error(f"{self.broker_id} worker failed to start: {self.last_status_error}")
        return False

    def is_alive(self) -> bool:
        return bool(self.process is not None and self.process.is_alive())

    def restart(self) -> bool:
        """Stop (if running) and start a fresh worker process."""
        self.logger.warning(f"Restarting {self.broker_id} broker worker process")
        self.stop(timeout=2.0)
        return self.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._reader_stop.set()

        if self.process is not None:
            if self.process.is_alive():
                try:
                    self.command_queue.put(BrokerCommand(command_id="shutdown", command_type="shutdown"))
                except Exception:
                    pass
                self.process.join(timeout=timeout)
                if self.process.is_alive():
                    self.logger.warning(f"{self.broker_id} worker did not exit cleanly, terminating")
                    self.process.terminate()
                    self.process.join(timeout=2.0)
            self.process = None

        if self._reader_thread is not None:
            self._reader_thread.join(timeout=2.0)
            self._reader_thread = None

        self.ready = False

    # -- command / result plumbing --------------------------------------

    def _reader_loop(self) -> None:
        while not self._reader_stop.is_set():
            try:
                result = self.result_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            except (EOFError, OSError):
                break
            with self._pending_cv:
                self._pending[result.command_id] = result
                self._pending_cv.notify_all()

    def submit(self, command_type: str, payload: Optional[Dict[str, Any]] = None) -> str:
        """Enqueue a command without waiting for the result. Non-blocking -
        this is what lets two different brokers' commands run concurrently."""
        if not self.is_alive():
            raise BrokerProcessUnavailableError(f"{self.broker_id} worker process is not running")

        command_id = f"{self.broker_id}_{uuid.uuid4().hex[:10]}"
        self.command_queue.put(BrokerCommand(command_id=command_id, command_type=command_type, payload=payload or {}))
        return command_id

    def collect(self, command_id: str, timeout: Optional[float] = None) -> BrokerCommandResult:
        """Block until the result for command_id arrives, the process dies, or timeout elapses."""
        timeout = self.command_timeout if timeout is None else timeout
        deadline = time.monotonic() + timeout

        with self._pending_cv:
            while command_id not in self._pending:
                if not self.is_alive():
                    raise BrokerProcessUnavailableError(
                        f"{self.broker_id} worker process died while waiting for command {command_id}"
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"Timed out after {timeout}s waiting for result of command {command_id} on {self.broker_id}"
                    )
                self._pending_cv.wait(timeout=min(remaining, 0.5))
            return self._pending.pop(command_id)

    def call(self, command_type: str, payload: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> BrokerCommandResult:
        """Submit and wait for a single command. Use submit()/collect() directly
        instead when you need two commands (e.g. to two different brokers) to
        run concurrently."""
        command_id = self.submit(command_type, payload)
        return self.collect(command_id, timeout=timeout)
