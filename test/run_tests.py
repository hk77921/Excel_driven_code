#!/usr/bin/env python3
"""
Test Runner for Excel-Driven Trading Bot
========================================

Simple test runner that can execute from the test directory.
This validates the folder structure and import paths.

Usage:
    cd test
    python run_tests.py
"""

import sys
import os
from pathlib import Path

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, parent_dir)

def test_imports():
    """Test that all core modules can be imported"""
    print("🧪 Testing module imports...")
    
    try:
        from src.core.models import CapitalParameters, TradeParameters, ScreenerSignal
        print("✅ Core models imported successfully")
        
        from src.core.state_manager import StateManager
        print("✅ State manager imported successfully")
        
        from src.core.capital_manager import CapitalManager
        print("✅ Capital manager imported successfully")
        
        from src.core.position_manager import PositionManager
        print("✅ Position manager imported successfully")
        
        # Test basic object creation
        cap_params = CapitalParameters(
            total_capital=100000,
            max_open_positions=5,
            risk_per_trade=0.02,
            max_daily_loss_pct=0.10,
            max_per_sector=2
        )
        print("✅ CapitalParameters created successfully")
        
        trade_params = TradeParameters(
            sl_atr_mult=2.0,
            target_atr_mult=3.0,
            trailing_sl_atr_mult=1.5,
            partial_exit_ratio=0.5,
            partial_exit_qty_pct=0.5
        )
        print("✅ TradeParameters created successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Import test failed: {e}")
        return False


def test_file_structure():
    """Test that the file structure is correct"""
    print("🧪 Testing file structure...")
    
    parent_dir = Path(__file__).parent.parent
    
    # Check required directories
    required_dirs = ['src', 'test', 'json', 'config', 'docs', 'logs']
    for dir_name in required_dirs:
        dir_path = parent_dir / dir_name
        if dir_path.exists():
            print(f"✅ {dir_name}/ directory exists")
        else:
            print(f"❌ {dir_name}/ directory missing")
            return False
    
    # Check key files
    required_files = [
        'main.py',
        'requirements.txt',
        'config/default_config.json'
    ]
    
    for file_path in required_files:
        full_path = parent_dir / file_path
        if full_path.exists():
            print(f"✅ {file_path} exists")
        else:
            print(f"❌ {file_path} missing")
            return False
    
    return True


def test_json_files():
    """Test that JSON files are accessible"""
    print("🧪 Testing JSON file access...")
    
    parent_dir = Path(__file__).parent.parent
    json_dir = parent_dir / 'json'
    
    if not json_dir.exists():
        print("❌ json/ directory not found")
        return False
    
    json_files = list(json_dir.glob('*.json'))
    if json_files:
        print(f"✅ Found {len(json_files)} JSON files in json/ directory")
        for json_file in json_files[:3]:  # Show first 3
            print(f"   📄 {json_file.name}")
    else:
        print("⚠️  No JSON files found in json/ directory")
    
    return True


def run_basic_functionality_test():
    """Run a basic functionality test without external dependencies"""
    print("🧪 Testing basic functionality...")
    
    try:
        from src.core.models import CapitalParameters, TradeParameters
        from src.core.capital_manager import CapitalManager
        
        # Test capital management
        cap_params = CapitalParameters(
            total_capital=100000,
            max_open_positions=5,
            risk_per_trade=0.02,
            max_daily_loss_pct=0.10,
            max_per_sector=2
        )
        
        cap_mgr = CapitalManager(cap_params)
        
        # Test position sizing
        entry_price = 1000.0
        stop_loss = 900.0  # 10% stop loss
        position_size = cap_mgr.calculate_position_size(
            entry_price=entry_price,
            stop_loss=stop_loss
        )
        
        if position_size > 0:
            print(f"✅ Position sizing calculation: {position_size} shares")
        else:
            print("❌ Position sizing failed")
            return False
        
        # Test capital allocation
        allocation = cap_mgr.calculate_available_capital(positions={}, pending_orders={})
        if allocation > 0:
            print(f"✅ Capital allocation: ₹{allocation:,.2f}")
        else:
            print("❌ Capital allocation failed")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Functionality test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("🤖 EXCEL-DRIVEN TRADING BOT - TEST SUITE")
    print("=" * 60)
    print(f"📁 Running from: {Path(__file__).parent}")
    print(f"📂 Parent directory: {Path(__file__).parent.parent}")
    print("=" * 60)
    
    tests = [
        ("File Structure", test_file_structure),
        ("Module Imports", test_imports),
        ("JSON Files", test_json_files),
        ("Basic Functionality", run_basic_functionality_test)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name} Test")
        print("-" * 40)
        
        if test_func():
            print(f"✅ {test_name} test PASSED")
            passed += 1
        else:
            print(f"❌ {test_name} test FAILED")
    
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"Passed: {passed}/{total}")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED - Structure is correct!")
        return True
    else:
        print("❌ Some tests failed - Check the issues above")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)