"""
Strategy 4: Correlation Sync Strategy (Reactive)
===============================================
Adaptive strategy with reactive confidence management that optimizes entries 
and exits based on real-time correlation between individual stocks and NIFTY/BANKNIFTY.

Key Features:
- Real-time correlation analysis between stock and indices
- Reactive confidence decay to prevent stale convictions
- Correlation-based entry timing optimization
- Dynamic position sizing based on correlation strength
- Divergence detection and exploitation
- Beta-adjusted risk management
- Sector correlation analysis

Correlation Regimes:
- High Correlation (>0.7): Index-following strategy, momentum trades
- Medium Correlation (0.3-0.7): Selective entry, standard parameters
- Low Correlation (<0.3): Stock-specific strategy, divergence plays
- Negative Correlation: Contrarian strategy, hedge positions

Author: GitHub Copilot
"""

import logging
import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from scipy.stats import pearsonr
import warnings

from src.core.models import TradeParameters, ScreenerSignal
from .market_detector import EnhancedMarketDetector, MarketState
from src.core.confidence_manager import ReactiveConfidenceManager


warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)


@dataclass
class CorrelationParameters:
    """Parameters for correlation sync strategy"""
    
    # Correlation calculation periods
    short_corr_period: int = 20    # 20-period correlation
    medium_corr_period: int = 50   # 50-period correlation
    long_corr_period: int = 100    # 100-period correlation
    
    # Correlation thresholds
    high_correlation_threshold: float = 0.7
    medium_correlation_threshold: float = 0.3
    negative_correlation_threshold: float = -0.3
    
    # Position sizing by correlation
    high_corr_size_mult: float = 1.2      # Larger positions when highly correlated
    medium_corr_size_mult: float = 1.0    # Normal positions
    low_corr_size_mult: float = 0.8       # Smaller positions when uncorrelated
    negative_corr_size_mult: float = 0.6  # Smallest positions for negative correlation
    
    # Entry timing by correlation
    high_corr_index_alignment: bool = True    # Require index alignment for high correlation
    low_corr_divergence_play: bool = True     # Play divergences in low correlation
    
    # Beta adjustments
    high_beta_threshold: float = 1.5      # High beta stocks
    low_beta_threshold: float = 0.7       # Low beta stocks
    
    high_beta_sl_mult: float = 1.3        # Wider stops for high beta
    low_beta_sl_mult: float = 0.8         # Tighter stops for low beta
    
    high_beta_target_mult: float = 1.4    # Higher targets for high beta
    low_beta_target_mult: float = 0.8     # Lower targets for low beta
    
    # Divergence detection
    divergence_lookback: int = 20         # Periods to look back
    divergence_threshold: float = 0.15    # 15% threshold for significant divergence
    
    # Correlation stability requirements
    correlation_stability_threshold: float = 0.2  # Max acceptable correlation change
    min_correlation_confidence: float = 0.6       # Minimum confidence in correlation


@dataclass
class CorrelationAnalysis:
    """Comprehensive correlation analysis"""
    symbol: str
    nifty_correlation_short: float
    nifty_correlation_medium: float
    nifty_correlation_long: float
    banknifty_correlation_short: float
    banknifty_correlation_medium: float
    banknifty_correlation_long: float
    primary_index_correlation: float      # Higher of NIFTY/BANKNIFTY
    beta_nifty: float
    beta_banknifty: float
    correlation_regime: str               # HIGH, MEDIUM, LOW, NEGATIVE
    correlation_trend: str                # INCREASING, DECREASING, STABLE
    correlation_stability: float          # How stable the correlation is
    divergence_detected: bool
    divergence_direction: str             # BULLISH_DIVERGENCE, BEARISH_DIVERGENCE, NONE
    relative_strength: float              # vs primary index
    sector_correlation: float
    confidence: float
    timestamp: datetime


class CorrelationSyncStrategy:
    """
    Correlation-based adaptive trading strategy.
    
    This strategy:
    1. Analyzes real-time correlation between stocks and indices
    2. Adjusts entry criteria based on correlation strength
    3. Optimizes position sizing using beta and correlation
    4. Detects and exploits correlation divergences
    5. Implements correlation-aware risk management
    """
    
    def __init__(self, market_detector: EnhancedMarketDetector):
        """
        Initialize correlation sync strategy with reactive confidence management.
        
        Args:
            market_detector: Enhanced market detector instance
        """
        self.name = "CORRELATION_SYNC"
        self.market_detector = market_detector
        self.params = CorrelationParameters()
        
        # Reactive confidence management
        self.confidence_manager = ReactiveConfidenceManager()
        
        # Correlation analysis cache
        self.correlation_cache: Dict[str, CorrelationAnalysis] = {}
        self.stock_data_cache: Dict[str, pd.DataFrame] = {}
        self.last_cache_update: Dict[str, datetime] = {}
        
        # Index data for correlation calculation
        self.nifty_data: Optional[pd.DataFrame] = None
        self.banknifty_data: Optional[pd.DataFrame] = None
        self.last_index_update: Optional[datetime] = None
        
        logger.info("Correlation sync strategy initialized with reactive confidence management")
    
    def update_index_data(self) -> None:
        """Update index data for correlation calculations"""
        try:
            current_time = datetime.now()
            
            # Update every 15 minutes
            if (self.last_index_update is None or 
                (current_time - self.last_index_update).seconds >= 900):
                
                self.nifty_data = self.market_detector._fetch_intraday_data(
                    self.market_detector.nifty_symbol, period="5d", interval="5m"
                )
                
                self.banknifty_data = self.market_detector._fetch_intraday_data(
                    self.market_detector.banknifty_symbol, period="5d", interval="5m"
                )
                
                self.last_index_update = current_time
                logger.debug("Index data updated for correlation analysis")
        
        except Exception as e:
            logger.error(f"Failed to update index data: {e}")
    
    def should_enter_trade(self, signal: ScreenerSignal) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Determine if should enter trade based on correlation analysis with reactive confidence.
        
        Args:
            signal: Screener signal
            
        Returns:
            (should_enter, reason, adjusted_parameters)
        """
        # Update index data
        self.update_index_data()
        
        if self.nifty_data is None or self.banknifty_data is None:
            return False, "Index data unavailable for correlation analysis", {}
        
        # Get correlation analysis for the symbol
        correlation_analysis = self._get_correlation_analysis(signal.symbol)
        
        if correlation_analysis is None:
            return False, "Correlation analysis failed", {}
        
        # Update confidence manager with current market conditions
        current_price = getattr(signal, 'current_price', 0)
        if current_price > 0:
            # Calculate current volatility from recent price changes
            stock_data = self._fetch_stock_data(signal.symbol)
            current_volatility = 0.02  # Default 2%
            if stock_data is not None and len(stock_data) >= 5:
                returns = stock_data['Close'].pct_change().tail(5)
                current_volatility = returns.std() if not returns.empty else 0.02
            
            self.confidence_manager.update_market_conditions(
                symbol=signal.symbol,
                current_price=current_price,
                current_volatility=current_volatility,
                current_correlation=correlation_analysis.primary_index_correlation
            )
        
        # Get current confidence with decay applied
        current_confidence, confidence_details = self.confidence_manager.get_current_confidence(
            symbol=signal.symbol,
            strategy=self.name
        )
        
        # Update correlation analysis confidence with decayed value
        correlation_analysis.confidence = max(correlation_analysis.confidence, current_confidence)
        
        # Evaluate correlation-based entry

        
        should_enter, reason = self._evaluate_correlation_entry(signal, correlation_analysis)
        
        if not should_enter:
            return False, reason, {}
        
        # Add new confidence event for this decision
        confidence_context = {
            'correlation_regime': correlation_analysis.correlation_regime,
            'primary_correlation': correlation_analysis.primary_index_correlation,
            'signal_score': signal.score,
            'market_alignment': reason
        }
        
        self.confidence_manager.add_confidence_event(
            symbol=signal.symbol,
            initial_confidence=correlation_analysis.confidence,
            source_strategy=self.name,
            context=confidence_context,
            decay_rate=0.025  # Correlation-specific decay rate
        )
        
        # Calculate adjusted parameters
        adjusted_params = self._calculate_correlation_parameters(signal, correlation_analysis)
        
        # Add confidence information to parameters
        adjusted_params['confidence_details'] = confidence_details
        adjusted_params['reactive_confidence'] = current_confidence
        
        logger.info(
            f"Correlation entry approved for {signal.symbol}: {reason} | "
            f"Regime: {correlation_analysis.correlation_regime} | "
            f"Confidence: {correlation_analysis.confidence:.2f} (reactive: {current_confidence:.2f})"
        )
        
        return True, reason, adjusted_params
    
    def _get_correlation_analysis(self, symbol: str) -> Optional[CorrelationAnalysis]:
        """Get or calculate correlation analysis for symbol"""
        try:
            current_time = datetime.now()
            
            # Check cache (update every 10 minutes)
            if (symbol in self.last_cache_update and 
                (current_time - self.last_cache_update[symbol]).seconds < 600 and
                symbol in self.correlation_cache):
                return self.correlation_cache[symbol]
            
            # Fetch stock data
            stock_data = self._fetch_stock_data(symbol)
            if stock_data is None or stock_data.empty:
                return None
            
            # Perform correlation analysis
            analysis = self._perform_correlation_analysis(symbol, stock_data)
            
            if analysis:
                self.correlation_cache[symbol] = analysis
                self.last_cache_update[symbol] = current_time
            
            return analysis
            
        except Exception as e:
            logger.error(f"Failed to get correlation analysis for {symbol}: {e}")
            return None
    
    def _fetch_stock_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch stock data with caching"""
        try:
            current_time = datetime.now()
            
            # Check cache (update every 10 minutes)
            if (symbol in self.last_cache_update and 
                (current_time - self.last_cache_update[symbol]).seconds < 600 and
                symbol in self.stock_data_cache):
                return self.stock_data_cache[symbol]
            
            # Fetch new data
            import yfinance as yf
            stock_data = yf.download(f"{symbol}.NS", period="5d", interval="5m", progress=False)
            
            if stock_data is not None and not stock_data.empty:
                if isinstance(stock_data.columns, pd.MultiIndex):
                    stock_data.columns = stock_data.columns.droplevel(1)
                
                self.stock_data_cache[symbol] = stock_data
                return stock_data
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to fetch data for {symbol}: {e}")
            return None
    
    def _perform_correlation_analysis(self, symbol: str, stock_data: pd.DataFrame) -> Optional[CorrelationAnalysis]:
        """Perform comprehensive correlation analysis"""
        try:
            # Update index data
            self.update_index_data()
            
            if self.nifty_data is None or self.banknifty_data is None:
                return None
            # Align data timeframes
            stock_returns = stock_data['Close'].pct_change().dropna()
            nifty_returns = self.nifty_data['Close'].pct_change().dropna()
            banknifty_returns = self.banknifty_data['Close'].pct_change().dropna()
            
            # Align indices (find common timestamps)
            common_index = stock_returns.index.intersection(nifty_returns.index)
            common_index = common_index.intersection(banknifty_returns.index)
            
            if len(common_index) < self.params.long_corr_period:
                return None
            
            # Align data to common timestamps
            stock_aligned = stock_returns.loc[common_index]
            nifty_aligned = nifty_returns.loc[common_index]
            banknifty_aligned = banknifty_returns.loc[common_index]
            
            # Calculate correlations for different periods
            correlations = {}
            
            # NIFTY correlations
            for period, name in [(self.params.short_corr_period, 'short'),
                               (self.params.medium_corr_period, 'medium'),
                               (self.params.long_corr_period, 'long')]:
                
                if len(stock_aligned) >= period:
                    stock_subset = stock_aligned.tail(period)
                    nifty_subset = nifty_aligned.tail(period)
                    banknifty_subset = banknifty_aligned.tail(period)
                    
                    # Calculate correlations
                    nifty_corr, _ = pearsonr(stock_subset, nifty_subset)
                    banknifty_corr, _ = pearsonr(stock_subset, banknifty_subset)
                    
                    correlations[f'nifty_{name}'] = nifty_corr if not np.isnan(nifty_corr) else 0.0
                    correlations[f'banknifty_{name}'] = banknifty_corr if not np.isnan(banknifty_corr) else 0.0
                else:
                    correlations[f'nifty_{name}'] = 0.0
                    correlations[f'banknifty_{name}'] = 0.0
            
            # Calculate beta (using medium-term data)
            if len(stock_aligned) >= self.params.medium_corr_period:
                period_data = self.params.medium_corr_period
                
                # Beta calculation: Cov(Stock, Index) / Var(Index)
                stock_subset = stock_aligned.tail(period_data)
                nifty_subset = nifty_aligned.tail(period_data)
                banknifty_subset = banknifty_aligned.tail(period_data)
                
                nifty_beta = np.cov(stock_subset, nifty_subset)[0,1] / np.var(nifty_subset) if np.var(nifty_subset) > 0 else 1.0
                banknifty_beta = np.cov(stock_subset, banknifty_subset)[0,1] / np.var(banknifty_subset) if np.var(banknifty_subset) > 0 else 1.0
                
                # Handle NaN values
                nifty_beta = nifty_beta if not np.isnan(nifty_beta) else 1.0
                banknifty_beta = banknifty_beta if not np.isnan(banknifty_beta) else 1.0
            else:
                nifty_beta = 1.0
                banknifty_beta = 1.0
            
            # Determine primary index (higher correlation)
            nifty_avg_corr = (correlations['nifty_short'] + correlations['nifty_medium'] + correlations['nifty_long']) / 3
            banknifty_avg_corr = (correlations['banknifty_short'] + correlations['banknifty_medium'] + correlations['banknifty_long']) / 3
            
            if abs(nifty_avg_corr) >= abs(banknifty_avg_corr):
                primary_correlation = nifty_avg_corr
                primary_beta = nifty_beta
            else:
                primary_correlation = banknifty_avg_corr
                primary_beta = banknifty_beta
            
            # Classify correlation regime
            abs_primary_corr = abs(primary_correlation)
            
            if abs_primary_corr >= self.params.high_correlation_threshold:
                correlation_regime = "HIGH"
            elif abs_primary_corr >= self.params.medium_correlation_threshold:
                correlation_regime = "MEDIUM"
            elif primary_correlation <= self.params.negative_correlation_threshold:
                correlation_regime = "NEGATIVE"
            else:
                correlation_regime = "LOW"
            
            # Calculate correlation trend
            if len(stock_aligned) >= self.params.long_corr_period + 20:
                recent_corr = correlations['nifty_short']
                older_period = min(self.params.medium_corr_period, len(stock_aligned) - 20)
                
                older_stock = stock_aligned.iloc[-(older_period+20):-20]
                older_nifty = nifty_aligned.iloc[-(older_period+20):-20]
                
                if len(older_stock) >= 10:
                    older_corr, _ = pearsonr(older_stock, older_nifty)
                    older_corr = older_corr if not np.isnan(older_corr) else recent_corr
                    
                    corr_change = recent_corr - older_corr
                    if corr_change > 0.1:
                        correlation_trend = "INCREASING"
                    elif corr_change < -0.1:
                        correlation_trend = "DECREASING"
                    else:
                        correlation_trend = "STABLE"
                else:
                    correlation_trend = "STABLE"
            else:
                correlation_trend = "STABLE"
            
            # Calculate correlation stability
            corr_values = [correlations['nifty_short'], correlations['nifty_medium'], correlations['nifty_long']]
            correlation_stability = 1.0 - (max(corr_values) - min(corr_values)) if max(corr_values) != min(corr_values) else 1.0
            correlation_stability = max(0.0, correlation_stability)
            
            # Detect divergence
            divergence_detected, divergence_direction = self._detect_correlation_divergence(
                stock_aligned, nifty_aligned, primary_correlation
            )
            
            # Calculate relative strength
            if len(stock_aligned) >= 20:
                stock_perf = (stock_aligned.iloc[-1] / stock_aligned.iloc[-20] - 1) * 100
                nifty_perf = (nifty_aligned.iloc[-1] / nifty_aligned.iloc[-20] - 1) * 100
                relative_strength = stock_perf - nifty_perf
            else:
                relative_strength = 0.0
            
            # Calculate confidence
            confidence = min(1.0, correlation_stability * abs_primary_corr + 0.3)
            
            analysis = CorrelationAnalysis(
                symbol=symbol,
                nifty_correlation_short=correlations['nifty_short'],
                nifty_correlation_medium=correlations['nifty_medium'],
                nifty_correlation_long=correlations['nifty_long'],
                banknifty_correlation_short=correlations['banknifty_short'],
                banknifty_correlation_medium=correlations['banknifty_medium'],
                banknifty_correlation_long=correlations['banknifty_long'],
                primary_index_correlation=primary_correlation,
                beta_nifty=nifty_beta,
                beta_banknifty=banknifty_beta,
                correlation_regime=correlation_regime,
                correlation_trend=correlation_trend,
                correlation_stability=correlation_stability,
                divergence_detected=divergence_detected,
                divergence_direction=divergence_direction,
                relative_strength=relative_strength,
                sector_correlation=0.5,  # Placeholder for sector correlation
                confidence=confidence,
                timestamp=datetime.now()
            )
            
            logger.debug(f"Correlation Analysis for {symbol}: {correlation_regime} regime ({primary_correlation:.3f})")
            return analysis
            
        except Exception as e:
            logger.error(f"Correlation analysis failed for {symbol}: {e}")
            return None
    
    def _detect_correlation_divergence(self, stock_returns: pd.Series, index_returns: pd.Series, 
                                     base_correlation: float) -> Tuple[bool, str]:
        """Detect correlation divergences"""
        try:
            if len(stock_returns) < self.params.divergence_lookback:
                return False, "NONE"
            
            # Get recent data
            recent_stock = stock_returns.tail(self.params.divergence_lookback)
            recent_index = index_returns.tail(self.params.divergence_lookback)
            
            # Calculate price movements
            stock_movement = (recent_stock.sum()) * 100  # Cumulative return %
            index_movement = (recent_index.sum()) * 100
            
            # Expected stock movement based on correlation and beta
            expected_stock_movement = index_movement * base_correlation
            
            # Check for significant divergence
            divergence = stock_movement - expected_stock_movement
            
            if abs(divergence) > self.params.divergence_threshold * 100:
                if divergence > 0:
                    return True, "BULLISH_DIVERGENCE"  # Stock outperforming expectation
                else:
                    return True, "BEARISH_DIVERGENCE"  # Stock underperforming expectation
            
            return False, "NONE"
            
        except Exception:
            return False, "NONE"
    
    def _evaluate_correlation_entry(self, signal: ScreenerSignal, corr_analysis: CorrelationAnalysis) -> Tuple[bool, str]:
        """Evaluate if should enter based on correlation analysis"""
        
        # 1. Check correlation confidence
        if corr_analysis.confidence < self.params.min_correlation_confidence:
            return False, f"Correlation analysis confidence {corr_analysis.confidence:.2f} too low"
        
        # 2. Correlation regime-specific logic
        if corr_analysis.correlation_regime == "HIGH":
            # High correlation - require index alignment
            market_state = self.market_detector.get_current_market_state()
            
            if signal.trend == "BULLISH" and not market_state.is_bullish():
                return False, "Bullish signal but market not bullish (high correlation stock)"
            
            if signal.trend == "BEARISH" and not market_state.is_bearish():
                return False, "Bearish signal but market not bearish (high correlation stock)"
            
            # Require higher score for high correlation stocks
            min_score = 45
            if signal.score < min_score:
                return False, f"High correlation stock needs score ≥{min_score}"
        
        elif corr_analysis.correlation_regime == "LOW":
            # Low correlation - look for divergences and stock-specific signals
            if not corr_analysis.divergence_detected:
                # For low correlation without divergence, need very strong signal
                if signal.score < 55:
                    return False, "Low correlation stock without divergence needs score ≥55"
            else:
                # Divergence play - check alignment
                if (corr_analysis.divergence_direction == "BULLISH_DIVERGENCE" and 
                    signal.trend != "BULLISH"):
                    return False, "Bullish divergence requires bullish signal"
                
                if (corr_analysis.divergence_direction == "BEARISH_DIVERGENCE" and 
                    signal.trend != "BEARISH"):
                    return False, "Bearish divergence requires bearish signal"
        
        elif corr_analysis.correlation_regime == "NEGATIVE":
            # Negative correlation - contrarian strategy
            market_state = self.market_detector.get_current_market_state()
            
            # In negative correlation, look for counter-trend opportunities
            if signal.trend == "BULLISH" and market_state.is_bullish():
                return False, "Negative correlation stock: avoid bullish signals in bullish market"
            
            # Need higher confidence for negative correlation trades
            if signal.score < 60:
                return False, "Negative correlation stock needs score ≥60"
        
        # 3. Check correlation stability
        if corr_analysis.correlation_stability < 0.5:
            return False, f"Correlation unstable ({corr_analysis.correlation_stability:.2f})"
        
        # 4. Beta considerations
        primary_beta = corr_analysis.beta_nifty if abs(corr_analysis.nifty_correlation_medium) >= abs(corr_analysis.banknifty_correlation_medium) else corr_analysis.beta_banknifty
        
        if abs(primary_beta) > 2.0:
            # Very high beta - be cautious
            if signal.score < 50:
                return False, f"High beta stock (β={primary_beta:.2f}) needs score ≥50"
        
        # 5. Relative strength check
        if corr_analysis.correlation_regime == "HIGH":
            # For high correlation stocks, check relative strength alignment
            if (signal.trend == "BULLISH" and corr_analysis.relative_strength < -2.0):
                return False, "Bullish signal but stock showing relative weakness"
            
            if (signal.trend == "BEARISH" and corr_analysis.relative_strength > 2.0):
                return False, "Bearish signal but stock showing relative strength"
        
        reason = f"Correlation entry: {corr_analysis.correlation_regime} correlation ({corr_analysis.primary_index_correlation:.3f})"
        
        if corr_analysis.divergence_detected:
            reason += f", {corr_analysis.divergence_direction.lower()}"
        
        return True, reason
    
    def _calculate_correlation_parameters(self, signal: ScreenerSignal, corr_analysis: CorrelationAnalysis) -> Dict[str, Any]:
        """Calculate adjusted parameters based on correlation analysis"""
        
        # Base parameters by correlation regime
        if corr_analysis.correlation_regime == "HIGH":
            size_mult = self.params.high_corr_size_mult
            entry_reason = f"high_corr_{corr_analysis.primary_index_correlation:.2f}"
        
        elif corr_analysis.correlation_regime == "MEDIUM":
            size_mult = self.params.medium_corr_size_mult
            entry_reason = f"medium_corr_{corr_analysis.primary_index_correlation:.2f}"
        
        elif corr_analysis.correlation_regime == "LOW":
            size_mult = self.params.low_corr_size_mult
            entry_reason = f"low_corr_{corr_analysis.primary_index_correlation:.2f}"
        
        else:  # NEGATIVE
            size_mult = self.params.negative_corr_size_mult
            entry_reason = f"negative_corr_{corr_analysis.primary_index_correlation:.2f}"
        
        # Beta-based adjustments
        primary_beta = (corr_analysis.beta_nifty if abs(corr_analysis.nifty_correlation_medium) >= 
                       abs(corr_analysis.banknifty_correlation_medium) else corr_analysis.beta_banknifty)
        
        # Adjust stops and targets based on beta
        if abs(primary_beta) >= self.params.high_beta_threshold:
            atr_sl_mult = self.params.high_beta_sl_mult
            atr_target_mult = self.params.high_beta_target_mult
        elif abs(primary_beta) <= self.params.low_beta_threshold:
            atr_sl_mult = self.params.low_beta_sl_mult
            atr_target_mult = self.params.low_beta_target_mult
        else:
            atr_sl_mult = 1.5  # Default
            atr_target_mult = 2.0  # Default
        
        # Divergence adjustments
        if corr_analysis.divergence_detected:
            if corr_analysis.divergence_direction == "BULLISH_DIVERGENCE":
                size_mult *= 1.1       # Slightly larger position
                atr_target_mult *= 1.2 # Higher targets
                entry_reason += "_bull_div"
            else:  # BEARISH_DIVERGENCE
                size_mult *= 0.9       # Slightly smaller position
                atr_target_mult *= 0.9 # Lower targets
                entry_reason += "_bear_div"
        
        # Correlation stability adjustment
        stability_adjustment = 0.8 + (corr_analysis.correlation_stability * 0.4)  # 0.8 to 1.2 range
        size_mult *= stability_adjustment
        
        # Relative strength adjustment
        if abs(corr_analysis.relative_strength) > 5.0:  # Strong relative performance
            if ((corr_analysis.relative_strength > 0 and signal.trend == "BULLISH") or
                (corr_analysis.relative_strength < 0 and signal.trend == "BEARISH")):
                atr_target_mult *= 1.15  # Higher targets for aligned relative strength
        
        # Correlation trend adjustment
        if corr_analysis.correlation_trend == "INCREASING" and corr_analysis.correlation_regime == "HIGH":
            size_mult *= 1.05  # Slightly larger positions for increasing correlation
        elif corr_analysis.correlation_trend == "DECREASING" and corr_analysis.correlation_regime == "HIGH":
            size_mult *= 0.95  # Slightly smaller positions for decreasing correlation
        
        adjusted_params = {
            'atr_sl_mult': atr_sl_mult,
            'atr_target_mult': atr_target_mult,
            'partial_exit_ratio': 0.8,  # Standard partial exit
            'position_size_multiplier': size_mult,
            'correlation_regime': corr_analysis.correlation_regime,
            'primary_correlation': corr_analysis.primary_index_correlation,
            'beta': primary_beta,
            'relative_strength': corr_analysis.relative_strength,
            'correlation_confidence': corr_analysis.confidence,
            'divergence_detected': corr_analysis.divergence_detected,
            'entry_reason': entry_reason
        }
        
        # Special correlation-based features
        if corr_analysis.correlation_regime == "HIGH" and abs(corr_analysis.primary_index_correlation) > 0.8:
            adjusted_params['index_sync_exit'] = True  # Exit when index reverses
        
        if corr_analysis.divergence_detected:
            adjusted_params['divergence_target_mult'] = 1.5  # Special divergence target
            adjusted_params['quick_profit_target'] = True
        
        if corr_analysis.correlation_regime == "NEGATIVE":
            adjusted_params['contrarian_mode'] = True
            adjusted_params['hedge_position'] = True
        
        return adjusted_params
    
    def get_correlation_summary(self, symbol: str = None) -> Dict[str, Any]:
        """Get correlation analysis summary"""
        if symbol and symbol in self.correlation_cache:
            corr = self.correlation_cache[symbol]
            
            return {
                'strategy_name': self.name,
                'symbol': symbol,
                'correlation_regime': corr.correlation_regime,
                'primary_correlation': f"{corr.primary_index_correlation:.3f}",
                'beta': f"{corr.beta_nifty:.2f}" if abs(corr.nifty_correlation_medium) >= abs(corr.banknifty_correlation_medium) else f"{corr.beta_banknifty:.2f}",
                'correlation_trend': corr.correlation_trend,
                'correlation_stability': f"{corr.correlation_stability:.2f}",
                'divergence_detected': corr.divergence_detected,
                'divergence_direction': corr.divergence_direction,
                'relative_strength': f"{corr.relative_strength:.2f}%",
                'confidence': f"{corr.confidence:.2f}",
                'correlations': {
                    'nifty_short': f"{corr.nifty_correlation_short:.3f}",
                    'nifty_medium': f"{corr.nifty_correlation_medium:.3f}",
                    'nifty_long': f"{corr.nifty_correlation_long:.3f}",
                    'banknifty_short': f"{corr.banknifty_correlation_short:.3f}",
                    'banknifty_medium': f"{corr.banknifty_correlation_medium:.3f}",
                    'banknifty_long': f"{corr.banknifty_correlation_long:.3f}"
                },
                'last_update': corr.timestamp.strftime('%H:%M:%S')
            }
        
        return {
            'strategy_name': self.name,
            'cached_symbols': len(self.correlation_cache),
            'last_index_update': self.last_index_update.strftime('%H:%M:%S') if self.last_index_update else 'Never'
        }
    
    def reset_daily_state(self) -> None:
        """Reset daily state variables"""
        self.correlation_cache.clear()
        self.stock_data_cache.clear()
        self.last_cache_update.clear()
        self.nifty_data = None
        self.banknifty_data = None
        self.last_index_update = None
        
        logger.info("Correlation sync strategy daily state reset")