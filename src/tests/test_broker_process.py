"""
Tests for broker worker process isolation (Priority 1).

Covers: process startup/readiness, account-identity validation at connect
time and before every mutating command, true concurrency between two
broker processes, and crash detection + restart recovery.
"""

import os
import time

import pytest

from datetime import datetime

from src.brokers.base_broker import AccountInfo, Order, OrderStatus, OrderType, Position, PositionSide
from src.execution.broker_process import (
    BrokerCommand,
    BrokerProcessClient,
    BrokerProcessUnavailableError,
    AccountIdentityError,
    EXIT_CONNECT_FAILED,
    EXIT_IDENTITY_MISMATCH,
    _dispatch,
)


class FakeBroker:
    """Minimal stand-in for a BaseBroker subclass, used only inside the
    worker process so these tests never need a real MT5 terminal. Tracks
    real Position objects (tagged by comment) so reconciliation-by-comment
    logic in OrderManager can be exercised end-to-end."""

    def __init__(self, broker_id, login, connected_account_id, connect_should_fail=False,
                 crash_on=None, slow_on=None, reject_on=None, close_always_succeeds=False):
        self.broker_id = broker_id
        self.login = login
        self._connected_account_id = connected_account_id
        self.connect_should_fail = connect_should_fail
        self.crash_on = crash_on
        self.slow_on = slow_on or {}
        self.reject_on = reject_on
        # A real broker tracks open positions by ticket on its own server,
        # independent of which of our OS processes is asking - a fresh
        # process (e.g. after a restart) can still close a position it
        # never itself opened. This flag models that, instead of requiring
        # the position to be present in this instance's own _positions dict.
        self.close_always_succeeds = close_always_succeeds
        self._positions = {}
        self._order_counter = 0
        self.connected = False

    def connect(self):
        if self.connect_should_fail:
            raise ConnectionError("simulated connect failure")
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False

    def get_account_info(self):
        return AccountInfo(
            broker_id=self.broker_id, account_id=self._connected_account_id,
            balance=1000.0, equity=1000.0, free_margin=900.0, margin=100.0,
            margin_level=1000.0, currency="USD", leverage=100,
        )

    def send_order(self, instrument, side, volume, order_type=OrderType.MARKET, price=None,
                    stop_loss=None, take_profit=None, comment="", magic_number=None):
        if self.crash_on == "send_order":
            os._exit(1)  # hard-kill this process, simulating a real crash
        if self.reject_on == "send_order":
            raise RuntimeError("simulated broker-side order rejection")
        delay = self.slow_on.get("send_order")
        if delay:
            time.sleep(delay)
        self._order_counter += 1
        order_id = f"order_{self._order_counter}"
        position_id = f"pos_{self._order_counter}"
        position = Position(
            position_id=position_id, broker_id=self.broker_id, account_id=self._connected_account_id,
            instrument=instrument, side=PositionSide(side.value if hasattr(side, "value") else side),
            volume=volume, open_price=1.2345, open_time=datetime.utcnow(), current_price=1.2345,
            comment=comment,
        )
        self._positions[position_id] = position
        return Order(
            order_id=order_id, broker_id=self.broker_id, account_id=self._connected_account_id,
            instrument=instrument, order_type=order_type, side=side, volume=volume,
            status=OrderStatus.FILLED, filled_volume=volume, filled_price=1.2345,
            position_id=position_id, comment=comment, magic_number=magic_number,
        )

    def close_position(self, position_id, volume=None):
        found = self._positions.pop(position_id, None) is not None
        return found or self.close_always_succeeds

    def get_position(self, position_id):
        return self._positions.get(position_id)

    def get_open_positions(self):
        return list(self._positions.values())

    def is_connected(self):
        return self.connected


class FakeBrokerFactory:
    """Picklable factory (plain attributes only) so it survives the
    multiprocessing spawn/fork boundary."""

    def __init__(self, login="100", connected_account_id="100", connect_should_fail=False,
                 crash_on=None, slow_on=None, reject_on=None, close_always_succeeds=False):
        self.login = login
        self.connected_account_id = connected_account_id
        self.connect_should_fail = connect_should_fail
        self.crash_on = crash_on
        self.slow_on = slow_on
        self.reject_on = reject_on
        self.close_always_succeeds = close_always_succeeds

    def __call__(self, broker_id):
        return FakeBroker(
            broker_id, self.login, self.connected_account_id,
            connect_should_fail=self.connect_should_fail,
            crash_on=self.crash_on, slow_on=self.slow_on, reject_on=self.reject_on,
            close_always_succeeds=self.close_always_succeeds,
        )


@pytest.fixture
def client_factory():
    created = []

    def _make(factory, broker_id="vantage", **kwargs):
        kwargs.setdefault("connect_timeout", 10.0)
        kwargs.setdefault("command_timeout", 5.0)
        client = BrokerProcessClient(broker_id, broker_factory=factory, **kwargs)
        created.append(client)
        return client

    yield _make

    for c in created:
        c.stop(timeout=3.0)


class TestBrokerProcessStartup:
    def test_starts_and_reports_ready_when_identity_matches(self, client_factory):
        client = client_factory(FakeBrokerFactory(login="100", connected_account_id="100"))
        assert client.start() is True
        assert client.ready is True
        assert client.last_known_account_id == "100"
        assert client.is_alive() is True

    def test_fails_to_start_on_identity_mismatch(self, client_factory):
        client = client_factory(FakeBrokerFactory(login="100", connected_account_id="999"))
        assert client.start() is False
        assert client.ready is False
        assert "mismatch" in client.last_status_error.lower()
        client.process.join(timeout=5)
        assert client.process.exitcode == EXIT_IDENTITY_MISMATCH

    def test_fails_to_start_on_connect_failure(self, client_factory):
        client = client_factory(FakeBrokerFactory(connect_should_fail=True), connect_timeout=20.0)
        assert client.start() is False
        assert "could not connect" in client.last_status_error.lower()
        client.process.join(timeout=5)
        assert client.process.exitcode == EXIT_CONNECT_FAILED


class TestBrokerProcessCommands:
    def test_send_order_round_trip(self, client_factory):
        client = client_factory(FakeBrokerFactory())
        assert client.start() is True
        result = client.call("send_order", {"instrument": "EURUSD", "side": "BUY", "volume": 0.01})
        assert result.success is True
        assert result.result.status == OrderStatus.FILLED
        assert result.result.position_id == "pos_1"

    def test_close_position(self, client_factory):
        client = client_factory(FakeBrokerFactory())
        client.start()
        opened = client.call("send_order", {"instrument": "EURUSD", "side": "BUY", "volume": 0.01})
        closed = client.call("close_position", {"position_id": opened.result.position_id})
        assert closed.success is True
        assert closed.result is True

    def test_unknown_command_reports_failure_not_crash(self, client_factory):
        client = client_factory(FakeBrokerFactory())
        client.start()
        result = client.call("not_a_real_command", {})
        assert result.success is False
        assert client.is_alive() is True


class TestConcurrentBrokerProcesses:
    def test_two_brokers_execute_concurrently_not_sequentially(self):
        """Two slow sends on two different broker processes should overlap:
        total wall time should track the slower single call, not their sum."""
        client_a = BrokerProcessClient(
            "vantage", broker_factory=FakeBrokerFactory(slow_on={"send_order": 1.0}),
            connect_timeout=10.0, command_timeout=5.0,
        )
        client_b = BrokerProcessClient(
            "justmarkets", broker_factory=FakeBrokerFactory(slow_on={"send_order": 1.0}),
            connect_timeout=10.0, command_timeout=5.0,
        )
        try:
            assert client_a.start() is True
            assert client_b.start() is True

            start = time.monotonic()
            id_a = client_a.submit("send_order", {"instrument": "EURUSD", "side": "BUY", "volume": 0.01})
            id_b = client_b.submit("send_order", {"instrument": "EURUSD", "side": "SELL", "volume": 0.01})
            result_a = client_a.collect(id_a, timeout=5.0)
            result_b = client_b.collect(id_b, timeout=5.0)
            elapsed = time.monotonic() - start

            assert result_a.success is True
            assert result_b.success is True
            # Sequential execution would take ~2.0s; concurrent stays close to 1.0s.
            assert elapsed < 1.8, f"legs did not run concurrently (took {elapsed:.2f}s)"
        finally:
            client_a.stop()
            client_b.stop()


class TestBrokerProcessCrashAndRestart:
    def test_process_crash_is_detected(self, client_factory):
        client = client_factory(FakeBrokerFactory(crash_on="send_order"))
        client.start()
        with pytest.raises(BrokerProcessUnavailableError):
            client.call("send_order", {"instrument": "EURUSD", "side": "BUY", "volume": 0.01}, timeout=5.0)
        assert client.is_alive() is False

    def test_restart_after_crash_recovers(self, client_factory):
        client = client_factory(FakeBrokerFactory(crash_on="send_order"))
        client.start()
        with pytest.raises(BrokerProcessUnavailableError):
            client.call("send_order", {"instrument": "EURUSD", "side": "BUY", "volume": 0.01}, timeout=5.0)

        assert client.restart() is True
        assert client.is_alive() is True
        result = client.call("get_account_info")
        assert result.success is True


class TestAccountIdentityEnforcementAtDispatch:
    """Exercises the identity re-check directly at the dispatch layer, since
    forcing a real broker's identity to change mid-session isn't something
    a deterministic subprocess test should rely on."""

    def test_mutating_command_checked_and_rejected_on_mismatch(self):
        def fail_validate():
            raise AccountIdentityError("identity changed")

        command = BrokerCommand(command_id="c1", command_type="close_position",
                                 payload={"position_id": "pos_1"})
        with pytest.raises(AccountIdentityError):
            _dispatch(broker=object(), command=command, validate_identity=fail_validate)

    def test_read_only_command_not_subject_to_identity_check(self):
        calls = {"count": 0}

        def fail_validate():
            calls["count"] += 1
            raise AccountIdentityError("should not be called")

        broker = FakeBroker("vantage", "100", "100")
        command = BrokerCommand(command_id="c2", command_type="get_account_info", payload={})
        result = _dispatch(broker=broker, command=command, validate_identity=fail_validate)

        assert result.account_id == "100"
        assert calls["count"] == 0

    def test_mutating_command_passes_through_when_identity_matches(self):
        calls = {"count": 0}

        def ok_validate():
            calls["count"] += 1

        broker = FakeBroker("vantage", "100", "100")
        command = BrokerCommand(command_id="c3", command_type="send_order",
                                 payload={"instrument": "EURUSD", "side": "BUY", "volume": 0.01})
        result = _dispatch(broker=broker, command=command, validate_identity=ok_validate)

        assert calls["count"] == 1
        assert result.status == OrderStatus.FILLED
