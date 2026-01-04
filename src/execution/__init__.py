"""
Execution Module
===============
Execution adapters for different trading modes.

All modes use the same TradingEngine core logic.
Each mode handles broker-specific details.

Modes:
- paper.py: Simulated trading (for testing)
- live.py: Real trading (CAUTION: real money)
- backtest.py: Historical backtesting

Factory Pattern:
- create_execution_mode() factory function automatically switches
  between PAPER and LIVE based on config/environment
- No code changes needed - just update config.yaml execution.mode
"""

import logging
from typing import Optional, Dict, Any

from src.core import CapitalParameters, TradeParameters
from .adapter import ExecutionAdapter
from .paper import PaperTradingMode
from .live import LiveTradingMode
from .backtest import BacktestMode


logger = logging.getLogger(__name__)


def create_execution_mode(
    mode: str,
    capital_params: CapitalParameters,
    trade_params: TradeParameters,
    state_dir: str = "state",
    **kwargs
) -> ExecutionAdapter:
    """
    Factory function to create execution mode.
    
    This is the unified interface that switches between PAPER and LIVE
    without changing code - just update config/trading_config.yaml.
    
    Args:
        mode: "PAPER", "LIVE", or "BACKTEST"
        capital_params: Capital configuration
        trade_params: Trading configuration
        state_dir: Base state directory
        **kwargs: Mode-specific arguments
    
    Returns:
        ExecutionAdapter instance (Paper, Live, or Backtest)
    
    Example:
        # In your main code:
        config = load_config()  # Load from trading_config.yaml
        mode = config['execution']['mode']  # "PAPER" or "LIVE"
        
        executor = create_execution_mode(
            mode=mode,
            capital_params=CapitalParameters(...),
            trade_params=TradeParameters(...)
        )
        
        # No other code changes needed!
        # Just update trading_config.yaml to switch between PAPER/LIVE
    """
    mode = mode.upper()
    
    if mode == "PAPER":
        logger.info("📄 Creating PAPER trading mode (simulated)")
        return PaperTradingMode(
            capital_params=capital_params,
            trade_params=trade_params,
            state_dir=f"{state_dir}/paper"
        )
    
    elif mode == "LIVE":
        logger.warning("⚠️  Creating LIVE trading mode (REAL MONEY!)")
        logger.warning("Make sure KITE_API_KEY and KITE_ACCESS_TOKEN are set in .env")
        return LiveTradingMode(
            capital_params=capital_params,
            trade_params=trade_params,
            state_dir=f"{state_dir}/live"
        )
    
    elif mode == "BACKTEST":
        logger.info("📊 Creating BACKTEST mode (historical data)")
        return BacktestMode(
            capital_params=capital_params,
            trade_params=trade_params,
            state_dir=f"{state_dir}/backtest",
            **kwargs
        )
    
    else:
        raise ValueError(
            f"Invalid execution mode: {mode}. "
            f"Use 'PAPER', 'LIVE', or 'BACKTEST'"
        )


__all__ = [
    'ExecutionAdapter',
    'PaperTradingMode',
    'LiveTradingMode',
    'BacktestMode',
    'create_execution_mode'
]
