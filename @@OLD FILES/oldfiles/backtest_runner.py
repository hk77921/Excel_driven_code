"""
MULTI-TIMEFRAME BACKTESTING RUNNER
===================================
Uses the unified StrategyCore to ensure consistency
"""

import pandas as pd
import yfinance as yf
from datetime import datetime
from typing import List, Dict
import json
import logging
from unified_strategy import (
    StrategyConfig, StrategyCore, BacktestDataProvider, 
    ExecutionEngine, add_indicators
)

# ==============================
# TIMEFRAME CONFIGURATIONS
# ==============================

TIMEFRAMES = {
    "1d_3m": {"interval": "1d", "period": "3mo", "name": "Daily - 3 Months"},
    "1d_6m": {"interval": "1d", "period": "6mo", "name": "Daily - 6 Months"},
    "1d_1y": {"interval": "1d", "period": "1y", "name": "Daily - 1 Year"},
    "1h_1m": {"interval": "1h", "period": "1mo", "name": "Hourly - 1 Month"},
    "15m_1w": {"interval": "15m", "period": "7d", "name": "15min - 1 Week"},
}


def fetch_data_for_timeframe(symbols: List[str], interval: str, period: str) -> Dict[str, pd.DataFrame]:
    """Fetch and prepare data for a timeframe"""
    data = {}
    
    for symbol in symbols:
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                continue
            
            df = df.reset_index()
            df.columns = df.columns.str.lower()
            
            # Ensure required columns
            required = ['date', 'open', 'high', 'low', 'close', 'volume']
            if not all(col in df.columns for col in required):
                continue
            
            data[symbol] = df[required]
            logging.info(f"{symbol}: Fetched {len(df)} bars ({interval})")
            
        except Exception as e:
            logging.error(f"{symbol} fetch failed: {e}")
    
    return data


def run_backtest_for_timeframe(
    symbols: List[str],
    timeframe_key: str,
    config: StrategyConfig
) -> Dict:
    """Run backtest for a specific timeframe"""
    
    tf = TIMEFRAMES[timeframe_key]
    
    logging.info(f"\n{'='*80}")
    logging.info(f"BACKTESTING: {tf['name']}")
    logging.info(f"{'='*80}")
    
    # Fetch data
    raw_data = fetch_data_for_timeframe(symbols, tf['interval'], tf['period'])
    
    if not raw_data:
        logging.error("No data fetched")
        return {"error": "No data"}
    
    # Add indicators
    prepared_data = {}
    for symbol, df in raw_data.items():
        df_with_indicators = add_indicators(df, config)
        if len(df_with_indicators) >= 50:
            prepared_data[symbol] = df_with_indicators
    
    # Create components
    data_provider = BacktestDataProvider(prepared_data)
    strategy = StrategyCore(config)
    engine = ExecutionEngine(strategy, data_provider, config)
    
    # Get all dates
    all_dates = sorted(set(
        date for df in prepared_data.values()
        for date in df['date']
    ))
    
    logging.info(f"Running backtest: {len(prepared_data)} symbols, {len(all_dates)} periods")
    
    # Run backtest
    for date in all_dates:
        for symbol, df in prepared_data.items():
            rows = df[df['date'] == date]
            if not rows.empty:
                bar = rows.iloc[0].to_dict()
                engine.process_bar(symbol, date, bar)
    
    # Get results
    results = engine.get_results()
    results['timeframe'] = tf['name']
    results['interval'] = tf['interval']
    results['period'] = tf['period']
    
    # Print summary
    if 'error' not in results:
        print(f"\n{'='*80}")
        print(f"RESULTS: {tf['name']}")
        print(f"{'='*80}")
        print(f"Total Return:     {results['capital']['total_return_pct']:>10.2f}%")
        print(f"Win Rate:         {results['trades']['win_rate']:>10.2f}%")
        print(f"Total Trades:     {results['trades']['total']:>10}")
        print(f"Profit Factor:    {results['pnl']['profit_factor']:>10.2f}")
        print(f"Avg R-Multiple:   {results['pnl']['avg_r_multiple']:>10.2f}")
        print(f"{'='*80}\n")
    
    return results


def run_multi_timeframe_backtest(symbols: List[str], config: StrategyConfig) -> Dict[str, Dict]:
    """Run backtest across multiple timeframes"""
    
    all_results = {}
    
    for tf_key in TIMEFRAMES.keys():
        results = run_backtest_for_timeframe(symbols, tf_key, config)
        all_results[tf_key] = results
    
    return all_results


def run_parameter_sensitivity(
    symbols: List[str],
    timeframe: str,
    parameter: str,
    values: List[float]
) -> pd.DataFrame:
    """Test different parameter values"""
    
    results = []
    
    for value in values:
        logging.info(f"\nTesting {parameter} = {value}")
        
        # Create config with modified parameter
        config = StrategyConfig()
        setattr(config, parameter, value)
        
        # Run backtest
        result = run_backtest_for_timeframe(symbols, timeframe, config)
        
        if 'error' not in result:
            results.append({
                parameter: value,
                'return_pct': result['capital']['total_return_pct'],
                'win_rate': result['trades']['win_rate'],
                'profit_factor': result['pnl']['profit_factor'],
                'total_trades': result['trades']['total']
            })
    
    df = pd.DataFrame(results)
    print(f"\n{'='*80}")
    print(f"SENSITIVITY ANALYSIS: {parameter}")
    print(f"{'='*80}")
    print(df.to_string(index=False))
    print(f"{'='*80}\n")
    
    return df


# ==============================
# MAIN
# ==============================

def main():
    """Main execution"""
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f'backtest_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        ]
    )
    
    # Stock universe
    SYMBOLS = [
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
        "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
        "MARUTI", "TATASTEEL", "WIPRO", "HCLTECH", "AXISBANK"
    ]
    
    # Base configuration
    config = StrategyConfig(
        initial_capital=100000,
        risk_per_trade=0.005,
        max_open_positions=5
    )
    
    # 1. Multi-timeframe backtest
    print("\n" + "="*80)
    print("MULTI-TIMEFRAME BACKTESTING")
    print("="*80 + "\n")
    
    results = run_multi_timeframe_backtest(SYMBOLS, config)
    
    # Save results
    with open('backtest_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    logging.info("Results saved to: backtest_results.json")
    
    # 2. Parameter sensitivity
    print("\n" + "="*80)
    print("PARAMETER SENSITIVITY ANALYSIS")
    print("="*80 + "\n")
    
    sensitivity = run_parameter_sensitivity(
        symbols=SYMBOLS,
        timeframe="1d_6m",
        parameter="risk_per_trade",
        values=[0.003, 0.005, 0.01, 0.015, 0.02]
    )
    
    sensitivity.to_csv('sensitivity_risk.csv', index=False)
    logging.info("Sensitivity results saved to: sensitivity_risk.csv")
    
    print("\n" + "="*80)
    print("BACKTESTING COMPLETE")
    print("="*80)


if __name__ == "__main__":
    main()
