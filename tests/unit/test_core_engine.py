"""
Unit Tests - Core Trading Logic
===============================
Tests the core engine independent of execution mode.
These tests validate that all modes (backtest, paper, live)
use the same correct logic.

Run with: pytest tests/unit/test_core_engine.py
"""

import pytest
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

# Add src to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from src.core import (
    Order, Position, Trade, DailyPnL, ScreenerSignal,
    TradeParameters, CapitalParameters, OrderSide, OrderStatus,
    StateManager, CapitalManager, PositionManager, TradingEngine
)


class TestModels:
    """Test data models"""
    
    def test_order_creation(self):
        """Test Order model"""
        order = Order(
            order_id="TEST1",
            symbol="SBIN",
            side=OrderSide.BUY,
            req_qty=100,
            price=500.0,
            created_at=datetime.now()
        )
        
        assert order.symbol == "SBIN"
        assert order.side == OrderSide.BUY
        assert not order.is_filled()
        assert order.fill_ratio() == 0.0
    
    def test_position_creation(self):
        """Test Position model"""
        pos = Position(
            symbol="SBIN",
            side=OrderSide.BUY,
            entry_price=500.0,
            quantity=100,
            qty_remaining=100,
            atr=20.0,
            stop_loss=480.0,
            target=540.0,
            entry_time=datetime.now()
        )
        
        assert pos.symbol == "SBIN"
        assert pos.is_open()
        assert pos.qty_closed() == 0


class TestStateManager:
    """Test state persistence"""
    
    def test_state_manager_init(self):
        """Test state manager initialization"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StateManager(tmpdir)
            assert os.path.exists(tmpdir)
            assert os.path.exists(f"{tmpdir}/backups")
    
    def test_save_and_load_positions(self):
        """Test saving and loading positions"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StateManager(tmpdir)
            
            position = {
                'symbol': 'SBIN',
                'entry_price': 500.0,
                'quantity': 100,
                'qty_remaining': 100,
                'stop_loss': 480.0,
                'atr': 20.0
            }
            
            mgr.add_position('SBIN', position)
            loaded = mgr.get_position('SBIN')
            
            assert loaded is not None
            assert loaded['symbol'] == 'SBIN'
            assert loaded['entry_price'] == 500.0
    
    def test_order_management(self):
        """Test order save/load"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StateManager(tmpdir)
            
            order = {
                'symbol': 'SBIN',
                'side': 'BUY',
                'req_qty': 100,
                'price': 500.0,
                'status': 'PENDING',
                'filled_qty': 0
            }
            
            mgr.add_order('ORD1', order)
            mgr.update_order_status('ORD1', 'FILLED', 100)
            
            orders = mgr.load_orders()
            assert orders['ORD1']['status'] == 'FILLED'
            assert orders['ORD1']['filled_qty'] == 100


class TestCapitalManager:
    """Test capital management"""
    
    def test_position_exposure(self):
        """Test position exposure calculation"""
        params = CapitalParameters(total_capital=10000)
        mgr = CapitalManager(params)
        
        positions = {
            'SBIN': {
                'entry_price': 500.0,
                'qty_remaining': 100
            },
            'INFY': {
                'entry_price': 1000.0,
                'qty_remaining': 50
            }
        }
        
        exposure = mgr._calculate_position_exposure(positions)
        assert exposure == 500*100 + 1000*50  # 50,000 + 50,000 = 100,000
    
    def test_available_capital(self):
        """Test available capital calculation"""
        params = CapitalParameters(
            total_capital=100000,
            safety_buffer_pct=0.15
        )
        mgr = CapitalManager(params)
        
        positions = {
            'SBIN': {
                'entry_price': 500.0,
                'qty_remaining': 100  # 50,000
            }
        }
        
        pending = {}
        
        available = mgr.calculate_available_capital(positions, pending)
        # 100,000 - 50,000 - 15,000 (buffer) = 35,000
        assert available == 35000
    
    def test_position_size_calculation(self):
        """Test position sizing based on risk"""
        params = CapitalParameters(
            total_capital=10000,
            risk_per_trade=0.01  # 1%
        )
        mgr = CapitalManager(params)
        
        entry = 100.0
        sl = 95.0  # 5 risk
        
        qty = mgr.calculate_position_size(entry, sl)
        # Risk = 10,000 * 0.01 = 100
        # Qty = 100 / (100 - 95) = 100 / 5 = 20
        assert qty == 20
    
    def test_daily_loss_limit(self):
        """Test daily loss limit check"""
        params = CapitalParameters(
            total_capital=10000,
            max_daily_loss_pct=0.02  # 2%
        )
        mgr = CapitalManager(params)
        
        # Loss within limit
        within, msg = mgr.check_daily_loss_limit(-150)  # 1.5%
        assert within is True
        
        # Loss exceeds limit
        within, msg = mgr.check_daily_loss_limit(-250)  # 2.5%
        assert within is False


class TestPositionManager:
    """Test position management"""
    
    def test_sl_and_target_calculation(self):
        """Test SL and target calculation"""
        entry = 100.0
        atr = 5.0
        
        sl, target = PositionManager.calculate_sl_and_target(
            entry_price=entry,
            atr=atr,
            sl_mult=1.5,
            target_mult=2.0,
            side=OrderSide.BUY
        )
        
        assert sl == 100.0 - (5.0 * 1.5)  # 92.5
        assert target == 100.0 + (5.0 * 2.0)  # 110.0
    
    def test_check_stop_loss_hit(self):
        """Test SL hit detection"""
        position = {
            'symbol': 'SBIN',
            'side': OrderSide.BUY,
            'stop_loss': 95.0,
            'entry_price': 100.0,
            'qty_remaining': 100,
            'atr': 5.0
        }
        
        # Price above SL
        assert not PositionManager.check_stop_loss_hit(position, 100.0)
        
        # Price at SL
        assert PositionManager.check_stop_loss_hit(position, 95.0)
        
        # Price below SL
        assert PositionManager.check_stop_loss_hit(position, 90.0)
    
    def test_unrealized_pnl(self):
        """Test unrealized P&L calculation"""
        position = {
            'symbol': 'SBIN',
            'side': OrderSide.BUY,
            'entry_price': 100.0,
            'qty_remaining': 100
        }
        
        # Price up 5%
        pnl = PositionManager.calculate_unrealized_pnl(position, 105.0)
        assert pnl == 500.0  # 5 * 100
        
        # Price down 5%
        pnl = PositionManager.calculate_unrealized_pnl(position, 95.0)
        assert pnl == -500.0


class TestTradingEngine:
    """Test core trading engine"""
    
    def setup_method(self):
        """Setup for each test"""
        self.tmpdir = tempfile.mkdtemp()
        self.capital_params = CapitalParameters(
            total_capital=100000,
            risk_per_trade=0.01
        )
        self.trade_params = TradeParameters()
        self.state = StateManager(self.tmpdir)
        self.engine = TradingEngine(self.capital_params, self.trade_params, self.state)
    
    def test_process_signal(self):
        """Test signal processing"""
        signal = ScreenerSignal(
            symbol='SBIN',
            score=8.5,
            atr=20.0,
            adx=28.0,
            volume_ratio=1.5,
            trend='BULLISH',
            price=500.0,
            sector='FINANCIALS',
            timestamp=datetime.now()
        )
        
        success, order, reason = self.engine.process_signal(signal)
        
        assert success is True
        assert order is not None
        assert order.symbol == 'SBIN'
        assert order.side == OrderSide.BUY
    
    def test_cannot_open_same_position_twice(self):
        """Test preventing duplicate positions"""
        signal = ScreenerSignal(
            symbol='SBIN',
            score=8.5,
            atr=20.0,
            adx=28.0,
            volume_ratio=1.5,
            trend='BULLISH',
            price=500.0,
            sector='FINANCIALS',
            timestamp=datetime.now()
        )
        
        # First signal succeeds
        success1, _, _ = self.engine.process_signal(signal)
        assert success1 is True
        
        # Add position to state
        position = {
            'symbol': 'SBIN',
            'entry_price': 500.0,
            'quantity': 100,
            'qty_remaining': 100,
            'stop_loss': 480.0,
            'atr': 20.0
        }
        self.state.add_position('SBIN', position)
        
        # Second signal fails
        success2, _, reason = self.engine.process_signal(signal)
        assert success2 is False
        assert 'Already in position' in reason
    
    def cleanup_method(self):
        """Cleanup after each test"""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
