import json
import os
from datetime import datetime

STATE_FILE = "trade_state.json"
PENDING_ORDERS_FILE = "pending_orders.json"

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def load_pending_orders():
    """Load pending orders from persistent storage"""
    if not os.path.exists(PENDING_ORDERS_FILE):
        return {}

    try:
        with open(PENDING_ORDERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_pending_orders(pending_orders: dict):
    """Persist pending orders to disk"""
    with open(PENDING_ORDERS_FILE, "w") as f:
        json.dump(pending_orders, f, indent=2, default=str)

def add_trade(state, symbol, trade_data):
    state[symbol] = trade_data
    save_state(state)

def remove_trade(state, symbol):
    if symbol in state:
        del state[symbol]
        save_state(state)

def validate_trade(trade: dict):
    if trade["QTY_REMAINING"] < 0:
        raise ValueError("Negative QTY_REMAINING")
    if trade["QTY_REMAINING"] > trade["QTY"]:
        raise ValueError("QTY_REMAINING exceeds original QTY")

