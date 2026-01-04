"""
Timing Filter - Entry and Exit Timing Intelligence
================================================
Main timing filter that coordinates timing decisions using market regime and rules.
"""

import logging
from datetime import datetime, time, date
from typing import Dict, Tuple, Optional, List

from ..core.models import ScreenerSignal
from .market_regime import MarketRegimeManager, MarketRegime
from .timing_rules import TimingRules


logger = logging.getLogger(__name__)


class TimingFilter:
    """
    Central timing filter that makes entry and exit timing decisions.
    """
    
    def __init__(self, regime_manager: Optional[MarketRegimeManager] = None, state_manager = None):
        """
        Initialize timing filter.
        
        Args:
            regime_manager: Optional market regime manager (creates new if None)
            state_manager: State manager for checking positions/orders (optional)
        """
        self.regime_manager = regime_manager or MarketRegimeManager()
        self.state_manager = state_manager
        
        # Basic market hours (IST)
        self.market_open = time(9, 15)
        self.market_close = time(15, 30)
        self.pre_close = time(15, 15)  # Stop new entries 15 min before close
        
        # Global timing settings
        self.max_daily_entries = 10
        self.daily_entry_count = 0
        self.last_reset_date = datetime.now().date()
        
        # Symbol entry tracking to prevent rapid duplicates
        self.recent_entry_attempts = {}  # symbol -> last_attempt_time
        self.min_entry_interval_minutes = 5  # Don't attempt same symbol within 5 minutes
        
        logger.info("Timing filter initialized")
    
    def should_enter_now(
        self, 
        signal: ScreenerSignal, 
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Main entry timing decision.
        
        Args:
            signal: Screener signal to evaluate
            current_time: Current time (defaults to now)
            
        Returns:
            (should_enter, reason)
        """
        if current_time is None:
            current_time = datetime.now()
        
        symbol = signal.symbol
        
        # FIRST CHECK: Duplicate position prevention (if state manager available)
        if self.state_manager:
            positions = self.state_manager.load_positions()
            if symbol in positions and positions[symbol].get('qty_remaining', 0) > 0:
                qty_remaining = positions[symbol].get('qty_remaining', 0)
                entry_price = positions[symbol].get('entry_price', 0)
                logger.warning(
                    f"TIMING FILTER DUPLICATE BLOCK: {symbol} already in position | "
                    f"qty_remaining: {qty_remaining} | entry_price: Rs.{entry_price:.2f}"
                )
                return False, f"Already in position - {qty_remaining} shares @ Rs.{entry_price:.2f}"
            
            # Also check pending orders
            pending_orders = self.state_manager.load_orders()
            for order_id, order_data in pending_orders.items():
                if (order_data.get('symbol') == symbol and 
                    order_data.get('status') in ['PENDING', 'PLACED', 'OPEN']):
                    logger.warning(
                        f"TIMING FILTER DUPLICATE BLOCK: {symbol} has pending order | "
                        f"order_id: {order_id}"
                    )
                    return False, f"Pending order exists - {order_id}"
        
        # SECOND CHECK: Recent entry attempt tracking 
        current_timestamp = current_time.timestamp()
        if symbol in self.recent_entry_attempts:
            last_attempt = self.recent_entry_attempts[symbol]
            time_since_last = (current_timestamp - last_attempt) / 60  # minutes
            if time_since_last < self.min_entry_interval_minutes:
                logger.info(
                    f"TIMING FILTER RAPID BLOCK: {symbol} attempted {time_since_last:.1f} mins ago | "
                    f"min interval: {self.min_entry_interval_minutes} mins"
                )
                return False, f"Recent entry attempt {time_since_last:.1f}m ago (min: {self.min_entry_interval_minutes}m)"
        
        # Record this attempt
        self.recent_entry_attempts[symbol] = current_timestamp
        
        # Reset daily counters
        self._reset_daily_counters(current_time.date())
        
        # 1. Basic market hours check
        can_trade, reason = self._check_market_hours(current_time)
        if not can_trade:
            return False, reason
        
        # 2. Check daily limits
        if self.daily_entry_count >= self.max_daily_entries:
            return False, f"Daily entry limit reached ({self.max_daily_entries})"
        
        # 3. Global market regime check
        if not self.regime_manager.should_trade_now():
            return False, "Market regime prohibits trading"
        
        # 4. Get regime-specific timing rules
        self.regime_manager.detect_regime()  # Refresh if needed
        timing_rules = self.regime_manager.get_timing_rules()
        
        # 5. Apply regime-specific entry rules
        can_enter, regime_reason = timing_rules.can_enter_now(signal, current_time)
        if not can_enter:
            return False, f"Regime timing: {regime_reason}"
        
        # 6. Additional signal quality checks
        quality_check, quality_reason = self._check_signal_quality(signal)
        if not quality_check:
            return False, f"Signal quality: {quality_reason}"
        
        # All checks passed - approve entry
        # NOTE: Don't increment counter here - do it when order is actually placed
        
        regime_info = self.regime_manager.get_regime_info()
        logger.info(
            f"TIMING ENTRY APPROVED: {symbol} | "
            f"Regime: {regime_info['regime']} | "
            f"Score: {signal.score} | "
            f"Daily entries: {self.daily_entry_count}/{self.max_daily_entries}"
        )
        
        return True, f"Entry approved ({timing_rules.name})"
    
 
    
    def should_exit_now(
        self, 
        position: dict, 
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Check if position should exit based on timing.
        
        Args:
            position: Position dictionary
            current_time: Current time (defaults to now)
            
        Returns:
            (should_exit, exit_reason)
        """
        if current_time is None:
            current_time = datetime.now()
        
        # 1. End of day check
        current_time_only = current_time.time()
        if current_time_only >= self.pre_close:
            return True, "EOD_EXIT"
        
        # 2. Get regime-specific exit rules
        timing_rules = self.regime_manager.get_timing_rules()
        
        # 3. Check regime-specific exit timing
        exit_reason = timing_rules.get_optimal_exit_time(position, current_time)
        if exit_reason:
            return True, exit_reason
        
        return False, "No timing exit required"
    
    def get_timing_info(self) -> Dict:
        """
        Get current timing filter status.
        
        Returns:
            Dict with timing information
        """
        regime_info = self.regime_manager.get_regime_info()
        timing_rules = self.regime_manager.get_timing_rules()
        
        return {
            'current_time': datetime.now().isoformat(),
            'market_regime': regime_info,
            'timing_rules': timing_rules.name,
            'daily_entries': f"{self.daily_entry_count}/{self.max_daily_entries}",
            'entry_windows': timing_rules.get_entry_windows(),
            'market_hours': {
                'open': self.market_open.isoformat(),
                'close': self.market_close.isoformat(),
                'pre_close': self.pre_close.isoformat()
            }
        }
    
    def _check_market_hours(self, current_time: datetime) -> Tuple[bool, str]:
        """
        Check if current time is within trading hours.
        
        Args:
            current_time: Time to check
            
        Returns:
            (can_trade, reason)
        """
        current_time_only = current_time.time()
        
        # Check if market is open
        if current_time_only < self.market_open:
            return False, f"Market not open yet (opens at {self.market_open})"
        
        # Check if too close to market close
        if current_time_only >= self.pre_close:
            return False, f"Too close to market close ({self.pre_close})"
        
        # Check weekends (basic check)
        if current_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False, "Market closed on weekend"
        
        return True, "Market hours OK"
    
    def _check_signal_quality(self, signal: ScreenerSignal) -> Tuple[bool, str]:
        """
        Additional signal quality checks beyond regime rules.
        
        Args:
            signal: Signal to check
            
        Returns:
            (quality_ok, reason)
        """
        # Minimum baseline requirements
        if signal.price <= 0:
            return False, "Invalid price"
        
        if signal.atr <= 0:
            return False, "Invalid ATR"
        
        # Volume requirement
        if hasattr(signal, 'volume_ratio') and signal.volume_ratio < 1.1:
            return False, f"Low volume ratio: {signal.volume_ratio}"
        
        # Price range check (avoid penny stocks and very expensive stocks)
        if signal.price < 10:
            return False, f"Price too low: ₹{signal.price}"
        
        if signal.price > 10000:
            return False, f"Price too high: ₹{signal.price}"
        
        return True, "Signal quality OK"
    
    def _reset_daily_counters(self, current_date) -> None:
        """
        Reset daily counters if new day.
        
        Args:
            current_date: Current date
        """
        if current_date != self.last_reset_date:
            self.daily_entry_count = 0
            self.last_reset_date = current_date
            
            # Also clean up old recent entry attempts (keep only last 24 hours)
            current_timestamp = datetime.now().timestamp()
            cutoff_time = current_timestamp - (24 * 60 * 60)  # 24 hours ago
            
            symbols_to_remove = [
                symbol for symbol, timestamp in self.recent_entry_attempts.items()
                if timestamp < cutoff_time
            ]
            
            for symbol in symbols_to_remove:
                del self.recent_entry_attempts[symbol]
            
            if symbols_to_remove:
                logger.info(f"Cleaned up {len(symbols_to_remove)} old entry attempts")
            
            logger.info(f"Daily counters reset for {current_date}")
    
    def record_entry_placed(self, symbol: str):
        """
        Record that an entry order was successfully placed.
        Only increment the daily counter when order is actually placed.
        
        Args:
            symbol: Symbol for which order was placed
        """
        self.daily_entry_count += 1
        logger.info(
            f"Entry recorded for {symbol} | "
            f"Daily entries: {self.daily_entry_count}/{self.max_daily_entries}"
        )
    
    def reset_for_new_session(self):
        """
        Reset daily counters for a new screener session.
        Use this when starting a fresh screening session to avoid
        carrying over counts from previous runs on the same day.
        """
        today = date.today()
        self.daily_entry_count = 0
        self.last_reset_date = today
        
        # Also clear recent entry attempts for fresh session
        self.recent_entry_attempts.clear()
        
        logger.info(f"Daily counters and recent attempts reset for new session on {today}")
    
    def update_regime_settings(self, **kwargs) -> None:
        """
        Update regime manager settings.
        
        Args:
            **kwargs: Settings to update
        """
        if 'max_daily_entries' in kwargs:
            self.max_daily_entries = kwargs['max_daily_entries']
            logger.info(f"Updated max daily entries to {self.max_daily_entries}")
        
        # Update regime manager settings if provided
        regime_settings = {k: v for k, v in kwargs.items() 
                          if k in ['bull_threshold', 'bear_threshold', 'volatility_threshold']}
        
        if regime_settings:
            for key, value in regime_settings.items():
                setattr(self.regime_manager, key, value)
            logger.info(f"Updated regime settings: {regime_settings}")