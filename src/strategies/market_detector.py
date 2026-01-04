"""
Enhanced Market Direction Detector (Real-Time)
==============================================
Comprehensive real-time market analysis for NIFTY50/BANKNIFTY to power adaptive strategies.

Features:
- Real-time candle-by-candle analysis
- Instant gap detection and analysis  
- Reactive market momentum measurement
- Real-time volatility regime detection
- Dynamic support/resistance levels
- Live opening sentiment analysis

Author: GitHub Copilot
"""

import logging
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import numpy as np
from datetime import datetime, date, time, timedelta
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum

from src.core.realtime_monitor import RealtimeMarketMonitor, UpdateTrigger, MarketUpdate
from src.core.confidence_manager import ReactiveConfidenceManager
from src.core.data_risk_mitigator import DataSourceRiskMitigator, DataSourceType


logger = logging.getLogger(__name__)


class MarketDirection(str, Enum):
    """Market direction states"""
    STRONG_BULLISH = "STRONG_BULLISH"
    BULLISH = "BULLISH"
    WEAK_BULLISH = "WEAK_BULLISH"
    NEUTRAL = "NEUTRAL"
    WEAK_BEARISH = "WEAK_BEARISH"
    BEARISH = "BEARISH"
    STRONG_BEARISH = "STRONG_BEARISH"


class GapType(str, Enum):
    """Types of market gaps"""
    NO_GAP = "NO_GAP"
    GAP_UP_SMALL = "GAP_UP_SMALL"     # 0.5-1%
    GAP_UP_MEDIUM = "GAP_UP_MEDIUM"   # 1-2%
    GAP_UP_LARGE = "GAP_UP_LARGE"     # >2%
    GAP_DOWN_SMALL = "GAP_DOWN_SMALL" # 0.5-1%
    GAP_DOWN_MEDIUM = "GAP_DOWN_MEDIUM" # 1-2%
    GAP_DOWN_LARGE = "GAP_DOWN_LARGE" # >2%


class VolatilityRegime(str, Enum):
    """Market volatility states"""
    LOW = "LOW"         # <15 VIX
    NORMAL = "NORMAL"   # 15-25 VIX
    HIGH = "HIGH"       # 25-35 VIX
    EXTREME = "EXTREME" # >35 VIX


@dataclass
class MarketState:
    """Comprehensive market state analysis"""
    direction: MarketDirection
    confidence: float
    gap_type: GapType
    gap_size_pct: float
    volatility_regime: VolatilityRegime
    momentum_score: float
    trend_strength: float
    opening_sentiment: str
    nifty_rsi: float
    banknifty_rsi: float
    nifty_price: float
    banknifty_price: float
    support_level: float
    resistance_level: float
    timestamp: datetime
    
    def is_bullish(self) -> bool:
        return self.direction in [MarketDirection.BULLISH, MarketDirection.STRONG_BULLISH, MarketDirection.WEAK_BULLISH]
    
    def is_bearish(self) -> bool:
        return self.direction in [MarketDirection.BEARISH, MarketDirection.STRONG_BEARISH, MarketDirection.WEAK_BEARISH]
    
    def is_gap_up(self) -> bool:
        return self.gap_type in [GapType.GAP_UP_SMALL, GapType.GAP_UP_MEDIUM, GapType.GAP_UP_LARGE]
    
    def is_gap_down(self) -> bool:
        return self.gap_type in [GapType.GAP_DOWN_SMALL, GapType.GAP_DOWN_MEDIUM, GapType.GAP_DOWN_LARGE]
    
    def is_high_volatility(self) -> bool:
        return self.volatility_regime in [VolatilityRegime.HIGH, VolatilityRegime.EXTREME]


class EnhancedMarketDetector:
    """
    Enhanced real-time market direction detector for adaptive strategies.
    
    Analyzes NIFTY50 and BANKNIFTY with real-time candle-by-candle updates
    to provide instant market state changes for reactive trading decisions.
    """
    
    def __init__(self):
        """Initialize real-time market detector"""
        self.nifty_symbol = "^NSEI"
        self.banknifty_symbol = "^NSEBANK"
        # Try multiple VIX symbols as fallback
        self.vix_symbols = [ "^VIX", "INDIAVIX.NS"]
        
        # Initialize real-time components
        self.confidence_manager = ReactiveConfidenceManager()
        self.realtime_monitor = RealtimeMarketMonitor(
            confidence_manager=self.confidence_manager,
            update_interval_seconds=60  # 1-minute candles
        )
        
        # Initialize data risk mitigator
        self.data_mitigator = DataSourceRiskMitigator()
        
        # Cache for market data
        self.data_cache = {}
        self.last_update = {}
        
        # Real-time market state cache
        self.current_market_state: Optional[MarketState] = None
        self.last_state_update: Optional[datetime] = None
        
        # Thresholds for classification
        self.gap_thresholds = {
            'small': 0.5,   # 0.5%
            'medium': 1.0,  # 1%
            'large': 2.0    # 2%
        }
        
        self.momentum_period = 14
        self.volatility_period = 20
        
        # Register for real-time updates
        self._register_realtime_callbacks()
        
        # Start real-time monitoring
        self.realtime_monitor.start_monitoring()
        
        # Add indices to monitoring (with default prices)
        self.realtime_monitor.add_symbol(self.nifty_symbol, 24000.0)  # Default Nifty price
        self.realtime_monitor.add_symbol(self.banknifty_symbol, 52000.0)  # Default Bank Nifty price
        
        logger.info("Enhanced real-time market detector initialized")
    
    def _register_realtime_callbacks(self) -> None:
        """Register callbacks for real-time market updates"""
        
        # React to candle closes for immediate updates
        self.realtime_monitor.register_callback(
            UpdateTrigger.CANDLE_CLOSE, 
            self._on_candle_close
        )
        
        # React to significant price movements
        self.realtime_monitor.register_callback(
            UpdateTrigger.PRICE_THRESHOLD,
            self._on_price_threshold_breach
        )
        
        # React to volatility spikes
        self.realtime_monitor.register_callback(
            UpdateTrigger.VOLATILITY_SPIKE,
            self._on_volatility_spike
        )
        
        # React to regime changes
        self.realtime_monitor.register_callback(
            UpdateTrigger.REGIME_CHANGE,
            self._on_regime_change
        )
        
        logger.info("Registered real-time callbacks for market events")
    
    def _on_candle_close(self, update: MarketUpdate) -> None:
        """Handle candle close events"""
        logger.debug(f"Candle close: {update.symbol} at {update.data['price']}")
        
        # Invalidate cached market state to force refresh
        self.current_market_state = None
        self.last_state_update = None
        
        # Update real-time monitoring with new price
        if update.symbol in [self.nifty_symbol, self.banknifty_symbol]:
            # Force market state recalculation for index updates
            self._force_market_state_update()
    
    def _on_price_threshold_breach(self, update: MarketUpdate) -> None:
        """Handle significant price movements"""
        logger.warning(f"Price threshold breach: {update.symbol} - {update.data['price_change_pct']:.2%}")
        
        # Invalidate market state for immediate recalculation
        self.current_market_state = None
        
        # If it's an index, force immediate update
        if update.symbol in [self.nifty_symbol, self.banknifty_symbol]:
            self._force_market_state_update()
    
    def _on_volatility_spike(self, update: MarketUpdate) -> None:
        """Handle volatility spikes"""
        logger.warning(f"Volatility spike detected: {update.symbol} - {update.data['volatility']:.2%}")
        
        # Force market state update due to volatility regime change
        self._force_market_state_update()
    
    def _on_regime_change(self, update: MarketUpdate) -> None:
        """Handle market regime changes"""
        logger.warning(f"Regime change: {update.symbol} - {update.data}")
        
        # Invalidate all cached states
        self.current_market_state = None
        self.data_cache.clear()
        
        # Force immediate market state recalculation
        self._force_market_state_update()
    
    def _force_market_state_update(self) -> None:
        """Force immediate market state update"""
        try:
            # Clear cache to ensure fresh data
            self.current_market_state = None
            self.last_state_update = None
            
            # Recalculate market state
            new_state = self.get_current_market_state()
            
            logger.info(f"Forced market state update: {new_state.direction.value} (confidence: {new_state.confidence:.2f})")
            
        except Exception as e:
            logger.error(f"Error forcing market state update: {e}")
    
    def get_current_market_state(self) -> MarketState:
        """
        Get comprehensive current market state with real-time updates.
        
        Returns:
            MarketState with all analysis (cached for 30 seconds max)
        """
        try:
            # Check if we have a recent cached state (max 30 seconds old for real-time)
            current_time = datetime.now()
            if (self.current_market_state is not None and 
                self.last_state_update is not None and
                (current_time - self.last_state_update).total_seconds() < 30):
                return self.current_market_state
            
            # Get real-time data for both indices
            nifty_data = self._fetch_intraday_data(self.nifty_symbol)
            banknifty_data = self._fetch_intraday_data(self.banknifty_symbol)
            
            if nifty_data.empty or banknifty_data.empty:
                return self._get_default_state()
            
            # Update real-time monitor with latest prices
            nifty_price = float(nifty_data['Close'].iloc[-1])
            banknifty_price = float(banknifty_data['Close'].iloc[-1])
            
            self.realtime_monitor.update_symbol_data(self.nifty_symbol, nifty_price)
            self.realtime_monitor.update_symbol_data(self.banknifty_symbol, banknifty_price)
            
            # Analyze market direction with real-time context
            direction, confidence = self._analyze_market_direction_realtime(nifty_data, banknifty_data)
            
            # Detect gaps with real-time validation
            gap_type, gap_size = self._detect_gap_realtime(nifty_data)
            
            # Analyze volatility using real-time data
            volatility_regime = self._analyze_volatility_realtime()
            
            # Calculate momentum and trend with real-time updates
            momentum_score = self._calculate_momentum_realtime(nifty_data, banknifty_data)
            trend_strength = self._calculate_trend_strength(nifty_data)
            
            # Opening sentiment with real-time context
            opening_sentiment = self._analyze_opening_sentiment(nifty_data, banknifty_data)
            
            # Support/Resistance levels
            support, resistance = self._calculate_levels(nifty_data)
            
            # RSI values
            nifty_rsi = self._calculate_rsi(nifty_data)
            banknifty_rsi = self._calculate_rsi(banknifty_data)
            
            state = MarketState(
                direction=direction,
                confidence=confidence,
                gap_type=gap_type,
                gap_size_pct=gap_size,
                volatility_regime=volatility_regime,
                momentum_score=momentum_score,
                trend_strength=trend_strength,
                opening_sentiment=opening_sentiment,
                nifty_rsi=nifty_rsi,
                banknifty_rsi=banknifty_rsi,
                nifty_price=nifty_price,
                banknifty_price=banknifty_price,
                support_level=support,
                resistance_level=resistance,
                timestamp=datetime.now()
            )
            
            # Cache the state with timestamp
            self.current_market_state = state
            self.last_state_update = current_time
            
            logger.info(f"Market State (Real-time): {direction.value} ({confidence:.2f}), Gap: {gap_type.value} ({gap_size:.2f}%)")
            return state
            
        except Exception as e:
            logger.error(f"Failed to analyze market state: {e}")
            return self._get_default_state()
    
    def _analyze_market_direction_realtime(self, nifty_data: pd.DataFrame, banknifty_data: pd.DataFrame) -> Tuple[MarketDirection, float]:
        """Analyze market direction with real-time considerations"""
        
        # Get real-time states for context
        nifty_rt_state = self.realtime_monitor.get_realtime_state(self.nifty_symbol)
        banknifty_rt_state = self.realtime_monitor.get_realtime_state(self.banknifty_symbol)
        
        # Use traditional analysis as base
        direction, confidence = self._analyze_market_direction(nifty_data, banknifty_data)
        
        # Adjust based on real-time momentum and volatility
        if nifty_rt_state and banknifty_rt_state:
            # Strong real-time momentum can override traditional analysis
            #avg_momentum = (nifty_rt_state.momentum + banknifty_rt_state.momentum) / 2

            nifty_mom = self._safe_rt_value(nifty_rt_state, "momentum", 0.0)
            bank_mom = self._safe_rt_value(banknifty_rt_state, "momentum", 0.0)

            avg_momentum = (nifty_mom + bank_mom) / 2
            
            # High momentum with low volatility = strong directional move
            #avg_volatility = (nifty_rt_state.volatility_5min + banknifty_rt_state.volatility_5min) / 2

            nifty_vol = self._safe_rt_value(nifty_rt_state, "volatility_5min", 0.0)
            bank_vol = self._safe_rt_value(banknifty_rt_state, "volatility_5min", 0.0)

            avg_volatility = (nifty_vol + bank_vol) / 2


            
            if abs(avg_momentum) > 2.0 and avg_volatility < 0.025:  # Strong momentum, low volatility
                confidence = min(0.95, confidence * 1.2)
                
                if avg_momentum > 2.0 and direction.value.endswith('BEARISH'):
                    direction = MarketDirection.BULLISH  # Override to bullish
                elif avg_momentum < -2.0 and direction.value.endswith('BULLISH'):
                    direction = MarketDirection.BEARISH  # Override to bearish
        
        return direction, confidence
    
    def _detect_gap_realtime(self, nifty_data: pd.DataFrame) -> Tuple[GapType, float]:
        """Detect gaps with real-time validation"""
        
        # Traditional gap detection
        gap_type, gap_size = self._detect_gap(nifty_data)
        
        # Validate with real-time price action
        nifty_rt_state = self.realtime_monitor.get_realtime_state(self.nifty_symbol)
        
        if nifty_rt_state and nifty_rt_state.get('candle_count', 0) > 5:  # At least 5 candles since open
            # Check if gap is filling based on real-time price action
            if gap_type != GapType.NO_GAP:
                # If price has moved significantly against gap direction, reduce gap classification
                if ((gap_type.value.startswith('GAP_UP') and nifty_rt_state.get('price_change_pct', 0) < -0.005) or
                    (gap_type.value.startswith('GAP_DOWN') and nifty_rt_state.get('price_change_pct', 0) > 0.005)):
                    
                    # Downgrade gap significance due to filling action
                    if gap_type in [GapType.GAP_UP_LARGE, GapType.GAP_DOWN_LARGE]:
                        gap_type = GapType.GAP_UP_MEDIUM if gap_type == GapType.GAP_UP_LARGE else GapType.GAP_DOWN_MEDIUM
                    elif gap_type in [GapType.GAP_UP_MEDIUM, GapType.GAP_DOWN_MEDIUM]:
                        gap_type = GapType.GAP_UP_SMALL if gap_type == GapType.GAP_UP_MEDIUM else GapType.GAP_DOWN_SMALL
                    elif gap_type in [GapType.GAP_UP_SMALL, GapType.GAP_DOWN_SMALL]:
                        gap_type = GapType.NO_GAP
                        gap_size = 0.0
        
        return gap_type, gap_size
    
    def _analyze_volatility_realtime(self) -> VolatilityRegime:
        """Analyze volatility using real-time data"""
        
        # Get real-time volatility from monitoring
        nifty_rt_state = self.realtime_monitor.get_realtime_state(self.nifty_symbol)
        banknifty_rt_state = self.realtime_monitor.get_realtime_state(self.banknifty_symbol)
        
        if nifty_rt_state and banknifty_rt_state:
            # Use real-time volatility calculation
            nifty_vol = self._safe_rt_value(nifty_rt_state, "volatility_5min", 0.02)
            bank_vol = self._safe_rt_value(banknifty_rt_state, "volatility_5min", 0.02)
            avg_volatility = (nifty_vol + bank_vol) / 2
            
            # Convert to annualized volatility for VIX-like comparison
            annualized_vol = avg_volatility * np.sqrt(252) * 100
            
            if annualized_vol > 35:
                return VolatilityRegime.EXTREME
            elif annualized_vol > 25:
                return VolatilityRegime.HIGH
            elif annualized_vol > 15:
                return VolatilityRegime.NORMAL
            else:
                return VolatilityRegime.LOW
        
        # Fallback to traditional analysis
        return self._analyze_volatility()
    
    def _calculate_momentum_realtime(self, nifty_data: pd.DataFrame, banknifty_data: pd.DataFrame) -> float:
        """Calculate momentum with real-time context"""
        
        # Traditional momentum calculation
        base_momentum = self._calculate_momentum(nifty_data, banknifty_data)
        
        # Enhance with real-time momentum
        nifty_rt_state = self.realtime_monitor.get_realtime_state(self.nifty_symbol)
        banknifty_rt_state = self.realtime_monitor.get_realtime_state(self.banknifty_symbol)
        
        if nifty_rt_state and banknifty_rt_state:
            # Blend traditional and real-time momentum
            #realtime_momentum = (nifty_rt_state.momentum + banknifty_rt_state.momentum) / 2
            
            nifty_mom = self._safe_rt_value(nifty_rt_state, "momentum", 0.0)
            bank_mom = self._safe_rt_value(banknifty_rt_state, "momentum", 0.0)

            realtime_momentum = (nifty_mom + bank_mom) / 2


            # Weight recent real-time momentum higher if significant
            if abs(realtime_momentum) > 1.0:  # Significant real-time momentum
                momentum_score = 0.3 * base_momentum + 0.7 * (50 + realtime_momentum * 10)
            else:
                momentum_score = 0.7 * base_momentum + 0.3 * (50 + realtime_momentum * 10)
            
            return max(0, min(100, momentum_score))
        
        return base_momentum
    
    def _fetch_intraday_data(self, symbol: str, period: str = "1d", interval: str = "5m") -> pd.DataFrame:
        """Fetch intraday data with risk mitigation and validation"""
        cache_key = f"{symbol}_{interval}"
        now = datetime.now()
        
        # Check cache (reduced to 2 minute refresh for more real-time data)
        if (cache_key in self.last_update and 
            (now - self.last_update[cache_key]).seconds < 120 and
            cache_key in self.data_cache):
            return self.data_cache[cache_key]
        
        try:
            # Use data risk mitigator for validated data
            validated_data_point = self.data_mitigator.fetch_validated_data(symbol)
            
            # Fall back to traditional yfinance if risk mitigator fails
            if validated_data_point is None or validated_data_point.empty:
                logger.warning(f"Using fallback data fetch for {symbol}")
                data = yf.download(symbol, period=period, interval=interval, progress=False, timeout=5)
            else:
                # Use the validated data directly since it returns a DataFrame
                data = validated_data_point
                logger.debug(f"Using validated data for {symbol}")
            
            if data is not None and data.size > 0:
                # Clean data
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.droplevel(1)
                
                self.data_cache[cache_key] = data
                self.last_update[cache_key] = now
                
                # Update real-time monitor with latest price
                if len(data) > 0:
                    latest_price = float(data['Close'].iloc[-1])
                    latest_volume = float(data['Volume'].iloc[-1])
                    self.realtime_monitor.update_symbol_data(symbol, latest_price, latest_volume)
                
                return data
            
        except Exception as e:
            logger.warning(f"Failed to fetch data for {symbol}: {e}")
            return pd.DataFrame()
    
    def _analyze_market_direction(self, nifty_data: pd.DataFrame, banknifty_data: pd.DataFrame) -> Tuple[MarketDirection, float]:
        """Analyze overall market direction"""
        try:
            direction_scores = []
            
            # 1. EMA Analysis
            nifty_ema_score = self._get_ema_score(nifty_data)
            banknifty_ema_score = self._get_ema_score(banknifty_data)
            direction_scores.extend([nifty_ema_score, banknifty_ema_score])
            
            # 2. Price momentum (last 30 minutes)
            nifty_momentum = self._get_price_momentum(nifty_data, periods=6)  # 30 min
            banknifty_momentum = self._get_price_momentum(banknifty_data, periods=6)
            direction_scores.extend([nifty_momentum, banknifty_momentum])
            
            # 3. Volume confirmation
            volume_score = self._get_volume_score(nifty_data, banknifty_data)
            direction_scores.append(volume_score)
            
            # Calculate aggregate score
            avg_score = sum(direction_scores) / len(direction_scores)
            confidence = min(abs(avg_score) / 1.0, 1.0)  # Normalize confidence
            
            # Classify direction
            if avg_score > 0.6:
                direction = MarketDirection.STRONG_BULLISH
            elif avg_score > 0.3:
                direction = MarketDirection.BULLISH
            elif avg_score > 0.1:
                direction = MarketDirection.WEAK_BULLISH
            elif avg_score > -0.1:
                direction = MarketDirection.NEUTRAL
            elif avg_score > -0.3:
                direction = MarketDirection.WEAK_BEARISH
            elif avg_score > -0.6:
                direction = MarketDirection.BEARISH
            else:
                direction = MarketDirection.STRONG_BEARISH
            
            return direction, confidence
            
        except Exception as e:
            logger.warning(f"Direction analysis failed: {e}")
            return MarketDirection.NEUTRAL, 0.5
    
    def _get_ema_score(self, data: pd.DataFrame) -> float:
        """Get EMA-based direction score"""
        if len(data) < 50:
            return 0.0
            
        # Calculate EMAs
        data['EMA_9'] = ta.ema(data['Close'], length=9)
        data['EMA_21'] = ta.ema(data['Close'], length=21)
        data['EMA_50'] = ta.ema(data['Close'], length=50)
        
        current_price = data['Close'].iloc[-1]
        ema_9 = data['EMA_9'].iloc[-1]
        ema_21 = data['EMA_21'].iloc[-1]
        ema_50 = data['EMA_50'].iloc[-1]
        
        score = 0.0
        
        # Price vs EMAs
        if current_price > ema_9 > ema_21 > ema_50:
            score = 1.0  # Strong bullish
        elif current_price > ema_9 > ema_21:
            score = 0.7  # Bullish
        elif current_price > ema_21:
            score = 0.3  # Weak bullish
        elif current_price < ema_9 < ema_21 < ema_50:
            score = -1.0  # Strong bearish
        elif current_price < ema_9 < ema_21:
            score = -0.7  # Bearish
        elif current_price < ema_21:
            score = -0.3  # Weak bearish
        
        return score
    
    def _get_price_momentum(self, data: pd.DataFrame, periods: int = 6) -> float:
        """Get price momentum score over specified periods"""
        if len(data) < periods + 1:
            return 0.0
        
        current_price = data['Close'].iloc[-1]
        past_price = data['Close'].iloc[-(periods + 1)]
        
        momentum_pct = ((current_price - past_price) / past_price) * 100
        
        # Normalize to -1 to 1 scale
        return max(-1.0, min(1.0, momentum_pct / 2.0))  # 2% = full scale
    
    def _get_volume_score(self, nifty_data: pd.DataFrame, banknifty_data: pd.DataFrame) -> float:
        """Get volume-based confirmation score"""
        try:
            # Check if recent volume is above average
            nifty_vol_avg = nifty_data['Volume'].rolling(20).mean().iloc[-1]
            nifty_vol_current = nifty_data['Volume'].iloc[-1]
            
            banknifty_vol_avg = banknifty_data['Volume'].rolling(20).mean().iloc[-1]
            banknifty_vol_current = banknifty_data['Volume'].iloc[-1]
            
            nifty_vol_ratio = nifty_vol_current / nifty_vol_avg if nifty_vol_avg > 0 else 1.0
            banknifty_vol_ratio = banknifty_vol_current / banknifty_vol_avg if banknifty_vol_avg > 0 else 1.0
            
            avg_vol_ratio = (nifty_vol_ratio + banknifty_vol_ratio) / 2
            
            # Higher volume = higher confidence in direction
            if avg_vol_ratio > 1.5:
                return 0.5  # High volume confirmation
            elif avg_vol_ratio > 1.2:
                return 0.2  # Moderate confirmation
            else:
                return -0.1  # Low volume = less reliable
                
        except Exception:
            return 0.0
    
    def _detect_gap(self, nifty_data: pd.DataFrame) -> Tuple[GapType, float]:
        """Detect and classify market gaps"""
        try:
            if len(nifty_data) < 2:
                return GapType.NO_GAP, 0.0
            
            # Get yesterday's close and today's open
            # For intraday data, we need daily data
            daily_data = yf.download(self.nifty_symbol, period="5d", interval="1d", progress=False)

            if daily_data is None or len(daily_data) < 2:
                return GapType.NO_GAP, 0.0
            
            if isinstance(daily_data.columns, pd.MultiIndex):
                daily_data.columns = daily_data.columns.droplevel(1)
            
            prev_close = daily_data['Close'].iloc[-2]
            today_open = daily_data['Open'].iloc[-1]
            
            gap_pct = ((today_open - prev_close) / prev_close) * 100
            
            # Classify gap
            abs_gap = abs(gap_pct)
            
            if abs_gap < self.gap_thresholds['small']:
                return GapType.NO_GAP, gap_pct
            
            if gap_pct > 0:  # Gap up
                if abs_gap < self.gap_thresholds['medium']:
                    return GapType.GAP_UP_SMALL, gap_pct
                elif abs_gap < self.gap_thresholds['large']:
                    return GapType.GAP_UP_MEDIUM, gap_pct
                else:
                    return GapType.GAP_UP_LARGE, gap_pct
            else:  # Gap down
                if abs_gap < self.gap_thresholds['medium']:
                    return GapType.GAP_DOWN_SMALL, gap_pct
                elif abs_gap < self.gap_thresholds['large']:
                    return GapType.GAP_DOWN_MEDIUM, gap_pct
                else:
                    return GapType.GAP_DOWN_LARGE, gap_pct
            
        except Exception as e:
            logger.warning(f"Gap detection failed: {e}")
            return GapType.NO_GAP, 0.0
    
    def _analyze_volatility(self) -> VolatilityRegime:
        """Analyze current volatility regime"""
        try:
            # Try to get VIX data from multiple sources
            vix_data = None
            current_vix = None
            
            for vix_symbol in self.vix_symbols:
                try:
                    vix_data = yf.download(vix_symbol, period="5d", interval="1d", progress=False)
                    if vix_data is not None and not vix_data.empty:
                        if isinstance(vix_data.columns, pd.MultiIndex):
                            vix_data.columns = vix_data.columns.droplevel(1)
                        
                        current_vix = vix_data['Close'].iloc[-1]
                        break
                except Exception:
                    continue
            
            if current_vix is not None:
                if current_vix > 35:
                    return VolatilityRegime.EXTREME
                elif current_vix > 25:
                    return VolatilityRegime.HIGH
                elif current_vix > 15:
                    return VolatilityRegime.NORMAL
                else:
                    return VolatilityRegime.LOW
            
            # Fallback: Use NIFTY volatility
            nifty_data = self._fetch_intraday_data(self.nifty_symbol, period="5d", interval="1h")
            if len(nifty_data) > 20:
                returns = nifty_data['Close'].pct_change().dropna()
                daily_vol = returns.std() * np.sqrt(7)  # Hourly to daily
                
                if daily_vol > 0.04:  # 4%
                    return VolatilityRegime.EXTREME
                elif daily_vol > 0.025:  # 2.5%
                    return VolatilityRegime.HIGH
                elif daily_vol > 0.015:  # 1.5%
                    return VolatilityRegime.NORMAL
                else:
                    return VolatilityRegime.LOW
            
            return VolatilityRegime.NORMAL
            
        except Exception as e:
            logger.warning(f"Volatility analysis failed: {e}")
            return VolatilityRegime.NORMAL
    
    def _calculate_momentum(self, nifty_data: pd.DataFrame, banknifty_data: pd.DataFrame) -> float:
        """Calculate overall momentum score"""
        try:
            # ROC (Rate of Change) for both indices
            nifty_roc = ta.roc(nifty_data['Close'], length=self.momentum_period).iloc[-1]
            banknifty_roc = ta.roc(banknifty_data['Close'], length=self.momentum_period).iloc[-1]
            
            if pd.isna(nifty_roc) or pd.isna(banknifty_roc):
                return 0.0
            
            # Average momentum (normalized)
            avg_momentum = (nifty_roc + banknifty_roc) / 2
            
            # Normalize to 0-100 scale
            return max(0, min(100, 50 + avg_momentum))
            
        except Exception:
            return 50.0  # Neutral
    
    def _calculate_trend_strength(self, nifty_data: pd.DataFrame) -> float:
        """Calculate trend strength using ADX"""
        try:
            adx = ta.adx(nifty_data['High'], nifty_data['Low'], nifty_data['Close'])
            if adx is not None and 'ADX_14' in adx.columns:
                return adx['ADX_14'].iloc[-1]
            return 25.0  # Neutral
            
        except Exception:
            return 25.0  # Neutral
    
    def _analyze_opening_sentiment(self, nifty_data: pd.DataFrame, banknifty_data: pd.DataFrame) -> str:
        """Analyze opening sentiment"""
        try:
            current_time = datetime.now().time()
            
            # Check if it's opening session (9:15-10:00)
            if time(9, 15) <= current_time <= time(10, 0):
                # Analyze first 30 minutes performance
                recent_data = nifty_data.tail(6)  # Last 30 minutes (5min intervals)
                
                if len(recent_data) >= 3:
                    opening_change = ((recent_data['Close'].iloc[-1] - recent_data['Open'].iloc[0]) / 
                                    recent_data['Open'].iloc[0]) * 100
                    
                    if opening_change > 0.5:
                        return "STRONG_BULLISH_OPENING"
                    elif opening_change > 0.1:
                        return "BULLISH_OPENING"
                    elif opening_change > -0.1:
                        return "NEUTRAL_OPENING"
                    elif opening_change > -0.5:
                        return "BEARISH_OPENING"
                    else:
                        return "STRONG_BEARISH_OPENING"
            
            return "POST_OPENING"
            
        except Exception:
            return "UNKNOWN"
    
    def _calculate_levels(self, nifty_data: pd.DataFrame) -> Tuple[float, float]:
        """Calculate support and resistance levels"""
        try:
            if len(nifty_data) < 20:
                current_price = nifty_data['Close'].iloc[-1]
                return current_price * 0.995, current_price * 1.005
            
            # Recent highs and lows
            recent_data = nifty_data.tail(20)
            support = recent_data['Low'].min()
            resistance = recent_data['High'].max()
            
            return support, resistance
            
        except Exception:
            current_price = nifty_data['Close'].iloc[-1] if not nifty_data.empty else 20000
            return current_price * 0.995, current_price * 1.005
    
    def _calculate_rsi(self, data: pd.DataFrame) -> float:
        """Calculate RSI"""
        try:
            rsi = ta.rsi(data['Close'], length=14)
            return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0
        except Exception:
            return 50.0
    
    def _get_default_state(self) -> MarketState:
        """Get default market state when data unavailable"""
        return MarketState(
            direction=MarketDirection.NEUTRAL,
            confidence=0.5,
            gap_type=GapType.NO_GAP,
            gap_size_pct=0.0,
            volatility_regime=VolatilityRegime.NORMAL,
            momentum_score=50.0,
            trend_strength=25.0,
            opening_sentiment="UNKNOWN",
            nifty_rsi=50.0,
            banknifty_rsi=50.0,
            nifty_price=20000.0,
            banknifty_price=45000.0,
            support_level=19800.0,
            resistance_level=20200.0,
            timestamp=datetime.now()
        )
    
    # ... Additional methods and logic can be added here as needed
    # Helper methods to interpret market state
    def _safe_rt_value(self, rt_state, key: str, default=0.0):
        if rt_state is None:
            return default
        if isinstance(rt_state, dict):
            return rt_state.get(key, default)
        return getattr(rt_state, key, default)
