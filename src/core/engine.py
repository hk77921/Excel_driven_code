"""
Trading Engine - Core Trading Logic
===================================
The heart of the system. Contains all trading logic that is
independent of execution mode (backtest, paper, live).

Every trade decision goes through this engine.
All execution modes use the same core logic.
"""

import logging
from typing import Dict, Tuple, Optional, List
from datetime import datetime, timedelta

from scipy import signal

from .models import (
    Order, Position, Trade, DailyPnL, ScreenerSignal,
    TradeParameters, CapitalParameters, OrderSide, OrderStatus,
    PositionStatus
)
from .state_manager import StateManager
from .capital_manager import CapitalManager
from .position_manager import PositionManager
from .risk_manager import RiskManager
from .risk_governor import RiskGovernor
from .warmup_manager import WarmupManager
from src.core.fvg_detector import detect_fvg


logger = logging.getLogger(__name__)


class TradingEngine:
    """
    Core trading engine - same logic for all execution modes.
    
    Responsibilities:
    1. Process screener signals with market regime awareness
    2. Manage position lifecycle
    3. Handle exits (partial, full, SL, target)
    4. Track P&L and capital
    5. Enforce all risk limits including sector limits
    """
    
    def __init__(
        self,
        capital_params: CapitalParameters,
        trade_params: TradeParameters,
        state_manager: StateManager,
        timing_enabled: bool = True,
        symbols: Optional[List[str]] = None
    ):
        """
        Initialize trading engine.
        
        Args:
            capital_params: Capital management parameters
            trade_params: Trading parameters (ATR, SL, etc)
            state_manager: State persistence layer
            timing_enabled: Enable timing intelligence (default: True)
            symbols: List of symbols for warmup (optional)
        """
        self.capital_params = capital_params
        self.trade_params = trade_params
        self.state = state_manager
        self.capital_mgr = CapitalManager(capital_params)
        
        # Initialize risk management components
        self.risk_manager = RiskManager(capital_params, trade_params, state_manager)
        self.risk_governor = RiskGovernor(self.risk_manager, state_manager)
        
        # Initialize warmup manager if symbols provided
        if symbols:
            self.warmup_manager = WarmupManager(symbols)
        else:
            self.warmup_manager = None
        
        # Initialize adaptive strategies
        try:
            # Lazy import to avoid circular imports
            from src.strategies import AdaptiveStrategyManager
            self.adaptive_manager = AdaptiveStrategyManager()
            logger.info("Adaptive strategies initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize adaptive strategies: {e}")
            self.adaptive_manager = None
        
        # Market regime awareness
        self._current_market_trend: Optional[str] = None
        self._last_trend_update: Optional[datetime] = None
        
        # NEW: Timing intelligence
        self.timing_enabled = timing_enabled
        if timing_enabled:
            # Import here to avoid circular imports
            from ..timing.market_regime import MarketRegimeManager
            from ..timing.timing_filter import TimingFilter
            
            self.regime_manager = MarketRegimeManager()
            self.timing_filter = TimingFilter(self.regime_manager, state_manager)
            logger.info("Trading engine initialized with timing intelligence enabled")
        else:
            self.regime_manager = None
            self.timing_filter = None
            logger.info("Trading engine initialized with timing intelligence disabled")
        
        logger.info("Trading engine initialized with enhanced risk management")
    

  

    # ====== MARKET REGIME DETECTION ======
    
    def get_market_trend(self, force_update: bool = False) -> str:
        """
        Get current market trend with caching.
        
        Args:
            force_update: Force trend recalculation
            
        Returns:
            Market trend (BULLISH, BEARISH, SIDEWAYS, UNKNOWN)
        """
        # Update trend if needed (cache for 1 hour)
        now = datetime.now()
        needs_update = (
            force_update or
            self._current_market_trend is None or
            self._last_trend_update is None or
            (now - self._last_trend_update) > timedelta(hours=1)
        )
        
        if needs_update:
            try:
                # Local import to avoid circular dependency
                from ..screener.excel_screener import ExcelScreener
                screener = ExcelScreener()
                self._current_market_trend = screener.get_market_trend()
                self._last_trend_update = now
                
                logger.info(f"Market trend updated: {self._current_market_trend}")
            except Exception as e:
                logger.warning(f"Market trend detection failed: {e}")
                self._current_market_trend = "UNKNOWN"
        
        return self._current_market_trend or "UNKNOWN"
    
    def adjust_trade_limits_for_market(self, base_limit: int) -> int:
        """
        Adjust trade limits based on market regime.
        
        Args:
            base_limit: Base trade limit from rules
            
        Returns:
            Adjusted trade limit
        """
        trend = self.get_market_trend()
        
        if trend == "BEARISH":
            return max(1, int(base_limit * 0.5))  # 50% reduction
        elif trend == "SIDEWAYS":
            return max(2, int(base_limit * 0.7))  # 30% reduction  
        else:  # BULLISH or UNKNOWN
            return base_limit
    
    # ====== ENTRY LOGIC ======
    
    def process_signal(
        self,
        signal: ScreenerSignal,
        sector_map: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, Optional[Order], str]:
        """
        Process screener signal and create entry order with market regime awareness.
        
        Args:
            signal: Screener signal with symbol and parameters
            sector_map: Optional sector mapping from Excel
        
        Returns:
            (success, order_if_created, reason_if_failed)
        """
        try:
                symbol = signal.symbol
                
                logger.debug(f"{symbol}: Processing signal - Price: Rs.{signal.price:.2f}, Score: {signal.score}, ATR: {signal.atr:.2f}")
            
                # NEW: Apply timing intelligence filter
                if self.timing_enabled and self.timing_filter:
                    should_enter_timing, timing_reason = self.timing_filter.should_enter_now(signal)
                    if not should_enter_timing:
                        logger.debug(f"{symbol}: Timing filter rejected - {timing_reason}")
                        return False, None, f"{symbol}: {timing_reason}"
                
                # Local import to avoid circular dependency
                # from ..screener.excel_screener import ExcelScreener
                # screener = ExcelScreener()
                # should_enter, reason = screener.should_enter_trade(signal)
                # if not should_enter:
                #     logger.info(f"{symbol}: Entry rejected - {reason}")
                #     return False, None, f"{symbol}: {reason}"



                # Check 1: Not already in position - CRITICAL duplicate prevention
                positions = self.state.load_positions()
                if symbol in positions:
                    qty_remaining = positions[symbol].get('qty_remaining', 0)
                    if qty_remaining > 0:
                        logger.warning(
                            f"DUPLICATE PREVENTED: {symbol} already in position | "
                            f"qty_remaining: {qty_remaining} | "
                            f"entry_price: Rs.{positions[symbol].get('entry_price', 0):.2f}"
                        )
                        return False, None, f"{symbol}: Already in position - {qty_remaining} shares remaining"
                
                # Check 1B: Also check pending orders for the same symbol
                pending_orders = self.state.load_orders()
                for order_id, order_data in pending_orders.items():
                    if order_data.get('symbol') == symbol and order_data.get('status') == 'PENDING':
                        logger.warning(
                            f"DUPLICATE PREVENTED: {symbol} has pending order | "
                            f"order_id: {order_id} | "
                            f"qty: {order_data.get('req_qty', 0)}"
                        )
                        return False, None, f"{symbol}: Pending order exists - {order_id}"
                
                # Check 2: Get adaptive strategy decision for dynamic parameters
                if self.adaptive_manager:
                    try:
                        decision = self.adaptive_manager.evaluate_trade_entry(signal)
                        if not decision.should_enter:
                            logger.info(f"{symbol}: Adaptive strategy rejected - {decision.combined_reason}")
                            return False, None, f"{symbol}: {decision.combined_reason}"
                        
                        # Use adaptive parameters from final_parameters
                        params = decision.final_parameters
                        sl_mult = params.get('sl_multiplier', self.trade_params.sl_atr_mult)
                        target_mult = params.get('target_multiplier', self.trade_params.target_atr_mult)
                        position_size_mult = params.get('position_size_multiplier', 1.0)
                        
                        logger.info(f"{symbol}: Adaptive strategy approved - {decision.primary_strategy} | "
                                f"SL: {sl_mult:.2f}x, Target: {target_mult:.2f}x, Size: {position_size_mult:.2f}x")
                    except Exception as e:
                        logger.warning(f"{symbol}: Adaptive strategy error: {e}, using defaults")
                        sl_mult = self.trade_params.sl_atr_mult
                        target_mult = self.trade_params.target_atr_mult
                        position_size_mult = 1.0
                else:
                    # Fallback to original hardcoded parameters
                    logger.info(f"{symbol}: Adaptive strategy not enabled, using defaults")
                    sl_mult = self.trade_params.sl_atr_mult
                    target_mult = self.trade_params.target_atr_mult
                    position_size_mult = 1.0
                
                # Calculate position size with adaptive parameters
                entry_price = signal.price
                sl, target = PositionManager.calculate_sl_and_target(
                    entry_price=entry_price,
                    atr=signal.atr,
                    sl_mult=sl_mult,
                    target_mult=target_mult,
                    side=OrderSide.BUY
                )
                
                base_qty = self.capital_mgr.calculate_position_size(entry_price, sl)
                qty = max(1, int(base_qty * position_size_mult))  # Apply adaptive sizing
                logger.debug(f"{symbol}: Calculated qty: {qty}, SL: Rs.{sl:.2f}, Target: Rs.{target:.2f}")
                
                if qty <= 0:
                    logger.debug(f"{symbol}: Calculated quantity is 0 or negative")
                    return False, None, f"{symbol}: Calculated quantity is 0"
                
                # NEW: Create proposed order for risk governor evaluation
                import uuid
                proposed_order = Order(
                    order_id=str(uuid.uuid4())[:8],
                    symbol=symbol,
                    side=OrderSide.BUY,
                    req_qty=qty,
                    price=entry_price,
                    created_at=datetime.now()
                )
                
                
                
                # Reserve capital for proposed order
                order_value = proposed_order.req_qty * proposed_order.price
                logger.info(f"{symbol}: Reserving capital for proposed order - Value: Rs.{order_value:,.2f}")
                
               # self.capital_mgr.reserve(order_value)
                self.capital_mgr.reserve(symbol, order_value)
                logger.info(f"{symbol}: Reserved capital for proposed order - Value: Rs.{order_value:,.2f}")


                def convert_positions_to_objects(positions: List[Dict]) -> List[Position]:
                    return [Position(**pos) for pos in positions]



                # NEW: Risk Governor - Final approval checkpoint
                current_positions = [pos for pos in positions.values()]
                current_positions = convert_positions_to_objects(current_positions)
               
                governor_result = self.risk_governor.approve_trade(signal, proposed_order, current_positions)
                
                if governor_result.decision.value == "REJECT":
                    #self.capital_mgr.release_reservation(order_value)
                    self.capital_mgr.release_reservation(symbol, order_value)
                    logger.warning(f"{symbol}: Risk Governor REJECTED - {'; '.join(governor_result.reasons)}| Releasing capital reservation {order_value: Rs.{order_value:,.2f}}")
                    return False, None, f"{symbol}: Risk rejected - {'; '.join(governor_result.reasons)}"
                
                elif governor_result.decision.value == "DEFER":
                    logger.info(f"{symbol}: Risk Governor DEFERRED - {'; '.join(governor_result.reasons)}")
                    return False, None, f"{symbol}: Risk deferred - {'; '.join(governor_result.reasons)}"
                
                elif governor_result.decision.value == "MODIFY":
                    if governor_result.modified_order:
                        proposed_order = governor_result.modified_order
                        qty = proposed_order.req_qty
                        entry_price = proposed_order.price
                        
                        self.capital_mgr.release_reservation(symbol, order_value)
                        self.capital_mgr.reserve(symbol, qty * entry_price)

                        logger.info(f"{symbol}: Risk Governor requested modification - New qty: {qty}, New price: Rs.{entry_price:.2f}, Reasons: {'; '.join(governor_result.reasons)}")
                        logger.info(f"{symbol}: Risk Governor MODIFIED order - New qty: {qty}, Reasons: {'; '.join(governor_result.reasons)}")
                    else:
                        logger.warning(f"{symbol}: Risk Governor requested modification but no modified order provided")
                        return False, None, f"{symbol}: Risk modification failed"
                
                else:  # APPROVE
                    logger.info(f"{symbol}: Risk Governor APPROVED")
                
                # Check 3: Can we open this position? (includes sector limits) - Legacy check for compatibility
                # pending_orders already loaded above for duplicate check
                # can_open, reason = self.capital_mgr.can_open_position(
                #     symbol=symbol,
                #     entry_price=entry_price,
                #     quantity=qty,
                #     positions=positions,
                #     pending_orders=pending_orders,
                #     sector_map=sector_map
                # )
                
                # if not can_open:
                #     logger.debug(f"{symbol}: Capital management check failed: {reason}")
                #     return False, None, f"{symbol}: {reason}"
                
            
                
                # Create order
                order = Order(
                    order_id=f"ORD_{symbol}_{int(datetime.now().timestamp() * 1000)}",
                    symbol=symbol,
                    side=OrderSide.BUY,
                    req_qty=qty,
                    price=entry_price,
                    created_at=datetime.now(),
                    status=OrderStatus.PENDING,
                    atr=signal.atr,
                    sector=signal.sector
                )
                
                # Save immediately (CRITICAL - prevents duplicates)
                self.state.add_order(order.order_id, order.to_dict())
                
                logger.info(
                    f"{symbol}: Order created | "
                    f"BUY {qty} @ Rs.{entry_price:.2f} | "
                    f"SL: Rs.{sl:.2f}, Target: Rs.{target:.2f}"
                )
                
                return True, order, ""
        except Exception as e:
            self.capital_mgr.release_reservation(symbol, order_value)
            logger.error(f"Error processing signal for {signal.symbol}: {e} releasing capital reservation Rs.{order_value:,.2f}")
            
            return False, None, f"{signal.symbol}: Processing error - {e}"
    
    def on_order_filled(
        self,
        order_id: str,
        filled_qty: int,
        filled_price: float
    ) -> Tuple[bool, Optional[Dict], str]:
        """
        Handle order fill from broker.
        
        Args:
            order_id: Order ID that was filled
            filled_qty: Quantity filled
            filled_price: Price at which filled
        
        Returns:
            (success, position_dict_if_opened, reason_if_failed)
        """
        orders = self.state.load_orders()
        if order_id not in orders:
            return False, None, f"Order {order_id} not found"
        
        order = orders[order_id]
        symbol = order['symbol']
        
        # Calculate position entry (weighted average if partial fill)
        old_qty = order.get('filled_qty', 0)
        new_total_qty = old_qty + filled_qty
        
        if new_total_qty > order['req_qty']:
            return False, None, f"Over-filled: {new_total_qty} > {order['req_qty']}"
        
        # Update order
        order['filled_qty'] = new_total_qty
        order['filled_price'] = (
            (order['filled_price'] * old_qty + filled_price * filled_qty) / new_total_qty
        ) if old_qty > 0 else filled_price
        
        if order['filled_qty'] >= order['req_qty']:
            order['status'] = OrderStatus.FILLED.value
        else:
            order['status'] = OrderStatus.PARTIAL.value
        

        self.capital_mgr.commit_position(order['symbol'], order['filled_price'] * order['filled_qty'] )

        order['updated_at'] = datetime.now().isoformat()
        self.state.update_order_status(order_id, order['status'], order['filled_qty'])
        
        # If fully filled, create position
        if order['filled_qty'] >= order['req_qty']:
            entry_price = order['filled_price']
            qty = order['filled_qty']
            atr = order.get('atr', 0)
            
            sl, target = PositionManager.calculate_sl_and_target(
                entry_price=entry_price,
                atr=atr,
                sl_mult=self.trade_params.sl_atr_mult,
                target_mult=self.trade_params.target_atr_mult,
                side=OrderSide.BUY
            )
            
            position = {
                'symbol': symbol,
                'side': OrderSide.BUY.value,
                'entry_price': entry_price,
                'quantity': qty,
                'qty_remaining': qty,
                'atr': atr,
                'stop_loss': sl,
                'target': target,
                'entry_time': datetime.now().isoformat(),
                'partial_exit_done': False,
                'status': PositionStatus.OPEN.value
            }
            
            self.state.add_position(symbol, position)
            self.state.remove_order(order_id)
            
            logger.info(f"{symbol}: Position opened | Entry: Rs.{entry_price:.2f}, Qty: {qty}")
            return True, position, ""
        
        return False, None, f"{symbol}: Partial fill, waiting for remaining"
    
    # ====== EXIT LOGIC ======
    
    def check_and_handle_exits(
        self,
        current_prices: Dict[str, float]
    ) -> List[Tuple[str, int, float, str]]:
        """
        Check all positions for exit conditions.
        
        Args:
            current_prices: Current prices for all symbols
        
        Returns:
            List of (symbol, qty_to_exit, exit_price, reason)
        """
        exits = []
        positions = self.state.load_positions()
        
        for symbol, position in positions.items():
            if position.get('qty_remaining', 0) <= 0:
                continue
            
            if symbol not in current_prices:
                continue
            
            current_price = current_prices[symbol]

            atr = position["atr"]
            entry = position["entry_price"]
            bars = position.get("bars_since_entry", 0)
            position["bars_since_entry"] = bars + 1

             # 🔴 EARLY KILL (most important)
            if bars >= 3 and current_price < entry + 0.3 * atr:
                exits.append((symbol, position["qty_remaining"], current_price, "EARLY_KILL"))
                continue


             # 🟡 PARTIAL EXIT (earned)
            if not position["partial_done"] and current_price >= entry + atr:
                exits.append((symbol, int(position["qty_remaining"] * 0.5), current_price, "PARTIAL"))
                position["partial_done"] = True
                position["stop_loss"] = entry  # Move SL to BE
                self.state.add_position(symbol, position)
            
            # 🟢 STRUCTURE TRAIL
            if position.get("last_higher_low"):
                trail_sl = position["last_higher_low"] - 0.2 * atr
                if current_price < trail_sl:
                    exits.append((symbol, position["qty_remaining"], current_price, "TRAIL_EXIT"))

           


            # Check stop loss
            if PositionManager.check_stop_loss_hit(position, current_price):
                exits.append((
                    symbol,
                    position['qty_remaining'],
                    current_price,
                    "SL_HIT"
                ))
                logger.warning(
                    f"{symbol}: Stop loss hit | "
                    f"SL: Rs.{position['stop_loss']:.2f}, Price: Rs.{current_price:.2f}"
                )
                continue
            
            # Check target
            if PositionManager.check_target_hit(position, current_price):
                exits.append((
                    symbol,
                    position['qty_remaining'],
                    current_price,
                    "TARGET_HIT"
                ))
                logger.info(
                    f"{symbol}: Target hit | "
                    f"Target: Rs.{position['target']:.2f}, Price: Rs.{current_price:.2f}"
                )
                continue
            
            # Check multi-level exits
            position, exit_qty = PositionManager.check_multi_level_exit(
                position,
                current_price
                
            )
            if exit_qty > 0:
                exits.append((symbol, exit_qty, current_price, "MULTI_LEVEL_EXIT"))
                self.state.add_position(symbol, position)
                continue    


            # Check partial exit
            position, exit_qty = PositionManager.check_partial_exit(
                position,
                current_price,
                self.trade_params.partial_exit_ratio
            )
            
            if exit_qty > 0:
                exits.append((symbol, exit_qty, current_price, "PARTIAL_EXIT"))
                self.state.add_position(symbol, position)
            
            # Check trailing SL (only after partial exit)
            if position.get('partial_exit_done'):
                position, updated = PositionManager.update_trailing_sl(
                    position,
                    current_price,
                    self.trade_params.trailing_sl_atr_mult
                )
                if updated:
                    self.state.add_position(symbol, position)
        
        return exits
    
    def on_exit_executed(
        self,
        symbol: str,
        exit_qty: int,
        exit_price: float,
        reason: str
    ) -> Tuple[bool, str]:
        """
        Handle exit execution.
        
        Args:
            symbol: Symbol exited
            exit_qty: Quantity exited
            exit_price: Exit price
            reason: Reason for exit
        
        Returns:
            (success, message)
        """
        positions = self.state.load_positions()
        if symbol not in positions:
            return False, f"{symbol}: No position found"
        
        position = positions[symbol]
        remaining = position['qty_remaining'] - exit_qty
        
        if remaining < 0:
            return False, f"{symbol}: Trying to exit more than remaining"
        
        # Calculate realized P&L
        entry = position['entry_price']
        realized_pnl = (exit_price - entry) * exit_qty
        realized_pnl_pct = (realized_pnl / (entry * exit_qty)) * 100
        
        # Update position
        position['qty_remaining'] = remaining
        if remaining > 0:
            position['status'] = PositionStatus.OPEN.value
        else:
            position['status'] = PositionStatus.CLOSED.value
        
        self.state.add_position(symbol, position)
        
        logger.info(
            f"{symbol}: Exited {exit_qty} shares @ Rs.{exit_price:.2f} | "
            f"Reason: {reason} | "
            f"P&L: Rs.{realized_pnl:.2f} ({realized_pnl_pct:.2f}%)"
        )
        
        # If fully closed, remove position
        if remaining <= 0:
            self.state.remove_position(symbol)
            self.capital_mgr.release_position(symbol, entry * position['quantity'])
        
        return True, f"Exited {exit_qty} shares"
    
    # ====== NEW: WARMUP & ARMING METHODS ======
    
    def execute_warmup(self, force_refresh: bool = False):
        """Execute system warmup if warmup manager is available"""
        if self.warmup_manager:
            logger.info("Executing system warmup...")
            result = self.warmup_manager.execute_warmup(force_refresh)
            
            if result.success:
                logger.info(f"Warmup completed successfully in {result.total_duration:.2f}s")
                # Update market regime with warmed data
                if self.regime_manager:
                    self.risk_manager.update_market_regime("WARMED", 0.02)  # Default regime
            else:
                logger.error(f"Warmup failed with {len(result.failed_tasks)} task failures")
                raise Exception(f"System warmup failed: {', '.join([t.error_message for t in result.failed_tasks])}")
            
            return result
        else:
            logger.warning("No warmup manager available - skipping warmup")
            return None
    
    def update_market_context(self):
        """Update market context and regime detection"""
        try:
            if self.regime_manager:
                # Get current market regime
                regime_info = self.regime_manager.get_market_regime()
                current_regime = regime_info.get('regime', 'UNKNOWN')
                confidence = regime_info.get('confidence', 0.5)
                
                logger.info(f"Market regime updated: {current_regime} (confidence: {confidence:.2f})")
                
                # Update risk manager with current regime
                self.risk_manager.update_market_regime(current_regime, confidence * 0.05)  # Convert confidence to volatility proxy
                
                return regime_info
            else:
                logger.warning("No regime manager available")
                return {'regime': 'UNKNOWN', 'confidence': 0.5}
        except Exception as e:
            logger.error(f"Market context update failed: {e}")
            return {'regime': 'ERROR', 'confidence': 0.0}
    
    def get_risk_status(self) -> Dict:
        """Get comprehensive risk status from all risk components"""
        try:
            status = {
                'risk_manager': self.risk_manager.get_risk_status(),
                'risk_governor': self.risk_governor.get_governor_status(),
                'warmup_ready': self.warmup_manager.get_warmup_status() if self.warmup_manager else None,
                'timing_enabled': self.timing_enabled
            }
            
            if self.timing_filter:
                status['timing_info'] = self.timing_filter.get_timing_info()
                
            return status
        except Exception as e:
            logger.error(f"Failed to get risk status: {e}")
            return {'error': str(e)}
    
    def is_trading_allowed(self) -> Tuple[bool, str]:
        """Check if trading is currently allowed based on all conditions"""
        try:
            # Check market hours if timing is enabled
            if self.timing_enabled and self.timing_filter:
                timing_info = self.timing_filter.get_timing_info()
                if not timing_info.get('market_open', True):
                    return False, "Market is closed"
            
            # Check risk manager status
            risk_status = self.risk_manager.get_risk_status()
            
            # Check daily loss limit
            daily_pnl = risk_status.get('daily_pnl', 0)
            daily_limit = risk_status.get('daily_loss_limit', 0)
            if daily_pnl < -daily_limit:
                return False, f"Daily loss limit exceeded: ₹{daily_pnl:,.0f}"
            
            # Check available capital
            available_capital = risk_status.get('available_capital', 0)
            if available_capital <= 0:
                return False, "No capital available for trading"
            
            # Check position limits
            active_positions = risk_status.get('active_positions', 0)
            max_positions = risk_status.get('max_positions', 10)
            if active_positions >= max_positions:
                return False, f"Maximum positions reached: {active_positions}/{max_positions}"
            
            # Check if risk override is active
            if risk_status.get('risk_override_active', False):
                return True, "Trading allowed (risk override active)"
            
            return True, "All trading conditions satisfied"
            
        except Exception as e:
            logger.error(f"Trading allowed check failed: {e}")
            return False, f"Trading check error: {e}"
    
    # ====== P&L TRACKING ======
    
    def calculate_daily_pnl(self, date: str) -> DailyPnL:
        """
        Calculate daily P&L.
        
        Args:
            date: Date string (YYYY-MM-DD)
        
        Returns:
            DailyPnL object
        """
        positions = self.state.load_positions()
        
        # Unrealized P&L from open positions (for display only)
        unrealized = 0.0
        for symbol, pos in positions.items():
            # Would need current price here
            pass
        
        daily_pnl = self.state.load_daily_pnl(date)
        if daily_pnl:
            return DailyPnL(
                date=date,
                starting_capital=daily_pnl.get('starting_capital', self.capital_params.total_capital),
                realized_pnl=daily_pnl.get('realized_pnl', 0.0),
                unrealized_pnl=unrealized,
                trades_executed=daily_pnl.get('trades_executed', 0),
                trades_closed=daily_pnl.get('trades_closed', 0)
            )
        
        return DailyPnL(
            date=date,
            starting_capital=self.capital_params.total_capital
        )
    
    def update_daily_pnl(
        self,
        date: str,
        realized_pnl: float,
        trades_executed: int,
        trades_closed: int
    ):
        """Update daily P&L"""
        pnl_data = {
            'date': date,
            'starting_capital': self.capital_params.total_capital,
            'realized_pnl': realized_pnl,
            'unrealized_pnl': 0.0,
            'trades_executed': trades_executed,
            'trades_closed': trades_closed
        }
        self.state.save_daily_pnl(date, pnl_data)
