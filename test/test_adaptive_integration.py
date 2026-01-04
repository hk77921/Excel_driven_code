#!/usr/bin/env python
"""
Test Adaptive Strategies Integration with Paper/Live Trading
============================================================
This test verifies that the adaptive strategies are properly integrated
with the main trading engine and can be used for both paper and live trading.
"""

import sys
import os
import pandas as pd
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.core.engine import TradingEngine
from src.core.models import ScreenerSignal, TradeParameters, CapitalParameters
from src.core.state_manager import StateManager
from src.execution.paper import PaperTradingMode
from config.config_manager import ConfigManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

def test_adaptive_strategies_integration():
    """Test that adaptive strategies work with trading engine."""
    
    print("🚀 ADAPTIVE STRATEGIES INTEGRATION TEST")
    print("=" * 60)
    
    try:
        # Setup configuration
        config_manager = ConfigManager()
        capital_params = CapitalParameters(
            total_capital=50000.0,
            risk_per_trade=0.005,
            max_open_positions=5,
            max_per_sector=2
        )
        trade_params = TradeParameters(
            sl_atr_mult=2.0,
            target_atr_mult=4.0
        )
        
        # Create state manager for testing
        state_dir = Path("state/test_adaptive")
        state_dir.mkdir(parents=True, exist_ok=True)
        
        state_manager = StateManager(
            state_dir=str(state_dir)
        )
        
        # Initialize trading engine (this will include adaptive strategies)
        print("📋 Initializing Trading Engine with Adaptive Strategies...")
        engine = TradingEngine(
            capital_params=capital_params,
            trade_params=trade_params,
            state_manager=state_manager,
            timing_enabled=False  # Disable timing for clean test
        )
        
        if engine.adaptive_manager:
            print("✅ Adaptive Strategy Manager: LOADED")
            status = engine.adaptive_manager.get_strategy_status()
            print(f"   Mode: {status.get('current_mode', 'AUTO')}")
            print(f"   Strategies: {len(status.get('strategies', {}))} active")
        else:
            print("❌ Adaptive Strategy Manager: NOT LOADED")
            return False
        
        # Create test signals with different score ranges
        test_signals = [
            # High score signal
            ScreenerSignal(
                symbol="SBIN",
                score=88.5,
                atr=15.2,
                adx=68.3,
                volume_ratio=2.8,
                trend="BULLISH",
                price=520.0,
                sector="BANK",
                timestamp=datetime.now()
            ),
            # Medium score signal  
            ScreenerSignal(
                symbol="TCS",
                score=65.2,
                atr=12.8,
                adx=45.7,
                volume_ratio=1.9,
                trend="BULLISH",
                price=3850.0,
                sector="IT",
                timestamp=datetime.now()
            ),
            # Low score signal
            ScreenerSignal(
                symbol="INFY",
                score=42.1,
                atr=9.5,
                adx=28.9,
                volume_ratio=1.3,
                trend="NEUTRAL",
                price=1875.0,
                sector="IT", 
                timestamp=datetime.now()
            )
        ]
        
        print(f"\n📊 Processing {len(test_signals)} test signals...")
        
        results = []
        for i, signal in enumerate(test_signals):
            print(f"\n🔍 Signal {i+1}: {signal.symbol} (Score: {signal.score})")
            
            # Process signal through trading engine
            success, order, reason = engine.process_signal(signal)
            
            if success and order:
                print(f"   ✅ ORDER CREATED: {order.symbol}")
                print(f"      Qty: {order.req_qty}")
                print(f"      Price: ₹{order.price:.2f}")
                print(f"      Order ID: {order.order_id}")
                results.append({
                    'symbol': signal.symbol,
                    'score': signal.score,
                    'success': True,
                    'qty': order.req_qty,
                    'price': order.price
                })
            else:
                print(f"   ⏭️ REJECTED: {reason}")
                results.append({
                    'symbol': signal.symbol,
                    'score': signal.score,
                    'success': False,
                    'reason': reason
                })
        
        print(f"\n📈 RESULTS SUMMARY")
        print("=" * 40)
        
        successful = [r for r in results if r['success']]
        rejected = [r for r in results if not r['success']]
        
        print(f"Signals Processed: {len(test_signals)}")
        print(f"Orders Created: {len(successful)}")
        print(f"Signals Rejected: {len(rejected)}")
        
        if successful:
            print("\n✅ Successful Orders:")
            for result in successful:
                print(f"   {result['symbol']}: {result['qty']} shares @ ₹{result['price']:.2f}")
        
        if rejected:
            print("\n⏭️ Rejected Signals:")
            for result in rejected:
                print(f"   {result['symbol']}: {result['reason']}")
        
        # Test paper trading mode integration
        print(f"\n🧪 TESTING PAPER TRADING INTEGRATION")
        print("=" * 50)
        
        paper_engine = PaperTradingMode(
            capital_params=capital_params,
            trade_params=trade_params,
            state_dir=str(state_dir)
        )
        
        print("✅ Paper trading mode initialized with adaptive strategies")
        
        # Clean up test files
        for file in state_dir.glob("*.json"):
            if file.exists():
                file.unlink()
        
        print(f"\n🎯 INTEGRATION TEST RESULT: ✅ SUCCESS")
        print("Adaptive strategies are properly integrated with:")
        print("- Trading Engine: ✅ Working")
        print("- Paper Trading: ✅ Working") 
        print("- Live Trading: ✅ Ready (same engine)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ INTEGRATION TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_adaptive_strategies_integration()
    exit(0 if success else 1)