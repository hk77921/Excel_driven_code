import logging
from typing import Dict, Tuple, List

from src.core.state_manager import StateManager
from src.core.models import OrderSide, OrderStatus

logger = logging.getLogger(__name__)


class ReconciliationResult:
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.fixed_positions = 0
        self.fixed_orders = 0
        self.ghost_positions_removed = 0
        self.closed_positions_cleaned = 0

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


class BrokerStateReconciler:
    """
    Reconciles broker truth with local state.
    Broker ALWAYS wins.
    """

    def __init__(self, broker, state: StateManager):
        self.broker = broker
        self.state = state

    def reconcile(self) -> ReconciliationResult:
        result = ReconciliationResult()

        broker_positions = self._safe_call(self.broker.get_positions, "get_positions", result)
        broker_orders = self._safe_call(self.broker.get_open_orders, "get_open_orders", result)

        if broker_positions is None or broker_orders is None:
            result.errors.append("Broker data unavailable")
            return result

        # Debug logging
        logger.info(f"[RECON] Broker has {len(broker_orders)} open orders: {list(broker_orders.keys())}")

        local_positions = self.state.load_positions()
        local_orders = self.state.load_orders()
        
        logger.info(f"[RECON] Local has {len(local_orders)} orders: {list(local_orders.keys())}")

        # NEW: Clean closed positions from broker
        self._clean_closed_broker_positions(broker_positions, local_positions, result)

        self._reconcile_positions(broker_positions, local_positions, result)
        self._reconcile_orders(broker_orders, local_orders, result)

        return result



    def _reconcile_positions(
        self,
        broker_positions: Dict[str, dict],
        local_positions: Dict[str, dict],
        result: ReconciliationResult
    ):
        # Broker → Local
        for symbol, bp in broker_positions.items():
            qty = bp.get("qty", 0)
            if qty <= 0:
                continue

            if symbol not in local_positions:
                logger.warning(f"[RECON] Missing local position for {symbol}, rebuilding")
                local_positions[symbol] = {
                    "symbol": symbol,
                    "side": OrderSide.BUY,
                    "entry_price": bp["avg_price"],
                    "quantity": qty,
                    "qty_remaining": qty,
                    "atr": bp.get("atr", 0),
                    "stop_loss": bp.get("stop_loss"),
                    "target": bp.get("target"),
                    "partial_exit_done": False,
                    "status": "OPEN",
                    "sector": bp.get("sector")
                }
                result.fixed_positions += 1

            else:
                lp = local_positions[symbol]

                if lp["qty_remaining"] != qty:
                    logger.error(
                        f"[RECON] Qty mismatch {symbol}: local={lp['qty_remaining']} broker={qty}"
                    )
                    lp["qty_remaining"] = qty
                    lp["quantity"] = qty  # Sync total qty as well
                    
                    result.fixed_positions += 1

                if abs(lp["entry_price"] - bp["avg_price"]) > 0.01:
                    logger.warning(
                        f"[RECON] Price mismatch {symbol}: local={lp['entry_price']} broker={bp['avg_price']}"
                    )
                    lp["entry_price"] = bp["avg_price"]
                    result.fixed_positions += 1

        # Local → Broker (ghost positions)
        for symbol in list(local_positions.keys()):
            if symbol not in broker_positions:
                logger.critical(f"[RECON] Ghost position detected: {symbol}, removing")
                del local_positions[symbol]
                result.fixed_positions += 1

        self.state.save_positions(local_positions)



    def _reconcile_orders(
    self,
    broker_orders: Dict[str, dict],
    local_orders: Dict[str, dict],
    result: ReconciliationResult
):
        broker_order_ids = set(broker_orders.keys())
        orders_to_remove = []

        # Local orders missing at broker
        for oid, lo in local_orders.items():
            if oid not in broker_order_ids:
                status = lo.get("status", "UNKNOWN")
                # Remove any order that's not completed but missing from broker
                if status in [OrderStatus.PENDING.value, OrderStatus.PARTIAL.value, "OPEN", "TRIGGER_PENDING"]:
                    logger.warning(f"[RECON] Removing stale local order {oid} (status: {status})")
                    orders_to_remove.append(oid)
                    result.fixed_orders += 1
        
        # Remove stale orders
        for oid in orders_to_remove:
            del local_orders[oid]

        # Broker orders missing locally
        for oid, bo in broker_orders.items():
            if oid not in local_orders:
                logger.warning(f"[RECON] Importing broker order {oid}")
                local_orders[oid] = {
                    "order_id": oid,
                    "symbol": bo["symbol"],
                    "side": bo["side"],
                    "req_qty": bo["qty"],
                    "filled_qty": bo["filled_qty"],
                    "price": bo.get("price", 0),
                    "status": bo["status"],
                }
                result.fixed_orders += 1

        self.state.save_orders(local_orders)


    def _clean_closed_broker_positions(
        self,
        broker_positions: Dict[str, dict],
        local_positions: Dict[str, dict],
        result: ReconciliationResult
    ):
        """
        NEW METHOD: Remove local positions that broker shows as closed (qty=0)
        
        This is the CRITICAL fix for ghost positions showing P&L but 0 quantity
        """
        symbols_to_remove = []
        
        for symbol, bp in broker_positions.items():
            qty = bp.get("qty", 0)
            
            # Broker shows position as CLOSED (qty=0)
            if qty == 0:
                # But we have it in local state as OPEN
                if symbol in local_positions and local_positions[symbol].get('qty_remaining', 0) > 0:
                    logger.critical(
                        f"[RECON] CLOSED POSITION AT BROKER: {symbol} "
                        f"(local thinks qty={local_positions[symbol].get('qty_remaining', 0)}, "
                        f"broker shows qty=0)"
                    )
                    
                    # Mark for removal
                    symbols_to_remove.append(symbol)
                    result.closed_positions_cleaned += 1
        
        # Remove closed positions from local state
        for symbol in symbols_to_remove:
            logger.info(f"[RECON] Removing closed position: {symbol}")
            del local_positions[symbol]
        
        # Save cleaned positions
        if symbols_to_remove:
            self.state.save_positions(local_positions)
            logger.info(f"[RECON] Cleaned {len(symbols_to_remove)} closed positions")


    def _safe_call(self, fn, name: str, result: ReconciliationResult):
        try:
            return fn()
        except Exception as e:
            logger.critical(f"[RECON] Broker call failed: {name} → {e}")
            result.errors.append(f"{name} failed")
            return None

