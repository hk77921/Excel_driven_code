"""
Capital Manager - Core Risk Management
======================================
Handles all capital allocation and risk calculations.
CRITICAL: Tracks ACTUAL capital only, never unrealized P&L.

Used by all execution modes (backtest, paper, live).
"""

import logging
from typing import Dict, Tuple, Optional
from .models import CapitalParameters, CapitalBreakdown
from ..utils.sector_manager import SectorManager


logger = logging.getLogger(__name__)


class CapitalManager:
    """
    Core capital management.
    
    CRITICAL RULES:
    1. Only real capital counts (no unrealized P&L)
    2. Capital = Entry Price × Quantity (entry cost only)
    3. Safety buffer is UNTOUCHABLE
    4. Capital allocation must be conservative
    5. Sector limits are enforced
    """
    
    def __init__(self, params: CapitalParameters):
        """
        Initialize capital manager.
        
        Args:
            params: Capital parameters (total, risk, limits)
        """
        self.params = params
        self.sector_mgr = SectorManager(params)
        self._reserved_capital = 0.0
        self._positions_capital = 0.0
    
    def calculate_available_capital(
        self,
        positions: Dict[str, dict],
        pending_orders: Dict[str, dict]
    ) -> float:
        """
        Calculate available capital for new trades.
        
        CRITICAL: Only counts REAL capital allocated to positions
        
        Args:
            positions: All open positions
            pending_orders: All pending orders
        
        Returns:
            Available capital (never includes unrealized P&L)
        """
        # Position exposure (entry price × qty)
        position_exposure = self._calculate_position_exposure(positions)
        
        # Pending BUY capital
        pending_capital = self._calculate_pending_buy_capital(pending_orders)
        
        # Safety buffer (untouchable)
        safety_buffer = self._calculate_safety_buffer()
        
        # Available = Total - Positions - Pending - Buffer
        available = (
            self.params.total_capital
            - position_exposure
            - pending_capital
            - safety_buffer
        )
        
        return max(0.0, available)
    

    def available_capital(self) -> float:
        buffer = self.params.total_capital * self.params.safety_buffer_pct
        return max(
            0.0,
            self.params.total_capital
            - self._positions_capital
            - self._reserved_capital
            - buffer
        )

    def can_reserve(self, amount: float) -> bool:
            return amount <= self.available_capital()

    def reserve(self, amount: float):
        if not self.can_reserve(amount):
            raise RuntimeError(
                f"Insufficient capital. Need Rs.{amount:.2f}, "
                f"have Rs.{self.available_capital():.2f}"
            )
        self._reserved_capital += amount

    def commit_position(self, amount: float):
        self._reserved_capital -= amount
        self._positions_capital += amount

    def release_reservation(self, amount: float):
        self._reserved_capital = max(0.0, self._reserved_capital - amount)

    def release_position(self, amount: float):
        self._positions_capital = max(0.0, self._positions_capital - amount)



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
        
        # Get detailed breakdown for debugging
        position_exposure = self._calculate_position_exposure(positions)
        pending_capital = self._calculate_pending_buy_capital(pending_orders)
        safety_buffer = self._calculate_safety_buffer()
        
        logger.debug(
            f"{symbol}: Capital check - Need: Rs.{capital_needed:,.2f}, "
            f"Available: Rs.{available:,.2f}, Qty: {quantity}"
        )
        logger.debug(
            f"{symbol}: Capital breakdown - Total: Rs.{self.params.total_capital:,.2f}, "
            f"Positions: Rs.{position_exposure:,.2f}, "
            f"Pending: Rs.{pending_capital:,.2f}, "
            f"Buffer: Rs.{safety_buffer:,.2f}"
        )

        # Check 1: Capital available
        if capital_needed > available:
            # Log capital breakdown at DEBUG level to reduce verbosity
            logger.debug(
                f"{symbol}: CAPITAL BREAKDOWN - Total: Rs.{self.params.total_capital:,.2f}, "
                f"Positions: Rs.{position_exposure:,.2f}, "
                f"Pending: Rs.{pending_capital:,.2f}, "
                f"Buffer: Rs.{safety_buffer:,.2f}, "
                f"Available: Rs.{available:,.2f}"
            )
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
        positions: Dict[str, dict],
        pending_orders: Dict[str, dict]
    ) -> CapitalBreakdown:
        """
        Get capital allocation breakdown.
        
        Args:
            positions: All open positions
            pending_orders: All pending orders
        
        Returns:
            CapitalBreakdown with all allocations
        """
        position_exposure = self._calculate_position_exposure(positions)
        pending_capital = self._calculate_pending_buy_capital(pending_orders)
        safety_buffer = self._calculate_safety_buffer()
        available = self.calculate_available_capital(positions, pending_orders)
        
        return CapitalBreakdown(
            total_capital=self.params.total_capital,
            position_exposure=position_exposure,
            pending_buy_capital=pending_capital,
            safety_buffer=safety_buffer,
            available_capital=available
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
        # Basic capital breakdown
        position_exposure = self._calculate_position_exposure(positions)
        pending_capital = self._calculate_pending_buy_capital(pending_orders)
        safety_buffer = self._calculate_safety_buffer()
        available = self.calculate_available_capital(positions, pending_orders)
        
        # Sector breakdown
        sector_exposure = self.sector_mgr.get_sector_exposure(positions, sector_map)
        
        breakdown = CapitalBreakdown(
            total_capital=self.params.total_capital,
            position_exposure=position_exposure,
            pending_buy_capital=pending_capital,
            safety_buffer=safety_buffer,
            available_capital=available
        )
        
        return {
            "capital_breakdown": breakdown,
            "sector_exposure": sector_exposure,
            "open_positions": len([p for p in positions.values() if p.get('qty_remaining', 0) > 0]),
            "max_positions": self.params.max_open_positions,
            "max_per_sector": self.params.max_per_sector
        }
    
    # ====== INTERNAL HELPERS ======
    
    def _calculate_position_exposure(self, positions: Dict[str, dict]) -> float:
        """Calculate total capital allocated to open positions"""
        total = 0.0
        
        for symbol, pos in positions.items():
            entry = pos.get('entry_price', 0.0)
            qty = pos.get('qty_remaining', 0)
            
            if entry > 0 and qty > 0:
                exposure = entry * qty
                total += exposure
        
        return total
    
    def _calculate_pending_buy_capital(self, pending_orders: Dict[str, dict]) -> float:
        """Calculate capital reserved for pending BUY orders"""
        total = 0.0
        
        for order_id, order in pending_orders.items():
            if order.get('side') != 'BUY':
                continue
            
            price = order.get('price', 0.0)
            qty = order.get('req_qty', 0)
            
            if price > 0 and qty > 0:
                total += price * qty
        
        return total
    
    def _calculate_safety_buffer(self) -> float:
        """Calculate safety buffer (untouchable amount)"""
        return self.params.total_capital * self.params.safety_buffer_pct
