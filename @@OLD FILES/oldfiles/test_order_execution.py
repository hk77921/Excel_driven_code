"""Test order execution with paper trading"""
import os
os.environ["MODE"] = "PAPER"

from execution_engine import place_order, poll_orders, rate_limiter
import time

def test_rate_limiter():
    """Test rate limiting works"""
    print("Testing rate limiter (should take ~1 second)...")
    start = time.time()
    for i in range(10):
        rate_limiter.wait_if_needed()
    elapsed = time.time() - start
    print(f"✓ Rate limiter OK: {elapsed:.2f}s elapsed")
    assert elapsed >= 0.9, "Rate limiter not working"

def test_place_order():
    """Test order placement"""
    print("\nTesting order placement...")
    order_id = place_order("RELIANCE", 5, "BUY")
    assert order_id is not None, "Order placement failed"
    print(f"✓ Order placed: {order_id}")
    return order_id

def test_poll_orders(order_id):
    """Test order polling"""
    print("\nTesting order polling...")
    pending = {
        order_id: {
            "order_id": order_id,
            "symbol": "RELIANCE",
            "side": "BUY",
            "req_qty": 5,
            "price": 2500.0,
            "atr": 50.0,
            "sl": 2450.0,
            "reason": "TEST",
            "time": "2025-12-24T22:00:00"
        }
    }
    
    updates = poll_orders(pending)
    assert order_id in updates, "Order not found in poll results"
    status, qty, price = updates[order_id]
    print(f"✓ Order status: {status}, Qty: {qty}, Price: {price}")
    assert status == "COMPLETE", f"Expected COMPLETE, got {status}"

if __name__ == "__main__":
    print("=" * 60)
    print("ORDER EXECUTION TESTS")
    print("=" * 60)
    
    try:
        test_rate_limiter()
        oid = test_place_order()
        test_poll_orders(oid)
        
        print("\n" + "=" * 60)
        print(" ALL TESTS PASSED")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n TEST FAILED: {e}")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
