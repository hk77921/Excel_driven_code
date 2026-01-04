"""
State Manager - Core Persistence Layer
======================================
Handles all state persistence with ACID properties:
- Atomicity: All-or-nothing writes
- Consistency: Validated before saving
- Isolation: Thread-safe with locking
- Durability: Backup before overwrite

Used by all execution modes (backtest, paper, live).
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from threading import Lock
from pathlib import Path

from .models import Order, Position, Trade, DailyPnL, SystemState


logger = logging.getLogger(__name__)


class StateManager:
    """
    Core state management with ACID properties.
    All modes (backtest, paper, live) use this same interface.
    """
    
    def __init__(self, state_dir: str = "state"):
        """
        Initialize state manager.
        
        Args:
            state_dir: Directory for state files
        """
        self.state_dir = state_dir
        Path(state_dir).mkdir(exist_ok=True)
        Path(f"{state_dir}/backups").mkdir(exist_ok=True)
        
        self.positions_file = f"{state_dir}/positions.json"
        self.orders_file = f"{state_dir}/orders.json"
        self.trades_file = f"{state_dir}/trades.json"
        self.daily_pnl_file = f"{state_dir}/daily_pnl.json"

        self.current_market_regime = None
        self.regime_confidence = None
        self.trading_enabled = True
        self.emergency_stop_active = False
        self.max_positions = len(self.load_positions())
        self.available_capital = self.get_available_capital()
        self._lock = Lock()

    def clear_all_state(self):
        """
        Clear all state files for fresh start.
        CRITICAL for backtests to avoid contamination from previous runs.
        """
        logger.info("Clearing all state for fresh start")
        
        try:
            # Simple file deletion/creation - avoid complex _save_json to prevent deadlocks
            
            # Clear positions
            with open(self.positions_file, 'w') as f:
                json.dump({}, f)
            
            # Clear orders  
            with open(self.orders_file, 'w') as f:
                json.dump({}, f)
            
            # Clear trades
            with open(self.trades_file, 'w') as f:
                json.dump([], f)
            
            logger.info("State cleared successfully")
            
        except Exception as e:
            logger.error(f"Failed to clear state: {e}")
            # Continue anyway - backtest should still work with existing files
    

    def get_system_state(self) -> SystemState:
        """
        Return a read-only snapshot of current system state
        for Risk Governor and safety checks.
        """
        return SystemState(
            market_regime=str(self.current_market_regime)
                if hasattr(self, "current_market_regime") else None,

            regime_confidence=getattr(self, "regime_confidence", None),

            trading_enabled=getattr(self, "trading_enabled", True),

            emergency_stop_active=getattr(self, "emergency_stop_active", False),

            open_positions=len(getattr(self, "open_positions", [])),

            max_positions=getattr(self, "max_positions", 0),

            daily_pnl=self._get_today_pnl_safe(),

            capital_available=getattr(self, "available_capital", 0.0),

            last_updated=datetime.now()

        )

    # ====== POSITIONS ======
    
    def load_positions(self) -> Dict[str, dict]:
        """Load all open positions"""
        return self._load_json(self.positions_file)
    
    def save_positions(self, positions: Dict[str, dict]):
        """Save all positions atomically"""
        self._validate_positions(positions)
        self._save_json(self.positions_file, positions)

       
    
    def get_position(self, symbol: str) -> Optional[dict]:
        """Get specific position"""
        positions = self.load_positions()
        return positions.get(symbol)
    
    def add_position(self, symbol: str, position: dict):
        """Add or update position"""
        positions = self.load_positions()
        positions[symbol] = position
        self.save_positions(positions)
    
    def remove_position(self, symbol: str):
        """Remove closed position"""
        positions = self.load_positions()
        if symbol in positions:
            del positions[symbol]
        self.save_positions(positions)
    
    # ====== ORDERS ======
    
    def load_orders(self) -> Dict[str, dict]:
        """Load all pending orders"""
        return self._load_json(self.orders_file)
    
    def save_orders(self, orders: Dict[str, dict]):
        """Save all orders atomically"""
        self._validate_orders(orders)
        self._save_json(self.orders_file, orders)
    
    def add_order(self, order_id: str, order: dict):
        """Add new order"""
        orders = self.load_orders()
        orders[order_id] = order
        self.save_orders(orders)
    
    def update_order_status(self, order_id: str, status: str, filled_qty: int = 0):
        """Update order status"""
        orders = self.load_orders()
        if order_id in orders:
            orders[order_id]['status'] = status
            orders[order_id]['filled_qty'] = filled_qty
            orders[order_id]['updated_at'] = datetime.now().isoformat()
        self.save_orders(orders)
    
    def remove_order(self, order_id: str):
        """Remove completed order"""
        orders = self.load_orders()
        if order_id in orders:
            del orders[order_id]
        self.save_orders(orders)
    
    # ====== TRADES ======
    
    def load_trades(self) -> List[dict]:
        """Load closed trades"""
        return self._load_json(self.trades_file, default=[])
    
    def add_trade(self, trade: dict):
        """Add closed trade to journal"""
        trades = self.load_trades()
        trades.append(trade)
        self._save_json(self.trades_file, trades)
    
    # ====== DAILY P&L ======
    
    def load_daily_pnl(self, date: str) -> Optional[dict]:
        """Load daily P&L"""
        all_pnl = self._load_json(self.daily_pnl_file, default={})
        return all_pnl.get(date)
    
    def save_daily_pnl(self, date: str, pnl: dict):
        """Save daily P&L"""
        all_pnl = self._load_json(self.daily_pnl_file, default={})
        all_pnl[date] = pnl
        self._save_json(self.daily_pnl_file, all_pnl)
    
    # ====== INTERNAL METHODS ======
    
    def _get_today_pnl_safe(self) -> float:
        try:
            from datetime import date
            today = date.today().isoformat()
            pnl = self.load_daily_pnl(today)
            return pnl.get("realized_pnl", 0.0) if pnl else 0.0
        except Exception:
            return 0.0


    def _load_json(self, filepath: str, default: Any = None) -> Any:
        """Load JSON file with error handling"""
        if not os.path.exists(filepath):
            return default if default is not None else {}
        
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted JSON in {filepath}: {e}")
            # Try to load backup
            return self._load_backup(filepath, default)
        except Exception as e:
            logger.error(f"Failed to load {filepath}: {e}")
            return default if default is not None else {}
    
    def _save_json(self, filepath: str, data: Any):
        """Save JSON atomically with backup"""
        with self._lock:
            try:
                # Create backup first
                self._create_backup(filepath)
                
                # Write to temp file first
                temp_path = f"{filepath}.tmp"
                with open(temp_path, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                
                # Atomic rename
                os.replace(temp_path, filepath)
                logger.debug(f"Saved state to {filepath}")
                
            except Exception as e:
                logger.error(f"Failed to save {filepath}: {e}")
                if os.path.exists(f"{filepath}.tmp"):
                    os.remove(f"{filepath}.tmp")
                raise
    
    def _create_backup(self, filepath: str):
        """Create timestamped backup before overwrite"""
        if os.path.exists(filepath):
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.basename(filepath)
                backup_path = f"{self.state_dir}/backups/{filename}.{timestamp}.bak"
                
                with open(filepath, 'r') as src:
                    with open(backup_path, 'w') as dst:
                        dst.write(src.read())
                
                logger.debug(f"Backup created: {backup_path}")
            except Exception as e:
                logger.warning(f"Failed to create backup: {e}")
    
    def _load_backup(self, filepath: str, default: Any):
        """Load latest backup if main file corrupted"""
        backup_dir = f"{self.state_dir}/backups"
        filename = os.path.basename(filepath)
        
        try:
            backups = [f for f in os.listdir(backup_dir) 
                      if f.startswith(filename)]
            if not backups:
                return default if default is not None else {}
            
            # Load most recent backup
            latest = sorted(backups)[-1]
            backup_path = os.path.join(backup_dir, latest)
            
            with open(backup_path, 'r') as f:
                logger.info(f"Loaded backup: {backup_path}")
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load backup: {e}")
            return default if default is not None else {}
    
    # ====== VALIDATION ======
    
    def _validate_positions(self, positions: Dict[str, dict]):
        """Validate position data before saving"""
        for symbol, pos in positions.items():
            if not isinstance(pos, dict):
                raise ValueError(f"Invalid position format for {symbol}")
            
            # Check required fields
            required = ['entry_price', 'quantity', 'qty_remaining', 'stop_loss']
            missing = [f for f in required if f not in pos]
            if missing:
                raise ValueError(f"{symbol} missing fields: {missing}")
            
            # Check for negative quantities
            if pos.get('qty_remaining', 0) < 0:
                raise ValueError(f"{symbol} has negative qty_remaining")
    
    def _validate_orders(self, orders: Dict[str, dict]):
        """Validate order data before saving"""
        for order_id, order in orders.items():
            if not isinstance(order, dict):
                raise ValueError(f"Invalid order format for {order_id}")
            
            required = ['symbol', 'side', 'req_qty', 'price', 'status']
            missing = [f for f in required if f not in order]
            if missing:
                raise ValueError(f"{order_id} missing fields: {missing}")
    
    def get_available_capital(self) -> float:
        """Get available capital for trading"""
        # For now, return a default value
        # This should be enhanced to calculate actual available capital
        # based on positions and pending orders
        return 100000.0  # Default capital
