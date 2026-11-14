"""
End-to-end integration tests for concurrent paired-order execution
(Priority 2), run against the real BrokerProcessClient / real worker
processes (not the fast in-process fake used in test_execution.py).

These prove, with real timing across real OS processes, that:
  - both legs of a pair genuinely execute concurrently;
  - a slow/lost response is reconciled against live positions rather than
    assumed to have failed;
  - a lone filled leg is flattened immediately when its partner fails,
    rejects, times out, or the whole process disappears.
"""

import time

import pytest

from src.execution.order_manager import OrderManager, PairedOrderRequest
from src.execution.broker_process import BrokerProcessClient
from src.tests.test_broker_process import FakeBrokerFactory


def make_order_manager(vantage_factory, justmarkets_factory, pair_submission_timeout=3.0):
    om = OrderManager()
    om.brokers = {
        "vantage": _SpecOnlyBroker("vantage"),
        "justmarkets": _SpecOnlyBroker("justmarkets"),
    }
    om.broker_processes = {
        "vantage": BrokerProcessClient("vantage", broker_factory=vantage_factory,
                                        connect_timeout=15.0, command_timeout=5.0),
        "justmarkets": BrokerProcessClient("justmarkets", broker_factory=justmarkets_factory,
                                            connect_timeout=15.0, command_timeout=5.0),
    }
    om.pair_submission_timeout = pair_submission_timeout
    for client in om.broker_processes.values():
        assert client.start() is True
    return om


class _SpecOnlyBroker:
    """Stands in for the unconnected "spec" broker OrderManager keeps for
    local validate()/get_contract_spec() calls - never touched over IPC."""

    def __init__(self, broker_id):
        self.broker_id = broker_id

    def validate_lot_size(self, volume):
        return True

    def get_contract_spec(self, instrument):
        from src.brokers.base_broker import ContractSpec
        return ContractSpec(
            instrument=instrument, contract_size=100, tick_value=0.01, tick_size=0.01,
            margin_requirement_percent=0.5, swap_long=-5.0, swap_short=2.0,
            trading_hours="00:00-23:59",
        )


@pytest.fixture
def teardown_registry():
    managers = []
    yield managers
    for om in managers:
        om.disconnect_all()


def _paired_request(cycle_id="cycle-1"):
    return PairedOrderRequest(cycle_id=cycle_id, instrument="XAUUSD", lot_size=0.01, direction="BUY_SELL")


class TestConcurrentExecution:
    def test_both_legs_run_concurrently_across_real_processes(self, teardown_registry):
        om = make_order_manager(
            FakeBrokerFactory(login="100", connected_account_id="100", slow_on={"send_order": 1.0}),
            FakeBrokerFactory(login="200", connected_account_id="200", slow_on={"send_order": 1.0}),
        )
        teardown_registry.append(om)

        start = time.monotonic()
        result_a, result_b = om.execute_paired_orders(_paired_request("cycle-concurrent"))
        elapsed = time.monotonic() - start

        assert result_a.success is True
        assert result_b.success is True
        assert elapsed < 1.8, f"legs were not concurrent (took {elapsed:.2f}s for two 1s legs)"


class TestPartialFailureFlattening:
    def test_one_leg_rejected_flattens_the_other(self, teardown_registry):
        om = make_order_manager(
            FakeBrokerFactory(login="100", connected_account_id="100"),
            FakeBrokerFactory(login="200", connected_account_id="200", reject_on="send_order"),
        )
        teardown_registry.append(om)

        result_a, result_b = om.execute_paired_orders(_paired_request("cycle-reject"))

        assert result_a.success is True
        assert result_b.success is False

        # The filled leg (A) must have been flattened: its position should
        # no longer be open on broker A.
        remaining = om.get_open_positions("vantage")
        assert remaining == []

    def test_one_leg_crash_flattens_the_other(self, teardown_registry):
        om = make_order_manager(
            FakeBrokerFactory(login="100", connected_account_id="100"),
            FakeBrokerFactory(login="200", connected_account_id="200", crash_on="send_order"),
        )
        teardown_registry.append(om)

        result_a, result_b = om.execute_paired_orders(_paired_request("cycle-crash"))

        assert result_a.success is True
        assert result_b.success is False

        remaining = om.get_open_positions("vantage")
        assert remaining == []


class TestTimeoutReconciliation:
    def test_slow_fill_within_broker_but_past_pair_deadline_is_reconciled_not_assumed_failed(self, teardown_registry):
        """
        Broker B takes longer to answer than the shared pair deadline, but
        the order genuinely filled on the broker's side. OrderManager must
        not report this as a plain failure - it should reconcile against
        live open positions and find the fill.
        """
        om = make_order_manager(
            FakeBrokerFactory(login="100", connected_account_id="100"),
            FakeBrokerFactory(login="200", connected_account_id="200", slow_on={"send_order": 4.0}),
            pair_submission_timeout=1.0,
        )
        teardown_registry.append(om)

        result_a, result_b = om.execute_paired_orders(_paired_request("cycle-timeout"))

        assert result_a.success is True
        # Our wait on B hit the 1s pair deadline while B's send_order (4s)
        # was still running inside its worker process. execute_paired_orders
        # must not report this as a failure - it reconciles against B's
        # actual open positions (the reconciliation query queues behind the
        # in-flight send_order and is answered once it lands) and finds the
        # real fill, rather than guessing either way.
        assert result_b.success is True
        assert result_b.error is not None and "reconcil" in result_b.error.lower()

        positions_b = om.get_open_positions("justmarkets")
        assert len(positions_b) == 1, "the fill should exist on broker B"
