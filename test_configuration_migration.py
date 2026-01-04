#!/usr/bin/env python3
"""
Configuration Migration Test Suite
=================================

Comprehensive test suite to validate the new centralized configuration system
and ensure backward compatibility with existing code.

This test suite validates:
1. Enhanced configuration manager functionality
2. Backward compatibility with existing ConfigManager
3. Environment variable overrides
4. Configuration validation
5. All configuration file loading
6. Type safety and error handling

Usage:
    python test_configuration_migration.py
    python test_configuration_migration.py --verbose
    python test_configuration_migration.py --environment testing
"""

import sys
import os
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Test imports
try:
    from config.enhanced_config_manager import (
        EnhancedConfigManager, 
        create_config_manager,
        ConfigManager,  # Backward compatibility alias
        LoggingConfiguration,
        BrokerConfiguration, 
        EnvironmentConfiguration,
        UniverseConfiguration,
        MonitoringConfiguration,
        ConfigurationError
    )
    from src.core import TradeParameters, CapitalParameters
    print("✅ All imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)


class ConfigurationMigrationTestSuite(unittest.TestCase):
    """Comprehensive test suite for configuration migration"""
    
    def setUp(self):
        """Set up test environment with temporary config directory"""
        # Create temporary directory for test configs
        self.test_dir = tempfile.mkdtemp()
        self.config_dir = os.path.join(self.test_dir, 'config')
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Store original environment variables
        self.original_env = os.environ.copy()
        
        print(f"\nTest setup: Using temporary config dir: {self.config_dir}")
    
    def tearDown(self):
        """Clean up test environment"""
        # Restore original environment
        os.environ.clear()
        os.environ.update(self.original_env)
        
        # Clean up temporary directory
        shutil.rmtree(self.test_dir)
        print(f"Test cleanup: Removed {self.test_dir}")
    
    def test_enhanced_config_manager_initialization(self):
        """Test basic initialization of enhanced config manager"""
        print("\n🔍 Testing Enhanced Config Manager Initialization...")
        
        config_mgr = EnhancedConfigManager(config_dir=self.config_dir)
        
        self.assertIsInstance(config_mgr, EnhancedConfigManager)
        self.assertEqual(str(config_mgr.config_dir), self.config_dir)
        self.assertIn(config_mgr.environment, ['development', 'testing', 'production'])
        self.assertIn(config_mgr.execution_mode, ['PAPER', 'LIVE', 'BACKTEST'])
        
        print("✅ Enhanced config manager initialization test passed")
    
    def test_backward_compatibility_alias(self):
        """Test backward compatibility with old ConfigManager"""
        print("\n🔍 Testing Backward Compatibility...")
        
        # Test that ConfigManager alias works
        config_mgr = ConfigManager(config_dir=self.config_dir)
        
        self.assertIsInstance(config_mgr, EnhancedConfigManager)
        
        # Test that all old methods still work
        config_mgr.create_default_configs()
        
        capital_params = config_mgr.get_capital_parameters()
        self.assertIsInstance(capital_params, CapitalParameters)
        
        trade_params = config_mgr.get_trade_parameters()
        self.assertIsInstance(trade_params, TradeParameters)
        
        trading_config = config_mgr.load_trading_config()
        self.assertIsInstance(trading_config, dict)
        
        print("✅ Backward compatibility test passed")
    
    def test_configuration_data_classes(self):
        """Test configuration data classes and their defaults"""
        print("\n🔍 Testing Configuration Data Classes...")
        
        # Test LoggingConfiguration
        log_config = LoggingConfiguration()
        self.assertEqual(log_config.level, "INFO")
        self.assertTrue(log_config.unicode_support)
        
        # Test BrokerConfiguration  
        broker_config = BrokerConfiguration()
        self.assertEqual(broker_config.name, "zerodha")
        self.assertEqual(broker_config.product_type, "MIS")
        
        # Test EnvironmentConfiguration
        env_config = EnvironmentConfiguration()
        self.assertEqual(env_config.execution_mode, "PAPER")
        self.assertEqual(env_config.excel_file, "MiniRobo.xlsx")
        
        # Test UniverseConfiguration
        universe_config = UniverseConfiguration()
        self.assertEqual(universe_config.max_gainers, 10)
        self.assertEqual(universe_config.min_gap_percentage, 2.0)
        
        # Test MonitoringConfiguration
        monitoring_config = MonitoringConfiguration()
        self.assertTrue(monitoring_config.track_performance)
        self.assertEqual(monitoring_config.performance_window_days, 30)
        
        print("✅ Configuration data classes test passed")
    
    def test_default_config_creation(self):
        """Test creation of default configuration files"""
        print("\n🔍 Testing Default Config File Creation...")
        
        config_mgr = create_config_manager(config_dir=self.config_dir)
        
        # Check that all expected config files were created
        expected_files = [
            'trading_config.yaml',
            'symbols.yaml', 
            'rules.yaml',
            'environment.yaml',
            'logging.yaml',
            'broker.yaml',
            'monitoring.yaml'
        ]
        
        for filename in expected_files:
            file_path = os.path.join(self.config_dir, filename)
            self.assertTrue(os.path.exists(file_path), f"Missing config file: {filename}")
        
        print("✅ Default config creation test passed")
    
    def test_environment_variable_overrides(self):
        """Test environment variable override functionality"""
        print("\n🔍 Testing Environment Variable Overrides...")
        
        # Set test environment variables
        os.environ['EXECUTION_MODE'] = 'LIVE'
        os.environ['TRADING_CAPITAL'] = '15000'
        os.environ['LOG_LEVEL'] = 'DEBUG'
        os.environ['KITE_API_KEY'] = 'test_api_key'
        os.environ['KITE_ACCESS_TOKEN'] = 'test_access_token'
        
        config_mgr = create_config_manager(config_dir=self.config_dir)
        
        # Test environment configuration overrides
        env_config = config_mgr.get_environment_configuration()
        self.assertEqual(env_config.execution_mode, 'LIVE')
        
        # Test capital parameter overrides
        capital_params = config_mgr.get_capital_parameters()
        self.assertEqual(capital_params.total_capital, 15000.0)
        
        # Test logging configuration overrides
        log_config = config_mgr.get_logging_configuration()
        self.assertEqual(log_config.level, 'DEBUG')
        
        # Test broker configuration overrides
        broker_config = config_mgr.get_broker_configuration()
        self.assertEqual(broker_config.api_key, 'test_api_key')
        self.assertEqual(broker_config.access_token, 'test_access_token')
        
        print("✅ Environment variable overrides test passed")
    
    def test_configuration_validation(self):
        """Test configuration validation functionality"""
        print("\n🔍 Testing Configuration Validation...")
        
        config_mgr = create_config_manager(config_dir=self.config_dir)
        
        # Test valid configuration
        issues = config_mgr.validate_configuration()
        self.assertIsInstance(issues, list)
        
        # Test invalid configuration (negative capital)
        with patch.object(config_mgr, 'get_capital_parameters') as mock_capital:
            invalid_capital = CapitalParameters(
                total_capital=-1000,  # Invalid negative capital
                risk_per_trade=0.005,
                max_daily_loss_pct=0.02,
                max_open_positions=5,
                max_per_sector=2,
                safety_buffer_pct=0.15
            )
            mock_capital.return_value = invalid_capital
            
            issues = config_mgr.validate_configuration()
            self.assertTrue(len(issues) > 0)
            self.assertTrue(any('capital must be positive' in issue for issue in issues))
        
        print("✅ Configuration validation test passed")
    
    def test_live_mode_validation(self):
        """Test validation requirements for LIVE trading mode"""
        print("\n🔍 Testing LIVE Mode Validation...")
        
        # Clear any existing credentials first
        if 'KITE_API_KEY' in os.environ:
            del os.environ['KITE_API_KEY']
        if 'KITE_ACCESS_TOKEN' in os.environ:
            del os.environ['KITE_ACCESS_TOKEN']
        
        # Test LIVE mode without credentials (should fail)
        os.environ['EXECUTION_MODE'] = 'LIVE'
        
        # Create config manager after setting environment (don't load .env file)
        config_mgr = EnhancedConfigManager(config_dir=self.config_dir, load_env_file=False)
        
        with self.assertRaises(ConfigurationError) as context:
            config_mgr.get_broker_configuration()
        
        self.assertIn('LIVE trading mode requires', str(context.exception))
        
        # Test LIVE mode with credentials (should pass)
        os.environ['KITE_API_KEY'] = 'test_key'
        os.environ['KITE_ACCESS_TOKEN'] = 'test_token'
        
        # Create new config manager after setting credentials
        config_mgr2 = EnhancedConfigManager(config_dir=self.config_dir, load_env_file=False)
        broker_config = config_mgr2.get_broker_configuration()
        
        self.assertEqual(broker_config.api_key, 'test_key')
        self.assertEqual(broker_config.access_token, 'test_token')
        
        print("✅ LIVE mode validation test passed")
    
    def test_configuration_export_import(self):
        """Test configuration export functionality"""
        print("\n🔍 Testing Configuration Export/Import...")
        
        config_mgr = create_config_manager(config_dir=self.config_dir)
        
        # Test configuration export
        export_file = os.path.join(self.test_dir, 'test_config_export.json')
        exported_file = config_mgr.export_configuration(export_file)
        
        self.assertEqual(exported_file, export_file)
        self.assertTrue(os.path.exists(export_file))
        
        # Verify export file content
        import json
        with open(export_file, 'r') as f:
            config_data = json.load(f)
        
        self.assertIn('metadata', config_data)
        self.assertIn('environment', config_data)
        self.assertIn('logging', config_data)
        self.assertIn('broker', config_data)
        self.assertEqual(config_data['metadata']['config_version'], '2.0')
        
        print("✅ Configuration export/import test passed")
    
    def test_all_configuration_methods(self):
        """Test all configuration getter methods"""
        print("\n🔍 Testing All Configuration Getter Methods...")
        
        config_mgr = create_config_manager(config_dir=self.config_dir)
        
        # Test all new configuration methods
        env_config = config_mgr.get_environment_configuration()
        self.assertIsInstance(env_config, EnvironmentConfiguration)
        
        log_config = config_mgr.get_logging_configuration()
        self.assertIsInstance(log_config, LoggingConfiguration)
        
        broker_config = config_mgr.get_broker_configuration()
        self.assertIsInstance(broker_config, BrokerConfiguration)
        
        universe_config = config_mgr.get_universe_configuration()
        self.assertIsInstance(universe_config, UniverseConfiguration)
        
        monitoring_config = config_mgr.get_monitoring_configuration()
        self.assertIsInstance(monitoring_config, MonitoringConfiguration)
        
        # Test all existing configuration methods (backward compatibility)
        capital_params = config_mgr.get_capital_parameters()
        self.assertIsInstance(capital_params, CapitalParameters)
        
        trade_params = config_mgr.get_trade_parameters()
        self.assertIsInstance(trade_params, TradeParameters)
        
        trading_config = config_mgr.load_trading_config()
        self.assertIsInstance(trading_config, dict)
        
        timing_params = config_mgr.get_timing_parameters()
        self.assertIsInstance(timing_params, dict)
        
        symbols = config_mgr.load_symbols()
        self.assertIsInstance(symbols, dict)
        
        rules = config_mgr.load_rules()
        self.assertIsInstance(rules, dict)
        
        # Test complete configuration snapshot
        all_config = config_mgr.get_all_configurations()
        self.assertIsInstance(all_config, dict)
        self.assertIn('metadata', all_config)
        
        print("✅ All configuration getter methods test passed")
    
    def test_factory_function(self):
        """Test configuration factory function"""
        print("\n🔍 Testing Configuration Factory Function...")
        
        # Test factory function with different parameters
        config_mgr1 = create_config_manager(config_dir=self.config_dir)
        self.assertIsInstance(config_mgr1, EnhancedConfigManager)
        
        config_mgr2 = create_config_manager(
            environment='testing',
            config_dir=self.config_dir
        )
        self.assertEqual(config_mgr2.environment, 'testing')
        
        print("✅ Configuration factory function test passed")
    
    def test_configuration_reload(self):
        """Test configuration reload functionality"""
        print("\n🔍 Testing Configuration Reload...")
        
        config_mgr = create_config_manager(config_dir=self.config_dir)
        
        # Load initial configuration
        initial_capital = config_mgr.get_capital_parameters()
        
        # Force reload
        config_mgr.reload_all_configurations()
        
        # Verify reload worked (should still get same values)
        reloaded_capital = config_mgr.get_capital_parameters()
        self.assertEqual(initial_capital.total_capital, reloaded_capital.total_capital)
        
        print("✅ Configuration reload test passed")


def run_integration_tests():
    """Run integration tests with actual application components"""
    print("\n" + "="*60)
    print("RUNNING INTEGRATION TESTS")
    print("="*60)
    
    try:
        # Test integration with existing components
        print("\n🔍 Testing Integration with Main Application...")
        
        # Import main application components
        from config.enhanced_config_manager import create_config_manager
        
        # Create config manager for testing
        config_mgr = create_config_manager()
        
        # Test that configuration works with existing code
        capital_params = config_mgr.get_capital_parameters()
        trade_params = config_mgr.get_trade_parameters()
        
        print(f"  Capital: ₹{capital_params.total_capital:,.2f}")
        print(f"  Risk per trade: {capital_params.risk_per_trade*100:.1f}%")
        print(f"  Max positions: {capital_params.max_open_positions}")
        print(f"  SL multiplier: {trade_params.sl_atr_mult}x")
        print(f"  Target multiplier: {trade_params.target_atr_mult}x")
        
        print("✅ Integration tests passed")
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        return False
    
    return True


def run_performance_tests():
    """Run performance tests for configuration loading"""
    print("\n" + "="*60)
    print("RUNNING PERFORMANCE TESTS")
    print("="*60)
    
    import time
    
    try:
        print("\n🔍 Testing Configuration Loading Performance...")
        
        # Test configuration manager creation time
        start_time = time.time()
        config_mgr = create_config_manager()
        creation_time = time.time() - start_time
        
        print(f"  Config manager creation: {creation_time*1000:.2f}ms")
        
        # Test configuration loading time
        start_time = time.time()
        capital_params = config_mgr.get_capital_parameters()
        trade_params = config_mgr.get_trade_parameters()
        broker_config = config_mgr.get_broker_configuration()
        loading_time = time.time() - start_time
        
        print(f"  Configuration loading: {loading_time*1000:.2f}ms")
        
        # Test multiple config loads (should be cached)
        start_time = time.time()
        for _ in range(100):
            config_mgr.get_capital_parameters()
        cached_loading_time = time.time() - start_time
        
        print(f"  100x cached loads: {cached_loading_time*1000:.2f}ms")
        print(f"  Average per load: {cached_loading_time/100*1000:.3f}ms")
        
        # Performance assertions
        assert creation_time < 1.0, f"Config creation too slow: {creation_time:.2f}s"
        assert loading_time < 0.1, f"Config loading too slow: {loading_time:.2f}s"
        
        print("✅ Performance tests passed")
        
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        return False
    
    return True


def main():
    """Main test runner"""
    print("="*80)
    print("CONFIGURATION MIGRATION TEST SUITE")
    print("="*80)
    print("Testing centralized configuration system and backward compatibility...")
    
    # Run unit tests
    print("\n" + "="*60)
    print("RUNNING UNIT TESTS")  
    print("="*60)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(ConfigurationMigrationTestSuite)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # Check unit test results
    if not result.wasSuccessful():
        print(f"\n❌ Unit tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
        return 1
    
    print("\n✅ All unit tests passed!")
    
    # Run integration tests
    if not run_integration_tests():
        return 1
    
    # Run performance tests
    if not run_performance_tests():
        return 1
    
    # Final summary
    print("\n" + "="*80)
    print("TEST SUITE SUMMARY")
    print("="*80)
    print("✅ Unit Tests: PASSED")
    print("✅ Integration Tests: PASSED")
    print("✅ Performance Tests: PASSED")
    print("✅ Backward Compatibility: VERIFIED")
    print("✅ Environment Overrides: WORKING")
    print("✅ Configuration Validation: WORKING")
    print("\n🎉 Configuration migration is ready for deployment!")
    print("\nNext steps:")
    print("1. Review CONFIGURATION_MIGRATION_GUIDE.md")
    print("2. Update main.py to use enhanced config manager")
    print("3. Gradually migrate other modules")
    print("4. Test in your specific environment")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())