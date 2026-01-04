"""
Execution Adapter - Base Class
==============================
Adapter pattern for different execution modes.
All modes (backtest, paper, live) inherit from this.
All use the same TradingEngine core logic.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime

from src.core import (
    TradingEngine, TradeParameters, CapitalParameters,
    StateManager, ScreenerSignal, Order
)


logger = logging.getLogger(__name__)


class ExecutionAdapter(ABC):
    """
    Abstract base class for execution modes.
    
    All concrete implementations (Paper, Live, Backtest)
    inherit from this and use the same TradingEngine.
    
    The adapter pattern isolates mode-specific logic:
    - Order placement
    - Order status tracking
    - Price updates
    - Exit execution
    """
    
    def __init__(
        self,
        mode: str,
        capital_params: CapitalParameters,
        trade_params: TradeParameters,
        state_dir: str = "state",
        timing_enabled: bool = True,
        symbols: Optional[List[str]] = None
    ):
        """
        Initialize execution adapter.
        
        Args:
            mode: Execution mode (PAPER, LIVE, BACKTEST)
            capital_params: Capital parameters
            trade_params: Trading parameters
            state_dir: State directory
            timing_enabled: Enable timing intelligence
            symbols: List of symbols for enhanced engine initialization
        """
        self.mode = mode
        self.capital_params = capital_params
        self.trade_params = trade_params
        
        # Core logic (same for all modes) - now with symbols support
        self.state = StateManager(state_dir)
        self.engine = TradingEngine(capital_params, trade_params, self.state, timing_enabled, symbols)
        
        logger.info(f"Initialized {mode} execution adapter")
    
    @property
    def timing_filter(self):
        """Access to timing filter for market regime monitoring."""
        return getattr(self.engine, 'timing_filter', None)
    
    # ====== ABSTRACT METHODS (implement in subclasses) ======
    
    @abstractmethod
    def place_order(self, order: Order) -> Tuple[bool, str]:
        """
        Place an order with the broker.
        Mode-specific implementation.
        
        Args:
            order: Order to place
        
        Returns:
            (success, broker_order_id_or_error)
        """
        pass
    
    @abstractmethod
    def get_order_status(self, order_id: str) -> Tuple[str, int, Optional[float]]:
        """
        Get order status from broker.
        Mode-specific implementation.
        
        Args:
            order_id: Order ID
        
        Returns:
            (status, filled_qty, avg_price)
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel pending order.
        Mode-specific implementation.
        
        Args:
            order_id: Order ID to cancel
        
        Returns:
            True if cancelled
        """
        pass
    
    @abstractmethod
    def execute_exit(
        self,
        symbol: str,
        qty: int,
        exit_price: float
    ) -> Tuple[bool, str]:
        """
        Execute exit order.
        Mode-specific implementation.
        
        Args:
            symbol: Symbol to exit
            qty: Quantity to exit
            exit_price: Exit price
        
        Returns:
            (success, message)
        """
        pass
    
    @abstractmethod
    def get_current_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Get current prices for symbols.
        Mode-specific implementation.
        
        Args:
            symbols: List of symbols
        
        Returns:
            Dictionary of symbol -> current price
        """
        pass
    
    # ====== CORE WORKFLOW (same for all modes) ======
    
    def process_signal(self, signal: ScreenerSignal) -> Tuple[bool, str]:
        """
        Process screener signal.
        Uses same core logic for all modes.
        
        Args:
            signal: Screener signal
        
        Returns:
            (success, message)
        """
        # Core logic (TradingEngine)
        success, order, reason = self.engine.process_signal(signal)
        
        if not success:
            return False, reason
        
        # Mode-specific: place order with broker
        placed, broker_id = self.place_order(order)
        if not placed:
            # Rollback state
            self.state.remove_order(order.order_id)
            return False, broker_id
        
        # Record successful entry for timing filter
        if self.engine.timing_enabled and self.engine.timing_filter:
            self.engine.timing_filter.record_entry_placed(signal.symbol)
        
        logger.info(f"{signal.symbol}: Signal processed and order placed")
        return True, f"Order {order.order_id} placed"
    
    def execute_cycle(self) -> Dict[str, Any]:
        """
        Main execution cycle.
        - Check orders for fills
        - Check positions for exits
        - Execute exits
        - Monitor market regime
        
        Returns:
            Execution report with market status
        """
        report = {
            'timestamp': datetime.now().isoformat(),
            'orders_filled': 0,
            'orders_failed': 0,
            'exits_executed': 0,
            'exits_failed': 0,
            'errors': [],
            'market_regime': None,
            'regime_confidence': None,
            'should_trade': True
        }
        
        # Add market regime status to report
        try:
            if self.engine.timing_enabled and self.engine.timing_filter:
                regime_info = self.engine.timing_filter.regime_manager.get_regime_info()
                report['market_regime'] = regime_info['regime']
                report['regime_confidence'] = regime_info['confidence']
                report['should_trade'] = regime_info['should_trade']
        except Exception as e:
            logger.warning(f"Failed to get regime info: {e}")
        
        try:
            # NEW: Check timing-based exits first
            if self.engine.timing_enabled and self.engine.timing_filter:
                positions = self.state.load_positions()
                for symbol, position in positions.items():
                    should_exit_timing, exit_reason = self.engine.timing_filter.should_exit_now(position)
                    if should_exit_timing:
                        logger.info(f"{symbol}: Timing exit triggered - {exit_reason}")
                        success, exit_id = self.execute_exit(
                            symbol,
                            position['qty_remaining'],
                            position.get('current_price', position['entry_price'])
                        )
                        if success:
                            report['exits_executed'] += 1
                        else:
                            report['exits_failed'] += 1
                            report['errors'].append(f"Timing exit failed for {symbol}: {exit_id}")
            
            # Check pending orders
            orders = self.state.load_orders()
            for order_id, order_data in list(orders.items()):
                try:
                    status, filled_qty, avg_price = self.get_order_status(order_id)
                    
                    if filled_qty > order_data.get('filled_qty', 0):
                        # Order filled (or partially)
                        success, position, msg = self.engine.on_order_filled(
                            order_id,
                            filled_qty,
                            avg_price or order_data['price']  # Use avg_price if available, fallback to original
                        )
                        if success:
                            report['orders_filled'] += 1
                        else:
                            report['orders_failed'] += 1
                            report['errors'].append(msg)
                
                except Exception as e:
                    report['errors'].append(f"Order {order_id} check failed: {e}")
            
            # Check positions for exits
            symbols = list(self.state.load_positions().keys())
            if symbols:
                prices = self.get_current_prices(symbols)
                exits = self.engine.check_and_handle_exits(prices)
                
                for symbol, qty, price, reason in exits:
                    try:
                        success, msg = self.execute_exit(symbol, qty, price)
                        if success:
                            self.engine.on_exit_executed(symbol, qty, price, reason)
                            report['exits_executed'] += 1
                        else:
                            report['exits_failed'] += 1
                            report['errors'].append(msg)
                    except Exception as e:
                        report['errors'].append(f"Exit {symbol} failed: {e}")
        
        except Exception as e:
            report['errors'].append(f"Execution cycle error: {e}")
        
        return report
    
    def get_status(self) -> Dict:
        """Get current trading status"""
        positions = self.state.load_positions()
        orders = self.state.load_orders()
        
        breakdown = self.engine.capital_mgr.get_capital_breakdown(positions, orders)
        
        return {
            'mode': self.mode,
            'positions': len(positions),
            'pending_orders': len(orders),
            'capital_breakdown': breakdown.to_dict(),
            'timestamp': datetime.now().isoformat()
        }

    def clear_all_state(self):
        """
        Clear all state for fresh start.
        Used primarily by backtest mode to ensure clean runs.
        """
        self.state.clear_all_state()
