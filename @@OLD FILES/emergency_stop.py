"""
EMERGENCY STOP
--------------
Marks all open positions for immediate exit

USE THIS WHEN:
- Something goes wrong and you need to exit ALL positions
- Daily loss limit breached
- System malfunction detected
- Manual intervention required

After running this, execute: python execution_engine.py
"""

import json
import os
from datetime import datetime

STATE_FILE = "trade_state.json"

def emergency_stop():
    """Mark all positions for emergency exit"""
    
    print("="*60)
    print("🚨 EMERGENCY STOP INITIATED")
    print("="*60)
    
    if not os.path.exists(STATE_FILE):
        print("\n✓ No open positions found. Nothing to do.")
        return
    
    # Load current state
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
    except Exception as e:
        print(f"\n❌ ERROR: Could not load state file: {e}")
        return
    
    if not state:
        print("\n✓ No open positions found. Nothing to do.")
        return
    
    print(f"\n⚠️  Found {len(state)} open position(s):")
    
    # Display positions that will be closed
    for symbol, trade in state.items():
        qty = trade.get("qty_remaining", 0)
        entry = trade.get("entry", 0.0)
        exposure = qty * entry
        
        print(f"  • {symbol}: {qty} shares @ ₹{entry:.2f} (Exposure: ₹{exposure:,.2f})")
    
    # Confirmation
    print(f"\n{'='*60}")
    response = input("❓ Mark ALL positions for exit? (yes/no): ").strip().lower()
    
    if response != "yes":
        print("\n❌ Emergency stop cancelled.")
        return
    
    # Mark all positions for exit
    modified_count = 0
    for symbol, trade in state.items():
        if not trade.get("exit_pending", False):
            trade["exit_pending"] = True
            modified_count += 1
    
    # Save modified state
    try:
        # Create backup first
        backup_file = f"{STATE_FILE}.emergency_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with open(backup_file, "w") as f:
            with open(STATE_FILE, "r") as src:
                f.write(src.read())
        print(f"\n✓ Backup created: {backup_file}")
        
        # Save modified state
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        
        print(f"✓ Marked {modified_count} position(s) for exit")
        print(f"\n{'='*60}")
        print("✅ EMERGENCY STOP COMPLETE")
        print("="*60)
        print("\n📝 NEXT STEPS:")
        print("1. Run: python execution_engine.py")
        print("   (This will place SELL orders for all marked positions)")
        print("\n2. Monitor execution:")
        print("   tail -f trading_log_$(date +%Y%m%d).log")
        print("\n3. Verify positions closed:")
        print("   python monitor.py")
        print("\n⚠️  If execution_engine.py fails, manually close positions in Kite!")
        
    except Exception as e:
        print(f"\n❌ ERROR: Could not save state: {e}")
        print("Manual intervention required!")


def show_current_state():
    """Show current state without modifying"""
    
    print("\n" + "="*60)
    print("CURRENT STATE (View Only)")
    print("="*60)
    
    if not os.path.exists(STATE_FILE):
        print("\n✓ No state file found. No open positions.")
        return
    
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        
        if not state:
            print("\n✓ No open positions.")
            return
        
        print(f"\nOpen Positions: {len(state)}\n")
        
        for symbol, trade in state.items():
            entry = trade.get("entry", 0.0)
            sl = trade.get("sl", 0.0)
            qty = trade.get("qty", 0)
            qty_remaining = trade.get("qty_remaining", 0)
            exit_pending = trade.get("exit_pending", False)
            partial_done = trade.get("partial_done", False)
            
            status = []
            if exit_pending:
                status.append("EXIT PENDING")
            if partial_done:
                status.append("PARTIAL EXIT DONE")
            
            status_str = f" [{', '.join(status)}]" if status else ""
            
            print(f"{symbol}:")
            print(f"  Entry: ₹{entry:.2f} | SL: ₹{sl:.2f}")
            print(f"  Qty: {qty_remaining}/{qty}{status_str}")
            print()
            
    except Exception as e:
        print(f"Error reading state: {e}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--view":
        show_current_state()
    else:
        emergency_stop()