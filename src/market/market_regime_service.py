# src/market/market_regime_service.py

"""
Market Regime Service
=====================
Single authoritative source for:
- Market tradability
- Risk aggressiveness
- Volatility regime handling
- Confidence-based gating

NO trading component should infer market state on its own.
They must only CONSUME this service.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta

from src.strategies.market_detector import EnhancedMarketDetector

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    SIDEWAYS = "SIDEWAYS"
    VOLATILE = "VOLATILE"
    CHAOTIC = "CHAOTIC"


@dataclass(frozen=True)
class MarketRegimeSignal:
    regime: MarketRegime
    confidence: float           # 0–1
    tradable: bool              # master ON/OFF switch
    aggressiveness: float       # position-size multiplier
    volatility_penalty: float   # >1 = riskier
    timestamp: datetime


class MarketRegimeService:
    """
    Single source of truth for market regime.
    """

    def __init__(
        self,
        detector: EnhancedMarketDetector,
        min_confidence: float = 0.55,
        cooldown_seconds: int = 120
    ):
        self.detector = detector
        self.min_confidence = min_confidence
        self.cooldown = timedelta(seconds=cooldown_seconds)

        self._last_signal: MarketRegimeSignal | None = None
        self._last_update: datetime | None = None

    # ==========================================================
    # PUBLIC API — EVERYONE USES THIS
    # ==========================================================

    def get_market_regime(self) -> MarketRegimeSignal:
        now = datetime.now()

        # Cooldown protection (prevents regime thrashing)
        if self._last_signal and self._last_update:
            if now - self._last_update < self.cooldown:
                return self._last_signal

        state = self.detector.get_current_market_state()
        signal = self._map_state_to_regime(state)

        self._last_signal = signal
        self._last_update = now

        logger.info(
            f"[MARKET REGIME] {signal.regime.value} | "
            f"tradable={signal.tradable} | "
            f"confidence={signal.confidence:.2f} | "
            f"aggr={signal.aggressiveness:.2f}"
        )

        return signal

    # ==========================================================
    # INTERNAL LOGIC
    # ==========================================================

    def _map_state_to_regime(self, state) -> MarketRegimeSignal:
        """
        Converts EnhancedMarketDetector state into trading-safe regime.
        """

        confidence = float(state.confidence)
        volatility = state.volatility_regime.value

        # -------- REGIME CLASSIFICATION --------

        if state.is_high_volatility():
            regime = MarketRegime.VOLATILE
        elif state.is_bullish():
            regime = MarketRegime.BULLISH
        elif state.is_bearish():
            regime = MarketRegime.BEARISH
        else:
            regime = MarketRegime.SIDEWAYS

        # -------- TRADABILITY RULES --------

        tradable = True

        if confidence < self.min_confidence:
            tradable = False

        if regime == MarketRegime.VOLATILE and confidence < 0.65:
            tradable = False

        # -------- AGGRESSIVENESS --------

        aggressiveness = {
            MarketRegime.BULLISH: 1.00,
            MarketRegime.SIDEWAYS: 0.60,
            MarketRegime.BEARISH: 0.50,
            MarketRegime.VOLATILE: 0.30,
            MarketRegime.CHAOTIC: 0.00,
        }[regime]

        # -------- VOLATILITY PENALTY --------

        volatility_penalty = {
            "LOW": 1.0,
            "NORMAL": 1.1,
            "HIGH": 1.4,
            "EXTREME": 1.8,
        }.get(volatility, 1.3)

        return MarketRegimeSignal(
            regime=regime,
            confidence=confidence,
            tradable=tradable,
            aggressiveness=aggressiveness,
            volatility_penalty=volatility_penalty,
            timestamp=datetime.now(),
        )
