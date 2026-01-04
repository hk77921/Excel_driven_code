"""
Test Transaction Manager
========================
Test the new atomic transaction system for state management.
"""

import os
import sys
import tempfile
import shutil
import json
import time
import threading
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.core.transaction_manager import StateTransaction, TransactionManager, StateLockError


class TestTransactionManager:
    """Test suite for transaction manager"""
    
    def setup_method(self):
        """Setup test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = os.path.join(self.temp_dir, "state")
        print(f"Test setup: {self.state_dir}")
        
    def teardown_method(self):
        """Cleanup test environment"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        print("Test cleanup completed")
    
    def test_basic_transaction(self):
        """Test basic transaction functionality"""
        print("Testing basic transaction...")
        
        with StateTransaction(self.state_dir) as txn:
            positions, orders, trades, daily_pnl = txn.begin()
            
            # Add test data
            positions["SBIN"] = {
                "symbol": "SBIN",
                "quantity": 100,
                "avg_price": 500.0,
                "side": "BUY"
            }
            
            orders["ORDER001"] = {
                "order_id": "ORDER001",
                "symbol": "RELIANCE",
                "side": "BUY",
                "quantity": 50,
                "price": 2500.0,
                "status": "PENDING"
            }
            
            # Commit changes
            txn.commit(positions, orders, trades, daily_pnl)
        
        # Verify data was saved
        with StateTransaction(self.state_dir) as txn:
            positions, orders, trades, daily_pnl = txn.begin()
            
            assert "SBIN" in positions
            assert positions["SBIN"]["quantity"] == 100
            assert "ORDER001" in orders
            assert orders["ORDER001"]["symbol"] == "RELIANCE"
        
        print("✅ Basic transaction test passed")
    
    def test_transaction_rollback(self):
        """Test transaction rollback on exceptions"""
        print("Testing transaction rollback...")
        
        # First, add some initial data
        with StateTransaction(self.state_dir) as txn:
            positions, orders, trades, daily_pnl = txn.begin()
            positions["INITIAL"] = {"symbol": "INITIAL", "quantity": 10, "avg_price": 100.0}
            txn.commit(positions, orders, trades, daily_pnl)
        
        # Now test rollback
        try:
            with StateTransaction(self.state_dir) as txn:
                positions, orders, trades, daily_pnl = txn.begin()
                
                # Add data that should be rolled back
                positions["ROLLBACK"] = {"symbol": "ROLLBACK", "quantity": 999, "avg_price": 999.0}
                
                # Force an exception before commit
                raise ValueError("Simulated error")
                
        except ValueError:
            pass  # Expected exception
        
        # Verify rollback worked - ROLLBACK data should not exist
        with StateTransaction(self.state_dir) as txn:
            positions, orders, trades, daily_pnl = txn.begin()
            
            assert "INITIAL" in positions  # Original data should remain
            assert "ROLLBACK" not in positions  # Rollback data should be gone
        
        print("✅ Transaction rollback test passed")
    
    def test_concurrent_access(self):
        """Test that only one transaction can be active at a time"""
        print("Testing concurrent access...")
        
        results = []
        
        def worker_thread(worker_id):
            try:
                with StateTransaction(self.state_dir) as txn:
                    positions, orders, trades, daily_pnl = txn.begin(timeout=1)  # Short timeout
                    
                    # Simulate work
                    time.sleep(0.2)
                    
                    positions[f"WORKER_{worker_id}"] = {
                        "symbol": f"WORKER_{worker_id}",
                        "quantity": worker_id,
                        "avg_price": 100.0
                    }
                    
                    txn.commit(positions, orders, trades, daily_pnl)
                    results.append(f"Worker {worker_id}: SUCCESS")
                    
            except StateLockError:
                results.append(f"Worker {worker_id}: BLOCKED (expected)")
            except Exception as e:
                results.append(f"Worker {worker_id}: ERROR - {e}")
        
        # Start multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=worker_thread, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify results
        success_count = sum(1 for r in results if "SUCCESS" in r)
        blocked_count = sum(1 for r in results if "BLOCKED" in r)
        
        print(f"Results: {results}")
        assert success_count == 1, f"Expected 1 success, got {success_count}"
        assert blocked_count == 2, f"Expected 2 blocked, got {blocked_count}"
        
        print("✅ Concurrent access test passed")
    
    def test_backup_creation(self):
        """Test that backups are created before saves"""
        print("Testing backup creation...")
        
        # Create initial state
        with StateTransaction(self.state_dir) as txn:
            positions, orders, trades, daily_pnl = txn.begin()
            positions["TEST"] = {"symbol": "TEST", "quantity": 100, "avg_price": 200.0}
            txn.commit(positions, orders, trades, daily_pnl)
        
        # Modify state (this should create backups)
        with StateTransaction(self.state_dir) as txn:
            positions, orders, trades, daily_pnl = txn.begin()
            positions["TEST"]["quantity"] = 200  # Modify existing
            txn.commit(positions, orders, trades, daily_pnl)
        
        # Check that backup directory exists and has files
        backup_dir = os.path.join(self.state_dir, "backups")
        assert os.path.exists(backup_dir), "Backup directory should exist"
        
        backup_files = os.listdir(backup_dir)
        backup_files = [f for f in backup_files if f.endswith('.bak')]
        
        print(f"Backup files created: {len(backup_files)}")
        assert len(backup_files) > 0, "Should have created backup files"
        
        print("✅ Backup creation test passed")
    
    def test_data_validation(self):
        """Test data validation during commit"""
        print("Testing data validation...")
        
        try:
            with StateTransaction(self.state_dir) as txn:
                positions, orders, trades, daily_pnl = txn.begin()
                
                # Invalid positions data (not a dict)
                invalid_positions = "not a dict"
                
                # This should raise ValueError
                txn.commit(invalid_positions, orders, trades, daily_pnl)
                
            assert False, "Should have raised validation error"
            
        except (ValueError, StateLockError) as e:
            if "must be a dictionary" in str(e) or "must be a list" in str(e):
                print("✅ Data validation test passed - caught invalid data")
            else:
                raise e
    
    def run_all_tests(self):
        """Run all tests"""
        tests = [
            self.test_basic_transaction,
            self.test_transaction_rollback, 
            self.test_concurrent_access,
            self.test_backup_creation,
            self.test_data_validation
        ]
        
        passed = 0
        total = len(tests)
        
        for test in tests:
            try:
                self.setup_method()
                test()
                passed += 1
            except Exception as e:
                print(f"❌ Test failed: {test.__name__} - {e}")
            finally:
                self.teardown_method()
                print()
        
        print(f"🎯 Test Results: {passed}/{total} passed ({passed/total*100:.1f}%)")
        return passed == total


if __name__ == "__main__":
    print("="*60)
    print("TRANSACTION MANAGER TEST SUITE")
    print("="*60)
    
    tester = TestTransactionManager()
    success = tester.run_all_tests()
    
    if success:
        print("🎉 ALL TESTS PASSED - Transaction manager is ready!")
    else:
        print("⚠️  Some tests failed - needs investigation")
    
    print("="*60)