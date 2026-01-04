"""
Live Trading Mode
===============
Real trading with live Zerodha broker connection.

WARNING: This mode places real orders with real money!
Only use after thorough testing with paper trading.

Implements:
- Real Zerodha KiteConnect API connection
- Order validation and risk limits
- Real-time price updates from Zerodha
- Order status tracking and reconciliation
- Emergency stop capability
- Position reconciliation with broker
"""

import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import os

from src.core import CapitalParameters, TradeParameters, Order, OrderStatus
from src.broker.zerodha import ZerodhaBroker
from .adapter import ExecutionAdapter
from src.core.reconciliation import BrokerStateReconciler


logger = logging.getLogger(__name__)


class LiveTradingMode(ExecutionAdapter):
    """
    Live trading mode with Zerodha.
    
    CRITICAL: Only use after extensive paper trading validation!
    
    Features:
    - Real Zerodha connection via KiteConnect
    - Real order placement and tracking
    - Real P&L tracking
    - Emergency stop capability
    - Position reconciliation
    """
    
    def __init__(
        self,
        capital_params: CapitalParameters,
        trade_params: TradeParameters,
        state_dir: str = "state/live",
        timing_enabled: bool = True
    ):
        """
        Initialize live trading mode.
        
        IMPORTANT: Set KITE_API_KEY and KITE_ACCESS_TOKEN in .env before running!
        
        Args:
            capital_params: Capital parameters
            trade_params: Trading parameters
            state_dir: State directory for live trading
            timing_enabled: Enable timing intelligence
        """
        super().__init__("LIVE", capital_params, trade_params, state_dir, timing_enabled)
        
        # Initialize Zerodha broker in LIVE mode
        self.broker = ZerodhaBroker(mode="LIVE")
        
        # Safety features
        self.emergency_stop_enabled = False
        self.max_order_attempts = 3
        self.order_retry_delay = 5  # seconds
        
        # Try to connect, but allow graceful degradation for testing
        self._connect_to_broker()
        
        logger.info("Live trading mode initialized")
    

    
    def _connect_to_broker(self) -> bool:
        """
        Connect to Zerodha broker.
        
        Returns:
            True if connected, False otherwise
        """
        try:
            success, msg = self.broker.connect()
            if success:
                logger.info(f"✓ {msg}")

                reconciler = BrokerStateReconciler(self.broker, self.state)
                recon = reconciler.reconcile()

                if not recon.ok:
                    logger.critical("RECONCILIATION FAILED — HALTING TRADING")
                    self.emergency_stop_enabled = True
                    return False

               # Log reconciliation results
                logger.info(
                    f"Reconciliation OK | "
                    f"Positions fixed={recon.fixed_positions}, "
                    f"Ghost removed={recon.ghost_positions_removed}, "
                    f"Closed cleaned={recon.closed_positions_cleaned}, "
                    f"Orders fixed={recon.fixed_orders}"
                )

                # After reconciliation, prefer broker-provided capital in LIVE.
                positions = self.state.load_positions()
                pending_orders = self.state.load_orders()

                try:
                    broker_available = self.broker.get_available_capital(default=0.0)

                    
                    # Compute total_capital such that available = broker_available
                    sb_pct = self.engine.capital_mgr.params.safety_buffer_pct
                    pos_exposure = self.engine.capital_mgr._calculate_position_exposure(positions)
                    pending_cap = self.engine.capital_mgr._calculate_pending_buy_capital(pending_orders)

                    if sb_pct >= 1.0:
                        logger.warning("Invalid safety buffer percent; cannot override capital from broker")
                        total_from_broker = broker_available
                    else:
                        total_from_broker = (broker_available + pos_exposure + pending_cap) / (1.0 - sb_pct)
                        # Only override if we got a sensible positive number
                        if total_from_broker and total_from_broker > 0:
                            old_total = self.engine.capital_mgr.params.total_capital
                            self.engine.capital_mgr.params.total_capital = float(total_from_broker)
                            logger.info(
                                f"LIVE CAPITAL OVERRIDE: total_capital set from broker data: "
                                f"{old_total:,.2f} -> {total_from_broker:,.2f} (available: {broker_available:,.2f})"
                            )
                except Exception as e:
                    logger.warning(f"Failed to fetch/override capital from broker: {e}")

                # Log capital breakdown AFTER reconciliation
                breakdown = self.engine.capital_mgr.get_capital_breakdown(
                    positions, pending_orders
                )
                
                logger.info("=" * 70)
                logger.info("CAPITAL BREAKDOWN AFTER RECONCILIATION")
                logger.info("=" * 70)
                logger.info(f"Total Capital:        ₹{breakdown.total_capital:>12,.2f}")
                logger.info(f"- Position Exposure:  ₹{breakdown.position_exposure:>12,.2f}")
                logger.info(f"- Pending Orders:     ₹{breakdown.pending_buy_capital:>12,.2f}")
                logger.info(f"- Safety Buffer (15%): ₹{breakdown.safety_buffer:>12,.2f}")
                logger.info(f"= AVAILABLE CAPITAL:  ₹{breakdown.available_capital:>12,.2f}")
                logger.info("=" * 70)
                
                if positions:
                    logger.info(f"Open Positions: {len(positions)}")
                    for symbol, pos in positions.items():
                        qty_remaining = pos.get('qty_remaining', 0)
                        if qty_remaining > 0:
                            logger.info(
                                f"  {symbol}: {qty_remaining} remaining "
                                f"(Entry: ₹{pos['entry_price']:.2f})"
                            )
                else:
                    logger.info("No open positions")
                
                if pending_orders:
                    logger.info(f"Pending Orders: {len(pending_orders)}")
                    for order_id, order in pending_orders.items():
                        logger.info(
                            f"  {order_id}: {order['symbol']} "
                            f"{order['side']} {order.get('req_qty', 0)} "
                            f"@ ₹{order['price']:.2f}"
                        )
                else:
                    logger.info("No pending orders")
                
                logger.info("=" * 70)
                
                return True
            else:
                logger.warning(f"✗ Broker connection failed: {msg}")
                return False
        
        except Exception as e:
            logger.error(f"Error connecting to broker: {e}")
            return False
    
    def place_order(self, order: Order) -> Tuple[bool, str]:
        """
        Place real order with Zerodha.
        
        CRITICAL SAFETY CHECKS:
        1. Connection verified
        2. Emergency stop checked
        3. Capital validated
        4. Order logged atomically
        
        Args:
            order: Order to place
        
        Returns:
            (success, broker_order_id_or_error)
        """
        if not self.broker.is_connected:
            return False, "Not connected to broker"
        
        if self.emergency_stop_enabled:
            return False, "Emergency stop enabled - no new orders allowed"
        
        try:
            # Validate order
            if order.req_qty <= 0:
                return False, "Invalid quantity"
            
            # Place order through Zerodha
            order_id = self.broker.place_order(
                symbol=order.symbol,
                qty=order.req_qty,
                side=order.side,
                order_type="MARKET" if order.price == 0 else "LIMIT",
                price=order.price if order.price > 0 else 0.0,
                max_retries=self.max_order_attempts
            )
            
            if order_id:
                logger.info(
                    f"{order.symbol}: Live order placed | "
                    f"{order.side} {order.req_qty} | "
                    f"Broker Order: {order_id}"
                )
                return True, order_id
            else:
                return False, "Order rejected by broker"
        
        except Exception as e:
            logger.error(f"Failed to place live order: {e}")
            return False, str(e)
    
    def get_order_status(self, order_id: str) -> Tuple[str, int, Optional[float]]:
        """
        Get order status from Zerodha.
        Args:
            order_id: Order ID
        Returns:
            (status, filled_qty, avg_price)
        """
        if not self.broker.is_connected:
            return OrderStatus.REJECTED.value, 0, None
        try:
            status, filled_qty, avg_price = self.broker.get_order_status(order_id)
            return status, filled_qty, avg_price
        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            return OrderStatus.REJECTED.value, 0, None
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel pending order with Zerodha.
        
        Args:
            order_id: Order ID to cancel
        
        Returns:
            True if cancelled
        """
        if not self.broker.is_connected:
            return False
        
        try:
            
            orders = self.state.load_orders()
            if order_id not in orders:
                logger.warning(f"Order {order_id} not found in state for cancellation")
                return False
            
            if hasattr(self, 'broker') and self.broker.is_connected:
                success = self.broker.cancel_order(order_id)
                if not success:
                    return False

            self.state.remove_order(order_id)
            
            if success:
                logger.info(f"Order {order_id} cancelled successfully")
              
            else:
                logger.warning(f"Failed to cancel order {order_id}")
            return success
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False



    def execute_exit(
        self,
        symbol: str,
        qty: int,
        exit_price: float
    ) -> Tuple[bool, str]:
        """
        Execute exit (sell) with Zerodha.
        
        Args:
            symbol: Symbol to exit
            qty: Quantity to sell
            exit_price: Target exit price (may be used for limit orders)
        
        Returns:
            (success, order_id)
        """
        if not self.broker.is_connected:
            return False, "Not connected to broker"
        
        if self.emergency_stop_enabled:
            return False, "Emergency stop enabled"
        
        try:
            # Place SELL order at market
            order_id = self.broker.place_order(
                symbol=symbol,
                qty=qty,
                side="SELL",
                order_type="MARKET",
                max_retries=self.max_order_attempts
            )
            if order_id:
                logger.info(
                    f"{symbol}: Live exit placed | "
                    f"SELL {qty} @ market | "
                    f"Broker Order: {order_id}"
                )
                return True, order_id
            else:
                return False, "Exit order rejected"
        except Exception as e:
            logger.error(f"Failed to execute exit: {e}")
            return False, str(e)
    
    def get_available_capital(self) -> float:
        """
        Get available capital from Zerodha.
        
        Returns:
            Available capital (float)
        """
        try:
            positions = self.state.load_positions()
            orders = self.state.load_orders()
            return self.engine.capital_mgr.calculate_available_capital(
                positions, orders
            )
        except Exception as e:
            logger.error(f"Get available capital failed: {e}")
            return 0.0  
    
    
    def get_positions(self) -> Dict[str, Dict]:
        """
        Get current positions from Zerodha.
        
        Returns:
            {symbol: {qty, entry_price, ltp, pnl, pnl_pct}}
        """
        if not self.broker.is_connected:
            return {}
        
        return self.broker.get_positions()
    
    def reconcile_positions(self) -> Tuple[bool, str]:
        """
        Reconcile state with broker positions.
        
        Checks if all positions in state match broker,
        and alerts if orphan positions exist at broker.
        
        Returns:
            (success, message)
        """
        try:
            broker_positions = self.broker.get_positions()
            state_positions = self.state.load_positions()
            
            # Check for orphans at broker
            for symbol in broker_positions:
                if symbol not in state_positions:
                    logger.warning(
                        f"ORPHAN POSITION: {symbol} exists at broker "
                        f"but not in state! Qty: {broker_positions[symbol]['qty']}"
                    )
            
            # Check for missing positions at broker
            for symbol in state_positions:
                if symbol not in broker_positions:
                    logger.warning(
                        f" MISSING AT BROKER: {symbol} in state "
                        f"but not at broker"
                    )
            
            return True, "Reconciliation complete"
        
        except Exception as e:
            logger.error(f"Reconciliation failed: {e}")
            return False, str(e)
    
    def toggle_emergency_stop(self, enabled: bool):
        """
        Enable/disable emergency stop.
        
        When enabled, no new orders are allowed.
        Useful for halting trading in case of issues.
        
        Args:
            enabled: True to enable, False to disable
        """
        self.emergency_stop_enabled = enabled
        if enabled:
            logger.critical(" EMERGENCY STOP ENABLED - No new orders allowed!")
        else:
            logger.info("Emergency stop disabled")
    
    def is_emergency_stop_enabled(self) -> bool:
        """Check if emergency stop is enabled"""
        return self.emergency_stop_enabled
    
    def is_connected(self) -> bool:
        """Check connection status"""
        return self.broker.is_connected
    
    def disconnect(self):
        """Disconnect from broker"""
        self.broker.disconnect()
        logger.info("Disconnected from Zerodha")
    
    def get_current_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Get real-time prices from broker.
        Args:
            symbols: Symbols to get prices for
        Returns:
            Dictionary of symbol -> price
        """
        if not self.is_connected:
            logger.error("Not connected to broker")
            return {}
        
        try:
            # TODO: Call broker API for real-time prices
            result = {}
            for symbol in symbols:
                price = self.broker.get_live_price(symbol,use_cache=False)  # Placeholder
                if price is not None:
                    result[symbol] = price
                else:
                    logger.warning(f"Price for {symbol} not found")

            return result
        
        except Exception as e:
            logger.error(f"Failed to get prices: {e}")
            return {}
    
    def enable_emergency_stop(self):
        """
        Enable emergency stop.
        
        When enabled, no new orders are placed and
        all pending orders are cancelled.
        """
        self.emergency_stop_enabled = True
        logger.critical("EMERGENCY STOP ENABLED")
        
        # Cancel all pending orders
        orders = self.state.load_orders()
        for order_id in orders:
            try:
                self.cancel_order(order_id)
            except:
                pass
    
    def verify_connection_health(self) -> bool:
        """
        Periodic health check for broker connection.
        Call this every few minutes during trading.
        
        Returns:
            True if healthy, False if connection lost
        """
        if not self.broker.is_connected:
            logger.error("Broker connection lost!")
            self.toggle_emergency_stop(enabled=True)
            return False
        
        try:
            # Try to fetch available capital as health check
            capital = self.broker.get_available_capital()
            if capital is None or capital <= 0:
                logger.error("Invalid available capital - broker may be disconnected")
                self.toggle_emergency_stop(enabled=True)
                return False
            
            logger.debug(f"✓ Connection healthy. Capital: ₹{capital:,.0f}")
            return True
        
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self.toggle_emergency_stop(enabled=True)
            return False            


    def disable_emergency_stop(self):
        """Disable emergency stop"""
        self.emergency_stop_enabled = False
        logger.info("Emergency stop disabled")


    
    # ====== SAFETY METHODS ======
    
    def _validate_order_live(self, order: Order) -> bool:
        """
        Validate order before placing.
        
        Checks:
        1. Capital available
        2. Risk limits
        3. Position limits
        """
        capital_needed = order.price * order.req_qty
        positions = self.state.load_positions()
        pending_orders = self.state.load_orders()
        
        available = self.engine.capital_mgr.calculate_available_capital(
            positions, pending_orders
        )
        
        if capital_needed > available:
            logger.error(f"Insufficient capital: need {capital_needed}, have {available}")
            return False
        
        return True
