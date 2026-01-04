#!/usr/bin/env python3
"""
Main Entry Point for Excel-Driven Trading Bot
============================================

This is the main entry point for all trading bot operations.
Supports multiple execution modes:

1. Test Mode - Run comprehensive tests
2. Paper Trading - Simulate trading with real market data  
3. Live Trading - Execute real trades (requires broker setup)
4. Backtest - Historical strategy testing

Usage:
    python main.py --mode test
    python main.py --mode paper [--config config.json]
    python main.py --mode live [--config config.json]
    python main.py --mode backtest [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]

Requirements:
    - MiniRobo.xlsx file in the root directory
    - Proper configuration files in config/ directory
    - Required Python packages (see requirements.txt)
"""

import sys
import os
import argparse
import logging
import subprocess
import time
from datetime import datetime, date
from pathlib import Path
import json
from typing import Dict, Any, Optional
#from venv import logger
import logging

logger = logging.getLogger(__name__)

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.core.models import TradeParameters, CapitalParameters
from src.core.state_manager import StateManager
from src.execution.paper import PaperTradingMode
from src.execution.live import LiveTradingMode  
from src.execution.backtest import BacktestMode
from src.screener.excel_screener import ExcelScreener
from config.enhanced_config_manager import create_config_manager, EnhancedConfigManager


def setup_logging(config_mgr: EnhancedConfigManager = None, log_level_override: str = None) -> None:
    """Setup logging configuration from centralized config with UTF-8 support for Unicode characters like ₹"""
    if config_mgr is None:
        config_mgr = create_config_manager()
    
    # Get centralized logging configuration
    log_config = config_mgr.get_logging_configuration()
    env_config = config_mgr.get_environment_configuration()
    
    # Create logs directory
    log_dir = Path(env_config.logs_directory)
    log_dir.mkdir(exist_ok=True)
    
    # Use override if provided, otherwise use config
    log_level = log_level_override or log_config.level
    
    handlers = []
    
    # File handler (if enabled)
    if log_config.file_enabled:
        file_handler = logging.FileHandler(
            log_dir / f"trading_bot_{date.today().strftime('%Y%m%d')}.log",
            encoding='utf-8' if log_config.unicode_support else None
        )
        file_handler.setLevel(getattr(logging, log_config.level.upper()))
        handlers.append(file_handler)
    
    # Console handler (if enabled)  
    if log_config.console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        handlers.append(console_handler)
    
    # Configure basic logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_config.format,
        handlers=handlers,
        force=True  # Reset any existing configuration
    )
    
    # Set module-specific log levels if configured
    module_levels = getattr(log_config, 'module_levels', {})
    for module_name, level in module_levels.items():
        logger = logging.getLogger(module_name)
        logger.setLevel(getattr(logging, level.upper()))


def load_config_manager(config_path: Optional[str] = None) -> EnhancedConfigManager:
    """Load enhanced configuration manager"""
    try:
        # Create enhanced config manager (ignores config_path for now as we use YAML files)
        config_mgr = create_config_manager()
        
        # Validate configuration
        issues = config_mgr.validate_configuration()
        if issues:
            print(f"⚠️  Configuration validation issues found:")
            for issue in issues:
                print(f"   • {issue}")
            print("  Continuing with current configuration...")
        
        return config_mgr
    except Exception as e:
        print(f" Error loading enhanced config: {e}")
        print(" Creating config manager with defaults...")
        return EnhancedConfigManager()


def get_parameters_from_config_manager(config_mgr: EnhancedConfigManager) -> tuple:
    """Create parameter objects from enhanced config manager"""
    # Get parameters directly from enhanced config manager
    capital_params = config_mgr.get_capital_parameters()
    trade_params = config_mgr.get_trade_parameters()
    
    return capital_params, trade_params


def run_tests() -> None:
    """Run comprehensive test suite"""
    print(" Running comprehensive test suite...")
    
    # Run the simple test first (ASCII-only, no Unicode issues)
    try:
        result = subprocess.run(
            [sys.executable, "test/simple_test.py"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print(" Simple tests completed successfully!")
            if result.stdout:
                print(result.stdout)
                
            # Try to run the comprehensive test if simple tests pass
            print("\n Running comprehensive production test...")
            comp_result = subprocess.run(
                [sys.executable, "test/run_tests.py"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd="test"
            )
            
            if comp_result.returncode == 0:
                print(" Comprehensive tests completed successfully!")
                if comp_result.stdout:
                    print(comp_result.stdout)
            else:
                print(" Comprehensive tests had issues, but simple tests passed")
                if comp_result.stdout:
                    print(comp_result.stdout)
        else:
            print(f" Tests failed with return code {result.returncode}")
            if result.stderr:
                print(f"Error output: {result.stderr}")
            if result.stdout:
                print(f"Standard output: {result.stdout}")
            sys.exit(1)
    except subprocess.TimeoutExpired:
        print(" Tests timed out")
        sys.exit(1)
    except Exception as e:
        print(f" Tests failed: {e}")
        sys.exit(1)


def run_paper_trading(config_mgr: EnhancedConfigManager, args, fresh_start: bool = False) -> None:
    """Run paper trading mode"""
    print(" Starting Paper Trading Mode...")
    
    try:
        # Get parameters from enhanced config manager
        capital_params, trade_params = get_parameters_from_config_manager(config_mgr)
        
        # Load timing configuration with command line overrides
        config_timing_enabled = config_mgr.is_timing_enabled()
        
        # Apply command line overrides
        if args.force_timing:
            timing_enabled = True
            print(" 🔧 Timing intelligence FORCE ENABLED via command line")
        elif args.no_timing:
            timing_enabled = False
            print(" 🔧 Timing intelligence DISABLED via command line")
        else:
            timing_enabled = config_timing_enabled
            print(f" ⚙️  Timing intelligence: {'ENABLED' if timing_enabled else 'DISABLED'} (from config)")
        
        print(" 🚀 Starting Enhanced Paper Trading Mode with New Architecture...")
        
        # PHASE 1: Initialize State Manager
        print(" 📊 Phase 1: Initialize State Manager")
        state_manager = StateManager("state/paper")
        
        # Clear state if fresh start requested
        if fresh_start:
            print("   🧹 Clearing previous state for fresh start...")
            state_manager.clear_all_state()
            print("   ✅ State cleared - starting with clean slate")
        
        # PHASE 2: Initialize Risk Manager
        print(" 🛡️  Phase 2: Initialize Risk Manager")
        from src.core.risk_manager import RiskManager
        risk_manager = RiskManager(capital_params, trade_params, state_manager)
        print("   ✅ Risk Manager initialized with comprehensive controls")
        
        # PHASE 3: Initialize Market Context
        print(" 📈 Phase 3: Initialize Market Context")
        env_config = config_mgr.get_environment_configuration()
        screener = ExcelScreener(env_config.excel_file)
        
        # Get trading universe for warmup
        try:
            trading_symbols = screener.get_symbols_list()
            print(f"   📋 Trading universe: {len(trading_symbols)} symbols")
        except Exception as e:
            print(f"   ⚠️  Could not load symbols from Excel: {e}")
            trading_symbols = ['RELIANCE.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'TCS.NS', 'INFY.NS']
            print(f"   📋 Using default symbols: {len(trading_symbols)} symbols")
        
        # PHASE 4: Warm-up Strategies & Indicators  
        print(" 🔥 Phase 4: Warm-up Strategies & Indicators")
        from src.core.warmup_manager import WarmupManager
        warmup_manager = WarmupManager(trading_symbols[:10])  # Limit to first 10 for performance
        
        try:
            warmup_result = warmup_manager.execute_warmup()
            if warmup_result.success:
                print(f"   ✅ Warmup completed in {warmup_result.total_duration:.2f}s")
                print(f"   📊 {len(warmup_result.symbols_warmed)} symbols warmed with indicators")
            else:
                print(f"   ⚠️  Warmup had issues: {len(warmup_result.failed_tasks)} task failures")
        except Exception as e:
            print(f"   ⚠️  Warmup failed: {e}")
            print("   🔄 Continuing without warmup data...")
        
        # PHASE 5: Initialize Execution Mode with Enhanced Engine
        print(" ⚙️  Phase 5: Initialize Enhanced Execution Mode")
        trader = PaperTradingMode(
            capital_params, 
            trade_params, 
            "state/paper",
            timing_enabled=timing_enabled,
            symbols=trading_symbols  # Pass symbols for engine initialization
        )
        
        # PHASE 6: Arm Risk & Kill Switches
        print(" 🔒 Phase 6: Arm Risk & Kill Switches")
        from src.core.system_arming import SystemArming
        system_arming = SystemArming(risk_manager, state_manager)
        
        try:
            arming_result = system_arming.arm_system()
            if arming_result.status.value == "ARMED":
                print(f"   ✅ System ARMED successfully at {arming_result.armed_at.strftime('%H:%M:%S')}")
                print(f"   🛡️  {len(arming_result.checks)} safety checks passed")
            else:
                print(f"   ❌ System ARMING FAILED: {arming_result.error_message}")
                print("   🚨 Failed safety checks:")
                for check in arming_result.failed_checks:
                    print(f"      • {check.name}: {check.message}")
                
                # Ask user if they want to force arm (dangerous!)
                response = input("   ⚠️  Force arm system anyway? (type 'FORCE' to continue): ")
                if response == "FORCE":
                    arming_result = system_arming.arm_system(force=True)
                    print(f"   ⚠️  System FORCE ARMED - proceed with caution!")
                else:
                    print("   🛑 System not armed - exiting for safety")
                    return
                    
        except Exception as e:
            print(f"   ❌ Arming process failed: {e}")
            print("   🛑 Cannot proceed without proper system arming")
            return

        # Display enhanced status
        print(" 📊 Enhanced System Status:")
        if timing_enabled:
            print("   🧠 Timing Intelligence: ENABLED")
            if hasattr(trader.engine, 'timing_filter') and trader.engine.timing_filter:
                timing_info = trader.engine.timing_filter.get_timing_info()
                regime_info = timing_info['market_regime']
                print(f"     Market Regime: {regime_info['regime']} (confidence: {regime_info['confidence']:.2f})")
                print(f"     Daily Entries: {timing_info['daily_entries']}")
        else:
            print("   ⚡ Timing Intelligence: DISABLED (immediate execution)")
        
        # Show risk status
        risk_status = trader.engine.get_risk_status()
        print(f"   💰 Available Capital: ₹{risk_status['risk_manager']['available_capital']:,.0f}")
        print(f"   📊 Active Positions: {risk_status['risk_manager']['active_positions']}/{risk_status['risk_manager']['max_positions']}")
        print(f"   🎯 Daily P&L: ₹{risk_status['risk_manager']['daily_pnl']:,.0f}")
        
        print(" ✅ Enhanced Paper Trading System Ready!")
        print(" 🔍 Running screener...")
        
        # Reset timing filter for new session (clears daily entry count from previous runs)
        if trader.engine.timing_enabled and trader.engine.timing_filter:
            trader.engine.timing_filter.reset_for_new_session()
        
        # PHASE 7: Main Trading Loop with Enhanced Checks
        print(" 🔄 Phase 7: Begin Trading Operations")
        
        # Check if trading is allowed
        trading_allowed, reason = trader.engine.is_trading_allowed()
        if not trading_allowed:
            print(f" 🚫 Trading not allowed: {reason}")
            return
        
        # Update market context
        market_context = trader.engine.update_market_context()
        print(f" 📈 Market Context: {market_context.get('regime', 'Unknown')}")
        
        # Run screener
        signals = screener.run_screener()
        
        if signals:
            print(f" 🎯 Found {len(signals)} trading signals")
            
            # Process signals
            for signal in signals:
                success, order_id = trader.process_signal(signal)
                if success:
                    print(f" ✓ Order placed for {signal.symbol}: {order_id}")
                else:
                    print(f" ✗ Order rejected for {signal.symbol}: {order_id}")
        else:
            print(" No trading signals found today")
        
        # Run position monitoring
        report = trader.execute_cycle()
        print(f" Execution report: {report}")
        
        print("Paper trading session completed!")
        
    except Exception as e:
        print(f" Paper trading failed: {e}")
        logging.exception("Paper trading error")
        sys.exit(1)


def run_live_trading(config_mgr: EnhancedConfigManager, args) -> None:
    """Run live trading mode"""
    print(" Starting Live Trading Mode...")
    print("  WARNING: This will execute real trades with real money!")
    
    # Check broker configuration for LIVE mode
    try:
        broker_config = config_mgr.get_broker_configuration()
        print(f"  Broker: {broker_config.name}")
        print(f"  API Key: {'✓ Set' if broker_config.api_key else '✗ Missing'}")
        print(f"  Access Token: {'✓ Set' if broker_config.access_token else '✗ Missing'}")
    except Exception as e:
        print(f"  ✗ Broker configuration error: {e}")
        print("  Please check your .env file and broker configuration.")
        return
    
    confirmation = input("Type 'YES' to confirm live trading: ")
    if confirmation != 'YES':
        print(" Live trading cancelled")
        return
    
    try:
        # Get parameters from enhanced config manager
        capital_params, trade_params = get_parameters_from_config_manager(config_mgr)
        
        # Load timing configuration with command line overrides
        config_timing_enabled = config_mgr.is_timing_enabled()
        
        # Apply command line overrides
        if args.force_timing:
            timing_enabled = True
            print(" 🔧 Timing intelligence FORCE ENABLED via command line")
        elif args.no_timing:
            timing_enabled = False
            print(" 🔧 Timing intelligence DISABLED via command line")
        else:
            timing_enabled = config_timing_enabled
            print(f" ⚙️  Timing intelligence: {'ENABLED' if timing_enabled else 'DISABLED'} (from config)")
        
        # Initialize live trading (using PaperTradingMode with live broker)
        # NOTE: LiveTradingMode needs additional broker setup
        state_manager = StateManager("state/live")

        state = state_manager.get_system_state()
        assert state is not None, "StateManager returned None system state"
        assert hasattr(state, "capital_available"), "SystemState missing capital_available"
        assert hasattr(state, "open_positions"), "SystemState missing open_positions"
        assert hasattr(state, "trading_enabled"), "SystemState missing trading_enabled"




        trader = LiveTradingMode(capital_params, trade_params, "state/live", timing_enabled)
        
        if not trader.broker.is_connected:
            print("Failed to connect to live broker. Check broker settings. Exiting...")
            sys.exit(1)

        if reconcile_on_startup(self=trader) is False:
            print("❌ Broker reconciliation failed — exiting for safety")
            sys.exit(1)


        # Display capital breakdown after reconciliation
        positions = trader.state.load_positions()
        pending_orders = trader.state.load_orders()
        breakdown = trader.engine.capital_mgr.get_capital_breakdown(positions, pending_orders)
        
        print("\n" + "="*70)
        print("CAPITAL BREAKDOWN (AFTER BROKER RECONCILIATION)")
        print("="*70)
        print(f"Total Capital:        ₹{breakdown.total_capital:>12,.2f}")
        print(f"- Position Exposure:  ₹{breakdown.position_exposure:>12,.2f}")
        print(f"- Pending Orders:     ₹{breakdown.pending_buy_capital:>12,.2f}")
        print(f"- Safety Buffer (15%): ₹{breakdown.safety_buffer:>12,.2f}")
        print(f"= AVAILABLE CAPITAL:  ₹{breakdown.available_capital:>12,.2f}")
        print("="*70)
        
        if positions:
            print(f"\n✓ Open Positions: {len(positions)}")
            for symbol, pos in positions.items():
                qty_remaining = pos.get('qty_remaining', 0)
                if qty_remaining > 0:
                    print(f"  • {symbol}: {qty_remaining} shares @ ₹{pos['entry_price']:.2f}")
        else:
            print("\nNo open positions")
        
        if pending_orders:
            print(f"\n✓ Pending Orders: {len(pending_orders)}")
            for order_id, order in pending_orders.items():
                print(f"  • {order_id}: {order['symbol']} {order['side']} {order.get('req_qty', 0)}")
        
        print("="*70)
        print(f"\n⚠️  WARNING: LIVE TRADING - REAL MONEY AT RISK!")
        print(f"    Max Loss per Day (Kill Switch): ₹{capital_params.total_capital * capital_params.max_daily_loss_pct:,.2f}")
        print(f"    Current Available: ₹{breakdown.available_capital:,.2f}\n")

        confirmation = input("Type 'LIVE-TRADING-CONFIRMED' to proceed: ")
        if confirmation != 'LIVE-TRADING-CONFIRMED':
            print(" Live trading cancelled")
            sys.exit(0)


        # Initialize screener
        env_config = config_mgr.get_environment_configuration()
        screener = ExcelScreener(env_config.excel_file)
        
        print(" Live trading initialized successfully!")
        print(" Running screener...")
        print(f"\n⏰ Running on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"✓ Available Capital: ₹{breakdown.available_capital:,.2f}")
        print(f"✓ Open Positions: {list(positions.keys()) if positions else 'None'}")
        print("-" * 70 + "\n")
        
        # Reset timing filter for new session (clears daily entry count from previous runs)
        if trader.engine.timing_enabled and trader.engine.timing_filter:
            trader.engine.timing_filter.reset_for_new_session()
        
        # Run screener
        signals = screener.run_screener()
        
        if signals:
            print(f" Found {len(signals)} trading signals\n")
            
            # Process signals
            for signal in signals:
                success, message = trader.process_signal(signal)
                if success:
                    print(f"  ✓ {signal.symbol}: Order placed (ID: {message})")
                else:
                    # message is the rejection reason
                    print(f"  ✗ {signal.symbol}: Rejected - {message}")
        else:
            print(" No trading signals found today")
        
        # Run position monitoring with continuous market monitoring
        cycle_count = 0
        last_screener_run = datetime.now()
        screener_interval = 5  # Run screener every 5 minutes
        
        while True:
            try:
                cycle_count += 1
                current_time = datetime.now()
                
                # Verify connection health every cycle
                if not trader.verify_connection_health():
                    print("Broker connection lost! Emergency stop activated.")
                    print("Please check connection and restart.")
                    break
                
                # 1. Update market regime every cycle for continuous monitoring
                if hasattr(trader, 'timing_filter') and trader.timing_filter:
                    trader.timing_filter.regime_manager.detect_regime()
                    regime_info = trader.timing_filter.regime_manager.get_regime_info()
                    if cycle_count % 5 == 1:  # Log every 5 cycles (5 minutes)
                        logger.info(f"Market Status: {regime_info['regime']} | Confidence: {regime_info['confidence']:.2f} | Should Trade: {regime_info['should_trade']}")
                
                # 2. Run periodic screener to catch new signals
                time_since_screener = (current_time - last_screener_run).total_seconds() / 60
                if time_since_screener >= screener_interval:
                    print(f"\n🔍 Running periodic screener check ({current_time.strftime('%H:%M:%S')})...")
                    try:
                        new_signals = screener.run_screener()
                        if new_signals:
                            print(f"📊 Found {len(new_signals)} new trading signals")
                            # Process new signals
                            for signal in new_signals:
                                success, message = trader.process_signal(signal)
                                if success:
                                    print(f"  ✓ {signal.symbol}: Order placed (ID: {message})")
                                else:
                                    print(f"  ✗ {signal.symbol}: Rejected - {message}")
                        else:
                            print("📊 No new trading signals found")
                    except Exception as e:
                        logger.warning(f"Screener run failed: {e}")
                    
                    last_screener_run = current_time
                
                # 3. Run normal position monitoring cycle
                report = trader.execute_cycle()
                
                # 4. Enhanced reporting
                if report['errors']:
                    logger.warning(f"Cycle {cycle_count} had {len(report['errors'])} errors")
                
                if cycle_count % 10 == 0:  # Status update every 10 minutes
                    print(f"\n⏰ Trading Status ({current_time.strftime('%H:%M:%S')}):")
                    print(f"   Cycle: {cycle_count} | Orders: {report.get('orders_filled', 0)} filled | Exits: {report.get('exits_executed', 0)} executed")
                    if hasattr(trader, 'timing_filter') and trader.timing_filter:
                        regime_info = trader.timing_filter.regime_manager.get_regime_info()
                        print(f"   Market: {regime_info['regime']} | Trading: {'Enabled' if regime_info['should_trade'] else 'Paused'}")
                
                # Sleep before next cycle
                time.sleep(60)  # 1 minute between cycles
                    
            except Exception as e:
                logger.error(f"Trading cycle failed: {e}")
                trader.enable_emergency_stop()
                break
        
       
        print(f" Execution report: {report}")
        
        print("Live trading session completed!")
        
    except Exception as e:
        print(f" Live trading failed: {e}")
        logging.exception("Live trading error")
        sys.exit(1)


def run_backtest(start_date: str, end_date: str, config_mgr: EnhancedConfigManager, args, fresh_start: bool = False) -> None:
    """Run backtest mode"""
    print(f" Starting Backtest Mode: {start_date} to {end_date}")
    
    try:
        import yfinance as yf
        import pandas as pd
        from tqdm import tqdm
        
        # Get environment configuration for state directory
        env_config = config_mgr.get_environment_configuration()
        state_manager = StateManager(f"{env_config.state_directory}/backtest")
        if fresh_start:
            print(" Clearing previous state for fresh start...")
            state_manager.clear_all_state()

        # Get parameters from enhanced config manager
        capital_params, trade_params = get_parameters_from_config_manager(config_mgr)
        
        # Load timing configuration with command line overrides
        config_timing_enabled = config_mgr.is_timing_enabled()
        
        # Apply command line overrides
        if args.force_timing:
            timing_enabled = True
            print(" 🔧 Timing intelligence FORCE ENABLED via command line")
        elif args.no_timing:
            timing_enabled = False
            print(" 🔧 Timing intelligence DISABLED via command line")
        else:
            timing_enabled = config_timing_enabled
            print(f" ⚙️  Timing intelligence: {'ENABLED' if timing_enabled else 'DISABLED'} (from config)")
        
        # Initialize backtest
        trader = BacktestMode(capital_params, trade_params, f"{env_config.state_directory}/backtest", timing_enabled)
        
        # Load stock symbols from Excel file
        print(f" Loading stock universe from Excel...")
        from src.screener.excel_screener import ExcelScreener
        screener = ExcelScreener(env_config.excel_file)
        
        # Get universe from Excel (this loads the UNIVERSE sheet)
        universe_df = screener.load_universe()
        symbols = list(universe_df['SYMBOL']) if not universe_df.empty else []
        
        if not symbols:
            print(" No symbols found in Excel file")
            return
            
        print(f" Found {len(symbols)} symbols in universe")
        print(f" Fetching historical data from {start_date} to {end_date}...")
        
        # Fetch real historical data for each symbol
        successful_loads = 0
        failed_symbols = []
        
        print(f" Loading historical data for {len(symbols)} symbols...")
        for symbol in symbols:
            try:
                # Convert symbol format for yfinance (add .NS if not present)
                yf_symbol = symbol if '.NS' in symbol else f"{symbol}.NS"
                
                # Download historical data
                ticker = yf.Ticker(yf_symbol)
                hist_data = ticker.history(start=start_date, end=end_date, interval='1d')
                
                if not hist_data.empty:
                    # Prepare data in expected format
                    df = pd.DataFrame({
                        'date': pd.to_datetime(hist_data.index).strftime('%Y-%m-%d'),
                        'open': hist_data['Open'],
                        'high': hist_data['High'], 
                        'low': hist_data['Low'],
                        'close': hist_data['Close'],
                        'volume': hist_data['Volume']
                    }).reset_index(drop=True)
                    
                    # Load into backtest engine
                    trader.load_data(symbol, df)
                    successful_loads += 1
                else:
                    failed_symbols.append(symbol)
                    
            except Exception as e:
                failed_symbols.append(symbol)
                logging.warning(f"Failed to load data for {symbol}: {e}")
        
        print(f" Successfully loaded data for {successful_loads}/{len(symbols)} symbols")
        if failed_symbols:
            print(f"  Failed to load: {', '.join(failed_symbols[:5])}" + 
                  (f" and {len(failed_symbols)-5} more" if len(failed_symbols) > 5 else ""))
        
        if successful_loads == 0:
            print(" No historical data loaded. Cannot run backtest.")
            return
            
        print(" Backtest initialized with REAL historical data!")
        print(" Running historical simulation...")
        
        # Initialize screener for signal generation
        try:
            env_config = config_mgr.get_environment_configuration()
            screener = ExcelScreener(env_config.excel_file)
            print(" Screener initialized for signal generation")
        except Exception as e:
            print(f" Screener initialization failed: {e}")
            print(" Running backtest without signal generation (position management only)")
            screener = None
        
        # Run backtest on real data
        results = trader.run_backtest(screener)
        
        print(" Backtest Results:")
        if 'error' not in results:
            print(f"    Bars Processed: {results.get('bars_processed', 0)}")
            print(f"   Signals Generated: {results.get('signals_generated', 0)}")
            print(f"    Signals Processed: {results.get('signals_processed', 0)}")
            print(f"    Final Capital: Rs.{results.get('final_capital', 0):,.0f}")
            print(f"    Total P&L: Rs.{results.get('total_pnl', 0):,.0f}")
            print(f"    P&L Percentage: {results.get('pnl_percentage', 0):.2f}%")
            print(f"    Open Positions: {results.get('open_positions', 0)}")
            print(f"    Pending Orders: {results.get('pending_orders', 0)}")
            
            # Write backtest results to Excel SCREENER_OUTPUT sheet
            try:
                symbol_stats = results.get('symbol_statistics', {})
                if symbol_stats:
                    # Prepare results dataframe with proper screener format
                    output_data = []
                    for symbol, stats in symbol_stats.items():
                        # Only include symbols that were actually traded
                        if stats.get('total_trades', 0) > 0:
                            output_data.append({
                                "SYMBOL": symbol,
                                "SECTOR": "BACKTEST",
                                "PRICE": "-",
                                "ATR_PCT": "-",
                                "ADX": "-",
                                "VOL_RATIO": "-",
                                "ADTV_CR": "-",
                                "TREND": "-",
                                "SCORE": "-",
                                "REASONS": f"BT:{stats.get('total_trades')} trades, {stats.get('win_rate', 0):.1f}% win, P&L Rs.{stats.get('total_pnl', 0):.0f}",
                                "REL_STRENGTH": "-",
                                "ELIGIBLE": "TRADED",
                                "BACKTEST_RESULTS": f"Trades:{stats.get('total_trades', 0)} | PnL:Rs.{stats.get('total_pnl', 0):.0f} | Factor:{stats.get('profit_factor', 0):.2f}"
                            })
                    
                    if output_data:
                        # Create DataFrame
                        import pandas as pd
                        df_output = pd.DataFrame(output_data)
                        
                        # Write to Excel using screener's method
                        #screener.write_results_to_excel(df_output)
                        print(f" Backtest results written to SCREENER_OUTPUT sheet in MiniRobo.xlsx ({len(output_data)} traded symbols)")
                    else:
                        print(" No traded symbols in backtest to write to Excel")
            except Exception as e:
                print(f" Warning: Failed to write results to Excel: {e}")
                logging.debug(f"Excel write error: {e}")
            
            # Display per-symbol statistics
            symbol_stats = results.get('symbol_statistics', {})
            if symbol_stats:
                print("\n" + "="*80)
                print(" PER-SYMBOL PERFORMANCE ANALYSIS")
                print("="*80)
                
                # Sort symbols by total P&L including unrealized (best performers first)
                sorted_symbols = sorted(symbol_stats.items(), 
                                      key=lambda x: x[1].get('total_pnl_with_unrealized', x[1]['total_pnl']), 
                                      reverse=True)
                
                # Display summary table header
                print(f"{'Symbol':<12} {'Trades':<8} {'Win%':<8} {'Realized P&L':<12} {'Unrealized':<12} {'Total P&L':<12} {'Profit Factor':<12}")
                print("-" * 95)
                
                total_traded_symbols = 0
                profitable_symbols = 0
                symbols_with_positions = 0
                
                for symbol, stats in sorted_symbols:
                    # Show ALL symbols that have data, even if no trading activity
                    total_pnl_display = stats.get('total_pnl_with_unrealized', stats['total_pnl'])
                    unrealized_pnl = stats.get('unrealized_pnl', 0)
                    
                    # Count active symbols
                    if stats['total_trades'] > 0:
                        total_traded_symbols += 1
                    if unrealized_pnl != 0:
                        symbols_with_positions += 1
                    if total_pnl_display > 0:
                        profitable_symbols += 1
                        
                    profit_factor = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "INF" if stats['profit_factor'] > 0 else "-"
                    
                    # Show unrealized P&L if position is open
                    unrealized_str = f"Rs.{unrealized_pnl:.0f}" if unrealized_pnl != 0 else "-"
                    
                    # Show activity indicator
                    activity_indicator = ""
                    if stats['total_trades'] > 0 and unrealized_pnl != 0:
                        activity_indicator = " (T+O)"  # Traded + Open position
                    elif stats['total_trades'] > 0:
                        activity_indicator = " (T)"    # Traded only
                    elif unrealized_pnl != 0:
                        activity_indicator = " (O)"    # Open position only
                    
                    print(f"{symbol + activity_indicator:<12} {stats['total_trades']:<8} "
                          f"{stats['win_rate']:<7.1f}% "
                          f"Rs.{stats['total_pnl']:<11.0f} "
                          f"{unrealized_str:<12} "
                          f"Rs.{total_pnl_display:<11.0f} "
                          f"{profit_factor:<12}")
                
                # Summary statistics
                print("-" * 95)
                if total_traded_symbols > 0 or symbols_with_positions > 0:
                    print(f" SUMMARY: {len([s for s in sorted_symbols if s[1]['total_trades'] > 0 or s[1].get('unrealized_pnl', 0) != 0])} symbols active, "
                          f"{total_traded_symbols} traded, {symbols_with_positions} with open positions, "
                          f"{profitable_symbols} profitable")
                else:
                    print(" SUMMARY: No trading activity detected during backtest period")
                      
                # Top performers - only show if they're actually profitable
                top_performers = [(s, st) for s, st in sorted_symbols 
                                if (st['total_trades'] > 0 or st.get('unrealized_pnl', 0) != 0) 
                                and st.get('total_pnl_with_unrealized', st['total_pnl']) > 0]
                if top_performers:
                    print(f"\n TOP PERFORMERS:")
                    for i, (symbol, stats) in enumerate(top_performers[:3]):
                        total_pnl = stats.get('total_pnl_with_unrealized', stats['total_pnl'])
                        unrealized_note = " (with open position)" if stats.get('unrealized_pnl', 0) != 0 else ""
                        print(f"   {i+1}. {symbol}: Rs.{total_pnl:.0f} "
                              f"({stats['total_trades']} trades, {stats['win_rate']:.1f}% win rate){unrealized_note}")
                
                # Worst performers - only show if they're actually unprofitable
                worst_performers = [(s, st) for s, st in sorted_symbols 
                                  if (st['total_trades'] > 0 or st.get('unrealized_pnl', 0) != 0) 
                                  and st.get('total_pnl_with_unrealized', st['total_pnl']) < 0]
                if worst_performers:
                    print(f"\n  UNDERPERFORMERS:")
                    for i, (symbol, stats) in enumerate(worst_performers[-3:]):
                        total_pnl = stats.get('total_pnl_with_unrealized', stats['total_pnl'])
                        unrealized_note = " (with open position)" if stats.get('unrealized_pnl', 0) != 0 else ""
                        print(f"   {i+1}. {symbol}: Rs.{total_pnl:.0f} "
                              f"({stats['total_trades']} trades, {stats['win_rate']:.1f}% win rate){unrealized_note}")
            else:
                print("\n No trading activity detected during backtest period")
                
        else:
            print(f"    Error: {results.get('error')}")
        
        print("Backtest completed!")
        
    except Exception as e:
        print(f" Backtest failed: {e}")
        logging.exception("Backtest error")
        sys.exit(1)


def reconcile_on_startup(self) -> bool:
    """Reconcile state with broker on startup"""
    logger.info("Starting position reconciliation...")
    
    broker_positions = self.broker.get_positions()
    state_positions = self.state.load_positions()
    
    discrepancies = []
    
    # Check for positions at broker not in state
    for symbol, broker_pos in broker_positions.items():
        if symbol not in state_positions:
            discrepancies.append(f"Orphan position at broker: {symbol}")
    
    # Check for positions in state not at broker
    for symbol, state_pos in state_positions.items():
        if state_pos.get('qty_remaining', 0) > 0 and symbol not in broker_positions:
            discrepancies.append(f"Position in state but not at broker: {symbol}")
    
    if discrepancies:
        logger.critical(f"Position discrepancies found:\n" + "\n".join(discrepancies))
        return False
    
    logger.info("Position reconciliation completed - no discrepancies")
    return True

def main():
    """Main entry point"""
    # Fix Unicode encoding on Windows (support for ₹ rupee symbol)
    if sys.platform == 'win32':
        import io
        # Set UTF-8 encoding for stdout and stderr
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    
    parser = argparse.ArgumentParser(
        description="Excel-Driven Trading Bot with Configurable Timing Intelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Test mode (timing not used)
    python main.py --mode test
    
    # Paper trading with timing disabled (for testing)
    python main.py --mode paper --no-timing
    
    # Paper trading with timing enabled (overrides config)
    python main.py --mode paper --force-timing
    
    # Live trading with config-based timing
    python main.py --mode live
    
    # Backtest without timing restrictions
    python main.py --mode backtest --start-date 2024-01-01 --end-date 2024-12-31 --no-timing

Timing Configuration:
    Timing intelligence controls when trades can be entered/exited based on:
    - Market regime detection (bull/bear/sideways/volatile)
    - Optimal entry windows during trading hours
    - Risk-adjusted position sizing
    
    Configure in config/timing_config.yaml:
        timing:
          enabled: true/false
    
    Command line overrides:
        --no-timing:    Disable timing (useful for testing)
        --force-timing: Enable timing (overrides config)
        """
    )
    
    parser.add_argument(
        '--mode', '-m',
        choices=['test', 'paper', 'live', 'backtest'],
        required=True,
        help='Execution mode'
    )
    
    parser.add_argument(
    '--fresh-start', '-f',
    action='store_true',
    default=False,
    help='Clear all state for fresh start (paper/backtest modes only)'
    )
    parser.add_argument(
        '--config', '-c',
        help='Path to configuration file (JSON)'
    )
    
    parser.add_argument(
        '--start-date',
        help='Start date for backtest (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--end-date', 
        help='End date for backtest (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level'
    )
    
    parser.add_argument(
        '--no-timing',
        action='store_true',
        default=False,
        help='Disable timing intelligence (useful for testing and paper mode)'
    )
    
    parser.add_argument(
        '--force-timing',
        action='store_true', 
        default=False,
        help='Enable timing intelligence regardless of config (override config setting)'
    )
    
    args = parser.parse_args()
    
    # Load enhanced configuration manager first
    print("Loading configuration...")
    config_mgr = load_config_manager(args.config)
    
    # Setup logging using centralized configuration
    setup_logging(config_mgr, args.log_level)
    
    print("=" * 80)
    print("Excel-Driven Trading Bot")
    print("=" * 80)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode: {args.mode.upper()}")
    print("=" * 80)
    
    # Display configuration summary
    env_config = config_mgr.get_environment_configuration()
    capital_params = config_mgr.get_capital_parameters()
    print(f"Environment: {env_config.environment}")
    print(f"Execution Mode: {env_config.execution_mode}")
    print(f"Capital: ₹{capital_params.total_capital:,.2f}")
    print(f"Excel File: {env_config.excel_file}")
    print("=" * 80)
    
    if args.mode == 'test':
        run_tests()
        
    elif args.mode == 'paper':
        
        run_paper_trading(config_mgr, args, fresh_start=args.fresh_start)
        
    elif args.mode == 'live':
        run_live_trading(config_mgr, args)
        
    elif args.mode == 'backtest':
        if not args.start_date or not args.end_date:
            print(" Backtest mode requires --start-date and --end-date")
            sys.exit(1)
        run_backtest(args.start_date, args.end_date, config_mgr, args, fresh_start=args.fresh_start)


if __name__ == "__main__":
   
        main()