#!/usr/bin/env python3
"""
Quick test for timing intelligence after fixes
"""

import sys
import os
sys.path.insert(0, 'src')

from src.timing.market_regime import MarketRegimeManager
from src.timing.timing_filter import TimingFilter
from src.core.models import ScreenerSignal
from datetime import datetime

def main():
    print("🔧 Testing Fixed Timing System...")
    
    # Test regime manager
    print("\n📊 Testing Market Regime Detection...")
    regime_manager = MarketRegimeManager()
    
    try:
        regime, confidence = regime_manager.detect_regime()
        print(f"✅ Regime: {regime.value}, Confidence: {confidence:.2f}")
    except Exception as e:
        print(f"❌ Regime detection failed: {e}")
        return False
    
    # Test timing filter
    print("\n⏱️ Testing Timing Filter...")
    timing_filter = TimingFilter()
    
    # Create test signal
    test_signal = ScreenerSignal(
        symbol="SBIN",
        score=75.5,
        atr=15.0,
        adx=35.0,
        volume_ratio=2.5,
        trend="BULLISH",
        price=500.0,
        sector="Banking",
        timestamp=datetime.now()
    )
    
    try:
        should_enter, reason = timing_filter.should_enter_now(test_signal)
        print(f"✅ Entry Decision: {should_enter}, Reason: {reason}")
    except Exception as e:
        print(f"❌ Timing filter failed: {e}")
        return False
    
    print("\n🎉 All fixes working correctly!")
    return True

if __name__ == "__main__":
    main()