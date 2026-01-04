#!/usr/bin/env python3
"""
Simple Excel Integration Test
============================
Quick test of Excel integration functionality
"""

import json
import logging
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from src.universe.dynamic_universe_manager import DynamicUniverseManager
    
    print("🚀 Testing Excel Integration...")
    
    # Create universe manager
    universe_manager = DynamicUniverseManager()
    
    # Get current universe
    universe = universe_manager.get_current_universe()
    print(f"Current universe: {universe}")
    
    
    
    
    print(f"✅ Universe loaded: {len(universe.get('gainers', []))} gainers, {len(universe.get('losers', []))} losers")
    
    # Get Excel stats
    excel_stats = universe_manager.get_excel_stats()
    print(f"✅ Excel Integration: {'Enabled' if excel_stats.get('excel_integration_enabled') else 'Disabled'}")
    print(f"✅ XLWings Available: {excel_stats.get('xlwings_available')}")
    print(f"✅ Excel File: {excel_stats.get('excel_file_path')}")
    print(f"✅ File Exists: {excel_stats.get('excel_file_exists')}")
    
    # Test forced update
    if excel_stats.get('excel_integration_enabled') and excel_stats.get('xlwings_available'):
        print("\n🔄 Testing Excel update...")
        success = universe_manager.force_excel_update()
        print(f"✅ Excel Update: {'Success' if success else 'Failed'}")
        
        if success:
            print("\n🎉 SUCCESS! MiniRobo.xlsx has been updated with dynamic universe data!")
            print("   • Dynamic stocks are marked with SOURCE = 'DYNAMIC'")
            print("   • Static stocks are preserved")
            print("   • Check the UNIVERSE sheet in Excel")
        else:
            print("\n❌ Excel update failed. Check logs for details.")
    else:
        print("\n Excel integration not fully available")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()