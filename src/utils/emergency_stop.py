"""
Emergency Stop - Immediate Position Exit
======================================
Emergency mechanism to mark all open positions for immediate exit.

USE WHEN:
- System malfunction detected
- Daily loss limit breached  
- Manual intervention required
- Risk management override needed

Usage:
    from src.utils.emergency_stop import EmergencyStop
    emergency = EmergencyStop()
    emergency.execute_emergency_stop()
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import logging
from pathlib import Path

from ..core.state_manager import StateManager


logger = logging.getLogger(__name__)


class Colors:
    """ANSI color codes"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    MAGENTA = '\033[95m'


class EmergencyStop:
    """
    Emergency stop mechanism for trading bot.
    
    Provides immediate halt capability with:
    - Position marking for emergency exit
    - Order cancellation
    - Safety confirmations
    - Audit logging
    """
    
    def __init__(self, state_dir: str = "state", mode: str = "paper"):
        """
        Initialize emergency stop.
        
        Args:
            state_dir: Base state directory
            mode: Trading mode (paper, live, backtest)
        """
        self.state_dir = state_dir
        self.mode = mode.lower()
        
        # Mode-specific state directory
        self.mode_state_dir = f"{state_dir}/{self.mode}"
        self.state = StateManager(self.mode_state_dir)
        
        logger.info(f"Emergency stop initialized for {mode.upper()} mode")
    
    def execute_emergency_stop(self, reason: str = "Manual intervention") -> bool:
        """
        Execute emergency stop procedure.
        
        Args:
            reason: Reason for emergency stop
            
        Returns:
            True if successful, False otherwise
        """
        print(f"{Colors.BOLD}{Colors.RED}{'=' * 60}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.RED}🚨 EMERGENCY STOP INITIATED 🚨{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.RED}{'=' * 60}{Colors.RESET}")
        print(f"{Colors.YELLOW}Reason: {reason}{Colors.RESET}")
        print(f"{Colors.YELLOW}Mode: {self.mode.upper()}{Colors.RESET}")
        
        # Load current positions
        positions = self.state.load_positions()
        orders = self.state.load_orders()
        
        if not positions and not orders:
            print(f"\\n{Colors.GREEN}✓ No open positions or pending orders. Nothing to do.{Colors.RESET}")
            return True
        
        # Display what will be affected
        self._display_impact_summary(positions, orders)
        
        # Safety confirmation
        if not self._get_user_confirmation():
            print(f"\\n{Colors.YELLOW}Emergency stop cancelled by user.{Colors.RESET}")
            return False
        
        success = True
        
        try:
            # Mark all positions for emergency exit
            if positions:
                success &= self._mark_positions_for_exit(positions, reason)
            
            # Cancel all pending orders
            if orders:
                success &= self._cancel_pending_orders(orders, reason)
            
            # Log emergency event
            self._log_emergency_event(reason, positions, orders)
            
            if success:
                print(f"\\n{Colors.GREEN}✓ Emergency stop completed successfully.{Colors.RESET}")
                print(f"{Colors.CYAN}Next steps:{Colors.RESET}")
                print(f"  1. Run your trading execution to process exits")
                print(f"  2. Monitor positions until all are closed")
                print(f"  3. Review logs for emergency event details")
            else:
                print(f"\\n{Colors.YELLOW}⚠ Emergency stop completed with some errors.{Colors.RESET}")
                print(f"{Colors.YELLOW}Check logs for details.{Colors.RESET}")
            
        except Exception as e:
            print(f"\\n{Colors.RED}❌ Emergency stop failed: {e}{Colors.RESET}")
            logger.error(f"Emergency stop failed: {e}")
            success = False
        
        return success
    
    def check_emergency_triggers(
        self, 
        daily_pnl: float, 
        daily_loss_limit: float,
        max_drawdown: Optional[float] = None,
        drawdown_limit: Optional[float] = None
    ) -> Optional[str]:
        """
        Check if automatic emergency triggers should fire.
        
        Args:
            daily_pnl: Current daily P&L
            daily_loss_limit: Maximum daily loss allowed
            max_drawdown: Current maximum drawdown
            drawdown_limit: Maximum drawdown limit
            
        Returns:
            Trigger reason if emergency stop needed, None otherwise
        """
        # Daily loss limit check
        if daily_pnl <= -abs(daily_loss_limit):
            return f"Daily loss limit breached: Rs.{daily_pnl:,.2f} <= Rs.{-abs(daily_loss_limit):,.2f}"
        
        # Drawdown limit check
        if max_drawdown and drawdown_limit and max_drawdown >= drawdown_limit:
            return f"Drawdown limit breached: Rs.{max_drawdown:,.2f} >= Rs.{drawdown_limit:,.2f}"
        
        return None
    
    def _display_impact_summary(self, positions: Dict, orders: Dict):
        """Display what will be affected by emergency stop"""
        print(f"\\n{Colors.BOLD}IMPACT SUMMARY:{Colors.RESET}")
        
        if positions:
            total_exposure = 0.0
            unrealized_pnl = 0.0
            
            print(f"\\n{Colors.MAGENTA}OPEN POSITIONS TO BE CLOSED:{Colors.RESET}")
            print(f"  {'Symbol':<12} {'Qty':<8} {'Entry':<10} {'Exposure':<12} {'Est. P&L':<12}")
            print(f"  {'-'*60}")
            
            for symbol, pos in positions.items():
                qty = pos.get('qty_remaining', 0)
                if qty <= 0:
                    continue
                    
                entry = pos.get('entry', 0.0)
                current = pos.get('current_price', entry)
                
                exposure = qty * entry
                pnl = (current - entry) * qty
                
                total_exposure += exposure
                unrealized_pnl += pnl
                
                pnl_color = Colors.GREEN if pnl >= 0 else Colors.RED
                
                print(
                    f"  {symbol:<12} {qty:<8} Rs.{entry:<9.2f} Rs.{exposure:<11,.0f} "
                    f"{pnl_color}Rs.{pnl:<+11.2f}{Colors.RESET}"
                )
            
            print(f"  {'-'*60}")
            pnl_color = Colors.GREEN if unrealized_pnl >= 0 else Colors.RED
            print(f"  Total Exposure: Rs.{total_exposure:,.2f}")
            print(f"  Est. Unrealized P&L: {pnl_color}Rs.{unrealized_pnl:+,.2f}{Colors.RESET}")
        
        if orders:
            pending_capital = 0.0
            
            print(f"\\n{Colors.MAGENTA}PENDING ORDERS TO BE CANCELLED:{Colors.RESET}")
            print(f"  {'Symbol':<12} {'Side':<6} {'Qty':<8} {'Price':<10} {'Capital':<12}")
            print(f"  {'-'*55}")
            
            for order_id, order in orders.items():
                if order.get('status') not in ['PENDING', 'PARTIAL']:
                    continue
                
                symbol = order.get('symbol', '')
                side = order.get('side', '')
                qty = order.get('req_qty', 0)
                price = order.get('price', 0.0)
                
                capital = qty * price if side == 'BUY' else 0
                pending_capital += capital
                
                side_color = Colors.GREEN if side == 'BUY' else Colors.RED
                
                print(
                    f"  {symbol:<12} {side_color}{side:<6}{Colors.RESET} {qty:<8} "
                    f"Rs.{price:<9.2f} Rs.{capital:<11,.0f}"
                )
            
            print(f"  {'-'*55}")
            print(f"  Capital to be Released: Rs.{pending_capital:,.2f}")
    
    def _get_user_confirmation(self) -> bool:
        """Get user confirmation for emergency stop"""
        print(f"\\n{Colors.BOLD}{Colors.YELLOW}⚠ WARNING: This will immediately mark all positions for exit! ⚠{Colors.RESET}")
        
        try:
            confirmation = input(f"\\n{Colors.BOLD}Type 'EMERGENCY' to confirm: {Colors.RESET}").strip()
            return confirmation.upper() == 'EMERGENCY'
        except KeyboardInterrupt:
            return False
    
    def _mark_positions_for_exit(self, positions: Dict, reason: str) -> bool:
        """Mark all positions for emergency exit"""
        try:
            # Load existing positions and merge changes to avoid replacing the whole file
            existing_positions = self.state.load_positions() or {}
            any_updated = False

            for symbol, pos in existing_positions.items():
                qty = pos.get('qty_remaining', pos.get('qty', 0))
                if qty <= 0:
                    continue

                # Merge and enrich the existing position
                updated_pos = pos.copy()
                updated_pos['emergency_exit'] = True
                updated_pos['emergency_reason'] = reason
                updated_pos['emergency_time'] = datetime.now().isoformat()

                # Normalize entry price field: prefer 'entry_price', fallback to legacy 'entry'
                entry_price = pos.get('entry_price', pos.get('entry', 0))
                updated_pos['entry_price'] = entry_price

                # Ensure quantity fields exist for validators downstream
                if 'qty_remaining' not in updated_pos and 'quantity' in updated_pos:
                    updated_pos['qty_remaining'] = updated_pos.get('quantity', 0)
                if 'quantity' not in updated_pos and 'qty_remaining' in updated_pos:
                    updated_pos['quantity'] = updated_pos.get('qty_remaining', 0)

                # Keep a clear marker for where to exit (use entry price as placeholder)
                updated_pos['target'] = entry_price

                existing_positions[symbol] = updated_pos
                any_updated = True
                print(f"  ✓ {symbol}: Marked for emergency exit")

            # Save merged positions back to state (atomic and validated by StateManager)
            if any_updated:
                self.state.save_positions(existing_positions)

            return True
            
        except Exception as e:
            logger.error(f"Failed to mark positions for exit: {e}")
            return False
    
    def _cancel_pending_orders(self, orders: Dict, reason: str) -> bool:
        """Cancel all pending orders"""
        try:
            updated_orders = {}
            
            for order_id, order in orders.items():
                if order.get('status') not in ['PENDING', 'PARTIAL']:
                    updated_orders[order_id] = order
                    continue
                
                # Mark as cancelled
                updated_order = order.copy()
                updated_order['status'] = 'CANCELLED'
                updated_order['rejection_reason'] = f"Emergency stop: {reason}"
                updated_order['updated_at'] = datetime.now().isoformat()
                
                updated_orders[order_id] = updated_order
                
                symbol = order.get('symbol', 'UNKNOWN')
                side = order.get('side', '')
                print(f"  ✓ {symbol}: {side} order cancelled")
            
            # Save updated orders
            if updated_orders:
                self.state.save_orders(updated_orders)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to cancel orders: {e}")
            return False
    
    def _log_emergency_event(self, reason: str, positions: Dict, orders: Dict):
        """Log emergency stop event for audit trail"""
        try:
            event = {
                "timestamp": datetime.now().isoformat(),
                "mode": self.mode.upper(),
                "reason": reason,
                "positions_affected": len([p for p in positions.values() if p.get('qty_remaining', 0) > 0]),
                "orders_cancelled": len([o for o in orders.values() if o.get('status') in ['PENDING', 'PARTIAL']]),
                "total_exposure": sum(
                    p.get('qty_remaining', 0) * p.get('entry', 0) 
                    for p in positions.values() 
                    if p.get('qty_remaining', 0) > 0
                )
            }
            
            # Save to emergency log
            log_file = f"{self.mode_state_dir}/emergency_log.json"
            
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    log_data = json.load(f)
            else:
                log_data = []
            
            log_data.append(event)
            
            with open(log_file, 'w') as f:
                json.dump(log_data, f, indent=2)
            
            logger.critical(f"Emergency stop executed: {reason}")
            
        except Exception as e:
            logger.error(f"Failed to log emergency event: {e}")


# Command line interface
def main():
    """CLI entry point for emergency stop"""
    import sys
    
    mode = sys.argv[1] if len(sys.argv) > 1 else "paper"
    reason = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Manual CLI intervention"
    
    emergency = EmergencyStop(mode=mode)
    
    try:
        success = emergency.execute_emergency_stop(reason=reason)
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print(f"\\n{Colors.YELLOW}Emergency stop interrupted{Colors.RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\\n{Colors.RED}Emergency stop error: {e}{Colors.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()