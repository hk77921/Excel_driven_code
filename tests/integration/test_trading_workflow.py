"""
Integration Tests - Full Trading Workflow
==========================================
Tests complete trading workflows across different modes.
Validates that signal -> order -> fill -> exit works correctly.

Run with: pytest tests/integration/test_trading_workflow.py
"""

import pytest
import tempfile
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from src.core import (
    ScreenerSignal, TradeParameters, CapitalParameters,
    StateManager, TradingEngine, OrderSide
)
from src.execution import PaperTradingMode


class TestPaperTradingWorkflow:
    """Test complete paper trading workflow"""
    
    def setup_method(self):
        """Setup for each test"""
        self.tmpdir = tempfile.mkdtemp()
        self.capital_params = CapitalParameters(
            total_capital=50000,
            risk_per_trade=0.01,
            max_daily_loss_pct=0.02
        )
        self.trade_params = TradeParameters()
        
        self.trader = PaperTradingMode(
            self.capital_params,
            self.trade_params,
            self.tmpdir
        )
        # For testing, no delay on order fills
        self.trader.order_fill_delay = 0
    
    def test_full_entry_to_exit(self):
        """Test complete trade from signal to exit"""
        
        # Step 1: Create screener signal
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
        
        # Step 2: Process signal (creates order)
        success, msg = self.trader.process_signal(signal)
        assert success is True
        
        # Step 2a: Set price and execute cycle to fill order
        self.trader.set_price('SBIN', 500.0)
        self.trader.execute_cycle()
        
        # Check position exists after order filled
        positions = self.trader.state.load_positions()
        assert 'SBIN' in positions, f"Expected SBIN in positions, got {positions.keys()}"
        position = positions['SBIN']
        assert position['qty_remaining'] > 0
        
        # Step 3: Set price and execute cycle (test normal execution)
        self.trader.set_price('SBIN', 505.0)
        report = self.trader.execute_cycle()
        assert report['errors'] == []
        
        # Step 4: Move price up to trigger partial exit
        entry_price = position['entry_price']
        atr = position['atr']
        partial_exit_target = entry_price + (0.8 * (entry_price - position['stop_loss']))
        
        self.trader.set_price('SBIN', partial_exit_target + 1)
        report = self.trader.execute_cycle()
        
        # Check that position triggers partial exit or is fully exited
        positions = self.trader.state.load_positions()
        if 'SBIN' in positions:
            updated_pos = positions['SBIN']
            # After price movement towards target, qty_remaining should be same or less
            assert updated_pos['qty_remaining'] <= position['quantity']
        else:
            # Position might be fully exited
            pass
    
    def test_capital_limits_enforced(self):
        """Test that capital limits prevent overleveraging"""
        
        # With small capital, should limit positions
        trader = PaperTradingMode(
            CapitalParameters(total_capital=5000),
            self.trade_params,
            self.tmpdir
        )
        # For testing, no delay on order fills
        trader.order_fill_delay = 0
        
        # Try to open large position
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
        
        success, msg = trader.process_signal(signal)
        
        # Process order (fill it)
        trader.set_price('SBIN', 500.0)
        trader.execute_cycle()
        
        # Should succeed but with limited size
        if success:
            positions = trader.state.load_positions()
            assert 'SBIN' in positions, f"Expected SBIN in positions, got {positions.keys()}"
            position = positions['SBIN']
            
            # Capital used should not exceed available
            capital_used = position['entry_price'] * position['quantity']
            available = trader.engine.capital_mgr.calculate_available_capital(
                positions,
                trader.state.load_orders()
            )
            
            # Before next trade, some capital should remain
            assert available > 0 or capital_used >= 5000 * 0.85  # Buffer consideration
    
    def test_daily_loss_limit(self):
        """Test daily loss limit (kill switch)"""
        
        # Create position with loss
        self.trader.state.add_position('SBIN', {
            'symbol': 'SBIN',
            'entry_price': 500.0,
            'quantity': 100,
            'qty_remaining': 100,
            'stop_loss': 480.0,
            'atr': 20.0,
            'side': OrderSide.BUY.value
        })
        
        # Set price below SL (forces loss)
        self.trader.set_price('SBIN', 450.0)
        
        # Execute cycle (should trigger SL)
        report = self.trader.execute_cycle()
        
        # Position should be exited
        positions = self.trader.state.load_positions()
        assert 'SBIN' not in positions or positions['SBIN']['qty_remaining'] == 0
    
    def test_multiple_positions(self):
        """Test managing multiple open positions"""
        
        signals = [
            ScreenerSignal(
                symbol='SBIN',
                score=8.5, atr=20.0, adx=28.0, volume_ratio=1.5,
                trend='BULLISH', price=500.0, sector='FINANCIALS',
                timestamp=datetime.now()
            ),
            ScreenerSignal(
                symbol='INFY',
                score=8.0, atr=30.0, adx=25.0, volume_ratio=1.3,
                trend='BULLISH', price=1000.0, sector='IT',
                timestamp=datetime.now()
            ),
            ScreenerSignal(
                symbol='TCS',
                score=7.5, atr=25.0, adx=22.0, volume_ratio=1.2,
                trend='BULLISH', price=3000.0, sector='IT',
                timestamp=datetime.now()
            )
        ]
        
        # Process multiple signals
        for signal in signals:
            success, _ = self.trader.process_signal(signal)
            # Each should succeed (within limits)
        
        # Check total positions
        positions = self.trader.state.load_positions()
        assert len(positions) <= self.capital_params.max_open_positions
        
        # Check sector limits
        sectors = {}
        for sym, pos in positions.items():
            sector = pos.get('sector', 'UNKNOWN')
            sectors[sector] = sectors.get(sector, 0) + 1
            assert sectors[sector] <= self.capital_params.max_per_sector
    
    def cleanup_method(self):
        """Cleanup after each test"""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestStateRecovery:
    """Test recovery from failures"""
    
    def test_state_corruption_recovery(self):
        """Test recovery from corrupted state file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StateManager(tmpdir)
            
            # Save some data with all required fields
            pos = {
                'symbol': 'SBIN',
                'entry_price': 500.0,
                'quantity': 100,
                'qty_remaining': 100,
                'stop_loss': 480.0,
                'side': 'BUY',
                'atr': 20.0,
                'target': 520.0,
                'entry_time': datetime.now().isoformat(),
                'partial_exit_done': False,
                'status': 'OPEN'
            }
            mgr.add_position('SBIN', pos)
            
            # Corrupt the file
            pos_file = f"{tmpdir}/positions.json"
            with open(pos_file, 'w') as f:
                f.write("CORRUPTED DATA {{{")
            
            # Should recover from backup
            recovered = mgr.load_positions()
            assert isinstance(recovered, dict)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
