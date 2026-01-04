"""
Timing Rules - Regime-Specific Entry and Exit Timing
==================================================
Different timing strategies based on market regimes.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, time
from typing import Dict, Tuple, Optional

from ..core.models import ScreenerSignal


logger = logging.getLogger(__name__)


class TimingRules(ABC):
    """
    Abstract base class for timing rules.
    """
    
    def __init__(self):
        self.name = "BASE_TIMING_RULES"
    
    @abstractmethod
    def can_enter_now(self, signal: ScreenerSignal, current_time: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Check if entry is allowed now.
        
        Args:
            signal: Screener signal
            current_time: Current time (defaults to now)
            
        Returns:
            (can_enter, reason)
        """
        pass
    
    @abstractmethod
    def get_optimal_exit_time(self, position: dict, current_time: Optional[datetime] = None) -> Optional[str]:
        """
        Get optimal exit timing for position.
        
        Args:
            position: Position dictionary
            current_time: Current time
            
        Returns:
            Exit reason if should exit now, None to continue
        """
        pass
    
    @abstractmethod
    def get_entry_windows(self) -> Dict[str, Tuple[time, time]]:
        """
        Get allowed entry time windows.
        
        Returns:
            Dict of window_name: (start_time, end_time)
        """
        pass


class BullMarketRules(TimingRules):
    """
    Aggressive timing rules for bull market conditions.
    """
    
    def __init__(self):
        self.name = "BULL_MARKET"
        # Bull market: More aggressive, wider windows
        self.entry_windows = {
            'MARKET_OPEN': (time(9, 20), time(10, 0)),   # Early momentum
            'MID_MORNING': (time(10, 30), time(11, 30)), # Sustained moves
            'AFTERNOON': (time(14, 0), time(14, 45)),    # Final push
        }
        self.min_signal_score = 30  # Lower threshold in bull market - more aggressive
        
    def can_enter_now(self, signal: ScreenerSignal, current_time: Optional[datetime] = None) -> Tuple[bool, str]:
        if current_time is None:
            current_time = datetime.now()
        
        current_time_only = current_time.time()
        
        # Check signal quality (relaxed in bull market)
        if signal.score < self.min_signal_score:
            return False, f"Signal score {signal.score} below bull market threshold {self.min_signal_score}"
        
        # Check time windows
        in_window = False
        for window_name, (start, end) in self.entry_windows.items():
            if start <= current_time_only <= end:
                in_window = True
                break
        
        if not in_window:
            return False, "Outside bull market entry windows"
        
        # Additional bull market checks
        if signal.trend != 'BULLISH':
            return False, "Require bullish trend in bull market"
        
        return True, f"Bull market entry approved in {window_name}"
    
    def get_optimal_exit_time(self, position: dict, current_time: Optional[datetime] = None) -> Optional[str]:
        if current_time is None:
            current_time = datetime.now()
        
        current_time_only = current_time.time()
        
        # Bull market: Hold longer, exit near close if losing
        entry_time = datetime.fromisoformat(position['entry_time'])
        days_held = (current_time - entry_time).days
        
        # Don't exit winners early in bull market
        unrealized_pnl_pct = position.get('unrealized_pnl_pct', 0)
        if unrealized_pnl_pct > 2.0 and days_held < 3:
            return None  # Let winners run
        
        # Exit losers before market close
        if (unrealized_pnl_pct < -3.0 and 
            current_time_only >= time(15, 0)):
            return "TIME_EXIT_BULL_LOSER"
        
        return None
    
    def get_entry_windows(self) -> Dict[str, Tuple[time, time]]:
        return self.entry_windows


class BearMarketRules(TimingRules):
    """
    Conservative timing rules for bear market conditions.
    """
    
    def __init__(self):
        self.name = "BEAR_MARKET"
        # Bear market: Conservative, narrow windows
        self.entry_windows = {
            'LATE_MORNING': (time(11, 0), time(11, 30)),  # Wait for stability
            'AFTERNOON': (time(14, 30), time(15, 0)),     # Late entries only
        }
        self.min_signal_score = 50  # Higher threshold in bear market
        
    def can_enter_now(self, signal: ScreenerSignal, current_time: Optional[datetime] = None) -> Tuple[bool, str]:
        if current_time is None:
            current_time = datetime.now()
        
        current_time_only = current_time.time()
        
        # Strict signal quality in bear market
        if signal.score < self.min_signal_score:
            return False, f"Signal score {signal.score} below bear market threshold {self.min_signal_score}"
        
        # Check time windows
        in_window = False
        window_name = "NONE"
        for name, (start, end) in self.entry_windows.items():
            if start <= current_time_only <= end:
                in_window = True
                window_name = name
                break
        
        if not in_window:
            return False, "Outside bear market entry windows"
        
        # Additional bear market checks
        if signal.volume_ratio < 1.5:
            return False, "Require high volume conviction in bear market"
        
        return True, f"Bear market entry approved in {window_name}"
    
    def get_optimal_exit_time(self, position: dict, current_time: Optional[datetime] = None) -> Optional[str]:
        if current_time is None:
            current_time = datetime.now()
        
        current_time_only = current_time.time()
        
        # Bear market: Exit quickly on any profit
        unrealized_pnl_pct = position.get('unrealized_pnl_pct', 0)
        
        # Take profits quickly in bear market
        if unrealized_pnl_pct > 1.0:
            return "TIME_EXIT_BEAR_PROFIT"
        
        # Exit all positions before 3 PM in bear market
        if current_time_only >= time(15, 0):
            return "TIME_EXIT_BEAR_EOD"
        
        return None
    
    def get_entry_windows(self) -> Dict[str, Tuple[time, time]]:
        return self.entry_windows


class SidewaysRules(TimingRules):
    """
    Balanced timing rules for sideways/ranging market conditions.
    """
    
    def __init__(self):
        self.name = "SIDEWAYS"
        # Sideways market: Moderate approach
        self.entry_windows = {
            'MARKET_OPEN': (time(9, 25), time(9, 45)),    # Early moves
            'MID_MORNING': (time(10, 30), time(11, 15)),  # Breakouts
            'MIDDAY': (time(12, 30), time(13, 30)),       # Lunch time opportunities
            'AFTERNOON': (time(14, 0), time(14, 30)),     # Final session
        }
        self.min_signal_score = 30  # Lowered threshold for more opportunities
        
    def can_enter_now(self, signal: ScreenerSignal, current_time: Optional[datetime] = None) -> Tuple[bool, str]:
        if current_time is None:
            current_time = datetime.now()
        
        current_time_only = current_time.time()
        
        # Check signal quality
        if signal.score < self.min_signal_score:
            return False, f"Signal score {signal.score} below sideways threshold {self.min_signal_score}"
        
        # Check time windows
        in_window = False
        window_name = "NONE"
        for name, (start, end) in self.entry_windows.items():
            if start <= current_time_only <= end:
                in_window = True
                window_name = name
                break
        
        if not in_window:
            return False, "Outside sideways market entry windows"
        
        # Balanced requirements for sideways market
        if signal.volume_ratio < 1.1:
            return False, "Require moderate volume in sideways market"
        
        return True, f"Sideways market entry approved in {window_name}"
    
    def get_optimal_exit_time(self, position: dict, current_time: Optional[datetime] = None) -> Optional[str]:
        if current_time is None:
            current_time = datetime.now()
        
        current_time_only = current_time.time()
        
        # Sideways market: Moderate holding periods
        entry_time = datetime.fromisoformat(position['entry_time'])
        hours_held = (current_time - entry_time).total_seconds() / 3600
        
        # Exit if held for more than 6 hours without significant move
        unrealized_pnl_pct = position.get('unrealized_pnl_pct', 0)
        if hours_held > 6 and abs(unrealized_pnl_pct) < 1.0:
            return "TIME_EXIT_SIDEWAYS_STALE"
        
        return None
    
    def get_entry_windows(self) -> Dict[str, Tuple[time, time]]:
        return self.entry_windows


class VolatilityRules(TimingRules):
    """
    Cautious timing rules for high volatility conditions.
    """
    
    def __init__(self):
        self.name = "HIGH_VOLATILITY"
        # High volatility: Very narrow windows, wait for calm
        self.entry_windows = {
            'MID_MORNING': (time(11, 0), time(11, 15)),  # Small calm window
            'LATE_AFTERNOON': (time(14, 45), time(15, 0)), # Final 15 min only
        }
        self.min_signal_score = 60  # Very high threshold in volatility
        
    def can_enter_now(self, signal: ScreenerSignal, current_time: Optional[datetime] = None) -> Tuple[bool, str]:
        if current_time is None:
            current_time = datetime.now()
        
        current_time_only = current_time.time()
        
        # Very strict signal quality in volatile market
        if signal.score < self.min_signal_score:
            return False, f"Signal score {signal.score} below volatility threshold {self.min_signal_score}"
        
        # Check very narrow time windows
        in_window = False
        window_name = "NONE"
        for name, (start, end) in self.entry_windows.items():
            if start <= current_time_only <= end:
                in_window = True
                window_name = name
                break
        
        if not in_window:
            return False, "Outside volatility market entry windows"
        
        # Strict requirements for volatile market
        if signal.volume_ratio < 2.0:
            return False, "Require very high volume in volatile market"
            
        if signal.adx < 30:
            return False, "Require strong trend in volatile market"
        
        return True, f"Volatility market entry approved in {window_name}"
    
    def get_optimal_exit_time(self, position: dict, current_time: Optional[datetime] = None) -> Optional[str]:
        if current_time is None:
            current_time = datetime.now()
        
        current_time_only = current_time.time()
        
        # Volatile market: Exit quickly
        entry_time = datetime.fromisoformat(position['entry_time'])
        minutes_held = (current_time - entry_time).total_seconds() / 60
        
        # Exit after 2 hours max in volatile conditions
        if minutes_held > 120:
            return "TIME_EXIT_VOLATILITY_TIMEOUT"
        
        # Take small profits quickly
        unrealized_pnl_pct = position.get('unrealized_pnl_pct', 0)
        if unrealized_pnl_pct > 0.5:
            return "TIME_EXIT_VOLATILITY_PROFIT"
        
        return None
    
    def get_entry_windows(self) -> Dict[str, Tuple[time, time]]:
        return self.entry_windows