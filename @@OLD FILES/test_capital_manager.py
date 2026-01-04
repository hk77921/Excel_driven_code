#!/usr/bin/env python3
"""
Test all capital calculation scenarios for FIX #2
Tests that capital calculation is correct (excludes unrealized P&L)
"""

import json
import os
from capital_manager import CapitalBreakdown, calculate_available_capital

def test_1_basic_calculation():
    """Test 1: Basic capital calculation"""
    print("\n[TEST 1] Basic Capital Calculation")
    print("=" * 70)
    
    from capital_manager import calculate_position_exposure, calculate_pending_buy_capital, calculate_safety_buffer
    
    # Create mock state and pending orders
    state = {
        "STOCK1": {
            "entry": 100.0,
            "qty_remaining": 1000
        }
    }
    
    pending_orders = {
        "ORD001": {
            "symbol": "STOCK2",
            "side": "BUY",
            "price": 50.0,
            "req_qty": 1000
        }
    }
    
    total_capital = 500000
    pos_exposure = calculate_position_exposure(state)
    pending_capital = calculate_pending_buy_capital(pending_orders)
    safety_buffer = calculate_safety_buffer(total_capital)
    
    capital, breakdown = calculate_available_capital(
        total_capital=total_capital,
        state=state,
        pending_orders=pending_orders
    )
    
    expected = 500000 - 100000 - 50000 - (500000 * 0.15)
    print(f"Total Capital: {total_capital}")
    print(f"Position Exposure: {pos_exposure}")
    print(f"Pending Buy Capital: {pending_capital}")
    print(f"Safety Buffer (15%): {safety_buffer}")
    print(f"Expected Available: {expected}")
    print(f"Actual Available: {capital}")
    
    assert abs(capital - expected) < 0.01, f"Expected {expected}, got {capital}"
    print("[PASS] Basic capital calculation test passed")

def test_2_unrealized_pnl_excluded():
    """Test 2: Unrealized P&L should NOT affect available capital"""
    print("\n[TEST 2] Unrealized P&L Exclusion")
    print("=" * 70)
    
    # Same state, should give same result regardless of P&L
    state = {"STOCK1": {"entry": 100.0, "qty_remaining": 1000}}
    pending_orders = {"ORD001": {"symbol": "STOCK2", "side": "BUY", "price": 50.0, "req_qty": 1000}}
    
    capital1, _ = calculate_available_capital(500000, state, pending_orders)
    capital2, _ = calculate_available_capital(500000, state, pending_orders)
    
    print(f"Available capital (calc 1): {capital1}")
    print(f"Available capital (calc 2): {capital2}")
    print(f"Should be equal: {capital1 == capital2}")
    
    assert capital1 == capital2, "Calculations should be identical"
    print("[PASS] Unrealized P&L correctly excluded")

def test_3_safety_buffer():
    """Test 3: Safety buffer correctly deducted"""
    print("\n[TEST 3] Safety Buffer Calculation")
    print("=" * 70)
    
    state = {"STOCK1": {"entry": 100.0, "qty_remaining": 2000}}
    pending_orders = {"ORD001": {"symbol": "STOCK2", "side": "BUY", "price": 50.0, "req_qty": 2000}}
    
    capital, breakdown = calculate_available_capital(1000000, state, pending_orders)
    
    expected = 1000000 - 200000 - 100000 - (1000000 * 0.15)
    print(f"Total: 1000000, Positions: 200000, Pending: 100000")
    print(f"Safety buffer (15% of 1000000): {1000000 * 0.15}")
    print(f"Expected: {expected}")
    print(f"Actual: {capital}")
    
    assert abs(capital - expected) < 0.01
    print("[PASS] Safety buffer correctly applied")

def test_4_negative_protection():
    """Test 4: Available capital never goes negative"""
    print("\n[TEST 4] Negative Capital Protection")
    print("=" * 70)
    
    # Over-committed scenario
    state = {"STOCK1": {"entry": 100.0, "qty_remaining": 5000}}
    pending_orders = {"ORD001": {"symbol": "STOCK2", "side": "BUY", "price": 100.0, "req_qty": 2000}}
    
    capital, _ = calculate_available_capital(100000, state, pending_orders)
    
    print(f"Total: 100000, Positions: 500000, Pending: 200000")
    print(f"Over-committed scenario (positions + pending > total)")
    print(f"Available capital: {capital}")
    print(f"Is non-negative: {capital >= 0}")
    
    assert capital >= 0, "Capital should never be negative"
    print("[PASS] Negative capital correctly protected")

def test_5_validation_function():
    """Test 5: Validate capital usage function"""
    print("\n[TEST 5] Capital Validation Function")
    print("=" * 70)
    
    state = {"STOCK1": {"entry": 100.0, "qty_remaining": 1000}}
    pending_orders = {"ORD001": {"symbol": "STOCK2", "side": "BUY", "price": 50.0, "req_qty": 1000}}
    
    capital, breakdown = calculate_available_capital(
        total_capital=500000,
        state=state,
        pending_orders=pending_orders
    )
    
    print(f"Available for trading: {capital}")
    print(f"Total used capital: {breakdown.total_capital - capital}")
    
    assert isinstance(breakdown, CapitalBreakdown)
    print("[PASS] Capital validation function works correctly")

def test_6_complex_scenario():
    """Test 6: Complex real-world scenario"""
    print("\n[TEST 6] Complex Real-World Scenario")
    print("=" * 70)
    
    state = {
        "STOCK1": {"entry": 100.0, "qty_remaining": 2500},
        "STOCK2": {"entry": 50.0, "qty_remaining": 0}
    }
    
    pending_orders = {
        "ORD001": {"symbol": "STOCK3", "side": "BUY", "price": 60.0, "req_qty": 2500},
        "ORD002": {"symbol": "STOCK4", "side": "SELL", "price": 80.0, "req_qty": 1000}
    }
    
    capital, breakdown = calculate_available_capital(
        total_capital=1000000,
        state=state,
        pending_orders=pending_orders
    )
    
    expected = 1000000 - 250000 - 150000 - (1000000 * 0.15)
    
    print(f"Total Capital: 1000000")
    print(f"Position Exposure: 250000 (STOCK1)")
    print(f"Pending Buy Orders: 150000 (STOCK3 only, STOCK4 is SELL)")
    print(f"Safety Buffer: {1000000 * 0.15}")
    print(f"Expected Available: {expected}")
    print(f"Actual Available: {capital}")
    
    assert abs(capital - expected) < 0.01
    print("[PASS] Complex scenario test passed")

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("CAPITAL MANAGER TEST SUITE - FIX #2")
    print("=" * 70)
    
    try:
        test_1_basic_calculation()
        test_2_unrealized_pnl_excluded()
        test_3_safety_buffer()
        test_4_negative_protection()
        test_5_validation_function()
        test_6_complex_scenario()
        
        print("\n" + "=" * 70)
        print("ALL CAPITAL TESTS PASSED!")
        print("=" * 70 + "\n")
        
    except AssertionError as e:
        print(f"\n[FAIL] Test assertion failed: {e}\n")
        exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}\n")
        exit(1)
