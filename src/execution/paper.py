"""
Paper Trading Mode
=================
Simulates trading without real money or API calls.
Used for testing logic and strategy before live trading.

Uses Zerodha API for:
- Realistic price data (via yfinance for paper mode)
- Order simulation based on real market prices
- Position tracking with paper positions
- P&L calculations
"""

import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import time

from src.core import CapitalParameters, TradeParameters, Order, OrderStatus
from src.broker.zerodha import ZerodhaBroker
from .adapter import ExecutionAdapter


logger = logging.getLogger(__name__)


class PaperTradingMode(ExecutionAdapter):
    """
    Paper trading (simulated trading) with Zerodha.
    
    Simulates order fills and price updates using:
    - Real market prices (yfinance)
    - Simulated order fills
    - Paper position tracking
    
    Perfect for testing strategy logic without real money.
    """
    
    def __init__(
        self,
        capital_params: CapitalParameters,
        trade_params: TradeParameters,
        state_dir: str = "state/paper",
        timing_enabled: bool = True,
        symbols: Optional[List[str]] = None
    ):
        """
        Initialize paper trading mode.
        
        Args:
            capital_params: Capital parameters
            trade_params: Trading parameters
            state_dir: State directory for paper trading
            timing_enabled: Enable timing intelligence
            symbols: List of symbols for enhanced engine initialization
        """
        super().__init__("PAPER", capital_params, trade_params, state_dir, timing_enabled, symbols)
        
        # Initialize Zerodha broker in PAPER mode
        self.broker = ZerodhaBroker(mode="PAPER")
        success, msg = self.broker.connect()
        
        if success:
            logger.info("Paper trading initialized")
        else:
            logger.warning(f"Paper broker initialization: {msg}")
        
        # Paper-specific tracking
        self.paper_positions: Dict[str, Dict] = {}
        self.paper_orders: Dict[str, Dict] = {}
        
        logger.info("Paper trading mode initialized")
        self.prices: Dict[str, float] = {}
    
    def place_order(self, order: Order) -> Tuple[bool, str]:
        """
        Simulate order placement.
        
        Uses Zerodha broker to get realistic prices.
        Order fills simulated after brief delay.
        
        Args:
            order: Order to place
        
        Returns:
            (success, order_id)
        """
        try:
            # Get current price from Zerodha (yfinance for paper mode)
            current_price = self.broker.get_live_price(order.symbol)
            if current_price is None:
                current_price = order.price
            
            # Place order through broker (paper mode)
            order_id = self.broker.place_order(
                symbol=order.symbol,
                qty=order.req_qty,
                side=order.side,
                order_type="MARKET" if order.price == 0 else "LIMIT",
                price=order.price if order.price > 0 else current_price
            )
            
            if order_id:
                logger.info(
                    f"{order.symbol}: Paper order placed | "
                    f"{order.side} {order.req_qty} @ ₹{current_price:.2f} | "
                    f"Order: {order_id}"
                )
                return True, order_id
            else:
                return False, "Failed to place paper order"
        
        except Exception as e:
            logger.error(f"Paper order placement failed: {e}")
            return False, str(e)
    
    def get_order_status(self, order_id: str) -> Tuple[str, int, Optional[float]]:
        """
        Check paper order status.
        
        Orders simulate instant fills after 1 second.
        
        Args:
            order_id: Order ID
        
        Returns:
            (status, filled_qty, avg_price)
        """
        status, filled_qty, avg_price = self.broker.get_order_status(order_id)
        return status, filled_qty, avg_price
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel paper order.
        
        Args:
            order_id: Order to cancel
        
        Returns:
            True if cancelled
        """
        return self.broker.cancel_order(order_id)
    
    def execute_exit(
        self,
        symbol: str,
        qty: int,
        exit_price: float
    ) -> Tuple[bool, str]:
        """
        Execute exit in paper trading.
        
        Args:
            symbol: Symbol to exit
            qty: Quantity to sell
            exit_price: Exit price (not used in paper market orders)
        
        Returns:
            (success, order_id)
        """
        try:
            # Get current price for exit
            current_price = self.broker.get_live_price(symbol)
            if current_price is None:
                current_price = exit_price
            
            # Place SELL order
            order_id = self.broker.place_order(
                symbol=symbol,
                qty=qty,
                side="SELL",
                order_type="MARKET"
            )
            
            if order_id:
                logger.info(
                    f"{symbol}: Paper exit | "
                    f"SELL {qty} @ ₹{current_price:.2f}"
                )
                return True, order_id
            else:
                return False, "Failed to place exit order"
        
        except Exception as e:
            logger.error(f"Paper exit failed: {e}")
            return False, str(e)
    
    def get_live_price(self, symbol: str) -> Optional[float]:
        """
        Get live price for a symbol.
        
        Paper mode uses yfinance prices.
        
        Args:
            symbol: Symbol to get price for
        
        Returns:
            Price or None
        """
        return self.broker.get_live_price(symbol)
    
    def get_available_capital(self) -> float:
        """
        Get available trading capital.
        
        Paper mode returns configured default capital.
        
        Returns:
            Available capital
        """
        return self.broker.get_available_capital(
            default=self.capital_params.total_capital
        )
    
    def get_positions(self) -> Dict[str, Dict]:
        """
        Get current positions.
        
        Returns:
            {symbol: {qty, entry_price, ltp, pnl, ...}}
        """
        return self.broker.get_positions()
    
    def is_connected(self) -> bool:
        """Check connection status"""
        return self.broker.is_connected
    
    def disconnect(self):
        """Disconnect broker"""
        self.broker.disconnect()
    
    def get_current_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Get simulated prices for symbols.
        
        For paper trading, use last set prices
        (normally set by backtest engine or manual input).
        
        Args:
            symbols: Symbols to get prices for
        
        Returns:
            Dictionary of symbol -> price
        """
        result = {}
        for symbol in symbols:
            if symbol in self.prices:
                result[symbol] = self.prices[symbol]
            else:
                # No price data, skip
                pass
        
        return result
    
    def set_price(self, symbol: str, price: float):
        """
        Set simulated price for symbol.
        
        Used for testing or simulating price updates.
        
        Args:
            symbol: Symbol
            price: New price
        """
        self.prices[symbol] = price
        logger.debug(f"{symbol}: Paper price set to ₹{price:.2f}")
    
    def set_prices(self, prices: Dict[str, float]):
        """
        Set prices for multiple symbols.
        
        Args:
            prices: Dictionary of symbol -> price
        """
        self.prices.update(prices)
        logger.debug(f"Paper prices updated for {len(prices)} symbols")
