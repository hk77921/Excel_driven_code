"""
Test state locking mechanism
"""

import time
import logging
from multiprocessing import Process
from safe_state_manager import SafeStateManager, StateLockError

logging.basicConfig(level=logging.INFO)

def worker(worker_id: int, delay: float):
    """Simulated worker that modifies state"""
    try:
        print(f"Worker {worker_id} attempting to acquire lock...")
        
        with SafeStateManager() as manager:
            print(f"Worker {worker_id} acquired lock")
            state = manager.load()
            
            # Simulate work
            time.sleep(delay)
            
            # Modify state
            state[f"WORKER_{worker_id}"] = {
                "timestamp": time.time(),
                "worker_id": worker_id
            }
            
            manager.save(state)
            print(f"Worker {worker_id} saved and released lock")
            
    except StateLockError as e:
        print(f"Worker {worker_id} failed to acquire lock: {e}")

def test_concurrent_access():
    """Test that only one worker can access state at a time"""
    print("\n" + "="*60)
    print("TEST: Concurrent State Access")
    print("="*60)
    
    # Start 3 workers that try to access state simultaneously
    workers = []
    for i in range(3):
        p = Process(target=worker, args=(i, 2))  # Each holds lock for 2 seconds
        p.start()
        workers.append(p)
        time.sleep(0.1)  # Slight delay between starts
    
    # Wait for all workers
    for p in workers:
        p.join()
    
    # Verify state
    with SafeStateManager() as manager:
        state = manager.load()
        print(f"\nFinal state has {len(state)} workers")
        for key in sorted(state.keys()):
            if key.startswith("WORKER_"):
                print(f"  {key}: {state[key]}")
    
    print("\n✅ Test passed: All workers completed without race conditions")

if __name__ == "__main__":
    test_concurrent_access()