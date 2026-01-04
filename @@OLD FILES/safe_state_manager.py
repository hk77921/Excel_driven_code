"""
SAFE STATE MANAGER with File Locking
-------------------------------------
Prevents race conditions in concurrent access
"""

import json
import os
import shutil
import time
import logging
from datetime import datetime
from typing import Optional, Any

from state_manager import BACKUP_DIR

STATE_FILE = "trade_state.json"
PENDING_ORDERS_FILE = "pending_orders.json"
PNL_FILE = "daily_pnl.json"
LOCK_TIMEOUT = 10  # seconds


class StateLockError(Exception):
    """Raised when state lock cannot be acquired"""
    pass

class StateValidationError(Exception):
    """Raised when state validation fails"""
    pass

class SafeStateManager:
    """Thread-safe state manager with file locking"""
    
    def __init__(self, state_file: str = STATE_FILE):
        self.state_file = state_file
        self.lock_file = f"{state_file}.lock"
        self.lock_fd = None
    
    def acquire_lock(self, timeout: int = LOCK_TIMEOUT) -> bool:
        """Acquire exclusive lock on state file"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Use a simple approach: try to open for exclusive write
                # On Windows, this is simpler and more reliable
                self.lock_fd = open(self.lock_file, 'x')  # 'x' = exclusive creation, fails if exists
                self.lock_fd.write(f"{time.time()}")
                self.lock_fd.flush()
                logging.debug(f"Lock acquired: {self.lock_file}")
                return True
            except FileExistsError:
                # Lock file exists, another process has it
                # Check if it's stale (older than timeout)
                try:
                    mtime = os.path.getmtime(self.lock_file)
                    age = time.time() - mtime
                    if age > timeout * 2:  # Lock file is old, remove it
                        logging.warning(f"Removing stale lock file (age: {age:.1f}s)")
                        os.remove(self.lock_file)
                        time.sleep(0.05)
                        continue
                except Exception:
                    pass
                
                # Lock file is recent, wait and retry
                time.sleep(0.1)
            except Exception as e:
                logging.error(f"Lock acquisition error: {e}")
                return False
        
        logging.error(f"Failed to acquire lock after {timeout}s (timeout)")
        return False
    
    def release_lock(self):
        """Release the lock"""
        try:
            if self.lock_fd:
                self.lock_fd.close()
                self.lock_fd = None
            
            # Remove lock file
            if os.path.exists(self.lock_file):
                os.remove(self.lock_file)
            
            logging.debug(f"Lock released: {self.lock_file}")
        except Exception as e:
            logging.warning(f"Lock release error: {e}")
    
    def __enter__(self):
        """Context manager entry"""
        if not self.acquire_lock():
            raise StateLockError(f"Could not acquire lock: {self.lock_file}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.release_lock()
    
    def load(self) -> dict:
        """Load state (must be called within lock context)"""
        if not os.path.exists(self.state_file):
            return {}
        
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            return state
        except json.JSONDecodeError as e:
            logging.error(f"Corrupted state file: {e}")
            # Try backup
            return self._load_backup()
        except Exception as e:
            logging.error(f"Failed to load state: {e}")
            return {}
    
    def save(self, state: dict):
        """Save state (must be called within lock context)"""
        try:
            # Validate before saving
            self._validate_state(state)
            
            # Write to temp file first (atomic write)
            temp_file = f"{self.state_file}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(state, f, indent=2, default=str)
            
            # Atomic rename
            os.replace(temp_file, self.state_file)
            logging.debug(f"State saved: {len(state)} positions")
            
        except Exception as e:
            logging.error(f"Failed to save state: {e}")
            raise
    
    def _validate_state(self, state: dict):
        """Validate state structure before saving"""
        for symbol, trade in state.items():
            if not isinstance(trade, dict):
                raise ValueError(f"Invalid trade format for {symbol}")
            
             # Check required fields
            required_fields = [
                "symbol", "side", "entry", "sl", 
                "qty", "qty_remaining", "atr"
            ]
            missing = [f for f in required_fields if f not in trade]
            if missing:
                raise StateValidationError(
                    f"{symbol} missing required fields: {missing}"
                )
            
            # Check for negative quantities
            qty_remaining = trade.get("qty_remaining", 0)
            if qty_remaining < 0:
                raise ValueError(
                    f"{symbol} has negative qty_remaining: {qty_remaining}"
                )
            
            # Check qty_remaining <= qty
            qty = trade.get("qty", 0)
            if qty_remaining > qty:
                raise ValueError(
                    f"{symbol} qty_remaining ({qty_remaining}) > qty ({qty})"
                )
    

    def _cleanup_old_backups(self, keep: int = 50):
        """Remove old backup files, keeping only the most recent"""
        try:
            backup_files = [
                f for f in os.listdir(BACKUP_DIR)
                if f.startswith(os.path.basename(self.state_file))
            ]
            
            if len(backup_files) <= keep:
                return
            
            # Sort by modification time
            backup_files.sort(
                key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)),
                reverse=True
            )
            
            # Remove old backups
            for old_backup in backup_files[keep:]:
                os.remove(os.path.join(BACKUP_DIR, old_backup))
                logging.debug(f"Removed old backup: {old_backup}")
                
        except Exception as e:
            logging.warning(f"Failed to cleanup backups: {e}")

    def _create_backup(self):
        """Create timestamped backup of current state file"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = os.path.join(
                BACKUP_DIR,
                f"{os.path.basename(self.state_file)}.{timestamp}.bak"
            )
            
            shutil.copy2(self.state_file, backup_name)
            logging.debug(f"Backup created: {backup_name}")
            
            # Cleanup old backups (keep last 50)
            self._cleanup_old_backups(keep=50)
            
        except Exception as e:
            logging.warning(f"Failed to create backup: {e}")
            
    def _load_backup(self) -> dict:
        """Load most recent backup"""
        backup_dir = "backups"
        if not os.path.exists(backup_dir):
            return {}
        
        try:
            backups = [
                f for f in os.listdir(backup_dir)
                if f.startswith(os.path.basename(self.state_file))
            ]
            
            if not backups:
                return {}
            
            latest = sorted(backups)[-1]
            backup_path = os.path.join(backup_dir, latest)
            
            logging.warning(f"Loading backup: {backup_path}")
            with open(backup_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Backup load failed: {e}")
            return {}


class SafePendingOrdersManager(SafeStateManager):
    """Safe manager for pending orders"""
    
    def __init__(self):
        super().__init__(PENDING_ORDERS_FILE)
    
    def _validate_state(self, state: dict):
        """Override validation - pending orders have different structure"""
        # Pending orders is a dict of orders indexed by order_id
        # Just ensure it's a dict
        if not isinstance(state, dict):
            raise ValueError("Pending orders must be a dictionary")
        # Optional: validate each order has required fields
        for order_id, order in state.items():
            if not isinstance(order, dict):
                raise ValueError(f"Invalid order format for {order_id}")
            # Minimum required fields for pending orders
            required = ["symbol", "side", "req_qty"]
            missing = [f for f in required if f not in order]
            if missing:
                raise ValueError(f"Order {order_id} missing fields: {missing}")
        return


class SafePnLManager(SafeStateManager):
    """Safe manager for P&L data"""
    
    def __init__(self):
        super().__init__(PNL_FILE)
    
    def _validate_state(self, state: dict):
        """Override validation - PnL has different structure"""
        # PnL is a simple dict with metadata, not trade records
        # Just ensure it's a dict
        if not isinstance(state, dict):
            raise ValueError("PnL state must be a dictionary")
        # Optional: add specific field validation if needed
        # Expected fields: date, starting_capital, realized_pnl, unrealized_pnl, trades_executed
        return


# Convenience functions for backward compatibility
def safe_load_state() -> dict:
    """Load state with locking"""
    with SafeStateManager() as manager:
        return manager.load()


def safe_save_state(state: dict):
    """Save state with locking"""
    with SafeStateManager() as manager:
        manager.save(state)


def safe_load_pending_orders() -> dict:
    """Load pending orders with locking"""
    with SafePendingOrdersManager() as manager:
        return manager.load()


def safe_save_pending_orders(orders: dict):
    """Save pending orders with locking"""
    with SafePendingOrdersManager() as manager:
        manager.save(orders)


def safe_load_pnl() -> dict:
    """Load P&L with locking"""
    with SafePnLManager() as manager:
        return manager.load()


def safe_save_pnl(pnl: dict):
    """Save P&L with locking"""
    with SafePnLManager() as manager:
        manager.save(pnl)


# Transaction wrapper for atomic state updates
class StateTransaction:
    """Atomic transaction for state updates"""
    
    def __init__(self):
        self.state_manager = SafeStateManager()
        self.orders_manager = SafePendingOrdersManager()
        self.pnl_manager = SafePnLManager()
        
        self.state: dict = {}
        self.orders: dict = {}
        self.pnl: dict = {}
        self.committed = False
    
    def __enter__(self):
        """Begin transaction - acquire all locks"""
        try:
            if not self.state_manager.acquire_lock(timeout=15):
                raise StateLockError("Could not acquire state lock")
            
            if not self.orders_manager.acquire_lock(timeout=15):
                self.state_manager.release_lock()
                raise StateLockError("Could not acquire orders lock")
            
            
            if not self.pnl_manager.acquire_lock(timeout=15):
                self.state_manager.release_lock()
                self.orders_manager.release_lock()
                raise StateLockError("Could not acquire PnL lock")
            
            logging.info("Transaction started successfully")
            
            # # Acquire all locks
            # self.state_manager.acquire_lock()
            # self.orders_manager.acquire_lock()
            # self.pnl_manager.acquire_lock()
            
            # Load all data
            self.state = self.state_manager.load()
            self.orders = self.orders_manager.load()
            self.pnl = self.pnl_manager.load()

            logging.debug("Transaction data loaded")
            
            return self.state, self.orders, self.pnl
            
        except Exception as e:
            # Release any acquired locks
            self.state_manager.release_lock()
            self.orders_manager.release_lock()
            self.pnl_manager.release_lock()
            raise StateLockError(f"Transaction failed: {e}")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """End transaction - save and release locks"""
        try:
            # Only save if no exception occurred
            if exc_type is None and not self.committed:
                try:
                    # Create backups before saving
                    self.state_manager._create_backup()
                    self.orders_manager._create_backup()                    
                    self.pnl_manager._create_backup()


                    # Save all data
                    self.state_manager.save(self.state)
                    self.orders_manager.save(self.orders)
                    self.pnl_manager.save(self.pnl)
                    self.committed = True

                except Exception as e:
                    logging.warning(f"Backup creation failed: {e}") 


                logging.info("Transaction committed successfully")
        finally:
            # Always release locks
            self.state_manager.release_lock()
            self.orders_manager.release_lock()
            self.pnl_manager.release_lock()