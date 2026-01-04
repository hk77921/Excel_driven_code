"""
Sector Manager - Automatic Sector Mapping & Limits
==================================================
Manages sector classification and enforces sector-wise position limits.

Features:
- Automatic sector detection based on stock symbols
- Sector-wise position limit enforcement
- Real-time sector exposure tracking
- Integration with capital management
"""

import logging
import sys
from typing import Dict, List, Optional, Tuple
import json
import os
from pathlib import Path


# Add parent directory to path for imports (allows running as script or module)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

logger = logging.getLogger(__name__)


from src.core.models import CapitalParameters


logger = logging.getLogger(__name__)


class SectorManager:
    """
    Manages sector classification and limits for trading.
    
    Features:
    - Automatic sector mapping
    - Position limit enforcement
    - Exposure tracking
    - Risk concentration management
    """
    
    def __init__(self, capital_params: CapitalParameters):
        """
        Initialize sector manager.
        
        Args:
            capital_params: Capital parameters with sector limits
        """
        self.capital_params = capital_params
        
        # Built-in sector mappings (can be overridden by Excel)
        self.default_sector_map = self._build_default_sector_map()
        
        logger.info("Sector manager initialized")
    
    def get_symbol_sector(self, symbol: str, sector_map: Optional[Dict[str, str]] = None) -> str:
        """
        Get sector for a symbol with automatic detection.
        
        Args:
            symbol: Stock symbol
            sector_map: Optional custom sector mapping (from Excel)
            
        Returns:
            Sector name
        """
        # First check custom mapping (from Excel)
        if sector_map and symbol in sector_map:
            return sector_map[symbol]
        
        # Then check default mapping
        if symbol in self.default_sector_map:
            return self.default_sector_map[symbol]
        
        # Auto-detect based on symbol patterns
        detected_sector = self._auto_detect_sector(symbol)
        if detected_sector:
            return detected_sector
        
        return "OTHERS"
    
    def can_add_position_to_sector(
        self,
        symbol: str,
        sector: str,
        current_positions: Dict[str, dict],
        sector_map: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, str]:
        """
        Check if we can add another position to this sector.
        
        Args:
            symbol: Stock symbol
            sector: Sector name  
            current_positions: Current open positions
            sector_map: Optional sector mapping
            
        Returns:
            (can_add, reason_if_not)
        """
        # Count current positions in this sector
        sector_positions = self._count_sector_positions(sector, current_positions, sector_map)
        
        # Check sector limit
        max_per_sector = self.capital_params.max_per_sector
        
        if sector_positions >= max_per_sector:
            return False, f"Sector limit reached: {sector_positions}/{max_per_sector} in {sector}"
        
        return True, "OK"
    
    def get_sector_exposure(
        self,
        current_positions: Dict[str, dict],
        sector_map: Optional[Dict[str, str]] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate sector-wise exposure breakdown.
        
        Args:
            current_positions: Current open positions
            sector_map: Optional sector mapping
            
        Returns:
            Dict with sector exposure details
        """
        sector_exposure = {}
        
        for symbol, pos in current_positions.items():
            qty_remaining = pos.get('qty_remaining', 0)
            if qty_remaining <= 0:
                continue
            
            entry_price = pos.get('entry', 0.0)
            exposure = qty_remaining * entry_price
            
            sector = self.get_symbol_sector(symbol, sector_map)
            
            if sector not in sector_exposure:
                sector_exposure[sector] = {
                    'exposure': 0.0,
                    'positions': 0,
                    'symbols': []
                }
            
            sector_exposure[sector]['exposure'] += exposure
            sector_exposure[sector]['positions'] += 1
            sector_exposure[sector]['symbols'].append(symbol)
        
        return sector_exposure
    
    def _count_sector_positions(
        self,
        target_sector: str,
        current_positions: Dict[str, dict],
        sector_map: Optional[Dict[str, str]] = None
    ) -> int:
        """Count current positions in target sector"""
        count = 0
        
        for symbol, pos in current_positions.items():
            qty_remaining = pos.get('qty_remaining', 0)
            if qty_remaining <= 0:
                continue
            
            symbol_sector = self.get_symbol_sector(symbol, sector_map)
            if symbol_sector == target_sector:
                count += 1
        
        return count
    
    def _auto_detect_sector(self, symbol: str) -> Optional[str]:
        """Auto-detect sector based on symbol patterns"""
        symbol = symbol.upper()
        
        # Banking sector patterns
        bank_patterns = [
            'BANK', 'HDFC', 'ICICI', 'AXIS', 'KOTAK', 'INDUS', 'YES', 
            'PNB', 'CANARA', 'BOB', 'SBI', 'UNION', 'INDIAN'
        ]
        
        # IT sector patterns
        it_patterns = [
            'TCS', 'INFY', 'WIPRO', 'HCL', 'TECH', 'MIND', 'LTI', 
            'MPHASIS', 'COFORGE', 'ZENSAR', 'CYIENT'
        ]
        
        # Auto sector patterns  
        auto_patterns = [
            'TATA', 'MOTOR', 'MARUTI', 'MAHINDRA', 'BAJAJ', 'HERO',
            'TVS', 'EICHER', 'ASHOK', 'FORCE'
        ]
        
        # Pharma sector patterns
        pharma_patterns = [
            'SUN', 'REDDY', 'CIPLA', 'LUPIN', 'BIOCON', 'CADILA',
            'GLENMARK', 'TORRENT', 'ALKEM', 'PHARMA'
        ]
        
        # Energy/Oil sector patterns
        energy_patterns = [
            'RELIANCE', 'ONGC', 'IOC', 'BPCL', 'HPCL', 'GAIL', 
            'OIL', 'PETRONET', 'GAS'
        ]
        
        # FMCG sector patterns
        fmcg_patterns = [
            'HUL', 'ITC', 'NESTL', 'BRITANNIA', 'DABUR', 'MARICO',
            'COLGATE', 'GODREJ', 'EMAMI'
        ]
        
        # Check patterns
        for pattern in bank_patterns:
            if pattern in symbol:
                return "BANKING"
        
        for pattern in it_patterns:
            if pattern in symbol:
                return "IT"
        
        for pattern in auto_patterns:
            if pattern in symbol:
                return "AUTO"
        
        for pattern in pharma_patterns:
            if pattern in symbol:
                return "PHARMA"
        
        for pattern in energy_patterns:
            if pattern in symbol:
                return "ENERGY"
        
        for pattern in fmcg_patterns:
            if pattern in symbol:
                return "FMCG"
        
        return None
    
    def _build_default_sector_map(self) -> Dict[str, str]:
        """Build default sector mapping for major stocks"""
        return {
            # Banking
            "SBIN": "BANKING",
            "HDFCBANK": "BANKING", 
            "ICICIBANK": "BANKING",
            "AXISBANK": "BANKING",
            "KOTAKBANK": "BANKING",
            "INDUSINDBK": "BANKING",
            "YESBANK": "BANKING",
            "PNB": "BANKING",
            "CANARABANK": "BANKING",
            "BANKBARODA": "BANKING",
            
            # IT
            "TCS": "IT",
            "INFY": "IT", 
            "WIPRO": "IT",
            "HCLTECH": "IT",
            "TECHM": "IT",
            "MINDTREE": "IT",
            "LTI": "IT",
            "MPHASIS": "IT",
            
            # Auto
            "TATAMOTORS": "AUTO",
            "MARUTI": "AUTO",
            "M&M": "AUTO",
            "BAJAJ-AUTO": "AUTO",
            "HEROMOTOCO": "AUTO",
            "TVSMOTOR": "AUTO",
            "EICHERMOT": "AUTO",
            "ASHOKLEY": "AUTO",
            
            # Pharma
            "SUNPHARMA": "PHARMA",
            "DRREDDY": "PHARMA",
            "CIPLA": "PHARMA", 
            "LUPIN": "PHARMA",
            "BIOCON": "PHARMA",
            "CADILAHC": "PHARMA",
            "GLENMARK": "PHARMA",
            "TORNTPHARM": "PHARMA",
            
            # Energy
            "RELIANCE": "ENERGY",
            "ONGC": "ENERGY",
            "IOC": "ENERGY",
            "BPCL": "ENERGY",
            "HPCL": "ENERGY",
            "GAIL": "ENERGY",
            "PETRONET": "ENERGY",
            
            # FMCG
            "HINDUNILVR": "FMCG",
            "ITC": "FMCG",
            "NESTLEIND": "FMCG", 
            "BRITANNIA": "FMCG",
            "DABUR": "FMCG",
            "MARICO": "FMCG",
            "COLPAL": "FMCG",
            "GODREJCP": "FMCG",
            
            # Metals
            "TATASTEEL": "METALS",
            "JSWSTEEL": "METALS",
            "HINDALCO": "METALS",
            "VEDL": "METALS",
            "COALINDIA": "METALS",
            "NMDC": "METALS",
            "SAIL": "METALS",
            
            # Telecom
            "BHARTIARTL": "TELECOM",
            "IDEA": "TELECOM",
            "RCOM": "TELECOM",
            
            # Cement
            "ULTRACEMCO": "CEMENT",
            "SHREECEM": "CEMENT",
            "GRASIM": "CEMENT",
            "ACC": "CEMENT",
            "AMBUJACEMENT": "CEMENT",
            
            # Infrastructure
            "LT": "INFRA",
            "NTPC": "INFRA", 
            "POWERGRID": "INFRA",
            "BHARTIINFRA": "INFRA",
            
            # Diversified
            "ADANIENT": "DIVERSIFIED",
            "IGL": "UTILITIES",
            "PIDILITIND": "CHEMICALS"
        }


class AutoSectorMapper:
    """
    Enhanced automatic sector mapping with ML-like capabilities.
    Can learn from Excel mappings and improve over time.
    """
    
    def __init__(self, cache_file: str = "sector_cache.json"):
        """
        Initialize auto sector mapper.
        
        Args:
            cache_file: File to cache learned mappings
        """
        self.cache_file = cache_file
        self.learned_mappings = self._load_cached_mappings()
        
        # Enhanced pattern matching with weights
        self.sector_patterns = {
            "BANKING": {
                "keywords": ["BANK", "HDFC", "ICICI", "AXIS", "KOTAK", "SBI", "PNB", "YES"],
                "weight": 1.0
            },
            "IT": {
                "keywords": ["TCS", "INFY", "WIPRO", "HCL", "TECH", "INFO", "SOFT", "SYSTEM"],
                "weight": 1.0
            },
            "AUTO": {
                "keywords": ["MOTOR", "AUTO", "MARUTI", "TATA", "BAJAJ", "HERO", "TVS", "MAHINDRA"],
                "weight": 1.0
            },
            "PHARMA": {
                "keywords": ["PHARMA", "SUN", "REDDY", "CIPLA", "LUPIN", "BIO", "DRUG", "MED"],
                "weight": 1.0
            },
            "ENERGY": {
                "keywords": ["OIL", "GAS", "RELIANCE", "ONGC", "IOC", "BPCL", "HPCL", "PETRO"],
                "weight": 1.0
            },
            "FMCG": {
                "keywords": ["HUL", "ITC", "NESTLE", "BRIT", "DABUR", "MARICO", "GODREJ"],
                "weight": 1.0
            }
        }
        
        logger.info("Auto sector mapper initialized")
    
    def update_from_excel_mapping(self, excel_sector_map: Dict[str, str]):
        """
        Learn from Excel sector mappings to improve auto-detection.
        
        Args:
            excel_sector_map: Sector mapping from Excel
        """
        if not excel_sector_map:
            return
        
        # Update learned mappings
        for symbol, sector in excel_sector_map.items():
            if symbol not in self.learned_mappings:
                self.learned_mappings[symbol] = sector
                logger.debug(f"Learned mapping: {symbol} -> {sector}")
        
        # Save updated cache
        self._save_cached_mappings()
    
    def predict_sector(self, symbol: str) -> Tuple[str, float]:
        """
        Predict sector for symbol with confidence score.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            (predicted_sector, confidence_score)
        """
        symbol = symbol.upper()
        
        # Check learned mappings first
        if symbol in self.learned_mappings:
            return self.learned_mappings[symbol], 1.0
        
        # Pattern matching with scoring
        best_sector = "OTHERS"
        best_score = 0.0
        
        for sector, info in self.sector_patterns.items():
            score = 0.0
            
            for keyword in info["keywords"]:
                if keyword in symbol:
                    score += info["weight"]
            
            # Normalize score
            max_possible_score = len(info["keywords"]) * info["weight"]
            normalized_score = score / max_possible_score if max_possible_score > 0 else 0
            
            if normalized_score > best_score:
                best_score = normalized_score
                best_sector = sector
        
        # If no good match, try fuzzy matching
        if best_score < 0.3:
            fuzzy_sector, fuzzy_score = self._fuzzy_match_sector(symbol)
            if fuzzy_score > best_score:
                best_sector = fuzzy_sector
                best_score = fuzzy_score
        
        return best_sector, best_score
    
    def _fuzzy_match_sector(self, symbol: str) -> Tuple[str, float]:
        """Fuzzy matching for edge cases"""
        symbol = symbol.upper()
        
        # Check for common endings/prefixes
        if symbol.endswith("LTD") or symbol.endswith("LIMITED"):
            base_symbol = symbol.replace("LTD", "").replace("LIMITED", "").strip()
            return self.predict_sector(base_symbol)
        
        # Check for numeric suffixes
        import re
        clean_symbol = re.sub(r'\d+$', '', symbol)
        if clean_symbol != symbol and len(clean_symbol) > 2:
            return self.predict_sector(clean_symbol)
        
        return "OTHERS", 0.0
    
    def _load_cached_mappings(self) -> Dict[str, str]:
        """Load cached sector mappings"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"Failed to load sector cache: {e}")
        
        return {}
    
    def _save_cached_mappings(self):
        """Save cached sector mappings"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.learned_mappings, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save sector cache: {e}")