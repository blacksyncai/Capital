"""
Execution Worker

Background worker for executing trades and managing order flow.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any, Callable, Union, AsyncGenerator
import logging
import threading

from ..brokers.base_broker import BaseBroker, TickData, Position
from ..core.config import get_config
from ..core.logging import get_logger
from ..models.trade_cycles import TradeCycle, CycleStatus
from .order_manager import OrderManager, PairedOrderRequest, OrderResult, get_order_manager
from .trade_state import TradeStateManager, TradeState, ReconciliationResult, get_trade_state_manager


# Configure logging
logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    """Execution error."""
    pass


@dataclass
class ExecutionTask:
    """Represents an execution task."""
    task_id: str
    task_type: str  # open_cycle, close_cycle, reconcile, etc.
    cycle_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    priority: int = 0
    created_time: datetime = field(default_factory=datetime.utcnow)
    status: str = "pending"  # pending, in_progress, completed, failed
    result: Optional[Any] = None
    error: Optional[str] = None


class ExecutionWorker:
    """
    Background worker for executing trades.
    
    Runs in a separate thread or async task to handle:
    - Opening and closing trade cycles
    - Monitoring positions
    - Reconciling state
    - Handling errors
    """
    
    def __init__(
        self,
        order_manager: Optional[OrderManager] = None,
        trade_state_manager: Optional[TradeStateManager] = None,
    ):
        """
        Initialize the execution worker.

        Args:
            order_manager: Optional override, for tests. Defaults to the
                shared process-wide singleton so the risk engine, this
                worker, and the dashboard routes all see the same broker
                connections and the same trade state (see risk_engine.py
                for why that matters - a private copy here was previously
                how emergency stop's two halves ended up disagreeing).
            trade_state_manager: Optional override, for tests.
        """
        self.order_manager = order_manager if order_manager is not None else get_order_manager()
        self.trade_state_manager = (
            trade_state_manager if trade_state_manager is not None else get_trade_state_manager()
        )
        self.logger = get_logger("execution.worker")
        
        # Configuration
        self.poll_interval = 1.0  # seconds
        self.max_concurrent_tasks = 10
        self.reconciliation_interval = 60  # seconds
        
        # State
        self.running = False
        self.paused = False
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.active_tasks: Dict[str, ExecutionTask] = {}
        self.last_reconciliation_time: datetime = datetime.utcnow()
        
        # Thread and loop
        self.thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
    
    def start(self) -> None:
        """Start the execution worker."""
        if self.running:
            return
        
        self.running = True
        self.paused = False
        
        # Start in a new thread
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        
        self.logger.info("Execution worker started")
    
    def stop(self) -> None:
        """Stop the execution worker."""
        self.running = False
        
        # Wait for thread to finish
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        
        self.logger.info("Execution worker stopped")
    
    def pause(self) -> None:
        """Pause the execution worker."""
        self.paused = True
        self.logger.info("Execution worker paused")
    
    def resume(self) -> None:
        """Resume the execution worker."""
        self.paused = False
        self.logger.info("Execution worker resumed")
    
    def _run(self) -> None:
        """Main execution loop."""
        # Create new event loop
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            # Initialize
            self.order_manager.initialize()
            self.trade_state_manager.initialize()
            
            # Run async main
            self.loop.run_until_complete(self._async_main())
        except Exception as e:
            self.logger.error(f"Execution worker error: {e}")
        finally:
            # Cleanup
            self.order_manager.disconnect_all()
            if self.loop:
                self.loop.close()
                self.loop = None
    
    async def _async_main(self) -> None:
        """Async main loop."""
        self.logger.info("Execution worker async main started")
        
        while self.running:
            try:
                # Process tasks
                if not self.paused:
                    await self._process_tasks()
                
                # Check for new cycles to open
                await self._check_pending_cycles()
                
                # Reconcile positions
                await self._reconcile_positions()
                
                # Sleep
                await asyncio.sleep(self.poll_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in execution loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying
        
        self.logger.info("Execution worker async main stopped")
    
    async def _process_tasks(self) -> None:
        """Process tasks from the queue."""
        while self.running and not self.task_queue.empty():
            try:
                task = await self.task_queue.get()
                await self._execute_task(task)
            except Exception as e:
                self.logger.error(f"Error processing task: {e}")
    
    async def _execute_task(self, task: ExecutionTask) -> None:
        """Execute a single task."""
        self.active_tasks[task.task_id] = task
        task.status = "in_progress"
        
        try:
            if task.task_type == "open_cycle":
                if task.cycle_id:
                    state = self.trade_state_manager.open_cycle(task.cycle_id)
                    task.result = state
            elif task.task_type == "close_cycle":
                if task.cycle_id:
                    state = self.trade_state_manager.close_cycle(
                        task.cycle_id,
                        task.data.get("reason", "manual") if task.data else "manual",
                        task.data.get("comment", "") if task.data else ""
                    )
                    task.result = state
            elif task.task_type == "emergency_close":
                results = self.trade_state_manager.emergency_close_all(
                    task.data.get("reason", "emergency_stop") if task.data else "emergency_stop"
                )
                task.result = results
            elif task.task_type == "reconcile":
                result = self.trade_state_manager.reconcile_positions()
                task.result = result
            else:
                raise ExecutionError(f"Unknown task type: {task.task_type}")
            
            task.status = "completed"
            self.logger.info(f"Task completed: {task.task_id}, type={task.task_type}")
            
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            self.logger.error(f"Task failed: {task.task_id}, error={e}")
        finally:
            self.active_tasks.pop(task.task_id, None)
    
    async def _check_pending_cycles(self) -> None:
        """Check for pending cycles that need to be opened."""
        pending = self.trade_state_manager.pending_cycles
        if not pending:
            return
        
        for cycle_id, request in list(pending.items()):
            try:
                self.trade_state_manager.open_cycle(cycle_id)
            except Exception as e:
                self.logger.error(f"Failed to open pending cycle {cycle_id}: {e}")
    
    async def _reconcile_positions(self) -> None:
        """Reconcile positions periodically."""
        now = datetime.utcnow()
        if (now - self.last_reconciliation_time).total_seconds() < self.reconciliation_interval:
            return
        
        try:
            result = self.trade_state_manager.reconcile_positions()
            if not result.success:
                self.logger.warning(f"Reconciliation found issues: {result.mismatches}")
                # Attempt to fix
                self.trade_state_manager.fix_mismatches(result)
            
            self.last_reconciliation_time = now
        except Exception as e:
            self.logger.error(f"Error during reconciliation: {e}")
    
    def submit_task(self, task: ExecutionTask) -> None:
        """
        Submit a task to the execution worker.
        
        Args:
            task: Execution task
        """
        if not self.running:
            raise ExecutionError("Execution worker is not running")
        
        # Create loop if needed
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        
        # Run in executor to submit to queue
        future = asyncio.run_coroutine_threadsafe(
            self._submit_task_async(task),
            self.loop
        )
        future.result()  # Wait for submission
    
    async def _submit_task_async(self, task: ExecutionTask) -> None:
        """Async task submission."""
        await self.task_queue.put(task)
    
    def open_cycle(
        self,
        instrument: str,
        lot_size: float,
        direction: str = "BUY_SELL",
        strategy_id: Optional[str] = None,
        stop_loss_usd: Optional[float] = None,
        take_profit_usd: Optional[float] = None,
        comment: str = ""
    ) -> str:
        """
        Open a new trade cycle.
        
        Args:
            instrument: Trading instrument
            lot_size: Lot size per broker
            direction: Trade direction
            strategy_id: Strategy identifier
            stop_loss_usd: Stop loss in USD
            take_profit_usd: Take profit in USD
            comment: Cycle comment
            
        Returns:
            Cycle ID
        """
        # Create cycle in trade state manager
        cycle_id = self.trade_state_manager.create_cycle(
            instrument=instrument,
            lot_size=lot_size,
            direction=direction,
            strategy_id=strategy_id,
            stop_loss_usd=stop_loss_usd,
            take_profit_usd=take_profit_usd,
            comment=comment
        )
        
        # Submit task to open the cycle
        task = ExecutionTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            task_type="open_cycle",
            cycle_id=cycle_id,
            priority=1
        )
        self.submit_task(task)
        
        return cycle_id
    
    def close_cycle(self, cycle_id: str, reason: str = "manual", comment: str = "") -> None:
        """
        Close a trade cycle.
        
        Args:
            cycle_id: Cycle ID
            reason: Reason for closing
            comment: Additional comment
        """
        task = ExecutionTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            task_type="close_cycle",
            cycle_id=cycle_id,
            data={"reason": reason, "comment": comment},
            priority=1
        )
        self.submit_task(task)
    
    def emergency_stop(self, reason: str = "emergency_stop") -> None:
        """
        Trigger emergency stop.
        
        Args:
            reason: Reason for emergency stop
        """
        task = ExecutionTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            task_type="emergency_close",
            data={"reason": reason},
            priority=0  # Highest priority
        )
        self.submit_task(task)
    
    def reconcile(self) -> None:
        """Trigger reconciliation."""
        task = ExecutionTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            task_type="reconcile",
            priority=2
        )
        self.submit_task(task)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the execution worker.
        
        Returns:
            Status dictionary
        """
        return {
            "running": self.running,
            "paused": self.paused,
            "task_queue_size": self.task_queue.qsize() if self.loop else 0,
            "active_tasks": len(self.active_tasks),
            "active_cycles": len(self.trade_state_manager.active_cycles),
            "completed_cycles": len(self.trade_state_manager.completed_cycles),
            "last_reconciliation_time": self.last_reconciliation_time.isoformat() if self.last_reconciliation_time else None,
            "broker_connections": {
                broker_id: broker.is_connected()
                for broker_id, broker in self.order_manager.brokers.items()
            }
        }
    
    def get_active_cycles(self) -> Dict[str, TradeState]:
        """
        Get all active cycles.
        
        Returns:
            Dictionary of cycle_id -> TradeState
        """
        return self.trade_state_manager.get_active_cycles()
    
    def get_cycle_state(self, cycle_id: str) -> Optional[TradeState]:
        """
        Get the state of a specific cycle.
        
        Args:
            cycle_id: Cycle ID
            
        Returns:
            TradeState or None
        """
        return self.trade_state_manager.get_cycle_state(cycle_id)
    
    def get_all_pnl(self) -> Dict[str, Dict[str, float]]:
        """
        Get P&L for all active cycles.
        
        Returns:
            Dictionary of cycle_id -> P&L info
        """
        return self.trade_state_manager.get_all_pnl()


# Global execution worker instance
_execution_worker: Optional[ExecutionWorker] = None


def get_execution_worker() -> ExecutionWorker:
    """
    Get the global execution worker instance.
    
    Returns:
        ExecutionWorker instance
    """
    global _execution_worker
    if _execution_worker is None:
        _execution_worker = ExecutionWorker()
    return _execution_worker


def start_execution_worker() -> ExecutionWorker:
    """
    Start the global execution worker.
    
    Returns:
        ExecutionWorker instance
    """
    worker = get_execution_worker()
    worker.start()
    return worker


def stop_execution_worker() -> None:
    """Stop the global execution worker."""
    global _execution_worker
    if _execution_worker:
        _execution_worker.stop()
        _execution_worker = None
