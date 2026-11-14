"""
Dashboard Startup Tests

Regression tests ensuring the FastAPI app actually starts the background
execution worker on startup and stops it on shutdown.

Without a startup hook, nothing in the app ever calls
ExecutionWorker.start(). ExecutionWorker.submit_task() refuses to run
unless self.running is True, so every dashboard call that goes through
execution_worker (trade/open, trade/close, emergency/stop,
system/reconcile) failed immediately with
ExecutionError("Execution worker is not running") - independent of, and
upstream of, the separate missing-uuid-import bug in execution_worker.py.
"""

import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import create_app, reset_app
from src.execution.execution_worker import (
    ExecutionError,
    ExecutionTask,
    get_execution_worker,
    stop_execution_worker,
)


@pytest.fixture
def client():
    """A TestClient whose context manager drives the app's startup/shutdown events."""
    reset_app()
    stop_execution_worker()  # ensure a clean worker singleton before each test
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    stop_execution_worker()
    reset_app()


class TestExecutionWorkerStartup:
    """Regression tests for the missing startup/shutdown lifecycle hook."""

    def test_execution_worker_is_running_after_app_startup(self, client):
        worker = get_execution_worker()
        assert worker.running is True

    def test_submit_task_does_not_raise_not_running_after_startup(self, client):
        worker = get_execution_worker()

        # Before the fix, this raised ExecutionError("Execution worker is
        # not running") for every caller (trade/open, trade/close,
        # emergency/stop, system/reconcile) because self.running was
        # always False.
        task = ExecutionTask(task_id="task_regression_test", task_type="reconcile")
        worker.submit_task(task)

    def test_execution_worker_stops_after_app_shutdown(self):
        reset_app()
        stop_execution_worker()
        app = create_app()

        with TestClient(app) as test_client:
            worker = get_execution_worker()
            assert worker.running is True

        # Exiting the TestClient context fires the shutdown event.
        assert worker.running is False

        reset_app()
