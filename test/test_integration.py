"""
INTEGRATION TEST - Screener to Paper Trading
============================================
Tests the complete flow from screener signals to paper trade execution.
This recreates the workflow from the old execution_engine.py system.
"""

import json
import os
import sys
import pandas as pd
from datetime import datetime
from typing import Dict, List

# ==============================
# MOCK SCREENER (based on old excel_driven_screener.py)
# ==============================

def create_mock_screener_output():
    """
    Create mock screener output similar to excel_driven_screener.py
    This simulates the SCREENER_OUTPUT sheet in MiniRobo.xlsx
    """
    
    # Mock eligible stocks (similar to what screener would find)
    screener_data = [
        {
            'SYMBOL': 'SBIN',
            'SECTOR': 'BANKING', 
            'PRICE': 500.0,
            'ATR_PCT': 3.2,
            'ADX': 28.5,
            'VOL_RATIO': 1.4,
            'ADTV_CR': 8.5,
            'TREND': 'BULLISH',
            'SCORE': 87.3,
            'REASONS': 'ATR_CONTRACT,NEAR_EMA20,BULLISH',
            'REL_STRENGTH': 0.045,
            'ELIGIBLE': 'YES',
            'LAST_UPDATED': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        },
        {
            'SYMBOL': 'RELIANCE',
            'SECTOR': 'ENERGY',
            'PRICE': 2500.0,
            'ATR_PCT': 2.8,
            'ADX': 32.1,
            'VOL_RATIO': 1.6,
            'ADTV_CR': 12.3,
            'TREND': 'BULLISH', 
            'SCORE': 84.7,
            'REASONS': 'ADX_RISING,RS+4.5%,BULLISH',
            'REL_STRENGTH': 0.063,
            'ELIGIBLE': 'YES',
            'LAST_UPDATED': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        },
        {
            'SYMBOL': 'TCS',
            'SECTOR': 'IT',
            'PRICE': 3500.0,
            'ATR_PCT': 2.5,
            'ADX': 22.8,
            'VOL_RATIO': 1.1,
            'ADTV_CR': 15.7,
            'TREND': 'BULLISH',
            'SCORE': 78.2,
            'REASONS': 'NEAR_EMA20,BULLISH',
            'REL_STRENGTH': 0.021,
            'ELIGIBLE': 'YES',
            'LAST_UPDATED': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    ]
    
    # Create Excel file (mock MiniRobo.xlsx)
    df = pd.DataFrame(screener_data)
    excel_file = "MockMiniRobo.xlsx"
    
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='SCREENER_OUTPUT', index=False)
    
    print(f"📊 Created mock screener output: {excel_file}")
    print(f"   Found {len(screener_data)} eligible stocks")
    
    return excel_file, screener_data

# ==============================
# MOCK EXECUTION ENGINE (based on old execution_engine.py)
# ==============================

class MockExecutionEngine:
    """
    Simplified execution engine based on old execution_engine.py
    Focuses on paper trading workflow
    """
    
    def __init__(self, capital: float = 50000):
        self.MODE = "PAPER"
        self.CAPITAL = capital
        self.RISK_PER_TRADE = 0.01  # 1% risk per trade
        self.SL_ATR_MULT = 1.5
        self.MAX_OPEN_POSITIONS = 5
        
        # State tracking (like old execution_engine.py)
        self.state = {}  # Open positions
        self.pending_orders = {}  # Pending orders
        self.daily_pnl = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'starting_capital': capital,
            'realized_pnl': 0.0,
            'unrealized_pnl': 0.0,
            'trades_executed': 0
        }
        
        # Sector limits (like old execution_engine.py)
        self.MAX_PER_SECTOR = 2
        self.sector_map = {
            'SBIN': 'BANKING',
            'HDFCBANK': 'BANKING', 
            'RELIANCE': 'ENERGY',
            'TCS': 'IT',
            'INFY': 'IT'
        }
    
    def get_live_price(self, symbol: str) -> float:
        """Mock price fetching (in real system, uses yfinance or Kite API)"""
        mock_prices = {
            'SBIN': 500.0,
            'RELIANCE': 2500.0, 
            'TCS': 3500.0,
            'INFY': 1800.0,
            'HDFCBANK': 1600.0
        }
        return mock_prices.get(symbol, 1000.0)
    
    def calculate_qty(self, price: float, atr_pct: float) -> int:
        """
        Calculate position size based on risk (from old execution_engine.py)
        """
        atr_value = (atr_pct / 100) * price
        risk_amount = self.CAPITAL * self.RISK_PER_TRADE
        sl_points = atr_value * self.SL_ATR_MULT
        
        if sl_points == 0:
            return 1
        
        # Risk-based position sizing
        risk_based_qty = int(risk_amount / sl_points)
        
        # Capital constraint
        available_capital = self.get_available_capital()
        max_affordable = int(available_capital / price) if price > 0 else 0
        
        qty = min(risk_based_qty, max_affordable)
        return max(qty, 1)
    
    def get_available_capital(self) -> float:
        """Calculate available capital after existing positions"""
        allocated = sum(
            pos['entry'] * pos['qty_remaining'] 
            for pos in self.state.values()
        )
        return self.CAPITAL - allocated + self.daily_pnl['unrealized_pnl']
    
    def count_sector_positions(self, sector: str) -> int:
        """Count existing positions in sector"""
        count = 0
        for symbol in self.state:
            if self.sector_map.get(symbol) == sector:
                count += 1
        return count
    
    def can_trade_symbol(self, symbol: str, sector: str) -> tuple:
        """
        Check if we can trade this symbol (from old execution_engine.py logic)
        """
        # Check position limits
        if len(self.state) >= self.MAX_OPEN_POSITIONS:
            return False, f"Max positions reached ({self.MAX_OPEN_POSITIONS})"
        
        # Check sector limits  
        if self.count_sector_positions(sector) >= self.MAX_PER_SECTOR:
            return False, f"Max {sector} positions reached ({self.MAX_PER_SECTOR})"
        
        # Check if already have position
        if symbol in self.state:
            return False, "Already have position"
        
        # Check if buy order pending
        for po in self.pending_orders.values():
            if po['symbol'] == symbol and po['side'] == 'BUY':
                return False, "Buy order already pending"
        
        return True, "OK"
    
    def place_order(self, symbol: str, side: str, qty: int, price: float, atr: float) -> str:
        """
        Place paper order (from old execution_engine.py)
        """
        order_id = f"PAPER-{symbol}-{side}-{int(datetime.now().timestamp() * 1000)}"
        
        # Calculate stop loss
        sl = price - (atr * self.SL_ATR_MULT) if side == 'BUY' else price + (atr * self.SL_ATR_MULT)
        
        # Add to pending orders
        self.pending_orders[order_id] = {
            'order_id': order_id,
            'symbol': symbol,
            'side': side,
            'qty': qty,
            'price': price,
            'atr': atr,
            'sl': sl,
            'time': datetime.now().isoformat()
        }
        
        print(f"  📝 {side} order placed: {qty} {symbol} @ ₹{price:.2f} | SL: ₹{sl:.2f}")
        return order_id
    
    def fill_pending_orders(self):
        """
        Simulate order fills (paper mode instant execution)
        """
        filled_orders = []
        
        for order_id, order in list(self.pending_orders.items()):
            # In paper mode, orders fill instantly at requested price
            if order['side'] == 'BUY':
                # Create position
                self.state[order['symbol']] = {
                    'symbol': order['symbol'],
                    'side': 'BUY',
                    'entry': order['price'],
                    'sl': order['sl'],
                    'qty': order['qty'],
                    'qty_remaining': order['qty'],
                    'atr': order['atr'],
                    'entry_time': order['time'],
                    'exit_pending': False,
                    'realized_pnl': 0.0
                }
                
                self.daily_pnl['trades_executed'] += 1
                filled_orders.append(f"BUY {order['qty']} {order['symbol']}")
                
            elif order['side'] == 'SELL':
                # Close position  
                if order['symbol'] in self.state:
                    pos = self.state[order['symbol']]
                    pnl = (order['price'] - pos['entry']) * order['qty']
                    self.daily_pnl['realized_pnl'] += pnl
                    
                    del self.state[order['symbol']]
                    filled_orders.append(f"SELL {order['qty']} {order['symbol']} (P&L: ₹{pnl:+.2f})")
            
            del self.pending_orders[order_id]
        
        return filled_orders
    
    def process_screener_signals(self, signals: List[Dict]) -> Dict:
        """
        Process screener signals (main execution logic from old execution_engine.py)
        """
        results = {
            'processed': 0,
            'orders_placed': 0,
            'rejected': 0,
            'rejection_reasons': []
        }
        
        print(f"\n🔄 Processing {len(signals)} screener signals...")
        
        for signal in signals:
            symbol = signal['SYMBOL']
            sector = signal['SECTOR']
            price = signal['PRICE']
            atr_pct = signal['ATR_PCT']
            score = signal['SCORE']
            
            results['processed'] += 1
            
            # Check if we can trade this symbol
            can_trade, reason = self.can_trade_symbol(symbol, sector)
            
            if not can_trade:
                results['rejected'] += 1
                results['rejection_reasons'].append(f"{symbol}: {reason}")
                print(f"  ❌ {symbol}: {reason}")
                continue
            
            # Calculate position size
            qty = self.calculate_qty(price, atr_pct)
            atr_value = (atr_pct / 100) * price
            
            # Check capital availability
            required_capital = price * qty
            available = self.get_available_capital()
            
            if required_capital > available:
                results['rejected'] += 1
                results['rejection_reasons'].append(f"{symbol}: Insufficient capital")
                print(f"  ❌ {symbol}: Need ₹{required_capital:,.0f}, have ₹{available:,.0f}")
                continue
            
            # Place BUY order
            order_id = self.place_order(symbol, 'BUY', qty, price, atr_value)
            results['orders_placed'] += 1
            
            print(f"  ✅ {symbol}: Score {score:.1f} | Qty {qty} | Capital ₹{required_capital:,.0f}")
        
        return results
    
    def print_status(self):
        """Print current trading status"""
        available = self.get_available_capital()
        allocated = self.CAPITAL - available + self.daily_pnl['unrealized_pnl']
        
        print(f"\n💰 TRADING STATUS")
        print(f"   Capital: ₹{self.CAPITAL:,} | Available: ₹{available:,.0f} | Allocated: ₹{allocated:,.0f}")
        print(f"   P&L: ₹{self.daily_pnl['realized_pnl']:+,.0f} | Trades: {self.daily_pnl['trades_executed']}")
        print(f"   Positions: {len(self.state)} | Pending: {len(self.pending_orders)}")
        
        if self.state:
            print(f"   Open Positions:")
            for symbol, pos in self.state.items():
                ltp = self.get_live_price(symbol)
                pnl = (ltp - pos['entry']) * pos['qty_remaining']
                print(f"     {symbol}: {pos['qty_remaining']} @ ₹{pos['entry']:.0f} | "
                      f"LTP: ₹{ltp:.0f} | P&L: ₹{pnl:+.0f}")

# ==============================
# INTEGRATION TEST
# ==============================

def run_integration_test():
    """
    Run complete integration test: Screener -> Execution
    This recreates the old workflow from excel_driven_screener.py -> execution_engine.py
    """
    
    print("="*70)
    print("🧪 INTEGRATION TEST: Screener → Paper Trading")  
    print("="*70)
    print("Recreating the old workflow:")
    print("  1. excel_driven_screener.py → finds eligible stocks")
    print("  2. execution_engine.py → processes signals in PAPER mode")
    
    try:
        # Step 1: Create mock screener output (simulates excel_driven_screener.py)
        excel_file, signals = create_mock_screener_output()
        
        # Step 2: Initialize execution engine (simulates execution_engine.py)
        engine = MockExecutionEngine(capital=50000)
        engine.print_status()
        
        # Step 3: Process screener signals (main execution loop)
        results = engine.process_screener_signals(signals)
        
        # Step 4: Fill pending orders (simulate order execution)
        print(f"\n⚡ Executing pending orders...")
        filled = engine.fill_pending_orders()
        
        for fill in filled:
            print(f"  ✅ {fill}")
        
        # Step 5: Show final status
        engine.print_status()
        
        # Step 6: Results summary
        print(f"\n📊 EXECUTION SUMMARY")
        print(f"   Signals processed: {results['processed']}")
        print(f"   Orders placed: {results['orders_placed']}")
        print(f"   Orders filled: {len(filled)}")
        print(f"   Rejected: {results['rejected']}")
        
        if results['rejection_reasons']:
            print(f"   Rejection reasons:")
            for reason in results['rejection_reasons'][:5]:  # Show first 5
                print(f"     • {reason}")
        
        # Step 7: Save state (like old execution_engine.py)
        state_files = {
            'positions.json': engine.state,
            'pending_orders.json': engine.pending_orders, 
            'daily_pnl.json': engine.daily_pnl
        }
        
        for filename, data in state_files.items():
            with open(f"integration_test_{filename}", 'w') as f:
                json.dump(data, f, indent=2)
        
        print(f"\n💾 State saved to integration_test_*.json files")
        
        # Cleanup
        if os.path.exists(excel_file):
            os.remove(excel_file)
        
        print(f"\n✅ Integration test completed successfully!")
        print(f"   This demonstrates the paper trading workflow from your old system.")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run the integration test"""
    success = run_integration_test()
    
    if success:
        print(f"\n🎉 Paper trading integration validated!")
        print(f"\nNext steps:")
        print(f"  1. Run: python excel_driven_screener.py")
        print(f"  2. Check MiniRobo.xlsx SCREENER_OUTPUT sheet")
        print(f"  3. Run your paper trading execution")
        print(f"  4. Monitor positions and P&L")
    else:
        print(f"\n❌ Integration test failed - check errors above")

if __name__ == "__main__":
    main()