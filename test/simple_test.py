"""
Simple Test Runner for Excel-Driven Trading Bot
==============================================

ASCII-only test runner that avoids Unicode encoding issues.
"""

import os
import sys
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_basic_imports():
    """Test that core modules can be imported"""
    print("Testing basic imports...")
    
    try:
        from src.core.models import CapitalParameters, TradeParameters
        from src.core.state_manager import StateManager
        from src.core.capital_manager import CapitalManager
        print("PASS: Basic imports successful")
        return True
    except Exception as e:
        print(f"FAIL: Import failed - {e}")
        return False

def test_parameter_creation():
    """Test parameter object creation"""
    print("Testing parameter creation...")
    
    try:
        from src.core.models import CapitalParameters, TradeParameters
        
        cap_params = CapitalParameters(
            total_capital=100000,
            max_open_positions=5,
            risk_per_trade=0.02
        )
        
        trade_params = TradeParameters(
            sl_atr_mult=2.0,
            target_atr_mult=3.0
        )
        
        print("PASS: Parameter creation successful")
        return True
    except Exception as e:
        print(f"FAIL: Parameter creation failed - {e}")
        return False

def test_capital_manager():
    """Test capital manager functionality"""
    print("Testing capital manager...")
    
    try:
        from src.core.models import CapitalParameters
        from src.core.capital_manager import CapitalManager
        
        cap_params = CapitalParameters(
            total_capital=100000,
            max_open_positions=5,
            risk_per_trade=0.02
        )
        
        cap_mgr = CapitalManager(cap_params)
        
        # Test position sizing
        position_size = cap_mgr.calculate_position_size(
            entry_price=1000.0,
            stop_loss=900.0
        )
        
        if position_size > 0:
            print("PASS: Capital manager functionality works")
            return True
        else:
            print("FAIL: Invalid position size calculated")
            return False
            
    except Exception as e:
        print(f"FAIL: Capital manager test failed - {e}")
        return False

def test_state_management():
    """Test state manager functionality"""
    print("Testing state management...")
    
    try:
        from src.core.state_manager import StateManager
        
        # Use temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            state_mgr = StateManager(temp_dir)
            
            # Test basic state operations
            test_position = {
                "symbol": "TEST",
                "quantity": 100,
                "qty_remaining": 100,
                "entry_price": 1000.0,
                "stop_loss": 900.0,
                "status": "OPEN"
            }
            
            state_mgr.add_position("TEST", test_position)
            positions = state_mgr.load_positions()
            
            if "TEST" in positions:
                print("PASS: State management works")
                return True
            else:
                print("FAIL: Position not saved properly")
                return False
                
    except Exception as e:
        print(f"FAIL: State management test failed - {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("EXCEL-DRIVEN TRADING BOT - SIMPLE TEST SUITE")
    print("=" * 60)
    
    tests = [
        ("Basic Imports", test_basic_imports),
        ("Parameter Creation", test_parameter_creation),
        ("Capital Manager", test_capital_manager),
        ("State Management", test_state_management)
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\nRunning: {test_name}")
        print("-" * 40)
        
        if test_func():
            passed += 1
        else:
            failed += 1
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {passed/(passed+failed)*100:.1f}%")
    
    if failed == 0:
        print("\nALL TESTS PASSED!")
        return 0
    else:
        print(f"\n{failed} TESTS FAILED!")
        return 1

if __name__ == "__main__":
    sys.exit(main())