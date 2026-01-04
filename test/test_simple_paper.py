"""
SIMPLE PAPER TRADING TEST
========================
Quick test based on old execution_engine.py paper mode functionality.
Tests core paper trading functions without complex setup.

This recreates the paper trading logic from the old execution_engine.py
"""

import json
import os
import time
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Any
import yfinance as yf

# ==============================
# RECREATE OLD PAPER TRADING LOGIC
# ==============================

@dataclass
class Trade:
    """Represents a single trade (from old execution_engine.py)"""
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
    realized_pnl: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Trade':
        return cls(**data)

@dataclass
class PendingOrder:
    """Represents a pending order (from old execution_engine.py)"""
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
    
    @classmethod
    def from_dict(cls, data: dict) -> 'PendingOrder':
        return cls(**data)

@dataclass
class DailyPnL:
    """Daily P&L tracker (from old execution_engine.py)"""
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
        return (self.total_pnl / self.starting_capital) * 100

# Configuration (from old execution_engine.py)
MODE = "PAPER"
CAPITAL = 50000
RISK_PER_TRADE = 0.01
SL_ATR_MULT = 1.5
TARGET_ATR_MULT = 2.0
PARTIAL_EXIT_RATIO = 0.8

# Test state files
TEST_STATE_FILE = "../json/test_paper_state.json"
TEST_PENDING_FILE = "../json/test_paper_pending.json"
TEST_PNL_FILE = "../json/test_paper_pnl.json"

# ==============================
# PAPER TRADING FUNCTIONS (from old execution_engine.py)
# ==============================

def get_live_price(symbol: str) -> Optional[float]:
    """
    Fetch live price - paper mode implementation
    (Recreated from old execution_engine.py)
    """
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        data = ticker.history(period="1d", interval="1m")
        if not data.empty:
            price = data['Close'].iloc[-1]
            print(f"  📊 {symbol}: ₹{price:.2f} (yfinance)")
            return float(price)
    except Exception as e:
        print(f"  ⚠️  Price fetch failed for {symbol}: {e}")
        # Return a mock price for testing
        mock_prices = {
            'SBIN': 500.0,
            'RELIANCE': 2500.0,
            'TCS': 3500.0,
            'INFY': 1800.0,
            'HDFCBANK': 1600.0
        }
        return mock_prices.get(symbol, 1000.0)
    
    return None

def place_order(symbol: str, qty: int, side: str, order_type: str = "MARKET", 
                price: float = 0) -> Optional[str]:
    """
    Paper mode order placement (from old execution_engine.py)
    """
    if qty <= 0:
        print(f"  ❌ Invalid quantity {qty} for {symbol}")
        return None
    
    # Paper mode simulation
    fake_order_id = f"PAPER-{symbol}-{side}-{int(time.time() * 1000)}"
    print(f"  📝 PAPER {side} {qty} {symbol} @ MARKET")
    print(f"     Order ID: {fake_order_id}")
    return fake_order_id

def poll_orders(pending_orders: dict) -> Dict[str, tuple]:
    """
    Paper mode order polling - simulate instant fills
    (From old execution_engine.py)
    """
    result = {}
    for oid, po_data in pending_orders.items():
        po = PendingOrder.from_dict(po_data)
        current_price = get_live_price(po.symbol)
        if current_price is None:
            result[oid] = ("REJECTED", 0, None)
        else:
            result[oid] = ("COMPLETE", po.req_qty, current_price)
    return result

def calculate_qty(price: float, atr: float, available_capital: float) -> int:
    """Calculate position size based on risk (from old execution_engine.py)"""
    risk_amount = CAPITAL * RISK_PER_TRADE
    sl_points = atr * SL_ATR_MULT
    
    if sl_points == 0:
        return 1
    
    risk_based_qty = int(risk_amount / sl_points)
    max_affordable_qty = int(available_capital / price) if price > 0 else 0
    
    qty = min(risk_based_qty, max_affordable_qty)
    return max(qty, 1)

# ==============================
# PAPER TRADING TEST CLASS
# ==============================

class SimplePaperTradingTest:
    """Simple paper trading test using old execution_engine.py logic"""
    
    def __init__(self):
        self.state = {}
        self.pending_orders = {}
        self.pnl = DailyPnL(
            date=datetime.now().strftime("%Y-%m-%d"),
            starting_capital=CAPITAL
        )
        
        # Clean up old test files
        for file in [TEST_STATE_FILE, TEST_PENDING_FILE, TEST_PNL_FILE]:
            if os.path.exists(file):
                os.remove(file)
    
    def save_state(self):
        """Save test state to files"""
        with open(TEST_STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)
        
        with open(TEST_PENDING_FILE, 'w') as f:
            json.dump(self.pending_orders, f, indent=2)
        
        with open(TEST_PNL_FILE, 'w') as f:
            json.dump(asdict(self.pnl), f, indent=2)
    
    def load_state(self):
        """Load test state from files"""
        if os.path.exists(TEST_STATE_FILE):
            with open(TEST_STATE_FILE, 'r') as f:
                self.state = json.load(f)
        
        if os.path.exists(TEST_PENDING_FILE):
            with open(TEST_PENDING_FILE, 'r') as f:
                self.pending_orders = json.load(f)
        
        if os.path.exists(TEST_PNL_FILE):
            with open(TEST_PNL_FILE, 'r') as f:
                data = json.load(f)
                self.pnl = DailyPnL(**data)
    
    def print_status(self):
        """Print current trading status"""
        print(f"\n💰 Capital: ₹{CAPITAL:,} | P&L: ₹{self.pnl.total_pnl:+,.2f} ({self.pnl.pnl_pct:+.2f}%)")
        print(f"📈 Positions: {len(self.state)} | Pending: {len(self.pending_orders)} | Trades: {self.pnl.trades_executed}")
        
        if self.state:
            print("   Open Positions:")
            for symbol, trade_data in self.state.items():
                trade = Trade.from_dict(trade_data)
                ltp = get_live_price(symbol) or trade.entry
                pnl = (ltp - trade.entry) * trade.qty_remaining
                print(f"     {symbol}: {trade.qty_remaining} @ ₹{trade.entry:.2f} | "
                      f"LTP: ₹{ltp:.2f} | P&L: ₹{pnl:+.2f}")
    
    def test_buy_order(self, symbol: str, atr: float = 20.0):
        """Test placing a BUY order"""
        print(f"\n🛒 Testing BUY order for {symbol}")
        
        # Get price and calculate quantity
        price = get_live_price(symbol)
        if price is None:
            print(f"  ❌ Cannot get price for {symbol}")
            return False
        
        available_capital = CAPITAL - sum(
            Trade.from_dict(t).entry * Trade.from_dict(t).qty_remaining 
            for t in self.state.values()
        )
        
        qty = calculate_qty(price, atr, available_capital)
        
        print(f"  📊 Price: ₹{price:.2f}, ATR: {atr}, Qty: {qty}")
        
        # Place order
        order_id = place_order(symbol, qty, "BUY")
        if not order_id:
            print(f"  ❌ Failed to place order")
            return False
        
        # Add to pending orders
        sl = price - (atr * SL_ATR_MULT)
        self.pending_orders[order_id] = PendingOrder(
            order_id=order_id,
            symbol=symbol,
            side="BUY",
            req_qty=qty,
            price=price,
            atr=atr,
            sl=sl,
            reason="TEST_BUY",
            time=datetime.now().isoformat()
        ).to_dict()
        
        print(f"  ✅ Order placed: {order_id}")
        return True
    
    def test_sell_order(self, symbol: str, reason: str = "TEST_SELL"):
        """Test placing a SELL order"""
        print(f"\n💸 Testing SELL order for {symbol}")
        
        if symbol not in self.state:
            print(f"  ❌ No position found for {symbol}")
            return False
        
        trade = Trade.from_dict(self.state[symbol])
        
        if trade.exit_pending:
            print(f"  ⚠️  Exit already pending for {symbol}")
            return False
        
        # Place sell order
        order_id = place_order(symbol, trade.qty_remaining, "SELL")
        if not order_id:
            print(f"  ❌ Failed to place SELL order")
            return False
        
        # Add to pending orders
        self.pending_orders[order_id] = PendingOrder(
            order_id=order_id,
            symbol=symbol,
            side="SELL",
            req_qty=trade.qty_remaining,
            price=None,
            atr=None,
            sl=None,
            reason=reason,
            time=datetime.now().isoformat()
        ).to_dict()
        
        # Mark trade as exit pending
        trade.exit_pending = True
        self.state[symbol] = trade.to_dict()
        
        print(f"  ✅ SELL order placed: {order_id}")
        return True
    
    def process_pending_orders(self):
        """Process all pending orders"""
        print(f"\n⏳ Processing {len(self.pending_orders)} pending orders...")
        
        updates = poll_orders(self.pending_orders)
        
        for order_id, (status, filled_qty, avg_price) in updates.items():
            po_data = self.pending_orders.get(order_id)
            if not po_data:
                continue
            
            po = PendingOrder.from_dict(po_data)
            
            print(f"  📋 {po.symbol} {po.side}: {status}")
            
            if status == "COMPLETE" and filled_qty > 0:
                if po.side == "BUY":
                    # Create new trade
                    trade = Trade(
                        symbol=po.symbol,
                        side="BUY",
                        entry=avg_price,
                        sl=po.sl or (avg_price - ((po.atr or 20.0) * SL_ATR_MULT)),
                        qty=filled_qty,
                        qty_remaining=filled_qty,
                        atr=po.atr or 20.0,
                        entry_time=datetime.now().isoformat(),
                        realized_pnl=0.0
                    )
                    self.state[po.symbol] = trade.to_dict()
                    self.pnl.trades_executed += 1
                    
                    print(f"     ✅ Position created: {filled_qty} @ ₹{avg_price:.2f}")
                
                elif po.side == "SELL":
                    # Close trade
                    if po.symbol in self.state:
                        trade = Trade.from_dict(self.state[po.symbol])
                        pnl_per_share = avg_price - trade.entry
                        realized_pnl = pnl_per_share * filled_qty
                        
                        self.pnl.realized_pnl += realized_pnl
                        
                        trade.qty_remaining -= filled_qty
                        trade.realized_pnl += realized_pnl
                        
                        if trade.qty_remaining <= 0:
                            del self.state[po.symbol]
                            print(f"     ✅ Position closed: P&L ₹{realized_pnl:+.2f}")
                        else:
                            self.state[po.symbol] = trade.to_dict()
                            print(f"     ✅ Partial exit: P&L ₹{realized_pnl:+.2f}")
                
                del self.pending_orders[order_id]
            
            elif status in ("REJECTED", "CANCELLED"):
                print(f"     ❌ Order {status}")
                del self.pending_orders[order_id]
    
    def run_simple_test(self):
        """Run a simple paper trading test"""
        print("=" * 60)
        print("🧪 SIMPLE PAPER TRADING TEST")
        print("=" * 60)
        print("Based on old execution_engine.py paper mode logic")
        
        # Test sequence
        test_symbols = ['SBIN', 'RELIANCE']
        
        for symbol in test_symbols:
            self.print_status()
            
            # Test buy order
            success = self.test_buy_order(symbol, atr=25.0)
            if not success:
                continue
            
            # Process the buy order
            self.process_pending_orders()
            
            # Save state
            self.save_state()
            
            # Wait a moment
            time.sleep(1)
        
        # Show positions
        self.print_status()
        
        # Test selling one position
        if self.state:
            symbol_to_sell = list(self.state.keys())[0]
            self.test_sell_order(symbol_to_sell, "TEST_EXIT")
            self.process_pending_orders()
        
        # Final status
        self.print_status()
        
        print(f"\n✅ Simple paper trading test completed!")
        print(f"📁 Test files: {TEST_STATE_FILE}, {TEST_PENDING_FILE}, {TEST_PNL_FILE}")
        
        return True


def main():
    """Run simple paper trading test"""
    print("🚀 Starting Simple Paper Trading Test...")
    print("This recreates the paper trading logic from old execution_engine.py")
    
    try:
        tester = SimplePaperTradingTest()
        tester.run_simple_test()
        
        print(f"\n🎉 Test completed successfully!")
        print(f"💡 Check the generated JSON files to see state management")
        
    except KeyboardInterrupt:
        print(f"\n⏹️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()