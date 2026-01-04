"""
STATE MANAGER - Updated with P&L Tracking
------------------------------------------
Manages persistent state for trades, orders, and daily P&L
"""

import json
import os
from datetime import datetime
import logging

import time

STATE_FILE = "trade_state.json"
PENDING_ORDERS_FILE = "pending_orders.json"
PNL_FILE = "daily_pnl.json"
BACKUP_DIR = "backups"

# Ensure backup directory exists
os.makedirs(BACKUP_DIR, exist_ok=True)


def create_backup(filename: str):
    """Create timestamped backup of a file"""
    if os.path.exists(filename):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{BACKUP_DIR}/{os.path.basename(filename)}.{timestamp}.bak"
            
            with open(filename, "r") as src:
                with open(backup_name, "w") as dst:
                    dst.write(src.read())
            
            logging.debug(f"Backup created: {backup_name}")
        except Exception as e:
            logging.warning(f"Failed to create backup: {e}")


def load_state():
    """Load trade state with error handling"""
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
            
        # Validate state structure
        for symbol, trade in state.items():
            if not isinstance(trade, dict):
                logging.error(f"Invalid trade format for {symbol}")
                continue
            
            # Ensure required fields exist
            required = ["symbol", "side", "entry", "sl", "qty", "qty_remaining", "atr"]
            missing = [f for f in required if f not in trade]
            if missing:
                logging.error(f"{symbol} missing fields: {missing}")
        
        return state
    except json.JSONDecodeError as e:
        logging.error(f"Corrupted state file: {e}")
        # Try to load backup
        return load_latest_backup(STATE_FILE)
    except Exception as e:
        logging.error(f"Failed to load state: {e}")
        return {}


def save_state(state: dict):
    """Save trade state with backup"""
    try:
        # Create backup before overwriting
        create_backup(STATE_FILE)
        
        # Validate before saving
        for symbol, trade in state.items():
            if not isinstance(trade, dict):
                raise ValueError(f"Invalid trade format for {symbol}")
            
            # Check for negative quantities
            qty_remaining = trade.get("qty_remaining", 0)
            if qty_remaining < 0:
                raise ValueError(f"{symbol} has negative qty_remaining: {qty_remaining}")
        
        # Write atomically
        temp_file = f"{STATE_FILE}.tmp"
        with open(temp_file, "w") as f:
            json.dump(state, f, indent=2, default=str)
        
        # Rename to final file (atomic on most systems)
        os.replace(temp_file, STATE_FILE)
        
    except Exception as e:
        logging.error(f"Failed to save state: {e}")
        raise


def load_pending_orders():
    """Load pending orders from persistent storage"""
    if not os.path.exists(PENDING_ORDERS_FILE):
        return {}

    try:
        with open(PENDING_ORDERS_FILE, "r") as f:
            orders = json.load(f)
        return orders
    except json.JSONDecodeError as e:
        logging.error(f"Corrupted pending orders file: {e}")
        return load_latest_backup(PENDING_ORDERS_FILE)
    except Exception as e:
        logging.error(f"Failed to load pending orders: {e}")
        return {}


def save_pending_orders(pending_orders: dict):
    """Persist pending orders to disk"""
    try:
        create_backup(PENDING_ORDERS_FILE)
        
        temp_file = f"{PENDING_ORDERS_FILE}.tmp"
        with open(temp_file, "w") as f:
            json.dump(pending_orders, f, indent=2, default=str)
        
        os.replace(temp_file, PENDING_ORDERS_FILE)
        
    except Exception as e:
        logging.error(f"Failed to save pending orders: {e}")
        raise


def load_latest_backup(original_file: str):
    """Load most recent backup if main file corrupted"""
    try:
        backup_files = [
            f for f in os.listdir(BACKUP_DIR) 
            if f.startswith(os.path.basename(original_file))
        ]
        
        if not backup_files:
            logging.error(f"No backups found for {original_file}")
            return {}
        
        # Sort by timestamp (newest first)
        backup_files.sort(reverse=True)
        latest_backup = os.path.join(BACKUP_DIR, backup_files[0])
        
        logging.warning(f"Loading backup: {latest_backup}")
        with open(latest_backup, "r") as f:
            return json.load(f)
            
    except Exception as e:
        logging.error(f"Failed to load backup: {e}")
        return {}


def add_trade(state, symbol, trade_data):
    """Add or update a trade in state"""
    state[symbol] = trade_data
    save_state(state)


def remove_trade(state, symbol):
    """Remove a trade from state"""
    if symbol in state:
        del state[symbol]
        save_state(state)


def validate_trade(trade: dict):
    """Validate trade data structure"""
    required_fields = [
        "symbol", "side", "entry", "sl", 
        "qty", "qty_remaining", "atr"
    ]
    
    missing = [f for f in required_fields if f not in trade]
    if missing:
        raise ValueError(f"Trade missing required fields: {missing}")
    
    if trade["qty_remaining"] < 0:
        raise ValueError(f"Negative qty_remaining: {trade['qty_remaining']}")
    
    if trade["qty_remaining"] > trade["qty"]:
        raise ValueError(
            f"qty_remaining ({trade['qty_remaining']}) > "
            f"qty ({trade['qty']})"
        )
    
    if trade["entry"] <= 0 or trade["sl"] <= 0:
        raise ValueError("Entry or SL price cannot be <= 0")
    
    if trade["atr"] < 0:
        raise ValueError(f"Invalid ATR: {trade['atr']}")


def get_state_summary(state: dict) -> dict:
    """Get summary statistics of current state"""
    if not state:
        return {
            "open_positions": 0,
            "total_qty": 0,
            "total_exposure": 0.0,
            "symbols": []
        }
    
    total_qty = sum(t.get("qty_remaining", 0) for t in state.values())
    total_exposure = sum(
        t.get("entry", 0) * t.get("qty_remaining", 0) 
        for t in state.values()
    )
    
    return {
        "open_positions": len(state),
        "total_qty": total_qty,
        "total_exposure": total_exposure,
        "symbols": list(state.keys())
    }


def cleanup_old_backups(days_to_keep: int = 7):
    """Remove backups older than specified days"""
    try:
        import time
        cutoff_time = time.time() - (days_to_keep * 86400)
        
        for filename in os.listdir(BACKUP_DIR):
            filepath = os.path.join(BACKUP_DIR, filename)
            if os.path.getmtime(filepath) < cutoff_time:
                os.remove(filepath)
                logging.info(f"Removed old backup: {filename}")
                
    except Exception as e:
        logging.warning(f"Failed to cleanup old backups: {e}")


# Run cleanup on import (optional)
if os.path.exists(BACKUP_DIR):
    cleanup_old_backups()