#!/usr/bin/env python3
"""
Integration test runner for critical fixes (FIX #1 and FIX #2)

Tests the two critical fixes:
- FIX #1: State manager with atomic transactions and proper locking
- FIX #2: Capital manager with correct capital calculation formula
"""

import subprocess
import sys
from pathlib import Path

def run_test_suite(test_file, suite_name):
    """Run a single test file and report results"""
    print(f"\n{'='*70}")
    print(f"Running {suite_name}")
    print(f"{'='*70}\n")
    
    try:
        result = subprocess.run(
            [sys.executable, str(test_file)],
            cwd=str(test_file.parent),
            capture_output=True,
            text=True,
            timeout=30
        )
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] {suite_name} took too long to run")
        return False
    except Exception as e:
        print(f"[ERROR] Failed to run {suite_name}: {e}")
        return False

def main():
    """Run all critical fix tests"""
    test_dir = Path(__file__).parent
    
    test_files = [
        (test_dir / "test_state_transaction.py", "Test 1: State Transaction Manager"),
        (test_dir / "test_capital_manager.py", "Test 2: Capital Manager Calculations"),
    ]
    
    results = {}
    for test_file, suite_name in test_files:
        if not test_file.exists():
            print(f"[SKIP] {suite_name} - file not found: {test_file}")
            results[suite_name] = None
            continue
        
        results[suite_name] = run_test_suite(test_file, suite_name)
    
    # Print summary
    print(f"\n{'='*70}")
    print("CRITICAL FIX TEST SUMMARY")
    print(f"{'='*70}\n")
    
    all_passed = True
    for suite_name, passed in results.items():
        if passed is None:
            status = "[SKIP]"
        elif passed:
            status = "[PASS]"
        else:
            status = "[FAIL]"
            all_passed = False
        print(f"{status} {suite_name}")
    
    print(f"\n{'='*70}")
    if all_passed and all(p is not None for p in results.values()):
        print("ALL CRITICAL FIX TESTS PASSED!")
        print(f"{'='*70}\n")
        return 0
    else:
        print("SOME TESTS FAILED - Review output above")
        print(f"{'='*70}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
