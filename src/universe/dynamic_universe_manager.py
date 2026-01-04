"""
Dynamic Universe Manager
========================
Manages the dynamic selection and updating of trading universe
based on live NSE data and configuration parameters.

Features:
- Live NSE top gainers/losers fetching
- Sector diversification controls
- Market cap and liquidity filters  
- Fallback mechanisms
- Performance tracking
- Excel integration for MiniRobo.xlsx updates
"""

import logging
from typing import Dict, Any, List, Mapping, Optional, Tuple, Union
from datetime import datetime, time, timedelta
import yaml
from pathlib import Path
import pandas as pd

try:
    from nsetools import Nse
    NSE_AVAILABLE = True
except ImportError:
    NSE_AVAILABLE = False

try:
    import xlwings as xw
    XLWINGS_AVAILABLE = True
except ImportError:
    XLWINGS_AVAILABLE = False
    logging.warning("xlwings not available. Excel integration disabled.")

logger = logging.getLogger(__name__)


class DynamicUniverseManager:
    """Manages dynamic universe selection for trading strategies"""
    
    def __init__(self, config_path: str = None):
        """Initialize dynamic universe manager"""
        
        # Load configuration
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "dynamic_universe_config.yaml"
        
        self.config = self._load_config(config_path)
        self.universe_config = self.config.get('gainer_loser_universe', {})
        self.analytics_config = self.config.get('universe_analytics', {})
        self.excel_config = self.config.get('excel_integration', {})
        
        # Initialize NSE connection
        if NSE_AVAILABLE:
            self.nse = Nse()
        else:
            self.nse = None
            logger.warning("NSE tools not available")
            
        # Cache for universe data
        self._last_update = None
        self._cached_universe = None
        self._refresh_interval = timedelta(minutes=self.universe_config.get('refresh_interval_minutes', 15))
        
        # Excel integration
        self._excel_file_path = None
        self._last_excel_update = None
        self._excel_force_update_interval = timedelta(hours=self.excel_config.get('force_update_interval_hours', 4))
        
        if self.excel_config.get('enabled', False) and XLWINGS_AVAILABLE:
            excel_file = self.excel_config.get('excel_file', 'MiniRobo.xlsx')
            self._excel_file_path = Path(__file__).parent.parent.parent / excel_file
            logger.info(f"Excel integration enabled: {self._excel_file_path}")
        elif self.excel_config.get('enabled', False) and not XLWINGS_AVAILABLE:
            logger.warning("Excel integration requested but xlwings not available")
        
        # Performance tracking
        self._universe_performance = {}
        
        logger.info("Dynamic Universe Manager initialized")
    
    def _load_config(self, config_path: Path) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}. Using defaults.")
            return self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}. Using defaults.")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            'gainer_loser_universe': {
                'max_gainers': 10,
                'max_losers': 5,
                'min_gap_percentage': 2.0,
                'max_gap_percentage': 8.0,
                'refresh_interval_minutes': 15,
                'trading_hours_only': True,
                'max_stocks_per_sector': 3,
                'exclude_sectors': ['REALTY', 'PSE'],
                'min_market_cap_cr': 1000,
                'prefer_liquid_stocks': True,
                'static_fallback': False,
                'fallback_symbols': ['SBIN', 'INFY', 'TCS', 'MARUTI', 'WIPRO']
            },
            'excel_integration': {
                'enabled': False,
                'excel_file': 'MiniRobo.xlsx',
                'universe_sheet': 'UNIVERSE',
                'merge_with_existing': True,
                'max_total_stocks': 150,
                'preserve_static_stocks': True,
                'dynamic_marker_column': 'SOURCE',
                'dynamic_marker_value': 'DYNAMIC',
                'static_marker_value': 'MANUAL',
                'update_on_universe_refresh': True,
                'force_update_interval_hours': 4
            },
            'universe_analytics': {
                'track_performance': True,
                'min_success_rate': 60.0,
                'rebalance_threshold': 50.0
            }
        }
    
    def get_current_universe(self) -> Mapping[str, List[Dict[str, Any]]]:
        """
        Get current trading universe with latest data
        
        Returns:
            Dictionary with 'gainers' and 'losers' lists
        """
        current_time = datetime.now()
        
        # Check if we need to refresh
        # if (self._last_update is None or 
        #     current_time - self._last_update > self._refresh_interval or
        #     self._cached_universe is None):
            
        self._update_universe()
        
        # Update Excel if configured and needed
        if (self.excel_config.get('enabled', False) and 
            self.excel_config.get('update_on_universe_refresh', True) and
            self._excel_file_path and XLWINGS_AVAILABLE):
            self._update_excel_universe()
        
        return  None if self._cached_universe is None else self._cached_universe
    
    def _update_universe(self) -> None:
        """Update universe with fresh NSE data"""
        try:
            if not NSE_AVAILABLE or not self.nse:
                logger.warning("NSE not available, using fallback universe")
                #self._cached_universe = self._get_fallback_universe()
                return
            
            # Check trading hours if configured
            # if self.universe_config.get('trading_hours_only', True):
            #     if not self._is_trading_hours():
            #         logger.info("Outside trading hours, keeping cached universe")
            #         return
            
            logger.info("Updating dynamic universe from NSE...")
            
            # Fetch raw data
            raw_gainers = self.nse.get_top_gainers()
            raw_losers = self.nse.get_top_losers()
            
            # Process and filter data
            gainers = self._process_universe_data(raw_gainers, 'GAINER')
            losers = self._process_universe_data(raw_losers, 'LOSER')
            
            # Apply limits
            max_gainers = self.universe_config.get('max_gainers', 10)
            max_losers = self.universe_config.get('max_losers', 5)
            
            self._cached_universe = {
                'gainers': gainers[:max_gainers],
                'losers': losers[:max_losers],
                'update_time': datetime.now(),
                'data_source': 'Live NSE'
            }
            
            self._last_update = datetime.now()
            
            logger.info(f"Universe updated: {len(gainers)} gainers, {len(losers)} losers")
            
        except Exception as e:
            logger.error(f"Error updating universe: {e}")
            if not self._cached_universe:
                self._cached_universe = self._get_fallback_universe()
    
    def _process_universe_data(self, raw_data: List[Dict], signal_type: str) -> List[Dict[str, Any]]:
        """Process and filter raw NSE data"""
        if raw_data is None or (hasattr(raw_data, 'empty') and raw_data.empty) or len(raw_data) == 0:
            return []
        
        processed = []
        sector_counts = {}
        
    def _process_universe_data(self, raw_data, signal_type: str) -> List[Dict[str, Any]]:
        """Process and filter raw NSE data"""
        if raw_data is None or (hasattr(raw_data, 'empty') and raw_data.empty) or len(raw_data) == 0:
            return []
        
        processed = []
        sector_counts = {}
        
        # Handle pandas DataFrame from nsetools
        if hasattr(raw_data, 'iterrows'):
            # It's a pandas DataFrame
            for index, row in raw_data.iterrows():
                try:
                    # Convert pandas Series to dict-like access
                    item = row.to_dict()
                    processed_item = self._process_single_stock_data(item, signal_type, sector_counts)
                    if processed_item:
                        processed.append(processed_item)
                except Exception as e:
                    logger.warning(f"Error processing DataFrame row {index}: {e}")
                    continue
        else:
            # It's a list or other iterable
            for item in raw_data:
                try:
                    processed_item = self._process_single_stock_data(item, signal_type, sector_counts)
                    if processed_item:
                        processed.append(processed_item)
                except Exception as e:
                    logger.warning(f"Error processing item {item}: {e}")
                    continue
        
        return processed
    
    def _process_single_stock_data(self, item: Dict, signal_type: str, sector_counts: Dict) -> Optional[Dict[str, Any]]:
        """Process a single stock data item"""
        print(f"Processing item: {item}")
        try:
            # Extract data - handle both dict keys and DataFrame column names
            symbol = str(item.get('symbol', item.get('Symbol', ''))).replace(' ', '').upper()
            prev_price = float(item.get('prev_price', item.get('previousClose', item.get('prevPrice', 0))))
            open_price = float(item.get('open_price', item.get('open', item.get('openPrice', 0))))
            ltp = float(item.get('ltp', item.get('lastPrice', item.get('LTP', open_price))))
            volume = float(item.get('trade_quantity', item.get('totalTradedVolume', item.get('volume', 0))))
            
            if prev_price <= 0 or open_price <= 0:
                return None
            
            # Calculate gap
            gap_amount = open_price - prev_price
            gap_pct = (gap_amount / prev_price) * 100
            
            # # Apply gap filters
            # abs_gap = abs(gap_pct)
            # min_gap = self.universe_config.get('min_gap_percentage', 2.0)
            # max_gap = self.universe_config.get('max_gap_percentage', 8.0)
            
            # if abs_gap < min_gap or abs_gap > max_gap:
            #     return None
            
            # Sector diversification
            sector = item.get('sector', item.get('industry', 'UNKNOWN'))
            max_per_sector = self.universe_config.get('max_stocks_per_sector', 3)
            
            if sector in sector_counts:
                if sector_counts[sector] >= max_per_sector:
                    return None
            else:
                sector_counts[sector] = 0
            
            # Exclude certain sectors
            exclude_sectors = self.universe_config.get('exclude_sectors', [])
            if sector in exclude_sectors:
                return None
            
            # Add to processed list
            processed_item = {
                'symbol': symbol,
                'prev_price': prev_price,
                'open_price': open_price,
                'ltp': ltp,
                'gap_pct': gap_pct,
                'gap_amount': gap_amount,
                'volume': volume,
                'sector': sector,
                'signal_type': signal_type,
                'quality_score': self._calculate_quality_score(item, gap_pct)
            }
            
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
            return processed_item
            
        except Exception as e:
            logger.warning(f"Error processing {signal_type} item: {e}")
            return None
    
    def _calculate_quality_score(self, item: Dict, gap_pct: float) -> float:
        """Calculate quality score for ranking stocks"""
        score = 0.0
        
        # Gap size component (moderate gaps preferred)
        abs_gap = abs(gap_pct)
        if 3.0 <= abs_gap <= 6.0:  # Sweet spot
            score += 50
        elif 2.0 <= abs_gap < 3.0 or 6.0 < abs_gap <= 8.0:
            score += 30
        else:
            score += 10
        
        # Volume component (prefer high volume)
        volume = float(item.get('volume', 0))
        if volume > 1000000:  # High volume
            score += 30
        elif volume > 500000:  # Medium volume
            score += 20
        else:
            score += 10
        
        # Price component (avoid penny stocks)
        ltp = float(item.get('ltp', 0))
        if ltp > 100:  # Good price range
            score += 20
        elif ltp > 50:
            score += 15
        else:
            score += 5
        
        return score
    
    def _is_trading_hours(self) -> bool:
        """Check if current time is within trading hours"""
        now = datetime.now().time()
        return time(9, 15) <= now <= time(15, 30)
    
    def _get_fallback_universe(self) -> Dict[str, Union[List[Dict[str, Any]], datetime, str]]:
        """Get fallback universe when NSE data unavailable"""
        fallback_symbols = self.universe_config.get('fallback_symbols', [])
        
        # Create mock data for fallback
        gainers = []
        losers = []
        
        for symbol in fallback_symbols[:5]:
            gainers.append({
                'symbol': symbol,
                'prev_price': 100.0,
                'open_price': 103.0,
                'ltp': 102.5,
                'gap_pct': 3.0,
                'gap_amount': 3.0,
                'volume': 1000000,
                'sector': 'FALLBACK',
                'signal_type': 'GAINER',
                'quality_score': 50.0
            })
        
        for symbol in fallback_symbols[5:]:
            losers.append({
                'symbol': symbol,
                'prev_price': 100.0,
                'open_price': 97.0,
                'ltp': 97.5,
                'gap_pct': -3.0,
                'gap_amount': -3.0,
                'volume': 1000000,
                'sector': 'FALLBACK',
                'signal_type': 'LOSER',
                'quality_score': 50.0
            })
        
        return {
            'gainers': gainers,
            'losers': losers,
            'update_time': datetime.now(),
            'data_source': 'Static Fallback'
        }
    
    def get_universe_stats(self) -> Dict[str, Any]:
        """Get statistics about current universe"""
        universe = self.get_current_universe()
        
        if not universe:
            return {}
        
        gainers = universe.get('gainers', [])
        losers = universe.get('losers', [])
        
        # Calculate stats
        gainer_gaps = [g['gap_pct'] for g in gainers]
        loser_gaps = [abs(l['gap_pct']) for l in losers]
        
        return {
            'total_stocks': len(gainers) + len(losers),
            'gainers_count': len(gainers),
            'losers_count': len(losers),
            'avg_gainer_gap': sum(gainer_gaps) / len(gainer_gaps) if gainer_gaps else 0,
            'avg_loser_gap': sum(loser_gaps) / len(loser_gaps) if loser_gaps else 0,
            'max_gainer_gap': max(gainer_gaps) if gainer_gaps else 0,
            'max_loser_gap': max(loser_gaps) if loser_gaps else 0,
            'update_time': universe.get('update_time'),
            'data_source': universe.get('data_source'),
            'sectors_covered': len(set([s.get('sector') for s in gainers + losers])),
        }
    
    def update_config(self, new_config: Dict[str, Any]) -> bool:
        """Update configuration dynamically"""
        try:
            self.universe_config.update(new_config.get('gainer_loser_universe', {}))
            self.analytics_config.update(new_config.get('universe_analytics', {}))
            
            # Force refresh with new config
            self._cached_universe = None
            self._last_update = None
            
            logger.info("Dynamic universe configuration updated")
            return True
        except Exception as e:
            logger.error(f"Error updating config: {e}")
            return False
    
    def _update_excel_universe(self) -> bool:
        """Update MiniRobo.xlsx with current dynamic universe"""
        try:
            if not self._excel_file_path or not self._excel_file_path.exists():
                logger.warning(f"Excel file not found: {self._excel_file_path}")
                return False
            
            # Check if we need to force update
            force_update = (self._last_excel_update is None or 
                           datetime.now() - self._last_excel_update > self._excel_force_update_interval)
            
            if not force_update:
                logger.debug("Excel update not needed yet")
                return True
            
            logger.info("Updating Excel universe with dynamic data...")
            
            # Get current universe
            universe = self._cached_universe
            if not universe or not (universe.get('gainers') or universe.get('losers')):
                logger.info("No universe data available for Excel update")
                return False
            
            logger.info(f"Preparing to update Excel with {len(universe)} stocks")  
            # Prepare dynamic stocks data
            dynamic_stocks = self._prepare_excel_data(universe)
            
            logger.info(f"Updating {len(dynamic_stocks)} stocks in Excel...")
            # Update Excel
            success = self._write_to_excel(dynamic_stocks)
            
            if success:
                self._last_excel_update = datetime.now()
                logger.info(f"Successfully updated Excel with {len(dynamic_stocks)} dynamic stocks")
            
            return success
            
        except Exception as e:
            logger.error(f"Error updating Excel universe: {e}")
            return False
    
    def _prepare_excel_data(self, universe: Dict[str, Any]) -> pd.DataFrame:
        """Prepare universe data for Excel format"""
        dynamic_stocks = []
        
        # Process gainers
        for gainer in universe.get('gainers', []):
            dynamic_stocks.append({
                'SYMBOL': gainer['symbol'],
                'ENABLED': 'YES',
                'SECTOR': gainer.get('sector', 'UNKNOWN'),
                'SOURCE': self.excel_config.get('dynamic_marker_value', 'DYNAMIC'),
                'GAP_PCT': gainer.get('gap_pct', 0),
                'QUALITY_SCORE': gainer.get('quality_score', 0),
                'SIGNAL_TYPE': 'GAINER',
                'LAST_UPDATED': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        
        # Process losers
        for loser in universe.get('losers', []):
            dynamic_stocks.append({
                'SYMBOL': loser['symbol'],
                'ENABLED': 'YES',
                'SECTOR': loser.get('sector', 'UNKNOWN'),
                'SOURCE': self.excel_config.get('dynamic_marker_value', 'DYNAMIC'),
                'GAP_PCT': loser.get('gap_pct', 0),
                'QUALITY_SCORE': loser.get('quality_score', 0),
                'SIGNAL_TYPE': 'LOSER',
                'LAST_UPDATED': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return pd.DataFrame(dynamic_stocks)
    
    def _write_to_excel(self, dynamic_stocks: pd.DataFrame) -> bool:
        """Write dynamic stocks to Excel file"""
        try:
            print(dynamic_stocks)    # Ensure DataFrame is not empty

            with xw.App(visible=False) as app:
                wb = app.books.open(str(self._excel_file_path))
                
                try:
                    sheet_name = self.excel_config.get('universe_sheet', 'UNIVERSE')
                    
                    # Get or create sheet
                    try:
                        sheet = wb.sheets[sheet_name]
                    except:
                        logger.info(f"Creating new sheet: {sheet_name}")
                        sheet = wb.sheets.add(sheet_name)
                    
                    # Handle merge with existing data
                    if self.excel_config.get('merge_with_existing', True):
                        existing_df = self._read_existing_excel_data(sheet)
                        merged_df = self._merge_universe_data(existing_df, dynamic_stocks)
                    else:
                        merged_df = dynamic_stocks
                    
                    # Apply limits
                    max_stocks = self.excel_config.get('max_total_stocks', 150)
                    if len(merged_df) > max_stocks:
                        # Keep static stocks, then top dynamic by quality score
                        static_marker = self.excel_config.get('static_marker_value', 'MANUAL')
                        static_stocks = merged_df[merged_df.get('SOURCE', '') == static_marker]
                        dynamic_only = merged_df[merged_df.get('SOURCE', '') != static_marker]
                        
                        # Sort dynamic by quality score
                        dynamic_sorted = dynamic_only.sort_values('QUALITY_SCORE', ascending=False)
                        
                        remaining_slots = max_stocks - len(static_stocks)
                        if remaining_slots > 0:
                            top_dynamic = dynamic_sorted.head(remaining_slots)
                            merged_df = pd.concat([static_stocks, top_dynamic], ignore_index=True)
                        else:
                            merged_df = static_stocks.head(max_stocks)
                    
                    # Clear sheet and write data
                    sheet.clear()
                    
                    if not merged_df.empty:
                        # Write headers and data
                        sheet.range('A1').options(index=False, header=True).value = merged_df
                        
                        # Auto-fit columns
                        sheet.autofit()
                        
                        # Add update timestamp
                        last_row = len(merged_df) + 3
                        sheet.range(f'A{last_row}').value = f"Last Dynamic Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        
                        # Color-code dynamic vs static stocks
                        self._apply_excel_formatting(sheet, merged_df)
                    
                    # Save file
                    wb.save()
                    return True
                    
                finally:
                    wb.close()
                    
        except Exception as e:
            logger.error(f"Error writing to Excel: {e}")
            return False
    
    def _read_existing_excel_data(self, sheet) -> pd.DataFrame:
        """Read existing data from Excel sheet"""
        try:
            # Read existing universe table
            universe_range = sheet.range('A1').expand()
            df = universe_range.options(pd.DataFrame, header=1, index=False).value
            
            if df is None or df.empty:
                return pd.DataFrame()
            
            # Clean and validate
            df = df.dropna(subset=['SYMBOL'])
            df['SYMBOL'] = df['SYMBOL'].astype(str).str.strip().str.upper()
            
            # Add SOURCE column if missing
            if 'SOURCE' not in df.columns:
                static_marker = self.excel_config.get('static_marker_value', 'MANUAL')
                df['SOURCE'] = static_marker
            
            return df
            
        except Exception as e:
            logger.warning(f"Error reading existing Excel data: {e}")
            return pd.DataFrame()
    
    def _merge_universe_data(self, existing_df: pd.DataFrame, dynamic_df: pd.DataFrame) -> pd.DataFrame:
        """Merge existing and dynamic universe data"""
        try:
            if existing_df.empty:
                return dynamic_df
            
            if dynamic_df.empty:
                return existing_df
            
            # Preserve static stocks if configured
            if self.excel_config.get('preserve_static_stocks', True):
                static_marker = self.excel_config.get('static_marker_value', 'MANUAL')
                dynamic_marker = self.excel_config.get('dynamic_marker_value', 'DYNAMIC')
                
                # Keep all static stocks
                static_stocks = existing_df[existing_df.get('SOURCE', static_marker) == static_marker]
                
                # Remove old dynamic stocks
                static_symbols = set(static_stocks['SYMBOL'].str.upper())
                
                # Add new dynamic stocks (avoiding duplicates with static)
                new_dynamic = dynamic_df[~dynamic_df['SYMBOL'].str.upper().isin(static_symbols)].copy()
                
                # Combine
                merged_df = pd.concat([static_stocks, new_dynamic], ignore_index=True)
            else:
                # Simple replacement - remove old dynamic, add new
                dynamic_marker = self.excel_config.get('dynamic_marker_value', 'DYNAMIC')
                non_dynamic = existing_df[existing_df.get('SOURCE', '') != dynamic_marker]
                merged_df = pd.concat([non_dynamic, dynamic_df], ignore_index=True)
            
            # Remove duplicates (prioritize newest)
            merged_df = merged_df.drop_duplicates(subset=['SYMBOL'], keep='last')
            
            return merged_df
            
        except Exception as e:
            logger.error(f"Error merging universe data: {e}")
            return dynamic_df
    
    def _apply_excel_formatting(self, sheet, df: pd.DataFrame):
        """Apply formatting to distinguish dynamic vs static stocks"""
        try:
            dynamic_marker = self.excel_config.get('dynamic_marker_value', 'DYNAMIC')
            
            # Find SOURCE column
            source_col_idx = None
            for i, col in enumerate(df.columns):
                if col == 'SOURCE':
                    source_col_idx = i + 1  # xlwings uses 1-based indexing
                    break
            
            if source_col_idx is None:
                return
            
            # Apply light green background to dynamic stocks
            for row_idx in range(2, len(df) + 2):  # Skip header row
                source_value = sheet.range(f'{chr(64 + source_col_idx)}{row_idx}').value
                if source_value == dynamic_marker:
                    # Light green background for entire row
                    row_range = sheet.range(f'A{row_idx}:{chr(64 + len(df.columns))}{row_idx}')
                    row_range.color = (220, 255, 220)  # Light green
                    
        except Exception as e:
            logger.warning(f"Error applying Excel formatting: {e}")
    
    def force_excel_update(self) -> bool:
        """Force immediate Excel update regardless of timing"""
        if not self.excel_config.get('enabled', False) or not XLWINGS_AVAILABLE:
            logger.warning("Excel integration not available")
            return False
        
        self._last_excel_update = None  # Reset to force update
        return self._update_excel_universe()
    
    def get_excel_stats(self) -> Dict[str, Any]:
        """Get statistics about Excel integration"""
        return {
            'excel_integration_enabled': self.excel_config.get('enabled', False),
            'xlwings_available': XLWINGS_AVAILABLE,
            'excel_file_path': str(self._excel_file_path) if self._excel_file_path else None,
            'excel_file_exists': self._excel_file_path.exists() if self._excel_file_path else False,
            'last_excel_update': self._last_excel_update.isoformat() if self._last_excel_update else None,
            'next_forced_update': (self._last_excel_update + self._excel_force_update_interval).isoformat() 
                                if self._last_excel_update else 'Immediate',
            'update_on_refresh': self.excel_config.get('update_on_universe_refresh', True),
            'merge_with_existing': self.excel_config.get('merge_with_existing', True),
            'preserve_static_stocks': self.excel_config.get('preserve_static_stocks', True)
        }