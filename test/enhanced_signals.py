#!/usr/bin/env python
"""
Enhanced Signal Generator
=========================
Generates high-quality trading signals using multiple technical indicators.

Improvements:
- Technical analysis (RSI, SMA, ATR)
- Multi-factor confirmation
- Score-based entry quality
- Better risk/reward targets
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional, Union
import logging

logger = logging.getLogger(__name__)


class EnhancedSignalGenerator:
    """Generate better quality trading signals."""
    
    def __init__(self):
        self.rsi_period = 14
        self.sma_short = 20
        self.sma_long = 200
        self.atr_period = 14
        self.volume_period = 20
    
    def calculate_rsi(self, prices: Union[np.ndarray, pd.Series], period: int = 14) -> np.ndarray:
        """Calculate RSI (Relative Strength Index)."""
        # Convert to numpy array if needed
        if isinstance(prices, pd.Series):
            prices = prices.to_numpy()
        prices = np.asarray(prices, dtype=np.float64)
        
        deltas = np.diff(prices)
        seed = deltas[:period+1]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        rs = up / down if down != 0 else 0
        rsi = np.zeros_like(prices, dtype=np.float64)
        rsi[:period] = 100. - 100. / (1. + rs)
        
        for i in range(period, len(prices)):
            delta = deltas[i-1]
            if delta > 0:
                upval = delta
                downval = 0.
            else:
                upval = 0.
                downval = -delta
            
            up = (up * (period - 1) + upval) / period
            down = (down * (period - 1) + downval) / period
            rs = up / down if down != 0 else 0
            rsi[i] = 100. - 100. / (1. + rs)
        
        return rsi
    
    def calculate_sma(self, prices: Union[np.ndarray, pd.Series], period: int) -> np.ndarray:
        """Calculate Simple Moving Average."""
        # Convert to numpy array if needed
        if isinstance(prices, pd.Series):
            prices = prices.to_numpy()
        prices = np.asarray(prices, dtype=np.float64)
        
        sma = pd.Series(prices).rolling(window=period).mean().to_numpy()
        return sma
    
    def calculate_atr(self, high: Union[np.ndarray, pd.Series], 
                      low: Union[np.ndarray, pd.Series], 
                      close: Union[np.ndarray, pd.Series], 
                      period: int = 14) -> np.ndarray:
        """Calculate Average True Range."""
        # Convert to numpy arrays if needed
        if isinstance(high, pd.Series):
            high = high.to_numpy()
        if isinstance(low, pd.Series):
            low = low.to_numpy()
        if isinstance(close, pd.Series):
            close = close.to_numpy()
        
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)
        
        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - np.roll(close, 1)),
                np.abs(low - np.roll(close, 1))
            )
        )
        atr = pd.Series(tr).rolling(window=period).mean().to_numpy()
        return atr
    
    def analyze_bar(self, df: pd.DataFrame, index: int) -> Optional[Dict]:
        """
        Analyze a specific bar for signal quality.
        
        Args:
            df: OHLCV DataFrame with technical indicators
            index: Bar index to analyze
        
        Returns:
            Dict with signal quality metrics
        """
        if index < 20:
            return None
        
        bar = df.iloc[index]
        prev_bar = df.iloc[index - 1]
        
        # Get indicators
        price = bar['close']
        high = bar['high']
        low = bar['low']
        volume = bar['volume']
        rsi = df['rsi'].iloc[index]
        sma20 = df['sma20'].iloc[index]
        sma200 = df['sma200'].iloc[index]
        atr = df['atr'].iloc[index]
        avg_volume = df['volume'].rolling(self.volume_period).mean().iloc[index]
        
        factors = {}
        score = 0
        max_score = 100
        
        # Factor 1: Price above short-term MA (20)
        if price > sma20:
            factors['above_sma20'] = True
            score += 15
        else:
            factors['above_sma20'] = False
        
        # Factor 2: Price above long-term MA (200) - uptrend
        if price > sma200:
            factors['above_sma200'] = True
            score += 15
        else:
            factors['above_sma200'] = False
        
        # Factor 3: RSI in good range (50-70 = strong but not overbought)
        if 50 <= rsi <= 70:
            factors['rsi_optimal'] = True
            score += 20
        elif 40 <= rsi < 50:
            factors['rsi_optimal'] = True
            score += 10  # Less optimal
        else:
            factors['rsi_optimal'] = False
        
        # Factor 4: Volume confirmation
        if volume > avg_volume * 1.2:
            factors['volume_high'] = True
            score += 15
        else:
            factors['volume_high'] = False
        
        # Factor 5: Recent price movement
        sma5 = df['close'].rolling(5).mean().iloc[index]
        if price > sma5:
            factors['momentum_up'] = True
            score += 10
        else:
            factors['momentum_up'] = False
        
        # Factor 6: Not too far from SMA20 (not stretched)
        distance = ((price - sma20) / sma20) * 100
        if -2 < distance < 3:  # Within 3% above SMA20
            factors['price_near_sma'] = True
            score += 10
        else:
            factors['price_near_sma'] = False
        
        return {
            'price': price,
            'rsi': rsi,
            'sma20': sma20,
            'sma200': sma200,
            'atr': atr,
            'score': score,
            'factors': factors,
            'confirmed': score >= 60  # 60+ is good signal
        }
    
    def generate_signals(self, df: pd.DataFrame, min_score: int = 60) -> List[Tuple[int, Dict]]:
        """
        Generate trading signals from DataFrame.
        
        Args:
            df: OHLCV DataFrame
            min_score: Minimum signal score (0-100)
        
        Returns:
            List of (bar_index, signal_info) tuples
        """
        # Calculate indicators
        rsi_result = self.calculate_rsi(df['close'].to_numpy(), self.rsi_period)
        df['rsi'] = rsi_result
        
        sma20_result = self.calculate_sma(df['close'].to_numpy(), self.sma_short)
        df['sma20'] = sma20_result
        
        sma200_result = self.calculate_sma(df['close'].to_numpy(), self.sma_long)
        df['sma200'] = sma200_result
        
        atr_result = self.calculate_atr(df['high'].to_numpy(), df['low'].to_numpy(), df['close'].to_numpy(), self.atr_period)
        df['atr'] = atr_result
        
        signals = []
        
        # Find signal bars
        for i in range(20, len(df)):
            analysis = self.analyze_bar(df, i)
            
            if analysis and analysis['score'] >= min_score:
                signals.append((i, analysis))
        
        return signals
    
    def get_signal_quality(self, score: int) -> str:
        """Get quality description for score."""
        if score >= 85:
            return "Excellent [*****]"
        elif score >= 75:
            return "Strong [****]"
        elif score >= 65:
            return "Good [***]"
        elif score >= 60:
            return "Fair [**]"
        else:
            return "Weak [*]"


def test_enhanced_signals():
    """Test the enhanced signal generator."""
    import yfinance as yf
    
    print("\n" + "="*70)
    print("TESTING ENHANCED SIGNAL GENERATOR")
    print("="*70)
    
    # Fetch data
    print("\nFetching data for SBIN.NS...")
    ticker = yf.Ticker('SBIN.NS')
    df = ticker.history(period='1y', interval='1d')
    df = df.reset_index()
    df.columns = df.columns.str.lower()
    df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
    
    print(f"Loaded {len(df)} bars")
    
    # Generate signals
    generator = EnhancedSignalGenerator()
    signals = generator.generate_signals(df, min_score=60)
    
    print(f"\nFound {len(signals)} high-quality signals")
    
    if signals:
        print("\nTop signals:")
        print("-"*70)
        
        for i, (bar_idx, signal) in enumerate(signals[:10], 1):
            bar_date = df.iloc[bar_idx]['date']
            quality = generator.get_signal_quality(signal['score'])
            
            print(f"\n{i}. Bar {bar_idx} ({bar_date})")
            print(f"   Price: Rs{signal['price']:.2f}")
            print(f"   Score: {signal['score']}/100 {quality}")
            print(f"   RSI: {signal['rsi']:.1f}")
            print(f"   SMA20: Rs{signal['sma20']:.2f}")
            print(f"   ATR: Rs{signal['atr']:.2f}")
            print(f"   Factors met: {sum(1 for v in signal['factors'].values() if v)}/6")
    
    print("\n" + "="*70)
    print(f"Signal Generation Complete!")
    print(f"Win rate target: 60%+ with these signals")
    print("="*70)


if __name__ == '__main__':
    test_enhanced_signals()
