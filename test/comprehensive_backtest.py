#!/usr/bin/env python
"""
Comprehensive Backtest Suite
=============================
Tests trading strategy across multiple symbols, date ranges, and time periods.

Validates strategy robustness and identifies improvement opportunities.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import tempfile
from typing import Dict, List, Tuple, Optional
import json
import yfinance as yf

from src.core import (
    CapitalParameters, TradeParameters, ScreenerSignal
)
from src.execution import BacktestMode
from config.config_manager import ConfigManager

# Setup logging
logging.basicConfig(
    level=logging.WARNING,  # Suppress detailed logs for cleaner output
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ComprehensiveBacktester:
    """Run comprehensive backtest across multiple scenarios"""
    
    def __init__(self):
        """Initialize backtest suite"""
        self.config = ConfigManager()
        self.capital_params = self.config.get_capital_parameters()
        self.trade_params = self.config.get_trade_parameters()
        self.results = {}
        
    def fetch_data(self, symbol: str, period: str) -> Optional[pd.DataFrame]:
        """Fetch data with error handling"""
        try:
            logger.info(f"Fetching {symbol} for period {period}")
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval='1d')
            
            if df.empty:
                logger.warning(f"{symbol}: No data for period {period}")
                return None
            
            df = df.reset_index()
            df.columns = df.columns.str.lower()
            
            required = ['open', 'high', 'low', 'close', 'volume']
            if not all(col in df.columns for col in required):
                logger.warning(f"{symbol}: Missing required columns")
                return None
            
            return df[['date', 'open', 'high', 'low', 'close', 'volume']]
        
        except Exception as e:
            logger.error(f"Failed to fetch {symbol} ({period}): {e}")
            return None
    
    def run_backtest_on_data(
        self,
        symbol: str,
        df: pd.DataFrame,
        signal_bars: Optional[List[int]] = None
    ) -> Dict:
        """
        Run backtest on provided data.
        
        Args:
            symbol: Trading symbol
            df: OHLCV DataFrame
            signal_bars: List of bars to generate signals (if None, auto-select)
        
        Returns:
            Backtest results dictionary
        """
        if df.empty or len(df) < 20:
            return {'error': f'Insufficient data ({len(df)} bars)'}
        
        with tempfile.TemporaryDirectory() as tmpdir:
            backtest = BacktestMode(
                self.capital_params,
                self.trade_params,
                tmpdir
            )
            
            backtest.load_data(symbol, df)
            
            # Auto-select signal bars if not provided
            if signal_bars is None:
                # Generate signals at 25%, 50%, 75% of data
                total_bars = len(df)
                signal_bars = [
                    total_bars // 4,
                    total_bars // 2,
                    (3 * total_bars) // 4
                ]
            
            # Process signals
            signals_processed = 0
            for bar_idx in signal_bars:
                if bar_idx > 0 and bar_idx < len(df):
                    bar_data = df.iloc[bar_idx]
                    
                    signal = ScreenerSignal(
                        symbol=symbol.replace('.NS', ''),
                        score=8.5,
                        atr=20.0,
                        adx=28.0,
                        volume_ratio=1.5,
                        trend='BULLISH',
                        price=bar_data['close'],
                        sector='FINANCIALS',
                        timestamp=datetime.now()
                    )
                    
                    backtest.step(bar_idx)
                    success, _ = backtest.process_signal(signal)
                    if success:
                        signals_processed += 1
            
            # Run backtest
            results = backtest.run_backtest()
            results['signals_processed'] = signals_processed
            
            return results
    
    def test_symbol_across_periods(
        self,
        symbol: str,
        periods: Optional[List[str]] = None
    ) -> Dict[str, Dict]:
        """
        Test symbol across multiple time periods.
        
        Args:
            symbol: Trading symbol
            periods: List of periods (3mo, 6mo, 1y, 2y, etc.)
        
        Returns:
            Dictionary of results for each period
        """
        if periods is None:
            periods = ['3mo', '6mo', '1y', '2y']
        
        print(f"\n{'='*70}")
        print(f"Testing {symbol} across different time periods")
        print(f"{'='*70}")
        
        period_results = {}
        
        for period in periods:
            print(f"\n[INFO] Testing {symbol} - {period}...", end=' ')
            
            df = self.fetch_data(symbol, period)
            if df is None:
                print("[ERROR] Failed to fetch data")
                period_results[period] = {'error': 'Failed to fetch data'}
                continue
            
            results = self.run_backtest_on_data(symbol, df)
            period_results[period] = results
            
            # Print quick summary
            if 'error' not in results:
                pnl = results.get('total_pnl', 0)
                pnl_pct = results.get('pnl_percentage', 0)
                bars = results.get('bars_processed', 0)
                signals = results.get('signals_processed', 0)
                
                status = "WIN" if pnl > 0 else "BREAK-EVEN" if pnl == 0 else "LOSS"
                print(f"[{status}] {bars} bars | {signals} signals | P&L: Rs{pnl:.0f} ({pnl_pct:.2f}%)")
            else:
                print(f"[ERROR] {results['error']}")
        
        return period_results
    
    def test_multiple_symbols(
        self,
        symbols: Optional[List[str]] = None,
        period: str = '1y'
    ) -> Dict[str, Dict]:
        """
        Test multiple symbols for the same period.
        
        Args:
            symbols: List of symbols to test
            period: Time period for all tests
        
        Returns:
            Dictionary of results for each symbol
        """
        if symbols is None:
            symbols = ['SBIN.NS', 'INFY.NS', 'TCS.NS', 'RELIANCE.NS', 'HDFC.NS']
        
        print(f"\n{'='*70}")
        print(f"Testing multiple symbols - {period}")
        print(f"{'='*70}")
        
        symbol_results = {}
        
        for symbol in symbols:
            print(f"\n[INFO] Testing {symbol}...", end=' ')
            
            df = self.fetch_data(symbol, period)
            if df is None:
                print("[ERROR] Failed to fetch data")
                symbol_results[symbol] = {'error': 'Failed to fetch data'}
                continue
            
            results = self.run_backtest_on_data(symbol, df)
            symbol_results[symbol] = results
            
            # Print quick summary
            if 'error' not in results:
                pnl = results.get('total_pnl', 0)
                pnl_pct = results.get('pnl_percentage', 0)
                bars = results.get('bars_processed', 0)
                
                status = "WIN" if pnl > 0 else "BREAK-EVEN" if pnl == 0 else "LOSS"
                print(f"[{status}] {bars} bars | P&L: Rs{pnl:.0f} ({pnl_pct:.2f}%)")
            else:
                print(f"[ERROR] {results['error']}")
        
        return symbol_results
    
    def run_comprehensive_test(self) -> Dict:
        """Run full comprehensive backtest suite"""
        
        print("\n" + "="*70)
        print("COMPREHENSIVE BACKTESTING SUITE")
        print("="*70)
        
        comprehensive_results = {}
        
        # Test 1: SBIN across different periods
        print("\n[TEST 1] SBIN across time periods")
        sbin_periods = self.test_symbol_across_periods('SBIN.NS', ['3mo', '6mo', '1y'])
        comprehensive_results['SBIN_periods'] = sbin_periods
        
        # Test 2: Multiple symbols in 1 year
        print("\n[TEST 2] Multiple symbols - 1 year")
        symbols_1y = self.test_multiple_symbols(
            ['SBIN.NS', 'INFY.NS', 'TCS.NS', 'RELIANCE.NS', 'HDFC.NS'],
            '1y'
        )
        comprehensive_results['symbols_1y'] = symbols_1y
        
        # Test 3: Multiple symbols in 6 months
        print("\n[TEST 3] Multiple symbols - 6 months")
        symbols_6m = self.test_multiple_symbols(
            ['SBIN.NS', 'INFY.NS', 'TCS.NS'],
            '6mo'
        )
        comprehensive_results['symbols_6m'] = symbols_6m
        
        return comprehensive_results
    
    def generate_summary_report(self, results: Dict):
        """Generate comprehensive summary report"""
        
        print("\n" + "="*70)
        print("COMPREHENSIVE ANALYSIS REPORT")
        print("="*70)
        
        # Collect all valid results
        all_results = []
        
        for test_name, test_results in results.items():
            if isinstance(test_results, dict):
                for key, result in test_results.items():
                    if isinstance(result, dict) and 'error' not in result:
                        all_results.append({
                            'test': test_name,
                            'key': key,
                            'bars': result.get('bars_processed', 0),
                            'pnl': result.get('total_pnl', 0),
                            'pnl_pct': result.get('pnl_percentage', 0),
                            'final_capital': result.get('final_capital', 0)
                        })
        
        if not all_results:
            print("\n[WARNING] No valid results to analyze")
            return
        
        # Convert to DataFrame for analysis
        df_results = pd.DataFrame(all_results)
        
        # Statistics
        print("\n" + "-"*70)
        print("PERFORMANCE STATISTICS")
        print("-"*70)
        
        print(f"\nTotal Tests Run: {len(df_results)}")
        print(f"Profitable Tests: {(df_results['pnl'] > 0).sum()}")
        print(f"Loss-making Tests: {(df_results['pnl'] < 0).sum()}")
        print(f"Break-even Tests: {(df_results['pnl'] == 0).sum()}")
        
        print(f"\nAverage P&L: Rs{df_results['pnl'].mean():.2f}")
        print(f"Max P&L: Rs{df_results['pnl'].max():.2f}")
        print(f"Min P&L: Rs{df_results['pnl'].min():.2f}")
        
        print(f"\nAverage Return: {df_results['pnl_pct'].mean():.2f}%")
        print(f"Max Return: {df_results['pnl_pct'].max():.2f}%")
        print(f"Min Return: {df_results['pnl_pct'].min():.2f}%")
        
        # By symbol
        print("\n" + "-"*70)
        print("PERFORMANCE BY SYMBOL")
        print("-"*70)
        
        symbols = df_results['key'].unique()
        for symbol in sorted(symbols):
            sym_data = df_results[df_results['key'] == symbol]
            avg_pnl = sym_data['pnl'].mean()
            avg_pnl_pct = sym_data['pnl_pct'].mean()
            tests = len(sym_data)
            winning = (sym_data['pnl'] > 0).sum()
            
            print(f"\n{symbol}:")
            print(f"  Tests: {tests}")
            print(f"  Winning: {winning}/{tests}")
            print(f"  Avg P&L: Rs{avg_pnl:.2f} ({avg_pnl_pct:.2f}%)")
        
        # Best and worst performers
        print("\n" + "-"*70)
        print("TOP PERFORMERS")
        print("-"*70)
        
        top_5 = df_results.nlargest(5, 'pnl')
        for idx, row in top_5.iterrows():
            print(f"\n{row['key']} ({row['test']})")
            print(f"  P&L: Rs{row['pnl']:.2f} ({row['pnl_pct']:.2f}%)")
            print(f"  Bars: {row['bars']}")
        
        print("\n" + "-"*70)
        print("WORST PERFORMERS")
        print("-"*70)
        
        bottom_5 = df_results.nsmallest(5, 'pnl')
        for idx, row in bottom_5.iterrows():
            print(f"\n{row['key']} ({row['test']})")
            print(f"  P&L: Rs{row['pnl']:.2f} ({row['pnl_pct']:.2f}%)")
            print(f"  Bars: {row['bars']}")
        
        # Strategy insights
        print("\n" + "-"*70)
        print("STRATEGY INSIGHTS & RECOMMENDATIONS")
        print("-"*70)
        
        win_rate = ((df_results['pnl'] > 0).sum() / len(df_results)) * 100
        avg_return = df_results['pnl_pct'].mean()
        
        print(f"\n[RESULT] Overall Win Rate: {win_rate:.1f}%")
        print(f"[INFO] Overall Avg Return: {avg_return:.2f}%")
        
        if win_rate >= 50:
            print("[SUCCESS] Strategy is profitable on average")
        else:
            print("[WARNING] Strategy needs improvement - below 50% win rate")
        
        if df_results['pnl'].std() > df_results['pnl'].mean() * 2:
            print("[WARNING] High volatility in results - strategy may need risk controls")
        
        # By time period
        print("\n" + "-"*70)
        print("PERFORMANCE BY TIME PERIOD")
        print("-"*70)
        
        if 'test' in df_results.columns:
            for test in df_results['test'].unique():
                test_data = df_results[df_results['test'] == test]
                avg_return = test_data['pnl_pct'].mean()
                winning = (test_data['pnl'] > 0).sum()
                
                print(f"\n{test}:")
                print(f"  Tests: {len(test_data)}")
                print(f"  Winning: {winning}/{len(test_data)}")
                print(f"  Avg Return: {avg_return:.2f}%")
        
        print("\n" + "="*70)
        print("🎯 RECOMMENDATIONS")
        print("="*70)
        
        recommendations = []
        
        if win_rate < 40:
            recommendations.append(
                "1. Strategy has low win rate - Consider adjusting entry/exit signals"
            )
        
        if avg_return < 0:
            recommendations.append(
                "2. Strategy is unprofitable on average - Major rework needed"
            )
        elif avg_return < 2:
            recommendations.append(
                "2. Strategy has low average return - Optimize risk/reward ratio"
            )
        else:
            recommendations.append(
                "2. Strategy shows positive returns - Continue optimization"
            )
        
        recommendations.append(
            "3. Add stricter stop losses - Current exits may be too loose"
        )
        
        recommendations.append(
            "4. Test with different indicators - Consider RSI, MACD, Bollinger Bands"
        )
        
        recommendations.append(
            "5. Implement position sizing - Risk more on high-conviction trades"
        )
        
        for rec in recommendations:
            print(f"\n{rec}")
        
        print("\n" + "="*70)


if __name__ == '__main__':
    backtester = ComprehensiveBacktester()
    results = backtester.run_comprehensive_test()
    backtester.generate_summary_report(results)
    
    print("\n[SUCCESS] Comprehensive backtest completed!")
