"""
Broker Simulator for Testing

Provides a simulated broker implementation for testing without MT5 terminals.
This is a standalone simulator that doesn't require MT5 or real broker connections.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field

# Import enums from base_broker to ensure compatibility
from src.brokers.base_broker import (
    OrderSide,
    PositionSide,
    OrderType,
    OrderStatus,
    PositionStatus,
)


@dataclass
class Order:
    """Order representation."""
    order_id: str
    broker_id: str
    account_id: str
    instrument: str
    side: OrderSide
    volume: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    timestamp: datetime = field(default_factory=datetime.now)
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
    close_price: Optional[float] = None
    close_time: Optional[datetime] = None
    status: PositionStatus = PositionStatus.OPEN
    magic_number: Optional[int] = None


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
class AccountInfo:
    """Account information."""
    broker_id: str
    account_id: str
    account_name: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float
    currency: str
    account_type: str


@dataclass
class ContractSpec:
    """Contract specifications."""
    instrument: str
    contract_size: float = 1.0
    tick_value: float = 0.01
    tick_size: float = 0.01
    margin_requirement_percent: float = 1.0
    swap_long: float = 0.0
    swap_short: float = 0.0
    trading_hours: str = "00:00-23:59"
    min_lot_size: float = 0.01
    max_lot_size: float = 100.0
    lot_size_step: float = 0.01


class SimulatedBroker:
    """
    Simulated broker for testing without MT5 terminals.
    
    Provides mock implementations of broker methods with configurable behavior.
    This is a standalone class that doesn't inherit from BaseBroker.
    """
    
    def __init__(
        self,
        broker_id: str = "simulated",
        initial_balance: float = 10000.0,
        initial_equity: float = 10000.0,
        initial_free_margin: float = 10000.0,
    ):
        """
        Initialize simulated broker.
        
        Args:
            broker_id: Broker identifier
            initial_balance: Initial account balance
            initial_equity: Initial account equity
            initial_free_margin: Initial free margin
        """
        self.broker_id = broker_id
        self.connected = False
        
        # Account state
        self._balance = initial_balance
        self._equity = initial_equity
        self._free_margin = initial_free_margin
        self._margin_used = 0.0
        
        # Positions
        self._positions: Dict[str, Position] = {}
        self._position_counter = 0
        
        # Orders
        self._orders: Dict[str, Order] = {}
        self._order_counter = 0
        
        # Market data
        self._instrument_prices: Dict[str, float] = {
            "XAUUSD": 2000.0,
            "XAGUSD": 25.0,
            "BTCUSD": 50000.0,
            "ETHUSD": 3000.0,
            "EURUSD": 1.10,
        }
        self._instrument_spreads: Dict[str, float] = {
            "XAUUSD": 0.5,
            "XAGUSD": 0.02,
            "BTCUSD": 5.0,
            "ETHUSD": 1.0,
            "EURUSD": 0.0001,
        }
        
        # Contract specs
        self.contract_specs: Dict[str, ContractSpec] = {
            "XAUUSD": ContractSpec(
                instrument="XAUUSD",
                contract_size=100,
                tick_value=0.01,
                tick_size=0.01,
                margin_requirement_percent=0.5,
                swap_long=-5.0,
                swap_short=2.0,
                trading_hours="00:00-23:59",
            ),
            "BTCUSD": ContractSpec(
                instrument="BTCUSD",
                contract_size=1,
                tick_value=1.0,
                tick_size=0.01,
                margin_requirement_percent=2.0,
                swap_long=-10.0,
                swap_short=5.0,
                trading_hours="00:00-23:59",
            ),
        }
        
        # Account info
        self.account_info = AccountInfo(
            broker_id=broker_id,
            account_id=str(uuid.uuid4()),
            account_name=f"Simulated-{broker_id}",
            balance=initial_balance,
            equity=initial_equity,
            margin=initial_free_margin,
            free_margin=initial_free_margin,
            margin_level=100.0,
            currency="USD",
            account_type="DEMO",
        )
        
        # Behavior flags
        self.reject_orders = False
        self.partial_fills = False
        self.slippage_points = 0.0
        self.execution_delay_seconds = 0.0
    
    def connect(self) -> bool:
        """Connect to simulated broker."""
        self.connected = True
        return True
    
    def disconnect(self) -> None:
        """Disconnect from simulated broker."""
        self.connected = False
    
    def is_connected(self) -> bool:
        """Check if connected."""
        return self.connected
    
    def get_account_info(self) -> AccountInfo:
        """Get account information."""
        return self.account_info
    
    def get_balance(self) -> float:
        """Get account balance."""
        return self._balance
    
    def get_equity(self) -> float:
        """Get account equity."""
        return self._equity
    
    def get_free_margin(self) -> float:
        """Get free margin."""
        return self._free_margin
    
    def get_margin_used(self) -> float:
        """Get used margin."""
        return self._margin_used
    
    def get_contract_spec(self, instrument: str) -> Optional[ContractSpec]:
        """Get contract specifications."""
        return self.contract_specs.get(instrument)
    
    def get_tick(self, instrument: str) -> TickData:
        """Get current tick data."""
        price = self._instrument_prices.get(instrument, 0.0)
        spread = self._instrument_spreads.get(instrument, 0.0)
        return TickData(
            broker_id=self.broker_id,
            instrument=instrument,
            bid=price - spread/2,
            ask=price + spread/2,
            timestamp=datetime.now(),
            server_timestamp=datetime.now(),
        )
    
    def get_ticks(self, instrument: str, count: int = 1) -> List[TickData]:
        """Get multiple tick data points."""
        tick = self.get_tick(instrument)
        return [tick] * count
    
    def get_bid_ask(self, instrument: str) -> Tuple[float, float]:
        """Get bid and ask prices."""
        price = self._instrument_prices.get(instrument, 0.0)
        spread = self._instrument_spreads.get(instrument, 0.0)
        return price - spread/2, price + spread/2
    
    def set_price(self, instrument: str, price: float) -> None:
        """Set price for an instrument (for testing)."""
        self._instrument_prices[instrument] = price
    
    def set_spread(self, instrument: str, spread: float) -> None:
        """Set spread for an instrument (for testing)."""
        self._instrument_spreads[instrument] = spread
    
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
        magic_number: Optional[int] = None,
    ) -> Order:
        """Send an order (alias for place_order, compatible with base_broker interface)."""
        return self.place_order(
            instrument=instrument,
            side=side,
            volume=volume,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment,
            magic_number=magic_number,
        )
    
    def place_order(
        self,
        instrument: str,
        side: OrderSide,
        volume: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        comment: str = "",
        magic_number: Optional[int] = None,
    ) -> Order:
        """Place an order."""
        if not self.connected:
            raise ConnectionError("Broker not connected")
        
        if self.reject_orders:
            raise Exception("Order rejected by broker")
        
        # Generate order ID
        self._order_counter += 1
        order_id = f"{self.broker_id}-{self._order_counter}"
        
        # Get current price
        bid, ask = self.get_bid_ask(instrument)
        current_price = bid if side == OrderSide.SELL else ask
        
        # Apply slippage
        if self.slippage_points > 0:
            spec = self.get_contract_spec(instrument)
            if spec:
                if side == OrderSide.BUY:
                    current_price += self.slippage_points * spec.tick_size
                else:
                    current_price -= self.slippage_points * spec.tick_size
        
        # Create order
        order = Order(
            order_id=order_id,
            broker_id=self.broker_id,
            account_id=self.account_info.account_id,
            instrument=instrument,
            side=side,
            volume=volume,
            price=price or current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status=OrderStatus.FILLED,
            timestamp=datetime.now(),
            filled_volume=volume,
            filled_price=current_price,
            commission=0.0,
            swap=0.0,
            slippage=self.slippage_points,
            comment=comment,
            magic_number=magic_number,
        )
        
        self._orders[order_id] = order
        
        # Create position if market order
        position_id = f"{self.broker_id}-pos-{self._position_counter}"
        self._position_counter += 1
        
        position = Position(
            position_id=position_id,
            broker_id=self.broker_id,
            account_id=self.account_info.account_id,
            instrument=instrument,
            side=PositionSide(side.value),
            volume=volume,
            open_price=current_price,
            open_time=datetime.now(),
            current_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            commission=0.0,
            swap=0.0,
            profit=0.0,
            magic_number=magic_number,
        )
        self._positions[position_id] = position
        
        # Update account state
        spec = self.get_contract_spec(instrument)
        if spec:
            margin_required = volume * current_price * spec.contract_size * spec.margin_requirement_percent / 100
            self._margin_used += margin_required
            self._free_margin = self._balance - self._margin_used
        
        return order
    
    def close_position(self, position_id: str, volume: Optional[float] = None) -> Order:
        """Close a position."""
        if position_id not in self._positions:
            raise Exception(f"Position {position_id} not found")
        
        position = self._positions[position_id]
        
        # Determine close price
        bid, ask = self.get_bid_ask(position.instrument)
        close_price = ask if position.side == PositionSide.BUY else bid
        
        # Calculate P&L
        spec = self.get_contract_spec(position.instrument)
        if spec:
            if position.side == PositionSide.BUY:
                pnl = (close_price - position.open_price) * position.volume * spec.contract_size
            else:
                pnl = (position.open_price - close_price) * position.volume * spec.contract_size
        else:
            pnl = 0.0
        
        # Update account balance
        self._balance += pnl
        self._equity = self._balance
        
        # Release margin
        if spec:
            margin_required = position.volume * position.open_price * spec.contract_size * spec.margin_requirement_percent / 100
            self._margin_used -= margin_required
            self._free_margin = self._balance - self._margin_used
        
        # Create close order
        self._order_counter += 1
        order_id = f"{self.broker_id}-close-{self._order_counter}"
        
        close_order = Order(
            order_id=order_id,
            broker_id=self.broker_id,
            account_id=self.account_info.account_id,
            instrument=position.instrument,
            side=OrderSide.SELL if position.side == PositionSide.BUY else OrderSide.BUY,
            volume=volume or position.volume,
            price=close_price,
            status=OrderStatus.FILLED,
            timestamp=datetime.now(),
            filled_volume=volume or position.volume,
            filled_price=close_price,
            commission=0.0,
            swap=0.0,
            slippage=0.0,
            comment=f"Close position {position_id}",
        )
        
        self._orders[order_id] = close_order
        
        # Update position
        if volume and volume < position.volume:
            position.volume -= volume
        else:
            position.status = PositionStatus.CLOSED
            position.close_time = datetime.now()
            position.close_price = close_price
            position.profit = pnl
            del self._positions[position_id]
        
        return close_order
    
    def get_positions(self) -> List[Position]:
        """Get all open positions."""
        return list(self._positions.values())
    
    def get_open_positions(self) -> List[Position]:
        """Get all open positions (alias for get_positions)."""
        return self.get_positions()
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """Get a specific position."""
        return self._positions.get(position_id)
    
    def get_orders(self) -> List[Order]:
        """Get all orders."""
        return list(self._orders.values())
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get a specific order."""
        return self._orders.get(order_id)
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        if order_id in self._orders:
            order = self._orders[order_id]
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED
                return True
        return False
    
    def get_spread(self, instrument: str) -> float:
        """Get current spread."""
        return self._instrument_spreads.get(instrument, 0.0)
    
    def validate_lot_size(self, lot_size: float) -> bool:
        """Validate lot size."""
        return 0.01 <= lot_size <= 100.0
    
    def get_symbols(self) -> List[str]:
        """Get available symbols."""
        return list(self._instrument_prices.keys())


# Factory functions
def create_simulated_broker(
    broker_id: str = "simulated",
    initial_balance: float = 10000.0,
) -> SimulatedBroker:
    """Create a simulated broker instance."""
    return SimulatedBroker(
        broker_id=broker_id,
        initial_balance=initial_balance,
    )


def create_vantage_simulator(initial_balance: float = 10000.0) -> SimulatedBroker:
    """Create a simulated Vantage broker."""
    return SimulatedBroker(
        broker_id="vantage",
        initial_balance=initial_balance,
    )


def create_justmarkets_simulator(initial_balance: float = 10000.0) -> SimulatedBroker:
    """Create a simulated JustMarkets broker."""
    return SimulatedBroker(
        broker_id="justmarkets",
        initial_balance=initial_balance,
    )
