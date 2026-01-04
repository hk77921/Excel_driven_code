#!/usr/bin/env python3
"""
Gainer/Loser Strategy Demo
=========================
Demonstrates the custom gainer/loser trading strategy.

This script:
1. Fetches top NSE gainers and losers
2. Generates trading signals
3. Shows entry points and targets
4. Provides risk management parameters

Usage:
    python demo_gainer_loser.py
"""

import sys
import os
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.strategies.market_detector import EnhancedMarketDetector
from src.strategies.gainer_loser_strategy import GainerLoserStrategy


def main():
    """Main demo function"""
    print("🚀 GAINER/LOSER STRATEGY DEMO")
    print("=" * 50)
    
    try:
        # Initialize strategy
        market_detector = EnhancedMarketDetector()
        strategy = GainerLoserStrategy(market_detector)
        
        # Get strategy info
        info = strategy.get_strategy_info()
        print(f"\n📊 Strategy: {info['name']}")
        print(f"Description: {info['description']}")
        print(f"NSE Available: {info['nse_available']}")
        
        if not info['nse_available']:
            print("\n❌ NSE Tools not available!")
            print("Install with: pip install nsetools")
            return
        
        print(f"\n⚙️ Parameters:")
        params = info['parameters']
        for key, value in params.items():
            print(f"   {key}: {value}")
        
        # Get current trading signals
        print(f"\n🔍 Fetching NSE data...")
        signals = strategy.get_trading_signals()
        
        if not signals:
            print("❌ No signals found or NSE data unavailable")
            return
        
        print(f"\n✅ Found {len(signals)} potential signals:")
        print("-" * 80)
        print(f"{'Symbol':<10} {'Type':<8} {'Gap%':<8} {'Entry':<10} {'Target':<10} {'Current':<10}")
        print("-" * 80)
        
        valid_signals = []
        
        for signal in signals:
            # Evaluate each signal
            should_enter, reason, params = strategy.evaluate_gainer_loser_signal(signal)
            
            status = "✓" if should_enter else "✗"
            print(f"{signal.symbol:<10} {signal.signal_type:<8} {signal.gap_pct:<8.2f} "
                  f"{signal.entry_price:<10.2f} {signal.target_price:<10.2f} {signal.ltp:<10.2f} {status}")
            
            if should_enter:
                valid_signals.append((signal, params))
        
        # Show detailed analysis for valid signals
        if valid_signals:
            print(f"\n📈 TRADING RECOMMENDATIONS ({len(valid_signals)} signals):")
            print("=" * 60)
            
            for i, (signal, params) in enumerate(valid_signals, 1):
                print(f"\n{i}. {signal.symbol} ({signal.signal_type})")
                print(f"   Gap: {signal.gap_pct:.2f}% ({signal.prev_price:.2f} → {signal.open_price:.2f})")
                print(f"   Entry: ₹{params['entry_price']:.2f}")
                print(f"   Target: ₹{params['target_price']:.2f}")  
                print(f"   Stop Loss: ₹{params['stop_loss_price']:.2f}")
                print(f"   Position Size: {params['position_size_multiplier']:.2f}x")
                
                # Calculate potential returns
                entry = params['entry_price']
                target = params['target_price']
                sl = params['stop_loss_price']
                
                if signal.signal_type == 'GAINER':
                    profit_pct = ((entry - target) / entry) * 100  # Short trade
                    loss_pct = ((sl - entry) / entry) * 100
                else:
                    profit_pct = ((target - entry) / entry) * 100  # Long trade  
                    loss_pct = ((entry - sl) / entry) * 100
                
                print(f"   Potential Profit: {profit_pct:.2f}%")
                print(f"   Potential Loss: {loss_pct:.2f}%")
                print(f"   Risk:Reward = 1:{abs(profit_pct/loss_pct):.2f}")
        
        else:
            print(f"\n⚠️ No valid trading signals at this time")
            print("Possible reasons:")
            print("   • Market timing (trade window: 9:15 AM - 11:30 AM)")
            print("   • High volatility conditions")
            print("   • Gaps outside acceptable range (2-8%)")
            
        # Show current market state
        market_state = market_detector.get_current_market_state()
        print(f"\n📊 Current Market State:")
        print(f"   Direction: {market_state.direction.value}")
        print(f"   Gap Type: {market_state.gap_type.value}")
        print(f"   Gap Size: {market_state.gap_size_pct:.2f}%")
        print(f"   Volatility: {market_state.volatility_regime.value}")
        print(f"   NIFTY: {market_state.nifty_price:.2f}")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()