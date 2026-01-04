"""
TRADING BOT MONITOR
-------------------
Quick dashboard to check bot status, P&L, and open positions

Usage: python monitor.py
"""

import json
import os
from datetime import datetime
from typing import Optional

# ANSI color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

# Files
STATE_FILE = "trade_state.json"
PENDING_ORDERS_FILE = "pending_orders.json"
PNL_FILE = "daily_pnl.json"

def load_json(filename: str) -> dict:
    """Load JSON file with error handling"""
    if not os.path.exists(filename):
        return {}
    
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"{Colors.RED}Error loading {filename}: {e}{Colors.RESET}")
        return {}


def print_header(title: str):
    """Print formatted section header"""
    width = 70
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*width}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{title.center(width)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*width}{Colors.RESET}\n")


def print_row(label: str, value: str, color: str = Colors.RESET):
    """Print formatted key-value row"""
    print(f"{Colors.BOLD}{label:.<40}{Colors.RESET} {color}{value}{Colors.RESET}")


def get_price_color(value: float) -> str:
    """Get color based on positive/negative value"""
    if value > 0:
        return Colors.GREEN
    elif value < 0:
        return Colors.RED
    else:
        return Colors.YELLOW


def format_currency(amount: float) -> str:
    """Format amount as currency"""
    return f"₹{amount:,.2f}"


def format_percentage(pct: float) -> str:
    """Format percentage with sign"""
    return f"{pct:+.2f}%"


def monitor_daily_pnl():
    """Display daily P&L summary"""
    print_header("📊 DAILY P&L SUMMARY")
    
    pnl = load_json(PNL_FILE)
    
    if not pnl:
        print(f"{Colors.YELLOW}⚠️  No P&L data found. Has bot run today?{Colors.RESET}")
        return
    
    # Extract data
    date = pnl.get("date", "Unknown")
    starting_capital = pnl.get("starting_capital", 0.0)
    realized_pnl = pnl.get("realized_pnl", 0.0)
    unrealized_pnl = pnl.get("unrealized_pnl", 0.0)
    trades_executed = pnl.get("trades_executed", 0)
    
    total_pnl = realized_pnl + unrealized_pnl
    pnl_pct = (total_pnl / starting_capital * 100) if starting_capital > 0 else 0.0
    
    # Display
    print_row("Date", date, Colors.CYAN)
    print_row("Starting Capital", format_currency(starting_capital))
    print_row("Realized P&L", format_currency(realized_pnl), get_price_color(realized_pnl))
    print_row("Unrealized P&L", format_currency(unrealized_pnl), get_price_color(unrealized_pnl))
    print_row("Total P&L", format_currency(total_pnl), get_price_color(total_pnl))
    print_row("P&L Percentage", format_percentage(pnl_pct), get_price_color(total_pnl))
    print_row("Trades Executed", str(trades_executed), Colors.BLUE)
    
    # Kill-switch warning
    if pnl_pct <= -2.0:
        print(f"\n{Colors.RED}{Colors.BOLD}🚨 KILL-SWITCH TRIGGERED! Daily loss limit reached.{Colors.RESET}")
    elif pnl_pct <= -1.5:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️  WARNING: Approaching daily loss limit ({pnl_pct:.2f}%).{Colors.RESET}")
    elif pnl_pct >= 5.0:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 Excellent day! P&L: {pnl_pct:.2f}%{Colors.RESET}")


def monitor_open_positions():
    """Display open positions"""
    print_header("📈 OPEN POSITIONS")
    
    state = load_json(STATE_FILE)
    
    if not state:
        print(f"{Colors.GREEN}✓ No open positions{Colors.RESET}")
        return
    
    print(f"Total Open Positions: {Colors.BOLD}{len(state)}{Colors.RESET}\n")
    
    total_exposure = 0.0
    total_unrealized = 0.0
    
    for symbol, trade_data in state.items():
        entry = trade_data.get("entry", 0.0)
        sl = trade_data.get("sl", 0.0)
        qty = trade_data.get("qty", 0)
        qty_remaining = trade_data.get("qty_remaining", 0)
        atr = trade_data.get("atr", 0.0)
        partial_done = trade_data.get("partial_done", False)
        trailing_active = trade_data.get("trailing_active", False)
        exit_pending = trade_data.get("exit_pending", False)
        realized_pnl = trade_data.get("realized_pnl", 0.0)
        entry_time = trade_data.get("entry_time", "Unknown")
        
        exposure = entry * qty_remaining
        total_exposure += exposure
        
        # Calculate unrealized P&L (we don't have live price here, so just show entry)
        risk_per_share = abs(entry - sl)
        max_loss = risk_per_share * qty_remaining
        
        print(f"{Colors.BOLD}{Colors.BLUE}{symbol}{Colors.RESET}")
        print(f"  Entry: {Colors.CYAN}₹{entry:.2f}{Colors.RESET} | SL: {Colors.RED}₹{sl:.2f}{Colors.RESET} | Qty: {qty_remaining}/{qty}")
        print(f"  Exposure: ₹{exposure:,.2f} | Max Loss: ₹{max_loss:.2f}")
        print(f"  Entry Time: {entry_time}")
        
        # Status indicators
        status_flags = []
        if partial_done:
            status_flags.append(f"{Colors.GREEN}Partial Exit Done{Colors.RESET}")
        if trailing_active:
            status_flags.append(f"{Colors.YELLOW}Trailing SL Active{Colors.RESET}")
        if exit_pending:
            status_flags.append(f"{Colors.RED}Exit Pending{Colors.RESET}")
        if realized_pnl != 0:
            color = get_price_color(realized_pnl)
            status_flags.append(f"{color}Realized: ₹{realized_pnl:,.2f}{Colors.RESET}")
        
        if status_flags:
            print(f"  Status: {' | '.join(status_flags)}")
        
        print()
    
    print(f"{Colors.BOLD}Total Exposure: {format_currency(total_exposure)}{Colors.RESET}")


def monitor_pending_orders():
    """Display pending orders"""
    print_header("⏳ PENDING ORDERS")
    
    pending = load_json(PENDING_ORDERS_FILE)
    
    if not pending:
        print(f"{Colors.GREEN}✓ No pending orders{Colors.RESET}")
        return
    
    print(f"Total Pending: {Colors.BOLD}{len(pending)}{Colors.RESET}\n")
    
    for order_id, order_data in pending.items():
        symbol = order_data.get("symbol", "Unknown")
        side = order_data.get("side", "Unknown")
        qty = order_data.get("req_qty", 0)
        price = order_data.get("price")
        reason = order_data.get("reason", "N/A")
        time = order_data.get("time", "Unknown")
        
        side_color = Colors.GREEN if side == "BUY" else Colors.RED
        
        print(f"{Colors.BOLD}{symbol}{Colors.RESET} | {side_color}{side}{Colors.RESET} {qty} shares")
        print(f"  Order ID: {order_id}")
        if price:
            print(f"  Price: ₹{price:.2f}")
        print(f"  Reason: {reason}")
        print(f"  Time: {time}")
        print()


def monitor_system_health():
    """Check system health"""
    print_header("🔧 SYSTEM HEALTH")
    
    # Check if log file exists
    today = datetime.now().strftime("%Y%m%d")
    log_file = f"trading_log_{today}.log"
    
    if os.path.exists(log_file):
        print_row("Today's Log", f"✓ {log_file}", Colors.GREEN)
        
        # Check for errors in log
        try:
            with open(log_file, "r") as f:
                log_content = f.read()
                error_count = log_content.count("ERROR")
                critical_count = log_content.count("CRITICAL")
                warning_count = log_content.count("WARNING")
            
            print_row("Errors", str(error_count), Colors.RED if error_count > 0 else Colors.GREEN)
            print_row("Critical", str(critical_count), Colors.RED if critical_count > 0 else Colors.GREEN)
            print_row("Warnings", str(warning_count), Colors.YELLOW if warning_count > 0 else Colors.GREEN)
        except Exception as e:
            print(f"{Colors.YELLOW}Could not analyze log: {e}{Colors.RESET}")
    else:
        print_row("Today's Log", "✗ Not found", Colors.RED)
    
    # Check state file
    if os.path.exists(STATE_FILE):
        print_row("State File", "✓ Exists", Colors.GREEN)
        try:
            state = load_json(STATE_FILE)
            print_row("State Valid", "✓ JSON Valid", Colors.GREEN)
        except:
            print_row("State Valid", "✗ Corrupted", Colors.RED)
    else:
        print_row("State File", "✗ Missing", Colors.YELLOW)
    
    # Check pending orders file
    if os.path.exists(PENDING_ORDERS_FILE):
        print_row("Pending Orders File", "✓ Exists", Colors.GREEN)
    else:
        print_row("Pending Orders File", "✗ Missing", Colors.YELLOW)
    
    # Check P&L file
    if os.path.exists(PNL_FILE):
        print_row("P&L File", "✓ Exists", Colors.GREEN)
        pnl = load_json(PNL_FILE)
        if pnl.get("date") == datetime.now().strftime("%Y-%m-%d"):
            print_row("P&L Date", "✓ Current", Colors.GREEN)
        else:
            print_row("P&L Date", f"⚠️  Old: {pnl.get('date', 'Unknown')}", Colors.YELLOW)
    else:
        print_row("P&L File", "✗ Missing", Colors.RED)
    
    # Check backup directory
    if os.path.exists("backups"):
        backup_count = len([f for f in os.listdir("backups") if f.endswith(".bak")])
        print_row("Backups", f"✓ {backup_count} files", Colors.GREEN)
    else:
        print_row("Backups", "⚠️  Directory missing", Colors.YELLOW)


def monitor_capital():
    """Display capital allocation"""
    print_header("💰 CAPITAL ALLOCATION")
    
    pnl = load_json(PNL_FILE)
    state = load_json(STATE_FILE)
    
    starting_capital = pnl.get("starting_capital", 25000.0)
    
    # Calculate allocated capital
    allocated = 0.0
    for trade_data in state.values():
        entry = trade_data.get("entry", 0.0)
        qty_remaining = trade_data.get("qty_remaining", 0)
        allocated += entry * qty_remaining
    
    available = starting_capital - allocated
    
    print_row("Total Capital", format_currency(starting_capital))
    print_row("Allocated", format_currency(allocated), Colors.YELLOW)
    print_row("Available", format_currency(available), Colors.GREEN)
    
    if starting_capital > 0:
        allocation_pct = (allocated / starting_capital) * 100
        print_row("Allocation %", f"{allocation_pct:.1f}%", Colors.YELLOW)
        
        if allocation_pct > 80:
            print(f"\n{Colors.YELLOW}⚠️  High allocation! Only {allocation_pct:.1f}% capital available.{Colors.RESET}")


def show_quick_actions():
    """Display quick action commands"""
    print_header("⚡ QUICK ACTIONS")
    
    print(f"{Colors.BOLD}Emergency Stop:{Colors.RESET}")
    print(f"  python emergency_stop.py")
    print()
    
    print(f"{Colors.BOLD}View Today's Log:{Colors.RESET}")
    today = datetime.now().strftime("%Y%m%d")
    print(f"  cat trading_log_{today}.log")
    print()
    
    print(f"{Colors.BOLD}Check for Errors:{Colors.RESET}")
    print(f"  grep -i 'error\\|critical' trading_log_{today}.log")
    print()
    
    print(f"{Colors.BOLD}Run Execution:{Colors.RESET}")
    print(f"  python execution_engine.py")
    print()
    
    print(f"{Colors.BOLD}Run Tests:{Colors.RESET}")
    print(f"  python test_execution.py")


def main():
    """Main monitoring dashboard"""
    os.system('clear' if os.name == 'posix' else 'cls')
    
    print(f"\n{Colors.BOLD}{Colors.MAGENTA}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.MAGENTA}{'TRADING BOT - MONITORING DASHBOARD'.center(70)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.MAGENTA}{'='*70}{Colors.RESET}")
    print(f"{Colors.CYAN}Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.RESET}")
    
    try:
        monitor_daily_pnl()
        monitor_capital()
        monitor_open_positions()
        monitor_pending_orders()
        monitor_system_health()
        show_quick_actions()
        
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}{'='*70}{Colors.RESET}\n")
        
    except Exception as e:
        print(f"\n{Colors.RED}Error running monitor: {e}{Colors.RESET}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()