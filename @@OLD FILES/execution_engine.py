"""
EXECUTION ENGINE - FIXED VERSION
---------------------------------
Critical bugs fixed:
1. Exit price fetching
2. Capital tracking
3. Daily loss kill-switch
4. P&L tracking
"""

import pandas as pd
import logging
from datetime import datetime
import math
import os
from typing import Optional, Any, Dict, Tuple
import time
from collections import deque
from threading import Lock
import sys

from dataclasses import dataclass, asdict



from safe_state_manager import (
    SafeStateManager, 
    SafePendingOrdersManager,
    SafePnLManager,
    StateTransaction,
    StateLockError,
    safe_load_state as load_state,
    safe_save_state as save_state,
    safe_load_pending_orders as load_pending_orders,
    safe_save_pending_orders as save_pending_orders,
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ==============================
# CONFIG
# ==============================
EXCEL_FILE = "MiniRobo.xlsx"
SHEET = "SCREENER_OUTPUT"
SECTOR_SHEET = "SECTOR_MAP"

MODE = "LIVE"        # PAPER | LIVE
CAPITAL = 5000   # Increased from 5k (recommended minimum)
RISK_PER_TRADE = 0.005  # 0.5% per trade
MAX_DAILY_LOSS = 0.02   # 2% kill-switch
MAX_OPEN_POSITIONS = 5
MAX_PER_SECTOR = 2
MAX_SLIPPAGE_PCT = 0.2  # 0.2% slippage tolerance

# Trading parameters
ATR_PERIOD = 14
SL_ATR_MULT = 1.5
TARGET_ATR_MULT = 2.0
PARTIAL_EXIT_RATIO = 0.8
PARTIAL_EXIT_QTY_PCT = 0.5
TRAILING_SL_ATR_MULT = 1.5
ORDER_TIMEOUT_SECONDS = 300

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"trading_log_{datetime.now().strftime('%Y%m%d')}.log", encoding='utf-8')
    ]
)

# ==============================
# NEW: P&L TRACKING
# ==============================
@dataclass
class DailyPnL:
    """Track daily P&L for kill-switch"""
    date: str
    starting_capital: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    trades_executed: int = 0
    
    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl
    
    @property
    def pnl_pct(self) -> float:
        if self.starting_capital == 0:
            return 0.0
        return (self.total_pnl / self.starting_capital) * 100
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @staticmethod
    def from_dict(data: dict) -> 'DailyPnL':
        return DailyPnL(
            date=data.get("date", ""),
            starting_capital=data.get("starting_capital", 0.0),
            realized_pnl=data.get("realized_pnl", 0.0),
            unrealized_pnl=data.get("unrealized_pnl", 0.0),
            trades_executed=data.get("trades_executed", 0)
        )


# ==============================
# DATA MODELS (Updated)
# ==============================
@dataclass
class Trade:
    """Represents a single open trade"""
    symbol: str
    side: str
    entry: float
    sl: float
    qty: int
    qty_remaining: int
    atr: float
    partial_done: bool = False
    trailing_active: bool = False
    entry_time: Optional[str] = None
    exit_pending: bool = False
    realized_pnl: float = 0.0  # NEW: Track realized P&L per trade
    entry_fees: float = 0.0  # NEW: Track entry fees
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @staticmethod
    def from_dict(data: dict) -> 'Trade':
        if isinstance(data, Trade):
            return data
        return Trade(
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            entry=float(data.get("entry", 0.0)),
            sl=float(data.get("sl", 0.0)),
            qty=int(data.get("qty", 0)),
            qty_remaining=int(data.get("qty_remaining", 0)),
            atr=float(data.get("atr", 0.0)),
            partial_done=bool(data.get("partial_done", False)),
            trailing_active=bool(data.get("trailing_active", False)),
            entry_time=data.get("entry_time"),
            exit_pending=bool(data.get("exit_pending", False)),
            realized_pnl=float(data.get("realized_pnl", 0.0)),
            entry_fees=float(data.get("entry_fees", 0.0))
        )


@dataclass
class PendingOrder:
    """Represents an order awaiting execution"""
    order_id: str
    symbol: str
    side: str
    req_qty: int
    price: Optional[float]
    atr: Optional[float]
    sl: Optional[float]
    reason: Optional[str] = None
    time: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @staticmethod
    def from_dict(data: dict) -> 'PendingOrder':
        if isinstance(data, PendingOrder):
            return data
        return PendingOrder(
            order_id=data.get("order_id", ""),
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            req_qty=int(data.get("req_qty", 0)),
            price=data.get("price"),
            atr=data.get("atr"),
            sl=data.get("sl"),
            reason=data.get("reason"),
            time=data.get("time")
        )



# ==============================
# RATE LIMITER (Zerodha: 10 req/sec)
# ==============================
class RateLimiter:
    """Thread-safe rate limiter for API calls"""
    def __init__(self, max_calls: int = 10, time_window: float = 1.0):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = deque()
        self.lock = Lock()
    
    def wait_if_needed(self):
        """Block if rate limit would be exceeded"""
        with self.lock:
            now = time.time()
            # Remove calls outside the time window
            while self.calls and self.calls[0] < now - self.time_window:
                self.calls.popleft()
            
            if len(self.calls) >= self.max_calls:
                sleep_time = self.time_window - (now - self.calls[0])
                if sleep_time > 0:
                    logging.debug(f"Rate limit: sleeping {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                    self.calls.popleft()
            
            self.calls.append(time.time())

# Global rate limiter
rate_limiter = RateLimiter(max_calls=8, time_window=1.0)  # Conservative: 8/sec




# ==============================
# BROKER INIT
# ==============================
def init_kite() -> Optional[Any]:
    """Initialize Zerodha Kite connection for LIVE mode"""
    try:
        from kiteconnect import KiteConnect
        api_key = os.getenv("KITE_API_KEY")
        access_token = os.getenv("KITE_ACCESS_TOKEN")
        
        if not api_key or not access_token:
            logging.error("KITE_API_KEY or KITE_ACCESS_TOKEN not set")
            return None
        
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)
        
        # Test connection
        profile = kite.profile()
               
        if isinstance(profile, dict):
            user_name = profile.get('user_name', 'Unknown')
            logging.info(f"Kite connected: {user_name}")
        else:
            # Handle the case when 'profile' is not a dictionary
            logging.info("Kite connection failed")

        return kite
    except Exception as e:
        logging.error(f"Failed to initialize Kite: {e}")
        return None


kite: Optional[Any] = init_kite() if MODE == "LIVE" else None


# ==============================
# NEW: DAILY P&L MANAGEMENT
# ==============================
PNL_FILE = "daily_pnl.json"

def load_daily_pnl() -> DailyPnL:
    """Load or initialize today's P&L tracker"""
    import json
    today = datetime.now().strftime("%Y-%m-%d")
    
    if os.path.exists(PNL_FILE):
        try:
            with open(PNL_FILE, "r") as f:
                data = json.load(f)
                pnl = DailyPnL.from_dict(data)
                
                # Reset if new day
                if pnl.date != today:
                    logging.info(f"New day detected. Previous P&L: {pnl.pnl_pct:.2f}%")
                    return DailyPnL(date=today, starting_capital=CAPITAL)
                
                return pnl
        except Exception as e:
            logging.warning(f"Failed to load P&L file: {e}")
    
    return DailyPnL(date=today, starting_capital=CAPITAL)


def save_daily_pnl(pnl: DailyPnL):
    """Persist daily P&L"""
    import json
    with open(PNL_FILE, "w") as f:
        json.dump(pnl.to_dict(), f, indent=2)


def check_daily_loss_killswitch(pnl: DailyPnL) -> bool:
    """Check if daily loss limit reached"""
    if pnl.pnl_pct <= -(MAX_DAILY_LOSS * 100):
        logging.critical(
            f"DAILY LOSS KILL-SWITCH TRIGGERED! "
            f"P&L: {pnl.pnl_pct:.2f}% (Limit: -{MAX_DAILY_LOSS*100}%)"
        )
        return True
    return False


# ==============================
# FIXED: GET LIVE PRICE
# ==============================
def get_live_price(symbol: str) -> Optional[float]:
    """
    Fetch live price for a symbol.
    FIXED: Now properly handles both PAPER and LIVE modes
    """
    if MODE == "PAPER":
        # In paper mode, fetch from yfinance for realistic simulation
        try:
            import yfinance as yf
            ticker = yf.Ticker(f"{symbol}.NS")
            data = ticker.history(period="1d", interval="1m")
            if not data.empty:
                price = data['Close'].iloc[-1]
                logging.debug(f"{symbol} live price (YF): {price:.2f}")
                return float(price)
        except Exception as e:
            logging.warning(f"Failed to fetch paper price for {symbol}: {e}")
            return None
    
    if kite is None:
        logging.warning("Kite not initialized, cannot fetch live price")
        return None
    
    try:
        quote = kite.quote(f"NSE:{symbol}")
        price = quote[f"NSE:{symbol}"]["last_price"]
        logging.debug(f"{symbol} live price (Kite): {price:.2f}")
        return float(price)
    except Exception as e:
        logging.warning(f"Failed to fetch price for {symbol}: {e}")
        return None


# ==============================
# CAPITAL MANAGEMENT
# ==============================
def get_live_capital(kite: Optional[Any]) -> float:
    """Fetch available capital from broker"""
    if kite is None:
        return CAPITAL
    try:
        margins = kite.margins()
        return margins["equity"]["available"]["cash"]
    except Exception as e:
        logging.error(f"Failed to fetch live capital: {e}")
        return CAPITAL


def load_sector_map() -> dict:
    """Load sector map from Excel"""
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name=SECTOR_SHEET)
        return dict(zip(df["SYMBOL"], df["SECTOR"]))
    except Exception as e:
        logging.warning(f"Failed to load sector map: {e}")
        return {}


def get_symbol_sector(sector_map: dict, symbol: str) -> str:
    """Get sector for a symbol with fallback"""
    return sector_map.get(symbol, "OTHERS")


def count_positions_by_sector(state: dict, sector_map: dict, symbol: str) -> int:
    """Count existing positions in the same sector"""
    target_sector = get_symbol_sector(sector_map, symbol)
    count = 0
    for sym in state:
        if get_symbol_sector(sector_map, sym) == target_sector:
            count += 1
    return count


# ==============================
# RECONCILIATION
# ==============================
def reconcile_with_broker(state: dict, kite: Optional[Any]) -> dict:
    """Verify state matches broker positions (LIVE mode only)"""
    if kite is None:
        return state
    
    try:
        broker_positions = kite.positions()["net"]
        live_symbols = {p["tradingsymbol"]: p for p in broker_positions if p["quantity"] != 0}

        reconciled = {}
        for symbol, trade_dict in state.items():
            if symbol in live_symbols:
                reconciled[symbol] = trade_dict
            else:
                logging.warning(f"{symbol} missing at broker. Removing from state.")

        # ADD THIS: Detect orphaned broker positions
        for symbol, broker_pos in live_symbols.items():
            if symbol not in state:
                logging.critical(
                    f" ORPHAN POSITION DETECTED: {symbol} exists at broker "
                    f"but not in state! Qty: {broker_pos['quantity']}"
                )
                # Option 1: Add to state with conservative SL
                # Option 2: Alert and halt trading
                # Option 3: Auto-exit position

        return reconciled
    except Exception as e:
        logging.error(f"Reconciliation failed: {e}")
        return state

# ==============================
# POSITION SIZING
# ==============================
def calculate_qty(price: float, atr: float, available_capital: float) -> int:
    """
    Calculate position size based on risk per trade.
    FIXED: Now checks if affordable
    """
    risk_amount = CAPITAL * RISK_PER_TRADE
    sl_points = atr * SL_ATR_MULT
    
    if sl_points == 0:
        logging.warning(f"SL points is zero, using minimum qty")
        return 1
    
    risk_based_qty = math.floor(risk_amount / sl_points)
    max_affordable_qty = math.floor(available_capital / price) if price > 0 else 0
    
    qty = min(risk_based_qty, max_affordable_qty)
    qty = max(qty, 1)  # Minimum 1 share
    
    # Safety check: don't allocate more than 30% of capital to one position
    max_position_size = CAPITAL * 0.3
    if qty * price > max_position_size:
        qty = math.floor(max_position_size / price)
        qty = max(qty, 1)
    
    return qty


# ==============================
# ORDER EXECUTION
# ==============================

def place_order(symbol: str, qty: int, side: str, order_type: str = "MARKET", 
                price: float = 0, max_retries: int = 3) -> Optional[str]:
    """
    Place an order with retry logic and proper error handling.
    
    Args:
        symbol: Stock symbol
        qty: Quantity to trade
        side: "BUY" or "SELL"
        order_type: "MARKET" or "LIMIT"
        price: Required for LIMIT orders
        max_retries: Number of retry attempts
    
    Returns:
        Order ID on success, None on failure
    """
    if qty <= 0:
        logging.error(f"Invalid quantity {qty} for {symbol}")
        return None
    
    # Paper mode simulation
    if MODE == "PAPER":
        fake_order_id = f"PAPER-{symbol}-{side}-{int(time.time() * 1000)}"
        logging.info(f" PAPER {side} {qty} {symbol}")
        return fake_order_id
    
    # Live mode with retries
    if kite is None:
        logging.error("Kite connection not initialized")
        return None
    
    for attempt in range(max_retries):
        try:
            rate_limiter.wait_if_needed()  # Respect rate limits
            
            order_params = {
                "variety": kite.VARIETY_REGULAR,
                "exchange": kite.EXCHANGE_NSE,
                "tradingsymbol": symbol,
                "transaction_type": kite.TRANSACTION_TYPE_BUY if side == "BUY" else kite.TRANSACTION_TYPE_SELL,
                "quantity": qty,
                "product": kite.PRODUCT_MIS,  # Intraday
                "order_type": kite.ORDER_TYPE_MARKET if order_type == "MARKET" else kite.ORDER_TYPE_LIMIT
            }
            
            if order_type == "LIMIT" and price:
                order_params["price"] = price
            
            order_id = kite.place_order(**order_params)
            logging.info(f" {side} order placed: {qty} {symbol} | Order ID: {order_id}")
            return str(order_id)
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Don't retry on these errors
            if any(x in error_msg for x in ["insufficient funds", "rejected", "invalid symbol"]):
                logging.error(f" {symbol} order REJECTED: {e}")
                return None
            
            # Retry on network/timeout errors
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                logging.warning(f"{symbol} order attempt {attempt+1} failed: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                logging.error(f" {symbol} order FAILED after {max_retries} attempts: {e}")
                return None
    
    return None



# ==============================
# ORDER STATUS CHECKER
# ==============================

def poll_orders(pending_orders: dict, max_retries: int = 3) -> Dict[str, Tuple[str, int, Optional[float]]]:
    """
    Poll broker for order updates with retry logic.
    
    Returns:
        dict: {order_id: (status, filled_qty, avg_price)}
    """
    if MODE == "PAPER":
        # Paper mode: simulate instant fills
        result = {}
        for oid, podata in pending_orders.items():
            po = PendingOrder.from_dict(podata)
            current_price = get_live_price(po.symbol)
            if current_price is None:
                current_price = po.price if po.price else 0.0
            result[oid] = ("COMPLETE", po.req_qty, current_price)
        return result
    
    if kite is None:
        logging.error("Kite not initialized for order polling")
        return {}
    
    # Live mode with retry
    for attempt in range(max_retries):
        try:
            rate_limiter.wait_if_needed()
            broker_orders = kite.orders()
            result = {}
            
            for o in broker_orders:
                oid = str(o["order_id"])
                if oid not in pending_orders:
                    continue
                
                status = o["status"]
                filled_qty = o.get("filled_quantity", 0)
                avg_price = o.get("average_price", 0.0)
                
                # Map broker statuses to our statuses
                if status == "COMPLETE":
                    result[oid] = ("COMPLETE", filled_qty, avg_price)
                elif status in ["OPEN", "TRIGGER PENDING", "PENDING"]:
                    result[oid] = ("PENDING", filled_qty, avg_price if filled_qty > 0 else None)
                elif status in ["REJECTED", "CANCELLED"]:
                    result[oid] = (status, filled_qty, avg_price if filled_qty > 0 else None)
                else:
                    logging.warning(f"Unknown order status: {status} for {oid}")
                    result[oid] = ("UNKNOWN", filled_qty, avg_price)
            
            return result
            
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logging.warning(f"Order polling failed (attempt {attempt+1}): {e}. Retrying...")
                time.sleep(wait_time)
                continue
            else:
                logging.error(f"Order polling FAILED after {max_retries} attempts: {e}")
                return {}
    
    return {}





# ==============================
# FIXED: PROCESS PENDING SELLS
# ==============================
def process_pending_sells(
    state: dict, 
    pending_orders: dict, 
    pnl: DailyPnL
) -> Tuple[dict, dict, DailyPnL]:
    """
    Process completed/rejected SELL orders.
    FIXED: Now properly tracks P&L and updates capital
    """
    updates = poll_orders(pending_orders)

    for order_id, (status, filled_qty, avg_price) in updates.items():
        po_data = pending_orders.get(order_id)
        if not po_data:
            continue
        
        po = PendingOrder.from_dict(po_data)
        if po.side != "SELL":
            continue

        symbol = po.symbol
        trade_dict = state.get(symbol)
        
        if not trade_dict:
            logging.warning(f"{symbol} not in state, but SELL order exists")
            del pending_orders[order_id]
            continue

        if status == "COMPLETE" and filled_qty > 0:
            trade = Trade.from_dict(trade_dict)
            
            # FIXED: Calculate realized P&L
            exit_price = avg_price if avg_price and avg_price > 0 else get_live_price(symbol)
            if exit_price is None:
                exit_price = trade.entry
                logging.warning(f"{symbol} exit price unknown, using entry price")
            
            pnl_per_share = exit_price - trade.entry if trade.side == "BUY" else trade.entry - exit_price
            realized_pnl = pnl_per_share * filled_qty
            
            # Update trade
            trade.realized_pnl += realized_pnl
            trade.qty_remaining -= filled_qty
            
            # Update daily P&L
            pnl.realized_pnl += realized_pnl
            
            logging.info(
                f" {symbol} | SELL CONFIRMED | "
                f"Qty={filled_qty}, Price={exit_price:.2f}, "
                f"P&L={realized_pnl:+.2f} ({(pnl_per_share/trade.entry)*100:+.2f}%)"
            )

            if trade.qty_remaining <= 0:
                logging.info(
                    f" {symbol} | POSITION CLOSED | "
                    f"Total P&L: {trade.realized_pnl:+.2f}"
                )
                del state[symbol]
            else:
                trade.exit_pending = False
                state[symbol] = trade.to_dict()
                logging.info(
                    f"{symbol} | PARTIAL SELL CONFIRMED | "
                    f"Remaining={trade.qty_remaining}"
                )
            
            del pending_orders[order_id]

        elif status in ("REJECTED", "CANCELLED"):
            logging.error(f" {symbol} | SELL {status}")
            # Don't remove from state, but clear exit_pending flag
            if trade_dict:
                trade = Trade.from_dict(trade_dict)
                trade.exit_pending = False
                state[symbol] = trade.to_dict()
            del pending_orders[order_id]

    return state, pending_orders, pnl


# ==============================
# FIXED: PROCESS PENDING BUYS
# ==============================
def process_pending_buys(
    state: dict, 
    pending_orders: dict,
    pnl: DailyPnL
) -> Tuple[dict, dict, DailyPnL]:
    """
    Process completed/rejected BUY orders.
    FIXED: Now uses actual fill price
    """
    updates = poll_orders(pending_orders)

    for oid, (status, filled_qty, avg_price) in updates.items():
        po_data = pending_orders.get(oid)
        if not po_data:
            continue
        
        po = PendingOrder.from_dict(po_data)
        if po.side != "BUY":
            continue

        symbol = po.symbol

        if status == "COMPLETE" and filled_qty > 0:
            # FIXED: Use actual fill price
            entry_price = avg_price if avg_price and avg_price > 0 else po.price

            if avg_price and po.price:
                slippage_pct = abs(avg_price - po.price) / po.price * 100
                if slippage_pct > MAX_SLIPPAGE_PCT:
                    logging.error(f"{symbol} excessive slippage: {slippage_pct:.2f}%")

            if entry_price is None or entry_price == 0:
                entry_price = get_live_price(symbol)
            
            if entry_price is None:
                logging.error(f"{symbol} entry price unknown, skipping")
                del pending_orders[oid]
                continue

            # NEW: Calculate entry fees
            entry_value = entry_price * filled_qty
            entry_fees = calculate_broker_fees(entry_value, "BUY")
                    
            trade = Trade(
                symbol=symbol,
                side="BUY",
                entry=entry_price,
                sl=po.sl if po.sl else entry_price - (po.atr * SL_ATR_MULT if po.atr else 0),
                qty=filled_qty,
                qty_remaining=filled_qty,
                atr=po.atr if po.atr else 0.0,
                partial_done=False,
                trailing_active=False,
                entry_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                exit_pending=False,
                realized_pnl=0.0,
                entry_fees=entry_fees
            )
            
            state[symbol] = trade.to_dict()
            pnl.trades_executed += 1
            
            logging.info(
                f"{symbol} | BUY CONFIRMED | "
                f"Qty={filled_qty}, Entry={entry_price:.2f}, SL={trade.sl:.2f}"
            )
            del pending_orders[oid]

        elif status in ("REJECTED", "CANCELLED"):
            logging.warning(f" {symbol} | BUY {status}")
            del pending_orders[oid]

    return state, pending_orders, pnl


# ==============================
# ORDER MANAGEMENT
# ==============================
def initiate_sell(
    symbol: str, 
    qty: int, 
    reason: str, 
    pending_orders: dict,
    state: dict
) -> bool:
    """
    Places SELL order and tracks it.
    Updates state to mark exit_pending.
    """
    trade_dict = state.get(symbol)
    if not trade_dict:
        logging.warning(f"{symbol} not in state, cannot sell")
        return False
    
    trade = Trade.from_dict(trade_dict)
    if trade.exit_pending:
        logging.info(f"{symbol} | SELL already pending, skipping")
        return False
    
    order_id = place_order(symbol, qty, "SELL")
    if not order_id:
        logging.error(f"{symbol} | SELL failed to place ({reason})")
        return False

    pending_orders[order_id] = PendingOrder(
        order_id=order_id,
        symbol=symbol,
        side="SELL",
        req_qty=qty,
        price=None,
        atr=None,
        sl=None,
        reason=reason,
        time=datetime.now().isoformat()
    ).to_dict()

    # Mark trade as having exit pending
    trade.exit_pending = True
    state[symbol] = trade.to_dict()

    logging.info(f" {symbol} | SELL placed | Qty={qty} | Reason={reason}")
    return True


def is_buy_pending(symbol: str, pending_orders: dict) -> bool:
    """Check if a BUY order is already pending for this symbol"""
    for po_data in pending_orders.values():
        po = PendingOrder.from_dict(po_data)
        if po.side == "BUY" and po.symbol == symbol:
            return True
    return False


def cleanup_stale_orders(pending_orders: dict) -> dict:
    """Remove orders that have timed out"""
    current_time = datetime.now()
    stale_orders = []
    
    for oid, po_data in pending_orders.items():
        po = PendingOrder.from_dict(po_data)
        
        if po.time:
            try:
                order_time = datetime.fromisoformat(po.time)
                if (current_time - order_time).total_seconds() > ORDER_TIMEOUT_SECONDS:
                    stale_orders.append(oid)
                    logging.warning(f" Order {oid} ({po.symbol}) timed out")
            except Exception:
                pass
    
    for oid in stale_orders:
        del pending_orders[oid]
    
    return pending_orders


# ==============================
# CALCULATE UNREALIZED P&L
# ==============================
def calculate_unrealized_pnl(state: dict) -> float:
    """Calculate total unrealized P&L across all positions"""
    total_unrealized = 0.0
    
    for symbol, trade_dict in state.items():
        trade = Trade.from_dict(trade_dict)
        
        ltp = get_live_price(symbol)
        if ltp is None:
            ltp = trade.entry
        
        if trade.side == "BUY":
            pnl_per_share = ltp - trade.entry
        else:
            pnl_per_share = trade.entry - ltp
        
        position_pnl = pnl_per_share * trade.qty_remaining
        total_unrealized += position_pnl
    
    return total_unrealized

# ==============================
# BROKER FEE CALCULATION
# ==============================
def calculate_broker_fees(trade_value: float, side: str, product: str = "MIS") -> float:
    """
    Calculate Zerodha fees for equity intraday (MIS) trades.
    Based on Zerodha's fee structure as of 2025.
    
    Args:
        trade_value: Total value of trade (price * quantity)
        side: "BUY" or "SELL"
        product: "MIS" (intraday) or "CNC" (delivery)
    
    Returns:
        Total fees in rupees
    """
    if trade_value == 0:
        return 0.0
    
    # Zerodha Intraday (MIS) Charges
    brokerage = min(20.0, trade_value * 0.0003)  # ₹20 or 0.03%, whichever is lower
    
    # STT (Securities Transaction Tax) - only on SELL side
    stt = (trade_value * 0.00025) if side == "SELL" else 0.0
    
    # Exchange transaction charges
    nse_charges = trade_value * 0.0000325  # 0.00325%
    
    # SEBI charges
    sebi_charges = trade_value * 0.000001  # ₹10 per crore
    
    # Stamp duty - only on BUY side
    stamp_duty = (trade_value * 0.00003) if side == "BUY" else 0.0
    
    # GST on brokerage + transaction charges
    taxable_amount = brokerage + nse_charges
    gst = taxable_amount * 0.18
    
    total_fees = brokerage + stt + nse_charges + sebi_charges + stamp_duty + gst
    
    return round(total_fees, 2)

def calculate_round_trip_fees(entry_value: float, exit_value: float) -> float:
    """
    Calculate total fees for entry + exit.
    
    Args:
        entry_value: Entry trade value (entry_price * qty)
        exit_value: Exit trade value (exit_price * qty)
    
    Returns:
        Total round-trip fees
    """
    entry_fees = calculate_broker_fees(entry_value, "BUY")
    exit_fees = calculate_broker_fees(exit_value, "SELL")
    total = entry_fees + exit_fees
    
    return round(total, 2)


# ==============================
# POSITION MANAGEMENT
# ==============================
def process_existing_trades(state: dict, sector_map: dict) -> Tuple[dict, dict]:
    """
    Process existing open positions:
    - Check for partial exits at +0.8R
    - Update trailing stop losses
    - Check for stop loss hits
    Returns (updated state, sells to execute)
    """
    sells_to_execute = {}

    for symbol, trade_dict in list(state.items()):
        trade = Trade.from_dict(trade_dict)
        
        if trade.exit_pending:
            continue

        # Get live price
        ltp = get_live_price(symbol)

        # ADD THIS:
       

        if ltp is None:
            logging.warning(f"{symbol} price unavailable, skipping checks")
            continue
        
        
        # Check for partial exit at +0.8R
        r_value = abs(trade.entry - trade.sl)
        if not trade.partial_done and trade.side == "BUY" and r_value > 0:
            target_price = trade.entry + (PARTIAL_EXIT_RATIO * r_value)
            
            if ltp >= target_price:
                exit_qty = max(1, int(trade.qty_remaining * PARTIAL_EXIT_QTY_PCT))
                
                # Only exit if we have shares left after partial
                if exit_qty < trade.qty_remaining:
                    trade.partial_done = True
                    sells_to_execute[symbol] = (exit_qty, "PARTIAL_EXIT")
                    logging.info(
                        f" {symbol} | Partial exit triggered | "
                        f"LTP={ltp:.2f}, Target={target_price:.2f}"
                    )
        
        # Update trailing SL after partial exit
        if trade.partial_done and trade.side == "BUY":
            new_sl = ltp - (TRAILING_SL_ATR_MULT * trade.atr)
            if new_sl > trade.sl:
                trade.sl = new_sl
                trade.trailing_active = True
                logging.info(f" {symbol} | Trailing SL updated to {trade.sl:.2f}")
        
        # Check for stop loss hit
        if trade.side == "BUY" and ltp <= trade.sl:
            sells_to_execute[symbol] = (trade.qty_remaining, "STOP_LOSS")
            logging.warning(
                f" {symbol} | Stop loss hit | "
                f"LTP={ltp:.2f}, SL={trade.sl:.2f}"
            )
            continue
        
        state[symbol] = trade.to_dict()
    
    return state, sells_to_execute


# ==============================
# MAIN EXECUTION LOOP
# ==============================
def run_execution_old():
    """Main execution cycle with proper error handling"""
    
    try:
        # Load daily P&L
        pnl = load_daily_pnl()
        logging.info(
            f"Daily P&L: {pnl.pnl_pct:+.2f}% "
            f"(Realized: {pnl.realized_pnl:+.2f}, Trades: {pnl.trades_executed})"
        )
        
        # Check kill-switch FIRST
        if check_daily_loss_killswitch(pnl):
            logging.critical("Trading halted due to daily loss limit")
            return
        
        # Load Excel screener output
        try:
            df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET)
            required_cols = ["SYMBOL", "PRICE", "ELIGIBLE"]
            missing = [col for col in required_cols if col not in df.columns]
            if missing:
                logging.error(f"Missing columns in Excel: {missing}")
                return
        except Exception as e:
            logging.error(f"Failed to read Excel file: {e}")
            return

        # Filter eligible stocks
        df = df[df["ELIGIBLE"] == "YES"].copy()
        df = df.drop_duplicates(subset=["SYMBOL"], keep="first")
        if df.empty:
            logging.warning("No eligible stocks to trade")
            return

        # Load state
        state = load_state()
        pending_orders = load_pending_orders()
        sector_map = load_sector_map()

        logging.info(
            f"Open positions: {len(state)}, "
            f"Pending orders: {len(pending_orders)}"
        )

        # ===== STEP 1: Process existing trades =====
        state, sells_to_execute = process_existing_trades(state, sector_map)
        
        # Initiate sell orders
        for symbol, (qty, reason) in sells_to_execute.items():
            initiate_sell(symbol, qty, reason, pending_orders, state)

        # ===== STEP 2: Process pending orders =====
        state, pending_orders, pnl = process_pending_sells(state, pending_orders, pnl)
        state, pending_orders, pnl = process_pending_buys(state, pending_orders, pnl)

        # ===== STEP 3: Cleanup stale orders =====
        pending_orders = cleanup_stale_orders(pending_orders)

        # ===== STEP 4: Update unrealized P&L =====
        pnl.unrealized_pnl = calculate_unrealized_pnl(state)
        
        logging.info(
            f"Total P&L: {pnl.pnl_pct:+.2f}% "
            f"(Realized: {pnl.realized_pnl:+.2f}, "
            f"Unrealized: {pnl.unrealized_pnl:+.2f})"
        )
        
        # Check kill-switch after updating P&L
        if check_daily_loss_killswitch(pnl):
            logging.critical("Trading halted due to daily loss limit")
            save_state(state)
            save_pending_orders(pending_orders)
            save_daily_pnl(pnl)
            return

        # ===== STEP 5: Calculate available capital =====
        if MODE == "LIVE":
            total_capital = get_live_capital(kite)
        else:
            total_capital = CAPITAL
        
        allocated_capital = sum(
            Trade.from_dict(t).entry * Trade.from_dict(t).qty_remaining 
            for t in state.values()
        )
        available_capital = total_capital - allocated_capital
        
       # Capital reserved for pending BUY orders (CRITICAL FIX)
        pending_buy_capital = 0.0
        for oid, podata in pending_orders.items():
            po = PendingOrder.from_dict(podata)
            if po.side == "BUY":
                # Use price if available, otherwise estimate from current price
                order_price = po.price if po.price else 0.0
                if order_price == 0.0:
                    # Try to get current price for estimation
                    current_price = get_live_price(po.symbol)
                    order_price = current_price if current_price else 0.0
                
                pending_buy_capital += order_price * po.req_qty

        available_capital = total_capital - allocated_capital - pending_buy_capital + pnl.unrealized_pnl

        logging.info(
            f"Capital | Total: ₹{total_capital:,.2f}, "
            f"Allocated: ₹{allocated_capital:,.2f}, "
            f"Pending: ₹{pending_buy_capital:,.2f}, "
            f"Available: ₹{available_capital:,.2f}"
        )
        
        logging.info(
            f"Unrealized P&L: {pnl.unrealized_pnl:+.2f} "
            f"(Realized: {pnl.realized_pnl:+.2f}, Trades: {pnl.trades_executed})"
        )


        # Safety check
        if available_capital < 0:
            logging.error(
                f"NEGATIVE AVAILABLE CAPITAL!"
                f"Total={total_capital:.0f}, Allocated={allocated_capital:.0f}, "
                f"Pending={pending_buy_capital:.0f}"
            )
            available_capital = 0.0  # Prevent new trades

        # ===== STEP 6: Process new screener signals =====
        df["EXECUTED"] = "NO"
        
        for _, row in df.iterrows():
            symbol = row["SYMBOL"]
            
            # Skip if already trading
            if symbol in state:
                logging.debug(f"{symbol} already in state, skipping")
                continue

            # Skip if BUY already pending
            if is_buy_pending(symbol, pending_orders):
                logging.debug(f"{symbol} BUY already pending, skipping")
                continue

            # Check position limits
            if len(state) >= MAX_OPEN_POSITIONS:
                logging.warning("Max open positions reached, stopping new entries")
                break

            # Check sector limits
            if MAX_PER_SECTOR > 0:
                sector_count = count_positions_by_sector(state, sector_map, symbol)
                if sector_count >= MAX_PER_SECTOR:
                    logging.info(
                        f"{symbol} sector limit reached "
                        f"({sector_count}/{MAX_PER_SECTOR}), skipping"
                    )
                    continue

            # Calculate position size
            price = row["PRICE"]
            atr = row["ATR_PCT"] * price / 100
            
            if atr == 0:
                logging.warning(f"{symbol} ATR is zero, skipping")
                continue
            
            qty = calculate_qty(price, atr, available_capital)
            required_capital = qty * price

            # Check capital availability
            if required_capital > available_capital:
                logging.warning(
                    f"{symbol} requires {required_capital:.2f}, "
                    f"only {available_capital:.2f} available, skipping"
                )
                continue

            # Safety check: Don't trade if stock price > 20% of capital
            if price > CAPITAL * 0.2:
                logging.warning(
                    f"{symbol} price {price:.2f} too high "
                    f"(>20% of capital), skipping"
                )
                continue

             


            # Place order
            order_id = place_order(symbol, qty, "BUY")
            if not order_id:
                logging.warning(f"Failed to place order for {symbol}, skipping")
                continue


            # Verify order wasn't immediately rejected
            time.sleep(0.5)  # Brief pause
            status_check = poll_orders({order_id: pending_orders[order_id]})
            if status_check.get(order_id, ("UNKNOWN",))[0] == "REJECTED":
                logging.error(f"{symbol} order rejected immediately")
                continue    


            available_capital -= required_capital  # Reserve capital

            # Track pending order
            sl = price - (atr * SL_ATR_MULT)
            pending_orders[order_id] = PendingOrder(
                order_id=order_id,
                symbol=symbol,
                side="BUY",
                req_qty=qty,
                price=price,
                atr=atr,
                sl=sl,
                reason=None,
                time=datetime.now().isoformat()
            ).to_dict()

         
            df.loc[df["SYMBOL"] == symbol, "EXECUTED"] = "YES"
            
            logging.info(
                f"{symbol} | BUY order placed | "
                f"Qty={qty}, Price={price:.2f}, SL={sl:.2f}"
            )

        # Process immediate fills (paper mode or fast broker)
        state, pending_orders, pnl = process_pending_buys(state, pending_orders, pnl)
        
        # ===== SAVE STATE =====
        save_state(state)
        save_pending_orders(pending_orders)
        save_daily_pnl(pnl)

        # Write execution log
        try:
            with pd.ExcelWriter(
                EXCEL_FILE, 
                engine="openpyxl", 
                mode="a", 
                if_sheet_exists="replace"
            ) as writer:
                df.to_excel(writer, sheet_name="EXECUTION_LOG", index=False)
        except Exception as e:
            logging.error(f"Failed to write execution log: {e}")

        logging.info(" Execution cycle completed successfully")
        
    except Exception as e:
        logging.critical(f" CRITICAL ERROR in execution cycle: {e}", exc_info=True)
        raise

def run_execution():
    """Main execution cycle with safe state management"""

    if not verify_connection():
         logging.critical("Connection lost! Attempting recovery...")

    try:
       
        # Use transaction for atomic state updates
        with StateTransaction() as (state, pending_orders, pnl_data):
            
            # Convert P&L dict to object
            pnl = DailyPnL.from_dict(pnl_data) if pnl_data else load_daily_pnl()
            
            logging.info(
                f"Daily P&L: {pnl.pnl_pct:+.2f}% "
                f"(Realized: {pnl.realized_pnl:+.2f}, Trades: {pnl.trades_executed})"
            )
            
            # Check kill-switch FIRST
            if check_daily_loss_killswitch(pnl):
                logging.critical("Trading halted due to daily loss limit")
                return
            
            # Load Excel screener output
            try:
                df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET)
                required_cols = ["SYMBOL", "PRICE", "ELIGIBLE"]
                missing = [col for col in required_cols if col not in df.columns]
                if missing:
                    logging.error(f"Missing columns in Excel: {missing}")
                    return
            except Exception as e:
                logging.error(f"Failed to read Excel file: {e}")
                return
            
            # Filter eligible stocks
            df = df[df["ELIGIBLE"] == "YES"].copy()
            df = df.drop_duplicates(subset=["SYMBOL"], keep="first")
            
            if df.empty:
                logging.warning("No eligible stocks to trade")
                return
            
            sector_map = load_sector_map()
            
            logging.info(
                f"Open positions: {len(state)}, "
                f"Pending orders: {len(pending_orders)}"
            )
            
            # ===== STEP 1: Process existing trades =====
            state, sells_to_execute = process_existing_trades(state, sector_map)
            
            # Initiate sell orders
            for symbol, (qty, reason) in sells_to_execute.items():
                initiate_sell(symbol, qty, reason, pending_orders, state)
            
            # ===== STEP 2: Process pending orders =====
            state, pending_orders, pnl = process_pending_sells(
                state, pending_orders, pnl
            )
            state, pending_orders, pnl = process_pending_buys(
                state, pending_orders, pnl
            )
            
            # ===== STEP 3: Cleanup stale orders =====
            pending_orders = cleanup_stale_orders(pending_orders)
            
            # ===== STEP 4: Update unrealized P&L =====
            pnl.unrealized_pnl = calculate_unrealized_pnl(state)
            
            logging.info(
                f"Total P&L: {pnl.pnl_pct:+.2f}% "
                f"(Realized: {pnl.realized_pnl:+.2f}, "
                f"Unrealized: {pnl.unrealized_pnl:+.2f})"
            )
            
            # Check kill-switch after updating P&L
            if check_daily_loss_killswitch(pnl):
                logging.critical("Trading halted due to daily loss limit")
                return
            
            # ===== STEP 5: Calculate available capital =====
            if MODE == "LIVE":
                total_capital = get_live_capital(kite)
            else:
                total_capital = CAPITAL
            
            allocated_capital = sum(
                Trade.from_dict(t).entry * Trade.from_dict(t).qty_remaining 
                for t in state.values()
            )
            available_capital = total_capital - allocated_capital

           # Capital reserved for pending BUY orders (CRITICAL FIX)
            pending_buy_capital = 0.0
            for oid, podata in pending_orders.items():
                po = PendingOrder.from_dict(podata)
                if po.side == "BUY":
                    # Use price if available, otherwise estimate from current price
                    order_price = po.price if po.price else 0.0
                    if order_price == 0.0:
                        # Try to get current price for estimation
                        current_price = get_live_price(po.symbol)
                        order_price = current_price if current_price else 0.0
                    
                    pending_buy_capital += order_price * po.req_qty

            available_capital = total_capital - allocated_capital - pending_buy_capital + pnl.unrealized_pnl
    

            logging.info(
                f"Capital | Total: {total_capital:.2f}, "
                f"Allocated: {allocated_capital:.2f}, "
                f"Available: {available_capital:.2f}"
                f"Available: ₹{available_capital:,.2f}"
            )
            
            logging.info(
            f"Unrealized P&L: {pnl.unrealized_pnl:+.2f} "
            f"(Realized: {pnl.realized_pnl:+.2f}, Trades: {pnl.trades_executed})"
        )

            # Safety check
            if available_capital < 0:
                logging.error(
                    f"NEGATIVE AVAILABLE CAPITAL!"
                    f"Total={total_capital:.0f}, Allocated={allocated_capital:.0f}, "
                    f"Pending={pending_buy_capital:.0f}"
                )
                available_capital = 0.0  # Prevent new trades

            # ===== STEP 6: Process new screener signals =====
            df["EXECUTED"] = "NO"
            
            for _, row in df.iterrows():
                symbol = row["SYMBOL"]
                
                # Skip if already trading
                if symbol in state:
                    logging.debug(f"{symbol} already in state, skipping")
                    continue
                
                # Skip if BUY already pending
                if is_buy_pending(symbol, pending_orders):
                    logging.debug(f"{symbol} BUY already pending, skipping")
                    continue
                
                # Check position limits
                if len(state) >= MAX_OPEN_POSITIONS:
                    logging.warning("Max open positions reached, stopping new entries")
                    break
                
                # Check sector limits
                if MAX_PER_SECTOR > 0:
                    sector_count = count_positions_by_sector(
                        state, sector_map, symbol
                    )
                    if sector_count >= MAX_PER_SECTOR:
                        logging.info(
                            f"{symbol} sector limit reached "
                            f"({sector_count}/{MAX_PER_SECTOR}), skipping"
                        )
                        continue
                
                # Calculate position size
                price = row["PRICE"]
                atr = row["ATR_PCT"] * price / 100
                
                if atr == 0:
                    logging.warning(f"{symbol} ATR is zero, skipping")
                    continue
                
                qty = calculate_qty(price, atr, available_capital)
                required_capital = qty * price
                
                # Check capital availability
                if required_capital > available_capital:
                    logging.warning(
                        f"{symbol} requires {required_capital:.2f}, "
                        f"only {available_capital:.2f} available, skipping"
                    )
                    continue
                
                # Safety check: Don't trade if stock price > 20% of capital
                if price > CAPITAL * 0.2:
                    logging.warning(
                        f"{symbol} price {price:.2f} too high "
                        f"(>20% of capital), skipping"
                    )
                    continue
                
                # Place order
                order_id = place_order(symbol, qty, "BUY")
                if not order_id:
                    logging.warning(f"Failed to place order for {symbol}, skipping")
                    continue
                
                # Verify order wasn't immediately rejected
                time.sleep(0.5)  # Brief pause
                status_check = poll_orders({order_id: pending_orders[order_id]})
                if status_check.get(order_id, ("UNKNOWN",))[0] == "REJECTED":
                    logging.error(f"{symbol} order rejected immediately")
                    continue


                available_capital -= required_capital  # Reserve capital
                # Track pending order
                sl = price - (atr * SL_ATR_MULT)
                pending_orders[order_id] = PendingOrder(
                    order_id=order_id,
                    symbol=symbol,
                    side="BUY",
                    req_qty=qty,
                    price=price,
                    atr=atr,
                    sl=sl,
                    reason=None,
                    time=datetime.now().isoformat()
                ).to_dict()
                
              
                df.loc[df["SYMBOL"] == symbol, "EXECUTED"] = "YES"
                
                logging.info(
                    f"{symbol} | BUY order placed | "
                    f"Qty={qty}, Price={price:.2f}, SL={sl:.2f}"
                )
            
            # Process immediate fills (paper mode or fast broker)
            state, pending_orders, pnl = process_pending_buys(
                state, pending_orders, pnl
            )
            
            # Transaction will auto-save on successful exit
            logging.info("Execution cycle completed successfully")
            
    except StateLockError as e:
        logging.error(f"State lock error: {e}")
        logging.error("Another instance may be running. Exiting.")
        return
    except Exception as e:
        logging.critical(f"CRITICAL ERROR in execution cycle: {e}", exc_info=True)
        raise


def verify_connection() -> bool:
    """Check if we can reach broker API"""
    try:
        if kite:
            kite.profile()  # Simple API call
        return True
    except:
        return False



# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    try:
        logging.info("=" * 60)
        logging.info(f"Starting execution cycle | Mode: {MODE}")
        
        logging.info("Loading state for reconciliation...")
        state = load_state()
        reconciled_state = reconcile_with_broker(state, kite)
        save_state(reconciled_state)
        logging.info("State reconciled with broker positions")
        
        logging.info("=" * 60)
        
        run_execution()
        
    except KeyboardInterrupt:
        logging.info("Execution interrupted by user")
    except Exception as e:
        logging.critical(f"Fatal error: {e}", exc_info=True)