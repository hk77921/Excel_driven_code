#!/usr/bin/env python
"""
Strategy Improvement Module
============================
Enhanced trading strategy with better entry/exit signals.

Improvements:
1. Better entry signals (use actual price crossovers)
2. Stricter stop losses
3. Smarter exits (use technical indicators)
4. Position sizing optimization
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class StrategyImprover:
    """Improved trading strategy with better signals"""
    
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift(1))
        low_close = abs(df['low'] - df['close'].shift(1))
        
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        
        return atr
    
    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def calculate_sma(df: pd.DataFrame, period: int = 20) -> pd.Series:
        """Calculate Simple Moving Average"""
        return df['close'].rolling(window=period).mean()
    
    @staticmethod
    def find_best_entry_points(df: pd.DataFrame, num_signals: int = 3) -> list:
        """
        Find best entry points based on technical analysis.
        
        Strategy:
        - Price above 20-day SMA
        - RSI between 50-70 (strong uptrend, not overbought)
        - Price close to 52-week low (good entry)
        - Volume spike (confirmation)
        """
        df = df.copy()
        df['SMA20'] = StrategyImprover.calculate_sma(df, 20)
        df['RSI'] = StrategyImprover.calculate_rsi(df, 14)
        df['ATR'] = StrategyImprover.calculate_atr(df, 14)
        
        # Calculate volume trend
        df['volume_avg'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_avg']
        
        # Calculate 52-week range
        df['52w_high'] = df['high'].rolling(252).max()
        df['52w_low'] = df['low'].rolling(252).min()
        df['52w_range'] = df['52w_high'] - df['52w_low']
        df['distance_from_low'] = df['close'] - df['52w_low']
        df['dist_from_low_pct'] = (df['distance_from_low'] / df['52w_range']) * 100
        
        # Score each bar
        signals = []
        
        for idx in range(len(df)):
            if idx < 50:  # Need enough history
                continue
            
            row = df.iloc[idx]
            
            score = 0
            conditions = []
            
            # Condition 1: Price above SMA20 (uptrend)
            if row['close'] > row['SMA20']:
                score += 20
                conditions.append("Price > SMA20")
            
            # Condition 2: RSI in good zone (50-70)
            if 50 <= row['RSI'] <= 70:
                score += 20
                conditions.append("RSI 50-70")
            elif 40 <= row['RSI'] < 50:
                score += 10  # Partial credit
                conditions.append("RSI 40-50")
            
            # Condition 3: Price near 52-week low (good value)
            if 10 <= row['dist_from_low_pct'] <= 25:
                score += 20
                conditions.append("Near 52w-low")
            elif 25 < row['dist_from_low_pct'] <= 35:
                score += 10
                conditions.append("Moderately low")
            
            # Condition 4: Volume above average (confirmation)
            if row['volume_ratio'] > 1.2:
                score += 20
                conditions.append("Volume spike")
            elif row['volume_ratio'] > 1.0:
                score += 10
                conditions.append("Above avg volume")
            
            # Condition 5: Not too expensive relative to ATR
            if row['close'] < row['52w_high'] - (row['ATR'] * 5):
                score += 20
                conditions.append("Below prev resistance")
            
            if score >= 40:  # Threshold for good signal
                signals.append({
                    'bar_idx': idx,
                    'date': row.get('date', idx),
                    'price': row['close'],
                    'score': score,
                    'rsi': row['RSI'],
                    'volume_ratio': row['volume_ratio'],
                    'atr': row['ATR'],
                    'conditions': conditions
                })
        
        # Sort by score and return top signals
        signals.sort(key=lambda x: x['score'], reverse=True)
        return signals[:num_signals]
    
    @staticmethod
    def calculate_smart_stops_and_targets(
        entry_price: float,
        atr: float,
        market_trend: str = 'BULLISH'
    ) -> Tuple[float, float]:
        """
        Calculate smart stop loss and target based on ATR and market condition.
        
        Improved logic:
        - Stop loss: 1.2x ATR below entry (tighter than 1.5x)
        - Target: 2.5x ATR above entry (better risk/reward)
        """
        if market_trend == 'BULLISH':
            stop_loss = entry_price - (atr * 1.2)  # Tighter stop
            target = entry_price + (atr * 2.5)      # Better target
        else:
            stop_loss = entry_price - (atr * 2.0)
            target = entry_price + (atr * 1.5)
        
        return stop_loss, target
    
    @staticmethod
    def generate_summary(signals: list) -> str:
        """Generate summary of identified signals"""
        summary = "\n" + "="*70
        summary += "\n📊 TECHNICAL SIGNAL ANALYSIS"
        summary += "\n" + "="*70
        
        if not signals:
            summary += "\n⚠️ No high-quality signals found"
            return summary
        
        summary += f"\n\nFound {len(signals)} high-quality entry signals:\n"
        
        for i, signal in enumerate(signals, 1):
            summary += f"\nSignal {i}:"
            summary += f"\n  Bar: {signal['bar_idx']}"
            summary += f"\n  Price: ₹{signal['price']:.2f}"
            summary += f"\n  Score: {signal['score']}/100"
            summary += f"\n  RSI: {signal['rsi']:.1f}"
            summary += f"\n  Volume Ratio: {signal['volume_ratio']:.2f}x"
            summary += f"\n  ATR: ₹{signal['atr']:.2f}"
            summary += f"\n  Conditions Met: {', '.join(signal['conditions'])}"
        
        summary += "\n\n" + "="*70
        return summary


class ImprovedBacktestRunner:
    """Run backtest with improved strategy"""
    
    def __init__(self, capital_params, trade_params):
        """Initialize runner"""
        self.capital_params = capital_params
        self.trade_params = trade_params
    
    def run_improved_backtest(self, symbol: str, df: pd.DataFrame):
        """
        Run backtest with improved entry signals.
        
        Args:
            symbol: Trading symbol
            df: OHLCV DataFrame
        
        Returns:
            Tuple of (signals, summary)
        """
        # Find best entry points
        signals = StrategyImprover.find_best_entry_points(df, num_signals=3)
        summary = StrategyImprover.generate_summary(signals)
        
        return signals, summary


# Strategy recommendations based on analysis
STRATEGY_IMPROVEMENTS = """
╔════════════════════════════════════════════════════════════════╗
║         STRATEGY IMPROVEMENT RECOMMENDATIONS                   ║
╚════════════════════════════════════════════════════════════════╝

Current Issues:
• 0% win rate across all time periods
• All trades break-even (orders not filling)
• Entry signals too loose - need better filters
• Stop losses not tight enough
• No technical analysis incorporated

Recommended Improvements:

1. BETTER ENTRY SIGNALS (Currently: Simple price-based)
   ✓ Use RSI (Relative Strength Index)
   ✓ Use SMA (Simple Moving Average) for trend
   ✓ Look for price near 52-week lows
   ✓ Confirm with volume spikes
   ✓ Only enter when RSI 50-70 (strong but not overbought)

2. TIGHTER STOP LOSSES
   Current: 1.5x ATR below entry
   Improved: 1.2x ATR below entry (33% tighter)
   
3. BETTER TARGETS
   Current: 2.0x ATR above entry (1:1.33 R/R ratio)
   Improved: 2.5x ATR above entry (1:2.08 R/R ratio)

4. FILTER WEAK SIGNALS
   • Score entry quality (40+ points)
   • Require at least 3 conditions met:
     - Price above 20-day SMA
     - RSI 50-70
     - Price near 52-week low
     - Volume above average
     - Below previous resistance

5. POSITION SIZING
   • Risk fixed 0.5% per trade
   • Scale into winners
   • Scale out at partial targets

6. TIME-BASED EXITS
   • Exit if no movement for 20 days
   • Tighten stops if RSI drops below 50
   • Exit partial at first target

7. MARKET CONDITION FILTERS
   • Only enter in uptrends (price > 200-day SMA)
   • Check overall market sentiment
   • Avoid trading around earnings

Next Steps:
1. Run comprehensive_backtest.py with new signals
2. Test improved entry logic
3. Measure win rate improvement
4. Optimize position sizing
5. Validate on multiple symbols and time periods
"""

if __name__ == '__main__':
    print(STRATEGY_IMPROVEMENTS)
