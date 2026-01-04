"""
Market Regime Manager
===================
Detects current market conditions and provides regime-appropriate timing rules.

Market Regimes:
- BULL_MARKET: Strong uptrend, aggressive entry timing
- BEAR_MARKET: Downtrend, defensive timing
- SIDEWAYS: Range-bound, selective timing  
- HIGH_VOLATILITY: Volatile conditions, cautious timing
"""

import logging
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from enum import Enum

from .timing_rules import TimingRules, BullMarketRules, BearMarketRules, SidewaysRules, VolatilityRules


logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    BULL_MARKET = "BULL"
    BEAR_MARKET = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "VOLATILE"


class MarketRegimeManager:
    """
    Detects and manages market regimes for timing decisions.
    """
    
    def __init__(self, index_symbol: str = "^NSEI", lookback_days: int = 60):
        """
        Initialize market regime manager.
        
        Args:
            index_symbol: Index symbol for regime detection (NIFTY)
            lookback_days: Days of historical data for analysis
        """
        self.index_symbol = index_symbol
        self.lookback_days = lookback_days
        self.current_regime = MarketRegime.SIDEWAYS
        self.regime_confidence = 0.5
        self.last_update = None
        
        # Regime detection parameters
        self.bull_threshold = 0.02  # 2% above 20-day MA
        self.bear_threshold = -0.02  # 2% below 20-day MA
        self.volatility_threshold = 0.025  # 2.5% daily volatility
        
        logger.info(f"Market regime manager initialized for {index_symbol}")
    
    def detect_regime(self) -> Tuple[MarketRegime, float]:
        """
        Detect current market regime based on index analysis.
        
        Returns:
            (regime, confidence_score)
        """
        try:
            # Get recent market data with better error handling
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.lookback_days + 20)  # Extra buffer
            
            # Fetch index data with retries
            index_data = None
            for attempt in range(2):
                try:
                    index_data = yf.download(
                        self.index_symbol,
                        start=start_date,
                        end=end_date,
                        progress=False,
                        auto_adjust=True,
                        timeout=10
                    )
                    if index_data is not None and len(index_data) >= 10:
                        break
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} to fetch index data failed: {e}")
                    if attempt == 0:
                        # Try with shorter period on first failure
                        start_date = end_date - timedelta(days=30)
            
            if index_data is None or len(index_data) < 10:
                logger.warning(f"Insufficient data for regime detection: got {len(index_data) if index_data is not None else 0} days, using conservative defaults")
                return MarketRegime.SIDEWAYS, 0.6
            
            # Calculate indicators
            if index_data is None or 'Close' not in index_data:
                logger.error("Invalid index data structure")
                return MarketRegime.SIDEWAYS, 0.5
                
            close_prices = index_data['Close']
            
            # Ensure we have enough data and adapt calculations accordingly
            data_length = len(close_prices)
            if data_length < 20:
                logger.warning(f"Very limited price data ({data_length} days) - using simplified analysis")
                # Use shorter periods for limited data
                ma_period = max(5, data_length // 3)
                ma_20 = close_prices.rolling(ma_period).mean()
                ma_50 = ma_20  # Same MA when data is limited
            elif data_length < 50:
                logger.info(f"Limited price data ({data_length} days) - using adapted analysis")
                # Use 20-day MA and shorter 30-day MA instead of 50
                ma_20 = close_prices.rolling(20).mean()
                ma_50 = close_prices.rolling(min(30, data_length)).mean()
            else:
                ma_20 = close_prices.rolling(20).mean()
                ma_50 = close_prices.rolling(50).mean()
            
            # Current position relative to MAs (use .iloc[-1] to get scalar values)
            current_price = close_prices.iloc[-1].item() if len(close_prices) > 0 else 0
            current_ma20 = ma_20.iloc[-1].item() if len(ma_20) > 0 else current_price
            current_ma50 = ma_50.iloc[-1].item() if len(ma_50) > 0 else current_ma20
            
            # Price momentum (ensure scalars)
            price_vs_ma20 = float((current_price - current_ma20) / current_ma20) if current_ma20 != 0 else 0.0
            ma20_vs_ma50 = float((current_ma20 - current_ma50) / current_ma50) if current_ma50 != 0 else 0.0
            
            # Volatility (ensure scalar)
            returns = close_prices.pct_change().dropna()
            if len(returns) >= 10:
                volatility_series = returns.tail(10).std()
                volatility = float(volatility_series.iloc[0]) if hasattr(volatility_series, 'iloc') else float(volatility_series)
            else:
                volatility = 0.0  # 10-day volatility
            
            # Trend strength (ensure we have enough data)
            trend_days = min(5, len(close_prices) - 1)
            recent_trend = float((current_price - close_prices.iloc[-trend_days].item()) / close_prices.iloc[-trend_days].item()) if trend_days > 0 else 0.0
            
            # Regime detection logic
            confidence = 0.6  # Base confidence
            
            # High volatility check first
            if volatility > self.volatility_threshold:
                regime = MarketRegime.HIGH_VOLATILITY
                confidence = min(0.9, volatility / self.volatility_threshold * 0.7)
                
            # Bull market conditions (check individual conditions to avoid series comparison)
            elif (abs(price_vs_ma20) > abs(self.bull_threshold) and 
                  price_vs_ma20 > self.bull_threshold and
                  ma20_vs_ma50 > 0 and 
                  recent_trend > 0.01):  # 1% recent gain
                regime = MarketRegime.BULL_MARKET
                confidence = min(0.9, abs(price_vs_ma20) * 10)  # Use abs for confidence calculation
                
            # Bear market conditions (check individual conditions)
            elif (abs(price_vs_ma20) > abs(self.bear_threshold) and
                  price_vs_ma20 < self.bear_threshold and
                  ma20_vs_ma50 < 0 and
                  recent_trend < -0.01):  # 1% recent loss
                regime = MarketRegime.BEAR_MARKET  
                confidence = min(0.9, abs(price_vs_ma20) * 10)
                
            # Sideways market (default)
            else:
                regime = MarketRegime.SIDEWAYS
                confidence = 0.6
            
            # Cache results
            self.current_regime = regime
            self.regime_confidence = confidence
            self.last_update = datetime.now()
            
            logger.info(
                f"Market regime: {regime.value} "
                f"(confidence: {confidence:.2f}) | "
                f"Price vs MA20: {price_vs_ma20:.2%}, "
                f"Volatility: {volatility:.2%}"
            )
            
            return regime, confidence
            
        except Exception as e:
            logger.error(f"Regime detection failed: {e}")
            return MarketRegime.SIDEWAYS, 0.5
    
    def get_timing_rules(self, regime: Optional[MarketRegime] = None) -> TimingRules:
        """
        Get timing rules for current or specified regime.
        
        Args:
            regime: Optional specific regime, uses current if None
            
        Returns:
            TimingRules instance for the regime
        """
        if regime is None:
            regime = self.current_regime
        
        rules_map = {
            MarketRegime.BULL_MARKET: BullMarketRules(),
            MarketRegime.BEAR_MARKET: BearMarketRules(),
            MarketRegime.SIDEWAYS: SidewaysRules(),
            MarketRegime.HIGH_VOLATILITY: VolatilityRules()
        }
        
        return rules_map.get(regime, SidewaysRules())
    
    def should_trade_now(self) -> bool:
        """
        Global decision on whether trading should be active.
        
        Returns:
            True if market conditions allow trading
        """
        # Update regime if stale (older than 1 hour)
        if (self.last_update is None or 
            datetime.now() - self.last_update > timedelta(hours=1)):
            self.detect_regime()
        
        # Don't trade in extremely volatile conditions with low confidence
        if (self.current_regime == MarketRegime.HIGH_VOLATILITY and 
            self.regime_confidence > 0.8):
            logger.warning("Extreme volatility detected - pausing trading")
            return False
        
        # Don't trade in strong bear market with high confidence
        if (self.current_regime == MarketRegime.BEAR_MARKET and 
            self.regime_confidence > 0.85):
            logger.warning("Strong bear market - limiting trading")  
            return False
        
        return True
    
    def get_regime_info(self) -> Dict:
        """
        Get current regime information for logging/monitoring.
        
        Returns:
            Dict with regime details
        """
        # Auto-refresh if data is stale (older than 5 minutes for monitoring)
        if (self.last_update is None or 
            datetime.now() - self.last_update > timedelta(minutes=5)):
            try:
                self.detect_regime()
            except Exception as e:
                logger.warning(f"Auto-refresh regime failed: {e}")
        
        return {
            'regime': self.current_regime.value,
            'confidence': self.regime_confidence,
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'should_trade': self.should_trade_now(),
            'minutes_since_update': int((datetime.now() - self.last_update).total_seconds() / 60) if self.last_update else None
        }
    
    def get_market_regime(self) -> Tuple[MarketRegime, float]:
        """Get current market regime (alias for detect_regime)"""
        return self.detect_regime()