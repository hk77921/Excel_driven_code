"""
UNIFIED TRADING STRATEGY CORE
==============================
Single source of truth for strategy logic used across:
- Backtesting
- Paper Trading  
- Live Trading

This ensures NO logic gaps between testing and production.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
import logging
from abc import ABC, abstractmethod
import math

# ==============================
# CONFIGURATION (Single Source)
# ==============================

@dataclass
class StrategyConfig:
    """Strategy parameters - same for backtest/paper/live"""
    # Capital management
    initial_capital: float = 100000.0
    risk_per_trade: float = 0.005  # 0.5%
    max_position_pct: float = 0.30  # 30% max per position
    
    # Position limits
    max_open_positions: int = 5
    max_per_sector: int = 2
    
    # Strategy parameters (from your trade_manager.py)
    atr_period: int = 14
    sl_atr_mult: float = 1.5
    target_atr_mult: float = 2.0
    partial_exit_ratio: float = 0.8  # 0.8R
    partial_exit_qty_pct: float = 0.5  # 50%
    trailing_sl_atr_mult: float = 1.5
    
    # Risk management
    max_daily_loss_pct: float = 0.02  # 2%
    
    # Entry filters (from your screener)
    min_atr_pct: float = 2.0
    max_atr_pct: float = 5.0
    min_adx: float = 20.0
    min_vol_ratio: float = 1.0
    trend_required: str = "BULLISH"
    
    # Costs
    brokerage_pct: float = 0.0003
    slippage_pct: float = 0.001
    
    # Technical indicators
    ema_short: int = 20
    ema_long: int = 50
    vol_window: int = 20


# ==============================
# TRADE MODEL (Shared)
# ==============================

@dataclass
class Trade:
    """Trade model - identical to your execution_engine.py Trade class"""
    symbol: str
    side: str  # BUY/SELL
    entry: float
    sl: float
    qty: int
    qty_remaining: int
    atr: float
    
    # State tracking
    partial_done: bool = False
    trailing_active: bool = False
    entry_time: Optional[datetime] = None
    exit_pending: bool = False
    
    # P&L tracking
    realized_pnl: float = 0.0
    entry_fees: float = 0.0
    
    # Exit tracking
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    
    # Partial exit tracking
    partial_exit_time: Optional[datetime] = None
    partial_exit_price: Optional[float] = None
    partial_exit_qty: int = 0
    
    @property
    def is_open(self) -> bool:
        return self.exit_time is None
    
    @property
    def pnl_pct(self) -> float:
        if self.exit_price:
            return ((self.exit_price - self.entry) / self.entry) * 100
        return 0.0
    
    @property
    def r_multiple(self) -> float:
        """Risk multiple"""
        r_value = abs(self.entry - self.sl)
        if r_value == 0:
            return 0.0
        if self.exit_price:
            profit = self.exit_price - self.entry
            return profit / r_value
        return 0.0
    
    def to_dict(self) -> dict:
        """Convert to dict for state persistence"""
        d = asdict(self)
        # Convert datetime to string
        if self.entry_time:
            d['entry_time'] = self.entry_time.isoformat()
        if self.exit_time:
            d['exit_time'] = self.exit_time.isoformat()
        if self.partial_exit_time:
            d['partial_exit_time'] = self.partial_exit_time.isoformat()
        return d
    
    @staticmethod
    def from_dict(data: dict) -> 'Trade':
        """Load from dict"""
        # Handle datetime conversion
        if 'entry_time' in data and isinstance(data['entry_time'], str):
            data['entry_time'] = datetime.fromisoformat(data['entry_time'])
        if 'exit_time' in data and isinstance(data['exit_time'], str):
            data['exit_time'] = datetime.fromisoformat(data['exit_time'])
        if 'partial_exit_time' in data and isinstance(data['partial_exit_time'], str):
            data['partial_exit_time'] = datetime.fromisoformat(data['partial_exit_time'])
        
        return Trade(**data)


# ==============================
# CORE STRATEGY LOGIC (Unified)
# ==============================

class StrategyCore:
    """
    Core strategy logic - SAME code for backtest/paper/live
    Extracted from your trade_manager.py and execution_engine.py
    """
    
    def __init__(self, config: StrategyConfig):
        self.config = config
    
    # ===== ENTRY LOGIC =====
    
    def check_entry_filters(self, bar: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if entry conditions are met
        Maps to your screener logic in excel_driven_screener.py
        """
        # ATR filter
        atr_pct = (bar['atr'] / bar['close']) * 100
        if atr_pct < self.config.min_atr_pct or atr_pct > self.config.max_atr_pct:
            return False, f"ATR {atr_pct:.2f}% outside range"
        
        # ADX filter
        if bar['adx'] < self.config.min_adx:
            return False, f"ADX {bar['adx']:.1f} too low"
        
        # Volume filter
        if bar['vol_ratio'] < self.config.min_vol_ratio:
            return False, f"Volume ratio {bar['vol_ratio']:.2f} too low"
        
        # Trend filter
        if self.config.trend_required == "BULLISH":
            if bar['ema20'] <= bar['ema50']:
                return False, "Not in bullish trend"
        
        return True, "PASS"
    
    def calculate_position_size(self, price: float, atr: float, available_capital: float) -> int:
        """
        Calculate position size - identical to your execution_engine.py
        """
        risk_amount = self.config.initial_capital * self.config.risk_per_trade
        sl_points = atr * self.config.sl_atr_mult
        
        if sl_points == 0:
            return 1
        
        risk_based_qty = int(risk_amount / sl_points)
        
        # Max position constraint
        max_affordable = int((available_capital * self.config.max_position_pct) / price)
        
        qty = min(risk_based_qty, max_affordable)
        return max(1, qty)
    
    def calculate_stop_loss(self, entry_price: float, atr: float, side: str = "BUY") -> float:
        """Calculate initial stop loss"""
        if side == "BUY":
            return entry_price - (atr * self.config.sl_atr_mult)
        else:  # SELL/SHORT
            return entry_price + (atr * self.config.sl_atr_mult)
    
    # ===== EXIT LOGIC (From trade_manager.py) =====
    
    def check_partial_exit(self, trade: Trade, ltp: float) -> Tuple[Trade, int]:
        """
        Check if partial exit should be triggered at +0.8R
        EXACT COPY of your trade_manager.py check_partial_exit function
        """
        # Skip if already done
        if trade.partial_done:
            return trade, 0
        
        entry = trade.entry
        sl = trade.sl
        side = trade.side
        symbol = trade.symbol
        
        # Calculate R-value (risk per share)
        r_value = abs(entry - sl)
        if r_value == 0:
            logging.warning(f"{symbol}: R-value is zero, skipping partial exit")
            return trade, 0
        
        # Only handle BUY side for now
        if side == "BUY":
            # Target is entry + 0.8R
            target_price = entry + (self.config.partial_exit_ratio * r_value)
            
            if ltp >= target_price:
                # Exit 50% of remaining quantity
                exit_qty = max(1, int(trade.qty_remaining * self.config.partial_exit_qty_pct))
                
                # Must leave at least 1 share remaining
                if exit_qty >= trade.qty_remaining:
                    exit_qty = trade.qty_remaining - 1
                
                if exit_qty > 0:
                    trade.partial_done = True
                    logging.info(
                        f"{symbol}: Partial exit triggered | "
                        f"LTP={ltp:.2f}, Target={target_price:.2f}, "
                        f"Exit Qty={exit_qty}/{trade.qty_remaining}"
                    )
                    return trade, exit_qty
                else:
                    logging.debug(
                        f"{symbol}: Partial exit target reached but "
                        f"insufficient qty remaining"
                    )
        
        # TODO: Add SHORT side logic when needed
        return trade, 0
    
    def update_trailing_sl(self, trade: Trade, ltp: float) -> Tuple[Trade, bool]:
        """
        Update trailing stop loss after partial exit
        EXACT COPY of your trade_manager.py update_trailing_sl function
        """
        # Only trail after partial exit
        if not trade.partial_done:
            return trade, False
        
        atr = trade.atr
        side = trade.side
        symbol = trade.symbol
        
        if atr == 0:
            logging.warning(f"{symbol}: ATR is zero, cannot trail SL")
            return trade, False
        
        if side == "BUY":
            # Trail SL at LTP - 1.5*ATR
            new_sl = ltp - (self.config.trailing_sl_atr_mult * atr)
            
            # Only update if new SL is higher (more protective)
            if new_sl > trade.sl:
                old_sl = trade.sl
                trade.sl = new_sl
                trade.trailing_active = True
                logging.info(
                    f"{symbol}: Trailing SL updated | "
                    f"Old={old_sl:.2f}, New={new_sl:.2f}, LTP={ltp:.2f}"
                )
                return trade, True
        
        # TODO: Add SHORT side logic when needed
        return trade, False
    
    def check_stop_loss_hit(self, trade: Trade, ltp: float) -> bool:
        """
        Check if stop loss has been hit
        EXACT COPY of your trade_manager.py check_stop_loss_hit function
        """
        side = trade.side
        sl = trade.sl
        symbol = trade.symbol
        
        if side == "BUY":
            if ltp <= sl:
                logging.warning(
                    f"{symbol}: STOP LOSS HIT | "
                    f"LTP={ltp:.2f}, SL={sl:.2f}, "
                    f"Loss={(ltp-trade.entry)/trade.entry*100:.2f}%"
                )
                return True
        
        # TODO: Add SHORT side logic when needed
        return False
    
    def calculate_pnl(self, trade: Trade, exit_price: float, exit_qty: int) -> float:
        """
        Calculate P&L for a trade exit
        EXACT COPY of your trade_manager.py calculate_pnl function
        """
        entry = trade.entry
        side = trade.side
        
        if side == "BUY":
            pnl_per_share = exit_price - entry
        else:  # SHORT
            pnl_per_share = entry - exit_price
        
        total_pnl = pnl_per_share * exit_qty
        return total_pnl
    
    # ===== FEE CALCULATION (From execution_engine.py) =====
    
    def calculate_fees(self, value: float, side: str) -> float:
        """
        Calculate trading fees - Zerodha structure
        From your execution_engine.py calculate_broker_fees function
        """
        if value == 0:
            return 0.0
        
        # Brokerage
        brokerage = min(20.0, value * 0.0003)
        
        # STT (only on SELL)
        stt = (value * 0.00025) if side == "SELL" else 0.0
        
        # Exchange charges
        nse_charges = value * 0.0000325
        
        # SEBI charges
        sebi_charges = value * 0.000001
        
        # Stamp duty (only on BUY)
        stamp_duty = (value * 0.00003) if side == "BUY" else 0.0
        
        # GST
        taxable = brokerage + nse_charges
        gst = taxable * 0.18
        
        total = brokerage + stt + nse_charges + sebi_charges + stamp_duty + gst
        return round(total, 2)


# ==============================
# DATA PROVIDER INTERFACE
# ==============================

class DataProvider(ABC):
    """Abstract interface for data - allows swapping between backtest/live/paper"""
    
    @abstractmethod
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for symbol"""
        pass
    
    @abstractmethod
    def get_historical_bar(self, symbol: str, date: datetime) -> Optional[Dict[str, Any]]:
        """Get OHLCV + indicators for a specific bar"""
        pass
    
    @abstractmethod
    def place_order(self, symbol: str, qty: int, side: str, price: Optional[float] = None) -> Optional[str]:
        """Place order - returns order_id"""
        pass
    
    @abstractmethod
    def get_order_status(self, order_id: str) -> Tuple[str, int, Optional[float]]:
        """Get order status - returns (status, filled_qty, avg_price)"""
        pass


# ==============================
# BACKTEST DATA PROVIDER
# ==============================

class BacktestDataProvider(DataProvider):
    """Data provider for backtesting"""
    
    def __init__(self, historical_data: Dict[str, pd.DataFrame]):
        """
        Args:
            historical_data: Dict of {symbol: dataframe with OHLCV + indicators}
        """
        self.data = historical_data
        self.current_date: Optional[datetime] = None
        self.orders: Dict[str, Dict] = {}
        self.order_counter = 0
    
    def set_current_date(self, date: datetime):
        """Set current simulation date"""
        self.current_date = date
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get close price for current date"""
        if symbol not in self.data or self.current_date is None:
            return None
        
        df = self.data[symbol]
        rows = df[df['date'] == self.current_date]
        
        if rows.empty:
            return None
        
        return float(rows.iloc[0]['close'])
    
    def get_historical_bar(self, symbol: str, date: datetime) -> Optional[Dict[str, Any]]:
        """Get full bar data"""
        if symbol not in self.data:
            return None
        
        df = self.data[symbol]
        rows = df[df['date'] == date]
        
        if rows.empty:
            return None
        
        return rows.iloc[0].to_dict()
    
    def place_order(self, symbol: str, qty: int, side: str, price: Optional[float] = None) -> Optional[str]:
        """Simulate order placement"""
        self.order_counter += 1
        order_id = f"BT-{self.order_counter}"
        
        # In backtest, orders fill instantly at next bar's open
        self.orders[order_id] = {
            'symbol': symbol,
            'qty': qty,
            'side': side,
            'price': price,
            'status': 'PENDING',
            'placed_date': self.current_date
        }
        
        return order_id
    
    def get_order_status(self, order_id: str) -> Tuple[str, int, Optional[float]]:
        """Check order status"""
        if order_id not in self.orders:
            return ("UNKNOWN", 0, None)
        
        order = self.orders[order_id]
        
        # Simulate instant fill in backtest
        if order['status'] == 'PENDING':
            # Fill at current price (simplified)
            fill_price = self.get_current_price(order['symbol'])
            
            if fill_price:
                order['status'] = 'COMPLETE'
                order['fill_price'] = fill_price
                return ("COMPLETE", order['qty'], fill_price)
        
        return (order['status'], order.get('qty', 0), order.get('fill_price'))


# ==============================
# LIVE DATA PROVIDER
# ==============================

class LiveDataProvider(DataProvider):
    """Data provider for live/paper trading using yfinance or Kite"""
    
    def __init__(self, mode: str = "PAPER", kite=None):
        """
        Args:
            mode: "PAPER" or "LIVE"
            kite: KiteConnect instance for live trading
        """
        self.mode = mode
        self.kite = kite
        self.orders: Dict[str, Dict] = {}
        self.order_counter = 0
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get live price"""
        if self.mode == "PAPER":
            try:
                import yfinance as yf
                ticker = yf.Ticker(f"{symbol}.NS")
                data = ticker.history(period="1d", interval="1m")
                if not data.empty:
                    return float(data['Close'].iloc[-1])
            except Exception as e:
                logging.warning(f"Failed to fetch price for {symbol}: {e}")
                return None
        
        elif self.mode == "LIVE" and self.kite:
            try:
                quote = self.kite.quote(f"NSE:{symbol}")
                return float(quote[f"NSE:{symbol}"]["last_price"])
            except Exception as e:
                logging.warning(f"Failed to fetch price for {symbol}: {e}")
                return None
        
        return None
    
    def get_historical_bar(self, symbol: str, date: datetime) -> Optional[Dict[str, Any]]:
        """Get bar with indicators - would need to calculate live"""
        # This would fetch recent data and calculate indicators
        # Simplified for now
        price = self.get_current_price(symbol)
        if price:
            return {'close': price}
        return None
    
    def place_order(self, symbol: str, qty: int, side: str, price: Optional[float] = None) -> Optional[str]:
        """Place order"""
        if self.mode == "PAPER":
            # Simulate order
            self.order_counter += 1
            order_id = f"PAPER-{self.order_counter}"
            
            self.orders[order_id] = {
                'symbol': symbol,
                'qty': qty,
                'side': side,
                'status': 'COMPLETE',  # Paper orders fill instantly
                'fill_price': price or self.get_current_price(symbol)
            }
            
            return order_id
        
        elif self.mode == "LIVE" and self.kite:
            # Place real order via Kite
            try:
                order_params = {
                    "variety": self.kite.VARIETY_REGULAR,
                    "exchange": self.kite.EXCHANGE_NSE,
                    "tradingsymbol": symbol,
                    "transaction_type": self.kite.TRANSACTION_TYPE_BUY if side == "BUY" else self.kite.TRANSACTION_TYPE_SELL,
                    "quantity": qty,
                    "product": self.kite.PRODUCT_MIS,
                    "order_type": self.kite.ORDER_TYPE_MARKET
                }
                
                order_id = self.kite.place_order(**order_params)
                return str(order_id)
                
            except Exception as e:
                logging.error(f"Order placement failed: {e}")
                return None
        
        return None
    
    def get_order_status(self, order_id: str) -> Tuple[str, int, Optional[float]]:
        """Get order status"""
        if self.mode == "PAPER":
            if order_id in self.orders:
                order = self.orders[order_id]
                return (order['status'], order['qty'], order['fill_price'])
        
        elif self.mode == "LIVE" and self.kite:
            try:
                orders = self.kite.orders()
                for o in orders:
                    if str(o['order_id']) == order_id:
                        return (o['status'], o.get('filled_quantity', 0), o.get('average_price'))
            except Exception as e:
                logging.error(f"Failed to fetch order status: {e}")
        
        return ("UNKNOWN", 0, None)


# ==============================
# UNIFIED EXECUTION ENGINE
# ==============================

class ExecutionEngine:
    """
    Unified execution engine - works with ANY data provider
    Same logic for backtest/paper/live
    """
    
    def __init__(self, 
                 strategy: StrategyCore,
                 data_provider: DataProvider,
                 config: StrategyConfig):
        
        self.strategy = strategy
        self.data = data_provider
        self.config = config
        
        # State
        self.capital = config.initial_capital
        self.starting_capital = config.initial_capital
        self.open_trades: Dict[str, Trade] = {}
        self.closed_trades: List[Trade] = []
        
        # Daily tracking
        self.daily_pnl: Dict[str, float] = {}
        self.current_date: Optional[datetime] = None
        
        # Pending orders
        self.pending_orders: Dict[str, Dict] = {}
    
    def get_available_capital(self) -> float:
        """Calculate available capital"""
        allocated = sum(
            trade.entry * trade.qty_remaining
            for trade in self.open_trades.values()
        )
        return self.capital - allocated
    
    def check_daily_loss_limit(self, date: datetime) -> bool:
        """Check if daily loss limit reached"""
        date_key = date.strftime("%Y-%m-%d")
        daily_loss = self.daily_pnl.get(date_key, 0.0)
        
        loss_pct = abs(daily_loss / self.starting_capital)
        
        if loss_pct >= self.config.max_daily_loss_pct:
            logging.critical(f"DAILY LOSS KILL-SWITCH: {loss_pct:.2%}")
            return True
        
        return False
    
    def process_bar(self, symbol: str, date: datetime, bar: Dict[str, Any]) -> None:
        """
        Process a single bar - CORE LOGIC
        This is called by both backtest and live trading loops
        """
        self.current_date = date
        
        # Set date in data provider (for backtest)
        if isinstance(self.data, BacktestDataProvider):
            self.data.set_current_date(date)
        
        # Check daily loss limit
        if self.check_daily_loss_limit(date):
            return
        
        # ===== EXISTING POSITION MANAGEMENT =====
        if symbol in self.open_trades:
            trade = self.open_trades[symbol]
            
            if trade.exit_pending:
                return
            
            ltp = bar['close']
            high = bar.get('high', ltp)
            low = bar.get('low', ltp)
            
            # Check partial exit
            trade, exit_qty = self.strategy.check_partial_exit(trade, high)
            
            if exit_qty > 0:
                self._execute_partial_exit(trade, date, high, exit_qty)
            
            # Update trailing SL
            trade, _ = self.strategy.update_trailing_sl(trade, ltp)
            
            # Check stop loss
            if self.strategy.check_stop_loss_hit(trade, low):
                self._execute_full_exit(trade, date, low, "STOP_LOSS")
        
        # ===== NEW ENTRY SIGNAL =====
        else:
            # Check if we can take new position
            if len(self.open_trades) >= self.config.max_open_positions:
                return
            
            # Check entry filters
            passed, reason = self.strategy.check_entry_filters(bar)
            
            if not passed:
                logging.debug(f"{symbol} {date.date()}: Entry rejected - {reason}")
                return
            
            # Calculate position size
            price = bar['close']
            atr = bar['atr']
            available = self.get_available_capital()
            
            qty = self.strategy.calculate_position_size(price, atr, available)
            required = qty * price
            
            if required > available:
                logging.debug(f"{symbol}: Insufficient capital")
                return
            
            # Execute entry
            self._execute_entry(symbol, date, bar, qty)
    
    def _execute_entry(self, symbol: str, date: datetime, bar: Dict[str, Any], qty: int) -> None:
        """Execute entry"""
        price = bar['close']
        atr = bar['atr']
        
        sl = self.strategy.calculate_stop_loss(price, atr, "BUY")
        
        # Calculate fees
        entry_value = price * qty
        fees = self.strategy.calculate_fees(entry_value, "BUY")
        
        # Create trade
        trade = Trade(
            symbol=symbol,
            side="BUY",
            entry=price,
            sl=sl,
            qty=qty,
            qty_remaining=qty,
            atr=atr,
            entry_time=date,
            entry_fees=fees
        )
        
        self.open_trades[symbol] = trade
        
        logging.info(
            f"[ENTRY] {symbol} | {date.date()} | "
            f"Price: {price:.2f} | Qty: {qty} | SL: {sl:.2f}"
        )
    
    def _execute_partial_exit(self, trade: Trade, date: datetime, price: float, qty: int) -> None:
        """Execute partial exit"""
        exit_value = price * qty
        fees = self.strategy.calculate_fees(exit_value, "SELL")
        
        pnl = self.strategy.calculate_pnl(trade, price, qty) - fees
        
        trade.partial_exit_time = date
        trade.partial_exit_price = price
        trade.partial_exit_qty = qty
        trade.qty_remaining -= qty
        trade.realized_pnl += pnl
        
        # Update daily P&L
        date_key = date.strftime("%Y-%m-%d")
        self.daily_pnl[date_key] = self.daily_pnl.get(date_key, 0.0) + pnl
        
        logging.info(
            f"[PARTIAL EXIT] {trade.symbol} | {date.date()} | "
            f"Price: {price:.2f} | Qty: {qty} | P&L: {pnl:+,.2f}"
        )
    
    def _execute_full_exit(self, trade: Trade, date: datetime, price: float, reason: str) -> None:
        """Execute full exit"""
        qty = trade.qty_remaining
        exit_value = price * qty
        fees = self.strategy.calculate_fees(exit_value, "SELL")
        
        pnl = self.strategy.calculate_pnl(trade, price, qty) - fees
        
        trade.exit_time = date
        trade.exit_price = price
        trade.exit_reason = reason
        trade.qty_remaining = 0
        trade.realized_pnl += pnl
        
        # Update capital and P&L
        self.capital += trade.realized_pnl
        
        date_key = date.strftime("%Y-%m-%d")
        self.daily_pnl[date_key] = self.daily_pnl.get(date_key, 0.0) + pnl
        
        # Move to closed trades
        self.closed_trades.append(trade)
        del self.open_trades[trade.symbol]
        
        logging.info(
            f"[EXIT] {trade.symbol} | {date.date()} | {reason} | "
            f"Price: {price:.2f} | Total P&L: {trade.realized_pnl:+,.2f} ({trade.pnl_pct:+.2f}%) | "
            f"R: {trade.r_multiple:+.2f}"
        )
    
    def get_results(self) -> Dict:
        """Get performance results"""
        if not self.closed_trades:
            return {"error": "No trades executed"}
        
        total_return = self.capital - self.starting_capital
        total_return_pct = (total_return / self.starting_capital) * 100
        
        winning_trades = [t for t in self.closed_trades if t.realized_pnl > 0]
        losing_trades = [t for t in self.closed_trades if t.realized_pnl < 0]
        
        win_rate = (len(winning_trades) / len(self.closed_trades)) * 100
        
        avg_win = np.mean([t.realized_pnl for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t.realized_pnl for t in losing_trades]) if losing_trades else 0
        
        total_wins = sum(t.realized_pnl for t in winning_trades)
        total_losses = sum(t.realized_pnl for t in losing_trades)
        
        profit_factor = abs(total_wins / total_losses) if total_losses != 0 else 0
        
        avg_r = np.mean([t.r_multiple for t in self.closed_trades])
        
        return {
            "capital": {
                "initial": self.starting_capital,
                "final": self.capital,
                "total_return": total_return,
                "total_return_pct": total_return_pct
            },
            "trades": {
                "total": len(self.closed_trades),
                "winning": len(winning_trades),
                "losing": len(losing_trades),
                "win_rate": win_rate
            },
            "pnl": {
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "profit_factor": profit_factor,
                "avg_r_multiple": avg_r
            }
        }


# ==============================
# INDICATOR CALCULATION
# ==============================

def add_indicators(df: pd.DataFrame, config: StrategyConfig) -> pd.DataFrame:
    """Add technical indicators to dataframe"""
    df = df.copy()
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    df['atr'] = tr.rolling(window=config.atr_period).mean()
    
    # ADX (simplified)
    up_move = df['high'].diff()
    down_move = -df['low'].diff()
    plus_dm = ((up_move > down_move) & (up_move > 0)).astype(int) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)).astype(int) * down_move
    
    plus_di = 100 * plus_dm.rolling(window=14).sum() / (tr.rolling(14).sum())
    minus_di = 100 * minus_dm.rolling(window=14).sum() / (tr.rolling(14).sum())
    
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    df['adx'] = dx.rolling(window=14).mean()
    
    # EMAs
    df['ema20'] = df['close'].ewm(span=config.ema_short, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=config.ema_long, adjust=False).mean()
    
    # Volume ratio
    df['vol_avg'] = df['volume'].rolling(window=config.vol_window).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']
    
    return df.dropna()


# ==============================
# USAGE EXAMPLES
# ==============================

def example_backtest():
    """Example: Run backtest"""
    import yfinance as yf
    
    # Configuration
    config = StrategyConfig(
        initial_capital=100000,
        risk_per_trade=0.005,
        max_open_positions=5
    )
    
    # Fetch historical data
    symbols = ["RELIANCE", "TCS", "INFY"]
    historical_data = {}
    
    for symbol in symbols:
        ticker = yf.Ticker(f"{symbol}.NS")
        df = ticker.history(period="6mo", interval="1d")
        df = df.reset_index()
        df.columns = df.columns.str.lower()
        df = add_indicators(df, config)
        historical_data[symbol] = df
    
    # Create backtest data provider
    data_provider = BacktestDataProvider(historical_data)
    
    # Create strategy and engine
    strategy = StrategyCore(config)
    engine = ExecutionEngine(strategy, data_provider, config)
    
    # Get all dates
    all_dates = sorted(set(
        date for df in historical_data.values()
        for date in df['date']
    ))
    
    # Run backtest
    for date in all_dates:
        for symbol, df in historical_data.items():
            rows = df[df['date'] == date]
            if not rows.empty:
                bar = rows.iloc[0].to_dict()
                engine.process_bar(symbol, date, bar)
    
    # Get results
    results = engine.get_results()
    if results is None or "error" in results:
        print("No trades executed in backtest.")
        return
    print(f"\nBacktest Results:")
    print(f"Total Return: {results['capital']['total_return_pct']:.2f}%")
    print(f"Win Rate: {results['trades']['win_rate']:.2f}%")
    print(f"Profit Factor: {results['pnl']['profit_factor']:.2f}")


def example_paper_trading():
    """Example: Run paper trading"""
    config = StrategyConfig()
    
    # Create live data provider in paper mode
    data_provider = LiveDataProvider(mode="PAPER")
    
    # Create strategy and engine
    strategy = StrategyCore(config)
    engine = ExecutionEngine(strategy, data_provider, config)
    
    # This would run in a loop, processing bars as they come in
    # Similar to your current execution_engine.py


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s'
    )
    
    print("Running backtest example...")
    example_backtest()
