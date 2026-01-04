"""
Adaptive Strategies Package
==========================
Package for all adaptive trading strategies that auto-adjust parameters
based on NIFTY/BANKNIFTY market conditions.

Strategies included:
1. Gap Trading Strategy - Handles market gaps and opening behavior
2. Momentum Adaptive Strategy - Scales with market momentum
3. Volatility Regime Strategy - Adapts to volatility environments
4. Correlation Sync Strategy - Optimizes based on index correlation

Usage:
    from src.strategies import AdaptiveStrategyManager
    
    # Initialize with default configuration
    manager = AdaptiveStrategyManager()
    
    # Evaluate a trade signal
    decision = manager.evaluate_trade_entry(signal)
    
    if decision.should_enter:
        # Use the adjusted parameters for the trade
        params = decision.final_parameters
        print(f"Enter trade using {decision.primary_strategy} strategy")

Author: GitHub Copilot
"""

from .adaptive_manager import AdaptiveStrategyManager, StrategyConfiguration, StrategyMode
from .market_detector import EnhancedMarketDetector, MarketState, MarketDirection, GapType, VolatilityRegime
from .gap_trading import GapTradingStrategy
from .momentum_adaptive import MomentumAdaptiveStrategy
from .volatility_regime import VolatilityRegimeStrategy
from .correlation_sync import CorrelationSyncStrategy

__all__ = [
    'AdaptiveStrategyManager',
    'StrategyConfiguration', 
    'StrategyMode',
    'EnhancedMarketDetector',
    'MarketState',
    'MarketDirection',
    'GapType',
    'VolatilityRegime',
    'GapTradingStrategy',
    'MomentumAdaptiveStrategy',
    'VolatilityRegimeStrategy',
    'CorrelationSyncStrategy'
]

__version__ = "1.0.0"
__author__ = "GitHub Copilot"