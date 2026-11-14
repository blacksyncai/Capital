"""
Simple Execution Tests

Focused tests for the most critical execution functionality.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from src.tests.test_broker_simulator import (
    SimulatedBroker,
    create_simulated_broker,
    create_vantage_simulator,
    create_justmarkets_simulator,
    Order,
    OrderSide,
    OrderStatus,
    Position,
    PositionSide,
    PositionStatus,
)


class TestSimulatedBroker:
    """Test the simulated broker implementation."""
    
    def test_connect_and_disconnect(self):
        """Test connecting and disconnecting."""
        broker = create_simulated_broker("test", initial_balance=10000.0)
        
        assert broker.is_connected() is False
        assert broker.connect() is True
        assert broker.is_connected() is True
        
        broker.disconnect()
        assert broker.is_connected() is False
    
    def test_place_buy_order(self):
        """Test placing a BUY order."""
        broker = create_simulated_broker("vantage", initial_balance=10000.0)
        broker.connect()
        
        order = broker.place_order(
            instrument="XAUUSD",
            side=OrderSide.BUY,
            volume=0.01,
        )
        
        assert order.status == OrderStatus.FILLED
        assert order.side == OrderSide.BUY
        assert order.volume == 0.01
        assert order.instrument == "XAUUSD"
        assert order.filled_volume == 0.01
    
    def test_place_sell_order(self):
        """Test placing a SELL order."""
        broker = create_simulated_broker("justmarkets", initial_balance=10000.0)
        broker.connect()
        
        order = broker.place_order(
            instrument="XAUUSD",
            side=OrderSide.SELL,
            volume=0.01,
        )
        
        assert order.status == OrderStatus.FILLED
        assert order.side == OrderSide.SELL
        assert order.volume == 0.01
    
    def test_position_created_on_order(self):
        """Test that a position is created when placing a market order."""
        broker = create_simulated_broker("vantage", initial_balance=10000.0)
        broker.connect()
        
        order = broker.place_order(
            instrument="XAUUSD",
            side=OrderSide.BUY,
            volume=0.01,
        )
        
        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0].side == PositionSide.BUY
        assert positions[0].volume == 0.01
        assert positions[0].instrument == "XAUUSD"
    
    def test_close_position(self):
        """Test closing a position."""
        broker = create_simulated_broker("vantage", initial_balance=10000.0)
        broker.connect()
        
        # Open a position
        order = broker.place_order(
            instrument="XAUUSD",
            side=OrderSide.BUY,
            volume=0.01,
        )
        
        positions = broker.get_positions()
        position_id = positions[0].position_id
        
        # Close the position
        close_order = broker.close_position(position_id)
        
        assert close_order.status == OrderStatus.FILLED
        assert len(broker.get_positions()) == 0
    
    def test_paired_orders_opposite_sides(self):
        """Test placing paired orders with opposite sides."""
        vantage = create_simulated_broker("vantage", initial_balance=10000.0)
        justmarkets = create_simulated_broker("justmarkets", initial_balance=10000.0)
        
        vantage.connect()
        justmarkets.connect()
        
        # Place BUY on vantage
        vantage_order = vantage.place_order(
            instrument="XAUUSD",
            side=OrderSide.BUY,
            volume=0.01,
        )
        
        # Place SELL on justmarkets
        justmarkets_order = justmarkets.place_order(
            instrument="XAUUSD",
            side=OrderSide.SELL,
            volume=0.01,
        )
        
        assert vantage_order.side == OrderSide.BUY
        assert justmarkets_order.side == OrderSide.SELL
        
        # Check positions
        vantage_positions = vantage.get_positions()
        justmarkets_positions = justmarkets.get_positions()
        
        assert len(vantage_positions) == 1
        assert len(justmarkets_positions) == 1
        assert vantage_positions[0].side == PositionSide.BUY
        assert justmarkets_positions[0].side == PositionSide.SELL
    
    def test_get_bid_ask(self):
        """Test getting bid/ask prices."""
        broker = create_simulated_broker("vantage")
        broker.connect()
        
        bid, ask = broker.get_bid_ask("XAUUSD")
        
        assert bid < ask
        assert ask - bid > 0
    
    def test_get_tick(self):
        """Test getting tick data."""
        broker = create_simulated_broker("vantage")
        broker.connect()
        
        tick = broker.get_tick("XAUUSD")
        
        assert tick.instrument == "XAUUSD"
        assert tick.broker_id == "vantage"
        assert tick.spread > 0
        assert tick.mid > 0
    
    def test_set_price(self):
        """Test setting price for testing."""
        broker = create_simulated_broker("vantage")
        broker.connect()
        
        broker.set_price("XAUUSD", 2500.0)
        
        bid, ask = broker.get_bid_ask("XAUUSD")
        assert bid > 2499
        assert ask > 2499
    
    def test_account_balance_updated_on_close(self):
        """Test that account balance is updated when closing positions."""
        broker = create_simulated_broker("vantage", initial_balance=10000.0)
        broker.connect()
        
        initial_balance = broker.get_balance()
        
        # Open position at 2000
        broker.set_price("XAUUSD", 2000.0)
        order = broker.place_order(
            instrument="XAUUSD",
            side=OrderSide.BUY,
            volume=0.01,
        )
        
        # Close position at 2010 (profit of $10 * 100 ounces = $1000)
        broker.set_price("XAUUSD", 2010.0)
        positions = broker.get_positions()
        broker.close_position(positions[0].position_id)
        
        # Check balance increased
        new_balance = broker.get_balance()
        assert new_balance > initial_balance
    
    def test_reject_orders_mode(self):
        """Test that orders can be rejected."""
        broker = create_simulated_broker("vantage", initial_balance=10000.0)
        broker.connect()
        broker.reject_orders = True
        
        with pytest.raises(Exception, match="rejected"):
            broker.place_order(
                instrument="XAUUSD",
                side=OrderSide.BUY,
                volume=0.01,
            )
    
    def test_contract_spec(self):
        """Test getting contract specifications."""
        broker = create_simulated_broker("vantage")
        broker.connect()
        
        spec = broker.get_contract_spec("XAUUSD")
        
        assert spec is not None
        assert spec.instrument == "XAUUSD"
        assert spec.contract_size == 100
        assert spec.tick_value == 0.01


class TestPairedTradeEndToEnd:
    """Test complete paired trade cycles."""
    
    def test_complete_paired_cycle(self):
        """Test a complete paired trade cycle: open and close."""
        vantage = create_vantage_simulator(initial_balance=10000.0)
        justmarkets = create_justmarkets_simulator(initial_balance=10000.0)
        
        vantage.connect()
        justmarkets.connect()
        
        # Set initial price
        vantage.set_price("XAUUSD", 2000.0)
        justmarkets.set_price("XAUUSD", 2000.0)
        
        # Open paired positions
        vantage_order = vantage.place_order(
            instrument="XAUUSD",
            side=OrderSide.BUY,
            volume=0.01,
            comment="Paired trade - Vantage",
        )
        
        justmarkets_order = justmarkets.place_order(
            instrument="XAUUSD",
            side=OrderSide.SELL,
            volume=0.01,
            comment="Paired trade - JustMarkets",
        )
        
        assert vantage_order.status == OrderStatus.FILLED
        assert justmarkets_order.status == OrderStatus.FILLED
        
        # Verify positions
        vantage_positions = vantage.get_positions()
        justmarkets_positions = justmarkets.get_positions()
        
        assert len(vantage_positions) == 1
        assert len(justmarkets_positions) == 1
        assert vantage_positions[0].side == PositionSide.BUY
        assert justmarkets_positions[0].side == PositionSide.SELL
        
        # Set new price for closing
        vantage.set_price("XAUUSD", 2005.0)
        justmarkets.set_price("XAUUSD", 2005.0)
        
        # Close positions
        vantage_close = vantage.close_position(vantage_positions[0].position_id)
        justmarkets_close = justmarkets.close_position(justmarkets_positions[0].position_id)
        
        assert vantage_close.status == OrderStatus.FILLED
        assert justmarkets_close.status == OrderStatus.FILLED
        
        # Verify all positions closed
        assert len(vantage.get_positions()) == 0
        assert len(justmarkets.get_positions()) == 0
        
        # Check that balance changed
        # Vantage: BUY at 2000, SELL at 2005 = profit
        # JustMarkets: SELL at 2000, BUY at 2005 = loss
        vantage_balance = vantage.get_balance()
        justmarkets_balance = justmarkets.get_balance()
        
        # The net should be zero (one gains, one loses)
        # But we need to check the actual P&L
        assert vantage_balance != 10000.0 or justmarkets_balance != 10000.0


class TestMultipleInstruments:
    """Test trading multiple instruments."""
    
    def test_trade_multiple_instruments(self):
        """Test trading different instruments."""
        broker = create_simulated_broker("vantage", initial_balance=10000.0)
        broker.connect()
        
        # Trade XAUUSD
        broker.place_order("XAUUSD", OrderSide.BUY, 0.01)
        
        # Trade BTCUSD
        broker.place_order("BTCUSD", OrderSide.BUY, 0.01)
        
        positions = broker.get_positions()
        assert len(positions) == 2
        
        instruments = {p.instrument for p in positions}
        assert "XAUUSD" in instruments
        assert "BTCUSD" in instruments


class TestMarginCalculation:
    """Test margin calculations."""
    
    def test_margin_used_on_open(self):
        """Test that margin is used when opening positions."""
        broker = create_simulated_broker("vantage", initial_balance=10000.0)
        broker.connect()
        
        initial_free_margin = broker.get_free_margin()
        
        # Open position
        broker.place_order("XAUUSD", OrderSide.BUY, 0.01)
        
        new_free_margin = broker.get_free_margin()
        
        # Free margin should decrease
        assert new_free_margin < initial_free_margin
        assert broker.get_margin_used() > 0
    
    def test_margin_released_on_close(self):
        """Test that margin is released when closing positions."""
        broker = create_simulated_broker("vantage", initial_balance=10000.0)
        broker.connect()
        
        # Open position
        broker.place_order("XAUUSD", OrderSide.BUY, 0.01)
        margin_used = broker.get_margin_used()
        
        # Close position
        positions = broker.get_positions()
        broker.close_position(positions[0].position_id)
        
        # Margin should be released
        assert broker.get_margin_used() < margin_used


class TestSpreadHandling:
    """Test spread handling."""
    
    def test_get_spread(self):
        """Test getting spread."""
        broker = create_simulated_broker("vantage")
        broker.connect()
        
        spread = broker.get_spread("XAUUSD")
        assert spread > 0
    
    def test_set_spread(self):
        """Test setting spread."""
        broker = create_simulated_broker("vantage")
        broker.connect()
        
        broker.set_spread("XAUUSD", 2.0)
        
        bid, ask = broker.get_bid_ask("XAUUSD")
        assert ask - bid == 2.0


class TestLotSizeValidation:
    """Test lot size validation."""
    
    def test_valid_lot_sizes(self):
        """Test valid lot sizes."""
        broker = create_simulated_broker("vantage")
        broker.connect()
        
        # These should all be valid
        assert broker.validate_lot_size(0.01) is True
        assert broker.validate_lot_size(0.05) is True
        assert broker.validate_lot_size(0.10) is True
        assert broker.validate_lot_size(1.0) is True
    
    def test_invalid_lot_sizes(self):
        """Test invalid lot sizes."""
        broker = create_simulated_broker("vantage")
        broker.connect()
        
        # These should be invalid
        assert broker.validate_lot_size(0.001) is False
        assert broker.validate_lot_size(101.0) is False
