"""
Vantage Markets Broker Implementation

Concrete implementation of BaseBroker for Vantage Markets.
Uses MetaTrader5 Python package for connectivity.
"""

import asyncio
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple, Union
import logging
import time

from .base_broker import (
    BaseBroker,
    TickData,
    BarData,
    Order,
    Position,
    AccountInfo,
    ContractSpec,
    OrderType,
    OrderSide,
    PositionSide,
    OrderStatus,
    PositionStatus,
    BrokerError,
    ConnectionError,
    OrderError,
    PositionError,
    MarketDataError,
)
from ..core.config import get_config
from ..core.logging import get_logger


# Configure logging
logger = logging.getLogger(__name__)


class VantageBroker(BaseBroker):
    """
    Vantage Markets broker implementation.
    
    Connects to Vantage MT5 terminal using MetaTrader5 Python package.
    """
    
    def __init__(self, broker_id: str = "vantage", config: Optional[Dict[str, Any]] = None):
        """
        Initialize Vantage broker.
        
        Args:
            broker_id: Broker identifier
            config: Broker configuration
        """
        super().__init__(broker_id, config)
        
        # MT5 specific settings
        self.mt5_path = self.config.get("mt5_path")
        self.server = None
        self.login = None
        self.password = None
        self.account_type = None
        
        # Set connection parameters based on trading mode
        self._set_connection_parameters()
        
        # MT5 connection handle
        self._mt5 = None
        
        # IB Rebate configuration
        self.ib_rebate_config = self.config.get("ib_rebate", {})
    
    def _set_connection_parameters(self) -> None:
        """Set connection parameters based on trading mode."""
        trading_mode = get_config().get_trading_mode()
        
        if trading_mode == "LIVE":
            live_config = self.config.get("live", {})
            self.server = live_config.get("server")
            self.login = live_config.get("login")
            self.password = live_config.get("password")
            self.account_type = live_config.get("account_type", "REAL")
        else:
            demo_config = self.config.get("demo", {})
            self.server = demo_config.get("server")
            self.login = demo_config.get("login")
            self.password = demo_config.get("password")
            self.account_type = demo_config.get("account_type", "DEMO")
    
    def _import_mt5(self):
        """
        Import MetaTrader5 package with error handling.
        
        Returns:
            MetaTrader5 module or None
        """
        try:
            import MetaTrader5 as mt5
            return mt5
        except ImportError as e:
            logger.error(f"MetaTrader5 package not found: {e}")
            logger.error("Install MetaTrader5 from: https://www.mql5.com/en/docs/integration/python_metatrader5")
            return None
        except Exception as e:
            logger.error(f"Error importing MetaTrader5: {e}")
            return None
    
    def connect(self) -> bool:
        """
        Connect to Vantage MT5 terminal.
        
        Returns:
            True if connection successful
            
        Raises:
            ConnectionError: If connection fails
        """
        mt5 = self._import_mt5()
        if mt5 is None:
            raise ConnectionError("MetaTrader5 package not available")
        
        try:
            # Initialize MT5
            if not mt5.initialize(
                login=self.login,
                password=self.password,
                server=self.server,
                path=self.mt5_path
            ):
                error_code = mt5.last_error()
                error_msg = f"MT5 initialization failed with code {error_code}"
                logger.error(error_msg)
                raise ConnectionError(error_msg)
            
            self._mt5 = mt5
            self.connected = True
            
            # Get account info
            self.account_info = self.get_account_info()
            
            logger.info(f"Connected to Vantage MT5 terminal: {self.server}")
            logger.info(f"Account: {self.account_info.account_id}, Balance: {self.account_info.balance}")
            
            return True
            
        except Exception as e:
            self.connected = False
            logger.error(f"Connection failed: {e}")
            raise ConnectionError(f"Connection failed: {e}")
    
    def disconnect(self) -> None:
        """Disconnect from Vantage MT5 terminal."""
        if self._mt5 is not None:
            try:
                self._mt5.shutdown()
                self._mt5 = None
                self.connected = False
                logger.info("Disconnected from Vantage MT5 terminal")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
    
    def is_connected(self) -> bool:
        """Check if connected to broker."""
        if not self.connected:
            return False
        
        if self._mt5 is None:
            return False
        
        try:
            # Test connection with a simple call
            self._mt5.symbols_total()
            return True
        except:
            return False
    
    def _reconnect_if_needed(self) -> bool:
        """
        Reconnect if connection is lost.
        
        Returns:
            True if connection is active
        """
        if not self.is_connected():
            logger.warning("Connection lost, attempting to reconnect...")
            try:
                self.disconnect()
                return self.connect()
            except Exception as e:
                logger.error(f"Reconnection failed: {e}")
                return False
        return True
    
    def get_account_info(self) -> AccountInfo:
        """
        Get account information.
        
        Returns:
            AccountInfo object
        """
        if not self._reconnect_if_needed():
            raise ConnectionError("Not connected to broker")
        
        try:
            account_info = self._mt5.account_info()
            if account_info is None:
                raise ConnectionError("Failed to get account info")
            
            # Convert to AccountInfo
            return AccountInfo(
                broker_id=self.broker_id,
                account_id=str(account_info.login),
                balance=float(account_info.balance),
                equity=float(account_info.equity),
                free_margin=float(account_info.margin_free),
                margin=float(account_info.margin),
                margin_level=float(account_info.margin_level),
                currency=account_info.currency,
                leverage=int(account_info.leverage),
                timestamp=datetime.utcnow()
            )
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            raise ConnectionError(f"Failed to get account info: {e}")
    
    def get_tick(self, instrument: str) -> TickData:
        """
        Get current tick data.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            TickData object
        """
        if not self._reconnect_if_needed():
            raise ConnectionError("Not connected to broker")
        
        # Map instrument to broker symbol
        broker_symbol = self.map_instrument(instrument)
        
        try:
            tick = self._mt5.symbol_info_tick(broker_symbol)
            if tick is None:
                raise MarketDataError(f"No tick data for {broker_symbol}")
            
            return TickData(
                broker_id=self.broker_id,
                instrument=instrument,
                bid=float(tick.bid),
                ask=float(tick.ask),
                timestamp=datetime.utcnow(),
                server_timestamp=datetime.fromtimestamp(tick.time),
                volume=float(tick.volume)
            )
        except Exception as e:
            logger.error(f"Failed to get tick for {instrument}: {e}")
            raise MarketDataError(f"Failed to get tick: {e}")
    
    def get_bid_ask(self, instrument: str) -> Tuple[float, float]:
        """
        Get bid and ask prices.
        
        Args:
            instrument: Instrument symbol
            
        Returns:
            Tuple of (bid, ask)
        """
        tick = self.get_tick(instrument)
        return (tick.bid, tick.ask)
    
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
            timeframe: Timeframe (M1, M5, H1, D1, etc.)
            count: Number of bars
            start_time: Optional start time
            
        Returns:
            List of BarData objects
        """
        if not self._reconnect_if_needed():
            raise ConnectionError("Not connected to broker")
        
        # Map instrument to broker symbol
        broker_symbol = self.map_instrument(instrument)
        
        # Convert timeframe to MT5 format
        mt5_timeframe = self._convert_timeframe(timeframe)
        
        try:
            if start_time:
                # Get bars from specific time
                bars = self._mt5.copy_rates_from(
                    broker_symbol,
                    mt5_timeframe,
                    start_time,
                    count
                )
            else:
                # Get last N bars
                bars = self._mt5.copy_rates_from_pos(
                    broker_symbol,
                    mt5_timeframe,
                    0,
                    count
                )
            
            if bars is None or len(bars) == 0:
                raise MarketDataError(f"No bar data for {broker_symbol} {timeframe}")
            
            result = []
            for bar in bars:
                result.append(BarData(
                    broker_id=self.broker_id,
                    instrument=instrument,
                    timeframe=timeframe,
                    open_time=datetime.fromtimestamp(bar["time"]),
                    close_time=datetime.fromtimestamp(bar["time"] + self._get_timeframe_seconds(timeframe)),
                    open=float(bar["open"]),
                    high=float(bar["high"]),
                    low=float(bar["low"]),
                    close=float(bar["close"]),
                    volume=float(bar["tick_volume"]),
                    tick_volume=float(bar["spread"]) if "spread" in bar else 0.0
                ))
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get bars for {instrument} {timeframe}: {e}")
            raise MarketDataError(f"Failed to get bars: {e}")
    
    def _convert_timeframe(self, timeframe: str) -> int:
        """
        Convert timeframe string to MT5 timeframe constant.
        
        Args:
            timeframe: Timeframe string (M1, M5, H1, etc.)
            
        Returns:
            MT5 timeframe constant
        """
        timeframes = {
            "M1": 1,
            "M2": 2,
            "M3": 3,
            "M4": 4,
            "M5": 5,
            "M6": 6,
            "M10": 10,
            "M12": 12,
            "M15": 15,
            "M20": 20,
            "M30": 30,
            "H1": 60,
            "H2": 120,
            "H3": 180,
            "H4": 240,
            "H6": 360,
            "H8": 480,
            "H12": 720,
            "D1": 1440,
            "W1": 10080,
            "MN1": 43200,
        }
        
        return timeframes.get(timeframe.upper(), 60)  # Default to H1
    
    def _get_timeframe_seconds(self, timeframe: str) -> int:
        """
        Get timeframe duration in seconds.
        
        Args:
            timeframe: Timeframe string
            
        Returns:
            Duration in seconds
        """
        if timeframe.upper().endswith("M"):
            minutes = int(timeframe.upper()[:-1])
            return minutes * 60
        elif timeframe.upper().endswith("H"):
            hours = int(timeframe.upper()[:-1])
            return hours * 3600
        elif timeframe.upper() == "D1":
            return 86400
        elif timeframe.upper() == "W1":
            return 604800
        elif timeframe.upper() == "MN1":
            return 2592000
        return 60  # Default to 1 minute
    
    def get_open_positions(self) -> List[Position]:
        """
        Get all open positions.
        
        Returns:
            List of Position objects
        """
        if not self._reconnect_if_needed():
            raise ConnectionError("Not connected to broker")
        
        try:
            positions = self._mt5.positions_get()
            if positions is None:
                return []
            
            result = []
            for pos in positions:
                # Get current price
                bid, ask = self.get_bid_ask(pos.symbol)
                current_price = (bid + ask) / 2
                
                result.append(Position(
                    position_id=str(pos.ticket),
                    broker_id=self.broker_id,
                    account_id=str(pos.login),
                    instrument=pos.symbol,
                    side=PositionSide.BUY if pos.type == 0 else PositionSide.SELL,
                    volume=float(pos.volume),
                    open_price=float(pos.price),
                    open_time=datetime.fromtimestamp(pos.time),
                    current_price=current_price,
                    stop_loss=float(pos.sl) if pos.sl != 0 else None,
                    take_profit=float(pos.tp) if pos.tp != 0 else None,
                    commission=float(pos.commission),
                    swap=float(pos.swap),
                    profit=float(pos.profit),
                    magic_number=int(pos.magic) if pos.magic != 0 else None,
                    comment=pos.comment
                ))
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get open positions: {e}")
            raise PositionError(f"Failed to get positions: {e}")
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """
        Get a specific position by ID.
        
        Args:
            position_id: Position ID
            
        Returns:
            Position object or None
        """
        positions = self.get_open_positions()
        for pos in positions:
            if pos.position_id == position_id:
                return pos
        return None
    
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
        if not self._reconnect_if_needed():
            raise ConnectionError("Not connected to broker")
        
        # Map instrument to broker symbol
        broker_symbol = self.map_instrument(instrument)
        
        # Convert order type and side to MT5 constants
        mt5_order_type = self._convert_order_type(order_type)
        mt5_side = self._convert_order_side(side)
        
        try:
            # Prepare request
            request = {
                "action": self._mt5.TRADE_ACTION_DEAL,
                "symbol": broker_symbol,
                "volume": volume,
                "type": mt5_order_type,
                "price": price if price else 0,
                "sl": stop_loss if stop_loss else 0,
                "tp": take_profit if take_profit else 0,
                "deviation": 10,  # Max slippage in points
                "magic": magic_number if magic_number else 0,
                "comment": comment if comment else "",
                "type_filling": self._mt5.ORDER_FILLING_FOK,
                "type_time": self._mt5.ORDER_TIME_GTC,
            }
            
            # For market orders
            if order_type == OrderType.MARKET:
                request["type"] = mt5_order_type
                
            # Send order
            result = self._mt5.order_send(request)
            
            if result is None:
                error_code = self._mt5.last_error()
                error_msg = f"Order send failed with code {error_code}"
                logger.error(error_msg)
                raise OrderError(error_msg)
            
            # Check if order was accepted
            if result.retcode != self._mt5.TRADE_RETCODE_DONE:
                error_msg = f"Order not accepted: {result.comment}"
                logger.error(error_msg)
                raise OrderError(error_msg)
            
            # Create Order object
            order = Order(
                order_id=str(result.order),
                broker_id=self.broker_id,
                account_id=str(result.login),
                instrument=instrument,
                order_type=order_type,
                side=side,
                volume=volume,
                price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                status=OrderStatus.FILLED if result.retcode == self._mt5.TRADE_RETCODE_DONE else OrderStatus.PENDING,
                timestamp=datetime.utcnow(),
                filled_volume=float(result.volume),
                filled_price=float(result.price),
                commission=float(result.commission),
                swap=0.0,
                slippage=float(result.price - (price if price else 0)) if price else 0.0,
                comment=comment,
                magic_number=magic_number
            )
            
            logger.info(f"Order sent: {order.order_id}, {side.value} {volume} {instrument} @ {order.filled_price}")
            return order
            
        except Exception as e:
            logger.error(f"Failed to send order: {e}")
            raise OrderError(f"Order failed: {e}")
    
    def _convert_order_type(self, order_type: OrderType) -> int:
        """
        Convert OrderType to MT5 order type constant.
        
        Args:
            order_type: OrderType enum
            
        Returns:
            MT5 order type constant
        """
        mt5 = self._import_mt5()
        if mt5 is None:
            return 0
        
        types = {
            OrderType.MARKET: mt5.ORDER_TYPE_BUY if False else mt5.ORDER_TYPE_SELL,  # Will be set by side
            OrderType.LIMIT: mt5.ORDER_TYPE_BUY_LIMIT if False else mt5.ORDER_TYPE_SELL_LIMIT,
            OrderType.STOP: mt5.ORDER_TYPE_BUY_STOP if False else mt5.ORDER_TYPE_SELL_STOP,
            OrderType.STOP_LIMIT: mt5.ORDER_TYPE_BUY_STOP_LIMIT if False else mt5.ORDER_TYPE_SELL_STOP_LIMIT,
        }
        
        return types.get(order_type, mt5.ORDER_TYPE_BUY)
    
    def _convert_order_side(self, side: OrderSide) -> int:
        """
        Convert OrderSide to MT5 order type modifier.
        
        Args:
            side: OrderSide enum
            
        Returns:
            MT5 order type (BUY or SELL)
        """
        mt5 = self._import_mt5()
        if mt5 is None:
            return 0
        
        if side == OrderSide.BUY:
            return mt5.ORDER_TYPE_BUY
        else:
            return mt5.ORDER_TYPE_SELL
    
    def close_position(self, position_id: str, volume: Optional[float] = None) -> bool:
        """
        Close a position.
        
        Args:
            position_id: Position ID
            volume: Volume to close (None = close all)
            
        Returns:
            True if position closed successfully
        """
        if not self._reconnect_if_needed():
            raise ConnectionError("Not connected to broker")
        
        # Get position
        position = self.get_position(position_id)
        if position is None:
            raise PositionError(f"Position {position_id} not found")
        
        # Determine close side (opposite of position side)
        close_side = OrderSide.SELL if position.side == PositionSide.BUY else OrderSide.BUY
        close_volume = volume if volume else position.volume
        
        # Close with opposite order
        try:
            order = self.send_order(
                instrument=position.instrument,
                side=close_side,
                volume=close_volume,
                order_type=OrderType.MARKET,
                comment=f"Close position {position_id}",
                magic_number=position.magic_number
            )
            
            logger.info(f"Position {position_id} closed with order {order.order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to close position {position_id}: {e}")
            raise PositionError(f"Failed to close position: {e}")
    
    def modify_order(
        self,
        order_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> bool:
        """
        Modify an existing order.
        
        Args:
            order_id: Order ID
            stop_loss: New stop loss price
            take_profit: New take profit price
            
        Returns:
            True if order modified successfully
        """
        if not self._reconnect_if_needed():
            raise ConnectionError("Not connected to broker")
        
        try:
            # Get order
            order = self.get_order(order_id)
            if order is None:
                raise OrderError(f"Order {order_id} not found")
            
            # Prepare modification request
            request = {
                "action": self._mt5.TRADE_ACTION_SLTP,
                "position": int(order_id),
                "symbol": order.instrument,
                "sl": stop_loss if stop_loss else 0,
                "tp": take_profit if take_profit else 0,
            }
            
            result = self._mt5.order_send(request)
            
            if result is None:
                error_code = self._mt5.last_error()
                error_msg = f"Order modification failed with code {error_code}"
                logger.error(error_msg)
                raise OrderError(error_msg)
            
            if result.retcode != self._mt5.TRADE_RETCODE_DONE:
                error_msg = f"Order modification not accepted: {result.comment}"
                logger.error(error_msg)
                raise OrderError(error_msg)
            
            logger.info(f"Order {order_id} modified: SL={stop_loss}, TP={take_profit}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to modify order {order_id}: {e}")
            raise OrderError(f"Order modification failed: {e}")
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID
            
        Returns:
            True if order cancelled successfully
        """
        if not self._reconnect_if_needed():
            raise ConnectionError("Not connected to broker")
        
        try:
            request = {
                "action": self._mt5.TRADE_ACTION_REMOVE,
                "order": int(order_id),
            }
            
            result = self._mt5.order_send(request)
            
            if result is None:
                error_code = self._mt5.last_error()
                error_msg = f"Order cancellation failed with code {error_code}"
                logger.error(error_msg)
                raise OrderError(error_msg)
            
            if result.retcode != self._mt5.TRADE_RETCODE_DONE:
                error_msg = f"Order cancellation not accepted: {result.comment}"
                logger.error(error_msg)
                raise OrderError(error_msg)
            
            logger.info(f"Order {order_id} cancelled")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            raise OrderError(f"Order cancellation failed: {e}")
    
    def get_open_orders(self) -> List[Order]:
        """
        Get all open orders.
        
        Returns:
            List of Order objects
        """
        if not self._reconnect_if_needed():
            raise ConnectionError("Not connected to broker")
        
        try:
            orders = self._mt5.orders_get()
            if orders is None:
                return []
            
            result = []
            for order_data in orders:
                result.append(Order(
                    order_id=str(order_data.ticket),
                    broker_id=self.broker_id,
                    account_id=str(order_data.login),
                    instrument=order_data.symbol,
                    order_type=self._convert_mt5_order_type(order_data.type),
                    side=self._convert_mt5_order_side(order_data.type),
                    volume=float(order_data.volume),
                    price=float(order_data.price),
                    stop_loss=float(order_data.sl) if order_data.sl != 0 else None,
                    take_profit=float(order_data.tp) if order_data.tp != 0 else None,
                    status=self._convert_mt5_order_status(order_data.state),
                    timestamp=datetime.fromtimestamp(order_data.time_setup),
                    filled_volume=float(order_data.volume_current),
                    filled_price=float(order_data.price_current),
                    commission=0.0,
                    swap=0.0,
                    slippage=0.0,
                    comment=order_data.comment,
                    magic_number=int(order_data.magic) if order_data.magic != 0 else None
                ))
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            raise OrderError(f"Failed to get orders: {e}")
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get a specific order by ID.
        
        Args:
            order_id: Order ID
            
        Returns:
            Order object or None
        """
        orders = self.get_open_orders()
        for order in orders:
            if order.order_id == order_id:
                return order
        return None
    
    def _convert_mt5_order_type(self, mt5_type: int) -> OrderType:
        """
        Convert MT5 order type to OrderType enum.
        
        Args:
            mt5_type: MT5 order type constant
            
        Returns:
            OrderType enum
        """
        if mt5_type in [0, 2, 4, 6]:  # BUY types
            if mt5_type == 2:
                return OrderType.LIMIT
            elif mt5_type == 4:
                return OrderType.STOP
            elif mt5_type == 6:
                return OrderType.STOP_LIMIT
            else:
                return OrderType.MARKET
        else:  # SELL types
            if mt5_type == 3:
                return OrderType.LIMIT
            elif mt5_type == 5:
                return OrderType.STOP
            elif mt5_type == 7:
                return OrderType.STOP_LIMIT
            else:
                return OrderType.MARKET
    
    def _convert_mt5_order_side(self, mt5_type: int) -> OrderSide:
        """
        Convert MT5 order type to OrderSide enum.
        
        Args:
            mt5_type: MT5 order type constant
            
        Returns:
            OrderSide enum
        """
        if mt5_type in [0, 2, 4, 6]:  # BUY types
            return OrderSide.BUY
        else:  # SELL types
            return OrderSide.SELL
    
    def _convert_mt5_order_status(self, mt5_state: int) -> OrderStatus:
        """
        Convert MT5 order state to OrderStatus enum.
        
        Args:
            mt5_state: MT5 order state constant
            
        Returns:
            OrderStatus enum
        """
        status_map = {
            0: OrderStatus.PENDING,
            1: OrderStatus.FILLED,
            2: OrderStatus.PARTIAL,
            3: OrderStatus.CANCELLED,
            4: OrderStatus.REJECTED,
            5: OrderStatus.EXPIRED,
        }
        return status_map.get(mt5_state, OrderStatus.PENDING)
    
    # Async methods
    async def connect_async(self) -> bool:
        """
        Connect asynchronously (runs in executor).
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.connect)
    
    async def get_tick_async(self, instrument: str) -> TickData:
        """
        Get tick data asynchronously.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_tick, instrument)
    
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
        Send order asynchronously.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.send_order,
            instrument,
            side,
            volume,
            order_type,
            price,
            stop_loss,
            take_profit,
            comment,
            magic_number
        )
    
    # IB Rebate methods
    def is_eligible_for_rebate(self, instrument: str, volume: float) -> bool:
        """
        Check if a trade is eligible for IB rebate.
        
        Args:
            instrument: Instrument symbol
            volume: Trade volume in lots
            
        Returns:
            True if eligible
        """
        eligible_instruments = self.ib_rebate_config.get("eligible_instruments", [])
        if instrument not in eligible_instruments:
            return False
        
        min_lot = self.ib_rebate_config.get("min_lot_size", 0.01)
        if volume < min_lot:
            return False
        
        return True
    
    def calculate_rebate(self, instrument: str, volume: float, holding_time_minutes: float) -> float:
        """
        Calculate IB rebate for a trade.
        
        Args:
            instrument: Instrument symbol
            volume: Trade volume in standard lots
            holding_time_minutes: Time position was held
            
        Returns:
            Rebate amount in USD
        """
        if not self.is_eligible_for_rebate(instrument, volume):
            return 0.0
        
        min_holding_time = self.ib_rebate_config.get("min_holding_time_minutes", 5)
        if holding_time_minutes < min_holding_time:
            return 0.0
        
        rebate_per_lot = self.ib_rebate_config.get("rebate_per_standard_lot", 0.0)
        return volume * rebate_per_lot
