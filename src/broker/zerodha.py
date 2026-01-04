"""
Zerodha Broker Integration
==========================
KiteConnect API wrapper supporting both PAPER and LIVE trading.

Features:
- Unified interface for PAPER and LIVE modes
- Automatic flag-based switching
- Rate limiting (Zerodha: 10 req/sec)
- Order placement with retry logic
- Position tracking and reconciliation
- Real-time price updates
- Error handling and recovery
"""

import logging
import os
import time
from typing import Dict, Optional, List, Tuple, Any
from datetime import datetime, timedelta
from enum import Enum
import yfinance as yf

import dotenv
logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Zerodha order status mapping"""
    PENDING = "PENDING"
    OPEN = "OPEN"
    COMPLETE = "COMPLETE"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    TRIGGER_PENDING = "TRIGGER_PENDING"


class OrderType(Enum):
    """Order types supported by Zerodha"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"


class TransactionType(Enum):
    """Buy/Sell"""
    BUY = "BUY"
    SELL = "SELL"


class Product(Enum):
    """Product types (MIS=Intraday, CNC=Delivery, NRML=Normal)"""
    MIS = "MIS"  # Intraday (most liquid, squareoff at close)
    CNC = "CNC"  # Delivery
    NRML = "NRML"  # Normal (margin)


# ==============================
# RATE LIMITER
# ==============================
class RateLimiter:
    """Enforce Zerodha's 10 req/sec rate limit"""
    
    def __init__(self, max_calls: int = 10, time_window: float = 1.0):
        self.max_calls = max_calls
        self.time_window = time_window
        self.call_times: List[float] = []
    
    def wait_if_needed(self):
        """Wait if rate limit would be exceeded"""
        now = time.time()
        # Remove calls older than time_window
        self.call_times = [t for t in self.call_times if now - t < self.time_window]
        
        if len(self.call_times) >= self.max_calls:
            sleep_time = self.time_window - (now - self.call_times[0])
            if sleep_time > 0:
                logger.debug(f"Rate limit: sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)
        
        self.call_times.append(time.time())


# ==============================
# ZERODHA BROKER CLASS
# ==============================
class ZerodhaBroker:
    """
    Unified Zerodha broker interface for PAPER and LIVE trading.
    
    Usage:
        broker = ZerodhaBroker(mode="PAPER")  # or "LIVE"
        broker.connect()
        order_id = broker.place_order(symbol, qty, side="BUY")
        status, filled_qty = broker.get_order_status(order_id)
    """
    
    def __init__(self, mode: str = "PAPER"):
        """
        Initialize broker.
        
        Args:
            mode: "PAPER" or "LIVE"
        """
        self.mode = mode.upper()
        
        if self.mode not in ["PAPER", "LIVE"]:
            raise ValueError(f"Invalid mode: {mode}. Use 'PAPER' or 'LIVE'")
        
        self.is_connected = False
        self.kite = None
        self.rate_limiter = RateLimiter()
        
        # For paper trading: simulated data
        self.paper_positions: Dict[str, Dict] = {}
        self.paper_orders: Dict[str, Dict] = {}
        self.price_cache: Dict[str, float] = {}
        self.last_price_update: Dict[str, datetime] = {}
        
        logger.info(f"ZerodhaBroker initialized in {self.mode} mode")
    
    def connect(self) -> Tuple[bool, str]:
        """
        Connect to broker.
        
        PAPER mode: Always succeeds (no real connection)
        LIVE mode: Connects via KiteConnect API
        
        Returns:
            (success, message)
        """
        if self.mode == "PAPER":
            self.is_connected = True
            logger.info("Paper trading: No real connection required")
            return True, "Paper mode connected"
        
        # LIVE mode: Connect to Zerodha
        try:
            from kiteconnect import KiteConnect
        except ImportError:
            return False, "kiteconnect not installed. Run: pip install kiteconnect"
        
        try:
            # Load .env variables
            dotenv.load_dotenv()

            api_key = os.getenv("KITE_API_KEY")
            access_token = os.getenv("KITE_ACCESS_TOKEN")
            
            if not api_key or not access_token:
                return False, "KITE_API_KEY or KITE_ACCESS_TOKEN not set in .env"
            
            # Initialize KiteConnect
            self.kite = KiteConnect(api_key=api_key)
            self.kite.set_access_token(access_token)
            
            # Test connection
            self.rate_limiter.wait_if_needed()
            profile = self.kite.profile()
            
            if isinstance(profile, dict):
                user_name = profile.get('user_name', 'Unknown')
                logger.info(f"✓ Zerodha connected: {user_name}")
            
            self.is_connected = True
            return True, f"Connected to Zerodha: {user_name}"
        
        except Exception as e:
            logger.error(f"Failed to connect to Zerodha: {e}")
            self.is_connected = False
            return False, str(e)
    
    def disconnect(self):
        """Disconnect from broker"""
        self.is_connected = False
        self.kite = None
        logger.info("Disconnected from broker")
    
    # ==============================
    # PRICE UTILITIES
    # ==============================
    
    def _round_to_tick(self, price: float, tick_size: float = 0.05) -> float:
        """
        Round price to the nearest tick size.
        Zerodha requires prices to be multiples of 0.05 for NSE stocks.
        
        Args:
            price: Price to round
            tick_size: Tick size (default 0.05 for NSE)
        
        Returns:
            Rounded price
        """
        if price <= 0:
            return price
        
        # Round to nearest tick
        rounded = round(price / tick_size) * tick_size
        
        # Ensure we don't lose precision due to float arithmetic
        return round(rounded, 2)
    
    # ==============================
    # PRICE FETCHING
    # ==============================
    
    def get_live_price(self, symbol: str, use_cache: bool = True) -> Optional[float]:
        """
        Get current market price for a symbol.
        
        PAPER mode: Fetches from yfinance
        LIVE mode: Fetches from Zerodha
        
        Args:
            symbol: Stock symbol (e.g., "RELIANCE", "TCS")
            use_cache: Use cached price if recent
        
        Returns:
            Price (float) or None if failed
        """
        # Check cache (valid for 5 seconds)
        if use_cache:
            last_update = self.last_price_update.get(symbol)
            if last_update and (datetime.now() - last_update).total_seconds() < 5:
                return self.price_cache.get(symbol)
        
        if self.mode == "PAPER":
            return self._fetch_paper_price(symbol)
        else:
            return self._fetch_live_price(symbol)
    
    def _fetch_paper_price(self, symbol: str) -> Optional[float]:
        """Fetch price from yfinance for paper trading"""
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            data = ticker.history(period="1d", interval="1m")
            
            if data.empty:
                logger.warning(f"No price data for {symbol}")
                return None
            
            price = float(data['Close'].iloc[-1])
            self.price_cache[symbol] = price
            self.last_price_update[symbol] = datetime.now()
            
            return price
        
        except Exception as e:
            logger.warning(f"Failed to fetch paper price for {symbol}: {e}")
            return None
    
    def _fetch_live_price(self, symbol: str) -> Optional[float]:
        """Fetch price from Zerodha for live trading"""
        if not self.is_connected or self.kite is None:
            logger.warning("Not connected to Zerodha")
            return None
        
        try:
            self.rate_limiter.wait_if_needed()
            quote = self.kite.quote(f"NSE:{symbol}")

            if not quote:
                logger.warning(f"No quote data for {symbol}")
                return None

            # Zerodha's quote can come in different shapes:
            # - {'NSE:SYMBOL': {...}} (common)
            # - a flat dict containing price fields
            # - sometimes nested differently depending on client/version
            price = None

            if isinstance(quote, dict):
                key = f"NSE:{symbol}"

                # Prefer the keyed entry if present
                entry = quote.get(key)
                if entry is None:
                    # Fall back to the first dict-like value
                    dict_values = [v for v in quote.values() if isinstance(v, dict)]
                    entry = dict_values[0] if dict_values else quote

                # Try common field names used by various clients
                for field in ("last_price", "last_traded_price", "ltp", "lastPrice", "last"):
                    try:
                        if isinstance(entry, dict) and field in entry and entry[field] is not None:
                            price = entry[field]
                            break
                    except Exception:
                        continue

                # If the entry itself is a numeric price
                if price is None and isinstance(entry, (int, float)):
                    price = entry

            else:
                # Non-dict responses: try attribute access
                price = getattr(quote, "last_price", None)

            if price is None:
                logger.debug(f"Quote structure for {symbol}: {quote}")
                logger.warning(f"Price not found in quote for {symbol}")
                return None

            try:
                price_float = float(price)
            except Exception:
                logger.warning(f"Invalid price value in quote for {symbol}: {price}")
                return None

            self.price_cache[symbol] = price_float
            self.last_price_update[symbol] = datetime.now()

            return price_float
        
        except Exception as e:
            logger.warning(f"Failed to fetch live price for {symbol}: {e}")
            return None
    
    # ==============================
    # ORDER PLACEMENT
    # ==============================
    
    def place_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "MARKET",
        price: float = 0.0,
        max_retries: int = 3
    ) -> Optional[str]:
        """
        Place an order.
        
        Args:
            symbol: Stock symbol
            qty: Quantity to trade
            side: "BUY" or "SELL"
            order_type: "MARKET" or "LIMIT"
            price: Required for LIMIT orders (will be rounded to tick size)
            max_retries: Number of retry attempts
        
        Returns:
            Order ID on success, None on failure
        """
        if not self.is_connected:
            logger.error("Broker not connected")
            return None
        
        if qty <= 0:
            logger.error(f"Invalid quantity: {qty}")
            return None
        
        # Round price to broker's tick size (0.05 for NSE)
        if price > 0:
            price = self._round_to_tick(price)
        
        if self.mode == "PAPER":
            return self._place_paper_order(symbol, qty, side, order_type, price)
        else:
            return self._place_live_order(symbol, qty, side, order_type, price, max_retries)
    
    def _place_paper_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str,
        price: float
    ) -> Optional[str]:
        """Simulate order placement for paper trading"""
        try:
            # Get current price
            current_price = self.get_live_price(symbol)
            if current_price is None:
                current_price = price if price > 0 else 100.0
            
            # Create fake order ID
            order_id = f"PAPER-{symbol}-{side}-{int(time.time() * 1000)}"
            
            # Simulate order
            self.paper_orders[order_id] = {
                "symbol": symbol,
                "qty": qty,
                "side": side,
                "order_type": order_type,
                "price": price if price > 0 else current_price,
                "current_price": current_price,
                "status": "PENDING",
                "filled_qty": 0,
                "placed_at": datetime.now().isoformat(),
                "filled_at": None
            }
            
            logger.info(
                f"PAPER {side:4} {qty:3} {symbol:8} @ ₹{current_price:.2f} | "
                f"Order: {order_id}"
            )
            
            return order_id
        
        except Exception as e:
            logger.error(f"Paper order placement failed: {e}")
            return None
    
    def _place_live_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str,
        price: float,
        max_retries: int
    ) -> Optional[str]:
        """Place real order with Zerodha"""
        if self.kite is None:
            logger.error("Kite not initialized")
            return None
        
        for attempt in range(max_retries):
            try:
                self.rate_limiter.wait_if_needed()
                
                order_params = {
                    "variety": self.kite.VARIETY_REGULAR,
                    "exchange": self.kite.EXCHANGE_NSE,
                    "tradingsymbol": symbol,
                    "transaction_type": (
                        self.kite.TRANSACTION_TYPE_BUY
                        if side == "BUY"
                        else self.kite.TRANSACTION_TYPE_SELL
                    ),
                    "quantity": qty,
                    "product": self.kite.PRODUCT_MIS,  # Intraday
                    "order_type": (
                        self.kite.ORDER_TYPE_MARKET
                        if order_type == "MARKET"
                        else self.kite.ORDER_TYPE_LIMIT
                    )
                }
                
                if order_type == "LIMIT" and price > 0:
                    order_params["price"] = price
                
                order_id = self.kite.place_order(**order_params)
                
                logger.info(
                    f"LIVE {side:4} {qty:3} {symbol:8} @ ₹{price:.2f} | "
                    f"Order: {order_id}"
                )
                
                return str(order_id)
            
            except Exception as e:
                error_msg = str(e).lower()
                
                # Don't retry on these errors
                if any(x in error_msg for x in [
                    "insufficient", "rejected", "invalid symbol", "disabled"
                ]):
                    logger.error(f"Order rejected: {e}")
                    return None
                
                # Retry on network/timeout errors
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(
                        f"Order attempt {attempt+1} failed: {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Order failed after {max_retries} attempts")
                    return None
        
        return None
    
    # ==============================
    # ORDER STATUS & TRACKING
    # ==============================
    
    def get_order_status(self, order_id: str) -> Tuple[str, int, Optional[float]]:
        """
        Get order status.
        
        Args:
            order_id: Order ID
        
        Returns:
            (status, filled_qty, avg_price)
        """
        if self.mode == "PAPER":
            return self._get_paper_order_status(order_id)
        else:
            return self._get_live_order_status(order_id)
    
    def _get_paper_order_status(self, order_id: str) -> Tuple[str, int, Optional[float]]:
        """Get paper order status (instant fill simulation)"""
        if order_id not in self.paper_orders:
            return OrderStatus.REJECTED.value, 0, None
        
        order = self.paper_orders[order_id]
        
        # Simulate instant fill after placement
        if order["status"] == "PENDING":
            placed_at = datetime.fromisoformat(order["placed_at"])
            elapsed = (datetime.now() - placed_at).total_seconds()
            
            # Fill after 1 second for realism
            if elapsed > 1.0:
                order["status"] = OrderStatus.COMPLETE.value
                order["filled_qty"] = order["qty"]
                order["filled_at"] = datetime.now().isoformat()
        
        return (
            order["status"],
            order["filled_qty"],
            order["price"]
        )
    
    def _get_live_order_status(self, order_id: str) -> Tuple[str, int, Optional[float]]:
        """Get live order status from Zerodha"""
        if not self.is_connected or self.kite is None:
            return OrderStatus.REJECTED.value, 0, None
        
        try:
            self.rate_limiter.wait_if_needed()
            broker_orders = self.kite.orders()
            
            for order in broker_orders:
                if str(order["order_id"]) == str(order_id):
                    status = order.get("status", "UNKNOWN")
                    filled_qty = order.get("filled_quantity", 0)
                    avg_price = order.get("average_price", 0.0) or None
                    
                    return status, filled_qty, avg_price
            
            return OrderStatus.REJECTED.value, 0, None
        
        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            return OrderStatus.REJECTED.value, 0, None
    
    def get_open_orders(self) -> Dict[str, Dict]:
        """
        Get all open orders (pending and partially filled).
        
        Returns:
            {order_id: {symbol, qty, side, status, filled_qty, ...}}
        """
        if self.mode == "PAPER":
            return self._get_paper_open_orders()
        else:
            return self._get_live_open_orders()
    
    def _get_paper_open_orders(self) -> Dict[str, Dict]:
        """Get paper trading open orders"""
        open_orders = {}
        for order_id, order in self.paper_orders.items():
            if order["status"] in [OrderStatus.PENDING.value, OrderStatus.OPEN.value]:
                open_orders[order_id] = {
                    "order_id": order_id,
                    "symbol": order["symbol"],
                    "qty": order["qty"],
                    "side": order["side"],
                    "status": order["status"],
                    "filled_qty": order["filled_qty"],
                    "avg_price": order["price"]
                }
        return open_orders
    
    def _get_live_open_orders(self) -> Dict[str, Dict]:
        """Get live trading open orders from Zerodha"""
        if not self.is_connected or self.kite is None:
            return {}
        
        try:
            self.rate_limiter.wait_if_needed()
            broker_orders = self.kite.orders()
            
            open_orders = {}
            for order in broker_orders:
                status = order.get("status", "UNKNOWN")
                
                # Include only pending/open/partial orders
                if status in ["PENDING", "OPEN", "TRIGGER_PENDING"]:
                    order_id = str(order["order_id"])
                    open_orders[order_id] = {
                        "order_id": order_id,
                        "symbol": order.get("tradingsymbol", "UNKNOWN"),
                        "qty": order.get("quantity", 0),
                        "side": order.get("transaction_type", "UNKNOWN"),
                        "status": status,
                        "filled_qty": order.get("filled_quantity", 0),
                        "avg_price": order.get("average_price", 0.0)
                    }
            
            return open_orders
        
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return {}
    
    # ==============================
    # POSITION MANAGEMENT
    # ==============================
    
    def get_positions(self) -> Dict[str, Dict]:
        """
        Get current positions.
        
        Returns:
            {symbol: {qty, entry_price, ltp, pnl_pct, ...}}
        """
        if self.mode == "PAPER":
            return self.paper_positions.copy()
        else:
            return self._get_live_positions()
    
    def _get_live_positions(self) -> Dict[str, Dict]:
        """Fetch positions from Zerodha"""
        if not self.is_connected or self.kite is None:
            return {}
        
        try:
            self.rate_limiter.wait_if_needed()
            positions_data = self.kite.positions()
            
            if not isinstance(positions_data, dict):
                logger.warning("Invalid positions data format")
                return {}
            
            positions = {}
            for pos in positions_data.get("net", []):
                if pos["quantity"] != 0:
                    symbol = pos["tradingsymbol"]
                    positions[symbol] = {
                        "qty": pos["quantity"],
                        "avg_price": pos.get("average_price", 0.0),
                        "ltp": pos.get("last_price", 0.0),
                        "pnl": pos.get("pnl", 0.0),
                        "pnl_pct": (pos.get("pnl", 0.0) / 
                                   (pos.get("average_price", 1.0) * 
                                    abs(pos["quantity"])) * 100)
                    }
            
            return positions
        
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return {}
    
    # ==============================
    # CAPITAL MANAGEMENT
    # ==============================
    
    def get_available_capital(self, default: float = 5000.0) -> float:
        """
        Get available trading capital.
        
        PAPER mode: Returns configured default
        LIVE mode: Fetches from Zerodha
        
        Args:
            default: Default capital (used in paper mode or if fetch fails)
        
        Returns:
            Available capital (float)
        """
        if self.mode == "PAPER":
            return default
        
        if not self.is_connected or self.kite is None:
            return default
        
        try:
            self.rate_limiter.wait_if_needed()
            margins = self.kite.margins()
            
            if not isinstance(margins, dict):
                logger.warning("Invalid margins data format")
                return default
            
            available_cash = margins.get("equity", {}).get("available", {}).get("cash")
            if available_cash is None:
                return default
            
            return float(available_cash)
        
        except Exception as e:
            logger.warning(f"Failed to fetch available capital: {e}")
            return default
    
    # ==============================
    # UTILITY METHODS
    # ==============================
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel pending order"""
        if self.mode == "PAPER":
            if order_id in self.paper_orders:
                self.paper_orders[order_id]["status"] = OrderStatus.CANCELLED.value
                logger.info(f"Paper order {order_id} cancelled")
                return True
            return False
        
        if not self.is_connected or self.kite is None:
            return False
        
        try:
            self.rate_limiter.wait_if_needed()
            self.kite.cancel_order(
                variety=self.kite.VARIETY_REGULAR,
                order_id=order_id
            )
            logger.info(f"Live order {order_id} cancelled")
            return True
        
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False
    
    def get_mode(self) -> str:
        """Get current mode (PAPER or LIVE)"""
        return self.mode
    
    def is_paper_mode(self) -> bool:
        """Check if in paper trading mode"""
        return self.mode == "PAPER"
    
    def is_live_mode(self) -> bool:
        """Check if in live trading mode"""
        return self.mode == "LIVE"
