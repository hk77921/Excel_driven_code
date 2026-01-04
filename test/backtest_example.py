#!/usr/bin/env python
"""
Backtest Runner
===============
Example script to run backtest on historical data.

Usage:
    python backtest_example.py
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from pathlib import Path
import tempfile
import yfinance as yf
from typing import Optional

from src.core import (
    CapitalParameters, TradeParameters, ScreenerSignal
)
from src.execution import BacktestMode
from config.config_manager import ConfigManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def generate_sample_data(symbol: str, days: int = 100) -> pd.DataFrame:
    """
    Generate sample OHLCV data for testing.
    
    Args:
        symbol: Symbol name
        days: Number of days of data
    
    Returns:
        DataFrame with OHLCV data
    """
    dates = pd.date_range(end=datetime.now(), periods=days, freq='1D')
    
    # Generate realistic price movement
    np.random.seed(42)
    prices = 500 + np.cumsum(np.random.randn(days) * 5)
    
    data = {
        'date': dates,
        'open': prices + np.random.randn(days) * 2,
        'high': prices + np.random.randn(days) * 3 + 5,
        'low': prices + np.random.randn(days) * 3 - 5,
        'close': prices,
        'volume': np.random.randint(1000000, 5000000, days)
    }
    
    return pd.DataFrame(data)


def fetch_yfinance_data(symbol: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """
    Fetch real historical data from yfinance.
    
    Args:
        symbol: Symbol (e.g., 'SBIN.NS' for Indian stocks)
        period: Period for data (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
        interval: Interval (1m, 5m, 15m, 30m, 60m, 1d, 1wk, 1mo)
    
    Returns:
        DataFrame with OHLCV data or None if failed
    """
    try:
        logger.info(f"Fetching real data for {symbol} ({period}, {interval})...")
        
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty:
            logger.error(f"{symbol}: No data returned from yfinance")
            return None
        
        # Rename columns to lowercase
        df = df.reset_index()
        df.columns = df.columns.str.lower()
        
        # Ensure required columns exist
        required = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required):
            logger.error(f"{symbol}: Missing required columns in yfinance data")
            return None
        
        logger.info(
            f"{symbol}: Fetched {len(df)} bars | "
            f"Date range: {df.iloc[0]['date']} to {df.iloc[-1]['date']} | "
            f"Price: Rs.{df.iloc[-1]['close']:.2f}"
        )
        
        return df[['date', 'open', 'high', 'low', 'close', 'volume']]
    
    except Exception as e:
        logger.error(f"{symbol}: Failed to fetch data from yfinance: {e}")
        return None


def run_sample_backtest():
    """Run a sample backtest with real data from yfinance."""
    
    logger.info("=" * 60)
    logger.info("REAL DATA BACKTEST RUNNER")
    logger.info("=" * 60)
    
    # Load configuration
    config = ConfigManager()
    capital_params = config.get_capital_parameters()
    trade_params = config.get_trade_parameters()
    
    logger.info(f"Capital: Rs.{capital_params.total_capital}")
    logger.info(f"Risk per trade: {capital_params.risk_per_trade * 100}%")
    logger.info(f"Max daily loss: {capital_params.max_daily_loss_pct * 100}%")
    
    # Create backtest instance (use temp directory)
    with tempfile.TemporaryDirectory() as tmpdir:
        backtest = BacktestMode(capital_params, trade_params, tmpdir)
        
        # Load REAL data from yfinance
        logger.info("\n📊 Loading REAL data from yfinance...")
        sbin_data = fetch_yfinance_data('SBIN.NS', period='1y', interval='1d')
        
        if sbin_data is None:
            logger.error("Failed to fetch data. Falling back to sample data...")
            sbin_data = generate_sample_data('SBIN', days=100)
        
        backtest.load_data('SBIN', sbin_data)
        
        # Create and process trading signals
        logger.info("\n📈 Processing trading signals...")
        
        # Signal: Enter at bar 50
        signal1 = ScreenerSignal(
            symbol='SBIN',
            score=8.5,
            atr=20.0,
            adx=28.0,
            volume_ratio=1.5,
            trend='BULLISH',
            price=sbin_data.iloc[50]['close'],  # Use actual price from bar 50
            sector='FINANCIALS',
            timestamp=datetime.now()
        )
        
        # Move to bar 50 and process signal
        backtest.step(50)
        entry_price = sbin_data.iloc[50]['close']
        logger.info(f"Signal 1: Entry at bar 50, Price: Rs.{entry_price:.2f}")
        success, msg = backtest.process_signal(signal1)
        logger.info(f"Signal processed: {success}, {msg}")
        
        # Run the backtest
        logger.info("\n🎯 Running backtest on full historical data...")
        results = backtest.run_backtest()
        
        # Print detailed results
        logger.info("\n" + "=" * 60)
        logger.info("BACKTEST RESULTS")
        logger.info("=" * 60)
        
        for key, value in results.items():
            if isinstance(value, float):
                logger.info(f"{key}: {value:.2f}")
            else:
                logger.info(f"{key}: {value}")
        
        return results


def run_yfinance_backtest(symbol: str = 'SBIN.NS', period: str = '1y'):
    """
    Run backtest with real yfinance data.
    
    Args:
        symbol: Symbol (e.g., 'SBIN.NS', 'INFY.NS', 'TCS.NS')
        period: Period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, max)
    """
    
    logger.info("=" * 60)
    logger.info(f"BACKTEST WITH REAL DATA: {symbol}")
    logger.info("=" * 60)
    
    # Load configuration
    config = ConfigManager()
    capital_params = config.get_capital_parameters()
    trade_params = config.get_trade_parameters()
    
    # Create backtest (use temp directory)
    with tempfile.TemporaryDirectory() as tmpdir:
        backtest = BacktestMode(capital_params, trade_params, tmpdir)
        
        # Fetch real data
        logger.info(f"\n📊 Fetching real data for {symbol}...")
        df = fetch_yfinance_data(symbol, period=period, interval='1d')
        
        if df is None or df.empty:
            logger.error(f"Failed to fetch data for {symbol}")
            return None
        
        backtest.load_data(symbol, df)
        
        # Process signals at various points
        logger.info(f"\n📈 Processing trading signals...")
        
        # Signal at 25% through the data
        signal_bar = len(df) // 4
        if signal_bar > 0 and signal_bar < len(df):
            entry_price = df.iloc[signal_bar]['close']
            logger.info(f"Signal 1: Bar {signal_bar}, Price: Rs.{entry_price:.2f}")
            
            signal = ScreenerSignal(
                symbol=symbol.replace('.NS', ''),
                score=8.5,
                atr=20.0,
                adx=28.0,
                volume_ratio=1.5,
                trend='BULLISH',
                price=entry_price,
                sector='FINANCIALS',
                timestamp=datetime.now()
            )
            
            backtest.step(signal_bar)
            success, msg = backtest.process_signal(signal)
            logger.info(f"Signal processed: {success}")
        
        # Run full backtest
        logger.info(f"\n🎯 Running backtest on {len(df)} bars of real data...")
        results = backtest.run_backtest()
        
        # Print results
        logger.info("\n" + "=" * 60)
        logger.info("BACKTEST RESULTS")
        logger.info("=" * 60)
        
        if results:
            for key, value in results.items():
                if isinstance(value, float):
                    logger.info(f"{key}: {value:.2f}")
                else:
                    logger.info(f"{key}: {value}")
        
        return results


if __name__ == '__main__':
    # Run backtest with real yfinance data (1 year of SBIN data)
    logger.info("\n🚀 Starting REAL DATA BACKTEST\n")
    
    # Option 1: Run with real SBIN data (1 year)
    results = run_yfinance_backtest(symbol='SBIN.NS', period='1y')
    
    # Option 2: Run sample backtest (if you want to test without internet)
    # results = run_sample_backtest()
    
    # Option 3: Run with different stocks
    # results = run_yfinance_backtest(symbol='INFY.NS', period='6mo')
    # results = run_yfinance_backtest(symbol='TCS.NS', period='1y')
    
    # Option 4: Run on your own CSV file
    # results = run_csv_backtest('path/to/your/data.csv', 'SYMBOL_NAME')
    
    logger.info("\n✅ Backtest completed!")

