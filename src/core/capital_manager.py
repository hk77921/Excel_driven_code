"""
Capital Manager - Core Risk Management (FIXED VERSION)
======================================
Handles all capital allocation and risk calculations.
CRITICAL: Single source of truth for capital tracking.

Used by all execution modes (backtest, paper, live).
"""

import logging
from typing import Dict, Tuple, Optional, List
from datetime import datetime
from dataclasses import dataclass
from .models import CapitalParameters, CapitalBreakdown
from ..utils.sector_manager import SectorManager


logger = logging.getLogger(__name__)


@dataclass
class CapitalEvent:
    """Audit trail entry for capital changes"""
    timestamp: datetime
    action: str  # RESERVE, COMMIT, RELEASE, FREE
    symbol: str
    amount: float
    available: float
    reserved: float
    committed: float
    total_check: float


class CapitalManager:
    """
    Core capital management with single source of truth.
    
    CRITICAL RULES:
    1. Only real capital counts (no unrealized P&L)
    2. Capital = Entry Price × Quantity (entry cost only)
    3. Safety buffer is UNTOUCHABLE
    4. Capital allocation must be conservative
    5. Sector limits are enforced
    
    CAPITAL STATES:
    - AVAILABLE: Free capital for new trades
    - RESERVED: Locked for pending orders (not yet filled)
    - COMMITTED: Locked in open positions
    
    INVARIANT: available + reserved + committed + buffer = total_capital
    """
    
    def __init__(self, params: CapitalParameters):
        """
        Initialize capital manager.
        
        Args:
            params: Capital parameters (total, risk, limits)
        """
        self.params = params
        self.sector_mgr = SectorManager(params)
        
        # Single source of truth for capital tracking
        self._available = params.total_capital
        self._reserved = 0.0
        self._committed = 0.0
        self._buffer = params.total_capital * params.safety_buffer_pct
        
        # Audit trail
        self._audit_trail: List[CapitalEvent] = []
        
        # Initial state
        self._log_capital_event("INIT", "SYSTEM", 0.0)
        
        logger.info(
            f"Capital Manager initialized: Total=₹{params.total_capital:,.2f}, "
            f"Buffer=₹{self._buffer:,.2f}, "
            f"Available=₹{self._available:,.2f}"
        )
    
    # ====== PUBLIC API ======
    
    def available_capital(self) -> float:
        """
        Get currently available capital for new trades.
        
        Returns:
            Available capital (excluding buffer)
        """
        return max(0.0, self._available)
    
    def reserved_capital(self) -> float:
        """Get capital reserved for pending orders"""
        return self._reserved
    
    def committed_capital(self) -> float:
        """Get capital committed to open positions"""
        return self._committed
    
    def can_reserve(self, amount: float) -> bool:
        """
        Check if amount can be reserved.
        
        Args:
            amount: Amount to reserve
            
        Returns:
            True if sufficient capital available
        """
        return amount <= self.available_capital()
    
    def reserve(self, symbol: str, amount: float) -> None:
        """
        Reserve capital for pending order.
        
        Args:
            symbol: Stock symbol
            amount: Amount to reserve
            
        Raises:
            RuntimeError: If insufficient capital
        """
        if not self.can_reserve(amount):
            available = self.available_capital()
            self._log_error_state(
                f"RESERVE FAILED for {symbol}: "
                f"Need ₹{amount:.2f}, have ₹{available:.2f}"
            )
            raise RuntimeError(
                f"Insufficient capital. Need Rs.{amount:.2f}, "
                f"have Rs.{available:.2f}"
            )
        
        # Move from available to reserved
        self._available -= amount
        self._reserved += amount
        
        self._log_capital_event("RESERVE", symbol, amount)
        self._validate_invariant()
        
        logger.info(
            f"{symbol}: Reserved ₹{amount:.2f} | "
            f"Available: ₹{self._available:.2f}, Reserved: ₹{self._reserved:.2f}"
        )
    
    def commit_position(self, symbol: str, amount: float) -> None:
        """
        Commit reserved capital to open position (order filled).
        
        Args:
            symbol: Stock symbol
            amount: Amount to commit
            
        Raises:
            RuntimeError: If trying to commit more than reserved
        """
        if amount > self._reserved + 0.01:  # Allow small rounding error
            self._log_error_state(
                f"COMMIT FAILED for {symbol}: "
                f"Cannot commit ₹{amount:.2f}, only ₹{self._reserved:.2f} reserved"
            )
            raise RuntimeError(
                f"Cannot commit ₹{amount:.2f}, only ₹{self._reserved:.2f} reserved"
            )
        
        # Move from reserved to committed
        self._reserved -= amount
        self._committed += amount
        
        self._log_capital_event("COMMIT", symbol, amount)
        self._validate_invariant()
        
        logger.info(
            f"{symbol}: Committed ₹{amount:.2f} | "
            f"Reserved: ₹{self._reserved:.2f}, Committed: ₹{self._committed:.2f}"
        )
    
    def release_reservation(self, symbol: str, amount: float) -> None:
        """
        Release reserved capital (order rejected/cancelled).
        
        Args:
            symbol: Stock symbol
            amount: Amount to release
        """
        if amount > self._reserved + 0.01:  # Allow small rounding error
            logger.warning(
                f"{symbol}: Cannot release ₹{amount:.2f}, "
                f"only ₹{self._reserved:.2f} reserved. Releasing available."
            )
            amount = self._reserved
        
        # Move from reserved back to available
        self._reserved -= amount
        self._available += amount
        
        self._log_capital_event("RELEASE", symbol, amount)
        self._validate_invariant()
        
        logger.info(
            f"{symbol}: Released ₹{amount:.2f} | "
            f"Available: ₹{self._available:.2f}, Reserved: ₹{self._reserved:.2f}"
        )
    
    def release_position(self, symbol: str, amount: float) -> None:
        """
        Release committed capital (position closed).
        
        Args:
            symbol: Stock symbol
            amount: Amount to release
        """
        if amount > self._committed + 0.01:  # Allow small rounding error
            logger.warning(
                f"{symbol}: Cannot release ₹{amount:.2f}, "
                f"only ₹{self._committed:.2f} committed. Releasing available."
            )
            amount = self._committed
        
        # Move from committed back to available
        self._committed -= amount
        self._available += amount
        
        self._log_capital_event("FREE", symbol, amount)
        self._validate_invariant()
        
        logger.info(
            f"{symbol}: Freed ₹{amount:.2f} | "
            f"Available: ₹{self._available:.2f}, Committed: ₹{self._committed:.2f}"
        )
    
    def can_open_position(
        self,
        symbol: str,
        entry_price: float,
        quantity: int,
        positions: Dict[str, dict],
        pending_orders: Dict[str, dict],
        sector_map: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, str]:
        """
        Check if new position can be opened.
        
        Validates:
        1. Available capital sufficient
        2. Position limits not exceeded
        3. Sector limits not exceeded
        
        Args:
            symbol: Stock symbol
            entry_price: Entry price
            quantity: Quantity to buy
            positions: All open positions
            pending_orders: All pending orders
            sector_map: Optional sector mapping from Excel
        
        Returns:
            (can_open, reason_if_not)
        """
        capital_needed = entry_price * quantity
        available = self.available_capital()
        
        logger.debug(
            f"{symbol}: Capital check - Need: ₹{capital_needed:,.2f}, "
            f"Available: ₹{available:,.2f}, Qty: {quantity}"
        )

        # Check 1: Capital available
        if capital_needed > available:
            self._log_capital_breakdown(symbol)
            return False, (
                f"{symbol}: Insufficient capital. Need Rs.{capital_needed:,.2f}, "
                f"have Rs.{available:,.2f}"
            )

        # Check 2: Position count limit
        open_count = len([p for p in positions.values() if p.get('qty_remaining', 0) > 0])
        if open_count >= self.params.max_open_positions:
            return False, (
                f"Max open positions ({self.params.max_open_positions}) reached"
            )
        
        # Check 3: Sector limits using sector manager
        symbol_sector = self.sector_mgr.get_symbol_sector(symbol, sector_map)
        can_add_sector, sector_reason = self.sector_mgr.can_add_position_to_sector(
            symbol, symbol_sector, positions, sector_map
        )
        
        if not can_add_sector:
            return False, sector_reason
        
        return True, ""
    
    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float
    ) -> int:
        """
        Calculate position size based on risk.
        
        Uses: Risk per trade = risk_per_trade × total_capital
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
        
        Returns:
            Number of shares to buy
        """
        # Risk amount = 0.5% of capital (default)
        risk_amount = self.params.total_capital * self.params.risk_per_trade
        
        # Risk per share = entry - stop loss
        risk_per_share = abs(entry_price - stop_loss)
        
        if risk_per_share <= 0:
            logger.warning(f"Invalid risk calculation: entry={entry_price}, sl={stop_loss}")
            return 0
        
        # Quantity = risk_amount / risk_per_share
        quantity = int(risk_amount / risk_per_share)
        
        logger.debug(
            f"Position size: {quantity} shares | "
            f"Risk: ₹{risk_amount:.2f} | "
            f"Risk/share: ₹{risk_per_share:.2f}"
        )
        
        return max(1, quantity)
    
    def get_capital_breakdown(
        self,
        positions: Dict[str, dict] = None,
        pending_orders: Dict[str, dict] = None
    ) -> CapitalBreakdown:
        """
        Get capital allocation breakdown.
        
        Args:
            positions: Ignored (for backward compatibility)
            pending_orders: Ignored (for backward compatibility)
        
        Returns:
            CapitalBreakdown with all allocations
        """
        return CapitalBreakdown(
            total_capital=self.params.total_capital,
            position_exposure=self._committed,  # Committed = positions
            pending_buy_capital=self._reserved,  # Reserved = pending orders
            safety_buffer=self._buffer,
            available_capital=self._available
        )
    
    def check_daily_loss_limit(self, daily_pnl: float) -> Tuple[bool, str]:
        """
        Check if daily loss limit exceeded (kill switch).
        
        Args:
            daily_pnl: Daily realized P&L (can be negative)
        
        Returns:
            (within_limit, reason_if_exceeded)
        """
        max_loss = self.params.total_capital * self.params.max_daily_loss_pct
        
        if daily_pnl < -max_loss:
            return False, (
                f"Daily loss limit exceeded. "
                f"Lost ₹{abs(daily_pnl):,.2f}, "
                f"limit: ₹{max_loss:,.2f}"
            )
        
        return True, ""
    
    def get_capital_breakdown_with_sectors(
        self,
        positions: Dict[str, dict],
        pending_orders: Dict[str, dict],
        sector_map: Optional[Dict[str, str]] = None
    ) -> Dict[str, any]:
        """
        Get detailed capital breakdown including sector analysis.
        
        Args:
            positions: All open positions
            pending_orders: All pending orders  
            sector_map: Optional sector mapping
            
        Returns:
            Detailed breakdown with sector information
        """
        # Sector breakdown
        sector_exposure = self.sector_mgr.get_sector_exposure(positions, sector_map)
        
        breakdown = self.get_capital_breakdown()
        
        return {
            "capital_breakdown": breakdown,
            "sector_exposure": sector_exposure,
            "open_positions": len([p for p in positions.values() if p.get('qty_remaining', 0) > 0]),
            "max_positions": self.params.max_open_positions,
            "max_per_sector": self.params.max_per_sector
        }
    
    # ====== AUDIT & VALIDATION ======
    
    def _log_capital_event_old(self, action: str, symbol: str, amount: float) -> None:
        """Log capital state change to audit trail"""
        total_check = self._available + self._reserved + self._committed + self._buffer
        
        event = CapitalEvent(
            timestamp=datetime.now(),
            action=action,
            symbol=symbol,
            amount=amount,
            available=self._available,
            reserved=self._reserved,
            committed=self._committed,
            total_check=total_check
        )
        
        self._audit_trail.append(event)
    
    def _log_capital_event(self, action: str, symbol: str, amount: float) -> None:
        """Log capital state change to audit trail"""
        # CRITICAL: Don't include buffer in total check - it's not additional capital
        total_check = self._available + self._reserved + self._committed
        
        event = CapitalEvent(
            timestamp=datetime.now(),
            action=action,
            symbol=symbol,
            amount=amount,
            available=self._available,
            reserved=self._reserved,
            committed=self._committed,
            total_check=total_check
        )
        
        self._audit_trail.append(event)
    



    def _validate_invariant_old(self) -> None:
        """Validate capital accounting invariant"""
        total_accounted = self._available + self._reserved + self._committed + self._buffer
        
        # Allow small rounding errors (1 paisa)
        if abs(total_accounted - self.params.total_capital) > 0.01:
            error_msg = (
                f"CAPITAL INVARIANT VIOLATION!\n"
                f"Total Capital: ₹{self.params.total_capital:,.2f}\n"
                f"Accounted:     ₹{total_accounted:,.2f}\n"
                f"Difference:    ₹{self.params.total_capital - total_accounted:,.2f}\n"
                f"Available:     ₹{self._available:,.2f}\n"
                f"Reserved:      ₹{self._reserved:,.2f}\n"
                f"Committed:     ₹{self._committed:,.2f}\n"
                f"Buffer:        ₹{self._buffer:,.2f}"
            )
            logger.error(error_msg)
            self.print_audit_trail()
            raise ValueError("Capital accounting error - SYSTEM HALT")
    
    def _validate_invariant(self) -> None:
        """Validate capital accounting invariant"""
        # CRITICAL: Buffer is NOT additional capital - it's a policy limit
        # Only count actual capital states: available, reserved, committed
        total_accounted = self._available + self._reserved + self._committed
        
        # Allow small rounding errors (1 paisa)
        if abs(total_accounted - self.params.total_capital) > 0.01:
            error_msg = (
                f"CAPITAL INVARIANT VIOLATION!\n"
                f"Total Capital: ₹{self.params.total_capital:,.2f}\n"
                f"Accounted:     ₹{total_accounted:,.2f}\n"
                f"Difference:    ₹{self.params.total_capital - total_accounted:,.2f}\n"
                f"Available:     ₹{self._available:,.2f}\n"
                f"Reserved:      ₹{self._reserved:,.2f}\n"
                f"Committed:     ₹{self._committed:,.2f}\n"
                f"Buffer:        ₹{self._buffer:,.2f} (policy limit, not counted in invariant)"
            )
            logger.error(error_msg)
            self.print_audit_trail()
            raise ValueError("Capital accounting error - SYSTEM HALT")



    def _log_capital_breakdown(self, symbol: str) -> None:
        """Log detailed capital breakdown"""
        logger.debug(
            f"{symbol}: CAPITAL BREAKDOWN\n"
            f"  Total:     ₹{self.params.total_capital:,.2f}\n"
            f"  Available: ₹{self._available:,.2f}\n"
            f"  Reserved:  ₹{self._reserved:,.2f}\n"
            f"  Committed: ₹{self._committed:,.2f}\n"
            f"  Buffer:    ₹{self._buffer:,.2f}"
        )
    
    def _log_error_state(self, message: str) -> None:
        """Log error with current state"""
        logger.error(
            f"{message}\n"
            f"Current State:\n"
            f"  Available: ₹{self._available:,.2f}\n"
            f"  Reserved:  ₹{self._reserved:,.2f}\n"
            f"  Committed: ₹{self._committed:,.2f}\n"
            f"  Buffer:    ₹{self._buffer:,.2f}"
        )
    
    def print_audit_trail(self, last_n: int = 20) -> None:
        """
        Print audit trail of capital changes.
        
        Args:
            last_n: Number of recent events to print
        """
        print("\n" + "="*100)
        print("CAPITAL AUDIT TRAIL")
        print("="*100)
        print(f"{'Time':<10} {'Action':<10} {'Symbol':<12} {'Amount':>12} {'Available':>12} "
              f"{'Reserved':>12} {'Committed':>12} {'Total Check':>12}")
        print("-"*100)
        
        for event in self._audit_trail[-last_n:]:
            print(
                f"{event.timestamp.strftime('%H:%M:%S'):<10} "
                f"{event.action:<10} "
                f"{event.symbol:<12} "
                f"₹{event.amount:>10,.2f} "
                f"₹{event.available:>10,.2f} "
                f"₹{event.reserved:>10,.2f} "
                f"₹{event.committed:>10,.2f} "
                f"₹{event.total_check:>10,.2f}"
            )
        
        print("="*100)
        print(f"Total Events: {len(self._audit_trail)}")
        print("="*100 + "\n")
    
    def get_summary_stats(self) -> Dict[str, float]:
        """Get summary statistics"""
        utilization = (self._reserved + self._committed) / self.params.total_capital * 100
        
        return {
            "total_capital": self.params.total_capital,
            "available": self._available,
            "reserved": self._reserved,
            "committed": self._committed,
            "buffer": self._buffer,
            "utilization_pct": utilization,
            "events_logged": len(self._audit_trail)
        }