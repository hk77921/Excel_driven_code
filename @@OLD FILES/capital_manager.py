"""
CAPITAL MANAGEMENT - CORRECT IMPLEMENTATION
Handles all aspects of available capital calculation
"""

import logging
from typing import Dict, Tuple
from dataclasses import dataclass

# Configuration
SAFETY_BUFFER_PCT = 0.15  # 15% safety buffer
MARGIN_MULTIPLIER = 1.0   # No margin for now (only use 1x)


@dataclass
class CapitalBreakdown:
    """Capital allocation breakdown"""
    total_capital: float
    position_exposure: float
    pending_buy_capital: float
    safety_buffer: float
    available_capital: float
    
    def __str__(self) -> str:
        return (
            f"Capital Breakdown:\n"
            f"  Total: ₹{self.total_capital:>12,.2f}\n"
            f"  - Positions: ₹{self.position_exposure:>12,.2f}\n"
            f"  - Pending: ₹{self.pending_buy_capital:>12,.2f}\n"
            f"  - Buffer: ₹{self.safety_buffer:>12,.2f}\n"
            f"  = Available: ₹{self.available_capital:>12,.2f}"
        )


def calculate_position_exposure(state: Dict) -> float:
    """
    Calculate total capital allocated to open positions.
    
    Args:
        state: Dictionary of open trades
    
    Returns:
        Total capital allocated
    """
    total = 0.0
    
    for symbol, trade_dict in state.items():
        if not isinstance(trade_dict, dict):
            continue
        
        # Use entry price * current quantity
        entry = trade_dict.get("entry", 0.0)
        qty_remaining = trade_dict.get("qty_remaining", 0)
        
        if entry > 0 and qty_remaining > 0:
            exposure = entry * qty_remaining
            total += exposure
            logging.debug(f"{symbol}: ₹{exposure:,.2f} exposure")
    
    logging.debug(f"Total position exposure: ₹{total:,.2f}")
    return total


def calculate_pending_buy_capital(pending_orders: Dict) -> float:
    """
    Calculate capital reserved for pending BUY orders.
    
    Args:
        pending_orders: Dictionary of pending orders
    
    Returns:
        Total capital reserved
    """
    total = 0.0
    
    for order_id, order_dict in pending_orders.items():
        if not isinstance(order_dict, dict):
            continue
        
        # Skip non-BUY orders
        if order_dict.get("side") != "BUY":
            continue
        
        # Use filled price if available, otherwise estimated
        price = order_dict.get("price", 0.0)
        qty = order_dict.get("req_qty", 0)
        
        if price > 0 and qty > 0:
            capital = price * qty
            total += capital
            logging.debug(f"{order_id} ({order_dict.get('symbol')}): ₹{capital:,.2f} pending")
    
    logging.debug(f"Total pending BUY capital: ₹{total:,.2f}")
    return total


def calculate_safety_buffer(total_capital: float) -> float:
    """
    Calculate safety buffer (amount to never touch).
    
    Args:
        total_capital: Total available capital
    
    Returns:
        Safety buffer amount
    """
    buffer = total_capital * SAFETY_BUFFER_PCT
    logging.debug(f"Safety buffer ({SAFETY_BUFFER_PCT*100:.0f}%): ₹{buffer:,.2f}")
    return buffer


def calculate_available_capital(
    total_capital: float,
    state: Dict,
    pending_orders: Dict
) -> Tuple[float, CapitalBreakdown]:
    """
    Calculate truly available capital for new trades.
    
    THIS IS THE CORRECT CALCULATION:
    
    Available = Total Capital
               - Position Exposure
               - Pending BUY Capital
               - Safety Buffer
    
    DO NOT INCLUDE:
    - Unrealized P&L (you don't have it until you exit)
    - Margin requirements (not using leverage)
    - Commission/fees (deduct from realized P&L)
    
    Args:
        total_capital: Total capital available
        state: Open positions
        pending_orders: Pending orders
    
    Returns:
        (available_capital, breakdown)
    """
    
    position_exposure = calculate_position_exposure(state)
    pending_buy_capital = calculate_pending_buy_capital(pending_orders)
    safety_buffer = calculate_safety_buffer(total_capital)
    
    available = (
        total_capital
        - position_exposure
        - pending_buy_capital
        - safety_buffer
    )
    
    # Safety: never go negative
    available = max(0.0, available)
    
    breakdown = CapitalBreakdown(
        total_capital=total_capital,
        position_exposure=position_exposure,
        pending_buy_capital=pending_buy_capital,
        safety_buffer=safety_buffer,
        available_capital=available
    )
    
    return available, breakdown


def log_capital_breakdown(breakdown: CapitalBreakdown):
    """Pretty-print capital breakdown"""
    logging.info(str(breakdown))


def validate_capital_usage(
    required_capital: float,
    available_capital: float,
    symbol: str
) -> Tuple[bool, str]:
    """
    Validate if a trade can be executed with current capital.
    
    Returns:
        (can_trade, reason)
    """
    if required_capital <= 0:
        return False, "Invalid capital requirement"
    
    if required_capital > available_capital:
        return False, (
            f"Insufficient capital: "
            f"need ₹{required_capital:,.2f}, "
            f"have ₹{available_capital:,.2f}"
        )
    
    return True, "OK"
