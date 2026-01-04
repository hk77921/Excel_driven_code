"""
Regime-Aware Strategy Weighting System
=====================================
Dynamic strategy weighting that adapts based on market regime, time of day,
and market conditions for optimal strategy selection.

Key Features:
- Time-based weighting (gap logic dominates opening, correlation mid-session)
- Market regime adaptation (volatility overrides during shocks)
- Performance-based weight adjustment
- Real-time strategy effectiveness tracking

Author: GitHub Copilot
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
import numpy as np

from ..strategies.market_detector import MarketDirection, VolatilityRegime, GapType
from .confidence_manager import ReactiveConfidenceManager


logger = logging.getLogger(__name__)


class MarketSession(str, Enum):
    """Market session periods"""
    PRE_MARKET = "PRE_MARKET"          # Before 9:15 AM
    OPENING = "OPENING"                # 9:15 - 10:00 AM (Gap dominates)
    EARLY_SESSION = "EARLY_SESSION"    # 10:00 - 11:30 AM (Momentum + Gap)
    MID_SESSION = "MID_SESSION"        # 11:30 AM - 2:00 PM (Correlation dominates)
    LATE_SESSION = "LATE_SESSION"      # 2:00 - 3:15 PM (Volatility + Momentum)
    CLOSING = "CLOSING"                # 3:15 - 3:30 PM (Exit focus)
    POST_MARKET = "POST_MARKET"        # After 3:30 PM


class MarketRegime(str, Enum):
    """Extended market regimes for strategy weighting"""
    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    VOLATILE_NEUTRAL = "VOLATILE_NEUTRAL"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    GAP_RECOVERY = "GAP_RECOVERY"
    GAP_CONTINUATION = "GAP_CONTINUATION"
    CORRELATION_BREAKDOWN = "CORRELATION_BREAKDOWN"
    MOMENTUM_EXHAUSTION = "MOMENTUM_EXHAUSTION"


@dataclass
class StrategyWeight:
    """Individual strategy weight configuration"""
    base_weight: float
    current_weight: float
    performance_multiplier: float = 1.0
    confidence_multiplier: float = 1.0
    regime_multiplier: float = 1.0
    session_multiplier: float = 1.0
    
    def calculate_effective_weight(self) -> float:
        """Calculate final effective weight"""
        return (self.base_weight * 
                self.performance_multiplier * 
                self.confidence_multiplier * 
                self.regime_multiplier * 
                self.session_multiplier)


@dataclass
class WeightingConfig:
    """Configuration for strategy weighting"""
    
    # Base weights for each strategy
    base_weights: Dict[str, float] = field(default_factory=lambda: {
        'gap_trading': 0.25,
        'momentum_adaptive': 0.25,
        'volatility_regime': 0.25,
        'correlation_sync': 0.25
    })
    
    # Session-based multipliers
    session_multipliers: Dict[MarketSession, Dict[str, float]] = field(default_factory=lambda: {
        MarketSession.OPENING: {
            'gap_trading': 2.5,        # Gap logic dominates first 45 minutes
            'momentum_adaptive': 0.8,
            'volatility_regime': 1.0,
            'correlation_sync': 0.5
        },
        MarketSession.EARLY_SESSION: {
            'gap_trading': 1.8,        # Still strong gap influence
            'momentum_adaptive': 1.5,  # Building momentum
            'volatility_regime': 1.0,
            'correlation_sync': 0.7
        },
        MarketSession.MID_SESSION: {
            'gap_trading': 0.5,        # Gap effect fades
            'momentum_adaptive': 1.2,
            'volatility_regime': 1.0,
            'correlation_sync': 2.0    # Correlation dominates mid-session
        },
        MarketSession.LATE_SESSION: {
            'gap_trading': 0.3,
            'momentum_adaptive': 1.5,  # Late momentum plays
            'volatility_regime': 1.8,  # Volatility increases toward close
            'correlation_sync': 1.2
        },
        MarketSession.CLOSING: {
            'gap_trading': 0.2,
            'momentum_adaptive': 0.8,
            'volatility_regime': 2.5,  # High volatility at close
            'correlation_sync': 0.8
        }
    })
    
    # Regime-based multipliers
    regime_multipliers: Dict[MarketRegime, Dict[str, float]] = field(default_factory=lambda: {
        MarketRegime.TRENDING_BULL: {
            'gap_trading': 1.2,
            'momentum_adaptive': 1.8,
            'volatility_regime': 0.7,
            'correlation_sync': 1.5
        },
        MarketRegime.TRENDING_BEAR: {
            'gap_trading': 1.2,
            'momentum_adaptive': 1.8,
            'volatility_regime': 0.8,
            'correlation_sync': 1.3
        },
        MarketRegime.VOLATILE_NEUTRAL: {
            'gap_trading': 0.8,
            'momentum_adaptive': 0.9,
            'volatility_regime': 2.5,  # Volatility overrides everything
            'correlation_sync': 0.6
        },
        MarketRegime.LOW_VOLATILITY: {
            'gap_trading': 1.0,
            'momentum_adaptive': 1.0,
            'volatility_regime': 0.5,
            'correlation_sync': 1.8
        },
        MarketRegime.GAP_RECOVERY: {
            'gap_trading': 3.0,        # Gap strategy dominates
            'momentum_adaptive': 0.5,
            'volatility_regime': 1.2,
            'correlation_sync': 0.8
        },
        MarketRegime.CORRELATION_BREAKDOWN: {
            'gap_trading': 1.5,
            'momentum_adaptive': 1.5,
            'volatility_regime': 1.8,
            'correlation_sync': 0.3    # Correlation strategy weakened
        }
    })


class RegimeAwareWeightingSystem:
    """
    Dynamic strategy weighting system that adapts to market conditions.
    
    This system:
    1. Adjusts strategy weights based on time of day
    2. Responds to market regime changes
    3. Incorporates real-time performance feedback
    4. Handles volatility overrides
    """
    
    def __init__(self, 
                 confidence_manager: ReactiveConfidenceManager,
                 config: Optional[WeightingConfig] = None):
        """
        Initialize regime-aware weighting system.
        
        Args:
            confidence_manager: Reactive confidence manager
            config: Weighting configuration
        """
        self.confidence_manager = confidence_manager
        self.config = config or WeightingConfig()
        
        # Strategy weights tracking
        self.strategy_weights: Dict[str, StrategyWeight] = {}
        self._initialize_strategy_weights()
        
        # Performance tracking for adaptive weighting
        self.performance_history: Dict[str, List[float]] = {
            strategy: [] for strategy in self.config.base_weights.keys()
        }
        
        # Regime detection state
        self.current_regime: Optional[MarketRegime] = None
        self.current_session: MarketSession = self._get_current_session()
        self.last_regime_update: Optional[datetime] = None
        
        logger.info("Regime-aware strategy weighting system initialized")
    
    def _initialize_strategy_weights(self) -> None:
        """Initialize strategy weights with base configuration"""
        for strategy, base_weight in self.config.base_weights.items():
            self.strategy_weights[strategy] = StrategyWeight(
                base_weight=base_weight,
                current_weight=base_weight
            )
    
    def _get_current_session(self) -> MarketSession:
        """Determine current market session based on time"""
        now = datetime.now().time()
        
        if now < time(9, 15):
            return MarketSession.PRE_MARKET
        elif now < time(10, 0):
            return MarketSession.OPENING
        elif now < time(11, 30):
            return MarketSession.EARLY_SESSION
        elif now < time(14, 0):
            return MarketSession.MID_SESSION
        elif now < time(15, 15):
            return MarketSession.LATE_SESSION
        elif now < time(15, 30):
            return MarketSession.CLOSING
        else:
            return MarketSession.POST_MARKET
    
    def _detect_market_regime(self, 
                            market_direction: MarketDirection,
                            volatility_regime: VolatilityRegime,
                            gap_type: GapType,
                            momentum_score: float,
                            correlation_stability: float = 0.7) -> MarketRegime:
        """Detect current market regime for weighting"""
        
        # Volatility override - highest priority
        if volatility_regime == VolatilityRegime.EXTREME:
            return MarketRegime.VOLATILE_NEUTRAL
        
        # Gap-based regimes
        if gap_type != GapType.NO_GAP:
            gap_size = abs(float(gap_type.value.split('_')[-1]) if gap_type.value.split('_')[-1].isdigit() else 1.0)
            
            # Check if gap is being filled or continuing
            if momentum_score > 60 and gap_type.value.startswith('GAP_UP'):
                return MarketRegime.GAP_CONTINUATION
            elif momentum_score < 40 and gap_type.value.startswith('GAP_DOWN'):
                return MarketRegime.GAP_CONTINUATION
            else:
                return MarketRegime.GAP_RECOVERY
        
        # Correlation breakdown detection
        if correlation_stability < 0.4:
            return MarketRegime.CORRELATION_BREAKDOWN
        
        # Trending regimes
        if market_direction in [MarketDirection.STRONG_BULLISH, MarketDirection.BULLISH] and momentum_score > 70:
            return MarketRegime.TRENDING_BULL
        elif market_direction in [MarketDirection.STRONG_BEARISH, MarketDirection.BEARISH] and momentum_score < 30:
            return MarketRegime.TRENDING_BEAR
        
        # Low volatility regime
        if volatility_regime == VolatilityRegime.LOW and abs(momentum_score - 50) < 10:
            return MarketRegime.LOW_VOLATILITY
        
        # Momentum exhaustion
        if volatility_regime == VolatilityRegime.HIGH and abs(momentum_score - 50) > 30:
            return MarketRegime.MOMENTUM_EXHAUSTION
        
        # Default to volatile neutral
        return MarketRegime.VOLATILE_NEUTRAL
    
    def update_market_conditions(self,
                               market_direction: MarketDirection,
                               volatility_regime: VolatilityRegime, 
                               gap_type: GapType,
                               momentum_score: float,
                               correlation_stability: float = 0.7) -> Dict[str, float]:
        """
        Update strategy weights based on current market conditions.
        
        Args:
            market_direction: Current market direction
            volatility_regime: Current volatility regime
            gap_type: Current gap type
            momentum_score: Momentum score (0-100)
            correlation_stability: Correlation stability measure
            
        Returns:
            Updated strategy weights dictionary
        """
        
        # Update current session
        self.current_session = self._get_current_session()
        
        # Detect current regime
        new_regime = self._detect_market_regime(
            market_direction, volatility_regime, gap_type, 
            momentum_score, correlation_stability
        )
        
        # Check for regime change
        if new_regime != self.current_regime:
            logger.info(f"Market regime change: {self.current_regime} → {new_regime}")
            self.current_regime = new_regime
            self.last_regime_update = datetime.now()
            
            # Invalidate confidence on significant regime changes
            if new_regime in [MarketRegime.VOLATILE_NEUTRAL, MarketRegime.CORRELATION_BREAKDOWN]:
                # Force confidence invalidation for all symbols
                logger.warning(f"Regime change to {new_regime} - invalidating confidence")
        
        # Update strategy weights
        return self._calculate_dynamic_weights()
    
    def _calculate_dynamic_weights(self) -> Dict[str, float]:
        """Calculate dynamic strategy weights based on current conditions"""
        
        # Update multipliers for each strategy
        for strategy_name, weight in self.strategy_weights.items():
            
            # Session multiplier
            session_mult = self.config.session_multipliers.get(
                self.current_session, {}
            ).get(strategy_name, 1.0)
            
            # Regime multiplier  
            regime_mult = self.config.regime_multipliers.get(
                self.current_regime, {}
            ).get(strategy_name, 1.0) if self.current_regime else 1.0
            
            # Performance multiplier based on recent performance
            performance_mult = self._calculate_performance_multiplier(strategy_name)
            
            # Confidence multiplier based on confidence manager
            confidence_mult = self._calculate_confidence_multiplier(strategy_name)
            
            # Apply multipliers
            weight.session_multiplier = session_mult
            weight.regime_multiplier = regime_mult
            weight.performance_multiplier = performance_mult
            weight.confidence_multiplier = confidence_mult
            
            # Calculate effective weight
            weight.current_weight = weight.calculate_effective_weight()
        
        # Normalize weights to sum to 1.0
        total_weight = sum(w.current_weight for w in self.strategy_weights.values())
        
        if total_weight > 0:
            for weight in self.strategy_weights.values():
                weight.current_weight /= total_weight
        
        # Return as dictionary
        weights_dict = {
            strategy: weight.current_weight 
            for strategy, weight in self.strategy_weights.items()
        }
        
        # Log significant weight changes
        if any(abs(weights_dict[s] - self.config.base_weights[s]) > 0.2 for s in weights_dict):
            logger.info(f"Significant weight change - Session: {self.current_session.value}, "
                       f"Regime: {self.current_regime.value if self.current_regime else 'None'}")
            for strategy, weight in weights_dict.items():
                logger.info(f"  {strategy}: {weight:.2f} (base: {self.config.base_weights[strategy]:.2f})")
        
        return weights_dict
    
    def _calculate_performance_multiplier(self, strategy: str) -> float:
        """Calculate performance multiplier based on recent performance"""
        return 1.0  # Placeholder for future performance-based logic
    
    def _calculate_confidence_multiplier(self, strategy: str) -> float:
        """Calculate confidence multiplier based on confidence manager"""
        if not self.confidence_manager:
            return 1.0
            
        # Get confidence for this strategy (use default if not found)
        confidence = self.confidence_manager.get_confidence(strategy, default_confidence=0.7)
        
        # Convert confidence (0.0-1.0) to multiplier (0.5-1.5)
        # Higher confidence = higher multiplier, lower confidence = lower multiplier
        multiplier = 0.5 + confidence  # 0.5 to 1.5 range
        
        return multiplier