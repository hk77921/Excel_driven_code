#!/usr/bin/env python
"""
Adaptive Strategies Backtest
============================
Backtests the new adaptive strategies system to validate performance.

This script integrates the adaptive strategies manager with the existing
backtest engine to test parameter adaptation in different market conditions.
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import json
from typing import Dict, List, Any

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core import ScreenerSignal, TradeParameters
from src.strategies.adaptive_manager import AdaptiveStrategyManager, StrategyMode
from src.execution.backtest import BacktestMode
from config.config_manager import ConfigManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

class AdaptiveBacktester:
    """Backtests adaptive strategies with different market conditions."""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.adaptive_manager = AdaptiveStrategyManager()
        self.results = []
        
    def create_test_signals(self) -> List[ScreenerSignal]:
        """Create test signals for different score ranges."""
        test_signals = [
            # Strong signals
            ScreenerSignal(
                symbol="SBIN",
                score=85.2,
                atr=15.5,
                adx=65.8,
                volume_ratio=2.5,
                trend="BULLISH",
                price=520.75,
                sector="BANK",
                timestamp=datetime.now()
            ),
            # Medium signals
            ScreenerSignal(
                symbol="TCS",
                score=65.8,
                atr=12.3,
                adx=45.2,
                volume_ratio=1.8,
                trend="BULLISH",
                price=3850.20,
                sector="IT",
                timestamp=datetime.now()
            ),
            # Weak signals
            ScreenerSignal(
                symbol="INFY", 
                score=45.2,
                atr=8.9,
                adx=32.1,
                volume_ratio=1.2,
                trend="NEUTRAL",
                price=1875.45,
                sector="IT",
                timestamp=datetime.now()
            ),
            # Very strong signal
            ScreenerSignal(
                symbol="RELIANCE",
                score=92.1,
                atr=28.7,
                adx=78.3,
                volume_ratio=3.2,
                trend="BULLISH",
                price=1285.90,
                sector="ENERGY",
                timestamp=datetime.now()
            )
        ]
        
        return test_signals
        
    def test_strategy_mode(self, mode: StrategyMode, signals: List[ScreenerSignal]) -> Dict[str, Any]:
        """Test adaptive strategies in a specific mode."""
        logger.info(f"🔧 Testing {mode.value} mode...")
        
        # Switch to test mode (disable cooldown)
        self.adaptive_manager.config.switching_cooldown_minutes = 0
        self.adaptive_manager.switch_mode(mode, f"Backtest: {mode.value} mode")
        
        results = {
            'mode': mode.value,
            'signals_processed': 0,
            'enters': 0,
            'skips': 0,
            'parameter_adjustments': [],
            'performance_metrics': {}
        }
        
        for signal in signals:
            try:
                # Get strategy decision
                decision = self.adaptive_manager.evaluate_trade_entry(signal)
                
                results['signals_processed'] += 1
                
                if decision.should_enter:
                    results['enters'] += 1
                    
                    # Record parameter adjustments 
                    param_adjustment = {
                        'symbol': signal.symbol,
                        'score': signal.score,
                        'sl_multiplier': decision.final_parameters.get('sl_multiplier', 1.0),
                        'target_multiplier': decision.final_parameters.get('target_multiplier', 2.0),
                        'position_size_multiplier': decision.final_parameters.get('position_size_multiplier', 1.0),
                        'primary_strategy': decision.primary_strategy
                    }
                    results['parameter_adjustments'].append(param_adjustment)
                    
                    logger.info(f"  ✅ {signal.symbol} (Score: {signal.score}) -> ENTER")
                    logger.info(f"      SL: {param_adjustment['sl_multiplier']:.2f} | "
                              f"Target: {param_adjustment['target_multiplier']:.2f} | "
                              f"Size: {param_adjustment['position_size_multiplier']:.2f}")
                    
                else:
                    results['skips'] += 1
                    logger.info(f"  ⏭️ {signal.symbol} (Score: {signal.score}) -> SKIP")
                    logger.info(f"      Reason: {decision.combined_reason}")
                    
            except Exception as e:
                logger.error(f"  ❌ Error processing {signal.symbol}: {e}")
                
        # Calculate performance metrics
        total_signals = len(signals)
        results['performance_metrics'] = {
            'enter_rate': results['enters'] / total_signals if total_signals > 0 else 0,
            'skip_rate': results['skips'] / total_signals if total_signals > 0 else 0,
            'avg_sl_multiplier': np.mean([p['sl_multiplier'] for p in results['parameter_adjustments']]) if results['parameter_adjustments'] else 0,
            'avg_target_multiplier': np.mean([p['target_multiplier'] for p in results['parameter_adjustments']]) if results['parameter_adjustments'] else 0,
            'avg_position_size': np.mean([p['position_size_multiplier'] for p in results['parameter_adjustments']]) if results['parameter_adjustments'] else 0
        }
        
        return results
        
    def run_comprehensive_backtest(self) -> Dict[str, Any]:
        """Run comprehensive backtest across all modes."""
        logger.info("🚀 ADAPTIVE STRATEGIES BACKTEST")
        logger.info("=" * 60)
        
        # Create test signals
        test_signals = self.create_test_signals()
        logger.info(f"📊 Generated {len(test_signals)} test signals")
        
        # Test all strategy modes
        modes_to_test = [
            StrategyMode.CONSERVATIVE,
            StrategyMode.AUTO,
            StrategyMode.AGGRESSIVE,
            StrategyMode.ENSEMBLE
        ]
        
        backtest_results = {}
        
        for mode in modes_to_test:
            mode_results = self.test_strategy_mode(mode, test_signals)
            backtest_results[mode.value] = mode_results
            
            logger.info(f"📈 {mode.value} Results:")
            logger.info(f"   Signals: {mode_results['signals_processed']}")
            logger.info(f"   Enters: {mode_results['enters']}")
            logger.info(f"   Skips: {mode_results['skips']}")
            logger.info(f"   Enter Rate: {mode_results['performance_metrics']['enter_rate']:.2%}")
            logger.info("")
            
        # Analyze market adaptation
        logger.info("🎯 MARKET ADAPTATION ANALYSIS")
        logger.info("=" * 60)
        
        for mode_name, mode_data in backtest_results.items():
            logger.info(f"\n📊 {mode_name} Mode Analysis:")
            
            if mode_data['parameter_adjustments']:
                adjustments = mode_data['parameter_adjustments']
                
                # Group by score ranges
                high_score = [a for a in adjustments if a['score'] >= 80]
                med_score = [a for a in adjustments if 60 <= a['score'] < 80]
                low_score = [a for a in adjustments if a['score'] < 60]
                
                for score_range, name in [(high_score, "High Score (80+)"), 
                                        (med_score, "Medium Score (60-80)"),
                                        (low_score, "Low Score (<60)")]:
                    if score_range:
                        avg_sl = np.mean([s['sl_multiplier'] for s in score_range])
                        avg_target = np.mean([s['target_multiplier'] for s in score_range])
                        avg_size = np.mean([s['position_size_multiplier'] for s in score_range])
                        
                        logger.info(f"   {name}: SL {avg_sl:.2f} | Target {avg_target:.2f} | Size {avg_size:.2f}")
            else:
                logger.info("   No trades generated in this mode")
                
        # Summary
        logger.info("\n🎯 BACKTEST SUMMARY")
        logger.info("=" * 60)
        
        total_enters = sum(r['enters'] for r in backtest_results.values())
        total_signals = sum(r['signals_processed'] for r in backtest_results.values())
        
        logger.info(f"Total Signals Processed: {total_signals}")
        logger.info(f"Total Entries Generated: {total_enters}")
        if total_signals > 0:
            logger.info(f"Overall Entry Rate: {total_enters/total_signals:.2%}")
        else:
            logger.info(f"Overall Entry Rate: 0.00%")
        
        # Mode comparison
        logger.info("\n📊 Mode Comparison:")
        for mode_name, mode_data in backtest_results.items():
            metrics = mode_data['performance_metrics']
            logger.info(f"{mode_name:12} | Enter: {metrics['enter_rate']:.2%} | "
                      f"Avg SL: {metrics['avg_sl_multiplier']:.2f} | "
                      f"Avg Target: {metrics['avg_target_multiplier']:.2f}")
        
        return backtest_results
        
def main():
    """Main backtest execution."""
    try:
        backtester = AdaptiveBacktester()
        results = backtester.run_comprehensive_backtest()
        
        logger.info("\n✅ ADAPTIVE STRATEGIES BACKTEST COMPLETED!")
        logger.info("Results can be analyzed for strategy optimization.")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Backtest failed: {e}")
        return None

if __name__ == "__main__":
    results = main()