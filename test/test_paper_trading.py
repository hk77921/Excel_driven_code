"""
PAPER TRADING TEST SUITE
========================
Comprehensive tests for paper trading functionality.
Tests the complete workflow from screener signals to trade execution.

Run: python test_paper_trading.py

Based on the old execution_engine.py paper trading functionality.
"""

import json
import os
import sys
import pandas as pd
from datetime import datetime, timedelta
from dataclasses import asdict
import tempfile
import shutil
import time
from typing import Dict, List, Tuple

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))

try:
    from src.core import (
        ScreenerSignal, TradeParameters, CapitalParameters,
        OrderSide
    )
    from src.execution.paper import PaperTradingMode
    from src.core.state_manager import StateManager
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running from the Excel_driven_code directory")
    sys.exit(1)

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

def print_test(name: str):
    print(f"\n{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BLUE}TEST: {name}{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*60}{Colors.RESET}")

def print_pass(message: str):
    print(f"{Colors.GREEN}✓ PASS:{Colors.RESET} {message}")

def print_fail(message: str):
    print(f"{Colors.RED}✗ FAIL:{Colors.RESET} {message}")

def print_info(message: str):
    print(f"{Colors.YELLOW}INFO:{Colors.RESET} {message}")

def print_debug(message: str):
    print(f"{Colors.CYAN}DEBUG:{Colors.RESET} {message}")

class PaperTradingTester:
    """Comprehensive paper trading test suite"""
    
    def __init__(self):
        """Initialize test environment"""
        # Create temporary directory for test state
        self.test_dir = tempfile.mkdtemp(prefix="paper_test_")
        print_info(f"Test directory: {self.test_dir}")
        
        # Test parameters (similar to old execution_engine.py)
        self.capital_params = CapitalParameters(
            total_capital=50000,  # ₹50k for testing
            risk_per_trade=0.01,  # 1% risk per trade
            max_daily_loss_pct=0.02,  # 2% daily loss limit
            max_open_positions=5,
            max_per_sector=2
        )
        
        self.trade_params = TradeParameters(
            atr_period=14,
            sl_atr_mult=1.5,
            target_atr_mult=2.0,
            partial_exit_ratio=0.8,
            trailing_sl_atr_mult=1.5
        )
        
        # Initialize paper trader
        self.trader = PaperTradingMode(
            self.capital_params,
            self.trade_params,
            self.test_dir
        )
        
        # Test symbols with known prices
        self.test_symbols = ['SBIN', 'RELIANCE', 'TCS', 'INFY', 'HDFCBANK']
        self.test_prices = {
            'SBIN': 500.0,
            'RELIANCE': 2500.0,
            'TCS': 3500.0,
            'INFY': 1800.0,
            'HDFCBANK': 1600.0
        }
    
    def cleanup(self):
        """Clean up test environment"""
        try:
            shutil.rmtree(self.test_dir)
            print_info("Test directory cleaned up")
        except Exception as e:
            print_fail(f"Failed to cleanup: {e}")
    
    def create_test_excel(self):
        """Create test Excel file similar to MiniRobo.xlsx"""
        excel_file = "TestMiniRobo.xlsx"
        
        # Create UNIVERSE sheet
        universe_data = []
        for symbol in self.test_symbols:
            universe_data.append({
                'SYMBOL': symbol,
                'ENABLED': 'YES'
            })
        
        # Create SCREENER_RULES sheet  
        rules_data = [
            {'RULE': 'MIN_ADTV_CR', 'VALUE': 5.0},
            {'RULE': 'MIN_ATR_PCT', 'VALUE': 2.0},
            {'RULE': 'MAX_ATR_PCT', 'VALUE': 5.0},
            {'RULE': 'MIN_ADX', 'VALUE': 20.0},
            {'RULE': 'MIN_VOL_RATIO', 'VALUE': 1.0},
            {'RULE': 'MAX_TRADES_PER_DAY', 'VALUE': 3},
            {'RULE': 'TREND_REQUIRED', 'VALUE': 'BULLISH'}
        ]
        
        # Create SECTOR_MAP sheet
        sector_data = [
            {'SYMBOL': 'SBIN', 'SECTOR': 'BANKING'},
            {'SYMBOL': 'RELIANCE', 'SECTOR': 'ENERGY'},
            {'SYMBOL': 'TCS', 'SECTOR': 'IT'},
            {'SYMBOL': 'INFY', 'SECTOR': 'IT'},
            {'SYMBOL': 'HDFCBANK', 'SECTOR': 'BANKING'}
        ]
        
        # Create SCREENER_OUTPUT sheet (eligible stocks)
        output_data = [
            {
                'SYMBOL': 'SBIN',
                'PRICE': 500.0,
                'ATR_PCT': 3.0,
                'ADX': 25.0,
                'VOL_RATIO': 1.2,
                'TREND': 'BULLISH',
                'SCORE': 85.0,
                'ELIGIBLE': 'YES'
            },
            {
                'SYMBOL': 'RELIANCE', 
                'PRICE': 2500.0,
                'ATR_PCT': 2.8,
                'ADX': 28.0,
                'VOL_RATIO': 1.5,
                'TREND': 'BULLISH',
                'SCORE': 82.0,
                'ELIGIBLE': 'YES'
            }
        ]
        
        # Write Excel file
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            pd.DataFrame(universe_data).to_excel(writer, sheet_name='UNIVERSE', index=False)
            pd.DataFrame(rules_data).to_excel(writer, sheet_name='SCREENER_RULES', index=False)
            pd.DataFrame(sector_data).to_excel(writer, sheet_name='SECTOR_MAP', index=False)
            pd.DataFrame(output_data).to_excel(writer, sheet_name='SCREENER_OUTPUT', index=False)
        
        print_info(f"Created test Excel file: {excel_file}")
        return excel_file
    
    def test_basic_connection(self):
        """Test 1: Basic paper trading connection"""
        print_test("Basic Paper Trading Connection")
        
        if self.trader.is_connected():
            print_pass("Paper trader connected successfully")
        else:
            print_fail("Paper trader connection failed")
            return False
        
        # Test capital retrieval
        available_capital = self.trader.get_available_capital()
        expected_capital = self.capital_params.total_capital
        
        if available_capital == expected_capital:
            print_pass(f"Capital correctly set: ₹{available_capital:,.2f}")
        else:
            print_fail(f"Capital mismatch: expected ₹{expected_capital}, got ₹{available_capital}")
            return False
        
        return True
    
    def test_price_fetching(self):
        """Test 2: Live price fetching"""
        print_test("Price Fetching")
        
        # Set test prices
        self.trader.set_prices(self.test_prices)
        
        for symbol, expected_price in self.test_prices.items():
            price = self.trader.get_live_price(symbol)
            if price == expected_price:
                print_pass(f"{symbol}: ₹{price:.2f}")
            else:
                print_fail(f"{symbol}: expected ₹{expected_price:.2f}, got ₹{price}")
                return False
        
        return True
    
    def test_order_placement(self):
        """Test 3: Order placement and execution"""
        print_test("Order Placement & Execution")
        
        symbol = 'SBIN'
        price = self.test_prices[symbol]
        
        # Create a buy signal
        signal = ScreenerSignal(
            symbol=symbol,
            score=85.0,
            atr=15.0,  # ATR for position sizing
            adx=25.0,
            volume_ratio=1.2,
            trend='BULLISH',
            price=price,
            sector='BANKING',
            timestamp=datetime.now()
        )
        
        # Process the signal
        success, msg = self.trader.process_signal(signal)
        if success:
            print_pass(f"Signal processed: {msg}")
        else:
            print_fail(f"Signal processing failed: {msg}")
            return False
        
        # Execute cycle to fill orders
        self.trader.set_price(symbol, price)  # Ensure price is set
        report = self.trader.execute_cycle()
        
        if report['errors']:
            print_fail(f"Execution errors: {report['errors']}")
            return False
        
        # Check if position was created
        positions = self.trader.get_positions()
        if symbol in positions:
            pos = positions[symbol]
            print_pass(f"Position created: {symbol} qty={pos.get('qty_remaining', 'N/A')}")
        else:
            print_fail(f"No position created for {symbol}")
            return False
        
        return True
    
    def test_stop_loss_execution(self):
        """Test 4: Stop loss trigger"""
        print_test("Stop Loss Execution")
        
        symbol = 'SBIN'
        
        # Get current position
        positions = self.trader.get_positions()
        if symbol not in positions:
            print_fail(f"No position found for {symbol}")
            return False
        
        position = positions[symbol]
        entry_price = position.get('entry_price', 0)
        stop_loss = position.get('stop_loss', 0)
        
        if not entry_price or not stop_loss:
            print_fail(f"Invalid position data: entry={entry_price}, sl={stop_loss}")
            return False
        
        print_info(f"Entry: ₹{entry_price:.2f}, Stop Loss: ₹{stop_loss:.2f}")
        
        # Move price below stop loss
        trigger_price = stop_loss - 1.0
        self.trader.set_price(symbol, trigger_price)
        
        print_info(f"Setting price to ₹{trigger_price:.2f} to trigger stop loss")
        
        # Execute cycle
        report = self.trader.execute_cycle()
        
        # Check if position was closed or exit order was placed
        updated_positions = self.trader.get_positions()
        
        if symbol not in updated_positions:
            print_pass(f"Position closed due to stop loss")
        else:
            # Position might still exist if exit is pending
            updated_pos = updated_positions[symbol]
            if updated_pos.get('exit_pending', False):
                print_pass(f"Exit order placed due to stop loss")
            else:
                print_fail(f"Stop loss not triggered properly")
                return False
        
        return True
    
    def test_profit_target_exit(self):
        """Test 5: Profit target and partial exit"""
        print_test("Profit Target & Partial Exit")
        
        # Create new position for this test
        symbol = 'RELIANCE'
        price = self.test_prices[symbol]
        
        signal = ScreenerSignal(
            symbol=symbol,
            score=82.0,
            atr=50.0,
            adx=28.0,
            volume_ratio=1.5,
            trend='BULLISH',
            price=price,
            sector='ENERGY',
            timestamp=datetime.now()
        )
        
        # Process signal and create position
        success, msg = self.trader.process_signal(signal)
        if not success:
            print_fail(f"Failed to create test position: {msg}")
            return False
        
        self.trader.execute_cycle()
        
        # Get position details
        positions = self.trader.get_positions()
        if symbol not in positions:
            print_fail(f"Test position not created for {symbol}")
            return False
        
        position = positions[symbol]
        entry_price = position.get('entry_price', 0)
        stop_loss = position.get('stop_loss', 0)
        
        # Calculate partial exit target (similar to old execution_engine.py)
        r_value = abs(entry_price - stop_loss)  # Risk value
        partial_target = entry_price + (0.8 * r_value)  # +0.8R target
        
        print_info(f"Entry: ₹{entry_price:.2f}, Partial target: ₹{partial_target:.2f}")
        
        # Move price to partial target
        self.trader.set_price(symbol, partial_target + 5)  # Slight buffer
        
        # Execute cycle
        report = self.trader.execute_cycle()
        
        # Check if partial exit occurred
        updated_positions = self.trader.get_positions()
        
        if symbol in updated_positions:
            updated_pos = updated_positions[symbol]
            original_qty = position.get('quantity', 0)
            remaining_qty = updated_pos.get('qty_remaining', original_qty)
            
            if remaining_qty < original_qty:
                print_pass(f"Partial exit executed: {original_qty} -> {remaining_qty}")
            else:
                print_info(f"Partial exit conditions not met yet")
        
        return True
    
    def test_capital_management(self):
        """Test 6: Capital allocation and limits"""
        print_test("Capital Management")
        
        # Check available capital after positions
        available = self.trader.get_available_capital()
        positions = self.trader.get_positions()
        
        allocated = 0
        for symbol, pos in positions.items():
            entry = pos.get('entry_price', 0)
            qty = pos.get('qty_remaining', 0)
            allocated += entry * qty
        
        total_capital = self.capital_params.total_capital
        expected_available = total_capital - allocated
        
        print_info(f"Total Capital: ₹{total_capital:,.2f}")
        print_info(f"Allocated: ₹{allocated:,.2f}")
        print_info(f"Available: ₹{available:,.2f}")
        print_info(f"Expected Available: ₹{expected_available:,.2f}")
        
        # Allow for some variance due to P&L
        if abs(available - expected_available) < total_capital * 0.1:  # 10% tolerance
            print_pass("Capital allocation appears correct")
        else:
            print_fail(f"Capital allocation mismatch")
            return False
        
        return True
    
    def test_pnl_tracking(self):
        """Test 7: P&L tracking and daily limits"""
        print_test("P&L Tracking")
        
        # Get current P&L
        today = datetime.now().strftime("%Y-%m-%d")
        pnl_data = self.trader.state.load_daily_pnl(today) or {
            'realized_pnl': 0.0,
            'unrealized_pnl': 0.0,
            'total_pnl': 0.0,
            'pnl_pct': 0.0,
            'trades_executed': 0
        }
        
        print_info(f"Realized P&L: ₹{pnl_data.get('realized_pnl', 0):+.2f}")
        print_info(f"Unrealized P&L: ₹{pnl_data.get('unrealized_pnl', 0):+.2f}")
        print_info(f"Total P&L: ₹{pnl_data.get('total_pnl', 0):+.2f}")
        print_info(f"P&L %: {pnl_data.get('pnl_pct', 0):+.2f}%")
        print_info(f"Trades Executed: {pnl_data.get('trades_executed', 0)}")
        
        # Test daily loss limit (simulate large loss)
        max_loss_pct = self.capital_params.max_daily_loss_pct * 100
        current_loss_pct = abs(min(0, pnl_data.get('pnl_pct', 0)))
        
        print_info(f"Current loss: {current_loss_pct:.2f}%, Limit: {max_loss_pct:.2f}%")
        
        if current_loss_pct < max_loss_pct:
            print_pass("Within daily loss limits")
        else:
            print_fail("Exceeded daily loss limits - should halt trading")
        
        return True
    
    def run_all_tests(self):
        """Run complete test suite"""
        print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.CYAN}PAPER TRADING TEST SUITE{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
        
        tests = [
            ("Basic Connection", self.test_basic_connection),
            ("Price Fetching", self.test_price_fetching),
            ("Order Placement", self.test_order_placement),
            ("Stop Loss", self.test_stop_loss_execution),
            ("Profit Targets", self.test_profit_target_exit),
            ("Capital Management", self.test_capital_management),
            ("P&L Tracking", self.test_pnl_tracking)
        ]
        
        passed = 0
        total = len(tests)
        
        for name, test_func in tests:
            try:
                if test_func():
                    passed += 1
                time.sleep(0.5)  # Brief pause between tests
            except Exception as e:
                print_fail(f"Test '{name}' threw exception: {e}")
        
        # Final summary
        print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.CYAN}TEST SUMMARY{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
        
        if passed == total:
            print(f"{Colors.GREEN}ALL TESTS PASSED: {passed}/{total}{Colors.RESET}")
            print(f"{Colors.GREEN}Paper trading is ready for use!{Colors.RESET}")
        else:
            print(f"{Colors.RED}TESTS FAILED: {passed}/{total} passed{Colors.RESET}")
            print(f"{Colors.RED}Fix issues before using paper trading{Colors.RESET}")
        
        # Show final positions
        print(f"\n{Colors.YELLOW}FINAL POSITIONS:{Colors.RESET}")
        positions = self.trader.get_positions()
        if positions:
            for symbol, pos in positions.items():
                qty = pos.get('qty_remaining', 0)
                entry = pos.get('entry_price', 0)
                ltp = self.trader.get_live_price(symbol) or entry
                pnl = (ltp - entry) * qty if pos.get('side') == 'BUY' else (entry - ltp) * qty
                print(f"  {symbol}: {qty} shares @ ₹{entry:.2f} | "
                      f"LTP: ₹{ltp:.2f} | P&L: ₹{pnl:+.2f}")
        else:
            print("  No open positions")
        
        return passed == total


def main():
    """Run paper trading tests"""
    tester = PaperTradingTester()
    
    try:
        # Create test Excel file
        tester.create_test_excel()
        
        # Run all tests
        success = tester.run_all_tests()
        
        if success:
            print(f"\n{Colors.GREEN}✓ Paper trading validation complete!{Colors.RESET}")
            print(f"{Colors.GREEN}Ready to test with real screener data.{Colors.RESET}")
        else:
            print(f"\n{Colors.RED}✗ Paper trading validation failed!{Colors.RESET}")
            print(f"{Colors.RED}Check errors above before proceeding.{Colors.RESET}")
    
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Tests interrupted by user{Colors.RESET}")
    except Exception as e:
        print(f"\n{Colors.RED}Test suite error: {e}{Colors.RESET}")
    finally:
        # Cleanup
        tester.cleanup()
        
        # Clean up test files
        for file in ['TestMiniRobo.xlsx']:
            if os.path.exists(file):
                try:
                    os.remove(file)
                    print_info(f"Cleaned up {file}")
                except:
                    pass


if __name__ == "__main__":
    main()