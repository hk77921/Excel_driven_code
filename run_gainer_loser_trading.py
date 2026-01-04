#!/usr/bin/env python3
"""
Gainer/Loser Integration Module
==============================
Integrates the gainer/loser strategy with the main trading system.

This module:
1. Runs the gainer/loser strategy alongside regular screener
2. Manages positions from both sources
3. Provides unified reporting
4. Handles timing and market conditions

Usage:
    python run_gainer_loser_trading.py --mode paper
"""

import sys
import os
import argparse
import logging
from datetime import datetime, time
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.core.models import ScreenerSignal, TradeParameters, CapitalParameters
from src.execution.paper import PaperTradingMode
from src.screener.excel_screener import ExcelScreener
from src.strategies.market_detector import EnhancedMarketDetector
from src.strategies.gainer_loser_strategy import GainerLoserStrategy, GainerLoserSignal
from config.config_manager import ConfigManager


def setup_logging():
    """Setup logging for the integration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        handlers=[
            logging.FileHandler(f"logs/gainer_loser_trading_{datetime.now().strftime('%Y%m%d')}.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )


def convert_gainer_loser_to_screener_signal(gl_signal: GainerLoserSignal, params: Dict[str, Any]) -> ScreenerSignal:
    """Convert GainerLoserSignal to ScreenerSignal for trading system"""
    
    # Calculate synthetic score based on gap size and volume
    gap_score = min(abs(gl_signal.gap_pct) * 10, 100)  # 1% gap = 10 points
    volume_score = min(gl_signal.volume / 1000000, 20)  # Volume bonus
    
    synthetic_score = gap_score + volume_score
    synthetic_score = max(40, min(synthetic_score, 100))  # Keep in 40-100 range
    
    # Calculate synthetic ATR based on gap size
    synthetic_atr = abs(gl_signal.gap_amount) * 0.5  # Conservative ATR estimation
    
    return ScreenerSignal(
        symbol=gl_signal.symbol,
        score=synthetic_score,
        atr=synthetic_atr,
        adx=60.0,  # Assume strong trend due to gap
        volume_ratio=2.0,  # Assume higher volume
        trend="BULLISH" if gl_signal.gap_pct > 0 else "BEARISH",
        price=gl_signal.ltp,
        sector=gl_signal.sector,
        timestamp=datetime.now(),
        
        # Add custom fields for gainer/loser strategy
        custom_data={
            'strategy_type': 'GAINER_LOSER',
            'gap_pct': gl_signal.gap_pct,
            'prev_price': gl_signal.prev_price,
            'open_price': gl_signal.open_price,
            'entry_price': gl_signal.entry_price,
            'target_price': gl_signal.target_price,
            'signal_type': gl_signal.signal_type,
            'trading_params': params
        }
    )


class GainerLoserTradingIntegration:
    """Integration class for gainer/loser trading with main system"""
    
    def __init__(self, mode: str = "paper", config_path: str = None):
        """Initialize the integration"""
        self.mode = mode
        
        # Load configuration
        config_mgr = ConfigManager()
        self.capital_params = config_mgr.get_capital_parameters()
        self.trade_params = config_mgr.get_trade_parameters()
        
        # Initialize components
        self.market_detector = EnhancedMarketDetector()
        self.gainer_loser_strategy = GainerLoserStrategy(self.market_detector)
        self.regular_screener = ExcelScreener("MiniRobo.xlsx")
        
        # Initialize trader
        if mode == "paper":
            self.trader = PaperTradingMode(
                self.capital_params,
                self.trade_params, 
                "state/paper"
            )
        else:
            raise NotImplementedError(f"Mode {mode} not implemented yet")
        
        self.logger = logging.getLogger(self.__class__.__name__)
        
    def run_combined_strategy(self) -> Dict[str, Any]:
        """Run both regular screener and gainer/loser strategy"""
        
        current_time = datetime.now().time()
        results = {
            'regular_signals': 0,
            'gainer_loser_signals': 0,
            'total_orders': 0,
            'successful_orders': 0,
            'errors': []
        }
        
        try:
            # 1. Run regular screener (always)
            self.logger.info("Running regular Excel screener...")
            regular_signals = self.regular_screener.run_screener()
            results['regular_signals'] = len(regular_signals)
            
            # Process regular signals
            for signal in regular_signals:
                success, order_id = self.trader.process_signal(signal)
                results['total_orders'] += 1
                if success:
                    results['successful_orders'] += 1
                    self.logger.info(f"✓ Regular signal: {signal.symbol} - {order_id}")
                else:
                    self.logger.warning(f"✗ Regular signal rejected: {signal.symbol} - {order_id}")
            
            # 2. Run gainer/loser strategy (only during market hours)
            if time(9, 15) <= current_time <= time(11, 30):
                self.logger.info("Running gainer/loser strategy...")
                
                gl_signals = self.gainer_loser_strategy.get_trading_signals()
                
                valid_gl_signals = []
                for gl_signal in gl_signals:
                    should_enter, reason, params = self.gainer_loser_strategy.evaluate_gainer_loser_signal(gl_signal)
                    
                    if should_enter:
                        # Convert to ScreenerSignal and process
                        screener_signal = convert_gainer_loser_to_screener_signal(gl_signal, params)
                        valid_gl_signals.append((gl_signal, screener_signal, params))
                
                results['gainer_loser_signals'] = len(valid_gl_signals)
                
                # Process gainer/loser signals
                for gl_signal, screener_signal, params in valid_gl_signals:
                    success, order_id = self.trader.process_signal(screener_signal)
                    results['total_orders'] += 1
                    
                    if success:
                        results['successful_orders'] += 1
                        self.logger.info(f"✓ Gainer/Loser: {gl_signal.symbol} ({gl_signal.signal_type}) - {order_id}")
                    else:
                        self.logger.warning(f"✗ Gainer/Loser rejected: {gl_signal.symbol} - {order_id}")
            
            else:
                self.logger.info("Outside gainer/loser trading window (9:15-11:30)")
            
            # 3. Execute position management cycle
            self.logger.info("Running position management cycle...")
            cycle_report = self.trader.execute_cycle()
            results['cycle_report'] = cycle_report
            
            return results
            
        except Exception as e:
            error_msg = f"Combined strategy execution failed: {e}"
            self.logger.error(error_msg)
            results['errors'].append(error_msg)
            return results
    
    def get_status_report(self) -> Dict[str, Any]:
        """Get comprehensive status report"""
        
        # Get market state
        market_state = self.market_detector.get_current_market_state()
        
        # Get strategy info
        strategy_info = self.gainer_loser_strategy.get_strategy_info()
        
        # Get trading status
        trader_status = self.trader.get_status() if hasattr(self.trader, 'get_status') else {}
        
        return {
            'timestamp': datetime.now().isoformat(),
            'market_state': {
                'direction': market_state.direction.value,
                'gap_type': market_state.gap_type.value,
                'gap_size_pct': market_state.gap_size_pct,
                'volatility_regime': market_state.volatility_regime.value,
                'nifty_price': market_state.nifty_price,
                'confidence': market_state.confidence
            },
            'strategy_info': strategy_info,
            'trader_status': trader_status,
            'mode': self.mode
        }


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Gainer/Loser Trading Integration")
    parser.add_argument('--mode', choices=['paper', 'live'], default='paper',
                       help='Trading mode (default: paper)')
    parser.add_argument('--config', type=str, help='Configuration file path')
    parser.add_argument('--once', action='store_true', help='Run once instead of continuous loop')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 GAINER/LOSER TRADING INTEGRATION")
    logger.info("=" * 50)
    
    try:
        # Initialize integration
        integration = GainerLoserTradingIntegration(args.mode, args.config)
        
        # Get initial status
        status = integration.get_status_report()
        logger.info(f"Market State: {status['market_state']['direction']} "
                   f"(Gap: {status['market_state']['gap_size_pct']:.2f}%)")
        logger.info(f"NSE Available: {status['strategy_info']['nse_available']}")
        
        if not status['strategy_info']['nse_available']:
            logger.error("NSE tools not available. Install with: pip install nsetools")
            return 1
        
        # Run strategy
        if args.once:
            logger.info("Running single execution...")
            results = integration.run_combined_strategy()
            
            # Print results
            logger.info(f"Results: {results['regular_signals']} regular + "
                       f"{results['gainer_loser_signals']} G/L signals")
            logger.info(f"Orders: {results['successful_orders']}/{results['total_orders']} successful")
            
            if results['errors']:
                for error in results['errors']:
                    logger.error(error)
        else:
            logger.info("Continuous mode not implemented. Use --once for single run.")
            return 1
        
        return 0
        
    except Exception as e:
        logger.error(f"Integration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())