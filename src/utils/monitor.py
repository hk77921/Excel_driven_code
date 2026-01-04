"""
Trading Monitor - Dashboard for Bot Status
==========================================
Real-time dashboard to check bot status, P&L, and open positions.

Usage: 
    from src.utils.monitor import TradingMonitor
    monitor = TradingMonitor()
    monitor.display_dashboard()
"""

import json
import os
from datetime import datetime
import sys
from typing import Optional, Dict, Any
import logging
from pathlib import Path

# Add parent directory to path for imports (allows running as script or module)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

logger = logging.getLogger(__name__)
from src.core.state_manager import StateManager

logger = logging.getLogger(__name__)


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


class TradingMonitor:
    """
    Trading bot monitor and dashboard.
    
    Provides real-time status display, P&L tracking,
    and system health monitoring.
    """
    
    def __init__(self, state_dir: str = "state", mode: str = "paper"):
        """
        Initialize trading monitor.
        
        Args:
            state_dir: State directory to monitor
            mode: Trading mode (paper, live, backtest)
        """
        self.state_dir = state_dir
        self.mode = mode.upper()
        
        # Initialize state manager for the specific mode
        mode_state_dir = f"{state_dir}/{mode.lower()}"
        self.state = StateManager(mode_state_dir)
        
        logger.info(f"Monitor initialized for {self.mode} mode")
    
    def display_dashboard(self):
        """Display complete trading dashboard"""
        self._print_header(f"TRADING BOT MONITOR - {self.mode} MODE")
        
        # System status
        self._display_system_status()
        
        # Open positions
        self._display_positions()
        
        # Pending orders
        self._display_pending_orders()
        
        # Daily P&L
        self._display_daily_pnl()
        
        # Recent trades
        self._display_recent_trades()
        
        print(f"\n{Colors.CYAN}Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.RESET}")
    
    def _display_system_status(self):
        """Display system health status"""
        self._print_section_header("SYSTEM STATUS")
        
        # Check state files
        positions_exist = os.path.exists(self.state.positions_file)
        orders_exist = os.path.exists(self.state.orders_file)
        
        status_color = Colors.GREEN if positions_exist and orders_exist else Colors.YELLOW
        
        print(f"  State Files: {status_color}{'✓ Healthy' if positions_exist and orders_exist else '⚠ Partial'}{Colors.RESET}")
        print(f"  Mode: {Colors.BOLD}{self.mode}{Colors.RESET}")
        print(f"  State Dir: {self.state_dir}")
    
    def _display_positions(self):
        """Display open positions"""
        self._print_section_header("OPEN POSITIONS")
        
        positions = self.state.load_positions()
        
        if not positions:
            print(f"  {Colors.YELLOW}No open positions{Colors.RESET}")
            return
        
        total_exposure = 0.0
        unrealized_pnl = 0.0
        
        print(f"  {'Symbol':<12} {'Qty':<8} {'Entry':<10} {'Current':<10} {'P&L':<12} {'P&L%':<8}")
        print(f"  {'-'*65}")
        
        for symbol, pos in positions.items():
            if pos.get('qty_remaining', 0) <= 0:
                continue
                
            qty = pos.get('qty_remaining', 0)
            entry_price = pos.get('entry', 0.0)
            current_price = pos.get('current_price', entry_price)  # Would need live price update
            
            position_pnl = (current_price - entry_price) * qty
            pnl_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
            
            exposure = entry_price * qty
            total_exposure += exposure
            unrealized_pnl += position_pnl
            
            pnl_color = Colors.GREEN if position_pnl >= 0 else Colors.RED
            
            print(
                f"{symbol:<12} {qty:<8} {entry_price:<10.2f} {current_price:<10.2f} "
                f"{pnl_color}{position_pnl:<+12.2f}{Colors.RESET} "
                f"{pnl_color}{pnl_pct:<+8.2f}%{Colors.RESET}"
            )
        
        pnl_color = Colors.GREEN if unrealized_pnl >= 0 else Colors.RED
        
        print(f"  {'-'*65}")
        print(f"  Total Exposure: ₹{total_exposure:,.2f}")
        print(f"  Unrealized P&L: {pnl_color}₹{unrealized_pnl:+,.2f}{Colors.RESET}")
    
    def _display_pending_orders(self):
        """Display pending orders"""
        self._print_section_header("PENDING ORDERS")
        
        orders = self.state.load_orders()
        
        if not orders:
            print(f"  {Colors.YELLOW}No pending orders{Colors.RESET}")
            return
        
        pending_count = 0
        pending_capital = 0.0
        
        print(f"  {'Symbol':<12} {'Side':<6} {'Qty':<8} {'Price':<10} {'Status':<12} {'Age':<10}")
        print(f"  {'-'*65}")
        
        for order_id, order in orders.items():
            if order.get('status') not in ['PENDING', 'PARTIAL']:
                continue
                
            symbol = order.get('symbol', '')
            side = order.get('side', '')
            qty = order.get('req_qty', 0)
            price = order.get('price', 0.0)
            status = order.get('status', '')
            created_at = order.get('created_at', '')
            
            # Calculate age
            try:
                created_time = datetime.fromisoformat(created_at.replace('Z', ''))
                age = datetime.now() - created_time
                age_str = f"{age.total_seconds()/60:.0f}m"
            except:
                age_str = "N/A"
            
            if side == 'BUY':
                pending_capital += qty * price
            
            pending_count += 1
            
            side_color = Colors.GREEN if side == 'BUY' else Colors.RED
            
            print(
                f"  {symbol:<12} {side_color}{side:<6}{Colors.RESET} {qty:<8} "
                f"{price:<10.2f} {status:<12} {age_str:<10}"
            )
        
        print(f"  {'-'*65}")
        print(f"  Pending Orders: {pending_count}")
        print(f"  Capital Blocked: ₹{pending_capital:,.2f}")
    
    def _display_daily_pnl(self):
        """Display daily P&L summary"""
        self._print_section_header("DAILY P&L")
        
        # Load today's P&L data
        daily_pnl_data = self._load_daily_pnl()
        
        if not daily_pnl_data:
            print(f"  {Colors.YELLOW}No P&L data available{Colors.RESET}")
            return
        
        realized_pnl = daily_pnl_data.get('realized_pnl', 0.0)
        total_trades = daily_pnl_data.get('total_trades', 0)
        winning_trades = daily_pnl_data.get('winning_trades', 0)
        starting_capital = daily_pnl_data.get('starting_capital', 0.0)
        
        pnl_pct = (realized_pnl / starting_capital * 100) if starting_capital > 0 else 0
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        pnl_color = Colors.GREEN if realized_pnl >= 0 else Colors.RED
        
        print(f"  Date: {daily_pnl_data.get('date', 'Today')}")
        print(f"  Starting Capital: ₹{starting_capital:,.2f}")
        print(f"  Realized P&L: {pnl_color}₹{realized_pnl:+,.2f} ({pnl_pct:+.2f}%){Colors.RESET}")
        print(f"  Total Trades: {total_trades}")
        print(f"  Win Rate: {win_rate:.1f}% ({winning_trades}/{total_trades})")
    
    def _display_recent_trades(self):
        """Display recent completed trades"""
        self._print_section_header("RECENT TRADES (Last 5)")
        
        trades = self._load_recent_trades(limit=5)
        
        if not trades:
            print(f"  {Colors.YELLOW}No recent trades{Colors.RESET}")
            return
        
        print(f"  {'Symbol':<12} {'Side':<6} {'Qty':<8} {'Entry':<10} {'Exit':<10} {'P&L':<12} {'Time':<12}")
        print(f"  {'-'*75}")
        
        for trade in trades:
            symbol = trade.get('symbol', '')
            side = trade.get('side', '')
            qty = trade.get('qty', 0)
            entry = trade.get('entry_price', 0.0)
            exit_price = trade.get('exit_price', 0.0)
            pnl = trade.get('realized_pnl', 0.0)
            timestamp = trade.get('exit_time', '')
            
            try:
                time_str = datetime.fromisoformat(timestamp.replace('Z', '')).strftime('%H:%M')
            except:
                time_str = 'N/A'
            
            pnl_color = Colors.GREEN if pnl >= 0 else Colors.RED
            side_color = Colors.GREEN if side == 'BUY' else Colors.RED
            
            print(
                f"  {symbol:<12} {side_color}{side:<6}{Colors.RESET} {qty:<8} "
                f"{entry:<10.2f} {exit_price:<10.2f} {pnl_color}{pnl:<+12.2f}{Colors.RESET} {time_str:<12}"
            )
    
    def _load_daily_pnl(self) -> Optional[Dict[str, Any]]:
        """Load daily P&L data"""
        try:
            pnl_file = f"{self.state.state_dir}/daily_pnl.json"
            if os.path.exists(pnl_file):
                with open(pnl_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"Failed to load daily P&L: {e}")
        
        return None
    
    def _load_recent_trades(self, limit: int = 5) -> list:
        """Load recent completed trades"""
        try:
            trades_file = f"{self.state.state_dir}/trades.json"
            if os.path.exists(trades_file):
                with open(trades_file, 'r') as f:
                    all_trades = json.load(f)
                    
                # Sort by exit time and return recent ones
                completed_trades = [
                    trade for trade in all_trades 
                    if trade.get('status') == 'CLOSED' and trade.get('exit_time')
                ]
                
                completed_trades.sort(
                    key=lambda x: x.get('exit_time', ''), 
                    reverse=True
                )
                
                return completed_trades[:limit]
        except Exception as e:
            logger.debug(f"Failed to load trades: {e}")
        
        return []
    
    def _print_header(self, title: str):
        """Print formatted main header"""
        width = 80
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * width}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{title.center(width)}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'=' * width}{Colors.RESET}\n")
    
    def _print_section_header(self, title: str):
        """Print formatted section header"""
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}{title}{Colors.RESET}")
        print(f"{Colors.MAGENTA}{'-' * len(title)}{Colors.RESET}")


# Command line interface
def main():
    """CLI entry point for monitor"""
    import sys
    
    mode = sys.argv[1] if len(sys.argv) > 1 else "paper"
    
    monitor = TradingMonitor(mode=mode)
    
    try:
        monitor.display_dashboard()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Monitor interrupted{Colors.RESET}")
    except Exception as e:
        print(f"\n{Colors.RED}Monitor error: {e}{Colors.RESET}")


if __name__ == "__main__":
    main()