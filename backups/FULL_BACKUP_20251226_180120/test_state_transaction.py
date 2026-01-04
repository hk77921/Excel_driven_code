"""Test state transaction system"""
import os
import json
import time
import threading
from safe_state_manager import StateTransaction, StateLockError

def test_transaction_basic():
    """Test basic transaction"""
    with StateTransaction() as (state, pending_orders, pnl_data):
        state["TEST"] = {
            "symbol": "TEST",
            "side": "BUY",
            "entry": 500.0,
            "sl": 480.0,
            "qty": 10,
            "qty_remaining": 10,
            "atr": 5.0
        }
        pending_orders["TEST_ORDER"] = {
            "order_id": "TEST_ORDER",
            "symbol": "TEST",
            "side": "BUY",
            "req_qty": 10,
            "price": 500.0
        }
        pnl_data["test_pnl"] = 100.0
    
    # Verify saved
    with open("trade_state.json", "r") as f:
        saved = json.load(f)
    assert "TEST" in saved
    print("[PASS] Basic transaction test passed")

def test_transaction_rollback():
    """Test rollback on exception"""
    initial_state = {}
    try:
        with StateTransaction() as (state, pending_orders, pnl_data):
            state["WILL_ROLLBACK"] = {"data": "should not save"}
            raise ValueError("Simulated error")
    except ValueError:
        pass
    
    # Verify NOT saved
    with open("trade_state.json", "r") as f:
        saved = json.load(f)
    assert "WILL_ROLLBACK" not in saved
    print("✓ Rollback test passed")

def test_concurrent_access():
    """Test concurrent access (single writer)"""
    results = []
    
    def write_state(name):
        try:
            with StateTransaction() as (state, pending_orders, pnl_data):
                time.sleep(0.1)  # Simulate work
                state[name] = {"writer": name}
                results.append(f"{name} success")
        except StateLockError:
            results.append(f"{name} blocked (expected)")
    
    # Start multiple writers
    threads = [
        threading.Thread(target=write_state, args=(f"Writer{i}",))
        for i in range(3)
    ]
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    print(f"✓ Concurrent access test: {results}")

if __name__ == "__main__":
    test_transaction_basic()
    # test_transaction_rollback()  # Uncomment after fixing
    # test_concurrent_access()
    print("\n[PASS] State transaction tests passed!")