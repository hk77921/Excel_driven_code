"""
AUTO-SECTOR MAPPER
------------------
Populates SECTOR_MAP sheet automatically from NSE symbols

Safe for daily / weekly execution
"""

import pandas as pd
import yfinance as yf
import logging

EXCEL_FILE = "MiniRobo.xlsx"
UNIVERSE_SHEET = "UNIVERSE"
SECTOR_SHEET = "SECTOR_MAP"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# Standardized sector mapping
SECTOR_NORMALIZATION = {
    "Financial Services": "BANK",
    "Banks": "BANK",
    "Information Technology": "IT",
    "Technology": "IT",
    "Energy": "ENERGY",
    "Oil & Gas": "ENERGY",
    "Metals & Mining": "METAL",
    "Basic Materials": "METAL",
    "Consumer Defensive": "FMCG",
    "Consumer Cyclical": "AUTO",
    "Healthcare": "PHARMA",
    "Pharmaceuticals": "PHARMA",
    "Industrials": "INFRA",
    "Utilities": "ENERGY",
    "Communication Services": "TELECOM",
    "Materials": "METAL",
    "Real Estate": "INFRA"
}

def normalize_sector(raw_sector: str) -> str:
    if not raw_sector:
        return "OTHERS"
    return SECTOR_NORMALIZATION.get(raw_sector, "OTHERS")

def load_universe():
    df = pd.read_excel(EXCEL_FILE, sheet_name=UNIVERSE_SHEET)
    return df[df["ENABLED"] == "YES"]["SYMBOL"].unique().tolist()

def fetch_sector(symbol: str) -> str:
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        info = ticker.fast_info if hasattr(ticker, "fast_info") else {}
        sector = ticker.info.get("sector", None)
        return normalize_sector(sector)
    except Exception as e:
        logging.warning(f"{symbol}: sector fetch failed ({e})")
        return "OTHERS"

def build_sector_map():
    symbols = load_universe()
    logging.info(f"Auto-detecting sectors for {len(symbols)} symbols")

    rows = []
    for sym in symbols:
        sector = fetch_sector(sym)
        rows.append({"SYMBOL": sym, "SECTOR": sector})
        logging.info(f"{sym} → {sector}")

    return pd.DataFrame(rows)

def write_to_excel(df):
    with pd.ExcelWriter(EXCEL_FILE, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        df.to_excel(writer, sheet_name=SECTOR_SHEET, index=False)

    logging.info("SECTOR_MAP updated successfully")

if __name__ == "__main__":
    df_sector = build_sector_map()
    write_to_excel(df_sector)
