"""
Core Trading Module
===================
Contains all core trading logic that is independent of execution mode.

Modules:
- models: Data structures (Order, Position, Trade, etc)
- state_manager: Persistent state management
- capital_manager: Capital allocation and risk
- position_manager: Position lifecycle
- engine: Main trading logic
"""

from .models import (
    Order, Position, Trade, DailyPnL, ScreenerSignal,
    TradeParameters, CapitalParameters, CapitalBreakdown,
    OrderSide, OrderStatus, PositionStatus, ExecutionMode
)
from .state_manager import StateManager
from .capital_manager import CapitalManager
from .position_manager import PositionManager
from .engine import TradingEngine

__all__ = [
    'Order', 'Position', 'Trade', 'DailyPnL', 'ScreenerSignal',
    'TradeParameters', 'CapitalParameters', 'CapitalBreakdown',
    'OrderSide', 'OrderStatus', 'PositionStatus', 'ExecutionMode',
    'StateManager', 'CapitalManager', 'PositionManager', 'TradingEngine'
]
