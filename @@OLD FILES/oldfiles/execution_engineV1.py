"""
EXECUTION ENGINE
----------------
Reads SCREENER_OUTPUT from Excel
Supports:
- Paper Trading
- Zerodha Live Trading
- ATR-based position sizing
- Daily loss kill-switch
- Sector-based position limits
- Persistent pending order tracking
"""

import pandas as pd
import logging
from datetime import datetime
import math
import os
from typing import Optional, Any, Dict, Tuple
from dataclasses import dataclass, asdict

from state_manager import (
    load_state, 
    save_state, 
    load_pending_orders,
    save_pending_orders,
    add_trade, 
    remove_trade
)
from trade_managerV1 import (
    update_trailing_sl, 
    reduce_quantity, 
    validate_quantity
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

MODE = "PAPER"        # PAPER | LIVE
CAPITAL = 25000   # Total capital
RISK_PER_TRADE = 0.005  # 0.5% per trade
MAX_DAILY_LOSS = 0.02   # 2% kill-switch
MAX_OPEN_POSITIONS = 5   # Max concurrent open positions
MAX_PER_SECTOR = 2

# ==============================
# TRADING PARAMETERS (Magic Numbers)
# ==============================
ATR_PERIOD = 14
SL_ATR_MULT = 1.5  # StopLoss multiplier
TARGET_ATR_MULT = 2.0  # Target multiplier
PARTIAL_EXIT_RATIO = 0.8  # Exit at +0.8R
PARTIAL_EXIT_QTY_PCT = 0.5  # Exit 50% of position
TRAILING_SL_ATR_MULT = 1.5  # Trailing SL uses same as initial SL
BROKER = "ZERODHA"
ORDER_TIMEOUT_SECONDS = 300  # 5 minutes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler()]
)


# ==============================
# DATA MODELS
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
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @staticmethod
    def from_dict(data: dict) -> 'Trade':
        """Create Trade from dictionary (handles dict or dataclass conversion)"""
        if isinstance(data, Trade):
            return data
        # Handle both old dict format and new format
        symbol = data.get("symbol") or data.get("SYMBOL") or ""
        side = data.get("side") or data.get("SIDE") or ""
        entry = data.get("entry") or data.get("ENTRY") or 0.0
        sl = data.get("sl") or data.get("SL") or 0.0
        qty = data.get("qty") or data.get("QTY") or 0
        qty_remaining = data.get("qty_remaining") or data.get("QTY_REMAINING") or 0
        atr = data.get("atr") or data.get("ATR") or 0.0
        exit_pending = data.get("exit_pending") or data.get("EXIT_PENDING", False)
        
        return Trade(
            symbol=symbol,
            side=side,
            entry=entry,
            sl=sl,
            qty=qty,
            qty_remaining=qty_remaining,
            atr=atr,
            partial_done=data.get("partial_done") or data.get("PARTIAL_DONE", False),
            trailing_active=data.get("trailing_active") or data.get("TRAILING_ACTIVE", False),
            entry_time=data.get("entry_time") or data.get("ENTRY_TIME"),
            exit_pending=exit_pending
        )


@dataclass
class PendingOrder:
    """Represents an order awaiting execution"""
    order_id: str
    symbol: str
    side: str  # BUY or SELL
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
            order_id=data.get("order_id") or "",
            symbol=data.get("symbol") or "",
            side=data.get("side") or "",
            req_qty=data.get("req_qty") or 0,
            price=data.get("price"),
            atr=data.get("atr"),
            sl=data.get("sl"),
            reason=data.get("reason"),
            time=data.get("time")
            
        )


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
        return kite
    except Exception as e:
        logging.error(f"Failed to initialize Kite: {e}")
        return None

kite: Optional[Any] = init_kite() if MODE == "LIVE" else None


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


def get_total_capital(state: dict) -> float:
    """Get total available capital based on mode"""
    if MODE == "PAPER":
        return CAPITAL
    if MODE == "LIVE":
        return get_live_capital(kite)
    return CAPITAL


def get_allocated_capital(state: dict) -> float:
    """Calculate capital currently allocated to open positions"""
    allocated = 0.0
    for symbol, trade_dict in state.items():
        trade = Trade.from_dict(trade_dict)
        allocated += trade.entry * trade.qty_remaining
    return allocated


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


def load_sector_map() -> dict:
    """Load sector map from Excel"""
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name=SECTOR_SHEET)
        return dict(zip(df["SYMBOL"], df["SECTOR"]))
    except Exception as e:
        logging.warning(f"Failed to load sector map: {e}")
        return {}


# ==============================
# POSITION SIZING
# ==============================
def calculate_qty(price: float, atr: float) -> int:
    """Calculate position size based on risk per trade"""
    risk_amount = CAPITAL * RISK_PER_TRADE
    sl_points = atr * SL_ATR_MULT
    qty = math.floor(risk_amount / sl_points)
    return max(qty, 1)


# ==============================
# ORDER EXECUTION
# ==============================
def place_order(symbol: str, qty: int, side: str) -> Optional[str]:
    """
    Place an order (BUY or SELL).
    Returns order ID on success, None on failure.
    """
    if MODE == "PAPER":
        fake_order_id = f"PAPER-{symbol}-{datetime.now().timestamp()}"
        logging.info(f"[PAPER] {side} {qty} {symbol}")
        return fake_order_id

    if kite is None:
        logging.error("Kite connection not initialized")
        return None

    try:
        order_id = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange=kite.EXCHANGE_NSE,
            tradingsymbol=symbol,
            transaction_type=(
                kite.TRANSACTION_TYPE_BUY
                if side == "BUY"
                else kite.TRANSACTION_TYPE_SELL
            ),
            quantity=qty,
            product=kite.PRODUCT_MIS,
            order_type=kite.ORDER_TYPE_MARKET
        )
        logging.info(f"Order placed: {side} {qty} {symbol} | Order ID: {order_id}")
        return order_id
    except Exception as e:
        logging.error(f"Order failed: {symbol} | {e}")
        return None


def get_live_price(symbol: str) -> Optional[float]:
    """
    Fetch live price for a symbol.
    Returns None if unavailable (e.g., in paper mode or if fetch fails).
    """
    if MODE == "PAPER":
        return None
    
    if kite is None:
        return None
    
    try:
        quote = kite.quote(f"NSE:{symbol}")
        return quote[f"NSE:{symbol}"]["last_price"]
    except Exception as e:
        logging.warning(f"Failed to fetch price for {symbol}: {e}")
        return None


def initiate_sell(symbol: str, qty: int, reason: str, pending_orders: dict) -> bool:
    """
    Places SELL order and tracks it.
    Does NOT modify state.
    """
    if Trade.from_dict(pending_orders.get(symbol, {})).exit_pending:
        logging.info(f"{symbol} | SELL already pending, skipping")
        return False
    order_id = place_order(symbol, qty, "SELL")

    if not order_id:
        logging.error(f"{symbol} | SELL failed to place ({reason})")
        return False

    pending_orders[order_id] = {
        "order_id": order_id,
        "symbol": symbol,
        "side": "SELL",
        "req_qty": qty,
        "price": None,
        "atr": None,
        "sl": None,
        "reason": reason,
        "time": datetime.now().isoformat()
    }

    logging.info(f"{symbol} | SELL placed | Qty={qty} | Reason={reason}")
    return True


def is_buy_pending(symbol: str, pending_orders: dict) -> bool:
    """Check if a BUY order is already pending for this symbol"""
    for po in pending_orders.values():
        po_dict = po if isinstance(po, dict) else po.to_dict()
        if po_dict.get("side") == "BUY" and po_dict.get("symbol") == symbol:
            return True
    return False


# ==============================
# ORDER STATUS CHECKER
# ==============================
def poll_orders(pending_orders: dict) -> Dict[str, Tuple[str, int]]:
    """
    Poll broker for order updates.
    Returns dict of {order_id: (status, filled_qty)}
    """
    if MODE == "PAPER":
        # In paper mode, assume instant fills
        return {oid: ("COMPLETE", po["req_qty"]) 
                for oid, po in pending_orders.items()}

    if kite is None:
        return {}
    
    try:
        broker_orders = kite.orders()
        result = {}
        for o in broker_orders:
            oid = o["order_id"]
            if oid in pending_orders:
                result[oid] = (o["status"], o["filled_quantity"])
        return result
    except Exception as e:
        logging.error(f"Failed to poll orders: {e}")
        return {}


# ==============================
# ORDER PROCESSING
# ==============================
exit_price = 10.0  # Replace with the actual value of the exit price
def process_pending_sells(state: dict, pending_orders: dict) -> Tuple[dict, dict]:
    """
    Process completed/rejected SELL orders.
    Updates state and removes processed orders.
    """
    updates = poll_orders(pending_orders)

    for order_id, (status, filled_qty) in updates.items():
        po = pending_orders.get(order_id)
        if not po:
            continue
        
        po_dict = po if isinstance(po, dict) else po.to_dict()
        if po_dict.get("side") != "SELL":
            continue

        symbol = po_dict.get("symbol")

        if status == "COMPLETE" and filled_qty > 0:
            trade_dict = state.get(symbol)
            available_capital += filled_qty * exit_price
            if not trade_dict:
                del pending_orders[order_id]
                continue

            trade = Trade.from_dict(trade_dict)
            trade.qty_remaining -= min(filled_qty, trade.qty_remaining)

            if trade.qty_remaining <= 0:
                logging.info(f"{symbol} | EXIT CONFIRMED")
                del state[symbol]
            else:
                trade.exit_pending = False
                state[symbol] = trade.to_dict()
                logging.info(
                    f"{symbol} | PARTIAL SELL CONFIRMED | "
                    f"Filled={filled_qty}, Remaining={trade.qty_remaining}"
                )
            trade.exit_pending = False
            del pending_orders[order_id]

        elif status in ("REJECTED", "CANCELLED"):
            logging.error(f"{symbol} | SELL {status}")
            del pending_orders[order_id]

    return state, pending_orders


def process_pending_buys(state: dict, pending_orders: dict, available_capital: float) -> Tuple[dict, dict, float]:
    """
    Process completed/rejected BUY orders.
    Updates state with new trades and removes processed orders.
    """
    updates = poll_orders(pending_orders)

    for oid, (status, filled_qty) in updates.items():
        po = pending_orders.get(oid)
        if not po:
            continue
        
        po_dict = po if isinstance(po, dict) else po.to_dict()
        if po_dict.get("side") != "BUY":
            continue

        symbol = po_dict.get("symbol")

        if status == "COMPLETE" and filled_qty > 0:
            if not symbol:
                logging.warning(f"BUY order {oid} has no symbol, skipping")
                continue
                
            trade = Trade(
                symbol=symbol,
                side="BUY",
                entry=po_dict.get("price") or 0.0,
                sl=po_dict.get("sl") or 0.0,
                qty=filled_qty,
                qty_remaining=filled_qty,
                atr=po_dict.get("atr") or 0.0,
                partial_done=False,
                trailing_active=False,
                entry_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            state[symbol] = trade.to_dict()
            price = po_dict.get("price") or 0.0
            available_capital -= filled_qty * price
            del pending_orders[oid]

        elif status in ("REJECTED", "CANCELLED"):
            logging.warning(f"{symbol} | BUY order {status}")
            del pending_orders[oid]

    return state, pending_orders, available_capital


def cleanup_stale_orders(pending_orders: dict) -> dict:
    """Remove orders that have timed out"""
    current_time = datetime.now()
    stale_orders = []
    
    for oid, po in pending_orders.items():
        po_dict = po if isinstance(po, dict) else po.to_dict()
        time_str = po_dict.get("time")
        
        if time_str:
            try:
                order_time = datetime.fromisoformat(time_str)
                if (current_time - order_time).total_seconds() > ORDER_TIMEOUT_SECONDS:
                    stale_orders.append(oid)
            except Exception:
                pass
    
    for oid in stale_orders:
        logging.warning(f"Order {oid} timeout, removing from pending")
        del pending_orders[oid]
    
    return pending_orders


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

        return reconciled
    except Exception as e:
        logging.error(f"Reconciliation failed: {e}")
        return state


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


        # Get live price (fallback to entry if unavailable)
        ltp = get_live_price(symbol)
        if ltp is None:
            ltp = trade.entry
        
        # Check for partial exit at +0.8R
        r_value = abs(trade.entry - trade.sl)
        if not trade.partial_done and trade.side == "BUY":
            if ltp >= trade.entry + (PARTIAL_EXIT_RATIO * r_value):
                exit_qty = max(1, int(trade.qty_remaining * PARTIAL_EXIT_QTY_PCT))
                if exit_qty >= trade.qty_remaining or exit_qty <= 0:
                    continue  # Skip if nothing to exit
                    
                trade.partial_done = True
                sells_to_execute[symbol] = (exit_qty, "PARTIAL_EXIT")
                logging.info(f"{symbol} | Partial exit triggered at {ltp:.2f}")
        
        # Update trailing SL after partial exit
        if trade.partial_done and trade.side == "BUY":
            new_sl = ltp - (TRAILING_SL_ATR_MULT * trade.atr)
            if new_sl > trade.sl:
                trade.sl = new_sl
                trade.trailing_active = True
                logging.info(f"{symbol} | Trailing SL updated to {trade.sl:.2f}")
        
        # Check for stop loss hit
        if trade.side == "BUY" and ltp <= trade.sl and not trade.exit_pending:
            trade.exit_pending = True
            sells_to_execute[symbol] = (trade.qty_remaining, "STOP_LOSS")
            logging.info(f"{symbol} | Stop loss hit at {ltp:.2f}")
            continue
        
        state[symbol] = trade.to_dict()
    
    return state, sells_to_execute


# ==============================
# EXECUTION LOOP
# ==============================
def run_execution():
    """Main execution cycle"""
    
    # Load Excel screener output
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET)
        required_cols = ["SYMBOL", "PRICE", "ATR_PCT", "ELIGIBLE"]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            logging.error(f"Missing columns in Excel: {missing}")
            return
    except Exception as e:
        logging.error(f"Failed to read Excel file: {e}")
        return

    # Filter eligible stocks and remove duplicates
    df = df[df["ELIGIBLE"] == "YES"].copy()
    df = df.drop_duplicates(subset=["SYMBOL"], keep="first")
    if df.empty:
        logging.warning("No eligible stocks to trade")
        return

    # Load state
    state = load_state()
    pending_orders = load_pending_orders()
    sector_map = load_sector_map()

    total_capital = get_total_capital(state)
    allocated_capital = get_allocated_capital(state)
    available_capital = total_capital - allocated_capital

    logging.info(
        f"Capital | Total: {total_capital:.2f}, "
        f"Allocated: {allocated_capital:.2f}, "
        f"Available: {available_capital:.2f}"
    )
    logging.info(f"Open positions: {len(state)}, Pending orders: {len(pending_orders)}")

    # ===== STEP 1: Process existing open trades =====
    state, sells_to_execute = process_existing_trades(state, sector_map)
    
    # Initiate all sell orders
    for symbol, (qty, reason) in sells_to_execute.items():
        trade = Trade.from_dict(state.get(symbol, {}))
        trade.exit_pending = True
        state[symbol] = trade.to_dict()
        initiate_sell(symbol, qty, reason, pending_orders)

    # ===== STEP 2: Process pending orders (all at once) =====
    state, pending_orders = process_pending_sells(state, pending_orders)
    state, pending_orders, available_capital = process_pending_buys(state, pending_orders, available_capital)

    # ===== STEP 3: Cleanup stale orders =====
    pending_orders = cleanup_stale_orders(pending_orders)

    # ===== STEP 4: Process new screener signals =====
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

        # Skip if sector limit reached
        if MAX_PER_SECTOR > 0:
            sector_count = count_positions_by_sector(state, sector_map, symbol)
            if sector_count >= MAX_PER_SECTOR:
                logging.info(f"{symbol} sector limit reached ({sector_count}/{MAX_PER_SECTOR}), skipping")
                continue

        # Check position limits
        if len(state) >= MAX_OPEN_POSITIONS:
            logging.warning("Max open positions reached, stopping new entries")
            break

        # Calculate position size
        price = row["PRICE"]
        atr = row["ATR_PCT"] * price / 100
        qty = calculate_qty(price, atr)

        # Check capital availability
        max_affordable_qty = int(available_capital / price) if price > 0 else 0
        if max_affordable_qty <= 0:
            logging.warning("No available capital left, stopping entries")
            break

        qty = min(qty, max_affordable_qty)
        required_capital = qty * price

        # Place order
        order_id = place_order(symbol, qty, "BUY")
        if not order_id:
            logging.warning(f"Failed to place order for {symbol}, skipping")
            continue

        # Track pending order
        pending_orders[order_id] = {
            "order_id": order_id,
            "symbol": symbol,
            "side": "BUY",
            "req_qty": qty,
            "price": price,
            "atr": atr,
            "sl": price - (atr * SL_ATR_MULT),
            "reason": None,
            "time": datetime.now().isoformat()
        }

        df.loc[df["SYMBOL"] == symbol, "EXECUTED"] = "YES"
        logging.info(f"{symbol} | BUY order placed | Qty={qty} | Price={price:.2f}")

    state, pending_orders, available_capital = process_pending_buys(state, pending_orders, available_capital)
    # ===== SAVE STATE =====
    save_state(state)
    save_pending_orders(pending_orders)

    # Write execution log
    try:
        with pd.ExcelWriter(EXCEL_FILE, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            df.to_excel(writer, sheet_name="EXECUTION_LOG", index=False)
    except Exception as e:
        logging.error(f"Failed to write execution log: {e}")

    logging.info("Execution cycle completed")


# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    if MODE == "LIVE":
        logging.info("Loading state for reconciliation...")
        state = load_state()
        reconciled_state = reconcile_with_broker(state, kite)
        save_state(reconciled_state)
        logging.info("State reconciled with broker positions")
    
    run_execution()
