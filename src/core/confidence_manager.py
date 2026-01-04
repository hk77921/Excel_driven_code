"""
Reactive Confidence Manager
=========================
Manages confidence decay and invalidation for all strategy decisions.

This system prevents stale confidence from causing false convictions by:
1. Time-based decay
2. Price-action invalidation  
3. Volatility shock override
4. Regime change invalidation

Author: GitHub Copilot
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
import numpy as np


logger = logging.getLogger(__name__)


class InvalidationType(str, Enum):
    """Types of confidence invalidation"""
    TIME_DECAY = "TIME_DECAY"
    PRICE_SHOCK = "PRICE_SHOCK"
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"
    REGIME_CHANGE = "REGIME_CHANGE"
    CORRELATION_BREAK = "CORRELATION_BREAK"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


@dataclass
class ConfidenceEvent:
    """Single confidence event with decay tracking"""
    initial_confidence: float
    current_confidence: float
    created_at: datetime
    last_update: datetime
    source_strategy: str
    context: Dict[str, Any]
    decay_rate: float = 0.02  # 2% per minute base decay
    invalidation_triggers: List[InvalidationType] = field(default_factory=list)
    is_active: bool = True
    
    def get_age_minutes(self) -> float:
        """Get age of confidence event in minutes"""
        return (datetime.now() - self.created_at).total_seconds() / 60.0
    
    def apply_time_decay(self) -> None:
        """Apply time-based confidence decay"""
        if not self.is_active:
            return
            
        age_minutes = self.get_age_minutes()
        
        # Exponential decay: confidence = initial * exp(-decay_rate * time)
        decayed_confidence = self.initial_confidence * np.exp(-self.decay_rate * age_minutes)
        
        # Update current confidence
        self.current_confidence = max(0.0, min(decayed_confidence, self.current_confidence))
        self.last_update = datetime.now()
        
        # Auto-deactivate if confidence drops too low
        if self.current_confidence < 0.1:
            self.is_active = False
            self.invalidation_triggers.append(InvalidationType.TIME_DECAY)


class ReactiveConfidenceManager:
    """
    Manages confidence levels with real-time decay and invalidation.
    
    Key Features:
    - Time-based exponential decay
    - Price shock invalidation
    - Volatility spike override
    - Regime change detection
    - Multi-strategy confidence aggregation
    """
    
    def __init__(self):
        """Initialize reactive confidence manager"""
        
        # Active confidence events by symbol
        self.confidence_events: Dict[str, List[ConfidenceEvent]] = {}
        
        # Invalidation thresholds
        self.price_shock_threshold = 0.03  # 3% price move invalidates confidence
        self.volatility_spike_threshold = 2.0  # 2x volatility spike
        self.correlation_break_threshold = 0.4  # 40% correlation drop
        
        # Cache for price tracking
        self.last_prices: Dict[str, float] = {}
        self.last_volatility: Dict[str, float] = {}
        self.last_correlations: Dict[str, float] = {}
        
        logger.info("Reactive confidence manager initialized")
    
    def add_confidence_event(self, 
                           symbol: str,
                           initial_confidence: float,
                           source_strategy: str,
                           context: Dict[str, Any],
                           decay_rate: Optional[float] = None) -> str:
        """
        Add new confidence event for tracking.
        
        Args:
            symbol: Stock symbol
            initial_confidence: Initial confidence level (0.0-1.0)
            source_strategy: Strategy that generated confidence
            context: Additional context for the confidence
            decay_rate: Custom decay rate (default based on strategy)
            
        Returns:
            Event ID for tracking
        """
        
        # Determine decay rate based on strategy if not provided
        if decay_rate is None:
            strategy_decay_rates = {
                'gap_trading': 0.05,      # Fast decay - gaps fill quickly
                'momentum_adaptive': 0.03, # Medium decay - momentum can shift
                'volatility_regime': 0.02, # Slow decay - volatility persistent
                'correlation_sync': 0.025  # Medium-slow decay
            }
            decay_rate = strategy_decay_rates.get(source_strategy, 0.02)
        
        # Create confidence event
        event = ConfidenceEvent(
            initial_confidence=initial_confidence,
            current_confidence=initial_confidence,
            created_at=datetime.now(),
            last_update=datetime.now(),
            source_strategy=source_strategy,
            context=context,
            decay_rate=decay_rate
        )
        
        # Add to tracking
        if symbol not in self.confidence_events:
            self.confidence_events[symbol] = []
        
        self.confidence_events[symbol].append(event)
        
        # Keep only last 10 events per symbol
        if len(self.confidence_events[symbol]) > 10:
            self.confidence_events[symbol] = self.confidence_events[symbol][-10:]
        
        event_id = f"{symbol}_{source_strategy}_{len(self.confidence_events[symbol])}"
        
        logger.debug(f"Added confidence event: {event_id} with confidence {initial_confidence:.2f}")
        
        return event_id
    
    def update_market_conditions(self, 
                               symbol: str,
                               current_price: float,
                               current_volatility: float,
                               current_correlation: Optional[float] = None) -> None:
        """
        Update market conditions and trigger invalidations if needed.
        
        Args:
            symbol: Stock symbol
            current_price: Current stock price
            current_volatility: Current volatility measure
            current_correlation: Current correlation with index
        """
        
        # Check for price shocks
        if symbol in self.last_prices:
            price_change = abs(current_price - self.last_prices[symbol]) / self.last_prices[symbol]
            
            if price_change > self.price_shock_threshold:
                self._invalidate_confidence(symbol, InvalidationType.PRICE_SHOCK, 
                                         f"Price shock: {price_change:.2%}")
        
        # Check for volatility spikes
        if symbol in self.last_volatility and self.last_volatility[symbol] > 0:
            volatility_ratio = current_volatility / self.last_volatility[symbol]
            
            if volatility_ratio > self.volatility_spike_threshold:
                self._invalidate_confidence(symbol, InvalidationType.VOLATILITY_SPIKE,
                                         f"Volatility spike: {volatility_ratio:.1f}x")
        
        # Check for correlation breaks
        if (current_correlation is not None and 
            symbol in self.last_correlations):
            
            correlation_drop = abs(current_correlation - self.last_correlations[symbol])
            
            if correlation_drop > self.correlation_break_threshold:
                self._invalidate_confidence(symbol, InvalidationType.CORRELATION_BREAK,
                                         f"Correlation break: {correlation_drop:.2f}")
        
        # Update cache
        self.last_prices[symbol] = current_price
        self.last_volatility[symbol] = current_volatility
        if current_correlation is not None:
            self.last_correlations[symbol] = current_correlation
    
    def get_current_confidence(self, symbol: str, strategy: Optional[str] = None) -> Tuple[float, Dict[str, Any]]:
        """
        Get current confidence level for symbol/strategy.
        
        Args:
            symbol: Stock symbol
            strategy: Specific strategy (if None, aggregates all)
            
        Returns:
            (confidence_level, confidence_details)
        """
        
        if symbol not in self.confidence_events:
            return 0.0, {"reason": "No confidence events", "active_events": 0}
        
        # Update all events with time decay
        for event in self.confidence_events[symbol]:
            event.apply_time_decay()
        
        # Filter active events
        active_events = [e for e in self.confidence_events[symbol] if e.is_active]
        
        if not active_events:
            return 0.0, {"reason": "No active confidence events", "total_events": len(self.confidence_events[symbol])}
        
        # Filter by strategy if specified
        if strategy:
            active_events = [e for e in active_events if e.source_strategy == strategy]
            
            if not active_events:
                return 0.0, {"reason": f"No active events for strategy {strategy}"}
        
        # Calculate weighted confidence
        total_weight = 0.0
        weighted_confidence = 0.0
        
        for event in active_events:
            # Weight by recency (newer events have higher weight)
            age_minutes = event.get_age_minutes()
            weight = np.exp(-age_minutes / 30.0)  # 30-minute half-life for weighting
            
            weighted_confidence += event.current_confidence * weight
            total_weight += weight
        
        if total_weight == 0:
            return 0.0, {"reason": "Zero total weight"}
        
        final_confidence = weighted_confidence / total_weight
        
        # Confidence details
        details = {
            "confidence": final_confidence,
            "active_events": len(active_events),
            "strategies": list(set(e.source_strategy for e in active_events)),
            "avg_age_minutes": np.mean([e.get_age_minutes() for e in active_events]),
            "oldest_event_age": max(e.get_age_minutes() for e in active_events),
            "newest_event_age": min(e.get_age_minutes() for e in active_events)
        }
        
        return final_confidence, details
    
    def force_invalidate(self, symbol: str, strategy: Optional[str] = None, reason: str = "Manual override") -> None:
        """
        Force invalidate confidence events.
        
        Args:
            symbol: Stock symbol
            strategy: Specific strategy (if None, invalidates all)
            reason: Reason for invalidation
        """
        
        if symbol not in self.confidence_events:
            return
        
        events_to_invalidate = self.confidence_events[symbol]
        
        if strategy:
            events_to_invalidate = [e for e in events_to_invalidate if e.source_strategy == strategy]
        
        for event in events_to_invalidate:
            if event.is_active:
                event.is_active = False
                event.invalidation_triggers.append(InvalidationType.MANUAL_OVERRIDE)
                event.context['invalidation_reason'] = reason
        
        logger.info(f"Force invalidated {len(events_to_invalidate)} confidence events for {symbol} ({strategy or 'all strategies'})")
    
    def _invalidate_confidence(self, symbol: str, invalidation_type: InvalidationType, reason: str) -> None:
        """Internal method to invalidate confidence events"""
        
        if symbol not in self.confidence_events:
            return
        
        invalidated_count = 0
        
        for event in self.confidence_events[symbol]:
            if event.is_active:
                event.is_active = False
                event.invalidation_triggers.append(invalidation_type)
                event.context['invalidation_reason'] = reason
                invalidated_count += 1
        
        if invalidated_count > 0:
            logger.warning(f"Invalidated {invalidated_count} confidence events for {symbol}: {reason}")
    
    def get_confidence(self, symbol: str, default_confidence: float = 0.7) -> float:
        """Get current confidence level for a symbol"""
        
        if symbol not in self.confidence_events:
            return default_confidence
        
        # Calculate average confidence from active events
        active_events = [e for e in self.confidence_events[symbol] if e.is_active]
        
        if not active_events:
            return default_confidence
        
        # Use weighted average based on event creation time (newer = higher weight)
        total_weight = 0
        weighted_confidence = 0
        
        for event in active_events:
            # Calculate decay based on age
            age_minutes = (datetime.now() - event.created_at).total_seconds() / 60
            decay_factor = np.exp(-age_minutes / self.config.decay_half_life_minutes)
            
            # Event's current confidence with decay
            current_confidence = event.initial_confidence * decay_factor
            
            weight = decay_factor  # Weight by decay factor
            weighted_confidence += current_confidence * weight
            total_weight += weight
        
        if total_weight > 0:
            return min(1.0, max(0.0, weighted_confidence / total_weight))
        else:
            return default_confidence
    
    def get_confidence_summary(self) -> Dict[str, Any]:
        """Get summary of all confidence events"""
        
        summary = {
            "total_symbols": len(self.confidence_events),
            "symbol_summaries": {}
        }
        
        for symbol, events in self.confidence_events.items():
            active_events = [e for e in events if e.is_active]
            
            # Update events with time decay
            for event in events:
                event.apply_time_decay()
            
            current_confidence, details = self.get_current_confidence(symbol)
            
            summary["symbol_summaries"][symbol] = {
                "current_confidence": current_confidence,
                "total_events": len(events),
                "active_events": len(active_events),
                "strategies": list(set(e.source_strategy for e in events)),
                "details": details
            }
        
        return summary
    
    def cleanup_old_events(self, max_age_hours: int = 24) -> None:
        """Remove events older than specified hours"""
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cleaned_symbols = []
        
        for symbol in list(self.confidence_events.keys()):
            original_count = len(self.confidence_events[symbol])
            
            # Remove old events
            self.confidence_events[symbol] = [
                e for e in self.confidence_events[symbol] 
                if e.created_at > cutoff_time
            ]
            
            # Remove symbol if no events left
            if not self.confidence_events[symbol]:
                del self.confidence_events[symbol]
                cleaned_symbols.append(symbol)
            else:
                removed_count = original_count - len(self.confidence_events[symbol])
                if removed_count > 0:
                    logger.debug(f"Cleaned {removed_count} old events for {symbol}")
        
        if cleaned_symbols:
            logger.info(f"Cleaned up confidence events for {len(cleaned_symbols)} symbols")