#!/usr/bin/env python3
"""
Quick script to manually clean up stale orders from the system.
Run this when you know the broker has no pending orders but the system shows stale ones.
"""

import json
import os
from datetime import datetime

def cleanup_stale_orders():
    """Clean up stale orders from the live state"""
    
    orders_file = "state/live/orders.json"
    backup_file = f"state/live/backups/orders_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    if not os.path.exists(orders_file):
        print(f"❌ Orders file not found: {orders_file}")
        return
    
    # Create backup directory if not exists
    os.makedirs(os.path.dirname(backup_file), exist_ok=True)
    
    # Load current orders
    with open(orders_file, 'r') as f:
        orders = json.load(f)
    
    print(f"📊 Current orders in system: {len(orders)}")
    
    if orders:
        print("\n🔍 Stale orders to be cleaned:")
        for order_id, order in orders.items():
            print(f"  • {order_id}: {order['symbol']} {order['side']} {order['req_qty']} @ ₹{order['price']:.2f} ({order['status']})")
        
        # Create backup
        with open(backup_file, 'w') as f:
            json.dump(orders, f, indent=2)
        print(f"\n💾 Backup created: {backup_file}")
        
        # Clear all orders
        with open(orders_file, 'w') as f:
            json.dump({}, f, indent=2)
        
        print(f"\n✅ Cleaned {len(orders)} stale orders")
        print("✅ Orders file is now empty")
    else:
        print("✅ No orders to clean - file is already empty")

if __name__ == "__main__":
    print("🧹 Stale Orders Cleanup Utility")
    print("=" * 50)
    
    confirm = input("\n⚠️  This will remove ALL pending orders from the system state.\n"
                   "Make sure your broker has NO pending orders before proceeding.\n"
                   "Type 'CLEANUP' to continue: ")
    
    if confirm == "CLEANUP":
        cleanup_stale_orders()
        print("\n🎉 Cleanup completed successfully!")
    else:
        print("\n❌ Cleanup cancelled - no changes made")