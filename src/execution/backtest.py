"""
Backtest Mode
=============
Backtests strategy on historical data.

Uses the same TradingEngine as paper and live modes,
but processes data points sequentially to simulate trading over time.

Features:
- Historical data processing
- Order fills based on historical prices
- Performance metrics and statistics
- Trade-by-trade analysis
"""

import logging
from typing import Dict, List, Tuple, Optional
import pandas as pd
from datetime import datetime

from src.core import CapitalParameters, TradeParameters, Order, OrderStatus
from .adapter import ExecutionAdapter


logger = logging.getLogger(__name__)


class BacktestMode(ExecutionAdapter):
    """
    Backtest mode for historical simulation.
    
    Processes historical data sequentially and simulates trading
    using the same TradingEngine as paper and live modes.
    """
    
    def __init__(
        self,
        capital_params: CapitalParameters,
        trade_params: TradeParameters,
        state_dir: str = "state/backtest",
        timing_enabled: bool = True
    ):
        """
        Initialize backtest mode.
        
        Args:
            capital_params: Capital parameters
            trade_params: Trading parameters
            state_dir: State directory for backtest
            timing_enabled: Enable timing intelligence
        """
        super().__init__("BACKTEST", capital_params, trade_params, state_dir, timing_enabled)
        
        # Backtest-specific settings
        self.data = {}  # Historical data for each symbol
        self.current_index = {}  # Current bar index for each symbol
        self.prices = {}  # Current prices (from bar)
        self.trades = []  # All trades executed
        self.daily_pnl = []  # Daily P&L tracking
        self.current_date = None
        
        # Per-symbol statistics tracking
        self.symbol_stats = {}  # Individual symbol performance
        self.symbol_trades = {}  # Trades per symbol
        self.symbol_pnl = {}  # P&L per symbol
        
        logger.info("Backtest mode initialized")
    
    def load_data(self, symbol: str, df: pd.DataFrame):
        """
        Load historical data for a symbol.
        
        Expected columns: date, open, high, low, close, volume
        
        Args:
            symbol: Symbol to load data for
            df: DataFrame with OHLCV data
        """
        if df.empty:
            logger.warning(f"{symbol}: Empty dataframe provided")
            return
        
        # Ensure required columns
        required = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required):
            logger.error(f"{symbol}: Missing required columns. Need: {required}")
            return
        
        self.data[symbol] = df.reset_index(drop=True)
        self.current_index[symbol] = 0
        
        # Initialize symbol statistics
        self.symbol_stats[symbol] = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'gross_profit': 0.0,
            'gross_loss': 0.0,
            'max_profit': 0.0,
            'max_loss': 0.0,
            'avg_profit': 0.0,
            'avg_loss': 0.0,
            'bars_in_market': 0,
            'data_bars': len(df)
        }
        self.symbol_trades[symbol] = []
        self.symbol_pnl[symbol] = 0.0
        
        logger.info(
            f"{symbol}: Loaded {len(df)} bars "
            f"({df.iloc[0].get('date', 'N/A')} to {df.iloc[-1].get('date', 'N/A')})"
        )
    
    def load_csv(self, symbol: str, filepath: str):
        """
        Load historical data from CSV file.
        
        Args:
            symbol: Symbol
            filepath: Path to CSV file
        """
        try:
            df = pd.read_csv(filepath)
            self.load_data(symbol, df)
        except Exception as e:
            logger.error(f"{symbol}: Failed to load CSV: {e}")
    
    def place_order(self, order: Order) -> Tuple[bool, str]:
        """
        Place order in backtest.
        
        Orders are recorded but not immediately filled.
        Fills are checked during execute_cycle.
        
        Args:
            order: Order to place
        
        Returns:
            (success, order_id)
        """
        try:
            logger.info(
                f"{order.symbol}: Backtest order placed | "
                f"{order.side} {order.req_qty} @ Rs.{order.price:.2f}"
            )
            return True, order.order_id
        except Exception as e:
            logger.error(f"Failed to place backtest order: {e}")
            return False, str(e)
    
    def get_order_status(self, order_id: str) -> Tuple[str, int, Optional[float]]:
        """
        Check order status in backtest.
        
        Orders fill immediately at the order price or better
        (using high/low from bar).
        
        Args:
            order_id: Order ID
        
        Returns:
            (status, filled_qty, avg_price)
        """
        orders = self.state.load_orders()
        if order_id not in orders:
            return OrderStatus.REJECTED.value, 0, None
        
        order = orders[order_id]
        symbol = order['symbol']
        
        # Check if we have current bar data
        if symbol not in self.data:
            return OrderStatus.PENDING.value, order.get('filled_qty', 0), None
        
        if self.current_index[symbol] >= len(self.data[symbol]):
            return OrderStatus.PENDING.value, order.get('filled_qty', 0), None
        
        bar = self.data[symbol].iloc[self.current_index[symbol]]
        order_price = order['price']
        
        # Check if order can fill at this bar
        filled_qty = order.get('filled_qty', 0)
        req_qty = order['req_qty']
        
        # Simulate order fill based on price
        # For buys: fill if price reaches order price or lower  
        # For sells: fill if price reaches order price or higher
        if filled_qty < req_qty:
            can_fill = False
            
            if order['side'] == 'BUY':
                # Buy order fills if low price <= order price
                can_fill = bar['low'] <= order_price
            elif order['side'] == 'SELL':
                # Sell order fills if high price >= order price
                can_fill = bar['high'] >= order_price
            
            if can_fill:
                filled_qty = req_qty  # Fill all for simplicity
                
                # CRITICAL: Notify engine to create position BEFORE updating order status
                # to avoid double-counting in on_order_filled method
                if order['side'] == 'BUY':
                    success, position, reason = self.engine.on_order_filled(
                        order_id, filled_qty, order_price
                    )
                    if success:
                        logger.info(f"{symbol}: Position created from filled order")
                    else:
                        logger.error(f"{symbol}: Failed to create position: {reason}")
                
                # Update order status (this will be done by engine.on_order_filled too, but for consistency)
                order['filled_qty'] = filled_qty
                order['status'] = OrderStatus.FILLED.value
                order['fill_price'] = order_price  # Simplified - use order price
                
                # Save updated order (may be redundant after engine call, but safe)
                orders[order_id] = order
                self.state.save_orders(orders)
                
                # Track trade for symbol statistics
                self._track_trade(symbol, order, order_price, filled_qty)
                
                logger.info(f"{symbol}: Order {order_id} filled - {order['side']} {filled_qty} @ Rs.{order_price:.2f}")
        
        return order.get('status', OrderStatus.PENDING.value), filled_qty, order.get('fill_price', order_price)

   

    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel order in backtest.
        
        Args:
            order_id: Order to cancel
        
        Returns:
            True if cancelled
        """
        orders = self.state.load_orders()
        if order_id not in orders:
            return False
        
        order = orders[order_id]
        order['status'] = OrderStatus.CANCELLED.value
        self.state.save_orders(orders)
        
        logger.info(f"Order {order_id} cancelled")
        return True
    
    def execute_exit(
        self,
        symbol: str,
        qty: int,
        exit_price: float
    ) -> Tuple[bool, str]:
        """
        Execute exit in backtest.
        
        Exit is simulated using current bar prices.
        Also tracks P&L for symbol statistics.
        
        Args:
            symbol: Symbol to exit
            qty: Quantity to exit
            exit_price: Target exit price
        
        Returns:
            (success, message)
        """
        try:
            # Check if this exit completes the position
            positions = self.state.load_positions()
            if symbol not in positions:
                logger.warning(f"{symbol}: No position found for exit")
                return False, "No position found"
            
            position = positions[symbol]
            remaining_before = position.get('qty_remaining', 0)
            remaining_after = remaining_before - qty
            
            # Track the exit trade for P&L calculation (but don't increment win/loss counters yet)
            self._track_exit_trade(symbol, qty, exit_price)
            
            # If position is completely closed, mark the trade as complete
            if remaining_after <= 0:
                # Calculate total P&L for this completed trade
                total_pnl = self.symbol_pnl.get(symbol, 0.0)
                self._complete_trade(symbol, total_pnl)
            
            logger.info(
                f"{symbol}: Backtest exit executed | "
                f"SELL {qty} @ Rs.{exit_price:.2f} | "
                f"Remaining: {remaining_after}"
            )
            return True, f"Exited {qty} shares at Rs.{exit_price:.2f}"
        except Exception as e:
            logger.error(f"Exit failed for {symbol}: {e}")
            return False, str(e)
    
    def get_current_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Get current prices from historical bars.
        
        Uses close price from the current bar for each symbol.
        
        Args:
            symbols: Symbols to get prices for
        
        Returns:
            Dictionary of symbol -> price
        """
        result = {}
        for symbol in symbols:
            if symbol in self.prices:
                result[symbol] = self.prices[symbol]
            elif symbol in self.data and self.current_index[symbol] < len(self.data[symbol]):
                bar = self.data[symbol].iloc[self.current_index[symbol]]
                result[symbol] = bar['close']
        return result
    
    def step(self, bar_index: Optional[int] = None) -> bool:
        """
        Move to next bar in all symbols.
        
        Args:
            bar_index: Specific bar index to move to (optional)
        
        Returns:
            True if there are more bars, False if we've reached the end
        """
        has_more = False
        
        for symbol in self.data.keys():
            if bar_index is not None:
                self.current_index[symbol] = bar_index
            else:
                self.current_index[symbol] += 1
            
            # Update current prices
            if self.current_index[symbol] < len(self.data[symbol]):
                bar = self.data[symbol].iloc[self.current_index[symbol]]
                self.prices[symbol] = bar['close']
                self.current_date = bar.get('date', None)
                has_more = True
        
        return has_more
    
    def run_backtest(self, screener=None) -> Dict:
        """
        Run full backtest on loaded data.
        
        Args:
            screener: Optional screener instance for signal generation
        
        Returns:
            Dictionary with backtest results
        """
        logger.info("=" * 50)
        logger.info("BACKTEST STARTED")
        logger.info("=" * 50)
        
        # CRITICAL: Clear all state for clean backtest start
        logger.info("Clearing previous state for clean backtest start")
        self.clear_all_state()
        
        if not self.data:
            logger.error("No data loaded for backtest")
            return {"error": "No data loaded"}
        
        # Get max bars across all symbols
        max_bars = max(len(df) for df in self.data.values())
        
        # Track signals generated
        total_signals = 0
        signals_processed = 0
        
        # Process each bar
        for bar_idx in range(max_bars):
            if not self.step(bar_idx):
                break
            
            # Generate trading signals if screener available and we have enough history
            if screener is not None and bar_idx >= 3:  # Wait for some history
                try:
                    # Update screener with current market data for available symbols
                    current_symbols = []
                    current_prices = {}
                    
                    for symbol in self.data.keys():
                        if self.current_index[symbol] < len(self.data[symbol]):
                            bar_data = self.data[symbol].iloc[self.current_index[symbol]]
                            current_symbols.append(symbol)
                            current_prices[symbol] = bar_data['close']
                    
                    # Generate signals for current bar
                    if current_symbols:
                        logger.debug(f"Bar {bar_idx}: Trying to generate signals for {len(current_symbols)} symbols")
                        
                        # Try using actual Excel screener first, fallback to simple signals
                        signals = []
                        try:
                            # For backtest mode, use simple signal generation for performance
                            # The Excel screener is too heavy for bar-by-bar processing
                            logger.debug(f"Backtest mode: Using simple signal generation for bar {bar_idx}")
                            signals = self._generate_simple_signals(current_symbols, current_prices)
                            logger.debug(f"Bar {bar_idx}: Simple signal generator produced {len(signals)} signals")
                        except Exception as simple_e:
                            logger.debug(f"Simple signal generation failed at bar {bar_idx}: {simple_e}")
                            signals = []
                        
                        total_signals += len(signals)
                        
                        # Process each signal
                        for signal in signals:
                            success, msg = self.process_signal(signal)
                            if success:
                                signals_processed += 1
                                logger.info(f"Bar {bar_idx}: Signal processed for {signal.symbol}")
                            else:
                                logger.debug(f"Bar {bar_idx}: Signal rejected for {signal.symbol}: {msg.replace('₹', 'Rs.')}")
                
                except Exception as e:
                    logger.warning(f"Signal generation failed at bar {bar_idx}: {e}")
            
            # Execute trading cycle (check orders, exits)
            report = self.execute_cycle()
            
            # Reduced logging frequency to every 50 bars instead of 10
            if bar_idx % 50 == 0:
                status = self.get_status()
                breakdown = status['capital_breakdown']
                logger.info(
                    f"Bar {bar_idx}: Open Positions={status['positions']}, "
                    f"Capital=Rs.{breakdown['total_capital']:.0f}"
                )
        
        # Generate final report with symbol statistics
        final_status = self.get_status()
        symbol_statistics = self._generate_symbol_statistics()
        
        # Calculate total realized P&L from all symbol statistics
        total_realized_pnl = sum(stats['total_pnl'] for stats in symbol_statistics.values())
        final_capital_with_pnl = self.capital_params.total_capital + total_realized_pnl
        
        results = {
            'status': 'completed',
            'bars_processed': max_bars,
            'signals_generated': total_signals,
            'signals_processed': signals_processed,
            'final_capital': final_capital_with_pnl,
            'total_pnl': total_realized_pnl,
            'pnl_percentage': (total_realized_pnl / self.capital_params.total_capital * 100),
            'open_positions': final_status['positions'],
            'pending_orders': final_status['pending_orders'],
            'symbol_statistics': symbol_statistics
        }
        
        logger.info("=" * 50)
        logger.info("BACKTEST COMPLETED")
        logger.info(f"Signals Generated: {total_signals}")
        logger.info(f"Signals Processed: {signals_processed}")
        logger.info(f"Final Capital: Rs.{results['final_capital']:.2f}")
        logger.info(f"Total P&L: Rs.{results['total_pnl']:.2f}")
        logger.info(f"P&L %: {results['pnl_percentage']:.2f}%")
        logger.info("=" * 50)
        
        return results
    
    def _generate_simple_signals(self, symbols: List[str], prices: Dict[str, float]) -> List:
        """
        Generate simple trading signals for backtest.
        
        This is a simplified signal generation for demonstration.
        In production, you'd use the full ExcelScreener.
        
        Args:
            symbols: Available symbols
            prices: Current prices
            
        Returns:
            List of ScreenerSignal objects
        """
        from src.core.models import ScreenerSignal
        from datetime import datetime
        
        signals = []
        logger.debug(f"_generate_simple_signals called with {len(symbols)} symbols")
        
        for symbol in symbols[:5]:  # Limit to 5 signals per bar for testing
            if symbol not in self.data:
                logger.debug(f"{symbol}: Not in data dict")
                continue
                
            current_idx = self.current_index[symbol]
            logger.debug(f"{symbol}: Current index = {current_idx}")
            if current_idx < 3:  # Need at least 3 bars of history for backtest
                logger.debug(f"{symbol}: Not enough history (need >=3, have {current_idx})")
                continue
                
            # Get recent bars for simple analysis
            df = self.data[symbol]
            recent_bars = df.iloc[max(0, current_idx-2):current_idx+1]
            
            if len(recent_bars) < 3:
                continue
                
            try:
                # Simple momentum signal
                current_price = recent_bars.iloc[-1]['close']
                sma_3 = recent_bars['close'].tail(3).mean()
                sma_5 = recent_bars['close'].tail(5).mean() if len(recent_bars) >= 5 else sma_3
                
                # Volume check
                avg_volume = recent_bars['volume'].tail(3).mean()
                current_volume = recent_bars.iloc[-1]['volume']
                
                # Simple bullish signal: price above SMA3 (very relaxed conditions for testing)
                if (current_price > sma_3 * 0.98 and  # Price within 2% of SMA
                    current_volume > avg_volume * 0.5 and  # Very low volume threshold
                    current_price > 1):  # Minimal price filter
                    
                    # Calculate ATR for position sizing
                    high_low = recent_bars['high'] - recent_bars['low']
                    atr = high_low.tail(3).mean() if len(recent_bars) >= 3 else high_low.mean()
                    
                    signal = ScreenerSignal(
                        symbol=symbol,
                        score=80,  # Score above threshold (80 >= 75 for BULLISH)
                        atr=atr,
                        adx=25.0,  # Mock ADX value
                        volume_ratio=current_volume / avg_volume,
                        trend="BULLISH",
                        price=current_price,
                        sector="UNKNOWN",
                        timestamp=datetime.now(),
                        reasons="Simple momentum + volume"
                    )
                    
                    signals.append(signal)
                    
            except Exception as e:
                logger.warning(f"Signal generation failed for {symbol}: {e}")
        
        return signals
        
    def _track_exit_trade(self, symbol: str, exit_qty: int, exit_price: float):
        """Track exit trade and calculate P&L for symbol statistics"""
        # Find matching entry trade(s) using FIFO
        entry_trades = [t for t in self.symbol_trades[symbol] if t['side'] == 'BUY']
        
        if not entry_trades:
            logger.warning(f"{symbol}: No entry trades found for exit tracking")
            return
        
        # Use the most recent entry (should match the position being closed)
        entry_trade = entry_trades[-1]
        entry_price = entry_trade['price']
        
        # Calculate P&L
        pnl = (exit_price - entry_price) * exit_qty
        
        # Update symbol statistics
        self.symbol_stats[symbol]['total_pnl'] += pnl
        self.symbol_pnl[symbol] += pnl
        
        # Track P&L for later win/loss determination, but don't increment counters here
        # Win/loss will be determined when the complete trade is closed
        if pnl > 0:
            self.symbol_stats[symbol]['gross_profit'] += pnl
            self.symbol_stats[symbol]['max_profit'] = max(self.symbol_stats[symbol]['max_profit'], pnl)
        else:
            self.symbol_stats[symbol]['gross_loss'] += abs(pnl)
            self.symbol_stats[symbol]['max_loss'] = max(self.symbol_stats[symbol]['max_loss'], abs(pnl))
        
        # Record the exit trade
        exit_trade = {
            'symbol': symbol,
            'side': 'SELL',
            'quantity': exit_qty,
            'price': exit_price,
            'order_price': exit_price,
            'timestamp': self.current_date,
            'bar_index': self.current_index.get(symbol, 0),
            'pnl': pnl
        }
        
        self.symbol_trades[symbol].append(exit_trade)
        
        logger.debug(f"{symbol}: Exit trade tracked - P&L: Rs.{pnl:.2f} (Entry: Rs.{entry_price:.2f}, Exit: Rs.{exit_price:.2f})")
    
    def _complete_trade(self, symbol: str, total_pnl: float):
        """Mark a trade as complete and update win/loss counters"""
        if total_pnl > 0:
            self.symbol_stats[symbol]['winning_trades'] += 1
        else:
            self.symbol_stats[symbol]['losing_trades'] += 1
        
        logger.debug(f"{symbol}: Trade completed with total P&L: Rs.{total_pnl:.2f}")
    
    def _track_trade(self, symbol: str, order: dict, fill_price: float, filled_qty: int):
        """Track trade for symbol statistics - mainly for order fills (entries)"""
        trade = {
            'symbol': symbol,
            'side': order['side'],
            'quantity': filled_qty,
            'price': fill_price,
            'order_price': order['price'],
            'timestamp': self.current_date,
            'bar_index': self.current_index.get(symbol, 0)
        }
        
        self.symbol_trades[symbol].append(trade)
        
        # Only count entry trades here, exits are handled by _track_exit_trade
        if order['side'] == 'BUY':
            self.symbol_stats[symbol]['total_trades'] += 1
    
    def _generate_symbol_statistics(self) -> dict:
        """Generate comprehensive statistics for each symbol"""
        stats = {}
        
        # Include ALL symbols that had data loaded, even if not traded
        # First ensure all loaded symbols are in symbol_stats
        for symbol in self.data.keys():
            if symbol not in self.symbol_stats:
                # Add missing symbol with default stats
                self.symbol_stats[symbol] = {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'total_pnl': 0.0,
                    'gross_profit': 0.0,
                    'gross_loss': 0.0,
                    'max_profit': 0.0,
                    'max_loss': 0.0,
                    'bars_in_market': 0,
                    'data_bars': len(self.data[symbol])
                }
        
        # Now process all symbols
        for symbol in self.data.keys():  # Use data keys to ensure ALL symbols
            symbol_data = self.symbol_stats[symbol]
            
            # Calculate derived statistics
            total_trades = symbol_data['total_trades']
            winning_trades = symbol_data['winning_trades'] 
            losing_trades = symbol_data['losing_trades']
            
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            avg_profit = (symbol_data['gross_profit'] / winning_trades) if winning_trades > 0 else 0
            avg_loss = (symbol_data['gross_loss'] / losing_trades) if losing_trades > 0 else 0
            
            profit_factor = (symbol_data['gross_profit'] / symbol_data['gross_loss']) if symbol_data['gross_loss'] > 0 else float('inf') if symbol_data['gross_profit'] > 0 else 0
            
            # Market exposure
            market_exposure = (symbol_data['bars_in_market'] / symbol_data['data_bars'] * 100) if symbol_data['data_bars'] > 0 else 0
            
            # Include unrealized P&L for open positions
            unrealized_pnl = self._calculate_unrealized_pnl(symbol)
            total_pnl_with_unrealized = symbol_data['total_pnl'] + unrealized_pnl
            
            stats[symbol] = {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': win_rate,
                'total_pnl': symbol_data['total_pnl'],  # Realized P&L only
                'unrealized_pnl': unrealized_pnl,
                'total_pnl_with_unrealized': total_pnl_with_unrealized,
                'gross_profit': symbol_data['gross_profit'],
                'gross_loss': symbol_data['gross_loss'],
                'max_profit': symbol_data['max_profit'],
                'max_loss': symbol_data['max_loss'],
                'avg_profit': avg_profit,
                'avg_loss': avg_loss,
                'profit_factor': profit_factor,
                'market_exposure': market_exposure,
                'data_bars': symbol_data['data_bars'],
                'has_open_position': unrealized_pnl != 0
            }
        
        logger.info(f"Generated statistics for {len(stats)} symbols: {list(stats.keys())}")
        return stats
            
    def _calculate_unrealized_pnl(self, symbol: str) -> float:
        """Calculate unrealized P&L for open positions"""
        try:
            positions = self.state.load_positions()
            if symbol not in positions:
                return 0.0
            
            position = positions[symbol]
            if position.get('status') != 'OPEN':
                return 0.0
            
            entry_price = position.get('entry_price', 0)
            current_price = self.prices.get(symbol, entry_price)
            qty = position.get('qty_remaining', 0)
            
            if qty > 0 and entry_price > 0:
                unrealized_pnl = (current_price - entry_price) * qty
                return unrealized_pnl
            
            return 0.0
        except Exception as e:
            logger.debug(f"Error calculating unrealized P&L for {symbol}: {e}")
            return 0.0
