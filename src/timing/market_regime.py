# src/timing/market_regime_manager.py

"""
Market Regime Manager (Unified & Real-Time)
=========================================
BACKWARD-COMPATIBLE replacement.

This file:
- Preserves existing public API
- Internally uses EnhancedMarketDetector
- Acts as a BRIDGE between legacy timing rules and modern regime logic

Nothing else in the system should detect market regime.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from enum import Enum

from .timing_rules import (
    TimingRules,
    BullMarketRules,
    BearMarketRules,
    SidewaysRules,
    VolatilityRules
)

from src.strategies.market_detector import EnhancedMarketDetector

logger = logging.getLogger(__name__)


# ============================================================
# ENUM (unchanged — DO NOT BREAK CALLERS)
# ============================================================

class MarketRegime(Enum):
    BULL_MARKET = "BULL"
    BEAR_MARKET = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "VOLATILE"


# ============================================================
# MANAGER
# ============================================================

class MarketRegimeManager:
    """
    Unified market regime manager.
    Legacy-compatible, real-time powered.
    """

    def __init__(self):
        self.detector = EnhancedMarketDetector()

        self.current_regime = MarketRegime.SIDEWAYS
        self.regime_confidence = 0.5
        self.last_update: Optional[datetime] = None

        # Anti-thrashing protection
        self._cooldown = timedelta(seconds=120)

        logger.info("Unified MarketRegimeManager initialized")

    # ========================================================
    # CORE API (UNCHANGED SIGNATURE)
    # ========================================================

    def detect_regime(self) -> Tuple[MarketRegime, float]:
        now = datetime.now()

        # Cooldown — prevents regime flip-flopping
        if self.last_update and now - self.last_update < self._cooldown:
            return self.current_regime, self.regime_confidence

        try:
            state = self.detector.get_current_market_state()

            regime = self._map_state_to_regime(state)
            confidence = float(state.confidence)

            self.current_regime = regime
            self.regime_confidence = confidence
            self.last_update = now

            logger.info(
                f"[MARKET REGIME] {regime.value} | "
                f"confidence={confidence:.2f} | "
                f"volatility={state.volatility_regime.value}"
            )

            return regime, confidence

        except Exception as e:
            logger.error(f"Market regime detection failed: {e}")
            return MarketRegime.SIDEWAYS, 0.5

    def get_market_regime(self) -> Tuple[MarketRegime, float]:
        """Alias for detect_regime (legacy compatibility)"""
        return self.detect_regime()

    # ========================================================
    # TIMING RULES (UNCHANGED)
    # ========================================================

    def get_timing_rules(self, regime: Optional[MarketRegime] = None) -> TimingRules:
        if regime is None:
            regime = self.current_regime

        return {
            MarketRegime.BULL_MARKET: BullMarketRules(),
            MarketRegime.BEAR_MARKET: BearMarketRules(),
            MarketRegime.SIDEWAYS: SidewaysRules(),
            MarketRegime.HIGH_VOLATILITY: VolatilityRules(),
        }.get(regime, SidewaysRules())

    # ========================================================
    # GLOBAL TRADE GATE
    # ========================================================

    def should_trade_now(self) -> bool:
        regime, confidence = self.detect_regime()

        # HARD STOPS
        if regime == MarketRegime.HIGH_VOLATILITY and confidence > 0.65:
            logger.warning("Trading paused: high volatility")
            return False

        if regime == MarketRegime.BEAR_MARKET and confidence > 0.75:
            logger.warning("Trading limited: strong bear regime")
            return False

        if confidence < 0.50:
            logger.warning("Trading paused: low regime confidence")
            return False

        return True

    # ========================================================
    # INFO / MONITORING
    # ========================================================

    def get_regime_info(self) -> Dict:
        regime, confidence = self.detect_regime()

        return {
            "regime": regime.value,
            "confidence": confidence,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "should_trade": self.should_trade_now(),
            "seconds_since_update": (
                int((datetime.now() - self.last_update).total_seconds())
                if self.last_update else None
            ),
        }

    # ========================================================
    # INTERNAL MAPPING
    # ========================================================

    def _map_state_to_regime(self, state) -> MarketRegime:
        if state.is_high_volatility():
            return MarketRegime.HIGH_VOLATILITY

        if state.is_bullish():
            return MarketRegime.BULL_MARKET

        if state.is_bearish():
            return MarketRegime.BEAR_MARKET

        return MarketRegime.SIDEWAYS
