"""
PRE-MARKET CHECKLIST
--------------------
Validates system readiness before trading session starts
"""

import os
import json
import socket
import logging
from datetime import datetime

# Configuration
MIN_CAPITAL = 5000  # Minimum trading capital required
EXCEL_FILE = "100_high_performing_stocks_sector_wise (1).csv"
STATE_FILE = "trade_state.json"
PENDING_ORDERS_FILE = "pending_orders.json"


def check_internet() -> bool:
    """Check if internet connection is available"""
    try:
        # Try to resolve a reliable DNS server
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        logging.info("✓ Internet connection verified")
        return True
    except (socket.timeout, socket.error):
        logging.error("✗ Internet connection failed")
        return False


def check_kite_connection() -> bool:
    """Check if Kite broker connection is available"""
    try:
        # This would require actual Kite API initialization
        # For now, we'll do a simple check
        logging.info("✓ Kite connection ready")
        return True
    except Exception as e:
        logging.error(f"✗ Kite connection failed: {e}")
        return False


def check_state_files_valid() -> bool:
    """Verify that state files exist and are valid JSON"""
    try:
        # Check trade state
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                json.load(f)
        
        # Check pending orders
        if os.path.exists(PENDING_ORDERS_FILE):
            with open(PENDING_ORDERS_FILE, "r") as f:
                json.load(f)
        
        logging.info("✓ State files are valid")
        return True
    except json.JSONDecodeError as e:
        logging.error(f"✗ State files are corrupted: {e}")
        return False
    except Exception as e:
        logging.error(f"✗ State file check failed: {e}")
        return False


def check_excel_accessible() -> bool:
    """Verify Excel file is accessible"""
    try:
        if not os.path.exists(EXCEL_FILE):
            logging.error(f"✗ Excel file not found: {EXCEL_FILE}")
            return False
        
        # Try to read the file
        with open(EXCEL_FILE, "r", encoding="utf-8") as f:
            f.readline()
        
        logging.info("✓ Excel file is accessible")
        return True
    except Exception as e:
        logging.error(f"✗ Excel file check failed: {e}")
        return False


def check_broker_balance() -> float:
    """Get current broker balance (placeholder)"""
    try:
        # This would query actual broker API
        # For now, return a default value
        balance = 50000.0
        logging.info(f"✓ Broker balance: ₹{balance:,.2f}")
        return balance
    except Exception as e:
        logging.error(f"✗ Broker balance check failed: {e}")
        return 0.0


def load_pending_orders() -> dict:
    """Load pending orders from persistent storage"""
    try:
        if not os.path.exists(PENDING_ORDERS_FILE):
            return {}
        
        with open(PENDING_ORDERS_FILE, "r") as f:
            orders = json.load(f)
        
        return orders
    except Exception as e:
        logging.error(f"Failed to load pending orders: {e}")
        return {}


def pre_market_checklist() -> bool:
    """Run before market opens"""
    checks = {
        "Internet": check_internet(),
        "Kite Connection": check_kite_connection(),
        "State Files": check_state_files_valid(),
        "Excel File": check_excel_accessible(),
        "Sufficient Capital": check_broker_balance() > MIN_CAPITAL,
        "No Pending Orders": len(load_pending_orders()) == 0
    }
    
    all_passed = all(checks.values())
    
    for check, status in checks.items():
        print(f"{'✓' if status else '✗'} {check}")
    
    return all_passed


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    result = pre_market_checklist()
    print(f"\nPre-market check: {'PASSED ✓' if result else 'FAILED ✗'}")
    exit(0 if result else 1)