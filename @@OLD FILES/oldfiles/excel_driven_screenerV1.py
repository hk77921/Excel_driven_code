"""
EXCEL-DRIVEN TRADING SCREENER
-----------------------------------
Excel → Screener → Trading (Professional Grade)

Author: You (Reviewed & Hardened)
"""

import pandas as pd
import pandas_ta as ta
import yfinance as yf
from datetime import datetime
import openpyxl
import logging
import os

# ==============================
# CONFIG
# ==============================
EXCEL_FILE = "MiniRobo.xlsx"
UNIVERSE_SHEET = "UNIVERSE"
RULES_SHEET = "SCREENER_RULES"
SECTOR_SHEET = "SECTOR_MAP"
OUTPUT_SHEET = "SCREENER_OUTPUT"

LOOKBACK_DAYS = 60
INDEX_SYMBOL = "^NSEI"  # NIFTY 50

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler()]
)


# ==============================
# Defaults for rules
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

# ==============================
# NORMALIZATION
# ==============================
def normalize_value(value, min_val, max_val):
    """Normalize to 0-100 scale"""
    return ((value - min_val) / (max_val - min_val)) * 100

# ==============================
# RULE NORMALIZATION
# ==============================

def normalize_rules(rules: dict) -> dict:
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
# EXCEL LOADERS
# ==============================
def load_rules():
    df = pd.read_excel(EXCEL_FILE, sheet_name=RULES_SHEET)
    return dict(zip(df["RULE"], df["VALUE"]))

def load_universe_old():
    df = pd.read_excel(EXCEL_FILE, sheet_name=UNIVERSE_SHEET)
    return df[df["ENABLED"] == "YES"]


def load_universe():
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name=UNIVERSE_SHEET)
    except FileNotFoundError:
        logging.error(f"Excel file not found: {EXCEL_FILE}")
        return pd.DataFrame()
    except Exception as e:
        logging.error(f"Failed to load universe: {e}")
        return pd.DataFrame()
    
    required_cols = ["SYMBOL", "ENABLED"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        logging.error(f"Missing columns in UNIVERSE: {missing}")
        return pd.DataFrame()
    
    # Normalize and validate
    df["ENABLED"] = df["ENABLED"].astype(str).str.upper()
    df = df[df["ENABLED"] == "YES"]
    df = df.dropna(subset=["SYMBOL"])
    df = df.drop_duplicates(subset=["SYMBOL"])
    
    if df.empty:
        logging.warning("No enabled stocks in UNIVERSE")
    
    return df
def load_sector_map():
    df = pd.read_excel(EXCEL_FILE, sheet_name=SECTOR_SHEET)
    return dict(zip(df["SYMBOL"], df["SECTOR"]))

# ==============================
# MARKET REGIME
# ==============================
def get_market_trend():
    df = yf.download(INDEX_SYMBOL, period="3mo", interval="1d", progress=False, auto_adjust=False)
    
    if df is None or df.empty:
        logging.warning("Failed to download market data")
        return "NEUTRAL"
    
    # Flatten MultiIndex columns if necessary
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    
    df["ema20"] = ta.ema(df["Close"], 20)
    df["ema50"] = ta.ema(df["Close"], 50)
    
    ema20_val = df["ema20"].iloc[-1]
    ema50_val = df["ema50"].iloc[-1]
    
    if pd.isna(ema20_val) or pd.isna(ema50_val):
        logging.warning("Insufficient data for market trend calculation")
        return "NEUTRAL"
    
    return "BULLISH" if ema20_val > ema50_val else "BEARISH"




# ==============================
# DATA FETCH
# ==============================
def fetch_ohlcv(symbol):
    df = yf.download(f"{symbol}.NS", period=f"{LOOKBACK_DAYS}d", interval="1d", progress=False, auto_adjust=False)
    
    if df is None or df.empty or len(df) < 30:
        return None
    
    # Flatten MultiIndex columns if necessary
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    
    df = df.reset_index()
    df.columns = df.columns.str.lower()
    return df[["date", "open", "high", "low", "close", "volume"]]


def fetch_bulk_ohlcv(symbols, lookback_days=60):
    """Fetch all symbols in one shot"""
    symbols_with_ns = [f"{s}.NS" for s in symbols]
    
    try:
        data = yf.download(
            symbols_with_ns,
            period=f"{lookback_days}d",
            group_by='ticker',
            progress=False,
            auto_adjust=False
        )
        
        if data is None or data.empty:
            return {}   
        
        # Flatten MultiIndex columns if necessary
        results = {}
        for symbol in symbols:
            symbol_ns = f"{symbol}.NS"
            if symbol_ns in data.columns.get_level_values(0):
                df = data[symbol_ns].copy()
                if len(df) >= 30:
                    df = df.reset_index()
                    df.columns = df.columns.str.lower()
                    results[symbol] = df[["date", "open", "high", "low", "close", "volume"]]
        
        return results
    except Exception as e:
        logging.error(f"Bulk fetch failed: {e}")
        return {}
# ==============================
# METRICS
# ==============================
def calculate_metrics(df, symbol,index_df,rules):
    try:
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], 14)
        df["adx"] = ta.adx(df["high"], df["low"], df["close"])["ADX_14"]
        df["ema20"] = ta.ema(df["close"], 20)
        df["ema50"] = ta.ema(df["close"], 50)
        df["vol_ratio"] = df["volume"] / df["volume"].rolling(20).mean()
        df["atr_avg"] = df["atr"].rolling(10).mean()
        df["atr_contracting"] = df["atr"] < df["atr_avg"]
        df["adx_rising"] = df["adx"] > df["adx"].shift(1)
    except Exception as e:
        logging.error(f"{symbol}: Error calculating technical indicators - {e}")
        return None

    last = df.iloc[-1]

  # Handle NaN values in technical indicators
    if pd.isna(last["atr"]) or pd.isna(last["adx"]) or pd.isna(last["ema20"]) or pd.isna(last["ema50"]):
        return None

    # Relative strength vs index
    rel_strength = None
    try:
        lb = int(rules.get("REL_STRENGTH_LOOKBACK", 30))
        if index_df is not None and len(df) >= lb and len(index_df) >= lb:
            stock_ret = (df["close"].iloc[-1] / df["close"].iloc[-lb]) - 1
            index_ret = (index_df["close"].iloc[-1] / index_df["close"].iloc[-lb]) - 1
            rel_strength = round(stock_ret - index_ret, 4)
        else:
            rel_strength = None
    except (KeyError, ValueError, IndexError) as e:  # Be specific
     logging.warning(f"{symbol}: RS calculation failed - {e}")
    rel_strength = None


    return {
        "symbol": symbol,
        "price": last["close"],
        "atr_pct": (last["atr"] / last["close"]) * 100,
        "atr_contracting": bool(last["atr_contracting"]),
        "adx": last["adx"],
        "vol_ratio": last["vol_ratio"],
        "adx_rising": bool(last["adx_rising"]),
        "ema20": last["ema20"],
        "ema50": last["ema50"],
        "trend": "BULLISH" if last["ema20"] > last["ema50"] else "BEARISH",
        "adtv_cr": ((df["close"] * df["volume"]).mean()) / 1e7,
        "rel_strength": rel_strength
    }

    
  
# ==============================
# Helpers for FILTERS
# ==============================

def build_pass_reasons(m, rules):
    reasons = []

    if m["atr_contracting"]:
        reasons.append("ATR_CONTRACTION")

    if abs((m["price"] - m["ema20"]) / m["ema20"]) * 100 <= rules["PRICE_EMA20_RANGE_PCT"]:
        reasons.append("PRICE_NEAR_EMA20")

    if m["adx_rising"]:
        reasons.append("ADX_RISING")

    if m["rel_strength"] is not None and m["rel_strength"] > 0:
        reasons.append("RELATIVE_STRENGTH")

    if m["trend"] == "BULLISH":
        reasons.append("EMA_TREND")

    return ",".join(reasons)




# ==============================
# FILTER ENGINE
# ==============================
def passes_filters(m, rules):
    if m["adtv_cr"] < rules["MIN_ADTV_CR"]:
        debug_rejection(m["symbol"], m)
        return False
    if not (rules["MIN_ATR_PCT"] <= m["atr_pct"] <= rules["MAX_ATR_PCT"]):
        debug_rejection(m["symbol"], m)
        return False
    if m["adx"] < rules["MIN_ADX"]:
        debug_rejection(m["symbol"], m)
        return False
    if m["vol_ratio"] < rules["MIN_VOL_RATIO"]:
        debug_rejection(m["symbol"], m)
        return False
    if rules["TREND_REQUIRED"] == "BULLISH" and m["trend"] != "BULLISH":
        debug_rejection(m["symbol"], m)
        return False
    
    if rules["REQUIRE_ATR_CONTRACTION"] == "YES" and not m["atr_contracting"]:
        debug_rejection(m["symbol"], m)
        return False

    if rules["REQUIRE_ADX_RISING"] == "YES" and not m["adx_rising"]:
        debug_rejection(m["symbol"], m)
        return False

    if rules["REQUIRE_REL_STRENGTH"] == "YES":
        if m["rel_strength"] is None or m["rel_strength"] <= 0:
            debug_rejection(m["symbol"], m)
            return False
        
    # Price location filter
    ema50_dist = abs((m["price"] - m["ema50"]) / m["ema50"]) * 100
    if ema50_dist > rules["MAX_EMA50_DISTANCE_PCT"]:
        debug_rejection(m["symbol"], m)
        return False
    return True


def debug_rejection(symbol, m):
    logging.debug(
        f"{symbol} REJECTED | "
        f"ATR%={m['atr_pct']:.2f} | "
        f"ATR_CONTRACT={m['atr_contracting']} | "
        f"ADX={m['adx']:.1f} | "
        f"ADX_RISE={m['adx_rising']} | "
        f"REL_STR={m['rel_strength']}"
    )

# ==============================
# MAIN SCREENER
# ==============================
def run_screener():

    logging.info("Running screener...")

    rules = normalize_rules(load_rules())
    #logging.info(f"Rules: {rules}") 

    universe = load_universe()
    #logging.info(f"Universe size: {len(universe)} stocks")

    sector_map = load_sector_map()
    #logging.info(f"Sector Map: {sector_map}")

    market_trend = get_market_trend()
    logging.info(f"Market Trend: {market_trend}")

    max_trades = int(rules["MAX_TRADES_PER_DAY"])
   
    # if market_trend != "BULLISH":
    #     max_trades = min(3, max_trades)
    # #logging.info(f"Max Trades Today: {max_trades}")

    if market_trend == "BEARISH":
        max_trades = max(1, int(max_trades * 0.4))  # 40% of normal
    elif market_trend == "NEUTRAL":
        max_trades = max(2, int(max_trades * 0.6))  # 60% of normal
    # else BULLISH: use full max_trades
    results = []

    index_df = yf.download(
        INDEX_SYMBOL,
        period="90d",
        interval="1d",
        progress=False,
        auto_adjust=False
    )
    #logging.info(f"Fetched index data for relative strength calculation {index_df.head(2)}")
    if index_df is None or index_df.empty:
        logging.warning("Index data unavailable – RS disabled")
        index_df = None
    else:
        if isinstance(index_df.columns, pd.MultiIndex):
            index_df.columns = index_df.columns.droplevel(1)

        index_df = index_df.reset_index()
        index_df.columns = index_df.columns.str.lower()


    for _, row in universe.iterrows():
        symbol = row["SYMBOL"]
        df = fetch_ohlcv(symbol)
        if df is None:
            continue

        m = calculate_metrics(df, symbol, index_df, rules)

        if m is None:
            logging.debug(f"{symbol}: Insufficient data for metrics")
            continue

        if not passes_filters(m, rules):
            continue

       
        score = (
            normalize_value(m["atr_pct"], 2, 5) * 0.30 +
            normalize_value(m["adx"], 20, 50) * 0.30 +
            normalize_value(m["vol_ratio"], 0.5, 3) * 0.20 +
            (20 if m["trend"] == "BULLISH" else 0) * 0.20
        )

            # Soft boosters
        if m["atr_contracting"]:
            score += 5

        if m["rel_strength"] is not None:
            score += max(0, m["rel_strength"] * 100)

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
            "ELIGIBLE": "YES"
        })

    if not results:
        logging.warning("No eligible stocks today.")
        return

    df_out = pd.DataFrame(results).sort_values("SCORE", ascending=False)
    df_out = df_out.head(max_trades)

    write_to_excel(df_out)


# ==============================
# EXCEL OUTPUT
# ==============================
def write_to_excel(df):
    with pd.ExcelWriter(EXCEL_FILE, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        df["LAST_UPDATED"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df.to_excel(writer, sheet_name=OUTPUT_SHEET, index=False)

    logging.info(f"Excel updated → {len(df)} stocks selected")

# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    run_screener()
