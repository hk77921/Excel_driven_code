"""Test script to verify adaptive strategies import fix"""
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)

try:
    from src.strategies import AdaptiveStrategyManager
    print("✓ AdaptiveStrategyManager imported successfully")
    
    manager = AdaptiveStrategyManager()
    print("✓ AdaptiveStrategyManager instantiated successfully")
    print("\n[SUCCESS] Adaptive strategies fixed!")
    print("No 'attempted relative import beyond top-level package' error")
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
