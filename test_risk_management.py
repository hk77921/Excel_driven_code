"""
Unit Tests for Enhanced Risk Management System
============================================

Tests for the new RiskManager, RiskGovernor, and SystemArming components.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import os
import tempfile
import sys
from datetime import datetime, date
import json

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.core.models import (
    CapitalParameters, TradeParameters, ScreenerSignal, Order, Position,
    OrderSide, OrderStatus, PositionStatus
)
from src.core.state_manager import StateManager
from src.core.risk_manager import RiskManager, RiskAssessment, RiskLevel
from src.core.risk_governor import RiskGovernor, GovernorDecision
from src.core.system_arming import SystemArming, ArmingStatus


class TestRiskManager(unittest.TestCase):
    """Test RiskManager functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_manager = StateManager(self.temp_dir)
        
        self.capital_params = CapitalParameters(
            total_capital=100000.0,
            max_position_value=20000.0,
            daily_loss_limit=5000.0,
            max_positions=5
        )
        
        self.trade_params = TradeParameters(
            sl_atr_mult=2.0,
            target_atr_mult=3.0,
            position_size_pct=0.02
        )
        
        self.risk_manager = RiskManager(
            self.capital_params,
            self.trade_params, 
            self.state_manager
        )
        
    def tearDown(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_risk_manager_initialization(self):
        """Test RiskManager initializes correctly"""
        self.assertIsNotNone(self.risk_manager)
        self.assertEqual(self.risk_manager.capital_params.total_capital, 100000.0)
        self.assertEqual(self.risk_manager.capital_params.max_position_value, 20000.0)
        
    def test_assess_trade_risk_basic_approval(self):
        """Test basic trade risk assessment approval"""
        signal = ScreenerSignal(
            symbol="RELIANCE.NS",
            trend="BULLISH",
            score=75.0,
            current_price=2500.0,
            volume=1000000,
            timestamp=datetime.now()
        )
        
        order = Order(
            symbol="RELIANCE.NS",
            side=OrderSide.BUY,
            quantity=5,
            price=2500.0,
            order_type=OrderType.LIMIT,
            product=ProductType.MIS
        )
        
        assessment = self.risk_manager.assess_trade_risk(signal, order, [])
        
        self.assertTrue(assessment.approved)
        self.assertIn(assessment.risk_level, [RiskLevel.LOW, RiskLevel.MEDIUM])
        self.assertLess(assessment.risk_score, 80)
        
    def test_assess_trade_risk_position_too_large(self):
        """Test risk assessment rejects oversized positions"""
        signal = ScreenerSignal(
            symbol="RELIANCE.NS",
            trend="BULLISH",
            score=75.0,
            current_price=2500.0,
            volume=1000000,
            timestamp=datetime.now()
        )
        
        # Create order that exceeds max position value
        order = Order(
            order_id="TEST002",
            symbol="RELIANCE.NS",
            side=OrderSide.BUY,
            req_qty=20,  # 20 * 2500 = 50,000 > 20,000 limit
            price=2500.0,
            created_at=datetime.now()
        )
        
        assessment = self.risk_manager.assess_trade_risk(signal, order, [])
        
        self.assertFalse(assessment.approved)
        self.assertEqual(assessment.risk_level, RiskLevel.HIGH)
        self.assertTrue(any("Position value exceeds limit" in reason for reason in assessment.reasons))
        
    def test_update_market_regime(self):
        """Test market regime updates affect risk limits"""
        original_limits = self.risk_manager._current_limits.max_position_value
        
        # Update to high volatility regime
        self.risk_manager.update_market_regime("HIGH_VOLATILITY", 0.05)
        
        # Should tighten risk limits
        self.assertLess(
            self.risk_manager._current_limits.max_position_value,
            original_limits
        )
        
    def test_get_risk_status(self):
        """Test risk status reporting"""
        status = self.risk_manager.get_risk_status()
        
        self.assertIn('daily_pnl', status)
        self.assertIn('available_capital', status)
        self.assertIn('active_positions', status)
        self.assertIn('max_positions', status)
        
    def test_emergency_mode_activation(self):
        """Test emergency mode stops new trades"""
        self.risk_manager.activate_emergency_mode("Test emergency")
        
        self.assertTrue(self.risk_manager._risk_override_active)
        self.assertEqual(self.risk_manager._current_limits.max_position_value, 0)


class TestRiskGovernor(unittest.TestCase):
    """Test RiskGovernor functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_manager = StateManager(self.temp_dir)
        
        self.capital_params = CapitalParameters(
            total_capital=100000.0,
            max_position_value=20000.0,
            daily_loss_limit=5000.0,
            max_positions=5
        )
        
        self.trade_params = TradeParameters(
            sl_atr_mult=2.0,
            target_atr_mult=3.0,
            position_size_pct=0.02
        )
        
        self.risk_manager = RiskManager(
            self.capital_params,
            self.trade_params,
            self.state_manager
        )
        
        self.risk_governor = RiskGovernor(self.risk_manager, self.state_manager)
        
    def tearDown(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        # Clean up any emergency stop files
        if os.path.exists("EMERGENCY_STOP.txt"):
            os.remove("EMERGENCY_STOP.txt")
    
    def test_governor_initialization(self):
        """Test RiskGovernor initializes with default rules"""
        self.assertIsNotNone(self.risk_governor)
        self.assertTrue(self.risk_governor.enabled)
        self.assertGreater(len(self.risk_governor.rules), 0)
        
    def test_approve_trade_basic_approval(self):
        """Test basic trade approval"""
        signal = ScreenerSignal(
            symbol="RELIANCE.NS",
            trend="BULLISH", 
            score=75.0,
            current_price=2500.0,
            volume=1000000,
            timestamp=datetime.now()
        )
        
        order = Order(
            symbol="RELIANCE.NS",
            side=OrderSide.BUY,
            quantity=5,
            price=2500.0,
            order_type=OrderType.LIMIT,
            product=ProductType.MIS
        )
        
        result = self.risk_governor.approve_trade(signal, order, [])
        
        self.assertEqual(result.decision, GovernorDecision.APPROVE)
        self.assertIsNotNone(result.reasons)
        
    def test_approve_trade_emergency_stop_rejection(self):
        """Test trade rejection during emergency stop"""
        # Create emergency stop file
        with open("EMERGENCY_STOP.txt", "w") as f:
            f.write("Test emergency stop")
        
        signal = ScreenerSignal(
            symbol="RELIANCE.NS",
            trend="BULLISH",
            score=75.0,
            current_price=2500.0,
            volume=1000000,
            timestamp=datetime.now()
        )
        
        order = Order(
            symbol="RELIANCE.NS",
            side=OrderSide.BUY,
            quantity=5,
            price=2500.0,
            order_type=OrderType.LIMIT,
            product=ProductType.MIS
        )
        
        result = self.risk_governor.approve_trade(signal, order, [])
        
        self.assertEqual(result.decision, GovernorDecision.REJECT)
        self.assertTrue(any("EMERGENCY STOP" in reason for reason in result.reasons))
        
    @patch('src.core.risk_governor.datetime')
    def test_approve_trade_market_hours_rejection(self, mock_datetime):
        """Test trade rejection outside market hours"""
        # Mock Sunday (weekend)
        mock_time = datetime(2024, 1, 7, 10, 0, 0)  # Sunday
        mock_datetime.now.return_value = mock_time
        mock_datetime.replace = datetime.replace
        
        signal = ScreenerSignal(
            symbol="RELIANCE.NS",
            trend="BULLISH",
            score=75.0,
            current_price=2500.0,
            volume=1000000,
            timestamp=mock_time
        )
        
        order = Order(
            symbol="RELIANCE.NS",
            side=OrderSide.BUY,
            quantity=5,
            price=2500.0,
            order_type=OrderType.LIMIT,
            product=ProductType.MIS
        )
        
        result = self.risk_governor.approve_trade(signal, order, [])
        
        self.assertEqual(result.decision, GovernorDecision.REJECT)
        self.assertTrue(any("Weekend" in reason for reason in result.reasons))
        
    def test_approve_trade_position_size_modification(self):
        """Test trade modification for oversized positions"""
        signal = ScreenerSignal(
            symbol="RELIANCE.NS",
            trend="BULLISH",
            score=75.0,
            current_price=2500.0,
            volume=1000000,
            timestamp=datetime.now()
        )
        
        # Create oversized order
        order = Order(
            order_id="TEST006",
            symbol="RELIANCE.NS",
            side=OrderSide.BUY,
            req_qty=20,  # Will exceed position limit
            price=2500.0,
            created_at=datetime.now()
        )
        
        result = self.risk_governor.approve_trade(signal, order, [])
        
        # Should either modify or reject (depends on exact limits)
        self.assertIn(result.decision, [GovernorDecision.MODIFY, GovernorDecision.REJECT])
        
        if result.decision == GovernorDecision.MODIFY:
            self.assertIsNotNone(result.modified_order)
            self.assertLess(result.modified_order.quantity, order.quantity)
            
    def test_governor_override(self):
        """Test risk governor override functionality"""
        self.risk_governor.enable_override("Test override", 1)  # 1 minute
        
        self.assertTrue(self.risk_governor.override_active)
        
        # Test that override bypasses most rules
        signal = ScreenerSignal(
            symbol="RELIANCE.NS",
            trend="BULLISH",
            score=75.0,
            current_price=2500.0,
            volume=1000000,
            timestamp=datetime.now()
        )
        
        # Oversized order that would normally be rejected
        order = Order(
            order_id="TEST007",
            symbol="RELIANCE.NS",
            side=OrderSide.BUY,
            req_qty=50,
            price=2500.0,
            created_at=datetime.now()
        )
        
        result = self.risk_governor.approve_trade(signal, order, [])
        
        self.assertEqual(result.decision, GovernorDecision.APPROVE)
        self.assertTrue(any("override active" in reason.lower() for reason in result.reasons))
        
    def test_get_governor_status(self):
        """Test governor status reporting"""
        status = self.risk_governor.get_governor_status()
        
        self.assertIn('enabled', status)
        self.assertIn('override_active', status)
        self.assertIn('total_rules', status)
        self.assertIn('stats', status)
        self.assertIn('rules', status)


class TestSystemArming(unittest.TestCase):
    """Test SystemArming functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_manager = StateManager(self.temp_dir)
        
        self.capital_params = CapitalParameters(
            total_capital=100000.0,
            max_position_value=20000.0,
            daily_loss_limit=5000.0,
            max_positions=5
        )
        
        self.trade_params = TradeParameters(
            sl_atr_mult=2.0,
            target_atr_mult=3.0,
            position_size_pct=0.02
        )
        
        self.risk_manager = RiskManager(
            self.capital_params,
            self.trade_params,
            self.state_manager
        )
        
        self.system_arming = SystemArming(self.risk_manager, self.state_manager)
        
    def tearDown(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        # Clean up any emergency stop files
        if os.path.exists("EMERGENCY_STOP.txt"):
            os.remove("EMERGENCY_STOP.txt")
            
        # Clean up state files
        if os.path.exists("state/armed_state.json"):
            os.remove("state/armed_state.json")
    
    def test_system_arming_initialization(self):
        """Test SystemArming initializes correctly"""
        self.assertIsNotNone(self.system_arming)
        self.assertEqual(self.system_arming.status, ArmingStatus.DISARMED)
        self.assertGreater(len(self.system_arming.kill_switches), 0)
        
    def test_arm_system_success(self):
        """Test successful system arming"""
        # Create required directories
        os.makedirs('config', exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        
        # Create mock config files
        with open('config/trading_config.yaml', 'w') as f:
            f.write('# Mock config')
        with open('config/broker.yaml', 'w') as f:
            f.write('# Mock config')
        with open('config/timing_config.yaml', 'w') as f:
            f.write('# Mock config')
        
        try:
            result = self.system_arming.arm_system()
            
            # Should succeed with mock setup
            self.assertEqual(result.status, ArmingStatus.ARMED)
            self.assertTrue(result.all_critical_checks_passed)
            self.assertIsNotNone(result.armed_at)
            
        finally:
            # Cleanup
            for file in ['config/trading_config.yaml', 'config/broker.yaml', 'config/timing_config.yaml']:
                if os.path.exists(file):
                    os.remove(file)
    
    def test_arm_system_emergency_stop_failure(self):
        """Test arming failure due to emergency stop"""
        # Create emergency stop file
        with open("EMERGENCY_STOP.txt", "w") as f:
            f.write("Test emergency stop")
        
        result = self.system_arming.arm_system()
        
        self.assertEqual(result.status, ArmingStatus.FAILED)
        self.assertFalse(result.all_critical_checks_passed)
        self.assertGreater(len(result.failed_checks), 0)
        
    def test_emergency_stop_activation(self):
        """Test emergency stop activation"""
        self.system_arming.emergency_stop("Test emergency")
        
        self.assertEqual(self.system_arming.status, ArmingStatus.EMERGENCY_STOP)
        self.assertTrue(self.system_arming.manual_emergency_stop)
        self.assertTrue(os.path.exists("EMERGENCY_STOP.txt"))
        
    def test_emergency_stop_reset(self):
        """Test emergency stop reset"""
        # Activate emergency stop first
        self.system_arming.emergency_stop("Test emergency")
        
        # Reset with correct authorization
        success = self.system_arming.reset_emergency_stop("RESET_EMERGENCY")
        
        self.assertTrue(success)
        self.assertEqual(self.system_arming.status, ArmingStatus.DISARMED)
        self.assertFalse(self.system_arming.manual_emergency_stop)
        self.assertFalse(os.path.exists("EMERGENCY_STOP.txt"))
        
    def test_emergency_stop_reset_wrong_auth(self):
        """Test emergency stop reset with wrong authorization"""
        # Activate emergency stop first
        self.system_arming.emergency_stop("Test emergency")
        
        # Try to reset with wrong authorization
        success = self.system_arming.reset_emergency_stop("WRONG_CODE")
        
        self.assertFalse(success)
        self.assertEqual(self.system_arming.status, ArmingStatus.EMERGENCY_STOP)
        self.assertTrue(os.path.exists("EMERGENCY_STOP.txt"))
        
    def test_check_armed_status(self):
        """Test armed status checking"""
        # Initially disarmed
        self.assertFalse(self.system_arming.check_armed_status())
        
        # Manually set to armed for testing
        self.system_arming.status = ArmingStatus.ARMED
        self.system_arming.armed_at = datetime.now()
        
        # Should return True if no critical failures
        status = self.system_arming.check_armed_status()
        # Status depends on kill switch results
        self.assertIsInstance(status, bool)
        
    def test_get_arming_status(self):
        """Test arming status reporting"""
        status = self.system_arming.get_arming_status()
        
        self.assertIn('status', status)
        self.assertIn('manual_emergency_stop', status)
        self.assertIn('auto_disarm_enabled', status)
        self.assertIn('kill_switches', status)
        
        # Kill switches should have proper structure
        for switch in status['kill_switches']:
            self.assertIn('name', switch)
            self.assertIn('passed', switch)
            self.assertIn('critical', switch)


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete risk management system"""
    
    def setUp(self):
        """Set up integration test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_manager = StateManager(self.temp_dir)
        
        self.capital_params = CapitalParameters(
            total_capital=100000.0,
            max_position_value=20000.0,
            daily_loss_limit=5000.0,
            max_positions=5
        )
        
        self.trade_params = TradeParameters(
            sl_atr_mult=2.0,
            target_atr_mult=3.0,
            position_size_pct=0.02
        )
        
        # Initialize all components
        self.risk_manager = RiskManager(
            self.capital_params,
            self.trade_params,
            self.state_manager
        )
        
        self.risk_governor = RiskGovernor(self.risk_manager, self.state_manager)
        self.system_arming = SystemArming(self.risk_manager, self.state_manager)
        
    def tearDown(self):
        """Clean up integration test environment"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        # Clean up any emergency stop files
        if os.path.exists("EMERGENCY_STOP.txt"):
            os.remove("EMERGENCY_STOP.txt")
    
    def test_complete_workflow(self):
        """Test complete risk management workflow"""
        # 1. Create a test signal and order
        signal = ScreenerSignal(
            symbol="RELIANCE.NS",
            trend="BULLISH",
            score=75.0,
            current_price=2500.0,
            volume=1000000,
            timestamp=datetime.now()
        )
        
        order = Order(
            symbol="RELIANCE.NS",
            side=OrderSide.BUY,
            quantity=5,
            price=2500.0,
            order_type=OrderType.LIMIT,
            product=ProductType.MIS
        )
        
        # 2. Risk Manager assessment
        risk_assessment = self.risk_manager.assess_trade_risk(signal, order, [])
        self.assertIsInstance(risk_assessment, RiskAssessment)
        
        # 3. Risk Governor approval  
        governor_result = self.risk_governor.approve_trade(signal, order, [])
        self.assertIsInstance(governor_result.decision, GovernorDecision)
        
        # 4. System should be functional
        risk_status = self.risk_manager.get_risk_status()
        self.assertIsInstance(risk_status, dict)
        
        governor_status = self.risk_governor.get_governor_status()
        self.assertIsInstance(governor_status, dict)
        
        arming_status = self.system_arming.get_arming_status()
        self.assertIsInstance(arming_status, dict)


if __name__ == '__main__':
    # Create test directories if they don't exist
    os.makedirs('config', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    os.makedirs('state', exist_ok=True)
    
    # Run the tests
    unittest.main(verbosity=2)