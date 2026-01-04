"""
Test Timing Intelligence System
==============================
Comprehensive testing for the hybrid timing approach.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, time
from src.timing.market_regime import MarketRegimeManager, MarketRegime
from src.timing.timing_filter import TimingFilter
from src.timing.timing_rules import BullMarketRules, BearMarketRules, SidewaysRules
from src.core.models import ScreenerSignal
from config.config_manager import ConfigManager


def test_market_regime_detection():
    """Test market regime detection"""
    print("=" * 60)
    print("TESTING MARKET REGIME DETECTION")
    print("=" * 60)
    
    regime_mgr = MarketRegimeManager()
    
    print("🔍 Detecting current market regime...")
    regime, confidence = regime_mgr.detect_regime()
    
    print(f"✓ Current Regime: {regime.value}")
    print(f"✓ Confidence: {confidence:.2f}")
    print(f"✓ Should Trade: {regime_mgr.should_trade_now()}")
    
    regime_info = regime_mgr.get_regime_info()
    print(f"✓ Regime Info: {regime_info}")
    
    return regime_mgr


def test_timing_rules():
    """Test timing rules for different regimes"""
    print("\n" + "=" * 60)
    print("TESTING TIMING RULES")
    print("=" * 60)
    
    # Create test signal
    test_signal = ScreenerSignal(
        symbol='TESTSTOCK',
        score=45.0,
        atr=15.0,
        adx=25.0,
        volume_ratio=1.5,
        trend='BULLISH',
        price=500.0,
        sector='BANKING',
        timestamp=datetime.now()
    )
    
    # Test different regime rules
    rules_map = {
        'BULL': BullMarketRules(),
        'BEAR': BearMarketRules(), 
        'SIDEWAYS': SidewaysRules()
    }
    
    for regime_name, rules in rules_map.items():
        print(f"\n📊 Testing {regime_name} Market Rules:")
        
        can_enter, reason = rules.can_enter_now(test_signal)
        print(f"  Entry Decision: {can_enter}")
        print(f"  Reason: {reason}")
        print(f"  Entry Windows: {rules.get_entry_windows()}")
    
    return test_signal


def test_timing_filter():
    """Test complete timing filter"""
    print("\n" + "=" * 60)
    print("TESTING TIMING FILTER")
    print("=" * 60)
    
    # Initialize timing filter
    regime_mgr = MarketRegimeManager()
    timing_filter = TimingFilter(regime_mgr)
    
    # Create test signal
    test_signal = ScreenerSignal(
        symbol='SBIN',
        score=42.0,
        atr=20.0,
        adx=28.0,
        volume_ratio=1.3,
        trend='BULLISH', 
        price=750.0,
        sector='BANKING',
        timestamp=datetime.now()
    )
    
    print(f"🎯 Testing signal: {test_signal.symbol}")
    print(f"   Score: {test_signal.score}")
    print(f"   Price: ₹{test_signal.price}")
    print(f"   Trend: {test_signal.trend}")
    
    # Test entry timing
    should_enter, reason = timing_filter.should_enter_now(test_signal)
    
    print(f"\n📈 Entry Decision: {'✓ APPROVED' if should_enter else '✗ REJECTED'}")
    print(f"   Reason: {reason}")
    
    # Test position exit timing
    test_position = {
        'symbol': 'SBIN',
        'entry_price': 750.0,
        'entry_time': datetime.now().isoformat(),
        'qty_remaining': 5,
        'unrealized_pnl_pct': 1.2
    }
    
    should_exit, exit_reason = timing_filter.should_exit_now(test_position)
    print(f"\n📉 Exit Decision: {'✓ EXIT NOW' if should_exit else '✗ HOLD'}")
    print(f"   Reason: {exit_reason}")
    
    # Get timing info
    timing_info = timing_filter.get_timing_info()
    print(f"\n📊 Timing Status:")
    print(f"   Market Regime: {timing_info['market_regime']['regime']}")
    print(f"   Timing Rules: {timing_info['timing_rules']}")
    print(f"   Daily Entries: {timing_info['daily_entries']}")
    
    return timing_filter


def test_configuration_loading():
    """Test configuration loading"""
    print("\n" + "=" * 60)
    print("TESTING CONFIGURATION LOADING")
    print("=" * 60)
    
    config_mgr = ConfigManager()
    
    # Test timing config loading
    timing_enabled = config_mgr.is_timing_enabled()
    print(f"✓ Timing Enabled: {timing_enabled}")
    
    if timing_enabled:
        timing_params = config_mgr.get_timing_parameters()
        print(f"✓ Timing Parameters: {timing_params}")
    
    # Test regular config still works
    capital_params = config_mgr.get_capital_parameters()
    trade_params = config_mgr.get_trade_parameters()
    
    print(f"✓ Capital Config: Total=₹{capital_params.total_capital}")
    print(f"✓ Trade Config: SL={trade_params.sl_atr_mult}x, Target={trade_params.target_atr_mult}x")
    
    return config_mgr


def test_integration_workflow():
    """Test full integration workflow"""
    print("\n" + "=" * 60)
    print("TESTING INTEGRATION WORKFLOW")
    print("=" * 60)
    
    # Simulate full workflow
    print("🔄 Simulating complete trading workflow...")
    
    # 1. Initialize components
    config_mgr = ConfigManager()
    timing_enabled = config_mgr.is_timing_enabled()
    
    if not timing_enabled:
        print("⚠️  Timing not enabled in config - enable it in timing_config.yaml")
        return False
    
    # 2. Create timing filter
    regime_mgr = MarketRegimeManager()
    timing_filter = TimingFilter(regime_mgr)
    
    # 3. Simulate signals
    test_signals = [
        ScreenerSignal('RELIANCE', 38.0, 25.0, 22.0, 1.1, 'BULLISH', 2800.0, 'OIL_GAS', datetime.now()),
        ScreenerSignal('TCS', 52.0, 35.0, 28.0, 1.4, 'BULLISH', 3500.0, 'IT', datetime.now()),
        ScreenerSignal('HDFC', 45.0, 18.0, 26.0, 1.2, 'BULLISH', 1650.0, 'BANKING', datetime.now()),
    ]
    
    print(f"📊 Testing {len(test_signals)} signals...")
    
    approved_count = 0
    rejected_count = 0
    
    for signal in test_signals:
        should_enter, reason = timing_filter.should_enter_now(signal)
        
        if should_enter:
            approved_count += 1
            print(f"   ✓ {signal.symbol}: APPROVED - {reason}")
        else:
            rejected_count += 1  
            print(f"   ✗ {signal.symbol}: REJECTED - {reason}")
    
    print(f"\n📈 Results: {approved_count} approved, {rejected_count} rejected")
    
    # 4. Get final status
    timing_info = timing_filter.get_timing_info()
    print(f"📊 Final Status: {timing_info['market_regime']['regime']} market")
    
    return True


def run_all_tests():
    """Run all timing tests"""
    print("🧪 TIMING INTELLIGENCE TEST SUITE")
    print("=" * 80)
    
    try:
        # Run tests
        test_market_regime_detection()
        test_timing_rules()
        test_timing_filter()
        test_configuration_loading()
        integration_ok = test_integration_workflow()
        
        print("\n" + "=" * 80)
        print("🎉 ALL TESTS COMPLETED")
        print("=" * 80)
        
        if integration_ok:
            print("✅ Integration test PASSED - System ready!")
        else:
            print("⚠️  Integration test needs configuration - Check timing_config.yaml")
        
        print("\n📋 NEXT STEPS:")
        print("1. Enable timing in timing_config.yaml (set enabled: true)")
        print("2. Run paper trading with: python main.py --mode paper")
        print("3. Monitor timing decisions in logs")
        print("4. Fine-tune regime thresholds based on results")
        
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)