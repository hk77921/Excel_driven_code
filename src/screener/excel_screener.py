"""
Excel-Driven Screener - Production Ready
=======================================
Professional-grade screener using xlwings for Excel integration.

Features:
- MiniRobo.xlsx integration with xlwings
- Technical analysis (ADX, ATR, Volume, Trend)
- Market regime detection
- Batch data fetching with caching
- Normalized scoring system
- Relative strength vs NIFTY
"""

import pandas as pd
import pandas_ta as ta
import yfinance as yf
import xlwings as xw
from datetime import datetime, date, timedelta
import logging
from pathlib import Path
import pickle
import os
from typing import Dict, List, Optional, Tuple, Any
from tqdm import tqdm
import numpy as np

from ..core.models import ScreenerSignal


logger = logging.getLogger(__name__)


class ExcelScreener:
    """
    Excel-driven screener with xlwings integration.
    
    Reads configuration from MiniRobo.xlsx and produces
    screener signals for the trading engine.
    """
    
    def __init__(
        self, 
        excel_file: str = "MiniRobo.xlsx",
        cache_dir: str = "screener_cache"
    ):
        """
        Initialize Excel screener.
        
        Args:
            excel_file: Path to MiniRobo.xlsx file
            cache_dir: Directory for caching market data
        """
        self.excel_file = excel_file
        self.cache_dir = cache_dir
        
        # Create cache directory
        Path(cache_dir).mkdir(exist_ok=True)
        
        # Configuration sheets
        self.universe_sheet = "UNIVERSE"
        self.rules_sheet = "SCREENER_RULES"
        self.sector_sheet = "SECTOR_MAP"
        self.output_sheet = "SCREENER_OUTPUT"
        
        # Constants
        self.lookback_days = 60
        self.index_symbol = "^NSEI"
        self.min_required_bars = 30
        self.volume_rolling_window = 20
        self.atr_rolling_window = 14
        self.rsi_rolling_window = 14
        
        # Scoring weights
        self.score_weights = {
            "atr": 0.30,
            "adx": 0.30,
            "volume": 0.20,
            "trend": 0.20
        }
        
        # Default rules
        self.default_rules = {
            "MIN_ADTV_CR": 2.0,      # Reduced from 5.0 (allows mid-cap stocks)
            "MIN_ATR_PCT": 1.5,      # Reduced from 2.0 (more volatile)
            "MAX_ATR_PCT": 6.0,      # Increased from 5.0 (allows more volatility)
            "MIN_ADX": 15.0,         # Reduced from 20.0 (allows weaker trends)
            "MIN_VOL_RATIO": 0.8,    # Reduced from 1.0 (less volume strict)
            "MAX_TRADES_PER_DAY": 5,
            "TREND_REQUIRED": "ANY"  # Changed from "BULLISH" (allows bearish too)
        }
        
        logger.info(f"Excel screener initialized: {excel_file}")
    
    # ====== EXCEL INTEGRATION ======
    
    def load_rules(self) -> Dict[str, Any]:
        """Load screener rules from Excel using xlwings"""
        try:
            with xw.App(visible=False) as app:
                wb = app.books.open(self.excel_file)
                try:
                    sheet = wb.sheets[self.rules_sheet]
                    
                    # Read rules table
                    rules_range = sheet.range('A1').expand()
                    df = rules_range.options(pd.DataFrame, header=1, index=False).value
                    
                    if df is None or df.empty or 'RULE' not in df.columns:
                        logger.warning("SCREENER_RULES sheet invalid, using defaults")
                        return self.default_rules.copy()
                    
                    # Convert to dict
                    rules = dict(zip(df['RULE'], df['VALUE']))
                    
                    # Validate and normalize
                    normalized_rules = self._normalize_rules(rules)
                    
                    logger.info(f"Loaded {len(normalized_rules)} screener rules")
                    return normalized_rules
                    
                finally:
                    wb.close()
                    
        except Exception as e:
            logger.error(f"Failed to load rules from Excel: {e}")
            return self.default_rules.copy()
    
    def load_universe(self) -> pd.DataFrame:
        """Load stock universe from Excel using xlwings"""
        try:
            with xw.App(visible=False) as app:
                wb = app.books.open(self.excel_file)
                try:
                    sheet = wb.sheets[self.universe_sheet]
                    
                    # Read universe table
                    universe_range = sheet.range('A1').expand()
                    df = universe_range.options(pd.DataFrame, header=1, index=False).value
                    
                    if df is None or df.empty:
                        logger.error("UNIVERSE sheet is empty")
                        return pd.DataFrame()
                    
                    # Validate required columns
                    required_cols = ["SYMBOL", "ENABLED"]
                    missing = [c for c in required_cols if c not in df.columns]
                    if missing:
                        logger.error(f"Missing columns in UNIVERSE: {missing}")
                        return pd.DataFrame()
                    
                    # Clean and filter
                    df["ENABLED"] = df["ENABLED"].astype(str).str.upper()
                    df = df[df["ENABLED"] == "YES"]
                    df = df.dropna(subset=["SYMBOL"])
                    df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip().str.upper()
                    df = df.drop_duplicates(subset=["SYMBOL"])
                    
                    logger.info(f"Loaded {len(df)} enabled stocks from universe")
                    return df
                    
                finally:
                    wb.close()
                    
        except Exception as e:
            logger.error(f"Failed to load universe from Excel: {e}")
            return pd.DataFrame()
    
    def load_sector_map(self) -> Dict[str, str]:
        """Load sector mapping from Excel using xlwings"""
        try:
            with xw.App(visible=False) as app:
                wb = app.books.open(self.excel_file)
                try:
                    sheet = wb.sheets[self.sector_sheet]
                    
                    # Read sector mapping
                    sector_range = sheet.range('A1').expand()
                    df = sector_range.options(pd.DataFrame, header=1, index=False).value
                    
                    if df is None or df.empty or 'SYMBOL' not in df.columns:
                        logger.warning("SECTOR_MAP sheet invalid")
                        return {}
                    
                    sector_map = dict(zip(df['SYMBOL'], df.get('SECTOR', 'OTHERS')))
                    
                    logger.info(f"Loaded sector mapping for {len(sector_map)} symbols")
                    return sector_map
                    
                finally:
                    wb.close()
                    
        except Exception as e:
            logger.warning(f"Failed to load sector map: {e}")
            return {}
    
    def get_symbols_list(self) -> List[str]:
        """Get list of symbols from universe"""
        try:
            universe = self.load_universe()
            if universe.empty:
                return []
            return universe['SYMBOL'].tolist()
        except Exception as e:
            logger.error(f"Failed to get symbols list: {e}")
            return []
    
    def write_results_to_excel(self, results: pd.DataFrame):
        """Write screener results to Excel using xlwings"""
        try:
            with xw.App(visible=False) as app:
                wb = app.books.open(self.excel_file)
                try:
                    # Get or create output sheet
                    try:
                        sheet = wb.sheets[self.output_sheet]
                        sheet.clear()
                    except:
                        sheet = wb.sheets.add(self.output_sheet)
                    
                    if not results.empty:
                        # Write results
                        sheet.range('A1').options(index=False, header=True).value = results
                        
                        # Auto-fit columns
                        sheet.autofit()
                        
                        # Add timestamp
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        sheet.range('A1').offset(len(results) + 2, 0).value = f"Last Updated: {timestamp}"
                    
                    wb.save()
                    logger.info(f"Written {len(results)} results to Excel: {self.output_sheet}")
                    
                finally:
                    wb.close()
                    
        except Exception as e:
            logger.error(f"Failed to write results to Excel: {e}")
    
    def should_enter_trade(self, signal: ScreenerSignal) -> Tuple[bool, str]:
        """
        Additional entry filters for high-quality trades only.
        
        Requirements:
        1. Signal score >= 40/100 (good quality)
        2. RSI 50-70 (bullish, not overbought)
        3. Price above 20-day SMA (in uptrend)
        4. Volume > 1.2x average (conviction)
        5. Bullish market regime
        
        Returns:
            (should_enter, reason_if_rejected)
        """
        
        # 1. Check signal score
        if signal.score < 40:
            return False, f"Score {signal.score} too low (need 40+)"
        
        # 2. Check RSI (if available)
        if hasattr(signal, 'rsi') and signal.rsi:
            if signal.rsi < 50 or signal.rsi > 70:
                return False, f"RSI {signal.rsi} outside 50-70 range"
        
        # 3. Check price vs SMA20
        if hasattr(signal, 'price_vs_sma20') and signal.price_vs_sma20:
            if signal.price_vs_sma20 < 0:  # Price below SMA20
                return False, f"Price below SMA20 (downtrend)"
        
        # 4. Check volume
        if hasattr(signal, 'volume_ratio') and signal.volume_ratio:
            if signal.volume_ratio < 1.2:
                return False, f"Volume ratio {signal.volume_ratio} too low"
        
        # 5. Check market regime
        if hasattr(signal, 'market_trend') and signal.market_trend:
            if signal.market_trend == "BEARISH":
                return False, "Bearish market regime - skip entry"
        
        return True, ""



    # ====== HELPER METHODS ======
    
    def _normalize_rules(self, rules: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and validate rules"""
        normalized = self.default_rules.copy()
        
        for key, value in rules.items():
            try:
                if key in ["MIN_ADTV_CR", "MIN_ATR_PCT", "MAX_ATR_PCT", "MIN_ADX", "MIN_VOL_RATIO"]:
                    normalized[key] = float(value)
                elif key == "MAX_TRADES_PER_DAY":
                    normalized[key] = int(value)
                elif key == "TREND_REQUIRED":
                    normalized[key] = str(value).upper()
                else:
                    normalized[key] = value
            except (ValueError, TypeError):
                logger.warning(f"Invalid rule value for {key}: {value}")
        
        return normalized
    
    # ====== DATA FETCHING & CACHING ======
    
    def _get_cache_path(self, symbol: str, data_type: str = "ohlcv") -> str:
        """Get cache file path for symbol"""
        today = date.today().strftime("%Y%m%d")
        return os.path.join(self.cache_dir, f"{symbol}_{data_type}_{today}.pkl")
    
    def _load_from_cache(self, symbol: str, data_type: str = "ohlcv") -> Optional[pd.DataFrame]:
        """Load data from cache if available"""
        cache_path = self._get_cache_path(symbol, data_type)
        
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception as e:
                logger.debug(f"Cache read failed for {symbol}: {e}")
        
        return None
    
    def _save_to_cache(self, symbol: str, data: pd.DataFrame, data_type: str = "ohlcv"):
        """Save data to cache"""
        cache_path = self._get_cache_path(symbol, data_type)
        
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.debug(f"Cache write failed for {symbol}: {e}")
    
    def fetch_ohlcv(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data for a symbol with caching"""
        # Try cache first
        cached_data = self._load_from_cache(symbol)
        if cached_data is not None:
            return cached_data
        
        try:
            # Fetch from yfinance
            ticker = f"{symbol}.NS" if not symbol.endswith('.NS') else symbol
            df = yf.download(
                ticker,
                period=f"{self.lookback_days}d",
                interval="1d",
                progress=False,
                auto_adjust=False
            )
            
            if df is None or df.empty:
                logger.debug(f"{symbol}: No data returned from Yahoo Finance")
                return None
            
            # Clean data
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            
            df = df.reset_index()
            df.columns = df.columns.str.lower()
            
            # Cache the data
            self._save_to_cache(symbol, df)
            
            return df
            
        except Exception as e:
            # Handle specific Yahoo Finance errors more gracefully
            error_msg = str(e)
            if "possibly delisted" in error_msg or "No data found" in error_msg:
                logger.warning(f"{symbol}: Possibly delisted or suspended (Yahoo Finance error)")
            else:
                logger.debug(f"Failed to fetch data for {symbol}: {e}")
            return None
    
    def fetch_bulk_ohlcv(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """Fetch OHLCV data for multiple symbols with batch processing"""
        results = {}
        
        for symbol in symbols:
            df = self.fetch_ohlcv(symbol)
            if df is not None:
                results[symbol] = df
        
        logger.info(f"Successfully fetched data for {len(results)}/{len(symbols)} symbols")
        return results
    
    # ====== TECHNICAL ANALYSIS ======
    
    def calculate_metrics(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        index_df: Optional[pd.DataFrame], 
        rules: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Calculate all technical metrics for a symbol"""
        try:
            if len(df) < self.min_required_bars:
                logger.info(f"{symbol}: Insufficient bars {len(df)} < {self.min_required_bars}")
                return None
            
            logger.debug(f"{symbol}: Processing {len(df)} bars")
            
            # Check columns
            required_cols = ['close', 'high', 'low', 'volume']
            missing_cols = [c for c in required_cols if c not in df.columns]
            if missing_cols:
                logger.info(f"{symbol}: Missing columns {missing_cols}. Available: {df.columns.tolist()}")
                return None
            
            # Current price
            current_price = df['close'].iloc[-1]
            
            # ATR calculations
            df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=self.atr_rolling_window)
            current_atr = df['atr'].iloc[-1]
            atr_pct = (current_atr / current_price) * 100
            
            # RSI calculations
            df['rsi'] = ta.rsi(df['close'], length=self.rsi_rolling_window)
            current_rsi = df['rsi'].iloc[-1]
           
            # Price vs SMA20
            df['sma20'] = ta.sma(df['close'], length=20)
            price_vs_sma20 = (current_price / df['sma20'].iloc[-1]) - 1

            # ADX - returns a DataFrame, take the ADX column
            adx_result = ta.adx(df['high'], df['low'], df['close'], length=14)
            df['adx'] = adx_result.iloc[:, 0]  # Take first column (ADX values)
            current_adx = df['adx'].iloc[-1]
            
            # Volume analysis
            df['vol_sma'] = df['volume'].rolling(self.volume_rolling_window).mean()
            recent_vol = df['volume'].iloc[-5:].mean()  # Last 5 days average
            baseline_vol = df['vol_sma'].iloc[-1]
            vol_ratio = recent_vol / baseline_vol if baseline_vol > 0 else 1.0
            
            # Average Daily Turnover (ADTV)
            avg_turnover = (df['close'] * df['volume']).iloc[-20:].mean()
            adtv_cr = avg_turnover / 10000000  # In crores
            
            # Trend analysis
            df['ema_20'] = ta.ema(df['close'], length=20)
            df['ema_50'] = ta.ema(df['close'], length=50)
            
            ema_20 = df['ema_20'].iloc[-1]
            ema_50 = df['ema_50'].iloc[-1]
            
            # Determine trend
            trend = "BULLISH" if current_price > ema_20 > ema_50 else "BEARISH"
            
            # Price position relative to EMAs
            near_ema20 = abs((current_price - ema_20) / current_price) < 0.02  # Within 2%
            
            # ATR contraction (volatility squeeze)
            atr_current = df['atr'].iloc[-1]
            atr_20_avg = df['atr'].iloc[-20:].mean()
            atr_contracting = atr_current < atr_20_avg * 0.8
            atr_expanding = ( df.close.iloc[-1] > max(df.high.iloc[-2], df.high.iloc[-3]) and df.volume.iloc[-1] > 1.5 * df.volume.rolling(20).mean().iloc[-1])


            
            # Relative strength vs index
            rel_strength = None
            if index_df is not None:
                rel_strength = self._calculate_relative_strength(df, index_df)
            
            metrics = {
                "symbol": symbol,
                "price": current_price,
                "atr": current_atr,
                "atr_pct": atr_pct,
                "adx": current_adx,
                "vol_ratio": vol_ratio,
                "adtv_cr": adtv_cr,
                "trend": trend,
                "near_ema20": near_ema20,
                "atr_contracting": atr_contracting,
                "atr_expanding": atr_expanding,
                "rel_strength": rel_strength,
                "ema_20": ema_20,
                "ema_50": ema_50,
                "rsi": current_rsi,
                "price_vs_sma20": price_vs_sma20
            }

            # logger.info(
            #         f"\n{'='*72}\n"
            #         f"{symbol} — TECHNICAL SNAPSHOT\n"
            #         f"{'-'*72}\n"
            #         f"PRICE ACTION\n"
            #         f"  Price            : {metrics['price']:.2f}\n"
            #         f"  Trend            : {metrics['trend']}\n"
            #         f"  EMA20 / EMA50    : {metrics['ema_20']:.2f} / {metrics['ema_50']:.2f}\n"
            #         f"  Near EMA20       : {metrics['near_ema20']}\n"
            #         f"  Price vs SMA20   : {metrics['price_vs_sma20']:.2f}\n\n"
            #         f"VOLATILITY\n"
            #         f"  ATR              : {metrics['atr']:.2f}\n"
            #         f"  ATR %            : {metrics['atr_pct']:.2f}\n"
            #         f"  ATR Squeeze      : {metrics['atr_contracting']}\n"
            #         f"  ATR Expansion    : {metrics['atr_expanding']}\n\n"
            #         f"MOMENTUM\n"
            #         f"  ADX              : {metrics['adx']:.2f}\n"
            #         f"  RSI              : {metrics['rsi']:.2f}\n\n"
            #         f"VOLUME & STRENGTH\n"
            #         f"  Volume Ratio     : {metrics['vol_ratio']:.2f}\n"
            #         f"  Relative Strength: {metrics['rel_strength']}\n"
            #         f"{'='*72}"
            #     )


            # logger.info(
            # f"{symbol} | "
            # f"ENTRY_CHECK → "
            # f"Squeeze:{metrics['atr_contracting']} | "
            # f"Expand:{metrics['atr_expanding']} | "
            # f"Vol:{metrics['vol_ratio']:.2f} | "
            # f"ADX:{metrics['adx']:.1f} | "
            # f"RSI:{metrics['rsi']:.1f} | "
            # f"RS:{metrics['rel_strength']} | "
            # f"NearEMA20:{metrics['near_ema20']} | "
            # f"PriceVsSMA20:{metrics['price_vs_sma20']:.2f}"
            # )


            
            return metrics
            
        except Exception as e:
            logger.info(f"Failed to calculate metrics for {symbol}: {e}")
            return None
    
    def _calculate_relative_strength(self, stock_df: pd.DataFrame, index_df: pd.DataFrame) -> Optional[float]:
        """Calculate relative strength vs index"""
        try:
            # Align dates
            stock_returns = stock_df['close'].pct_change().dropna()
            index_returns = index_df['close'].pct_change().dropna()
            
            if len(stock_returns) < 20 or len(index_returns) < 20:
                return None
            
            # Calculate 20-day relative performance using numpy for type safety
            stock_return_values = stock_returns.iloc[-20:].astype(float)
            index_return_values = index_returns.iloc[-20:].astype(float)
            
            # Calculate cumulative returns using numpy
            stock_perf = float(np.prod(stock_return_values + 1.0) - 1.0)
            index_perf = float(np.prod(index_return_values + 1.0) - 1.0)
            
            relative_strength = stock_perf - index_perf
            
            return float(relative_strength)
            
        except Exception as e:
            logger.debug(f"Relative strength calculation failed: {e}")
            return None
    
    # ====== FILTERING & SCORING ======
    
    
    
    def passes_filters(self, metrics: Dict[str, Any], rules: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if symbol passes all filters with detailed logging"""
        symbol = metrics.get("symbol", "UNKNOWN")
        failures = []
        
        try:
            # ADTV check
            if metrics["adtv_cr"] < rules["MIN_ADTV_CR"]:
                reason = f"ADTV {metrics['adtv_cr']:.1f} < {rules['MIN_ADTV_CR']}"
                failures.append(reason)
                logger.debug(f"{symbol} ❌ {reason}")
            
            # ATR percentage check
            if metrics["atr_pct"] < rules["MIN_ATR_PCT"]:
                reason = f"ATR% {metrics['atr_pct']:.2f} < MIN {rules['MIN_ATR_PCT']}"
                failures.append(reason)
                logger.debug(f"{symbol} ❌ {reason}")
            elif metrics["atr_pct"] > rules["MAX_ATR_PCT"]:
                reason = f"ATR% {metrics['atr_pct']:.2f} > MAX {rules['MAX_ATR_PCT']}"
                failures.append(reason)
                logger.debug(f"{symbol} ❌ {reason}")
            
            # ADX check
            if metrics["adx"] < rules["MIN_ADX"]:
                reason = f"ADX {metrics['adx']:.1f} < {rules['MIN_ADX']}"
                failures.append(reason)
                logger.debug(f"{symbol} ❌ {reason}")
            
            # Volume ratio check
            if metrics["vol_ratio"] < rules["MIN_VOL_RATIO"]:
                reason = f"Vol ratio {metrics['vol_ratio']:.2f} < {rules['MIN_VOL_RATIO']}"
                failures.append(reason)
                logger.debug(f"{symbol} ❌ {reason}")
            
            # Trend requirement
            if rules["TREND_REQUIRED"] != "ANY" and metrics["trend"] != rules["TREND_REQUIRED"]:
                reason = f"Trend {metrics['trend']} != {rules['TREND_REQUIRED']}"
                failures.append(reason)
                logger.debug(f"{symbol} ❌ {reason}")
            
            # If any failures, return first one
            if failures:
                return False, failures[0]
            
            # Passed all filters
            logger.debug(f"{symbol} ✅ PASSED ALL FILTERS")
            return True, "PASSED"
            
        except Exception as e:
            return False, f"Filter error: {e}"







    def calculate_score(self, metrics: Dict[str, Any]) -> float:
        """Calculate normalized score for the symbol"""
        try:
            # Normalize components to 0-100 scale
            atr_score = self._normalize_value(metrics["atr_pct"], 2.0, 5.0) * self.score_weights["atr"]
            adx_score = self._normalize_value(metrics["adx"], 20.0, 50.0) * self.score_weights["adx"] 
            vol_score = self._normalize_value(metrics["vol_ratio"], 1.0, 3.0) * self.score_weights["volume"]
            trend_score = (100 if metrics["trend"] == "BULLISH" else 0) * self.score_weights["trend"]
            
            base_score = atr_score + adx_score + vol_score + trend_score
            
            # Bonus points
            if metrics["atr_contracting"]:
                base_score += 5
            
            if metrics["near_ema20"]:
                base_score += 5
            
            if metrics["rel_strength"] is not None and metrics["rel_strength"] > 0:
                base_score += min(10, metrics["rel_strength"] * 200)  # Cap at 10 points
            
            return min(100, base_score)  # Cap at 100
            
        except Exception as e:
            logger.debug(f"Score calculation failed: {e}")
            return 0.0
    
    def _normalize_value(self, value: float, min_val: float, max_val: float) -> float:
        """Normalize value to 0-100 scale"""
        if value <= min_val:
            return 0.0
        elif value >= max_val:
            return 100.0
        else:
            return ((value - min_val) / (max_val - min_val)) * 100.0
    
    def build_reasons(self, metrics: Dict[str, Any], rules: Dict[str, Any]) -> str:
        """Build comma-separated list of positive signals"""
        reasons = []
        
        if metrics["atr_contracting"]:
            reasons.append("ATR_SQUEEZE")
        
        if metrics["near_ema20"]:
            reasons.append("NEAR_EMA20")
        
        if metrics["trend"] == "BULLISH":
            reasons.append("BULLISH_TREND")
        
        if metrics["vol_ratio"] > 1.5:
            reasons.append("HIGH_VOLUME")
        
        if metrics["adx"] > 30:
            reasons.append("STRONG_TREND")
        
        if metrics["rel_strength"] is not None and metrics["rel_strength"] > 0.01:
            reasons.append("OUTPERFORMING")
        
        return ",".join(reasons) if reasons else "BASIC_CRITERIA"
    
    # ====== MARKET REGIME ======
    
    def get_market_trend(self) -> str:
        """Determine overall market trend using NIFTY"""
        try:
            # Fetch index data
            index_df = yf.download(
                self.index_symbol,
                period="90d",
                interval="1d",
                progress=False,
                auto_adjust=False
            )
            
            if index_df is None or index_df.empty:
                return "UNKNOWN"
            
            # Clean data
            if isinstance(index_df.columns, pd.MultiIndex):
                index_df.columns = index_df.columns.droplevel(1)
            
            # Normalize column names to lowercase for consistency
            index_df.columns = index_df.columns.str.lower()
            
            # Calculate EMAs
            index_df['ema_20'] = ta.ema(index_df['close'], length=20)
            index_df['ema_50'] = ta.ema(index_df['close'], length=50)
            
            current_price = index_df['close'].iloc[-1]
            ema_20 = index_df['ema_20'].iloc[-1]
            ema_50 = index_df['ema_50'].iloc[-1]
            
            # Determine trend
            if current_price > ema_20 > ema_50:
                return "BULLISH"
            elif current_price < ema_20 < ema_50:
                return "BEARISH"
            else:
                return "SIDEWAYS"
                
        except Exception as e:
            logger.warning(f"Market trend calculation failed: {e}")
            return "UNKNOWN"
    
    def adjust_max_trades(self, market_trend: str, base_max: int) -> int:
        """Adjust max trades based on market regime"""
        if market_trend == "BEARISH":
            return max(1, int(base_max * 0.5))  # 50% of normal
        elif market_trend == "SIDEWAYS":
            return max(2, int(base_max * 0.7))  # 70% of normal
        else:  # BULLISH or UNKNOWN
            return base_max
    
    # ====== MAIN SCREENING METHOD ======
    
    def run_screener(self) -> List[ScreenerSignal]:
        """
        Run the complete screening process.
        
        Returns:
            List of ScreenerSignal objects for eligible stocks
        """
        logger.info("=" * 60)
        logger.info("STARTING EXCEL-DRIVEN SCREENER")
        logger.info("=" * 60)
        
        # Load configuration
        rules = self.load_rules()
        #logger.info(f"Screener Rules: {rules}")
        logger.info("\n ACTIVE FILTER RULES:")
        # for key, value in rules.items():
        #     logger.info(f"   {key}: {value}")


        universe = self.load_universe()
        
        if universe.empty:
            logger.error("No stocks in universe. Check UNIVERSE sheet.")
            return []
        
        sector_map = self.load_sector_map()
        
        # Market regime
        market_trend = self.get_market_trend()
        logger.info(f"Market Trend: {market_trend}")
        
        # Fetch all data
        symbols = universe["SYMBOL"].tolist()
        bulk_data = self.fetch_bulk_ohlcv(symbols)
        
        logger.info(f"Bulk data received: {len(bulk_data)} symbols with data")
        
        if not bulk_data:
            logger.error("No market data fetched. Check network/symbols.")
            return []
        
        # Fetch index data for relative strength
        index_df = None
        try:
            index_df = yf.download(
                self.index_symbol,
                period="180d",
                interval="1d", 
                progress=False,
                auto_adjust=False
            )
            if index_df is not None and isinstance(index_df.columns, pd.MultiIndex):
                index_df.columns = index_df.columns.droplevel(1)
            if index_df is None or index_df.empty:
                index_df = None
        except:
            logger.warning("Index data unavailable - relative strength disabled")
            index_df = None
        
        # Screen each stock
        results = []
        signals = []
        rejected_count = 0
        metrics_calculated = 0
        insufficient_bars = 0
        rejection_stats = {}
        
        logger.info(f"Starting screening of {len(symbols)} symbols. Bulk data has {len(bulk_data)} entries")
        
        missing_data = 0
        for symbol in symbols:
            df = bulk_data.get(symbol)
            if df is None:
                missing_data += 1
                continue
            
            # Check if sufficient data
            if len(df) < self.min_required_bars:
                insufficient_bars += 1
                logger.info(f"{symbol}: Only {len(df)} bars (need {self.min_required_bars})")
                continue
            
            # Calculate metrics
            metrics = self.calculate_metrics(df, symbol, index_df, rules)
            if metrics is None:
                logger.debug(f"{symbol}: Failed to calculate metrics")
                continue
            
            metrics_calculated += 1
            
            # Apply filters
            passed, reason = self.passes_filters(metrics, rules)
            if not passed:
                rejected_count += 1
                rejection_stats[reason] = rejection_stats.get(reason, 0) + 1
                logger.debug(f"{symbol} REJECTED: {reason}")
                continue
            
            # Calculate score and build reasons
            score = self.calculate_score(metrics)
            reasons = self.build_reasons(metrics, rules)
            
            # Add to results for Excel output
            results.append({
                "SYMBOL": symbol,
                "SECTOR": sector_map.get(symbol, "OTHERS"),
                "PRICE": round(metrics["price"], 2),
                "ATR_PCT": round(metrics["atr_pct"], 2),
                "ADX": round(metrics["adx"], 2),
                "VOL_RATIO": round(metrics["vol_ratio"], 2),
                "ADTV_CR": round(metrics["adtv_cr"], 2),
                "TREND": metrics["trend"],
                "SCORE": round(score, 2),
                "REASONS": reasons,
                "REL_STRENGTH": round(metrics["rel_strength"], 4) if metrics["rel_strength"] else None,
                "ELIGIBLE": "YES"
            })
            
            
            # Create ScreenerSignal for trading engine
            signal = ScreenerSignal(
                symbol=symbol,
                price=metrics["price"],
                atr=metrics["atr"],
                adx=metrics["adx"],
                volume_ratio=metrics["vol_ratio"],
                trend=metrics["trend"],
                score=score,
                sector=sector_map.get(symbol, "OTHERS"),
                reasons=reasons,
                timestamp=datetime.now()
            )
            signals.append(signal)
        

        # Log rejection statistics
        logger.info("\n📊 REJECTION STATISTICS:")
        logger.info(f"   Total Processed: {metrics_calculated}")
        logger.info(f"   Passed: {len(results)}")
        logger.info(f"   Rejected: {rejected_count}")
        logger.info("\n   Top Rejection Reasons:")
        
        sorted_reasons = sorted(rejection_stats.items(), key=lambda x: x[1], reverse=True)
        for reason, count in sorted_reasons[:5]:
            pct = (count / metrics_calculated * 100) if metrics_calculated > 0 else 0
            logger.debug(f"     • {reason}: {count} ({pct:.1f}%)")





        logger.info(f"Metrics calculated: {metrics_calculated}, Passed: {len(results)}, Rejected: {rejected_count}, Insufficient bars: {insufficient_bars}, Missing data: {missing_data}")
        
        if not results:
            logger.warning("No eligible stocks found today")
            # Write empty results
            empty_df = pd.DataFrame(columns=[
                "SYMBOL", "SECTOR", "PRICE", "ATR_PCT", "ADX", 
                "VOL_RATIO", "ADTV_CR", "TREND", "SCORE", "REASONS", 
                "REL_STRENGTH", "ELIGIBLE"
            ])
            self.write_results_to_excel(empty_df)
            return []
        
        # Sort by score and apply market-adjusted limits
        df_results = pd.DataFrame(results).sort_values("SCORE", ascending=False)
        max_trades = self.adjust_max_trades(market_trend, int(rules["MAX_TRADES_PER_DAY"]))
        logger.info(f"Max trades (adjusted for {market_trend}): {max_trades}")
        
        df_results = df_results.head(max_trades)
        
        # Display top picks
        logger.info(f"\n{'=' * 60}")
        logger.info("TOP PICKS:")
        logger.info(f"{'=' * 60}")
        for _, row in df_results.head(5).iterrows():
            logger.info(
                f"{row['SYMBOL']:10} | Score: {row['SCORE']:6.2f} | "
                f"Price: Rs.{row['PRICE']:7.2f} | {row['REASONS']}"
            )
        
        # Write results to Excel
        self.write_results_to_excel(df_results)
        
        # Return filtered signals
        filtered_signals = [s for s in signals if s.symbol in df_results['SYMBOL'].values]
        
        logger.info("=" * 60)
        logger.info("SCREENER COMPLETE")
        logger.info("=" * 60)
        
        return filtered_signals