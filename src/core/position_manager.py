"""
Position Manager - Core Position Logic
======================================
Handles all position lifecycle:
- Entry price calculation
- Stop loss and target calculation
- Partial exits and trailing stops
- P&L tracking

Used by all execution modes (backtest, paper, live).
"""

import logging
from typing import Dict, Tuple, Optional
from .models import OrderSide


logger = logging.getLogger(__name__)


class PositionManager:
    """Core position management logic"""
    
    @staticmethod
    def round_to_tick(price: float, tick_size: float = 0.05) -> float:
        """
        Round price to the nearest tick size.
        Zerodha requires prices to be multiples of 0.05 for NSE stocks.
        
        Args:
            price: Price to round
            tick_size: Tick size (default 0.05 for NSE)
        
        Returns:
            Rounded price
        """
        if price <= 0:
            return price
        
        # Round to nearest tick
        rounded = round(price / tick_size) * tick_size
        
        # Ensure we don't lose precision due to float arithmetic
        return round(rounded, 2)
    
    @staticmethod
    def calculate_sl_and_target(
        entry_price: float,
        atr: float,
        sl_mult: float = 0.8,
        target_mult: float = 2.5,
        side: OrderSide = OrderSide.BUY
    ) -> Tuple[float, float]:
        """
        Calculate stop loss and target based on ATR.
        Prices are rounded to nearest 0.05 (Zerodha tick size).
        
        Args:
            entry_price: Entry price
            atr: Average True Range
            sl_mult: Stop loss multiplier (1.5x ATR)
            target_mult: Target multiplier (2.0x ATR)
            side: BUY or SELL
        
        Returns:
            (stop_loss, target) - both rounded to tick size
        """
        if side == OrderSide.BUY:
            sl = entry_price - (atr * sl_mult)
            target = entry_price + (atr * target_mult)
        else:  # SELL
            sl = entry_price + (atr * sl_mult)
            target = entry_price - (atr * target_mult)
        
        # Round to broker's tick size (0.05 for NSE stocks)
        sl = PositionManager.round_to_tick(sl)
        target = PositionManager.round_to_tick(target)
        
        return sl, target
    
    @staticmethod
    def check_partial_exit(
        position: dict,
        current_price: float,
        partial_exit_ratio: float = 0.8
    ) -> Tuple[dict, int]:
        """
        Check if partial exit should be triggered.
        
        Partial exit at +0.8R (0.8x the risk)
        Exits 50% of remaining quantity
        
        Args:
            position: Position dictionary
            current_price: Current last traded price
            partial_exit_ratio: Exit at this R-value (0.8 = 0.8R)
        
        Returns:
            (updated_position, exit_qty)
        """
        # Skip if already done
        if position.get('partial_exit_done', False):
            return position, 0
        
        entry = position['entry_price']
        sl = position['stop_loss']
        side = position['side']
        symbol = position.get('symbol', 'UNKNOWN')
        
        # Calculate R-value (risk per share)
        r_value = abs(entry - sl)
        
        if r_value <= 0:
            logger.warning(f"{symbol}: Invalid R-value, skipping partial exit")
            return position, 0
        
        # For BUY: target is entry + (partial_exit_ratio * R)
        if side == OrderSide.BUY:
            target_price = entry + (partial_exit_ratio * r_value)
            
            if current_price >= target_price:
                # Exit 50% of remaining quantity
                exit_qty = max(1, int(position['qty_remaining'] * 0.5))
                
                # Must leave at least 1 share remaining
                if exit_qty >= position['qty_remaining']:
                    exit_qty = position['qty_remaining'] - 1
                
                if exit_qty > 0:
                    position['partial_exit_done'] = True
                    logger.info(
                        f"{symbol}: Partial exit triggered | "
                        f"Price: Rs.{current_price:.2f}, Target: Rs.{target_price:.2f} | "
                        f"Exiting {exit_qty}/{position['qty_remaining']} shares"
                    )
                    return position, exit_qty
        
        # TODO: Add SELL side logic when needed
        
        return position, 0
    
    @staticmethod
    def check_multi_level_exit(
        position: dict,
        current_price: float,
    ) -> Tuple[dict, int]:
        """
        Multi-level partial exit strategy:
        - Level 1: Exit 33% at +0.5R (lock profit early)
        - Level 2: Exit 33% at +1.0R (lock medium profit)
        - Level 3: Trail stop for remaining 34% (go for home run)
        
        Returns:
            (updated_position, exit_qty)
        """
        symbol = position.get('symbol', 'UNKNOWN')
        entry = position['entry_price']
        sl = position['stop_loss']
        side = position['side']
        qty_remaining = position['qty_remaining']
        
        # Calculate R-value
        r_value = abs(entry - sl)
        if r_value <= 0:
            return position, 0
        
        exit_qty = 0
        exit_reason = ""
        
        # LEVEL 1: +0.5R - Early profit lock (33%)
        if not position.get('level1_exit_done', False):
            if side == OrderSide.BUY:
                target = entry + (0.5 * r_value)
                if current_price >= target:
                    exit_qty = max(1, int(qty_remaining * 0.33))
                    position['level1_exit_done'] = True
                    exit_reason = "LEVEL1_+0.5R"
                    logger.info(
                        f"{symbol}: Level 1 exit | "
                        f"Price: Rs.{current_price:.2f}, Target: Rs.{target:.2f} | "
                        f"Exiting {exit_qty} shares (33%)"
                    )
                    return position, exit_qty
        
        # LEVEL 2: +1.0R - Medium profit lock (33%)
        if not position.get('level2_exit_done', False):
            if side == OrderSide.BUY:
                target = entry + (1.0 * r_value)
                if current_price >= target:
                    exit_qty = max(1, int(qty_remaining * 0.5))  # 50% of remaining
                    position['level2_exit_done'] = True
                    exit_reason = "LEVEL2_+1.0R"
                    logger.info(
                        f"{symbol}: Level 2 exit | "
                        f"Price: Rs.{current_price:.2f}, Target: Rs.{target:.2f} | "
                        f"Exiting {exit_qty} shares (50% of remaining)"
                    )
                    return position, exit_qty
        
        # LEVEL 3: Trail stop after level 2 (remaining qty)
        if position.get('level2_exit_done', False):
            # Use trailing stop logic here
            # Trail at: price - (0.8 * ATR)
            atr = position.get('atr', 0)
            if atr > 0:
                trailing_sl = current_price - (0.8 * atr)
                if trailing_sl > position['stop_loss']:
                    position['stop_loss'] = trailing_sl
                    # Don't exit yet, just update SL
                    return position, 0
        
        return position, 0


    @staticmethod
    def update_trailing_sl(
        position: dict,
        current_price: float,
        trailing_sl_mult: float = 1.5
    ) -> Tuple[dict, bool]:
        """
        Update trailing stop loss.
        
        Only activates after partial exit.
        SL only moves forward (never backward).
        
        Args:
            position: Position dictionary
            current_price: Current price
            trailing_sl_mult: Trailing SL multiplier
        
        Returns:
            (updated_position, sl_updated)
        """
        # Only trail after partial exit
        if not position.get('partial_exit_done', False):
            return position, False
        
        atr = position.get('atr', 0)
        side = position['side']
        symbol = position.get('symbol', 'UNKNOWN')
        
        if atr <= 0:
            logger.warning(f"{symbol}: Invalid ATR, cannot trail SL")
            return position, False
        
        if side == OrderSide.BUY:
            # Trail at current_price - (trailing_sl_mult * ATR)
            new_sl = current_price - (trailing_sl_mult * atr)
            
            # Only move up (more protective)
            if new_sl > position['stop_loss']:
                old_sl = position['stop_loss']
                position['stop_loss'] = new_sl
                position['trailing_sl'] = new_sl
                
                logger.info(
                    f"{symbol}: Trailing SL updated | "
                    f"Rs.{old_sl:.2f} -> Rs.{new_sl:.2f}"
                )
                return position, True
        
        # TODO: Add SELL side logic
        
        return position, False
    
    @staticmethod
    def calculate_unrealized_pnl(position: dict, current_price: float) -> float:
        """
        Calculate unrealized P&L.
        
        Args:
            position: Position dictionary
            current_price: Current price
        
        Returns:
            Unrealized P&L amount
        """
        entry = position['entry_price']
        qty = position['qty_remaining']
        side = position['side']
        
        if side == OrderSide.BUY:
            pnl = (current_price - entry) * qty
        else:  # SELL
            pnl = (entry - current_price) * qty
        
        return pnl
    
    @staticmethod
    def calculate_unrealized_pnl_pct(position: dict, current_price: float) -> float:
        """
        Calculate unrealized P&L percentage.
        
        Args:
            position: Position dictionary
            current_price: Current price
        
        Returns:
            Unrealized P&L percentage
        """
        entry = position['entry_price']
        qty = position['qty_remaining']
        
        if entry <= 0 or qty <= 0:
            return 0.0
        
        capital = entry * qty
        pnl = PositionManager.calculate_unrealized_pnl(position, current_price)
        
        return (pnl / capital) * 100
    
    @staticmethod
    def check_stop_loss_hit(position: dict, current_price: float) -> bool:
        """
        Check if stop loss is hit.
        
        Args:
            position: Position dictionary
            current_price: Current price
        
        Returns:
            True if SL hit
        """
        sl = position['stop_loss']
        side = position['side']
        
        if side == OrderSide.BUY:
            return current_price <= sl
        else:  # SELL
            return current_price >= sl
    
    @staticmethod
    def check_target_hit(position: dict, current_price: float) -> bool:
        """
        Check if target is hit.
        
        Args:
            position: Position dictionary
            current_price: Current price
        
        Returns:
            True if target hit
        """
        target = position.get('target', 0)
        side = position['side']
        
        if target <= 0:
            return False
        
        if side == OrderSide.BUY:
            return current_price >= target
        else:  # SELL
            return current_price <= target
    

    #Testing purpose
    @staticmethod
    def check_emergency_exit(
        position: dict, 
        current_price: float, 
        emergency_conditions: Optional[Dict] = None
    ) -> Tuple[dict, bool]:
        """
        Check if emergency exit conditions are met.
        
        Args:
            position: Position dictionary
            current_price: Current price
            emergency_conditions: Custom emergency conditions
            
        Returns:
            (updated_position, should_exit)
        """
        # Check if already marked for emergency exit
        if position.get('emergency_exit', False):
            return position, True
        
        # Default emergency conditions
        if not emergency_conditions:
            emergency_conditions = {
                'max_loss_pct': -10.0,  # Emergency exit at -10%
                'max_adverse_days': 5,   # Exit if losing for 5+ days
                'volume_spike_factor': 5.0  # Exit on unusual volume
            }
        
        # Calculate current loss percentage
        pnl_pct = PositionManager.calculate_unrealized_pnl_pct(position, current_price)
        
        # Emergency exit on excessive loss
        if pnl_pct <= emergency_conditions.get('max_loss_pct', -10.0):
            position['emergency_exit'] = True
            position['emergency_reason'] = f"Loss limit breached: {pnl_pct:.1f}%"
            logger.warning(
                f"{position.get('symbol', 'UNKNOWN')}: Emergency exit triggered - "
                f"Loss: {pnl_pct:.1f}%"
            )
            return position, True
        
        return position, False
    
    @staticmethod
    def update_relative_strength(
        position: dict,
        stock_return: float,
        index_return: float
    ) -> dict:
        """
        Update position's relative strength tracking.
        
        Args:
            position: Position dictionary
            stock_return: Stock's daily return
            index_return: Index's daily return
            
        Returns:
            Updated position with relative strength data
        """
        # Initialize relative strength tracking if not present
        if 'relative_strength' not in position:
            position['relative_strength'] = {
                'daily_rs': [],
                'avg_rs': 0.0,
                'rs_trend': 'NEUTRAL'
            }
        
        # Calculate daily relative strength
        daily_rs = stock_return - index_return
        position['relative_strength']['daily_rs'].append(daily_rs)
        
        # Keep only last 20 days
        if len(position['relative_strength']['daily_rs']) > 20:
            position['relative_strength']['daily_rs'] = position['relative_strength']['daily_rs'][-20:]
        
        # Calculate average relative strength
        rs_data = position['relative_strength']['daily_rs']
        if len(rs_data) >= 5:
            avg_rs = sum(rs_data[-5:]) / 5  # 5-day average
            position['relative_strength']['avg_rs'] = avg_rs
            
            # Determine trend
            if avg_rs > 0.001:  # Outperforming by >0.1%
                position['relative_strength']['rs_trend'] = 'OUTPERFORMING'
            elif avg_rs < -0.001:  # Underperforming by >0.1%
                position['relative_strength']['rs_trend'] = 'UNDERPERFORMING'
            else:
                position['relative_strength']['rs_trend'] = 'NEUTRAL'
        
        return position
    

    #Testing purpose
    @staticmethod
    def check_relative_strength_exit(
        position: dict,
        min_rs_days: int = 10,
        rs_threshold: float = -0.005
    ) -> Tuple[dict, bool]:
        """
        Check if position should exit due to poor relative strength.
        
        Args:
            position: Position dictionary
            min_rs_days: Minimum days of data needed
            rs_threshold: RS threshold for exit (-0.5% = underperforming by 0.5%)
            
        Returns:
            (updated_position, should_exit)
        """
        rs_data = position.get('relative_strength', {})
        
        if len(rs_data.get('daily_rs', [])) < min_rs_days:
            return position, False
        
        avg_rs = rs_data.get('avg_rs', 0.0)
        
        # Exit if consistently underperforming
        if avg_rs < rs_threshold and rs_data.get('rs_trend') == 'UNDERPERFORMING':
            position['rs_exit_triggered'] = True
            position['rs_exit_reason'] = f"Poor relative strength: {avg_rs:.3f}"
            
            logger.info(
                f"{position.get('symbol', 'UNKNOWN')}: Relative strength exit triggered - "
                f"Avg RS: {avg_rs:.3f}"
            )
            return position, True
        
        return position, False
    
    @staticmethod 
    def get_position_summary(position: dict, current_price: float) -> Dict:
        """
        Get comprehensive position summary.
        
        Args:
            position: Position dictionary
            current_price: Current price
            
        Returns:
            Detailed position summary
        """
        symbol = position.get('symbol', 'UNKNOWN')
        entry = position['entry_price']
        qty = position['qty_remaining']
        side = position['side']
        
        # P&L calculations
        unrealized_pnl = PositionManager.calculate_unrealized_pnl(position, current_price)
        unrealized_pnl_pct = PositionManager.calculate_unrealized_pnl_pct(position, current_price)
        
        # Risk metrics
        sl = position['stop_loss']
        risk_per_share = abs(entry - sl)
        r_multiple = unrealized_pnl / (risk_per_share * qty) if risk_per_share > 0 else 0
        
        # Position flags
        partial_done = position.get('partial_exit_done', False)
        trailing_active = position.get('trailing_sl', 0) > sl
        emergency_exit = position.get('emergency_exit', False)
        
        # Relative strength
        rs_data = position.get('relative_strength', {})
        rs_trend = rs_data.get('rs_trend', 'UNKNOWN')
        avg_rs = rs_data.get('avg_rs', 0.0)
        
        summary = {
            'symbol': symbol,
            'side': side,
            'entry_price': entry,
            'current_price': current_price,
            'quantity': qty,
            'exposure': entry * qty,
            'stop_loss': sl,
            'target': position.get('target', 0),
            'unrealized_pnl': unrealized_pnl,
            'unrealized_pnl_pct': unrealized_pnl_pct,
            'r_multiple': r_multiple,
            'partial_exit_done': partial_done,
            'trailing_active': trailing_active,
            'emergency_exit': emergency_exit,
            'relative_strength_trend': rs_trend,
            'avg_relative_strength': avg_rs,
            'sector': position.get('sector', 'UNKNOWN'),
            'days_held': position.get('days_held', 0),
            'entry_date': position.get('entry_date', ''),
        }
        
        return summary
