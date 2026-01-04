#!/usr/bin/env python3
"""
Enhanced Dynamic Universe Demo
==============================
Demonstrates the enhanced gainer/loser trading strategy with dynamic universe.

Features:
- Live NSE top 10 gainers + top 5 losers
- Intelligent filtering and ranking
- Sector diversification
- Real-time universe statistics
- Configuration flexibility

Usage:
    python demo_dynamic_universe.py
"""

import sys
import os
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.strategies.market_detector import EnhancedMarketDetector
from src.strategies.gainer_loser_strategy import GainerLoserStrategy
from src.universe.dynamic_universe_manager import DynamicUniverseManager


def print_section_header(title: str):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_universe_stats(stats: dict):
    """Print universe statistics"""
    print(f"📊 Universe Statistics:")
    print(f"   Total Stocks: {stats.get('total_stocks', 0)}")
    print(f"   Gainers: {stats.get('gainers_count', 0)} (avg gap: {stats.get('avg_gainer_gap', 0):.1f}%)")
    print(f"   Losers: {stats.get('losers_count', 0)} (avg gap: {stats.get('avg_loser_gap', 0):.1f}%)")
    print(f"   Max Gainer Gap: {stats.get('max_gainer_gap', 0):.1f}%")
    print(f"   Max Loser Gap: {stats.get('max_loser_gap', 0):.1f}%")
    print(f"   Sectors Covered: {stats.get('sectors_covered', 0)}")
    print(f"   Data Source: {stats.get('data_source', 'Unknown')}")
    print(f"   Last Update: {stats.get('update_time', 'Unknown')}")


def display_signals_table(signals, title: str):
    """Display signals in a formatted table"""
    if not signals:
        print(f"\n❌ No {title.lower()} found")
        return
    
    print(f"\n✅ {title} ({len(signals)} signals):")
    print("-" * 100)
    print(f"{'Symbol':<12} {'Type':<8} {'Gap%':<8} {'Entry':<10} {'Target':<10} {'Current':<10} {'Sector':<12} {'Score'}")
    print("-" * 100)
    
    for signal in signals:
        print(f"{signal.symbol:<12} {signal.signal_type:<8} {signal.gap_pct:<8.2f} "
              f"{signal.entry_price:<10.2f} {signal.target_price:<10.2f} {signal.ltp:<10.2f} "
              f"{signal.sector:<12} N/A")


def main():
    """Main demo function"""
    print_section_header("🚀 ENHANCED DYNAMIC UNIVERSE DEMO")
    
    try:
        # Initialize components
        print("🔧 Initializing components...")
        market_detector = EnhancedMarketDetector()
        universe_manager = DynamicUniverseManager()
        strategy = GainerLoserStrategy(market_detector)
        
        # Get strategy info
        print_section_header("📊 STRATEGY CONFIGURATION")
        info = strategy.get_strategy_info()
        print(f"Strategy: {info['name']}")
        print(f"Description: {info['description']}")
        print(f"NSE Available: {info['nse_available']}")
        
        if not info['nse_available']:
            print("\n❌ NSE Tools not available!")
            print("Install with: pip install nsetools")
            return
        
        # Show universe configuration
        universe_info = info.get('universe', {})
        print(f"\n⚙️ Universe Configuration:")
        print(f"   Max Gainers: {universe_info.get('max_gainers', 0)}")
        print(f"   Max Losers: {universe_info.get('max_losers', 0)}")
        print(f"   Dynamic Updates: {universe_info.get('dynamic_updates', False)}")
        print(f"   Data Source: {universe_info.get('data_source', 'Unknown')}")
        
        # Show Excel integration status
        excel_info = universe_info.get('excel_integration', {})
        print(f"\n📊 Excel Integration Status:")
        print(f"   Enabled: {excel_info.get('excel_integration_enabled', False)}")
        print(f"   XLWings Available: {excel_info.get('xlwings_available', False)}")
        print(f"   Excel File: {excel_info.get('excel_file_path', 'N/A')}")
        print(f"   File Exists: {excel_info.get('excel_file_exists', False)}")
        print(f"   Last Update: {excel_info.get('last_excel_update', 'Never')}")
        print(f"   Auto-Update: {excel_info.get('update_on_refresh', False)}")
        print(f"   Preserve Static: {excel_info.get('preserve_static_stocks', False)}")
        
        # Show strategy parameters  
        params = info.get('parameters', {})
        print(f"\n📋 Strategy Parameters:")
        for key, value in params.items():
            print(f"   {key}: {value}")
        
        # Get current universe statistics
        print_section_header("🌍 CURRENT UNIVERSE ANALYSIS")
        stats = universe_manager.get_universe_stats()
        print_universe_stats(stats)
        
        # Show market state
        print_section_header("📈 MARKET STATE ANALYSIS")
        market_state = market_detector.get_current_market_state()
        print(f"📊 Current Market State:")
        print(f"   Direction: {market_state.direction.value}")
        print(f"   Gap Type: {market_state.gap_type.value}")
        print(f"   Gap Size: {market_state.gap_size_pct:.2f}%")
        print(f"   Volatility: {market_state.volatility_regime.value}")
        print(f"   NIFTY: {market_state.nifty_price:.2f}")
        print(f"   Confidence: {market_state.confidence:.1f}%")
        
        # Get trading signals
        print_section_header("🎯 TRADING SIGNALS ANALYSIS")
        print(f"🔍 Generating signals from dynamic universe...")
        
        signals = strategy.get_trading_signals()
        
        if not signals:
            print("❌ No signals generated")
            print("\nPossible reasons:")
            print("   • No stocks meeting gap criteria (2-8%)")
            print("   • High volatility conditions")
            print("   • Outside trading hours")
            return
        
        # Separate gainers and losers
        gainers = [s for s in signals if s.signal_type == 'GAINER']
        losers = [s for s in signals if s.signal_type == 'LOSER']
        
        display_signals_table(gainers, "TOP GAINERS")
        display_signals_table(losers, "TOP LOSERS")
        
        # Evaluate signals
        print_section_header("✅ SIGNAL EVALUATION")
        
        valid_signals = []
        rejected_signals = []
        
        for signal in signals:
            should_enter, reason, params = strategy.evaluate_gainer_loser_signal(signal)
            
            if should_enter:
                valid_signals.append((signal, reason, params))
            else:
                rejected_signals.append((signal, reason))
        
        print(f"✅ Valid Signals: {len(valid_signals)}")
        print(f"❌ Rejected Signals: {len(rejected_signals)}")
        
        # Show valid signals
        if valid_signals:
            print(f"\n🎯 RECOMMENDED TRADES:")
            print("-" * 120)
            print(f"{'Symbol':<10} {'Type':<8} {'Gap%':<8} {'Entry':<10} {'Target':<10} {'Risk':<8} {'Reason'}")
            print("-" * 120)
            
            for signal, reason, trade_params in valid_signals:
                risk_amount = trade_params.get('risk_amount', 0)
                print(f"{signal.symbol:<10} {signal.signal_type:<8} {signal.gap_pct:<8.2f} "
                      f"{signal.entry_price:<10.2f} {signal.target_price:<10.2f} "
                      f"{risk_amount:<8.0f} {reason}")
        
        # Show rejection reasons
        if rejected_signals:
            print(f"\n❌ REJECTED SIGNALS:")
            rejection_reasons = {}
            for signal, reason in rejected_signals:
                if reason not in rejection_reasons:
                    rejection_reasons[reason] = []
                rejection_reasons[reason].append(signal.symbol)
            
            for reason, symbols in rejection_reasons.items():
                print(f"   • {reason}: {', '.join(symbols)}")
        
        # Performance summary
        print_section_header("📊 PERFORMANCE SUMMARY")
        acceptance_rate = len(valid_signals) / len(signals) * 100 if signals else 0
        print(f"Signal Acceptance Rate: {acceptance_rate:.1f}%")
        print(f"Universe Efficiency: {stats.get('total_stocks', 0)} stocks processed")
        print(f"Sector Diversification: {stats.get('sectors_covered', 0)} sectors")
        
        if acceptance_rate < 30:
            print("\n⚠️  LOW ACCEPTANCE RATE - Consider adjusting:")
            print("   • Gap percentage filters")
            print("   • Market volatility thresholds")
            print("   • Trading time windows")
        
        # Excel integration demo
        excel_stats = strategy.get_excel_integration_status()
        if excel_stats.get('excel_integration_enabled', False):
            print_section_header("📁 EXCEL INTEGRATION DEMO")
            print("🔄 Testing Excel update functionality...")
            
            update_success = strategy.force_excel_update()
            if update_success:
                print("✅ Excel file successfully updated with dynamic universe!")
                print(f"   File: {excel_stats.get('excel_file_path', 'Unknown')}")
                print(f"   Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print("   Check MiniRobo.xlsx UNIVERSE sheet for dynamic stocks (highlighted in green)")
            else:
                print("❌ Excel update failed. Check file permissions and xlwings installation.")
        else:
            print("\n📁 Excel Integration: Disabled (enable in config/dynamic_universe_config.yaml)")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()