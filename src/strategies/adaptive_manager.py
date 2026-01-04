"""
Adaptive Strategy Manager (Enhanced with Regime-Aware Weighting)
===============================================================
Central coordinator for all adaptive trading strategies with dynamic weighting.

This manager:
1. Coordinates all 4 adaptive strategies with regime-aware weighting
2. Dynamically adjusts strategy weights based on market conditions
3. Uses real-time confidence decay and validation
4. Implements time-of-day and regime-based strategy selection
5. Manages strategy switching logic with performance feedback
6. Provides unified parameter adjustments

Strategies Managed:
- Gap Trading Strategy: Handles market gaps and opening behavior
- Momentum Adaptive Strategy: Scales with market momentum  
- Volatility Regime Strategy: Adapts to volatility environments
- Correlation Sync Strategy: Optimizes based on index correlation

Author: GitHub Copilot
"""

import logging
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, time
from dataclasses import dataclass
from enum import Enum

from .market_detector import EnhancedMarketDetector, MarketState
from .gap_trading import GapTradingStrategy
from .momentum_adaptive import MomentumAdaptiveStrategy
from .volatility_regime import VolatilityRegimeStrategy
from .correlation_sync import CorrelationSyncStrategy
from src.core.regime_weighting import RegimeAwareWeightingSystem, MarketRegime as WeightingRegime
from src.core.confidence_manager import ReactiveConfidenceManager
from src.core.models import ScreenerSignal, TradeParameters


logger = logging.getLogger(__name__)


class StrategyMode(str, Enum):
    """Strategy selection modes"""
    AUTO = "AUTO"                    # Automatic selection based on conditions
    GAP_FOCUSED = "GAP_FOCUSED"     # Prioritize gap trading
    MOMENTUM_FOCUSED = "MOMENTUM_FOCUSED"   # Prioritize momentum
    VOLATILITY_FOCUSED = "VOLATILITY_FOCUSED"  # Prioritize volatility
    CORRELATION_FOCUSED = "CORRELATION_FOCUSED"  # Prioritize correlation
    ENSEMBLE = "ENSEMBLE"            # Use all strategies in ensemble
    CONSERVATIVE = "CONSERVATIVE"    # Most conservative approach
    AGGRESSIVE = "AGGRESSIVE"        # Most aggressive approach


@dataclass
class StrategyDecision:
    """Decision from strategy manager"""
    should_enter: bool
    primary_strategy: str
    contributing_strategies: List[str]
    combined_reason: str
    final_parameters: Dict[str, Any]
    risk_adjustment: float
    strategy_weights: Dict[str, float]
    timestamp: datetime
    confidence_score: float = 0.5


@dataclass
class StrategyConfiguration:
    """Configuration for strategy manager"""
    mode: StrategyMode = StrategyMode.AUTO
    
    # Strategy weights (when using ensemble mode)
    gap_weight: float = 0.25
    momentum_weight: float = 0.25
    volatility_weight: float = 0.25
    correlation_weight: float = 0.25
    
    # Strategy selection thresholds
    gap_priority_threshold: float = 1.0      # Gap size % to prioritize gap strategy
    momentum_priority_threshold: float = 80.0 # Momentum score to prioritize momentum
    volatility_priority_threshold: float = 30.0  # VIX level to prioritize volatility
    correlation_priority_threshold: float = 0.8  # Correlation to prioritize correlation
    
    # Risk management
    max_combined_risk_mult: float = 2.0      # Maximum combined risk multiplier
    min_confidence_required: float = 0.6     # Minimum confidence to trade
    
    # Strategy switching
    enable_strategy_switching: bool = True
    switching_cooldown_minutes: int = 30     # Minutes between strategy switches


class AdaptiveStrategyManager:
    """
    Central manager for all adaptive trading strategies.
    
    Coordinates multiple strategies to provide optimal trade decisions
    based on current market conditions and individual stock characteristics.
    """
    
    def __init__(self, config: Optional[StrategyConfiguration] = None):
        """
        Initialize adaptive strategy manager with regime-aware weighting.
        
        Args:
            config: Strategy configuration
        """
        self.config = config or StrategyConfiguration()
        
        # Initialize market detector (includes real-time monitoring and confidence management)
        self.market_detector = EnhancedMarketDetector()
        
        # Get confidence manager from market detector
        self.confidence_manager = self.market_detector.confidence_manager
        
        # Initialize regime-aware weighting system
        self.weighting_system = RegimeAwareWeightingSystem(
            confidence_manager=self.confidence_manager
        )
        
        # Initialize all strategies
        self.gap_strategy = GapTradingStrategy(self.market_detector)
        self.momentum_strategy = MomentumAdaptiveStrategy(self.market_detector)
        self.volatility_strategy = VolatilityRegimeStrategy(self.market_detector)
        self.correlation_strategy = CorrelationSyncStrategy(self.market_detector)
        
        # Strategy state
        self.current_mode = self.config.mode
        self.last_strategy_switch: Optional[datetime] = None
        self.strategy_performance: Dict[str, List[float]] = {
            'gap_trading': [],
            'momentum_adaptive': [],
            'volatility_regime': [],
            'correlation_sync': []
        }
        
        # Decision history for analysis
        self.decision_history: List[StrategyDecision] = []
        
        # Current strategy weights (updated dynamically)
        self.current_weights: Dict[str, float] = {}
        
        logger.info(f"Adaptive strategy manager initialized with regime-aware weighting in {self.current_mode.value} mode")
    
    def _get_market_context(self, market_state: MarketState) -> Dict[str, Any]:
        """Get market context for decision logging"""
        return {
            'direction': market_state.direction.value,
            'gap_type': market_state.gap_type.value,
            'gap_size_pct': market_state.gap_size_pct,
            'volatility_regime': market_state.volatility_regime.value,
            'momentum_score': market_state.momentum_score,
            'is_high_volatility': market_state.is_high_volatility(),
            'timestamp': datetime.now().isoformat()
        }
    
    def evaluate_trade_entry(self, signal: ScreenerSignal) -> StrategyDecision:
        """
        Evaluate trade entry using all available strategies with regime-aware weighting.
        
        Args:
            signal: Screener signal to evaluate
            
        Returns:
            StrategyDecision with combined analysis
        """
        try:
            current_time = datetime.now()
            
            # Update market state
            market_state = self.market_detector.get_current_market_state()
            
            # Update regime-aware weights based on current market conditions
            # Extract correlation stability from correlation strategy
            correlation_stability = 0.7  # Default
            try:
                correlation_analysis = self.correlation_strategy._get_correlation_analysis(signal.symbol)
                if correlation_analysis:
                    correlation_stability = correlation_analysis.correlation_stability
            except Exception as e:
                logger.debug(f"Could not get correlation stability: {e}")
            
            # Update dynamic weights
            self.current_weights = self.weighting_system.update_market_conditions(
                market_direction=market_state.direction,
                volatility_regime=market_state.volatility_regime,
                gap_type=market_state.gap_type,
                momentum_score=market_state.momentum_score,
                correlation_stability=correlation_stability
            )
            
            # Add symbol to real-time monitoring if available
            if hasattr(signal, 'price') and signal.price > 0:
                # Check if add_symbol method exists
                if hasattr(self.market_detector.realtime_monitor, 'add_symbol'):
                    self.market_detector.realtime_monitor.add_symbol(signal.symbol, signal.price)
                else:
                    logger.debug(f"Real-time monitor doesn't have add_symbol method for {signal.symbol}")
            
            # Determine which strategies to use based on weights
            active_strategies = self._select_active_strategies_weighted(market_state)
            
            logger.info(f"Evaluating {signal.symbol} with strategies: {active_strategies} | "
                       f"Weights: {self.current_weights}")
            
            # Evaluate each active strategy
            strategy_decisions = {}
            positive_strategies = []
            
            for strategy_name in active_strategies:
                strategy_decision = self._evaluate_single_strategy(strategy_name, signal, market_state)
                strategy_decisions[strategy_name] = strategy_decision
                
                if strategy_decision['should_enter']:
                    positive_strategies.append(strategy_name)
            
            # Make final decision using weighted ensemble
            if positive_strategies:
                final_decision = self._make_weighted_ensemble_decision(
                    positive_strategies, strategy_decisions, signal, market_state
                )
            else:
                final_decision = StrategyDecision(
                    should_enter=False,
                    primary_strategy="NONE",
                    contributing_strategies=[],
                    combined_reason="No strategies approved entry",
                    final_parameters={},
                    confidence_score=0.0,
                    risk_adjustment=1.0,
                    strategy_weights={},
                    timestamp=current_time
                )
            
            # Record decision
            self.decision_history.append(final_decision)
            
            # Keep only last 100 decisions
            if len(self.decision_history) > 100:
                self.decision_history = self.decision_history[-100:]
            
            return final_decision
            
        except Exception as e:
            logger.error(f"Error evaluating trade entry for {signal.symbol}: {e}")
            return StrategyDecision(
                should_enter=False,
                primary_strategy="ERROR",
                contributing_strategies=[],
                combined_reason=f"Evaluation error: {str(e)}",
                final_parameters={},
                confidence_score=0.0,
                risk_adjustment=1.0,
                strategy_weights={},
                timestamp=datetime.now()
            )
    
    def _evaluate_single_strategy(self, strategy_name: str, signal: ScreenerSignal, market_state: MarketState) -> Dict[str, Any]:
        """Evaluate a single strategy for the given signal"""
        
        try:
            if strategy_name == 'gap_trading':
                should_enter, reason, params = self.gap_strategy.should_enter_trade(signal)
            elif strategy_name == 'momentum_adaptive':
                should_enter, reason, params = self.momentum_strategy.should_enter_trade(signal)
            elif strategy_name == 'volatility_regime':
                should_enter, reason, params = self.volatility_strategy.should_enter_trade(signal)
            elif strategy_name == 'correlation_sync':
                should_enter, reason, params = self.correlation_strategy.should_enter_trade(signal)
            else:
                logger.warning(f"Unknown strategy: {strategy_name}")
                return {'should_enter': False, 'reason': f'Unknown strategy: {strategy_name}', 
                       'confidence': 0.0, 'parameters': {}}
            
            # Extract confidence from parameters or use default based on should_enter
            confidence = params.get('confidence', 0.8 if should_enter else 0.2)
            
            # Apply strategy weight as confidence multiplier
            strategy_weight = self.current_weights.get(strategy_name, 0.25)
            adjusted_confidence = confidence * (0.5 + strategy_weight)  # Weight influences confidence
            
            return {
                'should_enter': should_enter,
                'reason': reason,
                'confidence': adjusted_confidence,
                'parameters': params,
                'strategy_weight': strategy_weight
            }
            
        except Exception as e:
            logger.error(f"Error evaluating {strategy_name} strategy: {e}")
            return {'should_enter': False, 'reason': f'Strategy error: {str(e)}', 
                   'confidence': 0.0, 'parameters': {}}
            
    def _make_weighted_ensemble_decision(self, 
                                       positive_strategies: List[str],
                                       strategy_decisions: Dict[str, Dict],
                                       signal: ScreenerSignal,
                                       market_state: MarketState) -> StrategyDecision:
        """Make final decision using weighted ensemble of positive strategies"""
        
        # Calculate weighted confidence and parameters
        total_weight = sum(self.current_weights.get(s, 0) for s in positive_strategies)
        
        if total_weight == 0:
            return StrategyDecision(
                should_enter=False,
                primary_strategy="NONE",
                contributing_strategies=[],
                combined_reason="No positive strategy weights",
                final_parameters={},
                confidence_score=0.0,
                risk_adjustment=1.0,
                strategy_weights={},
                timestamp=datetime.now()
            )
        
        # Normalize weights for positive strategies
        normalized_weights = {
            strategy: self.current_weights.get(strategy, 0) / total_weight
            for strategy in positive_strategies
        }
        
        # Calculate weighted confidence
        weighted_confidence = sum(
            strategy_decisions[s]['confidence'] * weight
            for s, weight in normalized_weights.items()
        )
        
        # Determine primary strategy (highest weight among positive)
        primary_strategy = max(positive_strategies, 
                             key=lambda s: self.current_weights.get(s, 0))
        
        # Combine parameters from all positive strategies (weighted average)
        combined_params = self._combine_weighted_parameters(
            positive_strategies, strategy_decisions, normalized_weights
        )

        return StrategyDecision(
            should_enter=True,
            primary_strategy=primary_strategy,
            contributing_strategies=positive_strategies,
            combined_reason="Weighted ensemble entry",
            final_parameters=combined_params,
            confidence_score=weighted_confidence,
            risk_adjustment=self._calculate_risk_adjustment(
                positive_strategies, combined_params, market_state
            ),
            strategy_weights=normalized_weights,
            timestamp=datetime.now()
        )
    
    def _combine_weighted_parameters(self, positive_strategies: List[str], 
                                   strategy_decisions: Dict[str, Dict], 
                                   normalized_weights: Dict[str, float]) -> Dict[str, Any]:
        """Combine parameters from multiple strategies using weighted average"""
        
        combined_params = {}
        
        # Parameters to combine numerically
        numeric_params = [
            'atr_sl_mult', 'atr_target_mult', 'partial_exit_ratio', 
            'position_size_multiplier', 'risk_multiplier'
        ]
        
        # Combine numeric parameters using weighted average
        for param in numeric_params:
            weighted_sum = 0
            total_weight = 0
            
            for strategy in positive_strategies:
                params = strategy_decisions[strategy]['parameters']
                if param in params:
                    weight = normalized_weights.get(strategy, 0.25)
                    weighted_sum += params[param] * weight
                    total_weight += weight
            
            if total_weight > 0:
                combined_params[param] = weighted_sum / total_weight
            else:
                # Default values
                defaults = {
                    'atr_sl_mult': 1.5,
                    'atr_target_mult': 2.0,
                    'partial_exit_ratio': 0.8,
                    'position_size_multiplier': 1.0,
                    'risk_multiplier': 1.0
                }
                combined_params[param] = defaults.get(param, 1.0)
        
        # Add metadata
        combined_params['contributing_strategies'] = positive_strategies
        combined_params['strategy_weights'] = normalized_weights
        
        return combined_params
    
    def _select_active_strategies_weighted(self, market_state: MarketState) -> List[str]:
        """Select strategies based on current weights (above threshold)"""
        
        # Include strategies with weight above minimum threshold
        min_weight_threshold = 0.05  # 5% minimum weight to be active
        
        active_strategies = [
            strategy for strategy, weight in self.current_weights.items()
            if weight >= min_weight_threshold
        ]
        
        # Ensure at least one strategy is active (highest weighted)
        if not active_strategies:
            best_strategy = max(self.current_weights.items(), key=lambda x: x[1])
            active_strategies = [best_strategy[0]]
        
        # Always include volatility strategy if high volatility regime
        if (market_state.volatility_regime.value in ['HIGH', 'EXTREME'] and 
            'volatility_regime' not in active_strategies):
            active_strategies.append('volatility_regime')
        
        logger.debug(f"Active strategies (weighted): {active_strategies}")
        return active_strategies
    
    def _select_active_strategies_legacy(self, market_state: MarketState) -> List[str]:
        """Legacy strategy selection method based on mode"""
        active_strategies = []
        
        if self.current_mode == StrategyMode.AUTO:
            # Auto mode logic
            active_strategies = ['gap_trading', 'momentum_adaptive', 'volatility_regime', 'correlation_sync']
        
        elif self.current_mode == StrategyMode.ENSEMBLE:
            # Use all strategies
            active_strategies = ['gap_trading', 'momentum_adaptive', 'volatility_regime', 'correlation_sync']
        
        elif self.current_mode == StrategyMode.GAP_FOCUSED:
            active_strategies = ['gap_trading', 'volatility_regime']
        
        elif self.current_mode == StrategyMode.MOMENTUM_FOCUSED:
            active_strategies = ['momentum_adaptive', 'volatility_regime']
        
        elif self.current_mode == StrategyMode.VOLATILITY_FOCUSED:
            active_strategies = ['volatility_regime', 'correlation_sync']
        
        elif self.current_mode == StrategyMode.CORRELATION_FOCUSED:
            active_strategies = ['correlation_sync', 'volatility_regime']
        
        elif self.current_mode == StrategyMode.CONSERVATIVE:
            # Use volatility and correlation for conservative approach
            active_strategies = ['volatility_regime', 'correlation_sync']
        
        elif self.current_mode == StrategyMode.AGGRESSIVE:
            # Use gap and momentum for aggressive approach
            active_strategies = ['gap_trading', 'momentum_adaptive']
        
        else:
            # Default to ensemble
            active_strategies = ['gap_trading', 'momentum_adaptive', 'volatility_regime', 'correlation_sync']
        
        return active_strategies
    
    def _get_strategy_decision(self, strategy_name: str, signal: ScreenerSignal) -> Dict[str, Any]:
        """Get decision from a specific strategy"""
        try:
            if strategy_name == 'gap_trading':
                should_enter, reason, params = self.gap_strategy.should_enter_trade(signal)
            elif strategy_name == 'momentum_adaptive':
                should_enter, reason, params = self.momentum_strategy.should_enter_trade(signal)
            elif strategy_name == 'volatility_regime':
                should_enter, reason, params = self.volatility_strategy.should_enter_trade(signal)
            elif strategy_name == 'correlation_sync':
                should_enter, reason, params = self.correlation_strategy.should_enter_trade(signal)
            else:
                return {'should_enter': False, 'reason': 'Unknown strategy', 'params': {}}
            
            return {
                'should_enter': should_enter,
                'reason': reason,
                'params': params,
                'confidence': params.get('confidence_score', 0.5) if params else 0.5
            }
            
        except Exception as e:
            logger.warning(f"Strategy {strategy_name} failed: {e}")
            return {'should_enter': False, 'reason': f'Strategy error: {e}', 'params': {}}
    
    def _combine_strategy_decisions(self, signal: ScreenerSignal, market_state: MarketState, 
                                  strategy_decisions: Dict[str, Dict], active_strategies: List[str]) -> StrategyDecision:
        """Combine decisions from multiple strategies"""
        
        # Count positive decisions
        positive_decisions = [name for name in active_strategies 
                            if strategy_decisions[name]['should_enter']]
        
        # If no strategies approve, return negative decision
        if not positive_decisions:
            reasons = [f"{name}: {strategy_decisions[name]['reason']}" 
                      for name in active_strategies]
            
            return StrategyDecision(
                should_enter=False,
                primary_strategy="NONE",
                contributing_strategies=[],
                combined_reason=f"No strategy approval - {'; '.join(reasons)}",
                final_parameters={},
                confidence_score=0.0,
                risk_adjustment=1.0,
                strategy_weights={},
                timestamp=datetime.now()
            )
        
        # Determine primary strategy based on mode and conditions
        primary_strategy = self._select_primary_strategy(positive_decisions, market_state, strategy_decisions)
        
        # Calculate strategy weights
        strategy_weights = self._calculate_strategy_weights(positive_decisions, strategy_decisions)
        
        # Combine parameters from all positive strategies
        combined_params = self._combine_parameters(positive_decisions, strategy_decisions, strategy_weights)
        
        # Calculate overall confidence
        confidence_scores = [strategy_decisions[name]['confidence'] for name in positive_decisions]
        overall_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
        
        # Adjust confidence based on strategy agreement
        agreement_bonus = min(0.2, len(positive_decisions) * 0.05)  # Up to 20% bonus for agreement
        overall_confidence = min(1.0, overall_confidence + agreement_bonus)
        
        # Check minimum confidence requirement
        if overall_confidence < self.config.min_confidence_required:
            return StrategyDecision(
                should_enter=False,
                primary_strategy=primary_strategy,
                contributing_strategies=positive_decisions,
                combined_reason=f"Confidence {overall_confidence:.2f} below threshold {self.config.min_confidence_required}",
                final_parameters={},
                confidence_score=overall_confidence,
                risk_adjustment=1.0,
                strategy_weights=strategy_weights,
                timestamp=datetime.now()
            )
        
        # Calculate risk adjustment
        risk_adjustment = self._calculate_risk_adjustment(positive_decisions, combined_params, market_state)
        
        # Create combined reason
        reasons = [f"{name} ({strategy_decisions[name]['reason']})" for name in positive_decisions]
        combined_reason = f"Multi-strategy entry: {', '.join(reasons)}"
        
        return StrategyDecision(
            should_enter=True,
            primary_strategy=primary_strategy,
            contributing_strategies=positive_decisions,
            combined_reason=combined_reason,
            final_parameters=combined_params,
            confidence_score=overall_confidence,
            risk_adjustment=risk_adjustment,
            strategy_weights=strategy_weights,
            timestamp=datetime.now()
        )
    
    def _select_primary_strategy(self, positive_strategies: List[str], market_state: MarketState, 
                               strategy_decisions: Dict[str, Dict]) -> str:
        """Select the primary strategy from positive strategies"""
        
        # Priority based on market conditions
        if 'gap_trading' in positive_strategies and abs(market_state.gap_size_pct) > 1.5:
            return 'gap_trading'
        
        if 'momentum_adaptive' in positive_strategies and (
            market_state.momentum_score > 80 or market_state.momentum_score < 20
        ):
            return 'momentum_adaptive'
        
        if 'volatility_regime' in positive_strategies and market_state.is_high_volatility():
            return 'volatility_regime'
        
        # Default to highest confidence strategy
        max_confidence = 0
        primary = positive_strategies[0] if positive_strategies else 'volatility_regime'
        
        for strategy in positive_strategies:
            confidence = strategy_decisions[strategy]['confidence']
            if confidence > max_confidence:
                max_confidence = confidence
                primary = strategy
        
        return primary
    
    def _calculate_strategy_weights(self, positive_strategies: List[str], 
                                  strategy_decisions: Dict[str, Dict]) -> Dict[str, float]:
        """Calculate weights for each contributing strategy"""
        
        if len(positive_strategies) == 1:
            return {positive_strategies[0]: 1.0}
        
        # Base weights from configuration
        base_weights = {
            'gap_trading': self.config.gap_weight,
            'momentum_adaptive': self.config.momentum_weight,
            'volatility_regime': self.config.volatility_weight,
            'correlation_sync': self.config.correlation_weight
        }
        
        # Adjust weights based on confidence
        strategy_weights = {}
        total_weight = 0
        
        for strategy in positive_strategies:
            confidence = strategy_decisions[strategy]['confidence']
            weight = base_weights.get(strategy, 0.25) * confidence
            strategy_weights[strategy] = weight
            total_weight += weight
        
        # Normalize weights
        if total_weight > 0:
            for strategy in strategy_weights:
                strategy_weights[strategy] /= total_weight
        
        return strategy_weights
    
    def _combine_parameters(self, positive_strategies: List[str], strategy_decisions: Dict[str, Dict], 
                          strategy_weights: Dict[str, float]) -> Dict[str, Any]:
        """Combine parameters from multiple strategies using weighted average"""
        
        combined_params = {}
        
        # Parameters to combine numerically
        numeric_params = [
            'atr_sl_mult', 'atr_target_mult', 'partial_exit_ratio', 
            'position_size_multiplier', 'risk_multiplier'
        ]
        
        # Combine numeric parameters using weighted average
        for param in numeric_params:
            weighted_sum = 0
            total_weight = 0
            
            for strategy in positive_strategies:
                params = strategy_decisions[strategy]['params']
                if param in params:
                    weight = strategy_weights.get(strategy, 0.25)
                    weighted_sum += params[param] * weight
                    total_weight += weight
            
            if total_weight > 0:
                combined_params[param] = weighted_sum / total_weight
            else:
                # Default values
                defaults = {
                    'atr_sl_mult': 1.5,
                    'atr_target_mult': 2.0,
                    'partial_exit_ratio': 0.8,
                    'position_size_multiplier': 1.0,
                    'risk_multiplier': 1.0
                }
                combined_params[param] = defaults.get(param, 1.0)
        
        # Cap the combined risk multiplier
        if 'position_size_multiplier' in combined_params:
            combined_params['position_size_multiplier'] = min(
                combined_params['position_size_multiplier'], 
                self.config.max_combined_risk_mult
            )
        
        # Add metadata from strategies
        combined_params['contributing_strategies'] = positive_strategies
        combined_params['strategy_weights'] = strategy_weights
        
        # Collect all entry reasons
        entry_reasons = []
        for strategy in positive_strategies:
            params = strategy_decisions[strategy]['params']
            if 'entry_reason' in params:
                entry_reasons.append(f"{strategy}:{params['entry_reason']}")
        
        combined_params['entry_reason'] = '|'.join(entry_reasons) if entry_reasons else 'multi_strategy'
        
        return combined_params
    
    def _calculate_risk_adjustment(self, positive_strategies: List[str], combined_params: Dict[str, Any], 
                                 market_state: MarketState) -> float:
        """Calculate overall risk adjustment factor"""
        
        risk_factors = []
        
        # Base risk from combined multiplier
        base_risk = combined_params.get('position_size_multiplier', 1.0)
        risk_factors.append(base_risk)
        
        # Market state risk adjustments
        if market_state.is_high_volatility():
            risk_factors.append(0.8)  # Reduce risk in high volatility
        
        if abs(market_state.gap_size_pct) > 2.0:
            risk_factors.append(0.9)  # Reduce risk for large gaps
        
        # Strategy diversity bonus
        if len(positive_strategies) >= 3:
            risk_factors.append(1.1)  # Small bonus for strategy agreement
        
        # Calculate final risk adjustment
        final_risk = 1.0
        for factor in risk_factors:
            final_risk *= factor
        
        return min(self.config.max_combined_risk_mult, max(0.3, final_risk))
    
    def _get_default_decision(self, signal: ScreenerSignal) -> StrategyDecision:
        """Get default decision when analysis fails"""
        return StrategyDecision(
            should_enter=False,
            primary_strategy="ERROR",
            contributing_strategies=[],
            combined_reason="Strategy analysis failed - using conservative default",
            final_parameters={},
            confidence_score=0.0,
            risk_adjustment=1.0,
            strategy_weights={},
            timestamp=datetime.now()
        )
    
    def get_strategy_status(self) -> Dict[str, Any]:
        """Get comprehensive strategy manager status"""
        
        # Get current market state
        market_state = self.market_detector.get_current_market_state()
        
        # Get individual strategy status
        gap_info = self.gap_strategy.get_strategy_info()
        momentum_info = self.momentum_strategy.get_momentum_summary()
        volatility_info = self.volatility_strategy.get_volatility_summary()
        correlation_info = self.correlation_strategy.get_correlation_summary()
        
        # Recent decisions summary
        recent_decisions = self.decision_history[-10:] if self.decision_history else []
        entry_rate = sum(1 for d in recent_decisions if d.should_enter) / max(1, len(recent_decisions))
        
        # Primary strategies used
        primary_strategies = [d.primary_strategy for d in recent_decisions if d.should_enter]
        strategy_usage = {}
        for strategy in primary_strategies:
            strategy_usage[strategy] = strategy_usage.get(strategy, 0) + 1
        
        return {
            'manager_status': {
                'current_mode': self.current_mode.value,
                'last_strategy_switch': self.last_strategy_switch.strftime('%H:%M:%S') if self.last_strategy_switch else 'Never',
                'recent_entry_rate': f"{entry_rate:.1%}",
                'total_decisions': len(self.decision_history),
                'strategy_usage': strategy_usage
            },
            'market_state': {
                'direction': market_state.direction.value,
                'gap_type': market_state.gap_type.value,
                'gap_size': f"{market_state.gap_size_pct:.2f}%",
                'volatility_regime': market_state.volatility_regime.value,
                'momentum_score': f"{market_state.momentum_score:.1f}"
            },
            'individual_strategies': {
                'gap_trading': gap_info,
                'momentum_adaptive': momentum_info,
                'volatility_regime': volatility_info,
                'correlation_sync': correlation_info
            }
        }
    
    def switch_mode(self, new_mode: StrategyMode, reason: str = "Manual switch") -> bool:
        """Switch strategy mode with cooldown protection"""
        
        current_time = datetime.now()
        
        # Check cooldown
        if (self.config.enable_strategy_switching and 
            self.last_strategy_switch is not None and
            (current_time - self.last_strategy_switch).seconds < self.config.switching_cooldown_minutes * 60):
            
            logger.warning(f"Strategy switch blocked - cooldown active")
            return False
        
        old_mode = self.current_mode
        self.current_mode = new_mode
        self.last_strategy_switch = current_time
        
        logger.info(f"Strategy mode switched: {old_mode.value} → {new_mode.value} ({reason})")
        return True
    
    def reset_daily_state(self) -> None:
        """Reset daily state for all strategies"""
        
        # Reset individual strategies
        self.gap_strategy.reset_daily_state()
        self.momentum_strategy.reset_daily_state()
        self.volatility_strategy.reset_daily_state()
        self.correlation_strategy.reset_daily_state()
        
        # Reset manager state
        self.decision_history.clear()
        self.strategy_performance = {
            'gap_trading': [],
            'momentum_adaptive': [],
            'volatility_regime': [],
            'correlation_sync': []
        }
        
        logger.info("Adaptive strategy manager daily state reset")
    
    def update_strategy_performance(self, strategy: str, pnl_pct: float) -> None:
        """Update strategy performance tracking for both manager and weighting system"""
        if strategy in self.strategy_performance:
            self.strategy_performance[strategy].append(pnl_pct)
            
            # Keep only last 50 trades per strategy
            if len(self.strategy_performance[strategy]) > 50:
                self.strategy_performance[strategy] = self.strategy_performance[strategy][-50:]
        
        # Update weighting system with performance
        self.weighting_system.update_strategy_performance(strategy, pnl_pct)
        
        logger.info(f"Updated performance for {strategy}: {pnl_pct:.2f}%")