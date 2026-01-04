#!/usr/bin/env python3
"""
Excel Universe Update Utility
=============================
Utility to manually update MiniRobo.xlsx with dynamic universe data.

Features:
- Force immediate Excel update
- Show current Excel data vs dynamic data
- Test Excel integration functionality
- Backup and restore capabilities

Usage:
    python excel_universe_updater.py [--force] [--backup] [--status]
"""

import sys
import os
import argparse
from datetime import datetime
from pathlib import Path
import shutil

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.strategies.market_detector import EnhancedMarketDetector
from src.strategies.gainer_loser_strategy import GainerLoserStrategy
from src.universe.dynamic_universe_manager import DynamicUniverseManager

try:
    import xlwings as xw
    import pandas as pd
    XLWINGS_AVAILABLE = True
except ImportError:
    XLWINGS_AVAILABLE = False


def print_section(title: str):
    """Print formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def backup_excel_file(excel_path: Path) -> Path:
    """Create backup of Excel file"""
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_path}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = excel_path.parent / f"{excel_path.stem}_backup_{timestamp}{excel_path.suffix}"
    
    shutil.copy2(excel_path, backup_path)
    print(f"✅ Backup created: {backup_path}")
    return backup_path


def show_excel_status(strategy: GainerLoserStrategy):
    """Show current Excel integration status"""
    print_section("📊 EXCEL INTEGRATION STATUS")
    
    excel_stats = strategy.get_excel_integration_status()
    
    print(f"Excel Integration: {'✅ Enabled' if excel_stats.get('excel_integration_enabled') else '❌ Disabled'}")
    print(f"XLWings Available: {'✅ Yes' if excel_stats.get('xlwings_available') else '❌ No'}")
    print(f"Excel File: {excel_stats.get('excel_file_path', 'N/A')}")
    print(f"File Exists: {'✅ Yes' if excel_stats.get('excel_file_exists') else '❌ No'}")
    print(f"Last Update: {excel_stats.get('last_excel_update', 'Never')}")
    print(f"Next Forced Update: {excel_stats.get('next_forced_update', 'N/A')}")
    print(f"Auto-Update on Refresh: {'✅ Yes' if excel_stats.get('update_on_refresh') else '❌ No'}")
    print(f"Merge with Existing: {'✅ Yes' if excel_stats.get('merge_with_existing') else '❌ No'}")
    print(f"Preserve Static Stocks: {'✅ Yes' if excel_stats.get('preserve_static_stocks') else '❌ No'}")


def show_current_excel_data(excel_path: Path):
    """Show current data in Excel file"""
    try:
        if not XLWINGS_AVAILABLE:
            print("❌ XLWings not available - cannot read Excel data")
            return
        
        if not excel_path.exists():
            print(f"❌ Excel file not found: {excel_path}")
            return
        
        print_section("📄 CURRENT EXCEL DATA")
        
        with xw.App(visible=False) as app:
            wb = app.books.open(str(excel_path))
            
            try:
                sheet = wb.sheets['UNIVERSE']
                universe_range = sheet.range('A1').expand()
                df = universe_range.options(pd.DataFrame, header=1, index=False).value
                
                if df is None or df.empty:
                    print("📋 Excel UNIVERSE sheet is empty")
                    return
                
                print(f"Total Stocks: {len(df)}")
                
                # Show breakdown by source
                if 'SOURCE' in df.columns:
                    source_counts = df['SOURCE'].value_counts()
                    print("\nBreakdown by Source:")
                    for source, count in source_counts.items():
                        print(f"   {source}: {count} stocks")
                
                # Show recent dynamic stocks
                if 'SOURCE' in df.columns and 'LAST_UPDATED' in df.columns:
                    dynamic_stocks = df[df['SOURCE'] == 'DYNAMIC']
                    if not dynamic_stocks.empty:
                        print(f"\nRecent Dynamic Stocks ({len(dynamic_stocks)}):")
                        for _, stock in dynamic_stocks.head(10).iterrows():
                            signal_type = stock.get('SIGNAL_TYPE', 'N/A')
                            gap_pct = stock.get('GAP_PCT', 0)
                            updated = stock.get('LAST_UPDATED', 'N/A')
                            print(f"   {stock['SYMBOL']:<12} {signal_type:<8} {gap_pct:>6.1f}% {updated}")
                        
                        if len(dynamic_stocks) > 10:
                            print(f"   ... and {len(dynamic_stocks) - 10} more")
                
                # Show some static stocks
                if 'SOURCE' in df.columns:
                    static_stocks = df[df['SOURCE'] != 'DYNAMIC']
                    if not static_stocks.empty:
                        print(f"\nStatic/Manual Stocks ({len(static_stocks)}):")
                        for _, stock in static_stocks.head(5).iterrows():
                            sector = stock.get('SECTOR', 'N/A')
                            print(f"   {stock['SYMBOL']:<12} {sector}")
                        
                        if len(static_stocks) > 5:
                            print(f"   ... and {len(static_stocks) - 5} more")
                
            finally:
                wb.close()
                
    except Exception as e:
        print(f"❌ Error reading Excel data: {e}")


def show_dynamic_universe_data(universe_manager: DynamicUniverseManager):
    """Show current dynamic universe data"""
    print_section("🌍 CURRENT DYNAMIC UNIVERSE")
    
    universe = universe_manager.get_current_universe()
    stats = universe_manager.get_universe_stats()
    
    print(f"Data Source: {universe.get('data_source', 'Unknown')}")
    print(f"Last Update: {universe.get('update_time', 'Unknown')}")
    print(f"Total Stocks: {stats.get('total_stocks', 0)}")
    print(f"Gainers: {stats.get('gainers_count', 0)} (avg gap: {stats.get('avg_gainer_gap', 0):.1f}%)")
    print(f"Losers: {stats.get('losers_count', 0)} (avg gap: {stats.get('avg_loser_gap', 0):.1f}%)")
    print(f"Sectors: {stats.get('sectors_covered', 0)}")
    
    # Show sample stocks
    gainers = universe.get('gainers', [])
    losers = universe.get('losers', [])
    
    if gainers:
        print(f"\nTop Gainers ({len(gainers)}):")
        for gainer in gainers[:5]:
            print(f"   {gainer['symbol']:<12} {gainer['gap_pct']:>6.1f}% {gainer.get('sector', 'N/A'):<12}")
    
    if losers:
        print(f"\nTop Losers ({len(losers)}):")
        for loser in losers[:5]:
            print(f"   {loser['symbol']:<12} {loser['gap_pct']:>6.1f}% {loser.get('sector', 'N/A'):<12}")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Excel Universe Update Utility")
    parser.add_argument('--force', action='store_true', help='Force immediate Excel update')
    parser.add_argument('--backup', action='store_true', help='Create backup before updating')
    parser.add_argument('--status', action='store_true', help='Show status only (no updates)')
    
    args = parser.parse_args()
    
    print_section("🚀 EXCEL UNIVERSE UPDATE UTILITY")
    
    try:
        # Initialize components
        print("🔧 Initializing components...")
        market_detector = EnhancedMarketDetector()
        strategy = GainerLoserStrategy(market_detector)
        universe_manager = DynamicUniverseManager()
        
        excel_path = Path("MiniRobo.xlsx")
        
        if not excel_path.exists():
            print(f"❌ Excel file not found: {excel_path}")
            return
        
        # Show status
        show_excel_status(strategy)
        
        if args.status:
            show_current_excel_data(excel_path)
            show_dynamic_universe_data(universe_manager)
            return
        
        # Check prerequisites
        excel_stats = strategy.get_excel_integration_status()
        
        if not excel_stats.get('excel_integration_enabled'):
            print("\n❌ Excel integration is disabled")
            print("Enable it in config/dynamic_universe_config.yaml")
            return
        
        if not excel_stats.get('xlwings_available'):
            print("\n❌ XLWings not available")
            print("Install with: pip install xlwings")
            return
        
        if not excel_path.exists():
            print(f"\n❌ Excel file not found: {excel_path}")
            return
        
        # Create backup if requested
        if args.backup:
            backup_excel_file(excel_path)
        
        # Show current data
        show_current_excel_data(excel_path)
        show_dynamic_universe_data(universe_manager)
        
        # Perform update
        if args.force:
            print_section("🔄 PERFORMING EXCEL UPDATE")
            print("Updating Excel file with latest dynamic universe...")
            
            success = strategy.force_excel_update()
            
            if success:
                print("✅ Excel update completed successfully!")
                print("\nUpdated data:")
                show_current_excel_data(excel_path)
                
                print("\n📋 Summary:")
                print("• Dynamic stocks are highlighted in light green")
                print("• Static/manual stocks are preserved")
                print("• Check the 'SOURCE' column to distinguish stock types")
                print("• Use Excel filters to view only dynamic or static stocks")
            else:
                print("❌ Excel update failed!")
                print("Check logs for error details")
        else:
            print("\n💡 Use --force to perform the Excel update")
            print("   python excel_universe_updater.py --force")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()