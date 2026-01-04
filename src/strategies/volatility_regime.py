"""
Strategy 3: Volatility Regime Strategy
======================================
Adaptive strategy that adjusts all parameters based on market volatility regime.

Key Features:
- Detects volatility regimes (Low, Normal, High, Extreme)
- Scales position sizes inversely with volatility
- Adjusts ATR multipliers based on volatility environment
- Dynamic target and stop adjustments
- Volatility breakout detection
- Risk management based on VIX levels

Volatility Regimes:
- Low Volatility (<15 VIX): Larger positions, tighter stops
- Normal Volatility (15-25 VIX): Standard parameters  
- High Volatility (25-35 VIX): Smaller positions, wider stops
- Extreme Volatility (>35 VIX): Minimal positions, defensive mode

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
from .market_detector import EnhancedMarketDetector, MarketState, VolatilityRegime


logger = logging.getLogger(__name__)


@dataclass
class VolatilityParameters:
    """Parameters for volatility regime strategy"""
    
    # Volatility measurement periods
    short_vol_period: int = 10     # 10-period volatility
    medium_vol_period: int = 20    # 20-period volatility
    long_vol_period: int = 50      # 50-period volatility
    
    # VIX thresholds for regime classification
    low_vix_threshold: float = 15.0
    normal_vix_threshold: float = 25.0
    high_vix_threshold: float = 35.0
    
    # Position sizing by volatility regime
    low_vol_size_mult: float = 1.4        # Larger positions in low vol
    normal_vol_size_mult: float = 1.0     # Normal positions
    high_vol_size_mult: float = 0.7       # Smaller positions in high vol
    extreme_vol_size_mult: float = 0.4    # Minimal positions in extreme vol
    
    # ATR multipliers by volatility regime
    low_vol_atr_sl: float = 1.2           # Tighter stops in low vol
    normal_vol_atr_sl: float = 1.5        # Normal stops
    high_vol_atr_sl: float = 2.0          # Wider stops in high vol
    extreme_vol_atr_sl: float = 2.5       # Very wide stops in extreme vol
    
    low_vol_atr_target: float = 2.5       # Higher targets in low vol
    normal_vol_atr_target: float = 2.0    # Normal targets
    high_vol_atr_target: float = 1.5      # Lower targets in high vol
    extreme_vol_atr_target: float = 1.2   # Minimal targets in extreme vol
    
    # Partial exit ratios by volatility
    low_vol_partial_ratio: float = 1.0    # Exit at 1R in low vol
    normal_vol_partial_ratio: float = 0.8 # Exit at 0.8R normally
    high_vol_partial_ratio: float = 0.6   # Exit at 0.6R in high vol
    extreme_vol_partial_ratio: float = 0.4 # Exit at 0.4R in extreme vol
    
    # Volatility breakout parameters
    vol_expansion_threshold: float = 1.5   # 50% expansion from average
    vol_compression_threshold: float = 0.7 # 30% compression from average
    vol_breakout_min_score: float = 50     # Minimum score for vol breakouts
    
    # Risk scaling factors
    low_vol_risk_mult: float = 1.2        # Slightly higher risk in low vol
    normal_vol_risk_mult: float = 1.0     # Normal risk
    high_vol_risk_mult: float = 0.8       # Lower risk in high vol
    extreme_vol_risk_mult: float = 0.5    # Minimal risk in extreme vol


@dataclass
class VolatilityAnalysis:
    """Comprehensive volatility analysis"""
    current_regime: VolatilityRegime
    vix_level: float
    realized_vol_short: float
    realized_vol_medium: float
    realized_vol_long: float
    avg_realized_vol: float
    vol_rank_percentile: float
    vol_expansion_detected: bool
    vol_compression_detected: bool
    vol_trend: str                 # EXPANDING, CONTRACTING, STABLE
    vol_shock_detected: bool       # Sudden volatility spike
    confidence: float
    timestamp: datetime


class VolatilityRegimeStrategy:
    """
    Volatility regime-based adaptive trading strategy.
    
    This strategy:
    1. Monitors multiple volatility measures (VIX, realized volatility)
    2. Classifies volatility regimes
    3. Scales position sizes inversely with volatility
    4. Adjusts stops and targets based on volatility environment
    5. Detects volatility expansions and contractions
    6. Implements defensive measures in extreme volatility
    """
    
    def __init__(self, market_detector: EnhancedMarketDetector):
        """
        Initialize volatility regime strategy.
        
        Args:
            market_detector: Enhanced market detector instance
        """
        self.name = "VOLATILITY_REGIME"
        self.market_detector = market_detector
        self.params = VolatilityParameters()
        
        # Volatility analysis cache
        self.current_vol_analysis: Optional[VolatilityAnalysis] = None
        self.vol_history: List[float] = []
        self.last_analysis_time: Optional[datetime] = None
        
        # VIX data cache
        self.vix_data_cache: Optional[pd.DataFrame] = None
        self.last_vix_update: Optional[datetime] = None
        
        logger.info("Volatility regime strategy initialized")
    
    def update_volatility_analysis(self) -> None:
        """Update comprehensive volatility analysis"""
        try:
            current_time = datetime.now()
            
            # Update every 10 minutes
            if (self.last_analysis_time is None or 
                (current_time - self.last_analysis_time).seconds >= 600):
                
                self.current_vol_analysis = self._perform_volatility_analysis()
                self.last_analysis_time = current_time
                
                # Update volatility history
                if self.current_vol_analysis:
                    self.vol_history.append(self.current_vol_analysis.avg_realized_vol)
                    # Keep only last 100 readings (about 16 hours)
                    if len(self.vol_history) > 100:
                        self.vol_history = self.vol_history[-100:]
        
        except Exception as e:
            logger.error(f"Failed to update volatility analysis: {e}")
    
    def should_enter_trade(self, signal: ScreenerSignal) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Determine if should enter trade based on volatility conditions.
        
        Args:
            signal: Screener signal
            
        Returns:
            (should_enter, reason, adjusted_parameters)
        """
        # Update volatility analysis
        self.update_volatility_analysis()
        
        if self.current_vol_analysis is None:
            return False, "Volatility analysis unavailable", {}
        
        vol_analysis = self.current_vol_analysis
        
        # Evaluate volatility-based entry
        should_enter, reason = self._evaluate_volatility_entry(signal, vol_analysis)
        
        if not should_enter:
            return False, reason, {}
        
        # Calculate adjusted parameters
        adjusted_params = self._calculate_volatility_parameters(signal, vol_analysis)
        
        return True, reason, adjusted_params
    
    def _perform_volatility_analysis(self) -> Optional[VolatilityAnalysis]:
        """Perform comprehensive volatility analysis"""
        try:
            # Get VIX data
            vix_level = self._get_current_vix()
            
            # Get NIFTY data for realized volatility calculation
            nifty_data = self.market_detector._fetch_intraday_data(
                self.market_detector.nifty_symbol, period="5d", interval="1h"
            )
            
            if nifty_data.empty:
                return None
            
            # Calculate realized volatilities
            returns = nifty_data['Close'].pct_change().dropna()
            
            short_vol = self._calculate_realized_volatility(returns, self.params.short_vol_period)
            medium_vol = self._calculate_realized_volatility(returns, self.params.medium_vol_period)
            long_vol = self._calculate_realized_volatility(returns, self.params.long_vol_period)
            
            avg_realized_vol = (short_vol + medium_vol + long_vol) / 3
            
            # Determine volatility regime based on VIX
            if vix_level < self.params.low_vix_threshold:
                regime = VolatilityRegime.LOW
            elif vix_level < self.params.normal_vix_threshold:
                regime = VolatilityRegime.NORMAL
            elif vix_level < self.params.high_vix_threshold:
                regime = VolatilityRegime.HIGH
            else:
                regime = VolatilityRegime.EXTREME
            
            # Calculate volatility rank percentile (last 252 periods)
            if len(returns) >= 252:
                vol_252 = [self._calculate_realized_volatility(returns.iloc[i:i+20]) 
                          for i in range(len(returns)-252, len(returns)-20)]
                vol_rank = (sum(1 for v in vol_252 if v < short_vol) / len(vol_252)) * 100
            else:
                vol_rank = 50.0  # Default neutral
            
            # Detect volatility expansion/compression
            vol_expansion = False
            vol_compression = False
            
            if len(self.vol_history) >= 10:
                recent_avg_vol = sum(self.vol_history[-5:]) / 5
                older_avg_vol = sum(self.vol_history[-10:-5]) / 5
                
                if recent_avg_vol > older_avg_vol * self.params.vol_expansion_threshold:
                    vol_expansion = True
                elif recent_avg_vol < older_avg_vol * self.params.vol_compression_threshold:
                    vol_compression = True
            
            # Determine volatility trend
            if vol_expansion:
                vol_trend = "EXPANDING"
            elif vol_compression:
                vol_trend = "CONTRACTING"
            else:
                vol_trend = "STABLE"
            
            # Detect volatility shock (sudden spike)
            vol_shock = False
            if len(self.vol_history) >= 5:
                current_vol = short_vol
                recent_avg = sum(self.vol_history[-5:]) / 5
                if current_vol > recent_avg * 2.0:  # 100% spike
                    vol_shock = True
            
            # Calculate confidence based on consistency
            vol_spread = max(short_vol, medium_vol, long_vol) - min(short_vol, medium_vol, long_vol)
            confidence = max(0.5, 1.0 - (vol_spread / avg_realized_vol))
            
            analysis = VolatilityAnalysis(
                current_regime=regime,
                vix_level=vix_level,
                realized_vol_short=short_vol,
                realized_vol_medium=medium_vol,
                realized_vol_long=long_vol,
                avg_realized_vol=avg_realized_vol,
                vol_rank_percentile=vol_rank,
                vol_expansion_detected=vol_expansion,
                vol_compression_detected=vol_compression,
                vol_trend=vol_trend,
                vol_shock_detected=vol_shock,
                confidence=confidence,
                timestamp=datetime.now()
            )
            
            logger.debug(f"Volatility Analysis: {regime.value} regime (VIX: {vix_level:.1f}), Trend: {vol_trend}")
            return analysis
            
        except Exception as e:
            logger.error(f"Volatility analysis failed: {e}")
            return None
    
    def _get_current_vix(self) -> float:
        """Get current VIX level with caching"""
        try:
            current_time = datetime.now()
            
            # Update VIX data every 30 minutes
            if (self.last_vix_update is None or 
                (current_time - self.last_vix_update).seconds >= 1800):
                
                import yfinance as yf
                # Try multiple VIX symbols
                vix_symbols = [ "^VIX", "INDIAVIX.NS"]
                vix_data = None
                
                for vix_symbol in vix_symbols:
                    try:
                        vix_data = yf.download(vix_symbol, period="5d", interval="1d", progress=False)
                        if not vix_data.empty:
                            break
                    except Exception:
                        continue
                
                if vix_data is not None and not vix_data.empty:
                    if isinstance(vix_data.columns, pd.MultiIndex):
                        vix_data.columns = vix_data.columns.droplevel(1)
                    
                    self.vix_data_cache = vix_data
                    self.last_vix_update = current_time
            
            # Return current VIX level
            if self.vix_data_cache is not None and not self.vix_data_cache.empty:
                return float(self.vix_data_cache['Close'].iloc[-1])
            
            # Fallback: estimate from NIFTY volatility
            nifty_data = self.market_detector._fetch_intraday_data(
                self.market_detector.nifty_symbol, period="5d", interval="1h"
            )
            
            if not nifty_data.empty:
                returns = nifty_data['Close'].pct_change().dropna()
                if len(returns) >= 20:
                    realized_vol = self._calculate_realized_volatility(returns, 20)
                    # Convert to VIX-like scale (rough approximation)
                    estimated_vix = realized_vol * 100 * np.sqrt(252 / 20)
                    return max(10.0, min(60.0, estimated_vix))
            
            return 20.0  # Default normal level
            
        except Exception as e:
            logger.warning(f"Failed to get VIX data: {e}")
            return 20.0
    
    def _calculate_realized_volatility(self, returns: pd.Series, period: int=20) -> float:
        """Calculate realized volatility for given period"""
        try:
            if len(returns) < period:
                return 0.02  # Default 2% volatility
            
            recent_returns = returns.tail(period)
            vol = recent_returns.std() * np.sqrt(252 / period)  # Annualized
            return float(vol) if not pd.isna(vol) else 0.02
            
        except Exception:
            return 0.02
    
    def _evaluate_volatility_entry(self, signal: ScreenerSignal, vol_analysis: VolatilityAnalysis) -> Tuple[bool, str]:
        """Evaluate if should enter based on volatility conditions"""
        
        # 1. Check for volatility shock - be very cautious
        if vol_analysis.vol_shock_detected:
            if signal.score < 70:
                return False, "Volatility shock detected - need very high score"
        
        # 2. Extreme volatility regime - defensive mode
        if vol_analysis.current_regime == VolatilityRegime.EXTREME:
            if signal.score < 65:
                return False, f"Extreme volatility regime (VIX: {vol_analysis.vix_level:.1f}) - need score ≥65"
            
            # Only high-quality, oversold/overbought signals in extreme vol
            if signal.trend == "NEUTRAL":
                return False, "Need clear trend in extreme volatility"
        
        # 3. High volatility regime - be cautious
        elif vol_analysis.current_regime == VolatilityRegime.HIGH:
            if signal.score < 50:
                return False, f"High volatility regime (VIX: {vol_analysis.vix_level:.1f}) - need score ≥50"
        
        # 4. Low volatility regime - look for breakouts
        elif vol_analysis.current_regime == VolatilityRegime.LOW:
            # In low vol, favor volatility breakout setups
            if (vol_analysis.vol_expansion_detected and 
                signal.score >= self.params.vol_breakout_min_score):
                return True, f"Low vol regime volatility breakout (VIX: {vol_analysis.vix_level:.1f})"
            
            # Otherwise, standard criteria but more lenient
            if signal.score < 35:
                return False, "Even in low volatility, minimum score required"
        
        # 5. Check volatility trend alignment
        if vol_analysis.vol_trend == "EXPANDING":
            # Expanding volatility - be cautious with new entries
            if signal.score < 45:
                return False, f"Expanding volatility trend - need score ≥45"
        
        # 6. Volatility rank consideration
        if vol_analysis.vol_rank_percentile > 80:  # Very high volatility environment
            if signal.score < 55:
                return False, f"High volatility rank ({vol_analysis.vol_rank_percentile:.1f}%) - need higher score"
        
        # 7. Confidence check
        if vol_analysis.confidence < 0.6:
            return False, f"Volatility analysis confidence {vol_analysis.confidence:.2f} too low"
        
        reason = f"Volatility entry: {vol_analysis.current_regime.value} regime (VIX: {vol_analysis.vix_level:.1f})"
        return True, reason
    
    def _calculate_volatility_parameters(self, signal: ScreenerSignal, vol_analysis: VolatilityAnalysis) -> Dict[str, Any]:
        """Calculate adjusted parameters based on volatility analysis"""
        
        regime = vol_analysis.current_regime
        
        # Base parameters by volatility regime
        if regime == VolatilityRegime.LOW:
            size_mult = self.params.low_vol_size_mult
            atr_sl = self.params.low_vol_atr_sl
            atr_target = self.params.low_vol_atr_target
            partial_ratio = self.params.low_vol_partial_ratio
            risk_mult = self.params.low_vol_risk_mult
        
        elif regime == VolatilityRegime.NORMAL:
            size_mult = self.params.normal_vol_size_mult
            atr_sl = self.params.normal_vol_atr_sl
            atr_target = self.params.normal_vol_atr_target
            partial_ratio = self.params.normal_vol_partial_ratio
            risk_mult = self.params.normal_vol_risk_mult
        
        elif regime == VolatilityRegime.HIGH:
            size_mult = self.params.high_vol_size_mult
            atr_sl = self.params.high_vol_atr_sl
            atr_target = self.params.high_vol_atr_target
            partial_ratio = self.params.high_vol_partial_ratio
            risk_mult = self.params.high_vol_risk_mult
        
        else:  # EXTREME
            size_mult = self.params.extreme_vol_size_mult
            atr_sl = self.params.extreme_vol_atr_sl
            atr_target = self.params.extreme_vol_atr_target
            partial_ratio = self.params.extreme_vol_partial_ratio
            risk_mult = self.params.extreme_vol_risk_mult
        
        # Fine-tune based on volatility analysis
        
        # Volatility shock adjustment
        if vol_analysis.vol_shock_detected:
            size_mult *= 0.5    # Halve position size
            atr_sl *= 1.5       # Wider stops
            atr_target *= 0.7   # Lower targets
        
        # Volatility expansion/contraction adjustment
        if vol_analysis.vol_expansion_detected:
            size_mult *= 0.8    # Smaller positions during vol expansion
            atr_sl *= 1.2       # Slightly wider stops
        
        elif vol_analysis.vol_compression_detected:
            size_mult *= 1.1    # Slightly larger positions during compression
            atr_sl *= 0.9       # Tighter stops
            atr_target *= 1.1   # Higher targets
        
        # VIX level fine-tuning
        vix_adjustment = 1.0
        if vol_analysis.vix_level > 40:
            vix_adjustment = 0.7  # Very defensive
        elif vol_analysis.vix_level > 30:
            vix_adjustment = 0.85
        elif vol_analysis.vix_level < 12:
            vix_adjustment = 1.15  # Slightly more aggressive
        
        size_mult *= vix_adjustment
        
        # Volatility rank adjustment
        if vol_analysis.vol_rank_percentile > 90:
            size_mult *= 0.8    # Very high vol rank
        elif vol_analysis.vol_rank_percentile < 10:
            size_mult *= 1.2    # Very low vol rank
        
        entry_reason = f"{regime.value.lower()}_vol_regime_VIX_{vol_analysis.vix_level:.0f}"
        
        if vol_analysis.vol_expansion_detected:
            entry_reason += "_expanding"
        elif vol_analysis.vol_compression_detected:
            entry_reason += "_contracting"
        
        if vol_analysis.vol_shock_detected:
            entry_reason += "_shock"
        
        adjusted_params = {
            'atr_sl_mult': atr_sl,
            'atr_target_mult': atr_target,
            'partial_exit_ratio': partial_ratio,
            'position_size_multiplier': size_mult,
            'risk_multiplier': risk_mult,
            'volatility_regime': regime.value,
            'vix_level': vol_analysis.vix_level,
            'vol_rank_percentile': vol_analysis.vol_rank_percentile,
            'vol_trend': vol_analysis.vol_trend,
            'confidence_score': vol_analysis.confidence,
            'entry_reason': entry_reason
        }
        
        # Special volatility-based features
        if regime in [VolatilityRegime.HIGH, VolatilityRegime.EXTREME]:
            adjusted_params['quick_exit_enabled'] = True
            adjusted_params['time_based_exit_minutes'] = 120  # 2-hour max hold
        
        if vol_analysis.vol_compression_detected and regime == VolatilityRegime.LOW:
            adjusted_params['breakout_mode'] = True
            adjusted_params['volume_confirmation_required'] = True
        
        return adjusted_params
    
    def get_volatility_summary(self) -> Dict[str, Any]:
        """Get current volatility analysis summary"""
        if self.current_vol_analysis is None:
            self.update_volatility_analysis()
        
        if self.current_vol_analysis is None:
            return {'status': 'unavailable'}
        
        vol = self.current_vol_analysis
        
        # Calculate volatility trend over time
        vol_trend_direction = "STABLE"
        if len(self.vol_history) >= 10:
            recent_avg = sum(self.vol_history[-5:]) / 5
            older_avg = sum(self.vol_history[-10:-5]) / 5
            
            change_pct = ((recent_avg - older_avg) / older_avg) * 100
            if change_pct > 20:
                vol_trend_direction = "INCREASING"
            elif change_pct < -20:
                vol_trend_direction = "DECREASING"
        
        return {
            'strategy_name': self.name,
            'volatility_regime': vol.current_regime.value,
            'vix_level': f"{vol.vix_level:.1f}",
            'vol_rank_percentile': f"{vol.vol_rank_percentile:.1f}%",
            'volatility_trend': vol.vol_trend,
            'vol_trend_direction': vol_trend_direction,
            'vol_expansion_detected': vol.vol_expansion_detected,
            'vol_compression_detected': vol.vol_compression_detected,
            'vol_shock_detected': vol.vol_shock_detected,
            'confidence': f"{vol.confidence:.2f}",
            'realized_volatility': {
                'short_term': f"{vol.realized_vol_short:.3f}",
                'medium_term': f"{vol.realized_vol_medium:.3f}",
                'long_term': f"{vol.realized_vol_long:.3f}",
                'average': f"{vol.avg_realized_vol:.3f}"
            },
            'last_update': vol.timestamp.strftime('%H:%M:%S')
        }
    
    def reset_daily_state(self) -> None:
        """Reset daily state variables"""
        self.current_vol_analysis = None
        self.vol_history.clear()
        self.vix_data_cache = None
        self.last_analysis_time = None
        self.last_vix_update = None
        
        logger.info("Volatility regime strategy daily state reset")