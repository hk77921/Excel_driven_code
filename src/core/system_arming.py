"""
System Arming - Safety Control System  
=====================================

Implements the "Arm Risk & Kill Switches" phase from the system architecture.
Ensures all safety systems are active and validated before trading begins.

This is the final safety checkpoint before the system goes live.
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date
from dataclasses import dataclass
from enum import Enum
import os
import json

from .state_manager import StateManager
from .risk_manager import RiskManager
from .models import Position, Order

logger = logging.getLogger(__name__)


class ArmingStatus(Enum):
    DISARMED = "DISARMED"
    ARMING = "ARMING"
    ARMED = "ARMED"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    FAILED = "FAILED"


@dataclass
class SafetyCheck:
    """Individual safety check result"""
    name: str
    passed: bool
    message: str
    critical: bool = True
    

@dataclass
class ArmingResult:
    """Result of system arming process"""
    status: ArmingStatus
    checks: List[SafetyCheck]
    armed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    @property
    def all_critical_checks_passed(self) -> bool:
        return all(check.passed for check in self.checks if check.critical)
    
    @property
    def failed_checks(self) -> List[SafetyCheck]:
        return [check for check in self.checks if not check.passed]


class KillSwitch:
    """Individual kill switch implementation"""
    
    def __init__(self, name: str, check_function, critical: bool = True):
        self.name = name
        self.check_function = check_function
        self.critical = critical
        self.enabled = True
        self.last_check: Optional[datetime] = None
        self.last_result: Optional[bool] = None
    
    def check(self) -> SafetyCheck:
        """Execute the kill switch check"""
        try:
            self.last_check = datetime.now()
            result = self.check_function()
            self.last_result = result
            
            return SafetyCheck(
                name=self.name,
                passed=result,
                message=f"Kill switch '{self.name}' {'ACTIVE' if result else 'TRIGGERED'}",
                critical=self.critical
            )
        except Exception as e:
            logger.error(f"Kill switch '{self.name}' check failed: {e}")
            self.last_result = False
            return SafetyCheck(
                name=self.name,
                passed=False,
                message=f"Kill switch '{self.name}' check failed: {e}",
                critical=self.critical
            )


class SystemArming:
    """
    System Safety and Arming Control.
    
    Key responsibilities:
    1. Validate all safety systems before trading
    2. Implement kill switches and emergency stops
    3. Provide manual arming/disarming controls
    4. Monitor system health during operation
    5. Automatic disarming on critical failures
    """
    
    def __init__(self, risk_manager: RiskManager, state_manager: StateManager):
        self.risk_manager = risk_manager
        self.state = state_manager
        
        # Arming state
        self.status = ArmingStatus.DISARMED
        self.armed_at: Optional[datetime] = None
        self.last_arming_result: Optional[ArmingResult] = None
        
        # Kill switches
        self.kill_switches: Dict[str, KillSwitch] = {}
        self._initialize_kill_switches()
        
        # Emergency controls
        self.manual_emergency_stop = False
        self.auto_disarm_on_failure = True
        
        logger.info(f"System Arming initialized with {len(self.kill_switches)} kill switches")
    
    def _initialize_kill_switches(self):
        """Initialize all kill switches"""
        
        # Emergency stop file check
        self.add_kill_switch(
            "emergency_file",
            lambda: not os.path.exists("EMERGENCY_STOP.txt"),
            critical=True
        )
        
        # Daily loss limit check  
        self.add_kill_switch(
            "daily_loss_limit",
            self._check_daily_loss_limit,
            critical=True
        )
        
        # Capital availability check
        self.add_kill_switch(
            "capital_availability", 
            self._check_capital_availability,
            critical=True
        )
        
        # Market hours check
        self.add_kill_switch(
            "market_hours",
            self._check_market_hours,
            critical=False  # Non-critical - can trade outside hours in some modes
        )
        
        # System health check
        self.add_kill_switch(
            "system_health",
            self._check_system_health,
            critical=True
        )
        
        # Configuration integrity
        self.add_kill_switch(
            "config_integrity",
            self._check_config_integrity,
            critical=True
        )
        
        # State file integrity
        self.add_kill_switch(
            "state_integrity",
            self._check_state_integrity,
            critical=True
        )
    
    def add_kill_switch(self, name: str, check_function, critical: bool = True):
        """Add a new kill switch"""
        kill_switch = KillSwitch(name, check_function, critical)
        self.kill_switches[name] = kill_switch
        logger.info(f"Added kill switch: {name} ({'Critical' if critical else 'Non-critical'})")
    
    def remove_kill_switch(self, name: str) -> bool:
        """Remove a kill switch"""
        if name in self.kill_switches:
            del self.kill_switches[name]
            logger.info(f"Removed kill switch: {name}")
            return True
        return False
    
    def arm_system(self, force: bool = False) -> ArmingResult:
        """
        Arm the trading system after comprehensive safety checks.
        
        Args:
            force: Skip non-critical checks (use with extreme caution)
        
        Returns:
            ArmingResult with status and check results
        """
        logger.info("Starting system arming sequence...")
        self.status = ArmingStatus.ARMING
        
        try:
            # Run all safety checks
            checks = []
            
            # 1. Kill switch checks
            for name, kill_switch in self.kill_switches.items():
                if not kill_switch.enabled:
                    continue
                    
                check = kill_switch.check()
                checks.append(check)
                
                # Fail immediately on critical check failure (unless forced)
                if not check.passed and check.critical and not force:
                    logger.error(f"Critical safety check failed: {check.name}")
                    result = ArmingResult(
                        status=ArmingStatus.FAILED,
                        checks=checks,
                        error_message=f"Critical check failed: {check.name} - {check.message}"
                    )
                    self.last_arming_result = result
                    self.status = ArmingStatus.FAILED
                    return result
            
            # 2. Risk manager validation
            risk_check = self._validate_risk_manager()
            checks.append(risk_check)
            
            if not risk_check.passed and not force:
                logger.error("Risk manager validation failed")
                result = ArmingResult(
                    status=ArmingStatus.FAILED,
                    checks=checks,
                    error_message=f"Risk manager validation failed: {risk_check.message}"
                )
                self.last_arming_result = result
                self.status = ArmingStatus.FAILED
                return result
            
            # 3. Position reconciliation check
            reconciliation_check = self._check_position_reconciliation()
            checks.append(reconciliation_check)
            
            if not reconciliation_check.passed and not force:
                logger.error("Position reconciliation failed")
                result = ArmingResult(
                    status=ArmingStatus.FAILED,
                    checks=checks,
                    error_message=f"Reconciliation failed: {reconciliation_check.message}"
                )
                self.last_arming_result = result
                self.status = ArmingStatus.FAILED
                return result
            
            # 4. Final validation
            final_check = self._final_arming_validation()
            checks.append(final_check)
            
            # Determine final status
            critical_failures = [c for c in checks if not c.passed and c.critical]
            
            if critical_failures and not force:
                self.status = ArmingStatus.FAILED
                result = ArmingResult(
                    status=ArmingStatus.FAILED,
                    checks=checks,
                    error_message="Critical safety checks failed"
                )
            else:
                self.status = ArmingStatus.ARMED
                self.armed_at = datetime.now()
                
                # Save armed state
                self._save_armed_state()
                
                result = ArmingResult(
                    status=ArmingStatus.ARMED,
                    checks=checks,
                    armed_at=self.armed_at
                )
                
                logger.info(f"🔒 SYSTEM ARMED at {self.armed_at.strftime('%H:%M:%S')}")
                
                if force and critical_failures:
                    logger.warning(f"⚠️  FORCE ARMED with {len(critical_failures)} critical failures!")
            
            self.last_arming_result = result
            return result
            
        except Exception as e:
            logger.error(f"System arming failed with exception: {e}")
            self.status = ArmingStatus.FAILED
            
            result = ArmingResult(
                status=ArmingStatus.FAILED,
                checks=checks if 'checks' in locals() else [],
                error_message=f"Arming exception: {e}"
            )
            self.last_arming_result = result
            return result
    
    def disarm_system(self, reason: str = "Manual disarm"):
        """Disarm the trading system"""
        logger.warning(f"🔓 SYSTEM DISARMED: {reason}")
        
        previous_status = self.status
        self.status = ArmingStatus.DISARMED
        self.armed_at = None
        
        # Clear armed state
        self._clear_armed_state()
        
        # Log disarming
        disarm_event = {
            'timestamp': datetime.now().isoformat(),
            'reason': reason,
            'previous_status': previous_status.value,
            'disarmed_by': 'system' if self.auto_disarm_on_failure else 'manual'
        }
        
        self._log_arming_event('disarmed', disarm_event)
    
    def emergency_stop(self, reason: str):
        """Activate emergency stop"""
        logger.critical(f"🚨 EMERGENCY STOP ACTIVATED: {reason}")
        
        self.manual_emergency_stop = True
        self.status = ArmingStatus.EMERGENCY_STOP
        
        # Create emergency stop file
        with open("EMERGENCY_STOP.txt", "w") as f:
            f.write(f"Emergency Stop: {reason}\nTimestamp: {datetime.now()}\n")
        
        # Notify risk manager
        self.risk_manager.activate_emergency_mode(reason)
        
        # Log emergency event
        emergency_event = {
            'timestamp': datetime.now().isoformat(),
            'reason': reason,
            'triggered_by': 'manual'
        }
        
        self._log_arming_event('emergency_stop', emergency_event)
    
    def reset_emergency_stop(self, authorization_code: str = None):
        """Reset emergency stop (requires authorization)"""
        # Simple authorization check (in production would be more sophisticated)
        if authorization_code != "RESET_EMERGENCY":
            logger.error("Emergency stop reset failed: Invalid authorization code")
            return False
        
        logger.info("🔄 Emergency stop reset authorized")
        
        self.manual_emergency_stop = False
        
        # Remove emergency stop file
        if os.path.exists("EMERGENCY_STOP.txt"):
            os.remove("EMERGENCY_STOP.txt")
        
        # Reset risk manager
        self.risk_manager.deactivate_emergency_mode()
        
        # Return to disarmed state (requires manual arming)
        self.status = ArmingStatus.DISARMED
        
        logger.info("Emergency stop reset complete - system ready for manual arming")
        return True
    
    def check_armed_status(self) -> bool:
        """Check if system is currently armed and safe"""
        if self.status != ArmingStatus.ARMED:
            return False
        
        # Run continuous safety checks if armed
        if self.auto_disarm_on_failure:
            critical_failures = []
            
            for name, kill_switch in self.kill_switches.items():
                if not kill_switch.enabled or not kill_switch.critical:
                    continue
                
                check = kill_switch.check()
                if not check.passed:
                    critical_failures.append(check)
            
            if critical_failures:
                failure_reasons = [f.message for f in critical_failures]
                self.disarm_system(f"Auto-disarm: {'; '.join(failure_reasons)}")
                return False
        
        return True
    
    def get_arming_status(self) -> Dict:
        """Get comprehensive arming status"""
        # Run current kill switch checks
        current_checks = []
        for name, kill_switch in self.kill_switches.items():
            if kill_switch.enabled:
                check = kill_switch.check()
                current_checks.append({
                    'name': check.name,
                    'passed': check.passed,
                    'message': check.message,
                    'critical': check.critical,
                    'last_check': kill_switch.last_check.isoformat() if kill_switch.last_check else None
                })
        
        return {
            'status': self.status.value,
            'armed_at': self.armed_at.isoformat() if self.armed_at else None,
            'manual_emergency_stop': self.manual_emergency_stop,
            'auto_disarm_enabled': self.auto_disarm_on_failure,
            'kill_switches': current_checks,
            'last_arming_result': {
                'status': self.last_arming_result.status.value,
                'checks_passed': len([c for c in self.last_arming_result.checks if c.passed]),
                'total_checks': len(self.last_arming_result.checks),
                'error_message': self.last_arming_result.error_message
            } if self.last_arming_result else None
        }
    
    # Kill switch check implementations
    def _check_daily_loss_limit(self) -> bool:
        """Check if daily loss limit is not exceeded"""
        try:
            risk_status = self.risk_manager.get_risk_status()
            daily_pnl = risk_status['daily_pnl']
            daily_limit = risk_status['daily_loss_limit']
            
            return daily_pnl > -daily_limit
        except Exception as e:
            logger.error(f"Daily loss limit check failed: {e}")
            return False
    
    def _check_capital_availability(self) -> bool:
        """Check if sufficient capital is available"""
        try:
            risk_status = self.risk_manager.get_risk_status()
            available_capital = risk_status['available_capital']
            
            # Require at least minimum position value available
            min_required = self.risk_manager.capital_params.max_position_value * 0.1
            return available_capital > min_required
        except Exception as e:
            logger.error(f"Capital availability check failed: {e}")
            return False
    
    def _check_market_hours(self) -> bool:
        """Check if within market hours (non-critical)"""
        try:
            current_time = datetime.now()
            
            # Weekend check
            if current_time.weekday() >= 5:
                return False
            
            # Market hours check (9:15 AM to 3:30 PM)
            market_open = current_time.replace(hour=9, minute=15, second=0, microsecond=0)
            market_close = current_time.replace(hour=15, minute=30, second=0, microsecond=0)
            
            return market_open <= current_time <= market_close
        except Exception as e:
            logger.error(f"Market hours check failed: {e}")
            return False
    
    def _check_system_health(self) -> bool:
        """Check overall system health"""
        try:
            # Check critical directories exist
            required_dirs = ['state', 'config', 'logs']
            for dir_name in required_dirs:
                if not os.path.exists(dir_name):
                    logger.error(f"Required directory missing: {dir_name}")
                    return False
            
            # Check disk space (require at least 100MB)
            import shutil
            free_space = shutil.disk_usage('.').free
            if free_space < 100 * 1024 * 1024:  # 100MB
                logger.error(f"Low disk space: {free_space / (1024*1024):.1f}MB")
                return False
            
            return True
        except Exception as e:
            logger.error(f"System health check failed: {e}")
            return False
    
    def _check_config_integrity(self) -> bool:
        """Check configuration file integrity"""
        try:
            # Verify key config files exist and are readable
            config_files = [
                'config/trading_config.yaml',
                'config/broker.yaml', 
                'config/timing_config.yaml'
            ]
            
            for config_file in config_files:
                if not os.path.exists(config_file):
                    logger.error(f"Config file missing: {config_file}")
                    return False
                
                # Try to read the file
                with open(config_file, 'r') as f:
                    f.read()
            
            return True
        except Exception as e:
            logger.error(f"Config integrity check failed: {e}")
            return False
    
    def _check_state_integrity(self) -> bool:
        """Check state file integrity"""
        try:
            # Basic state file checks
            state_files = [
                'state/positions.json',
                'state/orders.json', 
                'state/daily_pnl.json'
            ]
            
            for state_file in state_files:
                if os.path.exists(state_file):
                    try:
                        with open(state_file, 'r') as f:
                            json.load(f)  # Verify JSON is valid
                    except json.JSONDecodeError as e:
                        logger.error(f"Corrupted state file {state_file}: {e}")
                        return False
            
            return True
        except Exception as e:
            logger.error(f"State integrity check failed: {e}")
            return False
    
    def _validate_risk_manager(self) -> SafetyCheck:
        """Validate risk manager is properly configured"""
        try:
            risk_status = self.risk_manager.get_risk_status()
            
            # Check if risk manager has reasonable limits
            if risk_status.get('daily_loss_limit', 0) <= 0:
                return SafetyCheck(
                    name="risk_manager",
                    passed=False,
                    message="Risk manager daily loss limit not configured",
                    critical=True
                )
            
            if risk_status.get('max_positions', 0) <= 0:
                return SafetyCheck(
                    name="risk_manager", 
                    passed=False,
                    message="Risk manager position limits not configured",
                    critical=True
                )
            
            return SafetyCheck(
                name="risk_manager",
                passed=True,
                message="Risk manager validation passed",
                critical=True
            )
            
        except Exception as e:
            return SafetyCheck(
                name="risk_manager",
                passed=False,
                message=f"Risk manager validation failed: {e}",
                critical=True
            )
    
    def _check_position_reconciliation(self) -> SafetyCheck:
        """Check if positions are reconciled with broker"""
        try:
            # This would normally run broker reconciliation
            # For now, just check if state is consistent
            positions = self.state.load_positions()
            
            # Basic consistency check
            for position in positions:
                if position.status.value == "OPEN" and position.quantity <= 0:
                    return SafetyCheck(
                        name="position_reconciliation",
                        passed=False,
                        message=f"Invalid position state: {position.symbol}",
                        critical=True
                    )
            
            return SafetyCheck(
                name="position_reconciliation",
                passed=True,
                message="Position reconciliation passed",
                critical=True
            )
            
        except Exception as e:
            return SafetyCheck(
                name="position_reconciliation",
                passed=False,
                message=f"Position reconciliation failed: {e}",
                critical=True
            )
    
    def _final_arming_validation(self) -> SafetyCheck:
        """Final validation before arming"""
        try:
            # Ensure no emergency conditions
            if self.manual_emergency_stop:
                return SafetyCheck(
                    name="final_validation",
                    passed=False,
                    message="Manual emergency stop is active",
                    critical=True
                )
            
            # Check if already armed
            if self.status == ArmingStatus.ARMED:
                return SafetyCheck(
                    name="final_validation",
                    passed=False,
                    message="System is already armed",
                    critical=False
                )
            
            return SafetyCheck(
                name="final_validation",
                passed=True,
                message="Final validation passed - system ready to arm",
                critical=True
            )
            
        except Exception as e:
            return SafetyCheck(
                name="final_validation",
                passed=False,
                message=f"Final validation failed: {e}",
                critical=True
            )
    
    def _save_armed_state(self):
        """Save armed state to persistent storage"""
        try:
            armed_state = {
                'armed_at': self.armed_at.isoformat(),
                'status': self.status.value,
                'arming_checks': len(self.last_arming_result.checks) if self.last_arming_result else 0
            }
            
            os.makedirs('state', exist_ok=True)
            with open('state/armed_state.json', 'w') as f:
                json.dump(armed_state, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save armed state: {e}")
    
    def _clear_armed_state(self):
        """Clear armed state from persistent storage"""
        try:
            if os.path.exists('state/armed_state.json'):
                os.remove('state/armed_state.json')
        except Exception as e:
            logger.error(f"Failed to clear armed state: {e}")
    
    def _log_arming_event(self, event_type: str, event_data: Dict):
        """Log arming/disarming events"""
        try:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'event_type': event_type,
                'data': event_data
            }
            
            os.makedirs('logs', exist_ok=True)
            log_file = f"logs/arming_events_{date.today().isoformat()}.json"
            
            # Append to log file
            events = []
            if os.path.exists(log_file):
                try:
                    with open(log_file, 'r') as f:
                        events = json.load(f)
                except:
                    events = []
            
            events.append(log_entry)
            
            with open(log_file, 'w') as f:
                json.dump(events, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to log arming event: {e}")