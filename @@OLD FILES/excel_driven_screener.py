"""
EXCEL-DRIVEN TRADING SCREENER - REFACTORED
-------------------------------------------
Professional-grade implementation with:
- Batch data fetching (10x faster)
- Proper error handling
- Data validation
- Normalized scoring
- Caching support
- Progress tracking
"""

import pandas as pd
import pandas_ta as ta
import yfinance as yf
from datetime import datetime
import logging
import os
import pickle
from datetime import date
from tqdm import tqdm

# ==============================
# CONFIG
# ==============================
EXCEL_FILE = "MiniRobo.xlsx"
UNIVERSE_SHEET = "UNIVERSE"
RULES_SHEET = "SCREENER_RULES"
SECTOR_SHEET = "SECTOR_MAP"
OUTPUT_SHEET = "SCREENER_OUTPUT"

LOOKBACK_DAYS = 60
INDEX_SYMBOL = "^NSEI"

# Constants (no more magic numbers!)
MIN_REQUIRED_BARS = 30
VOLUME_ROLLING_WINDOW = 20
ATR_ROLLING_WINDOW = 10
INDEX_LOOKBACK_DAYS = 90

# Scoring weights
SCORE_WEIGHT_ATR = 0.30
SCORE_WEIGHT_ADX = 0.30
SCORE_WEIGHT_VOL = 0.20
SCORE_WEIGHT_TREND = 0.20

# Cache directory
CACHE_DIR = "screener_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"screener_{datetime.now().strftime('%Y%m%d')}.log", encoding='utf-8')
    ]
)

# ==============================
# RULE DEFAULTS & NORMALIZATION
# ==============================
RULE_DEFAULTS = {
    "MIN_ADTV_CR": 5.0,
    "MIN_ATR_PCT": 2.0,
    "MAX_ATR_PCT": 5.0,
    "MIN_ADX": 20.0,
    "MIN_VOL_RATIO": 1.0,
    "MAX_EMA50_DISTANCE_PCT": 5.0,
    "PRICE_EMA20_RANGE_PCT": 3.0,
    "MAX_TRADES_PER_DAY": 5,
    "REL_STRENGTH_LOOKBACK": 30,
    "TREND_REQUIRED": "BULLISH",
    "REQUIRE_ATR_CONTRACTION": "NO",
    "REQUIRE_ADX_RISING": "NO",
    "REQUIRE_REL_STRENGTH": "NO"
}

def normalize_rules(rules: dict) -> dict:
    """Normalize rules with defaults and validation"""
    normalized = {}
    
    for key, default in RULE_DEFAULTS.items():
        value = rules.get(key, default)
        
        if isinstance(default, (int, float)):
            try:
                normalized[key] = type(default)(value)
            except (ValueError, TypeError):
                logging.warning(f"Invalid value for {key}: {value}, using default: {default}")
                normalized[key] = default
        else:
            normalized[key] = str(value).upper()
    
    return normalized


# ==============================
# EXCEL LOADERS WITH VALIDATION
# ==============================
def load_rules():
    """Load and validate screener rules"""
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name=RULES_SHEET)
        
        if "RULE" not in df.columns or "VALUE" not in df.columns:
            logging.error("SCREENER_RULES missing RULE or VALUE columns")
            return RULE_DEFAULTS
        
        rules = dict(zip(df["RULE"], df["VALUE"]))
        return normalize_rules(rules)
        
    except FileNotFoundError:
        logging.error(f"Excel file not found: {EXCEL_FILE}")
        return RULE_DEFAULTS
    except Exception as e:
        logging.error(f"Failed to load rules: {e}")
        return RULE_DEFAULTS


def load_universe():
    """Load and validate stock universe"""
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name=UNIVERSE_SHEET)
    except FileNotFoundError:
        logging.error(f"Excel file not found: {EXCEL_FILE}")
        return pd.DataFrame()
    except Exception as e:
        logging.error(f"Failed to load universe: {e}")
        return pd.DataFrame()
    
    # Validate columns
    required_cols = ["SYMBOL", "ENABLED"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        logging.error(f"Missing columns in UNIVERSE: {missing}")
        return pd.DataFrame()
    
    # Normalize and clean
    df["ENABLED"] = df["ENABLED"].astype(str).str.upper()
    df = df[df["ENABLED"] == "YES"]
    df = df.dropna(subset=["SYMBOL"])
    df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip().str.upper()
    df = df.drop_duplicates(subset=["SYMBOL"])
    
    if df.empty:
        logging.warning("No enabled stocks in UNIVERSE")
    else:
        logging.info(f"Loaded {len(df)} enabled stocks")
    
    return df


def load_sector_map():
    """Load sector mapping"""
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name=SECTOR_SHEET)
        
        if "SYMBOL" not in df.columns or "SECTOR" not in df.columns:
            logging.warning("SECTOR_MAP missing required columns")
            return {}
        
        return dict(zip(df["SYMBOL"], df["SECTOR"]))
        
    except Exception as e:
        logging.warning(f"Failed to load sector map: {e}")
        return {}


# ==============================
# DATA FETCHING - OPTIMIZED
# ==============================
def get_cache_path(symbol: str, data_type: str = "ohlcv") -> str:
    """Get cache file path for symbol"""
    today = date.today().strftime("%Y%m%d")
    return os.path.join(CACHE_DIR, f"{symbol}_{data_type}_{today}.pkl")


def load_from_cache(symbol: str, data_type: str = "ohlcv"):
    """Load data from cache if available"""
    cache_path = get_cache_path(symbol, data_type)
    
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            logging.debug(f"Cache read failed for {symbol}: {e}")
    
    return None


def save_to_cache(symbol: str, data, data_type: str = "ohlcv"):
    """Save data to cache"""
    cache_path = get_cache_path(symbol, data_type)
    
    try:
        with open(cache_path, "wb") as f:
            pickle.dump(data, f)
    except Exception as e:
        logging.warning(f"Cache write failed for {symbol}: {e}")


def fetch_bulk_ohlcv(symbols: list, lookback_days: int = LOOKBACK_DAYS) -> dict:
    """
    Fetch OHLCV data for multiple symbols at once (MUCH faster)
    Returns dict: {symbol: dataframe}
    """
    results = {}
    symbols_to_fetch = []
    
    # Check cache first
    for symbol in symbols:
        cached = load_from_cache(symbol)
        if cached is not None:
            results[symbol] = cached
        else:
            symbols_to_fetch.append(symbol)
    
    if not symbols_to_fetch:
        logging.info("All data loaded from cache")
        return results
    
    logging.info(f"Fetching fresh data for {len(symbols_to_fetch)} symbols...")
    
    # Prepare symbol list with .NS suffix
    symbols_with_ns = [f"{s}.NS" for s in symbols_to_fetch]
    
    try:
        # Batch download - THIS IS THE KEY OPTIMIZATION
        data = yf.download(
            symbols_with_ns,
            period=f"{lookback_days}d",
            interval="1d",
            group_by='ticker',
            progress=False,
            auto_adjust=False,
            threads=True  # Parallel downloads
        )
        
        # Handle single vs multiple symbols, but first ensure `data` is non-empty
        if data is None or (isinstance(data, pd.DataFrame) and data.empty):
            logging.warning("yf.download returned no data for requested symbols")
        else:
            # Single symbol returns non-grouped data
            if len(symbols_to_fetch) == 1:
                symbol = symbols_to_fetch[0]

                try:
                    if len(data) >= MIN_REQUIRED_BARS:
                        df = data.copy()
                        if isinstance(df.columns, pd.MultiIndex):
                            df.columns = df.columns.droplevel(1)
                        df = df.reset_index()
                        df.columns = df.columns.str.lower()
                        results[symbol] = df[["date", "open", "high", "low", "close", "volume"]]
                        save_to_cache(symbol, results[symbol])
                except Exception as e:
                    logging.debug(f"{symbol}: Data extraction failed - {e}")
            else:
                # Multiple symbols
                for symbol in symbols_to_fetch:
                    symbol_ns = f"{symbol}.NS"

                    try:
                        # Check whether this symbol was present in the multi-symbol result
                        if symbol_ns in data.columns.get_level_values(0):
                            df = data[symbol_ns].copy()

                            if len(df) >= MIN_REQUIRED_BARS:
                                df = df.reset_index()
                                df.columns = df.columns.str.lower()
                                df = df.dropna(subset=["close"])

                                if len(df) >= MIN_REQUIRED_BARS:
                                    results[symbol] = df[["date", "open", "high", "low", "close", "volume"]]
                                    save_to_cache(symbol, results[symbol])
                    except Exception as e:
                        logging.debug(f"{symbol}: Data extraction failed - {e}")

        # Count newly fetched (non-cached) symbols
        newly_fetched = sum(1 for s in symbols_to_fetch if s in results)
        logging.info(f"Successfully fetched {newly_fetched} new symbols")
        
    except Exception as e:
        logging.error(f"Bulk download failed: {e}")
    
    return results


def fetch_ohlcv_index(index_symbol: str = INDEX_SYMBOL) -> pd.DataFrame:
    """Fetch index data (NIFTY) for relative strength calculation"""
    
    # Check cache
    cached = load_from_cache(index_symbol, "index")
    if cached is not None:
        return cached
    
    try:
        df = yf.download(
            index_symbol,
            period=f"{INDEX_LOOKBACK_DAYS}d",
            interval="1d",
            progress=False,
            auto_adjust=False
        )
        
        if df is None or df.empty:
            logging.warning("Failed to download index data")
            return pd.DataFrame()
        
        # Flatten MultiIndex columns if necessary
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        
        df = df.reset_index()
        df.columns = df.columns.str.lower()
        
        # Cache it
        save_to_cache(index_symbol, df, "index")
        
        return df
        
    except Exception as e:
        logging.error(f"Index data fetch failed: {e}")
        return pd.DataFrame()


# ==============================
# MARKET REGIME
# ==============================
def get_market_trend() -> str:
    """Determine market trend from NIFTY"""
    try:
        df = fetch_ohlcv_index()
        
        if df is None or df.empty:
            return "NEUTRAL"
        
        df["ema20"] = ta.ema(df["close"], 20)
        df["ema50"] = ta.ema(df["close"], 50)
        
        ema20_val = df["ema20"].iloc[-1]
        ema50_val = df["ema50"].iloc[-1]
        
        if pd.isna(ema20_val) or pd.isna(ema50_val):
            return "NEUTRAL"
        
        return "BULLISH" if ema20_val > ema50_val else "BEARISH"
        
    except Exception as e:
        logging.error(f"Market trend calculation failed: {e}")
        return "NEUTRAL"


def adjust_max_trades(market_trend: str, base_max: int) -> int:
    """Adjust maximum trades based on market conditions"""
    if market_trend == "BEARISH":
        return max(1, int(base_max * 0.4))  # 40% of normal
    elif market_trend == "NEUTRAL":
        return max(2, int(base_max * 0.6))  # 60% of normal
    else:  # BULLISH
        return base_max


# ==============================
# METRICS CALCULATION
# ==============================
def calculate_metrics(df: pd.DataFrame, symbol: str, index_df: pd.DataFrame, rules: dict) -> dict:
    """Calculate all technical metrics for a symbol"""
    
    try:
        # Calculate indicators
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], 14)
        adx_result = ta.adx(df["high"], df["low"], df["close"])
        df["adx"] = adx_result["ADX_14"] if adx_result is not None else None
        df["ema20"] = ta.ema(df["close"], 20)
        df["ema50"] = ta.ema(df["close"], 50)
        df["vol_ratio"] = df["volume"] / df["volume"].rolling(VOLUME_ROLLING_WINDOW).mean()
        df["atr_avg"] = df["atr"].rolling(ATR_ROLLING_WINDOW).mean()
        df["atr_contracting"] = df["atr"] < df["atr_avg"]
        df["adx_rising"] = df["adx"] > df["adx"].shift(1)
        
    except Exception as e:
        logging.error(f"{symbol}: Indicator calculation failed - {e}")
        return dict()
    
    last = df.iloc[-1]
    
    # Validate required indicators
    if pd.isna(last["atr"]) or pd.isna(last["adx"]) or pd.isna(last["ema20"]) or pd.isna(last["ema50"]):
        logging.debug(f"{symbol}: Missing indicator values")
        return dict()
    
    # Relative strength calculation
    rel_strength = None
    try:
        lb = int(rules["REL_STRENGTH_LOOKBACK"])
        if index_df is not None and len(df) >= lb and len(index_df) >= lb:
            stock_ret = (df["close"].iloc[-1] / df["close"].iloc[-lb]) - 1
            index_ret = (index_df["close"].iloc[-1] / index_df["close"].iloc[-lb]) - 1
            rel_strength = round(stock_ret - index_ret, 4)
    except (KeyError, ValueError, IndexError) as e:
        logging.debug(f"{symbol}: RS calculation failed - {e}")
        rel_strength = None
    
    return {
        "symbol": symbol,
        "price": float(last["close"]),
        "atr_pct": float((last["atr"] / last["close"]) * 100),
        "atr_contracting": bool(last["atr_contracting"]),
        "adx": float(last["adx"]),
        "vol_ratio": float(last["vol_ratio"]),
        "adx_rising": bool(last["adx_rising"]),
        "ema20": float(last["ema20"]),
        "ema50": float(last["ema50"]),
        "trend": "BULLISH" if last["ema20"] > last["ema50"] else "BEARISH",
        "adtv_cr": float((df["close"] * df["volume"]).mean() / 1e7),
        "rel_strength": rel_strength
    }


# ==============================
# SCORING - NORMALIZED
# ==============================
def normalize_value(value: float, min_val: float, max_val: float) -> float:
    """Normalize value to 0-100 scale"""
    if max_val == min_val:
        return 50.0
    normalized = ((value - min_val) / (max_val - min_val)) * 100
    return max(0, min(100, normalized))  # Clamp to 0-100


def calculate_score(m: dict) -> float:
    """
    Calculate normalized score for a stock
    All metrics normalized to 0-100 scale before weighting
    """
    
    # Normalize each metric to 0-100
    atr_score = normalize_value(m["atr_pct"], 2.0, 5.0)
    adx_score = normalize_value(m["adx"], 20.0, 50.0)
    vol_score = normalize_value(m["vol_ratio"], 0.5, 3.0)
    trend_score = 100 if m["trend"] == "BULLISH" else 0
    
    # Weighted combination
    base_score = (
        atr_score * SCORE_WEIGHT_ATR +
        adx_score * SCORE_WEIGHT_ADX +
        vol_score * SCORE_WEIGHT_VOL +
        trend_score * SCORE_WEIGHT_TREND
    )
    
    # Soft boosters (add bonus points)
    bonus = 0
    if m["atr_contracting"]:
        bonus += 5
    if m["adx_rising"]:
        bonus += 3
    if m["rel_strength"] is not None and m["rel_strength"] > 0:
        bonus += min(10, m["rel_strength"] * 100)  # Cap at 10 bonus points
    
    return base_score + bonus


# ==============================
# FILTERING
# ==============================
def passes_filters(m: dict, rules: dict) -> tuple:
    """
    Check if stock passes all filters
    Returns (passed: bool, reason: str)
    """
    
    if m["adtv_cr"] < rules["MIN_ADTV_CR"]:
        return False, f"ADTV too low: {m['adtv_cr']:.2f}"
    
    if not (rules["MIN_ATR_PCT"] <= m["atr_pct"] <= rules["MAX_ATR_PCT"]):
        return False, f"ATR out of range: {m['atr_pct']:.2f}%"
    
    if m["adx"] < rules["MIN_ADX"]:
        return False, f"ADX too low: {m['adx']:.1f}"
    
    if m["vol_ratio"] < rules["MIN_VOL_RATIO"]:
        return False, f"Volume too low: {m['vol_ratio']:.2f}"
    
    if rules["TREND_REQUIRED"] == "BULLISH" and m["trend"] != "BULLISH":
        return False, "Not in bullish trend"
    
    if rules["REQUIRE_ATR_CONTRACTION"] == "YES" and not m["atr_contracting"]:
        return False, "ATR not contracting"
    
    if rules["REQUIRE_ADX_RISING"] == "YES" and not m["adx_rising"]:
        return False, "ADX not rising"
    
    if rules["REQUIRE_REL_STRENGTH"] == "YES":
        if m["rel_strength"] is None or m["rel_strength"] <= 0:
            return False, "Relative strength negative"
    
    # Price location filter
    ema50_dist = abs((m["price"] - m["ema50"]) / m["ema50"]) * 100
    if ema50_dist > rules["MAX_EMA50_DISTANCE_PCT"]:
        return False, f"Too far from EMA50: {ema50_dist:.1f}%"
    
    return True, "PASS"


def build_pass_reasons(m: dict, rules: dict) -> str:
    """Build comma-separated list of positive signals"""
    reasons = []
    
    if m["atr_contracting"]:
        reasons.append("ATR_CONTRACT")
    
    if abs((m["price"] - m["ema20"]) / m["ema20"]) * 100 <= rules["PRICE_EMA20_RANGE_PCT"]:
        reasons.append("NEAR_EMA20")
    
    if m["adx_rising"]:
        reasons.append("ADX_RISING")
    
    if m["rel_strength"] is not None and m["rel_strength"] > 0:
        reasons.append(f"RS+{m['rel_strength']:.2%}")
    
    if m["trend"] == "BULLISH":
        reasons.append("BULLISH")
    
    return ",".join(reasons) if reasons else "BASE_CRITERIA"


# ==============================
# EXCEL OUTPUT
# ==============================
def write_to_excel(df: pd.DataFrame):
    """Write results to Excel with error handling"""
    try:
        with pd.ExcelWriter(
            EXCEL_FILE, 
            engine="openpyxl", 
            mode="a", 
            if_sheet_exists="replace"
        ) as writer:
            df["LAST_UPDATED"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df.to_excel(writer, sheet_name=OUTPUT_SHEET, index=False)
        
        logging.info(f" Excel updated → {len(df)} stocks selected")
        
    except Exception as e:
        logging.error(f"Failed to write Excel: {e}")
        # Save to backup CSV
        backup_file = f"screener_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(backup_file, index=False)
        logging.info(f"Saved backup to: {backup_file}")


# ==============================
# MAIN SCREENER
# ==============================
def run_screener():
    """Main screener execution"""
    
    logging.info("="*60)
    logging.info("STARTING SCREENER")
    logging.info("="*60)
    
    # Load configuration
    rules = load_rules()
    universe = load_universe()
    
    if universe.empty:
        logging.error("No stocks to screen. Check UNIVERSE sheet.")
        return
    
    sector_map = load_sector_map()
    
    # Market regime
    market_trend = get_market_trend()
    logging.info(f" Market Trend: {market_trend}")
    
    # Fetch all data at once (THE KEY OPTIMIZATION)
    symbols = universe["SYMBOL"].tolist()
    bulk_data = fetch_bulk_ohlcv(symbols)
    
    if not bulk_data:
        logging.error("No data fetched. Check network/symbols.")
        return
    
    # Fetch index data once
    index_df = fetch_ohlcv_index()
    if index_df is None:
        logging.warning("Index data unavailable - relative strength disabled")
    
    # Screen each stock
    results = []
    rejected_count = 0
    
    for symbol in tqdm(symbols, desc="Screening stocks"):
        df = bulk_data.get(symbol)
        if df is None:
            continue
        
        m = calculate_metrics(df, symbol, index_df, rules)
        if m is None:
            continue
        
        passed, reason = passes_filters(m, rules)
        if not passed:
            rejected_count += 1
            logging.debug(f"{symbol} REJECTED: {reason}")
            continue
        
        score = calculate_score(m)
        reasons = build_pass_reasons(m, rules)
        
        results.append({
            "SYMBOL": symbol,
            "SECTOR": sector_map.get(symbol, "OTHERS"),
            "PRICE": round(m["price"], 2),
            "ATR_PCT": round(m["atr_pct"], 2),
            "ADX": round(m["adx"], 2),
            "VOL_RATIO": round(m["vol_ratio"], 2),
            "ADTV_CR": round(m["adtv_cr"], 2),
            "TREND": m["trend"],
            "SCORE": round(score, 2),
            "REASONS": reasons,
            "REL_STRENGTH": round(m["rel_strength"], 4) if m["rel_strength"] else None,
            "ELIGIBLE": "YES"
        })
    
    logging.info(f" Passed: {len(results)}, Rejected: {rejected_count}")
    
    if not results:
        logging.warning(" No eligible stocks today")
        # Write empty output with full expected schema so downstream consumers
        # (e.g., `execution_engine.py`) do not fail on missing columns.
        cols = [
            "SYMBOL",
            "SECTOR",
            "PRICE",
            "ATR_PCT",
            "ADX",
            "VOL_RATIO",
            "ADTV_CR",
            "TREND",
            "SCORE",
            "REASONS",
            "REL_STRENGTH",
            "ELIGIBLE"
        ]
        empty_df = pd.DataFrame(columns=cols)
        write_to_excel(empty_df)
        return
    
    # Sort and limit
    df_out = pd.DataFrame(results).sort_values("SCORE", ascending=False)
    
    max_trades = adjust_max_trades(market_trend, int(rules["MAX_TRADES_PER_DAY"]))
    logging.info(f"Max trades (adjusted for {market_trend}): {max_trades}")
    
    df_out = df_out.head(max_trades)
    
    # Display top picks
    logging.info(f"\n{'='*60}")
    logging.info("TOP PICKS:")
    logging.info(f"{'='*60}")
    for idx, row in df_out.head(5).iterrows():
        logging.info(
            f"{row['SYMBOL']:10} | Score: {row['SCORE']:6.2f} | "
            f"Price: ₹{row['PRICE']:7.2f} | {row['REASONS']}"
        )
    
    write_to_excel(df_out)
    
    logging.info("="*60)
    logging.info(" SCREENER COMPLETE")
    logging.info("="*60)


# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    run_screener()