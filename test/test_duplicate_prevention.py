#!/usr/bin/env python3
"""
Test Script: Duplicate Trade Prevention
=======================================
This script demonstrates how the enhanced duplicate prevention works.
"""

import logging
import sys
import os
from datetime import datetime

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)

def test_duplicate_prevention():
    """Test the duplicate trade prevention logic"""
    
    print("="*70)
    print("DUPLICATE TRADE PREVENTION TEST")
    print("="*70)
    
    # Import required modules
    from src.core.models import ScreenerSignal, CapitalParameters, TradeParameters
    from src.core.state_manager import StateManager
    from src.core.engine import TradingEngine
    from datetime import datetime
    
    # Create test parameters
    capital_params = CapitalParameters(
        total_capital=100000,
        max_risk_per_trade_pct=1.0,
        max_open_positions=5,
        max_sector_allocation_pct=20.0,
        reserve_cash_pct=10.0
    )
    
    trade_params = TradeParameters(
        sl_atr_mult=1.5,
        target_atr_mult=2.0,
        partial_exit_target_mult=1.0,
        trailing_sl_atr_mult=1.0
    )
    
    # Create state manager and engine
    state_manager = StateManager("state/test")
    engine = TradingEngine(capital_params, trade_params, state_manager, timing_enabled=True)
    
    # Create a test signal
    signal = ScreenerSignal(
        symbol='TESTSTOCK',
        score=8.5,
        atr=20.0,
        adx=25.0,
        volume_ratio=1.5,
        trend='BULLISH',
        price=500.0,
        sector='TECHNOLOGY',
        timestamp=datetime.now()
    )
    
    print(f"Testing signal: {signal.symbol} @ Rs.{signal.price}")
    print()
    
    # Test 1: First entry should succeed
    print("TEST 1: First entry attempt")
    success1, order1, reason1 = engine.process_signal(signal)
    print(f"Result: Success={success1}, Reason='{reason1}'")
    
    if success1:
        # Simulate adding the position to state
        position = {
            'symbol': signal.symbol,
            'entry_price': signal.price,
            'quantity': 100,
            'qty_remaining': 100,
            'stop_loss': signal.price - (1.5 * signal.atr),
            'atr': signal.atr
        }
        state_manager.add_position(signal.symbol, position)
        print(f"Position added: {position}")
    
    print()
    
    # Test 2: Second entry should fail (duplicate prevention)
    print("TEST 2: Duplicate entry attempt")
    success2, order2, reason2 = engine.process_signal(signal)
    print(f"Result: Success={success2}, Reason='{reason2}'")
    print()
    
    # Test 3: Try again after 1 second (should still fail due to recent attempt tracking)
    print("TEST 3: Rapid retry (should fail due to timing filter)")
    import time
    time.sleep(1)
    success3, order3, reason3 = engine.process_signal(signal)
    print(f"Result: Success={success3}, Reason='{reason3}'")
    print()
    
    # Cleanup
    try:
        state_manager.remove_position(signal.symbol)
        print("Test position cleaned up")
    except:
        pass
    
    print("="*70)
    print("DUPLICATE PREVENTION TEST COMPLETE")
    print("="*70)
    print()
    print("SUMMARY:")
    print(f"  First attempt:  {'✓ PASSED' if success1 else '✗ FAILED'}")
    print(f"  Duplicate block: {'✓ BLOCKED' if not success2 else '✗ ALLOWED'}")
    print(f"  Rapid retry:    {'✓ BLOCKED' if not success3 else '✗ ALLOWED'}")
    
    if success1 and not success2 and not success3:
        print("\n🎉 ALL TESTS PASSED - Duplicate prevention is working!")
    else:
        print("\n⚠️  SOME TESTS FAILED - Check the logs above")

if __name__ == "__main__":
    test_duplicate_prevention()