"""
Strategy 2: Momentum Adaptive Strategy
=====================================
Adaptive strategy that scales parameters based on market momentum strength.

Key Features:
- Analyzes NIFTY/BANKNIFTY momentum across multiple timeframes
- Scales position sizes based on momentum strength
- Adjusts targets and stops dynamically
- Implements momentum divergence detection
- Sector momentum alignment

Momentum Regimes:
- Strong Momentum (>80): Aggressive parameters, larger positions
- Moderate Momentum (40-80): Standard parameters
- Weak Momentum (<40): Conservative parameters, smaller positions

Author: GitHub Copilot
"""

import logging
import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timedelta
from dataclasses import dataclass

from src.core.models import TradeParameters, ScreenerSignal
from .market_detector import EnhancedMarketDetector, MarketState, MarketDirection


logger = logging.getLogger(__name__)


@dataclass
class MomentumParameters:
    """Parameters for momentum adaptive strategy"""
    
    # Momentum thresholds
    strong_momentum_threshold: float = 80.0
    weak_momentum_threshold: float = 40.0
    
    # Position sizing multipliers
    strong_momentum_size_mult: float = 1.5    # 50% larger positions
    moderate_momentum_size_mult: float = 1.0  # Normal size
    weak_momentum_size_mult: float = 0.6      # 40% smaller positions
    
    # Target multipliers based on momentum
    strong_momentum_target_mult: float = 3.0  # 3R targets in strong momentum
    moderate_momentum_target_mult: float = 2.0 # 2R targets normally
    weak_momentum_target_mult: float = 1.2    # 1.2R targets in weak momentum
    
    # Stop loss adjustments
    strong_momentum_sl_mult: float = 1.2      # Wider stops in strong momentum
    moderate_momentum_sl_mult: float = 1.0    # Normal stops
    weak_momentum_sl_mult: float = 0.8        # Tighter stops in weak momentum
    
    # Partial exit adjustments
    strong_momentum_partial_ratio: float = 1.2  # Exit at 1.2R in strong momentum
    moderate_momentum_partial_ratio: float = 0.8 # Exit at 0.8R normally
    weak_momentum_partial_ratio: float = 0.5    # Exit at 0.5R in weak momentum
    
    # Divergence parameters
    divergence_lookback_periods: int = 20
    divergence_threshold: float = 0.3         # 30% for significant divergence
    
    # Sector momentum requirements
    min_sector_momentum_score: float = 50.0   # Minimum sector momentum
    sector_momentum_weight: float = 0.3       # Weight in final decision


@dataclass
class MomentumAnalysis:
    """Comprehensive momentum analysis"""
    overall_momentum: float
    short_term_momentum: float    # 5-min momentum
    medium_term_momentum: float   # 15-min momentum
    long_term_momentum: float     # 1-hour momentum
    nifty_momentum: float
    banknifty_momentum: float
    sector_momentum: float
    momentum_regime: str
    momentum_direction: str
    divergence_detected: bool
    momentum_strength: str
    confidence: float


class MomentumAdaptiveStrategy:
    """
    Momentum-based adaptive trading strategy.
    
    This strategy:
    1. Analyzes momentum across multiple timeframes
    2. Scales position sizes based on momentum strength
    3. Adjusts targets and stops dynamically
    4. Detects momentum divergences
    5. Considers sector momentum alignment
    """
    
    def __init__(self, market_detector: EnhancedMarketDetector):
        """
        Initialize momentum adaptive strategy.
        
        Args:
            market_detector: Enhanced market detector instance
        """
        self.name = "MOMENTUM_ADAPTIVE"
        self.market_detector = market_detector
        self.params = MomentumParameters()
        
        # Momentum analysis cache
        self.current_momentum_analysis: Optional[MomentumAnalysis] = None
        self.momentum_history: List[float] = []
        self.last_analysis_time: Optional[datetime] = None
        
        # Sector momentum cache
        self.sector_momentum_cache: Dict[str, float] = {}
        
        logger.info("Momentum adaptive strategy initialized")
    
    def update_momentum_analysis(self) -> None:
        """Update comprehensive momentum analysis"""
        try:
            current_time = datetime.now()
            
            # Update every 5 minutes
            if (self.last_analysis_time is None or 
                (current_time - self.last_analysis_time).seconds >= 300):
                
                self.current_momentum_analysis = self._perform_momentum_analysis()
                self.last_analysis_time = current_time
                
                # Update momentum history
                if self.current_momentum_analysis:
                    self.momentum_history.append(self.current_momentum_analysis.overall_momentum)
                    # Keep only last 50 readings (about 4 hours)
                    if len(self.momentum_history) > 50:
                        self.momentum_history = self.momentum_history[-50:]
        
        except Exception as e:
            logger.error(f"Failed to update momentum analysis: {e}")
    
    def should_enter_trade(self, signal: ScreenerSignal) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Determine if should enter trade based on momentum conditions.
        
        Args:
            signal: Screener signal
            
        Returns:
            (should_enter, reason, adjusted_parameters)
        """
        # Update momentum analysis
        self.update_momentum_analysis()
        
        if self.current_momentum_analysis is None:
            return False, "Momentum analysis unavailable", {}
        
        momentum = self.current_momentum_analysis
        
        # Evaluate momentum-based entry
        should_enter, reason = self._evaluate_momentum_entry(signal, momentum)
        
        if not should_enter:
            return False, reason, {}
        
        # Calculate adjusted parameters
        adjusted_params = self._calculate_momentum_parameters(signal, momentum)
        
        return True, reason, adjusted_params
    
    def _perform_momentum_analysis(self) -> Optional[MomentumAnalysis]:
        """Perform comprehensive momentum analysis"""
        try:
            # Get market data for different timeframes
            nifty_5m = self.market_detector._fetch_intraday_data(
                self.market_detector.nifty_symbol, period="1d", interval="5m"
            )
            nifty_15m = self.market_detector._fetch_intraday_data(
                self.market_detector.nifty_symbol, period="2d", interval="15m"
            )
            nifty_1h = self.market_detector._fetch_intraday_data(
                self.market_detector.nifty_symbol, period="5d", interval="1h"
            )
            
            banknifty_5m = self.market_detector._fetch_intraday_data(
                self.market_detector.banknifty_symbol, period="1d", interval="5m"
            )
            
            if any(df.empty for df in [nifty_5m, nifty_15m, nifty_1h, banknifty_5m]):
                return None
            
            # Calculate momentum for different timeframes
            short_momentum = self._calculate_timeframe_momentum(nifty_5m, periods=12)  # 1 hour
            medium_momentum = self._calculate_timeframe_momentum(nifty_15m, periods=16) # 4 hours
            long_momentum = self._calculate_timeframe_momentum(nifty_1h, periods=6)    # 6 hours
            
            # NIFTY vs BANKNIFTY momentum
            nifty_momentum = self._calculate_timeframe_momentum(nifty_5m, periods=20)
            banknifty_momentum = self._calculate_timeframe_momentum(banknifty_5m, periods=20)
            
            # Overall momentum score (weighted average)
            overall_momentum = (
                short_momentum * 0.4 +      # 40% weight to short term
                medium_momentum * 0.35 +    # 35% weight to medium term
                long_momentum * 0.25        # 25% weight to long term
            )
            
            # Momentum regime classification
            if overall_momentum >= self.params.strong_momentum_threshold:
                momentum_regime = "STRONG"
                momentum_strength = "HIGH"
            elif overall_momentum >= self.params.weak_momentum_threshold:
                momentum_regime = "MODERATE"
                momentum_strength = "MEDIUM"
            else:
                momentum_regime = "WEAK"
                momentum_strength = "LOW"
            
            # Momentum direction
            if overall_momentum > 55:
                momentum_direction = "BULLISH"
            elif overall_momentum < 45:
                momentum_direction = "BEARISH"
            else:
                momentum_direction = "NEUTRAL"
            
            # Check for divergence
            divergence_detected = self._detect_momentum_divergence(nifty_5m)
            
            # Calculate confidence
            momentum_spread = abs(max(short_momentum, medium_momentum, long_momentum) - 
                                min(short_momentum, medium_momentum, long_momentum))
            confidence = max(0.5, 1.0 - (momentum_spread / 50.0))
            
            # Sector momentum (placeholder - will be calculated when symbol is known)
            sector_momentum = 50.0  # Default neutral
            
            analysis = MomentumAnalysis(
                overall_momentum=overall_momentum,
                short_term_momentum=short_momentum,
                medium_term_momentum=medium_momentum,
                long_term_momentum=long_momentum,
                nifty_momentum=nifty_momentum,
                banknifty_momentum=banknifty_momentum,
                sector_momentum=sector_momentum,
                momentum_regime=momentum_regime,
                momentum_direction=momentum_direction,
                divergence_detected=divergence_detected,
                momentum_strength=momentum_strength,
                confidence=confidence
            )
            
            logger.debug(f"Momentum Analysis: {momentum_regime} ({overall_momentum:.1f}), Direction: {momentum_direction}")
            return analysis
            
        except Exception as e:
            logger.error(f"Momentum analysis failed: {e}")
            return None
    
    def _calculate_timeframe_momentum(self, data: pd.DataFrame, periods: int = 14) -> float:
        """Calculate momentum score for specific timeframe"""
        try:
            if len(data) < periods + 5:
                return 50.0  # Neutral
            
            # Multiple momentum indicators
            
            # 1. ROC (Rate of Change)
            roc = ta.roc(data['Close'], length=periods)
            current_roc = roc.iloc[-1] if not pd.isna(roc.iloc[-1]) else 0
            
            # 2. RSI
            rsi = ta.rsi(data['Close'], length=periods)
            current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
            
            # 3. MACD Signal
            macd = ta.macd(data['Close'])
            if macd is not None and 'MACD_12_26_9' in macd.columns and 'MACDs_12_26_9' in macd.columns:
                macd_line = macd['MACD_12_26_9'].iloc[-1]
                macd_signal = macd['MACDs_12_26_9'].iloc[-1]
                macd_momentum = 60 if macd_line > macd_signal else 40
            else:
                macd_momentum = 50
            
            # 4. Price vs EMA
            ema = ta.ema(data['Close'], length=periods)
            current_price = data['Close'].iloc[-1]
            current_ema = ema.iloc[-1] if not pd.isna(ema.iloc[-1]) else current_price
            
            price_ema_ratio = current_price / current_ema
            price_momentum = min(100, max(0, 50 + (price_ema_ratio - 1) * 1000))
            
            # Combine indicators
            roc_score = min(100, max(0, 50 + current_roc * 2))
            
            momentum_score = (
                roc_score * 0.3 +           # 30% ROC
                current_rsi * 0.3 +         # 30% RSI
                macd_momentum * 0.2 +       # 20% MACD
                price_momentum * 0.2        # 20% Price vs EMA
            )
            
            return max(0, min(100, momentum_score))
            
        except Exception as e:
            logger.warning(f"Momentum calculation failed: {e}")
            return 50.0
    
    def _detect_momentum_divergence(self, data: pd.DataFrame) -> bool:
        """Detect momentum divergence between price and indicators"""
        try:
            if len(data) < self.params.divergence_lookback_periods:
                return False
            
            # Get recent data
            recent_data = data.tail(self.params.divergence_lookback_periods)
            
            # Price trend
            price_start = recent_data['Close'].iloc[0]
            price_end = recent_data['Close'].iloc[-1]
            price_change = (price_end - price_start) / price_start
            
            # RSI trend
            rsi = ta.rsi(recent_data['Close'], length=14)
            rsi_start = rsi.iloc[0]
            rsi_end = rsi.iloc[-1]
            rsi_change = (rsi_end - rsi_start) / 100.0  # Normalize
            
            # Check for divergence
            if (price_change > self.params.divergence_threshold and 
                rsi_change < -self.params.divergence_threshold):
                return True  # Bearish divergence
            
            if (price_change < -self.params.divergence_threshold and 
                rsi_change > self.params.divergence_threshold):
                return True  # Bullish divergence
            
            return False
            
        except Exception:
            return False
    
    def _calculate_sector_momentum(self, sector: str) -> float:
        """Calculate sector-specific momentum"""
        try:
            # Check cache first
            if sector in self.sector_momentum_cache:
                return self.sector_momentum_cache[sector]
            
            # For now, return default - can be enhanced with sector ETF data
            sector_momentum = 50.0  # Neutral
            
            # Cache result
            self.sector_momentum_cache[sector] = sector_momentum
            return sector_momentum
            
        except Exception:
            return 50.0
    
    def _evaluate_momentum_entry(self, signal: ScreenerSignal, momentum: MomentumAnalysis) -> Tuple[bool, str]:
        """Evaluate if should enter based on momentum conditions"""
        
        # 1. Check momentum regime requirements
        if momentum.momentum_regime == "WEAK":
            # In weak momentum, be very selective
            if signal.score < 60:
                return False, f"Score {signal.score} too low for weak momentum regime"
            
            # Require trend alignment in weak momentum
            if momentum.momentum_direction == "BEARISH" and signal.trend == "BULLISH":
                return False, "Bullish signal in weak bearish momentum"
        
        elif momentum.momentum_regime == "STRONG":
            # In strong momentum, be more aggressive but check alignment
            if momentum.momentum_direction != "NEUTRAL":
                expected_trend = "BULLISH" if momentum.momentum_direction == "BULLISH" else "BEARISH"
                if signal.trend != expected_trend and signal.trend != "NEUTRAL":
                    return False, f"Trend misalignment: {signal.trend} vs {momentum.momentum_direction} momentum"
        
        # 2. Check for momentum divergence
        if momentum.divergence_detected:
            # Be cautious with new entries during divergence
            if signal.score < 55:
                return False, "Momentum divergence detected - need higher score"
        
        # 3. Sector momentum check
        sector_momentum = self._calculate_sector_momentum(signal.sector)
        if sector_momentum < self.params.min_sector_momentum_score:
            return False, f"Sector momentum {sector_momentum:.1f} below minimum {self.params.min_sector_momentum_score}"
        
        # 4. Overall momentum confidence
        if momentum.confidence < 0.6:
            return False, f"Momentum analysis confidence {momentum.confidence:.2f} too low"
        
        # 5. Check momentum alignment across timeframes
        timeframe_spread = abs(momentum.short_term_momentum - momentum.long_term_momentum)
        if timeframe_spread > 40:  # 40 points spread
            return False, f"Momentum timeframes misaligned (spread: {timeframe_spread:.1f})"
        
        reason = f"Momentum entry: {momentum.momentum_regime} regime ({momentum.overall_momentum:.1f})"
        return True, reason
    
    def _calculate_momentum_parameters(self, signal: ScreenerSignal, momentum: MomentumAnalysis) -> Dict[str, Any]:
        """Calculate adjusted parameters based on momentum analysis"""
        
        # Base parameters based on momentum regime
        if momentum.momentum_regime == "STRONG":
            size_mult = self.params.strong_momentum_size_mult
            target_mult = self.params.strong_momentum_target_mult
            sl_mult = self.params.strong_momentum_sl_mult
            partial_ratio = self.params.strong_momentum_partial_ratio
            entry_reason = f"strong_momentum_{momentum.overall_momentum:.0f}"
        
        elif momentum.momentum_regime == "WEAK":
            size_mult = self.params.weak_momentum_size_mult
            target_mult = self.params.weak_momentum_target_mult
            sl_mult = self.params.weak_momentum_sl_mult
            partial_ratio = self.params.weak_momentum_partial_ratio
            entry_reason = f"weak_momentum_{momentum.overall_momentum:.0f}"
        
        else:  # MODERATE
            size_mult = self.params.moderate_momentum_size_mult
            target_mult = self.params.moderate_momentum_target_mult
            sl_mult = self.params.moderate_momentum_sl_mult
            partial_ratio = self.params.moderate_momentum_partial_ratio
            entry_reason = f"moderate_momentum_{momentum.overall_momentum:.0f}"
        
        # Fine-tune based on confidence and divergence
        confidence_adjustment = momentum.confidence
        if momentum.divergence_detected:
            size_mult *= 0.8        # Reduce position size
            target_mult *= 0.9      # Lower targets
            entry_reason += "_divergence"
        
        # Sector momentum adjustment
        sector_momentum = self._calculate_sector_momentum(signal.sector)
        sector_adj = 0.8 + (sector_momentum / 100.0) * 0.4  # 0.8 to 1.2 range
        size_mult *= sector_adj
        
        adjusted_params = {
            'atr_sl_mult': 1.5 * sl_mult,
            'atr_target_mult': target_mult,
            'partial_exit_ratio': partial_ratio,
            'position_size_multiplier': size_mult,
            'confidence_score': confidence_adjustment,
            'momentum_regime': momentum.momentum_regime,
            'momentum_score': momentum.overall_momentum,
            'sector_momentum': sector_momentum,
            'entry_reason': entry_reason
        }
        
        # Additional momentum-based adjustments
        if momentum.short_term_momentum > 75:
            adjusted_params['trailing_stop_enabled'] = True
            adjusted_params['trailing_stop_mult'] = 2.0
        
        return adjusted_params
    
    def get_momentum_summary(self) -> Dict[str, Any]:
        """Get current momentum analysis summary"""
        if self.current_momentum_analysis is None:
            self.update_momentum_analysis()
        
        if self.current_momentum_analysis is None:
            return {'status': 'unavailable'}
        
        momentum = self.current_momentum_analysis
        
        # Calculate momentum trend
        momentum_trend = "STABLE"
        if len(self.momentum_history) >= 5:
            recent_avg = sum(self.momentum_history[-5:]) / 5
            older_avg = sum(self.momentum_history[-10:-5]) / 5 if len(self.momentum_history) >= 10 else recent_avg
            
            if recent_avg > older_avg + 5:
                momentum_trend = "INCREASING"
            elif recent_avg < older_avg - 5:
                momentum_trend = "DECREASING"
        
        return {
            'strategy_name': self.name,
            'momentum_regime': momentum.momentum_regime,
            'overall_momentum': f"{momentum.overall_momentum:.1f}",
            'momentum_direction': momentum.momentum_direction,
            'momentum_strength': momentum.momentum_strength,
            'momentum_trend': momentum_trend,
            'divergence_detected': momentum.divergence_detected,
            'confidence': f"{momentum.confidence:.2f}",
            'timeframe_breakdown': {
                'short_term': f"{momentum.short_term_momentum:.1f}",
                'medium_term': f"{momentum.medium_term_momentum:.1f}",
                'long_term': f"{momentum.long_term_momentum:.1f}"
            },
            'indices_momentum': {
                'nifty': f"{momentum.nifty_momentum:.1f}",
                'banknifty': f"{momentum.banknifty_momentum:.1f}"
            },
            'last_update': self.last_analysis_time.strftime('%H:%M:%S') if self.last_analysis_time else 'Never'
        }
    
    def reset_daily_state(self) -> None:
        """Reset daily state variables"""
        self.current_momentum_analysis = None
        self.momentum_history.clear()
        self.sector_momentum_cache.clear()
        self.last_analysis_time = None
        
        logger.info("Momentum adaptive strategy daily state reset")