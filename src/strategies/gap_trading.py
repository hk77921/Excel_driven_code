"""
Strategy 1: Gap Trading Strategy
===============================
Adaptive strategy that adjusts parameters based on market gaps and opening behavior.

Key Features:
- Detects gap up/down situations and adjusts entry criteria
- Different parameters for gap fill vs gap continuation
- Opening range breakout logic
- Risk management based on gap size

Gap Types Handled:
- Small gaps (0.5-1%): Conservative approach
- Medium gaps (1-2%): Balanced approach  
- Large gaps (>2%): Aggressive fade or momentum play

Author: GitHub Copilot
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, time, timedelta
from dataclasses import dataclass

from src.core.models import TradeParameters, ScreenerSignal
from .market_detector import EnhancedMarketDetector, MarketState, GapType, MarketDirection


logger = logging.getLogger(__name__)


@dataclass
class GapTradingParameters:
    """Parameters specific to gap trading strategy"""
    # Base parameters
    base_atr_mult: float = 1.5
    base_target_mult: float = 2.0
    base_partial_exit: float = 0.8
    
    # Gap-specific adjustments
    gap_up_sl_reduction: float = 0.8    # Tighter SL on gap ups
    gap_down_sl_increase: float = 1.2   # Wider SL on gap downs
    
    gap_up_target_increase: float = 1.3  # Higher targets on gap ups
    gap_down_target_reduction: float = 0.8  # Lower targets on gap downs
    
    # Gap fade parameters
    large_gap_fade_threshold: float = 2.0  # >2% gap
    fade_entry_delay_minutes: int = 30     # Wait 30 min before fading
    fade_sl_mult: float = 0.5              # Tight SL for fades
    fade_target_mult: float = 1.0          # Conservative target for fades
    
    # Opening range parameters
    opening_range_minutes: int = 15        # First 15 minutes
    or_breakout_confirmation: float = 0.1  # 0.1% above/below range
    
    # Risk scaling based on gap size
    small_gap_risk_mult: float = 1.0      # Normal risk
    medium_gap_risk_mult: float = 0.8     # Reduce risk 20%
    large_gap_risk_mult: float = 0.6      # Reduce risk 40%


class GapTradingStrategy:
    """
    Gap trading strategy with adaptive parameter adjustment.
    
    This strategy:
    1. Identifies gap situations (up/down)
    2. Determines gap continuation vs gap fill probability
    3. Adjusts entry criteria, stops, and targets accordingly
    4. Implements opening range breakout logic
    5. Manages risk based on gap size
    """
    
    def __init__(self, market_detector: EnhancedMarketDetector):
        """
        Initialize gap trading strategy.
        
        Args:
            market_detector: Enhanced market detector instance
        """
        self.name = "GAP_TRADING"
        self.market_detector = market_detector
        self.params = GapTradingParameters()
        
        # Strategy state
        self.current_market_state: Optional[MarketState] = None
        self.opening_range_high: Optional[float] = None
        self.opening_range_low: Optional[float] = None
        self.opening_range_set: bool = False
        self.market_open_time = time(9, 15)
        
        logger.info("Gap trading strategy initialized")
    
    def update_market_state(self) -> None:
        """Update current market state"""
        self.current_market_state = self.market_detector.get_current_market_state()
        
        # Set opening range if needed
        current_time = datetime.now().time()
        if (current_time >= self.market_open_time and 
            current_time <= time(9, 30) and 
            not self.opening_range_set):
            self._set_opening_range()
    
    def should_enter_trade(self, signal: ScreenerSignal) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Determine if should enter trade based on gap conditions.
        
        Args:
            signal: Screener signal
            
        Returns:
            (should_enter, reason, adjusted_parameters)
        """
        if self.current_market_state is None:
            self.update_market_state()
        
        state = self.current_market_state
        current_time = datetime.now().time()
        
        # Get base decision
        should_enter, reason = self._evaluate_gap_entry(signal, state, current_time)
        
        if not should_enter:
            return False, reason, {}
        
        # Calculate adjusted parameters
        adjusted_params = self._calculate_adjusted_parameters(signal, state)
        
        return True, reason, adjusted_params
    
    def _evaluate_gap_entry(self, signal: ScreenerSignal, state: MarketState, current_time: time) -> Tuple[bool, str]:
        """Evaluate if should enter based on gap conditions"""
        
        # 1. Check if in trading window
        if current_time < time(9, 15) or current_time > time(15, 15):
            return False, "Outside trading hours"
        
        # 2. Gap-specific entry logic
        if state.gap_type == GapType.NO_GAP:
            return self._evaluate_normal_entry(signal, state)
        
        elif state.is_gap_up():
            return self._evaluate_gap_up_entry(signal, state, current_time)
        
        elif state.is_gap_down():
            return self._evaluate_gap_down_entry(signal, state, current_time)
        
        return False, "Unknown gap condition"
    
    def _evaluate_normal_entry(self, signal: ScreenerSignal, state: MarketState) -> Tuple[bool, str]:
        """Evaluate entry for normal (no gap) conditions"""
        
        # Standard entry criteria with slight bias based on market direction
        min_score = 40
        if state.is_bullish():
            min_score = 35  # More aggressive in bullish market
        elif state.is_bearish():
            min_score = 45  # More conservative in bearish market
        
        if signal.score < min_score:
            return False, f"Score {signal.score} below threshold {min_score}"
        
        # Check trend alignment
        if state.is_bullish() and signal.trend != "BULLISH":
            return False, "Trend misalignment in bullish market"
        
        if state.is_bearish() and signal.trend == "BULLISH":
            return False, "Bullish signal in bearish market"
        
        return True, "Normal market entry approved"
    
    def _evaluate_gap_up_entry(self, signal: ScreenerSignal, state: MarketState, current_time: time) -> Tuple[bool, str]:
        """Evaluate entry for gap up conditions"""
        
        gap_size = abs(state.gap_size_pct)
        
        # Large gap up - look for fade opportunities
        if gap_size > self.params.large_gap_fade_threshold:
            return self._evaluate_large_gap_fade(signal, state, current_time, is_gap_up=True)
        
        # Medium/Small gap up - momentum continuation
        if signal.trend != "BULLISH":
            return False, "Need bullish signal for gap up momentum"
        
        # Higher score requirement for gap up momentum
        min_score = 45 if gap_size > 1.0 else 40
        if signal.score < min_score:
            return False, f"Score {signal.score} insufficient for gap up momentum"
        
        # Check if opening range breakout (if range is set)
        if self.opening_range_set and self.opening_range_high is not None:
            current_price = signal.price
            if current_price <= self.opening_range_high * (1 + self.params.or_breakout_confirmation / 100):
                return False, "Waiting for opening range breakout"
        
        return True, f"Gap up momentum entry ({gap_size:.1f}%)"
    
    def _evaluate_gap_down_entry(self, signal: ScreenerSignal, state: MarketState, current_time: time) -> Tuple[bool, str]:
        """Evaluate entry for gap down conditions"""
        
        gap_size = abs(state.gap_size_pct)
        
        # Large gap down - look for bounce opportunities
        if gap_size > self.params.large_gap_fade_threshold:
            return self._evaluate_large_gap_bounce(signal, state, current_time)
        
        # Medium/Small gap down - be cautious with longs
        if signal.trend == "BULLISH":
            # Only strong signals in gap down
            if signal.score < 50:
                return False, f"Score {signal.score} insufficient for gap down long"
            
            # Check RSI oversold
            if state.nifty_rsi > 35:
                return False, "Not oversold enough for gap down long"
        
        return True, f"Gap down cautious entry ({gap_size:.1f}%)"
    
    def _evaluate_large_gap_fade(self, signal: ScreenerSignal, state: MarketState, current_time: time, is_gap_up: bool) -> Tuple[bool, str]:
        """Evaluate fade opportunity for large gaps"""
        
        # Wait for initial momentum to cool off
        minutes_since_open = self._minutes_since_market_open(current_time)
        if minutes_since_open < self.params.fade_entry_delay_minutes:
            return False, f"Waiting {self.params.fade_entry_delay_minutes - minutes_since_open} min before fade"
        
        if is_gap_up:
            # Look for bearish signals to fade gap up
            if signal.trend != "BEARISH" and signal.trend != "NEUTRAL":
                return False, "Need bearish/neutral signal to fade gap up"
            
            # Check if price is still elevated
            if signal.price < state.support_level * 1.01:
                return False, "Gap already filled"
        
        else:  # Gap down
            # Look for bullish signals to fade gap down  
            if signal.trend != "BULLISH":
                return False, "Need bullish signal to fade gap down"
            
            # Check oversold conditions
            if state.nifty_rsi > 30:
                return False, "Not oversold enough for gap down fade"
        
        gap_direction = "up" if is_gap_up else "down"
        return True, f"Large gap {gap_direction} fade opportunity ({abs(state.gap_size_pct):.1f}%)"
    
    def _evaluate_large_gap_bounce(self, signal: ScreenerSignal, state: MarketState, current_time: time) -> Tuple[bool, str]:
        """Evaluate bounce opportunity for large gap down"""
        
        gap_size = abs(state.gap_size_pct)
        
        # Only bullish signals for bounce
        if signal.trend != "BULLISH":
            return False, "Need bullish signal for gap down bounce"
        
        # Check oversold conditions
        if state.nifty_rsi > 25:
            return False, "Not oversold enough for bounce"
        
        # High score requirement
        if signal.score < 55:
            return False, f"Score {signal.score} insufficient for bounce play"
        
        return True, f"Gap down bounce opportunity ({gap_size:.1f}%)"
    
    def _calculate_adjusted_parameters(self, signal: ScreenerSignal, state: MarketState) -> Dict[str, Any]:
        """Calculate adjusted trading parameters based on gap conditions"""
        
        # Start with base parameters
        adjusted_params = {
            'atr_sl_mult': self.params.base_atr_mult,
            'atr_target_mult': self.params.base_target_mult,
            'partial_exit_ratio': self.params.base_partial_exit,
            'risk_multiplier': 1.0,
            'entry_reason': 'gap_strategy'
        }
        
        gap_size = abs(state.gap_size_pct)
        
        # Adjust based on gap type
        if state.gap_type == GapType.NO_GAP:
            # Normal parameters
            pass
        
        elif state.is_gap_up():
            if gap_size > self.params.large_gap_fade_threshold:
                # Large gap up - fade parameters
                adjusted_params.update({
                    'atr_sl_mult': self.params.fade_sl_mult,
                    'atr_target_mult': self.params.fade_target_mult,
                    'risk_multiplier': self.params.large_gap_risk_mult,
                    'entry_reason': 'large_gap_up_fade'
                })
            else:
                # Gap up momentum
                adjusted_params.update({
                    'atr_sl_mult': self.params.base_atr_mult * self.params.gap_up_sl_reduction,
                    'atr_target_mult': self.params.base_target_mult * self.params.gap_up_target_increase,
                    'risk_multiplier': self.params.medium_gap_risk_mult if gap_size > 1.0 else self.params.small_gap_risk_mult,
                    'entry_reason': f'gap_up_momentum_{gap_size:.1f}%'
                })
        
        elif state.is_gap_down():
            if gap_size > self.params.large_gap_fade_threshold:
                # Large gap down - bounce parameters
                adjusted_params.update({
                    'atr_sl_mult': self.params.base_atr_mult * 0.8,  # Tighter SL
                    'atr_target_mult': self.params.base_target_mult * 1.5,  # Higher target for bounce
                    'risk_multiplier': self.params.large_gap_risk_mult,
                    'entry_reason': 'large_gap_down_bounce'
                })
            else:
                # Gap down cautious
                adjusted_params.update({
                    'atr_sl_mult': self.params.base_atr_mult * self.params.gap_down_sl_increase,
                    'atr_target_mult': self.params.base_target_mult * self.params.gap_down_target_reduction,
                    'risk_multiplier': self.params.medium_gap_risk_mult if gap_size > 1.0 else self.params.small_gap_risk_mult,
                    'entry_reason': f'gap_down_cautious_{gap_size:.1f}%'
                })
        
        # Additional adjustments based on market conditions
        if state.volatility_regime.value in ['HIGH', 'EXTREME']:
            adjusted_params['risk_multiplier'] *= 0.7  # Reduce risk in high vol
            adjusted_params['atr_sl_mult'] *= 1.2      # Wider stops
        
        if state.momentum_score > 70:
            adjusted_params['atr_target_mult'] *= 1.2  # Higher targets in strong momentum
        elif state.momentum_score < 30:
            adjusted_params['atr_target_mult'] *= 0.8  # Lower targets in weak momentum
        
        return adjusted_params
    
    def _set_opening_range(self) -> None:
        """Set opening range based on first 15 minutes"""
        try:
            # Get current NIFTY data
            nifty_data = self.market_detector._fetch_intraday_data(
                self.market_detector.nifty_symbol, 
                period="1d", 
                interval="1m"
            )
            
            if not nifty_data.empty:
                # Get data from market open
                market_open_timestamp = datetime.now().replace(hour=9, minute=15, second=0, microsecond=0)
                
                # Filter for opening range
                opening_data = nifty_data[nifty_data.index >= market_open_timestamp.strftime('%Y-%m-%d %H:%M:%S')]
                
                if len(opening_data) >= self.params.opening_range_minutes:
                    self.opening_range_high = opening_data['High'].max()
                    self.opening_range_low = opening_data['Low'].min()
                    self.opening_range_set = True
                    
                    logger.info(f"Opening range set: {self.opening_range_low:.2f} - {self.opening_range_high:.2f}")
        
        except Exception as e:
            logger.warning(f"Failed to set opening range: {e}")
    
    def _minutes_since_market_open(self, current_time: time) -> int:
        """Calculate minutes since market open"""
        now = datetime.now()
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        
        if now >= market_open:
            return int((now - market_open).seconds / 60)
        else:
            return 0
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get current strategy information"""
        if self.current_market_state is None:
            self.update_market_state()
        
        state = self.current_market_state
        
        return {
            'strategy_name': self.name,
            'gap_type': state.gap_type.value if state else 'UNKNOWN',
            'gap_size': f"{state.gap_size_pct:.2f}%" if state else 'N/A',
            'market_direction': state.direction.value if state else 'UNKNOWN',
            'volatility_regime': state.volatility_regime.value if state else 'UNKNOWN',
            'opening_range_set': self.opening_range_set,
            'opening_range': f"{self.opening_range_low:.2f}-{self.opening_range_high:.2f}" if self.opening_range_set else 'Not Set',
            'last_update': state.timestamp.strftime('%H:%M:%S') if state else 'Never'
        }
    
    def reset_daily_state(self) -> None:
        """Reset daily state variables"""
        self.opening_range_high = None
        self.opening_range_low = None
        self.opening_range_set = False
        self.current_market_state = None
        
        logger.info("Gap trading strategy daily state reset")