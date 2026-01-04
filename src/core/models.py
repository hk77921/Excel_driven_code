"""
Data Models for Trading System
==============================
Defines all data structures used throughout the trading system.
These models ensure type safety and consistency across execution modes.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any, List
import json


class OrderSide(str, Enum):
    """Order side enumeration"""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Order status enumeration"""
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class PositionStatus(str, Enum):
    """Position status enumeration"""
    OPEN = "OPEN"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    CLOSED = "CLOSED"


class ExecutionMode(str, Enum):
    """Trading execution mode"""
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"




@dataclass
class TradeParameters:
    """
    Core trading parameters.
    These are the same across all execution modes.
    """
    atr_period: int = 14
    sl_atr_mult: float = 1.5
    target_atr_mult: float = 2.0
    partial_exit_ratio: float = 0.8  # 0.8R
    partial_exit_qty_pct: float = 0.5  # 50% qty
    trailing_sl_atr_mult: float = 1.5
    order_timeout_seconds: int = 300
    multi_level_targets: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CapitalParameters:
    """Capital management parameters"""
    total_capital: float
    risk_per_trade: float = 0.005  # 0.5%
    max_daily_loss_pct: float = 0.02  # 2%
    max_open_positions: int = 5
    max_per_sector: int = 2
    safety_buffer_pct: float = 0.15  # 15%
    max_position_pct: float = 0.1  # 10%
    

    @property
    def max_position_value(self) -> float:
        return round(self.total_capital * self.max_position_pct, 2)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Order:
    """
    Represents a single order (BUY or SELL).
    Immutable once created - only status changes.
    """
    order_id: str
    symbol: str
    side: OrderSide
    req_qty: int
    price: float
    created_at: datetime
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    filled_price: float = 0.0
    rejection_reason: Optional[str] = None
    updated_at: Optional[datetime] = None
    atr: float = 0.0
    sector: str = "UNKNOWN"
    
    def is_filled(self) -> bool:
        return self.filled_qty >= self.req_qty
    
    def is_pending(self) -> bool:
        return self.status in [OrderStatus.PENDING, OrderStatus.PARTIAL]
    
    def fill_ratio(self) -> float:
        return self.filled_qty / self.req_qty if self.req_qty > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['side'] = self.side.value
        data['status'] = self.status.value
        data['created_at'] = self.created_at.isoformat()
        if self.updated_at:
            data['updated_at'] = self.updated_at.isoformat()
        return data


@dataclass
class Position:
    """
    Represents an open trading position.
    Core position state shared across all execution modes.
    """
    symbol: str
    side: OrderSide
    entry_price: float
    quantity: int
    qty_remaining: int
    atr: float
    
    # Risk management
    stop_loss: float
    target: float
    
    # State tracking
    entry_time: datetime
    partial_exit_done: bool = False
    trailing_sl: Optional[float] = None
    unrealized_pnl: float = 0.0
    status: PositionStatus = PositionStatus.OPEN
    
    # Metadata
    sector: Optional[str] = None
    adx: Optional[float] = None
    volume_ratio: Optional[float] = None
    
    def is_open(self) -> bool:
        return self.qty_remaining > 0
    
    def qty_closed(self) -> int:
        return self.quantity - self.qty_remaining
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['side'] = self.side.value
        data['status'] = self.status.value
        data['entry_time'] = self.entry_time.isoformat()
        return data


@dataclass
class Trade:
    """
    A complete trade from entry to exit.
    Used for performance tracking and journaling.
    """
    trade_id: str
    symbol: str
    entry_price: float
    entry_qty: int
    entry_time: datetime
    side: OrderSide
    
    # Exit information
    exit_price: Optional[float] = None
    exit_qty: Optional[int] = None
    exit_time: Optional[datetime] = None
    
    # Performance
    realized_pnl: float = 0.0
    realized_pnl_pct: float = 0.0
    
    # Risk parameters
    stop_loss: float = 0.0
    target: float = 0.0
    
    # Metadata
    sector: Optional[str] = None
    
    def is_closed(self) -> bool:
        return self.exit_price is not None
    
    def calculate_pnl(self):
        """Calculate P&L if exit price is known"""
        if not self.is_closed():
            return 0.0, 0.0
        
        # exit_price and exit_qty are guaranteed to be non-None after is_closed() check
        exit_price = self.exit_price or 0.0
        exit_qty = self.exit_qty or 0
        
        if self.side == OrderSide.BUY:
            pnl = (exit_price - self.entry_price) * exit_qty
        else:  # SELL
            pnl = (self.entry_price - exit_price) * exit_qty
        
        pnl_pct = (pnl / (self.entry_price * self.entry_qty)) * 100 if self.entry_qty > 0 else 0.0
        return pnl, pnl_pct
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['side'] = self.side.value
        data['entry_time'] = self.entry_time.isoformat()
        if self.exit_time:
            data['exit_time'] = self.exit_time.isoformat()
        return data


@dataclass
class DailyPnL:
    """Daily performance tracking"""
    date: str
    starting_capital: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    trades_executed: int = 0
    trades_closed: int = 0
    
    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl
    
    @property
    def pnl_pct(self) -> float:
        if self.starting_capital == 0:
            return 0.0
        return (self.total_pnl / self.starting_capital) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CapitalBreakdown:
    """Capital allocation snapshot"""
    total_capital: float
    position_exposure: float
    pending_buy_capital: float
    safety_buffer: float
    available_capital: float
    
    def __str__(self) -> str:
        return (
            f"Capital Breakdown:\n"
            f"  Total:     ₹{self.total_capital:>12,.2f}\n"
            f"  - Positions: ₹{self.position_exposure:>12,.2f}\n"
            f"  - Pending:   ₹{self.pending_buy_capital:>12,.2f}\n"
            f"  - Buffer:    ₹{self.safety_buffer:>12,.2f}\n"
            f"  = Available: ₹{self.available_capital:>12,.2f}"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScreenerSignal:
    """
    Signal from stock screener.
    Contains all information needed to initiate a trade.
    """
    symbol: str
    score: float
    atr: float
    adx: float
    volume_ratio: float
    trend: str
    price: float
    sector: str
    timestamp: datetime
    reasons: str = ""  # Comma-separated list of signal reasons
    recent_highs: List[float] = field(default_factory=list)
    recent_lows: List[float] = field(default_factory=list)
    candle_index: int = 0
    rsi: Optional[float] = None
    price_vs_sma20: Optional[float] = None
    market_trend: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'symbol': self.symbol,
            'score': self.score,
            'atr': self.atr,
            'adx': self.adx,
            'volume_ratio': self.volume_ratio,
            'trend': self.trend,
            'price': self.price,
            'sector': self.sector,
            'timestamp': self.timestamp.isoformat(),
            'reasons': self.reasons,
            'recent_highs': self.recent_highs,
            'recent_lows': self.recent_lows,
            'candle_index': self.candle_index,
            'rsi': self.rsi,
            'price_vs_sma20': self.price_vs_sma20,
            'market_trend': self.market_trend
        }


@dataclass
class FairValueGap:
    symbol: str
    direction: str  # "BULLISH" or "BEARISH"
    high: float
    low: float
    size: float
    created_at_index: int

@dataclass
class SystemState:
    market_regime: Optional[str]
    regime_confidence: Optional[float]
    trading_enabled: bool
    emergency_stop_active: bool
    open_positions: int
    max_positions: int
    daily_pnl: float
    capital_available: float
    last_updated: datetime
