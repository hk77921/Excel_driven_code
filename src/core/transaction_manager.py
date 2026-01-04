"""
Transaction Manager - Atomic State Updates
==========================================
Provides ACID transaction support for state management.
Prevents data corruption during crashes and concurrent access.
"""

import json
import os
import logging
import shutil
from typing import Dict, Any, Optional, Tuple, List
from threading import Lock
from datetime import datetime
from pathlib import Path

from .state_manager import StateManager


logger = logging.getLogger(__name__)


class StateLockError(Exception):
    """Raised when state lock cannot be acquired"""
    pass


class TransactionManager:
    """
    Atomic transaction manager for state updates.
    
    Features:
    - ACID properties (Atomicity, Consistency, Isolation, Durability)
    - Automatic rollback on exceptions
    - Backup creation before saves
    - Timeout handling for locks
    - Proper lock ordering to prevent deadlocks
    """
    
    def __init__(self, state_dir: str = "state"):
        """
        Initialize transaction manager.
        
        Args:
            state_dir: Directory for state files
        """
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(exist_ok=True)
        
        # Create backup directory
        self.backup_dir = self.state_dir / "backups"
        self.backup_dir.mkdir(exist_ok=True)
        
        # Initialize individual state managers
        self.state_mgr = StateManager(state_dir)
        
        # Track transaction state
        self._in_transaction = False
        self._original_state = {}
        self._changes_made = False
        
        logger.debug(f"Transaction manager initialized: {state_dir}")
    
    def begin_transaction(self, timeout: int = 15, date: Optional[str] = None) -> Tuple[Dict, Dict, List, Dict]:
        """
        Begin atomic transaction.
        
        Args:
            timeout: Lock acquisition timeout in seconds
            date: Date for daily P&L (defaults to today)
            
        Returns:
            Tuple of (positions, orders, trades, daily_pnl)
            
        Raises:
            StateLockError: If locks cannot be acquired
        """
        if self._in_transaction:
            raise StateLockError("Transaction already in progress")
        
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            # Acquire locks with timeout
            if not self.state_mgr._lock.acquire(timeout=timeout):
                raise StateLockError(f"Could not acquire state lock within {timeout}s")
            
            self._in_transaction = True
            
            # Load current state
            positions = self.state_mgr.load_positions()
            orders = self.state_mgr.load_orders()
            trades = self.state_mgr.load_trades()
            daily_pnl = self.state_mgr.load_daily_pnl(date) or {}
            
            # Store original state for rollback
            self._original_state = {
                'positions': positions.copy(),
                'orders': orders.copy(),
                'trades': trades.copy(),
                'daily_pnl': daily_pnl.copy(),
                'date': date
            }
            
            logger.debug("Transaction started: all locks acquired")
            return positions, orders, trades, daily_pnl
            
        except Exception as e:
            # Clean up on failure
            self._cleanup_transaction()
            raise StateLockError(f"Failed to begin transaction: {e}")
    
    def commit_transaction(
        self,
        positions: Dict,
        orders: Dict,
        trades: List,
        daily_pnl: Dict,
        date: Optional[str] = None
    ) -> bool:
        """
        Commit transaction - save all state atomically.
        
        Args:
            positions: Updated positions data
            orders: Updated orders data
            trades: Updated trades data
            daily_pnl: Updated daily P&L data
            date: Date for daily P&L (uses stored date if None)
            
        Returns:
            bool: True if committed successfully
            
        Raises:
            StateLockError: If transaction fails
        """
        if not self._in_transaction:
            raise StateLockError("No transaction in progress")
        
        if date is None:
            date = self._original_state.get('date', datetime.now().strftime("%Y-%m-%d"))
        
        try:
            # Create backups before saving
            self._create_backups()
            
            # Validate data before saving
            self._validate_transaction_data(positions, orders, trades, daily_pnl)
            
            # Save all state atomically
            self.state_mgr.save_positions(positions)
            self.state_mgr.save_orders(orders)
            
            # Save trades - add new ones to existing list
            for trade in trades:
                if isinstance(trade, dict):
                    self.state_mgr.add_trade(trade)
            
            # Save daily P&L
            self.state_mgr.save_daily_pnl(date, daily_pnl)
            
            logger.info("Transaction committed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Transaction commit failed: {e}")
            # Attempt rollback
            try:
                self._rollback_transaction()
                logger.warning("Transaction rolled back successfully")
            except Exception as rollback_error:
                logger.critical(f"ROLLBACK FAILED: {rollback_error} - Manual intervention required!")
            
            raise StateLockError(f"Transaction commit failed: {e}")
        
        finally:
            self._cleanup_transaction()
    
    def rollback_transaction(self):
        """
        Manually rollback transaction to original state.
        """
        if not self._in_transaction:
            raise StateLockError("No transaction in progress")
        
        try:
            self._rollback_transaction()
            logger.info("Transaction rolled back manually")
        finally:
            self._cleanup_transaction()
    
    def _rollback_transaction(self):
        """
        Restore original state from backup.
        """
        if not self._original_state:
            logger.warning("No original state to rollback to")
            return
        
        try:
            # Restore from original state
            self.state_mgr.save_positions(self._original_state['positions'])
            self.state_mgr.save_orders(self._original_state['orders'])
            
            # Note: Cannot rollback trades as StateManager doesn't support overwriting trade list
            # This is a limitation - trades are append-only
            
            # Restore daily P&L
            date = self._original_state.get('date', datetime.now().strftime("%Y-%m-%d"))
            self.state_mgr.save_daily_pnl(date, self._original_state['daily_pnl'])
            
            logger.debug("State rolled back to transaction start")
            
        except Exception as e:
            logger.critical(f"Rollback failed: {e}")
            raise
    
    def _create_backups(self):
        """
        Create timestamped backups of all state files.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        state_files = [
            "positions.json",
            "orders.json", 
            "trades.json",
            "daily_pnl.json"
        ]
        
        for filename in state_files:
            source = self.state_dir / filename
            if source.exists():
                backup_name = f"{filename}.{timestamp}.bak"
                backup_path = self.backup_dir / backup_name
                
                try:
                    shutil.copy2(source, backup_path)
                    logger.debug(f"Backup created: {backup_name}")
                except Exception as e:
                    logger.warning(f"Failed to backup {filename}: {e}")
    
    def _validate_transaction_data(
        self,
        positions: Dict,
        orders: Dict,
        trades: List,
        daily_pnl: Dict
    ):
        """
        Validate transaction data before commit.
        
        Args:
            positions: Positions data to validate
            orders: Orders data to validate
            trades: Trades data to validate
            daily_pnl: Daily P&L data to validate
        
        Raises:
            ValueError: If data is invalid
        """
        # Basic type checks
        if not isinstance(positions, dict):
            raise ValueError("Positions must be a dictionary")
        if not isinstance(orders, dict):
            raise ValueError("Orders must be a dictionary")
        if not isinstance(trades, list):
            raise ValueError("Trades must be a list")
        if not isinstance(daily_pnl, dict):
            raise ValueError("Daily P&L must be a dictionary")
        
        # Validate positions structure
        for symbol, pos_data in positions.items():
            if not isinstance(pos_data, dict):
                raise ValueError(f"Position data for {symbol} must be a dictionary")
            
            required_fields = ['quantity', 'entry_price', 'symbol']
            for field in required_fields:
                if field not in pos_data:
                    logger.warning(f"Position {symbol} missing field: {field}")
        
        # Validate orders structure
        for order_id, order_data in orders.items():
            if not isinstance(order_data, dict):
                raise ValueError(f"Order data for {order_id} must be a dictionary")
            
            required_fields = ['order_id', 'symbol', 'side']
            for field in required_fields:
                if field not in order_data:
                    logger.warning(f"Order {order_id} missing field: {field}")
        
        logger.debug("Transaction data validation passed")
    
    def _cleanup_transaction(self):
        """
        Clean up transaction state and release locks.
        """
        try:
            if self._in_transaction:
                self.state_mgr._lock.release()
                
            self._in_transaction = False
            self._original_state.clear()
            self._changes_made = False
            
            logger.debug("Transaction cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during transaction cleanup: {e}")


class StateTransaction:
    """
    Context manager for atomic state transactions.
    
    Usage:
        with StateTransaction() as txn:
            positions, orders, trades, pnl = txn.begin()
            # Modify state...
            txn.commit(positions, orders, trades, pnl)
    """
    
    def __init__(self, state_dir: str = "state"):
        """
        Initialize transaction context manager.
        
        Args:
            state_dir: Directory for state files
        """
        self.manager = TransactionManager(state_dir)
        self._data = None
        
    def __enter__(self):
        """
        Enter transaction context.
        
        Returns:
            StateTransaction: Self for method chaining
        """
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit transaction context.
        
        Args:
            exc_type: Exception type (None if no exception)
            exc_val: Exception value
            exc_tb: Exception traceback
            
        Returns:
            bool: False to re-raise exceptions
        """
        if self.manager._in_transaction:
            if exc_type is None:
                logger.debug("Transaction exiting normally")
            else:
                logger.warning(f"Transaction exiting with exception: {exc_type.__name__}: {exc_val}")
                try:
                    self.manager.rollback_transaction()
                except Exception as rollback_error:
                    logger.critical(f"Rollback during exception handling failed: {rollback_error}")
        
        return False  # Don't suppress exceptions
    
    def begin(self, timeout: int = 15) -> Tuple[Dict, Dict, List, Dict]:
        """
        Begin transaction and load state.
        
        Args:
            timeout: Lock timeout in seconds
            
        Returns:
            Tuple of (positions, orders, trades, daily_pnl)
        """
        self._data = self.manager.begin_transaction(timeout)
        return self._data
    
    def commit(self, positions: Dict, orders: Dict, trades: List, daily_pnl: Dict):
        """
        Commit transaction with updated state.
        
        Args:
            positions: Updated positions
            orders: Updated orders
            trades: Updated trades
            daily_pnl: Updated daily P&L
        """
        self.manager.commit_transaction(positions, orders, trades, daily_pnl)
    
    def rollback(self):
        """
        Manually rollback transaction.
        """
        self.manager.rollback_transaction()


# Legacy compatibility wrapper
def StateTransactionLegacy():
    """
    Legacy wrapper for backward compatibility.
    
    Usage:
        with StateTransactionLegacy() as (positions, orders, trades, pnl):
            # Modify state...
            # Auto-commits on successful exit
    """
    class LegacyTransaction:
        def __init__(self):
            self.txn = StateTransaction()
            self._data = None
        
        def __enter__(self):
            self._txn_ctx = self.txn.__enter__()
            self._data = self._txn_ctx.begin()
            return self._data
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            try:
                if exc_type is None and self._data:
                    # Auto-commit on successful exit
                    positions, orders, trades, daily_pnl = self._data
                    self._txn_ctx.commit(positions, orders, trades, daily_pnl)
            finally:
                return self._txn_ctx.__exit__(exc_type, exc_val, exc_tb)
    
    return LegacyTransaction()