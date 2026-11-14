"""
Trade State Manager

Manages the state of paired trades and ensures consistency across brokers.
Provides reconciliation, state tracking, and recovery functionality.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any, Tuple, Set, Callable
import logging

from ..brokers.base_broker import BaseBroker, Position, PositionSide, PositionStatus
from ..core.config import get_config
from ..core.logging import get_logger
from ..core.database import get_database
from ..models.trades import Trade, TradeStatus
from ..models.positions import Position as PositionModel
from ..models.orders import Order as OrderModel
from ..models.trade_cycles import TradeCycle, CycleStatus
from .order_manager import OrderManager, OrderRequest, OrderResult, PairedOrderRequest


# Configure logging
logger = logging.getLogger(__name__)


class TradeStateError(Exception):
    """Trade state error."""
    pass


class ReconciliationError(TradeStateError):
    """Reconciliation error."""
    pass


class PositionMismatchError(ReconciliationError):
    """Position mismatch error."""
    pass


class TradeStatePersistenceError(TradeStateError):
    """
    Raised when a trade-state change could not be durably persisted after
    retrying.

    This must never be swallowed: it means our in-memory view of trade
    state (which cycles are open, which positions back them) may no longer
    match what a restart would recover from the database. Catching this
    and continuing as if nothing happened is exactly the failure mode that
    made emergency stop and restart recovery unreliable before - a cycle
    that "exists" only in memory is invisible to anything that restarts.
    """
    pass


@dataclass
class TradeState:
    """Represents the current state of a trade cycle."""
    cycle_id: str
    status: CycleStatus
    broker_a_position_id: Optional[str] = None
    broker_b_position_id: Optional[str] = None
    broker_a_order_id: Optional[str] = None
    broker_b_order_id: Optional[str] = None
    instrument: str = ""
    lot_size: float = 0.01
    direction: str = "BUY_SELL"
    opened_time: Optional[datetime] = None
    closed_time: Optional[datetime] = None
    strategy_id: Optional[str] = None
    
    @property
    def is_complete(self) -> bool:
        """Check if trade cycle is complete."""
        return (
            self.broker_a_position_id is not None
            and self.broker_b_position_id is not None
            and self.status == CycleStatus.CLOSED
        )
    
    @property
    def is_open(self) -> bool:
        """Check if trade cycle is open."""
        return self.status in [CycleStatus.OPEN, CycleStatus.OPENING, CycleStatus.CLOSING]
    
    def get_broker_a_direction(self) -> str:
        """Get the expected direction for broker A."""
        direction = self.direction.upper()
        return "BUY" if direction.startswith("BUY") else "SELL"
    
    def get_broker_b_direction(self) -> str:
        """Get the expected direction for broker B (opposite of A)."""
        direction = self.direction.upper()
        return "SELL" if direction.startswith("BUY") else "BUY"
    
    @property
    def both_positions_opened(self) -> bool:
        """Check if both positions are opened."""
        return self.broker_a_position_id is not None and self.broker_b_position_id is not None
    
    @property
    def both_positions_closed(self) -> bool:
        """Check if both positions are closed."""
        return self.closed_time is not None and self.status == CycleStatus.CLOSED


@dataclass
class ReconciliationResult:
    """Result of a reconciliation check."""
    success: bool
    mismatches: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    actions_taken: List[str] = field(default_factory=list)


class TradeStateManager:
    """
    Manages the state of paired trades across brokers.
    
    Provides:
    - Trade cycle lifecycle management
    - Position reconciliation
    - State persistence
    - Error recovery
    """
    
    def __init__(self):
        """Initialize the trade state manager."""
        self.order_manager = OrderManager()
        self.db = get_database()
        self.logger = get_logger("execution.trade_state")
        
        # In-memory state tracking
        self.active_cycles: Dict[str, TradeState] = {}
        self.pending_cycles: Dict[str, PairedOrderRequest] = {}
        self.completed_cycles: Dict[str, TradeState] = {}
        
        # Configuration
        self.max_active_cycles = 10
        self.reconciliation_interval = 60  # seconds
        self.position_mismatch_tolerance = 0.001  # lot tolerance
        self.db_max_retries = 3
        self.db_retry_delay = 0.5  # seconds

        self._initialized = False
        # Guards initialize(): it is now called both from the FastAPI
        # lifespan (risk engine startup) and from ExecutionWorker's own
        # background thread, against this same shared singleton. Without
        # this, both could race past the "if self._initialized: return"
        # check and double-initialize (double DB load, double connect_all).
        self._init_lock = threading.Lock()

    def _with_db_retries(self, fn: Callable[[], None], description: str) -> None:
        """
        Run a database write, retrying a bounded number of times on
        failure. If every attempt fails, raise TradeStatePersistenceError
        rather than log-and-continue - a caller that ignores this exception
        is explicitly choosing to proceed with state that may not survive
        a restart, which should never be the silent default.
        """
        last_error: Optional[Exception] = None
        for attempt in range(self.db_max_retries):
            try:
                fn()
                return
            except Exception as e:
                last_error = e
                self.logger.error(
                    f"{description} failed (attempt {attempt + 1}/{self.db_max_retries}): {e}"
                )
                if attempt < self.db_max_retries - 1:
                    time.sleep(self.db_retry_delay)

        self.logger.critical(f"{description} failed after {self.db_max_retries} attempts: {last_error}")
        raise TradeStatePersistenceError(
            f"{description} failed after {self.db_max_retries} attempts: {last_error}"
        )

    def initialize(self) -> None:
        """
        Initialize the trade state manager.

        Raises:
            TradeStatePersistenceError: If existing cycles cannot be loaded
                from the database. Starting up with an empty active_cycles
                dict when the database is simply unreachable would make
                emergency stop and reconciliation silently cover nothing -
                that is worse than refusing to start.
        """
        if self._initialized:
            return

        with self._init_lock:
            if self._initialized:
                return

            self.order_manager.initialize()
            self.order_manager.connect_all()

            # Load existing cycles from database
            try:
                self._load_cycles_from_db()
            except Exception as e:
                self.logger.critical(
                    f"Failed to load trade cycles from database on startup: {e}. "
                    f"Refusing to start with unknown trade state."
                )
                raise TradeStatePersistenceError(
                    f"Failed to load trade cycles from database on startup: {e}"
                )

            self._initialized = True
            self.logger.info("Trade state manager initialized")

    def _load_cycles_from_db(self) -> None:
        """
        Load trade cycles from database.

        Raises:
            Exception: Propagates any database error rather than swallowing
                it - callers (initialize()) decide how to react, but this
                method itself never hides a failure to load state.
        """
        with self.db.get_session() as session:
            # Load active cycles
            active_cycles = session.query(TradeCycle).filter(
                TradeCycle.status.in_([
                    CycleStatus.INITIATED.value,
                    CycleStatus.OPENING.value,
                    CycleStatus.OPEN.value,
                    CycleStatus.CLOSING.value
                ])
            ).all()

            for cycle in active_cycles:
                self.active_cycles[cycle.cycle_id] = TradeState(
                    cycle_id=cycle.cycle_id,
                    status=CycleStatus(cycle.status),
                    broker_a_position_id=cycle.position_a_id,
                    broker_b_position_id=cycle.position_b_id,
                    instrument=cycle.instrument,
                    lot_size=cycle.lot_size,
                    direction=cycle.direction,
                    opened_time=cycle.opened_time,
                    closed_time=cycle.closed_time,
                    strategy_id=cycle.strategy_id
                )

            self.logger.info(f"Loaded {len(active_cycles)} active cycles from database")
    
    def create_cycle(
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
        Create a new trade cycle.
        
        Args:
            instrument: Trading instrument
            lot_size: Lot size per broker
            direction: Trade direction (BUY_SELL or SELL_BUY)
            strategy_id: Strategy identifier
            stop_loss_usd: Stop loss in USD
            take_profit_usd: Take profit in USD
            comment: Cycle comment
            
        Returns:
            Cycle ID
        """
        cycle_id = f"cycle_{uuid.uuid4().hex[:12]}"

        # Create cycle record in database. A cycle that cannot be durably
        # recorded must not be allowed to silently proceed as in-memory-only:
        # a crash before the next successful write would then lose track of
        # it entirely, which is exactly the scenario emergency stop and
        # restart recovery exist to cover.
        def _write():
            with self.db.get_session() as session:
                cycle = TradeCycle(
                    cycle_id=cycle_id,
                    strategy_id=strategy_id or "paired_exit",
                    strategy_name=strategy_id or "Paired Exit",
                    instrument=instrument,
                    broker_a_id="vantage",
                    broker_b_id="justmarkets",
                    lot_size=lot_size,
                    direction=direction,
                    initiated_time=datetime.utcnow(),
                    status=CycleStatus.INITIATED.value,
                    comment=comment
                )
                session.add(cycle)
                session.commit()

        self._with_db_retries(_write, f"Creating cycle record {cycle_id}")
        
        # Create state
        state = TradeState(
            cycle_id=cycle_id,
            status=CycleStatus.INITIATED,
            instrument=instrument,
            lot_size=lot_size,
            direction=direction,
            strategy_id=strategy_id,
            opened_time=None,
            closed_time=None
        )
        
        self.pending_cycles[cycle_id] = PairedOrderRequest(
            cycle_id=cycle_id,
            instrument=instrument,
            lot_size=lot_size,
            direction=direction,
            strategy_id=strategy_id,
            stop_loss_usd=stop_loss_usd,
            take_profit_usd=take_profit_usd,
            comment=comment
        )
        
        self.active_cycles[cycle_id] = state
        
        self.logger.info(f"Created new cycle: {cycle_id}, {instrument}, {lot_size}, {direction}")
        
        return cycle_id
    
    def open_cycle(
        self,
        cycle_id: Optional[str] = None,
        instrument: Optional[str] = None,
        lot_size: Optional[float] = None,
        direction: str = "BUY_SELL",
        strategy_id: Optional[str] = None,
        stop_loss_usd: Optional[float] = None,
        take_profit_usd: Optional[float] = None,
        comment: str = ""
    ) -> TradeState:
        """
        Open a trade cycle by executing paired orders.
        
        Can be called with either:
        - cycle_id: Open an existing pending cycle
        - instrument, lot_size, etc.: Create and open a new cycle
        
        Args:
            cycle_id: Cycle ID (optional if creating new)
            instrument: Trading instrument (required if creating new)
            lot_size: Lot size per broker (required if creating new)
            direction: Trade direction
            strategy_id: Strategy identifier
            stop_loss_usd: Stop loss in USD
            take_profit_usd: Take profit in USD
            comment: Cycle comment
            
        Returns:
            TradeState with updated position IDs
            
        Raises:
            TradeStateError: If cycle cannot be opened
        """
        # If cycle_id provided, use existing pending cycle
        if cycle_id and cycle_id in self.pending_cycles:
            request = self.pending_cycles[cycle_id]
        elif instrument and lot_size:
            # Create a new cycle
            cycle_id = self.create_cycle(
                instrument=instrument,
                lot_size=lot_size,
                direction=direction,
                strategy_id=strategy_id,
                stop_loss_usd=stop_loss_usd,
                take_profit_usd=take_profit_usd,
                comment=comment,
            )
            request = self.pending_cycles[cycle_id]
        else:
            raise TradeStateError("Either cycle_id or (instrument and lot_size) must be provided")
        
        state = self.active_cycles.get(cycle_id)
        state = self.active_cycles.get(cycle_id)
        
        if state is None:
            raise TradeStateError(f"Cycle state not found: {cycle_id}")
        
        # Update state
        state.status = CycleStatus.OPENING
        
        # Execute paired orders
        try:
            result_a, result_b = self.order_manager.execute_paired_orders(request)
            
            # Check results
            if not result_a.success or not result_b.success:
                # Handle partial failure
                if result_a.success and result_b.success is False:
                    # Close broker A position
                    self.logger.warning(f"Broker B order failed, closing broker A position")
                    if result_a.order and result_a.order.position_id:
                        self.order_manager.close_position("vantage", result_a.order.position_id)
                    raise TradeStateError(
                        f"Partial failure: A={result_a.success}, B={result_b.success}, "
                        f"B_error={result_b.error}"
                    )
                elif result_b.success and result_a.success is False:
                    # Close broker B position
                    self.logger.warning(f"Broker A order failed, closing broker B position")
                    if result_b.order and result_b.order.position_id:
                        self.order_manager.close_position("justmarkets", result_b.order.position_id)
                    raise TradeStateError(
                        f"Partial failure: A={result_a.success}, B={result_b.success}, "
                        f"A_error={result_a.error}"
                    )
                else:
                    raise TradeStateError(
                        f"Both orders failed: A={result_a.error}, B={result_b.error}"
                    )
            
            # Update state with position IDs
            state.broker_a_position_id = result_a.order.position_id if result_a.order else None
            state.broker_b_position_id = result_b.order.position_id if result_b.order else None
            state.broker_a_order_id = result_a.order.order_id if result_a.order else None
            state.broker_b_order_id = result_b.order.order_id if result_b.order else None
            state.opened_time = datetime.utcnow()
            state.status = CycleStatus.OPEN
            
            # Remove from pending
            del self.pending_cycles[cycle_id]
            
            # Update in database
            self._update_cycle_in_db(state)
            
            self.logger.info(
                f"Cycle opened: {cycle_id}, "
                f"A_pos={state.broker_a_position_id}, "
                f"B_pos={state.broker_b_position_id}"
            )
            
            return cycle_id
            
        except Exception as e:
            state.status = CycleStatus.ERROR
            self.logger.error(f"Failed to open cycle {cycle_id}: {e}")
            try:
                self._update_cycle_in_db(state)
            except TradeStatePersistenceError as persist_error:
                # Don't let a persistence failure during error-handling bury
                # the original failure that got us here - surface both.
                raise TradeStateError(
                    f"Failed to open cycle: {e}. Additionally, could not persist "
                    f"the resulting ERROR status: {persist_error}"
                )
            raise TradeStateError(f"Failed to open cycle: {e}")
    
    def close_cycle(self, cycle_id: str, reason: str = "manual", comment: str = "") -> TradeState:
        """
        Close a trade cycle by closing both positions.
        
        Args:
            cycle_id: Cycle ID
            reason: Reason for closing
            comment: Additional comment
            
        Returns:
            Updated TradeState
            
        Raises:
            TradeStateError: If cycle cannot be closed
        """
        if cycle_id not in self.active_cycles:
            raise TradeStateError(f"Cycle not found: {cycle_id}")
        
        state = self.active_cycles[cycle_id]
        
        if not state.is_open:
            raise TradeStateError(f"Cycle {cycle_id} is not open")
        
        # Update state
        state.status = CycleStatus.CLOSING
        
        try:
            # Close both positions
            success_a = False
            success_b = False
            
            if state.broker_a_position_id:
                success_a = self.order_manager.close_position(
                    "vantage", state.broker_a_position_id
                )
            
            if state.broker_b_position_id:
                success_b = self.order_manager.close_position(
                    "justmarkets", state.broker_b_position_id
                )
            
            if not success_a or not success_b:
                self.logger.warning(
                    f"Partial close: A={success_a}, B={success_b}"
                )
                # Try to close the other position if one failed
                if not success_a and state.broker_a_position_id:
                    self.order_manager.close_position("vantage", state.broker_a_position_id)
                if not success_b and state.broker_b_position_id:
                    self.order_manager.close_position("justmarkets", state.broker_b_position_id)
            
            # Update state
            state.closed_time = datetime.utcnow()
            state.status = CycleStatus.CLOSED
            state.exit_reason = reason
            state.exit_comment = comment
            
            # Move to completed
            self.completed_cycles[cycle_id] = state
            del self.active_cycles[cycle_id]
            
            # Update in database
            self._update_cycle_in_db(state)
            
            self.logger.info(f"Cycle closed: {cycle_id}, reason={reason}")
            
            return True
            
        except Exception as e:
            state.status = CycleStatus.ERROR
            self.logger.error(f"Failed to close cycle {cycle_id}: {e}")
            try:
                self._update_cycle_in_db(state)
            except TradeStatePersistenceError as persist_error:
                # Positions may already be closed on the broker side at this
                # point - never let a persistence failure here disappear
                # silently, and never let it bury the original failure either.
                raise TradeStateError(
                    f"Failed to close cycle: {e}. Additionally, could not persist "
                    f"the resulting ERROR status: {persist_error}"
                )
            raise TradeStateError(f"Failed to close cycle: {e}")
    
    def close_cycle_by_position(
        self,
        broker_id: str,
        position_id: str,
        reason: str = "manual",
        comment: str = ""
    ) -> Optional[TradeState]:
        """
        Close a cycle by finding the position and closing both positions.
        
        Args:
            broker_id: Broker identifier
            position_id: Position ID to close
            reason: Reason for closing
            comment: Additional comment
            
        Returns:
            Updated TradeState or None if cycle not found
        """
        # Find cycle with this position
        cycle_id = None
        for cid, state in self.active_cycles.items():
            if (broker_id == "vantage" and state.broker_a_position_id == position_id) or \
               (broker_id == "justmarkets" and state.broker_b_position_id == position_id):
                cycle_id = cid
                break
        
        if cycle_id is None:
            self.logger.warning(f"Position {position_id} not found in any active cycle")
            return None
        
        return self.close_cycle(cycle_id, reason, comment)
    
    def emergency_close_all(self, reason: str = "emergency_stop") -> Dict[str, bool]:
        """
        Emergency close all active cycles.
        
        Args:
            reason: Reason for emergency close
            
        Returns:
            Dictionary of cycle_id -> success
        """
        results = {}
        
        for cycle_id, state in list(self.active_cycles.items()):
            try:
                self.close_cycle(cycle_id, reason, f"Emergency stop triggered")
                results[cycle_id] = True
            except Exception as e:
                self.logger.error(f"Failed to emergency close cycle {cycle_id}: {e}")
                results[cycle_id] = False
        
        self.logger.warning(f"Emergency close completed: {sum(results.values())}/{len(results)} successful")
        return results
    
    def emergency_stop(self, reason: str = "emergency_stop") -> bool:
        """
        Emergency stop - closes all active positions.
        
        Args:
            reason: Reason for emergency stop
            
        Returns:
            True if successful
        """
        result = self.emergency_close_all(reason)
        return all(result.values()) if result else True
    
    def reconcile_positions(self) -> ReconciliationResult:
        """
        Reconcile positions across brokers.
        
        Checks that paired positions are consistent and handles mismatches.
        
        Returns:
            ReconciliationResult
        """
        result = ReconciliationResult(success=True)
        
        try:
            # Get positions from both brokers
            broker_a_positions = self.order_manager.get_open_positions("vantage")
            broker_b_positions = self.order_manager.get_open_positions("justmarkets")
            
            # Build position maps
            broker_a_map: Dict[str, Position] = {pos.position_id: pos for pos in broker_a_positions}
            broker_b_map: Dict[str, Position] = {pos.position_id: pos for pos in broker_b_positions}
            
            # Check active cycles
            for cycle_id, state in list(self.active_cycles.items()):
                if state.status != CycleStatus.OPEN:
                    continue
                
                # Check if positions exist
                if state.broker_a_position_id and state.broker_a_position_id not in broker_a_map:
                    result.mismatches.append(
                        f"Cycle {cycle_id}: Broker A position {state.broker_a_position_id} not found"
                    )
                    result.actions_taken.append(
                        f"Cycle {cycle_id}: Marking as error due to missing position"
                    )
                    state.status = CycleStatus.ERROR
                    self._update_cycle_in_db(state)
                    result.success = False
                
                if state.broker_b_position_id and state.broker_b_position_id not in broker_b_map:
                    result.mismatches.append(
                        f"Cycle {cycle_id}: Broker B position {state.broker_b_position_id} not found"
                    )
                    result.actions_taken.append(
                        f"Cycle {cycle_id}: Marking as error due to missing position"
                    )
                    state.status = CycleStatus.ERROR
                    self._update_cycle_in_db(state)
                    result.success = False
                
                # Check if positions are still open
                if state.broker_a_position_id and state.broker_a_position_id in broker_a_map:
                    pos = broker_a_map[state.broker_a_position_id]
                    if pos.status != PositionStatus.OPEN:
                        result.warnings.append(
                            f"Cycle {cycle_id}: Broker A position {state.broker_a_position_id} is not open"
                        )
                
                if state.broker_b_position_id and state.broker_b_position_id in broker_b_map:
                    pos = broker_b_map[state.broker_b_position_id]
                    if pos.status != PositionStatus.OPEN:
                        result.warnings.append(
                            f"Cycle {cycle_id}: Broker B position {state.broker_b_position_id} is not open"
                        )
                
                # Check if positions are paired (opposite directions)
                if (state.broker_a_position_id and state.broker_b_position_id and
                    state.broker_a_position_id in broker_a_map and
                    state.broker_b_position_id in broker_b_map):
                    
                    pos_a = broker_a_map[state.broker_a_position_id]
                    pos_b = broker_b_map[state.broker_b_position_id]
                    
                    # Check if instruments match
                    if pos_a.instrument != pos_b.instrument:
                        result.mismatches.append(
                            f"Cycle {cycle_id}: Instrument mismatch - A: {pos_a.instrument}, B: {pos_b.instrument}"
                        )
                        result.success = False
                    
                    # Check if directions are opposite
                    expected_a_direction = state.get_broker_a_direction()
                    expected_b_direction = state.get_broker_b_direction()
                    
                    if pos_a.side.value != expected_a_direction:
                        result.mismatches.append(
                            f"Cycle {cycle_id}: Broker A direction mismatch - Expected: {expected_a_direction}, Actual: {pos_a.side.value}"
                        )
                        result.success = False
                    
                    if pos_b.side.value != expected_b_direction:
                        result.mismatches.append(
                            f"Cycle {cycle_id}: Broker B direction mismatch - Expected: {expected_b_direction}, Actual: {pos_b.side.value}"
                        )
                        result.success = False
                    
                    # Check if volumes are approximately equal
                    if abs(pos_a.volume - pos_b.volume) > self.position_mismatch_tolerance:
                        result.warnings.append(
                            f"Cycle {cycle_id}: Volume mismatch - A: {pos_a.volume}, B: {pos_b.volume}"
                        )
            
            # Check for orphaned positions (positions not in any cycle)
            all_cycle_positions = set()
            for state in self.active_cycles.values():
                if state.broker_a_position_id:
                    all_cycle_positions.add(state.broker_a_position_id)
                if state.broker_b_position_id:
                    all_cycle_positions.add(state.broker_b_position_id)
            
            for pos_id in broker_a_map:
                if pos_id not in all_cycle_positions:
                    result.warnings.append(f"Orphaned position on broker A: {pos_id}")
            
            for pos_id in broker_b_map:
                if pos_id not in all_cycle_positions:
                    result.warnings.append(f"Orphaned position on broker B: {pos_id}")
            
            if result.warnings:
                result.success = False  # Orphaned positions are a problem
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error during reconciliation: {e}")
            return ReconciliationResult(
                success=False,
                errors=[str(e)]
            )
    
    def fix_mismatches(self, reconciliation_result: ReconciliationResult) -> ReconciliationResult:
        """
        Attempt to fix mismatches found during reconciliation.
        
        Args:
            reconciliation_result: Result from reconciliation
            
        Returns:
            Updated reconciliation result with actions taken
        """
        result = reconciliation_result
        
        # For now, just log the mismatches
        # In a production system, this would attempt to close mismatched positions
        for mismatch in result.mismatches:
            self.logger.error(f"Mismatch detected: {mismatch}")
        
        for warning in result.warnings:
            self.logger.warning(f"Warning: {warning}")
        
        return result
    
    def get_cycle_state(self, cycle_id: str) -> Optional[TradeState]:
        """
        Get the state of a specific cycle.
        
        Args:
            cycle_id: Cycle ID
            
        Returns:
            TradeState or None
        """
        return self.active_cycles.get(cycle_id) or self.completed_cycles.get(cycle_id)
    
    def get_active_cycles(self) -> Dict[str, TradeState]:
        """
        Get all active cycles.
        
        Returns:
            Dictionary of cycle_id -> TradeState
        """
        return self.active_cycles.copy()
    
    def get_completed_cycles(self, limit: int = 100) -> List[TradeState]:
        """
        Get completed cycles.
        
        Args:
            limit: Maximum number of cycles to return
            
        Returns:
            List of TradeState
        """
        return list(self.completed_cycles.values())[-limit:]
    
    def get_cycle_pnl(self, cycle_id: str) -> Optional[Dict[str, float]]:
        """
        Get P&L for a specific cycle.
        
        Args:
            cycle_id: Cycle ID
            
        Returns:
            Dictionary with P&L information or None
        """
        state = self.get_cycle_state(cycle_id)
        if state is None:
            return None
        
        try:
            # Get positions from brokers
            broker_a_pos = None
            broker_b_pos = None
            
            if state.broker_a_position_id:
                broker_a_pos = self.order_manager.get_position("vantage", state.broker_a_position_id)
            if state.broker_b_position_id:
                broker_b_pos = self.order_manager.get_position("justmarkets", state.broker_b_position_id)
            
            # Calculate P&L
            pnl_a = broker_a_pos.profit if broker_a_pos else 0.0
            pnl_b = broker_b_pos.profit if broker_b_pos else 0.0
            combined_pnl = pnl_a + pnl_b
            
            return {
                "broker_a_pnl": pnl_a,
                "broker_b_pnl": pnl_b,
                "combined_pnl": combined_pnl,
                "calculated_time": datetime.utcnow()
            }
        except Exception as e:
            self.logger.error(f"Error getting P&L for cycle {cycle_id}: {e}")
            return None
    
    def get_all_pnl(self) -> Dict[str, Dict[str, float]]:
        """
        Get P&L for all active cycles.
        
        Returns:
            Dictionary of cycle_id -> P&L info
        """
        results = {}
        for cycle_id in self.active_cycles:
            pnl = self.get_cycle_pnl(cycle_id)
            if pnl:
                results[cycle_id] = pnl
        return results
    
    def _update_cycle_in_db(self, state: TradeState) -> None:
        """
        Update cycle state in database.

        Raises:
            TradeStatePersistenceError: If the update cannot be persisted
                after retrying. Never swallowed - by the time this is
                called, broker-side actions (an open or close) have
                typically already happened, so losing this write silently
                would leave our recorded state wrong about something real.

        Args:
            state: TradeState to update
        """
        def _write():
            with self.db.get_session() as session:
                cycle = session.query(TradeCycle).filter_by(cycle_id=state.cycle_id).first()
                if cycle is None:
                    raise TradeStateError(f"Cycle {state.cycle_id} not found in database for update")
                cycle.status = state.status.value
                cycle.position_a_id = state.broker_a_position_id
                cycle.position_b_id = state.broker_b_position_id
                cycle.opened_time = state.opened_time
                cycle.closed_time = state.closed_time
                cycle.exit_reason = getattr(state, 'exit_reason', None)
                cycle.exit_comment = getattr(state, 'exit_comment', None)
                session.commit()

        self._with_db_retries(_write, f"Updating cycle {state.cycle_id} (status={state.status.value})")

    def save_trade(self, trade: Trade) -> None:
        """
        Save a trade to the database.

        Args:
            trade: Trade to save

        Raises:
            TradeStatePersistenceError: If the save cannot be persisted after retrying.
        """
        def _write():
            with self.db.get_session() as session:
                session.add(trade)
                session.commit()

        self._with_db_retries(_write, "Saving trade")

    def save_position(self, position: PositionModel) -> None:
        """
        Save a position to the database.

        Args:
            position: Position to save

        Raises:
            TradeStatePersistenceError: If the save cannot be persisted after retrying.
        """
        def _write():
            with self.db.get_session() as session:
                session.add(position)
                session.commit()

        self._with_db_retries(_write, "Saving position")

    def save_order(self, order: OrderModel) -> None:
        """
        Save an order to the database.

        Args:
            order: Order to save

        Raises:
            TradeStatePersistenceError: If the save cannot be persisted after retrying.
        """
        def _write():
            with self.db.get_session() as session:
                session.add(order)
                session.commit()

        self._with_db_retries(_write, "Saving order")
    
    def cleanup_completed_cycles(self, max_completed: int = 1000) -> int:
        """
        Clean up old completed cycles.
        
        Args:
            max_completed: Maximum number of completed cycles to keep
            
        Returns:
            Number of cycles removed
        """
        if len(self.completed_cycles) <= max_completed:
            return 0
        
        # Remove oldest cycles
        to_remove = list(self.completed_cycles.keys())[:-max_completed]
        for cycle_id in to_remove:
            del self.completed_cycles[cycle_id]
        
        return len(to_remove)


# Global trade state manager instance
_trade_state_manager: Optional[TradeStateManager] = None


def get_trade_state_manager() -> TradeStateManager:
    """
    Get the global trade state manager instance.
    
    Returns:
        TradeStateManager instance
    """
    global _trade_state_manager
    if _trade_state_manager is None:
        _trade_state_manager = TradeStateManager()
    return _trade_state_manager


def reset_trade_state_manager() -> None:
    """Reset the global trade state manager instance."""
    global _trade_state_manager
    if _trade_state_manager:
        _trade_state_manager.order_manager.disconnect_all()
        _trade_state_manager = None
