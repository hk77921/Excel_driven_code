"""
STANDALONE PAPER TRADING TEST
============================
Simple paper trading test that doesn't depend on complex imports.
Based on the old execution_engine.py paper mode functionality.

This is the most reliable way to test paper trading logic.
"""

import json
import os
import time
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Any
import yfinance as yf

# ==============================
# STANDALONE DATA MODELS
# ==============================

@dataclass
class SimpleTrade:
    """Simple trade representation"""
    symbol: str
    side: str
    entry: float
    sl: float
    qty: int
    qty_remaining: int
    atr: float
    partial_done: bool = False
    entry_time: Optional[str] = None
    exit_pending: bool = False
    realized_pnl: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SimpleTrade':
        return cls(**data)

@dataclass
class SimpleOrder:
    """Simple order representation"""
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
    def from_dict(cls, data: dict) -> 'SimpleOrder':
        return cls(**data)

@dataclass
class SimplePnL:
    """Simple P&L tracker"""
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

# ==============================
# PAPER TRADING CONFIGURATION
# ==============================

CAPITAL = 50000
RISK_PER_TRADE = 0.01  # 1%
SL_ATR_MULT = 1.5
MAX_POSITIONS = 5

# ==============================
# PAPER TRADING FUNCTIONS
# ==============================

def get_mock_price(symbol: str) -> float:
    """Get mock price (fallback when yfinance fails)"""
    mock_prices = {
        'SBIN': 500.0,
        'RELIANCE': 2500.0,
        'TCS': 3500.0,
        'INFY': 1800.0,
        'HDFCBANK': 1600.0,
        'WIPRO': 400.0,
        'LT': 3200.0,
        'HINDUNILVR': 2800.0
    }
    return mock_prices.get(symbol, 1000.0)

def get_live_price(symbol: str) -> Optional[float]:
    """Get live price from yfinance with fallback"""
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        data = ticker.history(period="1d", interval="5m")
        if not data.empty:
            price = float(data['Close'].iloc[-1])
            print(f"  📊 {symbol}: ₹{price:.2f} (live)")
            return price
    except Exception as e:
        print(f"  ⚠️  Live price failed for {symbol}, using mock: {e}")
    
    # Fallback to mock price
    price = get_mock_price(symbol)
    print(f"  📊 {symbol}: ₹{price:.2f} (mock)")
    return price

def calculate_qty(price: float, atr: float, available_capital: float) -> int:
    """Calculate position size based on risk"""
    risk_amount = CAPITAL * RISK_PER_TRADE
    sl_points = atr * SL_ATR_MULT
    
    if sl_points <= 0:
        return 1
    
    risk_based_qty = int(risk_amount / sl_points)
    max_affordable = int(available_capital / price) if price > 0 else 0
    
    qty = min(risk_based_qty, max_affordable)
    return max(qty, 1)

def place_paper_order(symbol: str, qty: int, side: str) -> str:
    """Place paper order (simulation)"""
    order_id = f"PAPER-{symbol}-{side}-{int(time.time() * 1000)}"
    print(f"  📝 PAPER {side} {qty} {symbol}")
    return order_id

def simulate_order_fill(order: SimpleOrder) -> tuple:
    """Simulate order fill - returns (status, filled_qty, avg_price)"""
    # In paper mode, orders fill instantly at current price
    current_price = get_live_price(order.symbol)
    if current_price is None:
        return "REJECTED", 0, None
    
    return "COMPLETE", order.req_qty, current_price

# ==============================
# PAPER TRADER CLASS
# ==============================

class StandalonePaperTrader:
    """Standalone paper trader - no complex dependencies"""
    
    def __init__(self):
        self.state = {}  # Open positions
        self.pending_orders = {}  # Pending orders
        self.pnl = SimplePnL(
            date=datetime.now().strftime("%Y-%m-%d"),
            starting_capital=CAPITAL
        )
        
        print("🚀 Standalone Paper Trader Initialized")
        print(f"   Capital: ₹{CAPITAL:,}")
        print(f"   Risk per trade: {RISK_PER_TRADE*100:.1f}%")
    
    def get_available_capital(self) -> float:
        """Calculate available capital"""
        allocated = sum(
            SimpleTrade.from_dict(t).entry * SimpleTrade.from_dict(t).qty_remaining 
            for t in self.state.values()
        )
        return CAPITAL - allocated + self.pnl.unrealized_pnl
    
    def print_status(self):
        """Print current status"""
        available = self.get_available_capital()
        allocated = CAPITAL - available + self.pnl.unrealized_pnl
        
        print(f"\n💰 Status: ₹{CAPITAL:,} capital | ₹{available:,.0f} available")
        print(f"📈 P&L: ₹{self.pnl.total_pnl:+,.0f} ({self.pnl.pnl_pct:+.2f}%) | Trades: {self.pnl.trades_executed}")
        print(f"📊 Positions: {len(self.state)} | Pending: {len(self.pending_orders)}")
        
        if self.state:
            print("   Open Positions:")
            for symbol, trade_data in self.state.items():
                trade = SimpleTrade.from_dict(trade_data)
                ltp = get_live_price(symbol) or trade.entry
                pnl = (ltp - trade.entry) * trade.qty_remaining
                print(f"     {symbol}: {trade.qty_remaining} @ ₹{trade.entry:.0f} | "
                      f"LTP: ₹{ltp:.0f} | P&L: ₹{pnl:+.0f}")
    
    def place_buy_order(self, symbol: str, atr: float = 25.0) -> bool:
        """Place a BUY order"""
        print(f"\n🛒 Placing BUY order for {symbol}")
        
        # Check if already have position or pending order
        if symbol in self.state:
            print(f"  ❌ Already have position in {symbol}")
            return False
        
        for order in self.pending_orders.values():
            order_obj = SimpleOrder.from_dict(order)
            if order_obj.symbol == symbol and order_obj.side == "BUY":
                print(f"  ❌ BUY order already pending for {symbol}")
                return False
        
        # Check position limit
        if len(self.state) >= MAX_POSITIONS:
            print(f"  ❌ Max positions reached ({MAX_POSITIONS})")
            return False
        
        # Get price and calculate quantity
        price = get_live_price(symbol)
        if price is None:
            print(f"  ❌ Cannot get price for {symbol}")
            return False
        
        available = self.get_available_capital()
        qty = calculate_qty(price, atr, available)
        required_capital = price * qty
        
        if required_capital > available:
            print(f"  ❌ Insufficient capital: need ₹{required_capital:,.0f}, have ₹{available:,.0f}")
            return False
        
        # Place order
        order_id = place_paper_order(symbol, qty, "BUY")
        sl = price - (atr * SL_ATR_MULT)
        
        self.pending_orders[order_id] = SimpleOrder(
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
        
        print(f"  ✅ Order placed: Qty {qty}, Price ₹{price:.0f}, SL ₹{sl:.0f}")
        print(f"     Capital required: ₹{required_capital:,.0f}")
        return True
    
    def place_sell_order(self, symbol: str, reason: str = "TEST_SELL") -> bool:
        """Place a SELL order"""
        print(f"\n💸 Placing SELL order for {symbol}")
        
        if symbol not in self.state:
            print(f"  ❌ No position found for {symbol}")
            return False
        
        trade = SimpleTrade.from_dict(self.state[symbol])
        if trade.exit_pending:
            print(f"  ❌ Exit already pending for {symbol}")
            return False
        
        # Place sell order
        order_id = place_paper_order(symbol, trade.qty_remaining, "SELL")
        
        self.pending_orders[order_id] = SimpleOrder(
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
        
        # Mark position as exit pending
        trade.exit_pending = True
        self.state[symbol] = trade.to_dict()
        
        print(f"  ✅ SELL order placed: Qty {trade.qty_remaining}")
        return True
    
    def process_pending_orders(self):
        """Process all pending orders"""
        if not self.pending_orders:
            return
        
        print(f"\n⚡ Processing {len(self.pending_orders)} pending orders...")
        
        filled_orders = []
        
        for order_id, order_data in list(self.pending_orders.items()):
            order = SimpleOrder.from_dict(order_data)
            
            status, filled_qty, avg_price = simulate_order_fill(order)
            print(f"  📋 {order.symbol} {order.side}: {status}")
            
            if status == "COMPLETE" and filled_qty > 0:
                if order.side == "BUY":
                    # Create position
                    trade = SimpleTrade(
                        symbol=order.symbol,
                        side="BUY",
                        entry=avg_price,
                        sl=order.sl or (avg_price - ((order.atr or 20.0) * SL_ATR_MULT)),
                        qty=filled_qty,
                        qty_remaining=filled_qty,
                        atr=order.atr or 20.0,
                        entry_time=datetime.now().isoformat(),
                        realized_pnl=0.0
                    )
                    
                    self.state[order.symbol] = trade.to_dict()
                    self.pnl.trades_executed += 1
                    filled_orders.append(f"BUY {filled_qty} {order.symbol} @ ₹{avg_price:.0f}")
                    
                elif order.side == "SELL":
                    # Close position
                    if order.symbol in self.state:
                        trade = SimpleTrade.from_dict(self.state[order.symbol])
                        pnl_per_share = avg_price - trade.entry
                        realized_pnl = pnl_per_share * filled_qty
                        
                        self.pnl.realized_pnl += realized_pnl
                        trade.qty_remaining -= filled_qty
                        
                        if trade.qty_remaining <= 0:
                            del self.state[order.symbol]
                            filled_orders.append(f"SELL {filled_qty} {order.symbol} @ ₹{avg_price:.0f} (P&L: ₹{realized_pnl:+.0f})")
                        else:
                            self.state[order.symbol] = trade.to_dict()
                            filled_orders.append(f"PARTIAL SELL {filled_qty} {order.symbol}")
                
                del self.pending_orders[order_id]
                
            elif status in ("REJECTED", "CANCELLED"):
                print(f"     ❌ Order {status}")
                del self.pending_orders[order_id]
        
        for fill_msg in filled_orders:
            print(f"  ✅ {fill_msg}")
    
    def save_state(self):
        """Save current state to files"""
        files = {
            '../json/standalone_positions.json': self.state,
            '../json/standalone_pending.json': self.pending_orders,
            '../json/standalone_pnl.json': self.pnl.to_dict()
        }
        
        for filename, data in files.items():
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
        
        print(f"💾 State saved to {', '.join(files.keys())}")
    
    def run_test_sequence(self):
        """Run a complete test sequence"""
        print("\n" + "="*60)
        print("🧪 STANDALONE PAPER TRADING TEST")
        print("="*60)
        
        # Initial status
        self.print_status()
        
        # Test buying multiple stocks
        test_stocks = [
            ('SBIN', 25.0),
            ('RELIANCE', 30.0), 
            ('TCS', 20.0)
        ]
        
        for symbol, atr in test_stocks:
            success = self.place_buy_order(symbol, atr)
            if success:
                time.sleep(0.5)  # Brief pause between orders
        
        # Process buy orders
        self.process_pending_orders()
        self.print_status()
        
        # Test selling one position
        if self.state:
            symbol_to_sell = list(self.state.keys())[0]
            self.place_sell_order(symbol_to_sell, "PROFIT_TAKING")
            self.process_pending_orders()
        
        # Final status
        self.print_status()
        
        # Save state
        self.save_state()
        
        print(f"\n✅ Standalone paper trading test completed!")
        print(f"📊 Summary:")
        print(f"   • Trades executed: {self.pnl.trades_executed}")
        print(f"   • Realized P&L: ₹{self.pnl.realized_pnl:+.0f}")
        print(f"   • Open positions: {len(self.state)}")
        print(f"   • Capital utilization: {((CAPITAL - self.get_available_capital())/CAPITAL)*100:.1f}%")

# ==============================
# MAIN EXECUTION
# ==============================

def main():
    """Run standalone paper trading test"""
    try:
        trader = StandalonePaperTrader()
        trader.run_test_sequence()
        
        print(f"\n🎉 Test successful! No import dependencies required.")
        print(f"💡 This demonstrates core paper trading functionality.")
        
    except KeyboardInterrupt:
        print(f"\n⏹️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()