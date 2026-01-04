"""
PERFORMANCE TRACKER
-------------------
Analyze trading bot performance over time

Usage: python performance_tracker.py [days]
Example: python performance_tracker.py 30
"""

import json
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict

# ANSI Colors
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    MAGENTA = '\033[95m'

def load_daily_pnl_history(days: int = 30) -> list:
    """Load historical P&L data"""
    pnl_data = []
    
    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        
        # Try to find P&L file for this date
        # Could be named daily_pnl.json or have date suffix
        possible_files = [
            "daily_pnl.json",
            f"daily_pnl_{date}.json",
            f"backups/daily_pnl_{date}.json"
        ]
        
        for filename in possible_files:
            if os.path.exists(filename):
                try:
                    with open(filename, "r") as f:
                        data = json.load(f)
                        if data.get("date") == date:
                            pnl_data.append(data)
                            break
                except:
                    pass
    
    return sorted(pnl_data, key=lambda x: x.get("date", ""))


def analyze_performance(pnl_data: list):
    """Analyze and display performance metrics"""
    
    if not pnl_data:
        print(f"{Colors.RED}No historical data found{Colors.RESET}")
        return
    
    # Calculate metrics
    total_realized = sum(d.get("realized_pnl", 0) for d in pnl_data)
    total_unrealized = sum(d.get("unrealized_pnl", 0) for d in pnl_data)
    total_pnl = total_realized + total_unrealized
    total_trades = sum(d.get("trades_executed", 0) for d in pnl_data)
    
    # Daily P&L values
    daily_pnls = []
    daily_pcts = []
    for d in pnl_data:
        realized = d.get("realized_pnl", 0)
        unrealized = d.get("unrealized_pnl", 0)
        capital = d.get("starting_capital", 25000)
        
        daily_total = realized + unrealized
        daily_pct = (daily_total / capital * 100) if capital > 0 else 0
        
        daily_pnls.append(daily_total)
        daily_pcts.append(daily_pct)
    
    # Win rate
    winning_days = sum(1 for pnl in daily_pnls if pnl > 0)
    losing_days = sum(1 for pnl in daily_pnls if pnl < 0)
    flat_days = sum(1 for pnl in daily_pnls if pnl == 0)
    
    win_rate = (winning_days / len(daily_pnls) * 100) if daily_pnls else 0
    
    # Best/worst days
    best_day = max(daily_pnls) if daily_pnls else 0
    worst_day = min(daily_pnls) if daily_pnls else 0
    avg_daily = sum(daily_pnls) / len(daily_pnls) if daily_pnls else 0
    
    # Max drawdown
    peak = daily_pnls[0] if daily_pnls else 0
    max_drawdown = 0
    cumulative = 0
    
    for pnl in daily_pnls:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        drawdown = peak - cumulative
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    # Display results
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}PERFORMANCE SUMMARY - Last {len(pnl_data)} Trading Days{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}\n")
    
    # Overall P&L
    print(f"{Colors.BOLD}📊 PROFIT & LOSS{Colors.RESET}")
    print(f"{'─'*70}")
    
    color = Colors.GREEN if total_pnl > 0 else Colors.RED if total_pnl < 0 else Colors.YELLOW
    print(f"Total P&L: {color}₹{total_pnl:,.2f}{Colors.RESET}")
    print(f"  Realized: {Colors.GREEN if total_realized > 0 else Colors.RED}₹{total_realized:,.2f}{Colors.RESET}")
    print(f"  Unrealized: {Colors.YELLOW}₹{total_unrealized:,.2f}{Colors.RESET}")
    
    avg_capital = sum(d.get("starting_capital", 25000) for d in pnl_data) / len(pnl_data)
    total_pct = (total_pnl / avg_capital * 100) if avg_capital > 0 else 0
    print(f"Total Return: {color}{total_pct:+.2f}%{Colors.RESET}")
    print()
    
    # Trading activity
    print(f"{Colors.BOLD}📈 TRADING ACTIVITY{Colors.RESET}")
    print(f"{'─'*70}")
    print(f"Total Trades: {Colors.BLUE}{total_trades}{Colors.RESET}")
    print(f"Trading Days: {len(pnl_data)}")
    print(f"Avg Trades/Day: {total_trades/len(pnl_data):.1f}")
    print()
    
    # Win rate
    print(f"{Colors.BOLD}🎯 WIN RATE{Colors.RESET}")
    print(f"{'─'*70}")
    
    win_color = Colors.GREEN if win_rate >= 50 else Colors.YELLOW if win_rate >= 40 else Colors.RED
    print(f"Win Rate: {win_color}{win_rate:.1f}%{Colors.RESET}")
    print(f"  Winning Days: {Colors.GREEN}{winning_days}{Colors.RESET}")
    print(f"  Losing Days: {Colors.RED}{losing_days}{Colors.RESET}")
    print(f"  Flat Days: {Colors.YELLOW}{flat_days}{Colors.RESET}")
    print()
    
    # Daily statistics
    print(f"{Colors.BOLD}📉 DAILY STATISTICS{Colors.RESET}")
    print(f"{'─'*70}")
    print(f"Best Day: {Colors.GREEN}₹{best_day:,.2f}{Colors.RESET}")
    print(f"Worst Day: {Colors.RED}₹{worst_day:,.2f}{Colors.RESET}")
    print(f"Average Day: {Colors.CYAN}₹{avg_daily:,.2f}{Colors.RESET}")
    print(f"Max Drawdown: {Colors.RED}₹{max_drawdown:,.2f}{Colors.RESET}")
    print()
    
    # Risk metrics
    print(f"{Colors.BOLD}⚠️  RISK METRICS{Colors.RESET}")
    print(f"{'─'*70}")
    
    # Sharpe ratio (simplified - assumes 0% risk-free rate)
    if daily_pcts:
        import math
        mean_return = sum(daily_pcts) / len(daily_pcts)
        std_dev = math.sqrt(sum((x - mean_return)**2 for x in daily_pcts) / len(daily_pcts))
        sharpe = (mean_return / std_dev * math.sqrt(252)) if std_dev > 0 else 0
        
        sharpe_color = Colors.GREEN if sharpe > 1 else Colors.YELLOW if sharpe > 0.5 else Colors.RED
        print(f"Sharpe Ratio: {sharpe_color}{sharpe:.2f}{Colors.RESET}")
        print(f"Volatility: {std_dev:.2f}%")
    
    max_dd_pct = (max_drawdown / avg_capital * 100) if avg_capital > 0 else 0
    dd_color = Colors.GREEN if max_dd_pct < 5 else Colors.YELLOW if max_dd_pct < 10 else Colors.RED
    print(f"Max Drawdown %: {dd_color}{max_dd_pct:.2f}%{Colors.RESET}")
    print()
    
    # Health check
    print(f"{Colors.BOLD}💚 HEALTH CHECK{Colors.RESET}")
    print(f"{'─'*70}")
    
    health_flags = []
    
    if win_rate >= 50:
        health_flags.append(f"{Colors.GREEN}✓ Win rate healthy (>50%){Colors.RESET}")
    else:
        health_flags.append(f"{Colors.YELLOW}⚠ Win rate needs improvement (<50%){Colors.RESET}")
    
    if max_dd_pct < 10:
        health_flags.append(f"{Colors.GREEN}✓ Drawdown under control (<10%){Colors.RESET}")
    else:
        health_flags.append(f"{Colors.RED}✗ High drawdown (>10%){Colors.RESET}")
    
    if total_pnl > 0:
        health_flags.append(f"{Colors.GREEN}✓ Overall profitable{Colors.RESET}")
    else:
        health_flags.append(f"{Colors.RED}✗ Overall unprofitable{Colors.RESET}")
    
    if total_trades / len(pnl_data) < 5:
        health_flags.append(f"{Colors.GREEN}✓ Trade frequency reasonable (<5/day){Colors.RESET}")
    else:
        health_flags.append(f"{Colors.YELLOW}⚠ High trade frequency (>5/day){Colors.RESET}")
    
    for flag in health_flags:
        print(flag)
    
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}\n")


def show_daily_breakdown(pnl_data: list):
    """Show day-by-day breakdown"""
    
    print(f"\n{Colors.BOLD}{Colors.CYAN}DAILY BREAKDOWN{Colors.RESET}")
    print(f"{'─'*70}\n")
    
    print(f"{'Date':<12} {'P&L':>12} {'P&L%':>8} {'Trades':>8} {'Status':<10}")
    print(f"{'─'*70}")
    
    for d in reversed(pnl_data):  # Most recent first
        date = d.get("date", "Unknown")
        realized = d.get("realized_pnl", 0)
        unrealized = d.get("unrealized_pnl", 0)
        capital = d.get("starting_capital", 25000)
        trades = d.get("trades_executed", 0)
        
        total = realized + unrealized
        pct = (total / capital * 100) if capital > 0 else 0
        
        color = Colors.GREEN if total > 0 else Colors.RED if total < 0 else Colors.YELLOW
        status = "WIN" if total > 0 else "LOSS" if total < 0 else "FLAT"
        
        print(f"{date:<12} {color}₹{total:>10,.2f}{Colors.RESET} {color}{pct:>7.2f}%{Colors.RESET} {trades:>8} {status:<10}")
    
    print(f"{'─'*70}\n")


def main():
    """Main performance tracking function"""
    
    # Get number of days from command line
    days = 30
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except:
            print(f"Invalid number of days. Using default: 30")
    
    print(f"\n{Colors.BOLD}{Colors.MAGENTA}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.MAGENTA}TRADING BOT - PERFORMANCE ANALYSIS{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.MAGENTA}{'='*70}{Colors.RESET}")
    
    # Load data
    pnl_data = load_daily_pnl_history(days)
    
    if not pnl_data:
        print(f"\n{Colors.YELLOW}No performance data found.{Colors.RESET}")
        print(f"\n{Colors.CYAN}Note: This script looks for daily_pnl.json files.")
        print(f"Make sure the bot has been running and saving P&L data.{Colors.RESET}\n")
        return
    
    # Analyze and display
    analyze_performance(pnl_data)
    show_daily_breakdown(pnl_data)
    
    # Recommendations
    print(f"{Colors.BOLD}{Colors.YELLOW}💡 RECOMMENDATIONS{Colors.RESET}")
    print(f"{'─'*70}")
    
    total_pnl = sum(d.get("realized_pnl", 0) + d.get("unrealized_pnl", 0) for d in pnl_data)
    win_rate = sum(1 for d in pnl_data if (d.get("realized_pnl", 0) + d.get("unrealized_pnl", 0)) > 0) / len(pnl_data) * 100
    
    if total_pnl < 0 and win_rate < 40:
        print(f"{Colors.RED}Strategy needs significant revision. Consider:{Colors.RESET}")
        print("  • Review and tighten screener rules")
        print("  • Reduce position sizes")
        print("  • Adjust stop loss levels")
        print("  • Analyze losing trades for patterns")
    elif win_rate < 50:
        print(f"{Colors.YELLOW}Strategy shows potential but needs tuning:{Colors.RESET}")
        print("  • Analyze losing trades")
        print("  • Consider adjusting partial exit levels")
        print("  • Review sector allocation")
    else:
        print(f"{Colors.GREEN}Strategy performing well. Consider:{Colors.RESET}")
        print("  • Gradually increasing position sizes")
        print("  • Fine-tuning entry/exit rules")
        print("  • Maintaining current risk management")
    
    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    main()