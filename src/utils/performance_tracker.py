"""
Performance Tracker - Historical Analysis
========================================
Analyze trading bot performance over time with comprehensive metrics.

Usage:
    from src.utils.performance_tracker import PerformanceTracker
    tracker = PerformanceTracker()
    tracker.analyze_performance(days=30)
"""

import json
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Any
import logging
from pathlib import Path


# Add parent directory to path for imports (allows running as script or module)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

logger = logging.getLogger(__name__)
from src.core.state_manager import StateManager


class Colors:
    """ANSI color codes"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    MAGENTA = '\033[95m'


class PerformanceTracker:
    """
    Comprehensive performance analysis for trading bot.
    
    Tracks and analyzes:
    - Daily P&L trends
    - Win/Loss ratios
    - Average returns
    - Drawdowns
    - Trade frequency
    - Sector performance
    """
    
    def __init__(self, state_dir: str = "state", mode: str = "paper"):
        """
        Initialize performance tracker.
        
        Args:
            state_dir: Base state directory
            mode: Trading mode (paper, live, backtest)
        """
        self.state_dir = state_dir
        self.mode = mode.lower()
        
        # Mode-specific state directory
        self.mode_state_dir = f"{state_dir}/{self.mode}"
        self.state = StateManager(self.mode_state_dir)
        
        logger.info(f"Performance tracker initialized for {mode.upper()} mode")
    
    def analyze_performance(self, days: int = 30):
        """
        Run comprehensive performance analysis.
        
        Args:
            days: Number of days to analyze
        """
        self._print_header(f"PERFORMANCE ANALYSIS - {self.mode.upper()} MODE ({days} DAYS)")
        
        # Load historical data
        daily_data = self._load_daily_pnl_history(days)
        trade_data = self._load_trade_history(days)
        
        if not daily_data and not trade_data:
            print(f"{Colors.YELLOW}No historical data found for analysis{Colors.RESET}")
            return
        
        # Performance metrics
        self._display_summary_metrics(daily_data, trade_data)
        
        # Daily P&L trend
        self._display_daily_trends(daily_data)
        
        # Trade analysis
        self._display_trade_analysis(trade_data)
        
        # Sector performance
        self._display_sector_performance(trade_data)
        
        # Risk metrics
        self._display_risk_metrics(daily_data)
        
        print(f"\n{Colors.CYAN}Analysis completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.RESET}")
    
    def _load_daily_pnl_history(self, days: int) -> List[Dict[str, Any]]:
        """Load historical daily P&L data"""
        daily_data = []
        
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            
            # Check multiple possible locations for P&L files
            possible_files = [
                f"{self.mode_state_dir}/daily_pnl.json",
                f"{self.mode_state_dir}/daily_pnl_{date}.json",
                f"{self.state_dir}/backups/daily_pnl_{date}.json"
            ]
            
            for filename in possible_files:
                if os.path.exists(filename):
                    try:
                        with open(filename, "r") as f:
                            data = json.load(f)
                            if data.get("date") == date:
                                daily_data.append(data)
                                break
                    except Exception as e:
                        logger.debug(f"Failed to load {filename}: {e}")
        
        return sorted(daily_data, key=lambda x: x.get("date", ""))
    
    def _load_trade_history(self, days: int) -> List[Dict[str, Any]]:
        """Load historical trade data"""
        try:
            trades_file = f"{self.mode_state_dir}/trades.json"
            if not os.path.exists(trades_file):
                return []
            
            with open(trades_file, "r") as f:
                all_trades = json.load(f)
            
            # Filter trades within the date range
            cutoff_date = (datetime.now() - timedelta(days=days)).date()
            
            filtered_trades = []
            for trade in all_trades:
                try:
                    if trade.get('exit_time'):
                        trade_date = datetime.fromisoformat(
                            trade['exit_time'].replace('Z', '')
                        ).date()
                        if trade_date >= cutoff_date:
                            filtered_trades.append(trade)
                except:
                    continue
            
            return filtered_trades
            
        except Exception as e:
            logger.debug(f"Failed to load trade history: {e}")
            return []
    
    def _display_summary_metrics(self, daily_data: List[Dict], trade_data: List[Dict]):
        """Display high-level summary metrics"""
        self._print_section_header("SUMMARY METRICS")
        
        if not daily_data and not trade_data:
            print(f"  {Colors.YELLOW}No data available{Colors.RESET}")
            return
        
        # Calculate metrics from daily data
        if daily_data:
            total_pnl = sum(day.get('realized_pnl', 0) for day in daily_data)
            total_trades = sum(day.get('total_trades', 0) for day in daily_data)
            winning_days = len([d for d in daily_data if d.get('realized_pnl', 0) > 0])
            
            avg_daily_pnl = total_pnl / len(daily_data) if daily_data else 0
            win_day_pct = (winning_days / len(daily_data)) * 100 if daily_data else 0
        else:
            total_pnl = sum(t.get('realized_pnl', 0) for t in trade_data)
            total_trades = len(trade_data)
            avg_daily_pnl = 0
            win_day_pct = 0
        
        # Trade-level metrics
        if trade_data:
            winning_trades = len([t for t in trade_data if t.get('realized_pnl', 0) > 0])
            win_rate = (winning_trades / len(trade_data)) * 100 if trade_data else 0
            
            profitable_trades = [t['realized_pnl'] for t in trade_data if t.get('realized_pnl', 0) > 0]
            losing_trades = [t['realized_pnl'] for t in trade_data if t.get('realized_pnl', 0) < 0]
            
            avg_win = sum(profitable_trades) / len(profitable_trades) if profitable_trades else 0
            avg_loss = sum(losing_trades) / len(losing_trades) if losing_trades else 0
            
            # Risk-reward ratio
            risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        else:
            win_rate = 0
            avg_win = 0
            avg_loss = 0
            risk_reward = 0
        
        pnl_color = Colors.GREEN if total_pnl >= 0 else Colors.RED
        
        print(f"  Total P&L: {pnl_color}₹{total_pnl:+,.2f}{Colors.RESET}")
        print(f"  Total Trades: {total_trades}")
        print(f"  Win Rate: {Colors.GREEN if win_rate > 50 else Colors.RED}{win_rate:.1f}%{Colors.RESET}")
        print(f"  Avg Daily P&L: ₹{avg_daily_pnl:+,.2f}")
        print(f"  Winning Days: {win_day_pct:.1f}%")
        print(f"  Avg Win: {Colors.GREEN}₹{avg_win:+,.2f}{Colors.RESET}")
        print(f"  Avg Loss: {Colors.RED}₹{avg_loss:+,.2f}{Colors.RESET}")
        print(f"  Risk:Reward: {Colors.GREEN if risk_reward > 1 else Colors.RED}{risk_reward:.2f}:1{Colors.RESET}")
    
    def _display_daily_trends(self, daily_data: List[Dict]):
        """Display daily P&L trends"""
        self._print_section_header("DAILY P&L TRENDS")
        
        if not daily_data:
            print(f"  {Colors.YELLOW}No daily P&L data{Colors.RESET}")
            return
        
        print(f"  {'Date':<12} {'P&L':<12} {'P&L%':<8} {'Trades':<8} {'Status':<10}")
        print(f"  {'-'*55}")
        
        for day in daily_data[-10:]:  # Last 10 days
            date = day.get('date', 'N/A')
            pnl = day.get('realized_pnl', 0)
            pnl_pct = (pnl / day.get('starting_capital', 1)) * 100
            trades = day.get('total_trades', 0)
            
            pnl_color = Colors.GREEN if pnl >= 0 else Colors.RED
            status = "🟢 WIN" if pnl > 0 else "🔴 LOSS" if pnl < 0 else "⚪ FLAT"
            
            print(
                f"  {date:<12} {pnl_color}₹{pnl:+8.2f}{Colors.RESET} "
                f"{pnl_color}{pnl_pct:+6.2f}%{Colors.RESET} {trades:<8} {status:<10}"
            )
    
    def _display_trade_analysis(self, trade_data: List[Dict]):
        """Display detailed trade analysis"""
        self._print_section_header("TRADE ANALYSIS")
        
        if not trade_data:
            print(f"  {Colors.YELLOW}No trade data{Colors.RESET}")
            return
        
        # Group by symbol
        symbol_performance = defaultdict(lambda: {'count': 0, 'pnl': 0, 'wins': 0})
        
        for trade in trade_data:
            symbol = trade.get('symbol', 'UNKNOWN')
            pnl = trade.get('realized_pnl', 0)
            
            symbol_performance[symbol]['count'] += 1
            symbol_performance[symbol]['pnl'] += pnl
            if pnl > 0:
                symbol_performance[symbol]['wins'] += 1
        
        # Sort by total P&L
        sorted_symbols = sorted(
            symbol_performance.items(),
            key=lambda x: x[1]['pnl'],
            reverse=True
        )
        
        print(f"  {'Symbol':<12} {'Trades':<8} {'P&L':<12} {'Win%':<8} {'Avg P&L':<10}")
        print(f"  {'-'*55}")
        
        for symbol, stats in sorted_symbols[:10]:  # Top 10
            count = stats['count']
            total_pnl = stats['pnl']
            win_rate = (stats['wins'] / count) * 100
            avg_pnl = total_pnl / count
            
            pnl_color = Colors.GREEN if total_pnl >= 0 else Colors.RED
            
            print(
                f"  {symbol:<12} {count:<8} {pnl_color}₹{total_pnl:+8.2f}{Colors.RESET} "
                f"{win_rate:6.1f}% {pnl_color}₹{avg_pnl:+8.2f}{Colors.RESET}"
            )
    
    def _display_sector_performance(self, trade_data: List[Dict]):
        """Display sector-wise performance"""
        self._print_section_header("SECTOR PERFORMANCE")
        
        if not trade_data:
            print(f"  {Colors.YELLOW}No trade data{Colors.RESET}")
            return
        
        # Group by sector
        sector_performance = defaultdict(lambda: {'count': 0, 'pnl': 0, 'wins': 0})
        
        for trade in trade_data:
            sector = trade.get('sector', 'UNKNOWN')
            pnl = trade.get('realized_pnl', 0)
            
            sector_performance[sector]['count'] += 1
            sector_performance[sector]['pnl'] += pnl
            if pnl > 0:
                sector_performance[sector]['wins'] += 1
        
        # Sort by total P&L
        sorted_sectors = sorted(
            sector_performance.items(),
            key=lambda x: x[1]['pnl'],
            reverse=True
        )
        
        print(f"  {'Sector':<15} {'Trades':<8} {'P&L':<12} {'Win%':<8} {'Avg P&L':<10}")
        print(f"  {'-'*60}")
        
        for sector, stats in sorted_sectors:
            count = stats['count']
            total_pnl = stats['pnl']
            win_rate = (stats['wins'] / count) * 100
            avg_pnl = total_pnl / count
            
            pnl_color = Colors.GREEN if total_pnl >= 0 else Colors.RED
            
            print(
                f"  {sector:<15} {count:<8} {pnl_color}₹{total_pnl:+8.2f}{Colors.RESET} "
                f"{win_rate:6.1f}% {pnl_color}₹{avg_pnl:+8.2f}{Colors.RESET}"
            )
    
    def _display_risk_metrics(self, daily_data: List[Dict]):
        """Display risk and drawdown metrics"""
        self._print_section_header("RISK METRICS")
        
        if not daily_data:
            print(f"  {Colors.YELLOW}No daily data for risk analysis{Colors.RESET}")
            return
        
        # Calculate drawdown
        cumulative_pnl = 0
        peak = 0
        max_drawdown = 0
        current_drawdown = 0
        
        daily_returns = []
        
        for day in daily_data:
            daily_pnl = day.get('realized_pnl', 0)
            starting_capital = day.get('starting_capital', 100000)  # Default fallback
            
            cumulative_pnl += daily_pnl
            
            if cumulative_pnl > peak:
                peak = cumulative_pnl
                current_drawdown = 0
            else:
                current_drawdown = peak - cumulative_pnl
                max_drawdown = max(max_drawdown, current_drawdown)
            
            # Daily return percentage
            daily_return = (daily_pnl / starting_capital) * 100
            daily_returns.append(daily_return)
        
        # Calculate volatility (standard deviation of daily returns)
        if len(daily_returns) > 1:
            mean_return = sum(daily_returns) / len(daily_returns)
            variance = sum((r - mean_return) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
            volatility = variance ** 0.5
        else:
            volatility = 0
        
        # Sharpe ratio (assuming 0% risk-free rate)
        sharpe_ratio = (mean_return / volatility) if volatility > 0 else 0
        
        drawdown_color = Colors.GREEN if max_drawdown < 1000 else Colors.YELLOW if max_drawdown < 5000 else Colors.RED
        
        print(f"  Max Drawdown: {drawdown_color}₹{max_drawdown:,.2f}{Colors.RESET}")
        print(f"  Current Drawdown: ₹{current_drawdown:,.2f}")
        print(f"  Daily Volatility: {volatility:.2f}%")
        print(f"  Sharpe Ratio: {Colors.GREEN if sharpe_ratio > 1 else Colors.YELLOW if sharpe_ratio > 0 else Colors.RED}{sharpe_ratio:.2f}{Colors.RESET}")
        
        # Risk-adjusted metrics
        if len(daily_data) > 0:
            total_pnl = sum(d.get('realized_pnl', 0) for d in daily_data)
            risk_adjusted_return = total_pnl / max(max_drawdown, 1)  # Avoid division by zero
            
            print(f"  Risk-Adjusted Return: {risk_adjusted_return:.2f}")
    
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
    """CLI entry point for performance tracker"""
    import sys
    
    # Parse arguments
    days = 30
    mode = "paper"
    
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            mode = sys.argv[1]
    
    if len(sys.argv) > 2:
        mode = sys.argv[2]
    
    tracker = PerformanceTracker(mode=mode)
    
    try:
        tracker.analyze_performance(days=days)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Analysis interrupted{Colors.RESET}")
    except Exception as e:
        print(f"\n{Colors.RED}Analysis error: {e}{Colors.RESET}")


if __name__ == "__main__":
    main()