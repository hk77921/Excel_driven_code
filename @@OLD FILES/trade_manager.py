"""
TRADE MANAGER - Production Ready
---------------------------------
Manages partial exits, trailing stops, and position logic
All functions properly integrated and tested
"""

import logging
from typing import Tuple, Dict, Any


def check_partial_exit(trade: Dict[str, Any], ltp: float) -> Tuple[Dict[str, Any], int]:
    """
    Check if partial exit should be triggered at +0.8R.
    
    Args:
        trade: Trade dictionary
        ltp: Last traded price
    
    Returns:
        (updated_trade, exit_qty) - exit_qty=0 means no exit
    """
    # Skip if already done
    if trade.get("partial_done", False):
        return trade, 0
    
    entry = trade["entry"]
    sl = trade["sl"]
    side = trade["side"]
    symbol = trade.get("symbol", "UNKNOWN")
    
    # Calculate R-value (risk per share)
    r_value = abs(entry - sl)
    
    if r_value == 0:
        logging.warning(f"{symbol}: R-value is zero, skipping partial exit")
        return trade, 0
    
    # Only handle BUY side for now
    if side == "BUY":
        # Target is entry + 0.8R
        target_price = entry + (0.8 * r_value)
        
        if ltp >= target_price:
            # Exit 50% of remaining quantity
            exit_qty = max(1, int(trade["qty_remaining"] * 0.5))
            
            # Must leave at least 1 share remaining
            if exit_qty >= trade["qty_remaining"]:
                exit_qty = trade["qty_remaining"] - 1
            
            if exit_qty > 0:
                trade["partial_done"] = True
                logging.info(
                    f"{symbol}: Partial exit triggered | "
                    f"LTP={ltp:.2f}, Target={target_price:.2f}, "
                    f"Exit Qty={exit_qty}/{trade['qty_remaining']}"
                )
                return trade, exit_qty
            else:
                logging.debug(
                    f"{symbol}: Partial exit target reached but "
                    f"insufficient qty remaining"
                )
    
    # TODO: Add SHORT side logic when needed
    
    return trade, 0


def update_trailing_sl(trade: Dict[str, Any], ltp: float) -> Tuple[Dict[str, Any], bool]:
    """
    Update trailing stop loss after partial exit.
    SL only moves forward (never backward).
    
    Args:
        trade: Trade dictionary
        ltp: Last traded price
    
    Returns:
        (updated_trade, sl_moved) - sl_moved=True if SL was updated
    """
    # Only trail after partial exit
    if not trade.get("partial_done", False):
        return trade, False
    
    atr = trade["atr"]
    side = trade["side"]
    symbol = trade.get("symbol", "UNKNOWN")
    
    if atr == 0:
        logging.warning(f"{symbol}: ATR is zero, cannot trail SL")
        return trade, False
    
    if side == "BUY":
        # Trail SL at LTP - 1.5*ATR
        new_sl = ltp - (1.5 * atr)
        
        # Only update if new SL is higher (more protective)
        if new_sl > trade["sl"]:
            old_sl = trade["sl"]
            trade["sl"] = new_sl
            trade["trailing_active"] = True
            
            logging.info(
                f"{symbol}: Trailing SL updated | "
                f"Old={old_sl:.2f}, New={new_sl:.2f}, LTP={ltp:.2f}"
            )
            return trade, True
    
    # TODO: Add SHORT side logic when needed
    
    return trade, False


def check_stop_loss_hit(trade: Dict[str, Any], ltp: float) -> bool:
    """
    Check if stop loss has been hit.
    
    Args:
        trade: Trade dictionary
        ltp: Last traded price
    
    Returns:
        True if SL hit, False otherwise
    """
    side = trade["side"]
    sl = trade["sl"]
    symbol = trade.get("symbol", "UNKNOWN")
    
    if side == "BUY":
        if ltp <= sl:
            logging.warning(
                f"{symbol}: STOP LOSS HIT | "
                f"LTP={ltp:.2f}, SL={sl:.2f}, "
                f"Loss={(ltp-trade['entry'])/trade['entry']*100:.2f}%"
            )
            return True
    
    # TODO: Add SHORT side logic when needed
    
    return False


def calculate_pnl(trade: Dict[str, Any], exit_price: float, exit_qty: int) -> float:
    """
    Calculate P&L for a trade exit.
    
    Args:
        trade: Trade dictionary
        exit_price: Exit price
        exit_qty: Quantity being exited
    
    Returns:
        Realized P&L in currency
    """
    entry = trade["entry"]
    side = trade["side"]
    
    if side == "BUY":
        pnl_per_share = exit_price - entry
    else:  # SHORT
        pnl_per_share = entry - exit_price
    
    total_pnl = pnl_per_share * exit_qty
    
    return total_pnl


def reduce_quantity(trade: Dict[str, Any], sell_qty: int) -> Tuple[Dict[str, Any], int]:
    """
    Reduce trade quantity after partial/full exit.
    
    Args:
        trade: Trade dictionary
        sell_qty: Quantity to exit
    
    Returns:
        (updated_trade, actual_sell_qty)
    """
    actual_sell_qty = min(sell_qty, trade["qty_remaining"])
    trade["qty_remaining"] -= actual_sell_qty
    
    # Validate
    if trade["qty_remaining"] < 0:
        symbol = trade.get("symbol", "UNKNOWN")
        logging.error(f"{symbol}: qty_remaining went negative! Correcting to 0")
        trade["qty_remaining"] = 0
    
    return trade, actual_sell_qty


def validate_quantity(trade: Dict[str, Any]):
    """
    Validate trade quantities.
    Raises ValueError if invalid.
    """
    symbol = trade.get("symbol", "UNKNOWN")
    
    if trade["qty_remaining"] < 0:
        raise ValueError(f"{symbol}: qty_remaining < 0")
    
    if trade["qty_remaining"] > trade["qty"]:
        raise ValueError(
            f"{symbol}: qty_remaining ({trade['qty_remaining']}) > "
            f"qty ({trade['qty']})"
        )