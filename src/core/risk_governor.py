"""
Risk Governor - Trade Approval System
====================================

Final gatekeeper for all trade decisions. Implements multiple validation
layers and pluggable risk rules to ensure no unsafe trades are executed.

This is the last checkpoint before money is at risk.
"""

import logging
from typing import Dict, List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass,field
from enum import Enum

from .models import Order, Position, ScreenerSignal
from .risk_manager import RiskManager, RiskAssessment, RiskLevel
from .state_manager import StateManager

logger = logging.getLogger(__name__)


class GovernorDecision(Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT" 
    DEFER = "DEFER"
    MODIFY = "MODIFY"


@dataclass
class GovernorResult:
    """Result from risk governor evaluation"""
    decision: GovernorDecision
    modified_order: Optional[Order] = None
    reasons: List[str] = field(default_factory=list)
    risk_assessment: Optional[RiskAssessment] = None
    
    def __post_init__(self):
        if self.reasons is None:
            self.reasons = []
    
    def add_reason(self, reason: str):
        self.reasons.append(reason)


class RiskRule:
    """Base class for pluggable risk rules"""
    
    def __init__(self, name: str, priority: int = 50):
        self.name = name
        self.priority = priority  # Lower = higher priority
        self.enabled = True
    
    def evaluate(self, signal: ScreenerSignal, order: Order, positions: List[Position], context: Dict) -> GovernorResult:
        """Evaluate the risk rule - to be implemented by subclasses"""
        raise NotImplementedError("Risk rules must implement evaluate method")


class MarketHoursRule(RiskRule):
    """Ensure trades only happen during market hours"""
    
    def __init__(self):
        super().__init__("MarketHours", priority=10)  # High priority
    
    def evaluate(self, signal: ScreenerSignal, order: Order, positions: List[Position], context: Dict) -> GovernorResult:
        try:
            # Check if market is open (simplified - real implementation would use market calendar)
            current_time = datetime.now()
            market_open = current_time.replace(hour=9, minute=15, second=0, microsecond=0)
            market_close = current_time.replace(hour=15, minute=30, second=0, microsecond=0)
            
            # Harendra Local testing - disable market hours check

            
            # Check if it's a weekday (0=Monday, 6=Sunday)
            # if current_time.weekday() >= 5:  # Saturday or Sunday
            #     return GovernorResult(
            #         decision=GovernorDecision.REJECT,
            #         reasons=["Market closed - Weekend"]
            #     )
            
            # if not (market_open <= current_time <= market_close):
            #     return GovernorResult(
            #         decision=GovernorDecision.REJECT, 
            #         reasons=[f"Market closed - Current time: {current_time.strftime('%H:%M')}"]
            #     )
            
            return GovernorResult(decision=GovernorDecision.APPROVE)
            
        except Exception as e:
            logger.error(f"MarketHoursRule error: {e}")
            return GovernorResult(
                decision=GovernorDecision.REJECT,
                reasons=[f"Market hours check failed: {e}"]
            )


class EmergencyStopRule(RiskRule):
    """Check for emergency stop conditions"""
    
    def __init__(self, state_manager: StateManager):
        super().__init__("EmergencyStop", priority=5)  # Highest priority
        self.state = state_manager
    
    

    def evaluate(self, signal: ScreenerSignal, order: Order, positions: List[Position], context: Dict) -> GovernorResult:
        try:
            import os

            # 1️⃣ File-based emergency stop (hard kill)
            if os.path.exists("EMERGENCY_STOP.txt"):
                return GovernorResult(
                    decision=GovernorDecision.REJECT,
                    reasons=["EMERGENCY STOP file detected"]
                )

            # 2️⃣ SystemState-based emergency stop
            system_state = context.get("system_state")

            if system_state is None:
                return GovernorResult(
                    decision=GovernorDecision.REJECT,
                    reasons=["System state unavailable for emergency check"]
                )

            if system_state.emergency_stop_active:
                return GovernorResult(
                    decision=GovernorDecision.REJECT,
                    reasons=["Emergency stop active in system state"]
                )

            return GovernorResult(decision=GovernorDecision.APPROVE)

        except Exception as e:
            logger.error(f"EmergencyStopRule error: {e}")
            return GovernorResult(
                decision=GovernorDecision.REJECT,
                reasons=[f"Emergency stop check failed: {e}"]
            )

class DailyLossLimitRule(RiskRule):
    """Enforce daily loss limits"""
    
    def __init__(self, max_daily_loss: float):
        super().__init__("DailyLossLimit", priority=15)
        self.max_daily_loss = max_daily_loss
    
    def evaluate(self, signal: ScreenerSignal, order: Order, positions: List[Position], context: Dict) -> GovernorResult:
        try:
            current_pnl = context.get('daily_pnl', 0.0)
            
            if current_pnl < -self.max_daily_loss:
                return GovernorResult(
                    decision=GovernorDecision.REJECT,
                    reasons=[f"Daily loss limit exceeded: ₹{current_pnl:,.0f}"]
                )
            
            # Warning if approaching limit
            if current_pnl < -self.max_daily_loss * 0.9:
                return GovernorResult(
                    decision=GovernorDecision.DEFER,
                    reasons=[f"Approaching daily loss limit: ₹{current_pnl:,.0f}"]
                )
            
            return GovernorResult(decision=GovernorDecision.APPROVE)
            
        except Exception as e:
            logger.error(f"DailyLossLimitRule error: {e}")
            return GovernorResult(
                decision=GovernorDecision.REJECT,
                reasons=[f"Daily loss check failed: {e}"]
            )


class PositionSizeRule(RiskRule):
    """Validate and potentially modify position sizes"""
    
    def __init__(self, max_position_value: float):
        super().__init__("PositionSize", priority=20)
        self.max_position_value = max_position_value
    
    def evaluate(self, signal: ScreenerSignal, order: Order, positions: List[Position], context: Dict) -> GovernorResult:
        try:
            position_value = order.req_qty * order.price
            
            if position_value > self.max_position_value:
                # Calculate adjusted quantity
                max_quantity = int(self.max_position_value / order.price)
                
                if max_quantity > 0:
                    # Modify the order
                    modified_order = Order(
                        order_id=f"RISK_MOD_{order.order_id}",
                        symbol=order.symbol,
                        side=order.side,
                        req_qty=max_quantity,
                        price=order.price,
                        created_at=datetime.now()
                    )
                    
                    return GovernorResult(
                        decision=GovernorDecision.MODIFY,
                        modified_order=modified_order,
                        reasons=[f"Position size reduced from {order.req_qty} to {max_quantity} shares"]
                    )
                else:
                    return GovernorResult(
                        decision=GovernorDecision.REJECT,
                        reasons=[f"Position value too large: ₹{position_value:,.0f}"]
                    )
            
            return GovernorResult(decision=GovernorDecision.APPROVE)
            
        except Exception as e:
            logger.error(f"PositionSizeRule error: {e}")
            return GovernorResult(
                decision=GovernorDecision.REJECT,
                reasons=[f"Position size check failed: {e}"]
            )


class VolatilityAdjustmentRule(RiskRule):
    """Adjust position size based on volatility"""
    
    def __init__(self):
        super().__init__("VolatilityAdjustment", priority=25)
    
    def evaluate(self, signal: ScreenerSignal, order: Order, positions: List[Position], context: Dict) -> GovernorResult:
        try:
            # Get volatility from context or signal
            volatility = getattr(signal, 'volatility', None) or context.get('volatility', 0.02)
            
            adjustment_factor = 1.0
            reasons = []
            
            if volatility > 0.05:  # High volatility > 5%
                adjustment_factor = 0.6
                reasons.append(f"High volatility ({volatility:.1%}): position size reduced by 40%")
            elif volatility > 0.03:  # Medium-high volatility > 3%
                adjustment_factor = 0.8  
                reasons.append(f"Elevated volatility ({volatility:.1%}): position size reduced by 20%")
            elif volatility < 0.01:  # Low volatility < 1%
                adjustment_factor = 1.2
                reasons.append(f"Low volatility ({volatility:.1%}): position size increased by 20%")
            
            if adjustment_factor != 1.0:
                new_quantity = max(1, int(order.req_qty * adjustment_factor))
                
                modified_order = Order(
                    order_id=f"VOL_ADJ_{order.order_id}",
                    symbol=order.symbol,
                    side=order.side,
                    req_qty=new_quantity,
                    price=order.price,
                    created_at=datetime.now()
                )
                
                return GovernorResult(
                    decision=GovernorDecision.MODIFY,
                    modified_order=modified_order,
                    reasons=reasons
                )
            
            return GovernorResult(decision=GovernorDecision.APPROVE)
            
        except Exception as e:
            logger.error(f"VolatilityAdjustmentRule error: {e}")
            return GovernorResult(decision=GovernorDecision.APPROVE)  # Don't fail on volatility error


class RiskGovernor:
    """
    Final trade approval system with pluggable risk rules.
    
    Key responsibilities:
    1. Execute all risk rules in priority order
    2. Make final approve/reject/modify decisions
    3. Provide detailed reasoning for all decisions
    4. Support emergency overrides and manual controls
    """
    
    def __init__(self, risk_manager: RiskManager, state_manager: StateManager):
        self.risk_manager = risk_manager
        self.state = state_manager
        
        # Initialize built-in risk rules
        self.rules: List[RiskRule] = []
        self._initialize_default_rules()
        
        # Governor state
        self.enabled = True
        self.override_active = False
        self.stats = {
            'total_evaluations': 0,
            'approvals': 0,
            'rejections': 0,
            'modifications': 0,
            'deferrals': 0
        }
        
        logger.info(f"Risk Governor initialized with {len(self.rules)} risk rules")
    
    def _initialize_default_rules(self):
        """Initialize the default set of risk rules"""
        # Get parameters from risk manager
        capital_params = self.risk_manager.capital_params
        
        # Add built-in rules in priority order
        self.add_rule(EmergencyStopRule(self.state))
        self.add_rule(MarketHoursRule())
        #self.add_rule(DailyLossLimitRule(capital_params.daily_loss_limit))
        daily_loss_limit = (capital_params.total_capital * capital_params.max_daily_loss_pct) 
            
        self.add_rule(DailyLossLimitRule(daily_loss_limit))
        
        #self.add_rule(PositionSizeRule(capital_params.max_position_value))
        self.add_rule(VolatilityAdjustmentRule())
    
    def add_rule(self, rule: RiskRule):
        """Add a new risk rule"""
        self.rules.append(rule)
        # Sort by priority (lower number = higher priority)
        self.rules.sort(key=lambda r: r.priority)
        logger.info(f"Added risk rule: {rule.name} (priority: {rule.priority})")
    
    def remove_rule(self, rule_name: str) -> bool:
        """Remove a risk rule by name"""
        original_count = len(self.rules)
        self.rules = [r for r in self.rules if r.name != rule_name]
        removed = len(self.rules) < original_count
        if removed:
            logger.info(f"Removed risk rule: {rule_name}")
        return removed
    
    def approve_trade(
        self, 
        signal: ScreenerSignal, 
        proposed_order: Order,
        current_positions: List[Position],
        context: Optional[Dict] = None
    ) -> GovernorResult:
        """
        Final trade approval decision.
        
        Executes all risk rules and makes final decision.
        """
        self.stats['total_evaluations'] += 1
        
        try:
            # Check if governor is enabled
            if not self.enabled:
                result = GovernorResult(
                    decision=GovernorDecision.REJECT,
                    reasons=["Risk Governor is disabled"]
                )
                self._update_stats(result)
                return result
            
            # Prepare context
            if context is None:
                context = {}
            
            # Add system context
            context.update({
                'timestamp': datetime.now(),
                'daily_pnl': self._get_daily_pnl(),
                'system_state': self.state.get_system_state(),
                'override_active': self.override_active
            })
            
            logger.info(f"Risk Governor evaluating trade: {signal.symbol} x {proposed_order.req_qty}")
            
            # If override is active, skip most rules
            if self.override_active:
                logger.warning("Risk Governor override is ACTIVE - reduced rule checking")
                result = GovernorResult(
                    decision=GovernorDecision.APPROVE,
                    reasons=["Risk override active - trade approved with minimal checks"]
                )
                self._update_stats(result)
                return result
            
            # Execute all enabled rules in priority order
            current_order = proposed_order
            all_reasons = []
            
            for rule in self.rules:
                if not rule.enabled:
                    continue
                    
                try:
                    rule_result = rule.evaluate(signal, current_order, current_positions, context)
                    
                    # Add rule-specific reasons
                    if rule_result.reasons:
                        for reason in rule_result.reasons:
                            all_reasons.append(f"[{rule.name}] {reason}")
                    
                    # Handle rule decision
                    if rule_result.decision == GovernorDecision.REJECT:
                        final_result = GovernorResult(
                            decision=GovernorDecision.REJECT,
                            reasons=all_reasons
                        )
                        logger.warning(f"Trade REJECTED by {rule.name}: {signal.symbol}")
                        self._update_stats(final_result)
                        return final_result
                        
                    elif rule_result.decision == GovernorDecision.DEFER:
                        final_result = GovernorResult(
                            decision=GovernorDecision.DEFER,
                            reasons=all_reasons
                        )
                        logger.info(f"Trade DEFERRED by {rule.name}: {signal.symbol}")
                        self._update_stats(final_result)
                        return final_result
                        
                    elif rule_result.decision == GovernorDecision.MODIFY:
                        if rule_result.modified_order:
                            current_order = rule_result.modified_order
                            logger.info(f"Order modified by {rule.name}: {signal.symbol}")
                            
                except Exception as e:
                    logger.error(f"Risk rule {rule.name} failed: {e}")
                    # Continue with other rules unless it's a critical rule
                    if rule.priority <= 10:  # Critical rules
                        final_result = GovernorResult(
                            decision=GovernorDecision.REJECT,
                            reasons=all_reasons + [f"Critical rule {rule.name} failed: {e}"]
                        )
                        self._update_stats(final_result)
                        return final_result
            
            # Get comprehensive risk assessment
            risk_assessment = self.risk_manager.assess_trade_risk(signal, current_order, current_positions)
            
            # Make final decision based on risk assessment
            if not risk_assessment.approved:
                final_result = GovernorResult(
                    decision=GovernorDecision.REJECT,
                    reasons=all_reasons + risk_assessment.reasons,
                    risk_assessment=risk_assessment
                )
            else:
                # Apply any position size adjustments from risk assessment
                if risk_assessment.position_size_adjustment != 1.0:
                    adjusted_quantity = max(1, int(current_order.req_qty * risk_assessment.position_size_adjustment))
                    if adjusted_quantity != current_order.req_qty:
                        current_order = Order(
                            order_id=f"RISK_ADJ_{current_order.order_id}",
                            symbol=current_order.symbol,
                            side=current_order.side,
                            req_qty=adjusted_quantity,
                            price=current_order.price,
                            created_at=datetime.now()
                        )
                        all_reasons.append(f"Position size adjusted by risk assessment: {risk_assessment.position_size_adjustment:.2f}x")
                
                decision = GovernorDecision.MODIFY if current_order != proposed_order else GovernorDecision.APPROVE
                final_result = GovernorResult(
                    decision=decision,
                    modified_order=current_order if decision == GovernorDecision.MODIFY else None,
                    reasons=all_reasons,
                    risk_assessment=risk_assessment
                )
            
            # Log final decision
            log_level = logging.INFO if final_result.decision == GovernorDecision.APPROVE else logging.WARNING
            logger.log(log_level, f"Risk Governor final decision: {final_result.decision.value} for {signal.symbol}")
            
            self._update_stats(final_result)
            return final_result
            
        except Exception as e:
            logger.error(f"Risk Governor evaluation failed: {e}")
            error_result = GovernorResult(
                decision=GovernorDecision.REJECT,
                reasons=[f"Governor evaluation failed: {e}"]
            )
            self._update_stats(error_result)
            return error_result
    
    def enable_override(self, reason: str, duration_minutes: int = 60):
        """Enable risk override for emergency situations"""
        self.override_active = True
        logger.critical(f"RISK OVERRIDE ENABLED: {reason} (Duration: {duration_minutes} minutes)")
        
        # Set automatic disable (simplified - in production would use proper scheduler)
        import threading
        def disable_after_timeout():
            import time
            time.sleep(duration_minutes * 60)
            self.disable_override("Timeout reached")
        
        threading.Thread(target=disable_after_timeout, daemon=True).start()
    
    def disable_override(self, reason: str = "Manual disable"):
        """Disable risk override"""
        self.override_active = False
        logger.info(f"Risk override disabled: {reason}")
    
    def get_governor_status(self) -> Dict:
        """Get comprehensive governor status"""
        return {
            "enabled": self.enabled,
            "override_active": self.override_active,
            "total_rules": len(self.rules),
            "enabled_rules": len([r for r in self.rules if r.enabled]),
            "stats": self.stats.copy(),
            "rules": [
                {
                    "name": rule.name,
                    "priority": rule.priority,
                    "enabled": rule.enabled
                }
                for rule in self.rules
            ]
        }
    
    def _update_stats(self, result: GovernorResult):
        """Update governor statistics"""
        if result.decision == GovernorDecision.APPROVE:
            self.stats['approvals'] += 1
        elif result.decision == GovernorDecision.REJECT:
            self.stats['rejections'] += 1
        elif result.decision == GovernorDecision.MODIFY:
            self.stats['modifications'] += 1
        elif result.decision == GovernorDecision.DEFER:
            self.stats['deferrals'] += 1
    
    def _get_daily_pnl(self) -> float:
        """Get current daily P&L"""
        try:
            from datetime import date
            today = date.today().isoformat()
            daily_pnl = self.state.load_daily_pnl(today)
            if daily_pnl is not None:
                return float(daily_pnl.get('realized_pnl', 0.0))
            return 0.0
        except Exception:
            return 0.0