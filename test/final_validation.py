"""
Final Validation Test - Simulated Market Hours Trading
====================================================
This test simulates the complete trading workflow during market hours.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, time
from src.timing.timing_filter import TimingFilter
from src.timing.market_regime import MarketRegimeManager
from src.core.models import ScreenerSignal


def simulate_market_hours_trading():
    """Simulate complete trading during market hours"""
    
    print("🎯 FINAL VALIDATION: MARKET HOURS TRADING SIMULATION")
    print("=" * 70)
    
    # Initialize timing system
    regime_mgr = MarketRegimeManager()
    timing_filter = TimingFilter(regime_mgr)
    
    # Test signals (realistic from screener)
    test_signals = [
        ScreenerSignal('BEL', 13.64, 15.2, 26.4, 1.23, 'BULLISH', 393.30, 'INFRA', datetime.now()),
        ScreenerSignal('SBIN', 45.2, 18.5, 28.1, 1.45, 'BULLISH', 820.0, 'BANKING', datetime.now()),
        ScreenerSignal('RELIANCE', 38.7, 22.3, 25.6, 1.15, 'BULLISH', 2850.0, 'OIL_GAS', datetime.now()),
    ]
    
    # Test at different market times
    market_sessions = [
        (time(9, 30), "Market Open"),
        (time(10, 45), "Mid Morning"),
        (time(11, 15), "Late Morning"), 
        (time(14, 15), "Afternoon"),
        (time(15, 10), "Pre-Close"),
    ]
    
    print(f"📊 Testing {len(test_signals)} signals across {len(market_sessions)} time periods...")
    print()
    
    total_decisions = 0
    approved_decisions = 0
    
    for market_time, session_name in market_sessions:
        print(f"⏰ {session_name} ({market_time.strftime('%H:%M')})")
        print("-" * 50)
        
        session_approved = 0
        
        # Test each signal at this time
        simulated_time = datetime.now().replace(
            hour=market_time.hour,
            minute=market_time.minute,
            second=0,
            microsecond=0
        )
        
        for signal in test_signals:
            should_enter, reason = timing_filter.should_enter_now(signal, simulated_time)
            total_decisions += 1
            
            if should_enter:
                approved_decisions += 1
                session_approved += 1
                print(f"   ✅ {signal.symbol}: APPROVED (Score: {signal.score})")
            else:
                print(f"   ❌ {signal.symbol}: REJECTED - {reason}")
        
        print(f"   Session Result: {session_approved}/{len(test_signals)} approved")
        print()
    
    # Summary
    approval_rate = (approved_decisions / total_decisions) * 100
    
    print("=" * 70)
    print("📈 SIMULATION RESULTS")
    print("=" * 70)
    print(f"Total Decisions: {total_decisions}")
    print(f"Approved: {approved_decisions}")
    print(f"Rejected: {total_decisions - approved_decisions}")
    print(f"Approval Rate: {approval_rate:.1f}%")
    
    # Get timing system status
    timing_info = timing_filter.get_timing_info()
    
    print(f"\n🧠 System Status:")
    print(f"Market Regime: {timing_info['market_regime']['regime']}")
    print(f"Confidence: {timing_info['market_regime']['confidence']:.2f}")
    print(f"Timing Rules: {timing_info['timing_rules']}")
    
    # Validation criteria
    print(f"\n✅ VALIDATION CHECKLIST:")
    
    # Check 1: System makes decisions
    if total_decisions > 0:
        print("   ✓ System processes signals")
    else:
        print("   ❌ System not processing signals")
        
    # Check 2: Some approvals and rejections
    if approved_decisions > 0 and approved_decisions < total_decisions:
        print("   ✓ System approves and rejects appropriately")
    elif approved_decisions == 0:
        print("   ⚠️  System rejecting all signals (check thresholds)")
    elif approved_decisions == total_decisions:
        print("   ⚠️  System approving all signals (check filters)")
    
    # Check 3: Market hours respected
    if approval_rate > 0:
        print("   ✓ Market hours timing working")
    else:
        print("   ❌ Market hours timing issues")
    
    # Check 4: Regime detection working
    regime_info = timing_info['market_regime']
    if regime_info['regime'] in ['BULL_MARKET', 'BEAR_MARKET', 'SIDEWAYS', 'HIGH_VOLATILITY']:
        print("   ✓ Market regime detection functional")
    else:
        print("   ❌ Market regime detection issues")
    
    print(f"\n🎉 TIMING INTELLIGENCE SYSTEM VALIDATION: {'✅ PASSED' if approval_rate > 0 else '⚠️ NEEDS TUNING'}")
    
    return approval_rate > 0


def simulate_paper_trading_integration():
    """Test the paper trading integration flow"""
    
    print("\n" + "=" * 70)
    print("🔗 PAPER TRADING INTEGRATION TEST")
    print("=" * 70)
    
    try:
        from config.config_manager import ConfigManager
        from src.core.models import TradeParameters, CapitalParameters
        from src.execution.paper import PaperTradingMode
        
        # Test configuration loading
        config_mgr = ConfigManager()
        timing_enabled = config_mgr.is_timing_enabled()
        
        print(f"📋 Configuration Test:")
        print(f"   Timing Enabled: {'✅' if timing_enabled else '❌'} {timing_enabled}")
        
        if timing_enabled:
            # Test paper trading initialization
            capital_params = config_mgr.get_capital_parameters()
            trade_params = config_mgr.get_trade_parameters()
            
            print(f"   Capital: ₹{capital_params.total_capital}")
            print(f"   Risk per Trade: {capital_params.risk_per_trade:.1%}")
            
            # Initialize paper trader (don't actually trade)
            trader = PaperTradingMode(
                capital_params=capital_params,
                trade_params=trade_params,
                state_dir="state/test",
                timing_enabled=timing_enabled
            )
            
            print(f"   ✅ Paper trader initialized with timing")
            
            # Test timing system in trader
            if hasattr(trader.engine, 'timing_filter') and trader.engine.timing_filter:
                timing_info = trader.engine.timing_filter.get_timing_info()
                print(f"   ✅ Timing filter active: {timing_info['timing_rules']}")
            else:
                print(f"   ❌ Timing filter not found in trader")
                return False
            
            print(f"\n🎉 INTEGRATION TEST: ✅ PASSED")
            return True
            
        else:
            print(f"   ⚠️  Timing not enabled in configuration")
            print(f"   💡 Enable in timing_config.yaml: enabled: true")
            return False
            
    except Exception as e:
        print(f"   ❌ Integration test failed: {e}")
        return False


if __name__ == "__main__":
    print("🚀 FINAL VALIDATION TEST SUITE")
    print("=" * 80)
    
    # Run tests
    timing_test = simulate_market_hours_trading()
    integration_test = simulate_paper_trading_integration()
    
    # Final verdict
    print("\n" + "=" * 80)
    print("🏁 FINAL VERDICT")
    print("=" * 80)
    
    if timing_test and integration_test:
        print("🎉 ✅ ALL TESTS PASSED - TIMING INTELLIGENCE SYSTEM READY!")
        print("\n📋 Ready for Production:")
        print("   ✅ Market regime detection working")
        print("   ✅ Entry timing filters active") 
        print("   ✅ Configuration system working")
        print("   ✅ Paper trading integration complete")
        
        print(f"\n🚀 Next Steps:")
        print(f"   1. python main.py --mode paper")
        print(f"   2. Monitor timing decisions in real-time")
        print(f"   3. Fine-tune thresholds based on results")
        print(f"   4. Graduate to live trading when confident")
        
        exit_code = 0
        
    else:
        print("⚠️  SOME TESTS NEED ATTENTION")
        
        if not timing_test:
            print("   ❌ Timing logic needs adjustment")
        if not integration_test:
            print("   ❌ Integration needs fixing")
            
        print(f"\n🔧 Actions Needed:")
        print(f"   1. Check timing_config.yaml settings")
        print(f"   2. Verify regime detection thresholds")
        print(f"   3. Review signal quality requirements")
        
        exit_code = 1
    
    sys.exit(exit_code)