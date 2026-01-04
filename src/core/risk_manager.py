"""
Risk Manager - Centralized Risk Management
=========================================

Centralized risk management system that enforces:
- Position size limits
- Capital allocation limits  
- Sector concentration limits
- Daily loss limits
- Correlation limits
- Volatility-based adjustments

This is the single source of truth for all risk decisions.
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date
from dataclasses import dataclass,field
from enum import Enum

from .models import (
    Order, Position, ScreenerSignal, CapitalParameters, 
    TradeParameters, OrderSide
)
from .state_manager import StateManager

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM" 
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class RiskAssessment:
    """Risk assessment result for a trade decision"""
    approved: bool
    risk_level: RiskLevel
    risk_score: float  # 0-100
    reasons: List[str]
    position_size_adjustment: float = 1.0  # Multiplier for position size
    
    def add_reason(self, reason: str):
        self.reasons.append(reason)


@dataclass
class RiskLimits:
    """Dynamic risk limits based on market conditions"""
    max_position_value: float
    max_daily_loss: float
    max_sector_exposure: float
    max_correlation_exposure: float
    max_open_positions: int
    volatility_multiplier: float = 1.0


class RiskManager:
    """
    Centralized risk management system.
    
    Key responsibilities:
    1. Validate all trade decisions against risk limits
    2. Adjust position sizes based on volatility and correlation
    3. Track sector concentration and correlation exposure
    4. Monitor daily P&L and enforce loss limits
    5. Provide dynamic risk limit adjustments
    """
    
    def __init__(
        self, 
        capital_params: CapitalParameters,
        trade_params: TradeParameters,
        state_manager: StateManager
    ):
        self.capital_params = capital_params
        self.trade_params = trade_params
        self.state = state_manager
        
        # Risk tracking
        self._sector_exposure: Dict[str, float] = {}
        self._correlation_matrix: Dict[str, Dict[str, float]] = {}
        self._daily_pnl: float = 0.0
        self._risk_override_active: bool = False
        
        # Dynamic risk limits (updated based on market regime)
        self._current_limits = self._calculate_base_limits()
        
        logger.info("Risk Manager initialized with comprehensive risk controls")
    
    # def _calculate_base_limits_old(self) -> RiskLimits:
    #     """Calculate base risk limits from configuration"""
    #     # Calculate derived limits from CapitalParameters
    #     max_position_value = self.capital_params.total_capital * self.capital_params.risk_per_trade * 0.15  # Allow 20x risk per trade as max position
    #     max_daily_loss = self.capital_params.total_capital * self.capital_params.max_daily_loss_pct
        
    #     return RiskLimits(
    #         max_position_value=max_position_value,
    #         max_daily_loss=max_daily_loss,
    #         max_sector_exposure=0.30,  # 30% max in any sector
    #         max_correlation_exposure=0.50,  # 50% max in highly correlated stocks
    #         max_open_positions=self.capital_params.max_open_positions,
    #         volatility_multiplier=1.0
    #     )
    
    def _calculate_base_limits(self) -> RiskLimits:
        total_capital = self.capital_params.total_capital

        return RiskLimits(
            max_position_value=total_capital * 0.15,     # 15% per position
            max_daily_loss=total_capital * self.capital_params.max_daily_loss_pct,
            max_sector_exposure=0.35,                     # 35% sector cap
            max_correlation_exposure=0.60,                # 60% correlated
            max_open_positions=self.capital_params.max_open_positions,
            volatility_multiplier=1.0
    )

    def assess_trade_risk(
        self, 
        signal: ScreenerSignal, 
        proposed_order: Order,
        current_positions: List[Position]
    ) -> RiskAssessment:
        """
        Comprehensive risk assessment for a proposed trade.
        
        Returns:
            RiskAssessment with approval decision and risk details
        """
        assessment = RiskAssessment(
            approved=True,
            risk_level=RiskLevel.LOW,
            risk_score=0.0,
            reasons=[]
        )
        
        try:
            # # 1. Capital allocation check
            # if not self._check_capital_limits(proposed_order, assessment):
            #     assessment.approved = False
                
            # 2. Position size validation
            if not self._check_position_limits(proposed_order, current_positions, assessment):
                assessment.approved = False
                
            # 3. Daily loss limit check
            if not self._check_daily_loss_limit(assessment):
                assessment.approved = False
                
            # 4. Sector concentration check
            if not self._check_sector_limits(signal, proposed_order, current_positions, assessment):
                assessment.approved = False
                
            # 5. Correlation exposure check
            if not self._check_correlation_limits(signal, proposed_order, current_positions, assessment):
                assessment.risk_level = RiskLevel.MEDIUM
                assessment.risk_score += 20
                
            # 6. Volatility adjustment
            self._apply_volatility_adjustment(signal, assessment)
            
            # 7. Calculate final risk score
            self._calculate_risk_score(assessment)
            
            # 8. Final approval logic
            if assessment.risk_score > 80:
                assessment.approved = False
                assessment.add_reason("Overall risk score too high")
                
            logger.info(f"Risk assessment for {signal.symbol}: "
                       f"{'APPROVED' if assessment.approved else 'REJECTED'} "
                       f"(Score: {assessment.risk_score:.1f}, Level: {assessment.risk_level.value})")
            
        except Exception as e:
            logger.error(f"Risk assessment failed for {signal.symbol}: {e}")
            assessment.approved = False
            assessment.add_reason(f"Risk assessment error: {e}")
            
        return assessment
    
    # def _check_capital_limits_old(self, order: Order, assessment: RiskAssessment) -> bool:
    #     """Check if order fits within capital allocation limits"""
    #     try:
    #         available_capital = self.state.get_available_capital()
    #         required_capital = order.req_qty * order.price
            
    #         if required_capital > available_capital:
    #             assessment.add_reason(f"Insufficient capital: need ₹{required_capital:,.0f}, have ₹{available_capital:,.0f}")
    #             assessment.risk_level = RiskLevel.CRITICAL
    #             return False
                
    #         # Check against max position value
    #         if required_capital > self._current_limits.max_position_value:
    #             assessment.add_reason(f"Position value exceeds limit: ₹{required_capital:,.0f} > ₹{self._current_limits.max_position_value:,.0f}")
    #             assessment.risk_level = RiskLevel.HIGH
    #             return False
                
    #         return True
            
    #     except Exception as e:
    #         assessment.add_reason(f"Capital check failed: {e}")
    #         return False
    
    # def _check_capital_limits(self, order: Order, assessment: RiskAssessment) -> bool:
    #     """Check if order fits within capital allocation limits"""
    #     try:
    #         available_capital = self.state.get_available_capital()
    #         required_capital = order.req_qty * order.price
            
    #         if required_capital > available_capital:
    #             assessment.add_reason(f"Insufficient capital: need ₹{required_capital:,.0f}, have ₹{available_capital:,.0f}")
    #             assessment.risk_level = RiskLevel.CRITICAL
    #             return False
                
    #         # Check against max position value
    #         if required_capital > self._current_limits.max_position_value:
    #             adjustment = (
    #                 self._current_limits.max_position_value / required_capital
    #             )
    #             assessment.position_size_adjustment *= adjustment
    #             assessment.add_reason(
    #                 f"Position size reduced to fit max position value "
    #                 f"(adjustment {adjustment:.2f}x)"
    #             )
    #             assessment.risk_level = RiskLevel.MEDIUM
    #             assessment.risk_score += 10
    #             return True
                
    #         return True
            
    #     except Exception as e:
    #         assessment.add_reason(f"Capital check failed: {e}")
    #         return False
    


    def _check_position_limits(self, order: Order, positions: List[Position], assessment: RiskAssessment) -> bool:
        """Check position count and size limits"""
        try:
            active_positions = [p for p in positions if p.status.value == "OPEN"]
            
            # Check max positions
            if len(active_positions) >= self._current_limits.max_open_positions:
                assessment.add_reason(f"Max positions reached: {len(active_positions)}/{self._current_limits.max_open_positions}")
                assessment.risk_level = RiskLevel.HIGH
                return False
                
            # Check for existing position in same symbol
            existing_position = next((p for p in active_positions if p.symbol == order.symbol), None)
            if existing_position:
                assessment.add_reason(f"Position already exists in {order.symbol}")
                assessment.risk_level = RiskLevel.MEDIUM
                assessment.risk_score += 15
                
            return True
            
        except Exception as e:
            assessment.add_reason(f"Position check failed: {e}")
            return False
    
    def _check_daily_loss_limit(self, assessment: RiskAssessment) -> bool:
        """Check daily loss limits"""
        try:
            current_pnl = self._get_daily_pnl()
            
            if current_pnl < -self._current_limits.max_daily_loss:
                assessment.add_reason(f"Daily loss limit exceeded: ₹{current_pnl:,.0f}")
                assessment.risk_level = RiskLevel.CRITICAL
                return False
                
            # Warning if approaching limit
            if current_pnl < -self._current_limits.max_daily_loss * 0.8:
                assessment.add_reason(f"Approaching daily loss limit: ₹{current_pnl:,.0f}")
                assessment.risk_level = RiskLevel.HIGH
                assessment.risk_score += 25
                
            return True
            
        except Exception as e:
            assessment.add_reason(f"Daily loss check failed: {e}")
            return False
    
    def _check_sector_limits(self, signal: ScreenerSignal, order: Order, positions: List[Position], assessment: RiskAssessment) -> bool:
        """Check sector concentration limits"""
        try:
            # Get sector for the symbol (simplified - in real system would use sector mapping)
            symbol_sector = self._get_symbol_sector(signal.symbol)
            
            # Calculate current sector exposure
            sector_exposure = self._calculate_sector_exposure(positions)
            current_sector_value = sector_exposure.get(symbol_sector, 0)
            new_position_value = order.req_qty * order.price
            
            total_capital = self.capital_params.total_capital
            new_sector_exposure = (current_sector_value + new_position_value) / total_capital
            
            if symbol_sector is None or symbol_sector.lower() == "unknown":
                assessment.add_reason("Sector unknown – sector limits skipped")
                return True

            if new_sector_exposure > self._current_limits.max_sector_exposure:
                assessment.add_reason(f"Sector limit exceeded: {symbol_sector} exposure would be {new_sector_exposure:.1%}")
                assessment.risk_level = RiskLevel.HIGH
                assessment.risk_score += 20
                return True
                
            # Warning if approaching limit
            if new_sector_exposure > self._current_limits.max_sector_exposure * 0.8:
                assessment.add_reason(f"High sector exposure: {symbol_sector} at {new_sector_exposure:.1%}")
                assessment.risk_level = RiskLevel.MEDIUM
                assessment.risk_score += 15
                
            return True
            
        except Exception as e:
            assessment.add_reason(f"Sector check failed: {e}")
            return True  # Don't fail trade on sector check error
    
    def _check_correlation_limits(self, signal: ScreenerSignal, order: Order, positions: List[Position], assessment: RiskAssessment) -> bool:
        """Check correlation exposure limits"""
        try:
            # Simplified correlation check - in real system would use correlation matrix
            similar_symbols = self._get_correlated_symbols(signal.symbol)
            
            correlation_exposure = 0.0
            for position in positions:
                if position.symbol in similar_symbols and position.status.value == "OPEN":
                    correlation_exposure += position.entry_price * position.quantity
                    
            new_position_value = order.req_qty * order.price
            total_correlation_exposure = (correlation_exposure + new_position_value) / self.capital_params.total_capital
            
            if total_correlation_exposure > self._current_limits.max_correlation_exposure:
                assessment.add_reason(f"High correlation exposure: {total_correlation_exposure:.1%}")
                assessment.risk_level = RiskLevel.MEDIUM
                assessment.risk_score += 20
                
            return True
            
        except Exception as e:
            assessment.add_reason(f"Correlation check failed: {e}")
            return True  # Don't fail trade on correlation error
    
    def _apply_volatility_adjustment(self, signal: ScreenerSignal, assessment: RiskAssessment):
        """Apply position size adjustment based on volatility"""
        try:
            # Simplified volatility adjustment - in real system would calculate actual volatility
            if hasattr(signal, 'volatility') and signal.volatility:
                if signal.volatility > 0.03:  # High volatility (>3%)
                    assessment.position_size_adjustment *= 0.75  # Reduce position size
                    assessment.add_reason("High volatility: position size reduced")
                    assessment.risk_score += 10
                elif signal.volatility < 0.01:  # Low volatility (<1%)
                    assessment.position_size_adjustment *= 1.25  # Increase position size
                    assessment.add_reason("Low volatility: position size increased")
                    
        except Exception as e:
            logger.warning(f"Volatility adjustment failed: {e}")
    
    def _calculate_risk_score(self, assessment: RiskAssessment):
        """Calculate overall risk score"""
        # Base score from risk level
        level_scores = {
            RiskLevel.LOW: 10,
            RiskLevel.MEDIUM: 30,
            RiskLevel.HIGH: 60,
            RiskLevel.CRITICAL: 90
        }
        
        base_score = level_scores.get(assessment.risk_level, 50)
        assessment.risk_score = min(100, max(0, base_score + assessment.risk_score))
    
    def update_market_regime(self, regime: str, volatility: float):
        """Update risk limits based on market regime"""
        try:
            if regime in ["HIGH_VOLATILITY", "BEARISH"]:
                self._current_limits.volatility_multiplier = 0.75  # Reduce risk
                self._current_limits.max_position_value *= 0.8
                logger.info(f"Risk limits tightened for {regime} regime")
            elif regime in ["LOW_VOLATILITY", "BULLISH"]:
                self._current_limits.volatility_multiplier = 1.25  # Increase risk
                self._current_limits.max_position_value *= 1.1
                logger.info(f"Risk limits relaxed for {regime} regime")
            else:
                self._current_limits.volatility_multiplier = 1.0  # Neutral
                
        except Exception as e:
            logger.error(f"Failed to update risk limits: {e}")
    
    def get_risk_status(self) -> Dict:
        """Get comprehensive risk status"""
        try:
            positions = self.state.load_positions()
            active_positions = [p for p in positions if p.status.value == "OPEN"]
            
            return {
                "daily_pnl": self._get_daily_pnl(),
                "daily_loss_limit": self._current_limits.max_daily_loss,
                "active_positions": len(active_positions),
                "max_positions": self._current_limits.max_open_positions,
                "available_capital": self.state.get_available_capital(),
                "sector_exposure": self._calculate_sector_exposure(active_positions),
                "risk_override_active": self._risk_override_active,
                "current_limits": self._current_limits
            }
            
        except Exception as e:
            logger.error(f"Failed to get risk status: {e}")
            return {"error": str(e)}
    
    def activate_emergency_mode(self, reason: str):
        """Activate emergency risk mode - stop all new trades"""
        self._risk_override_active = True
        self._current_limits.max_position_value = 0
        logger.critical(f"EMERGENCY RISK MODE ACTIVATED: {reason}")
    
    def deactivate_emergency_mode(self):
        """Deactivate emergency mode"""
        self._risk_override_active = False
        self._current_limits = self._calculate_base_limits()
        logger.info("Emergency risk mode deactivated")
    
    # Helper methods
    def _get_daily_pnl(self) -> float:
        """Get current daily P&L"""
        try:
            daily_pnl = self.state.load_daily_pnl()
            today = date.today().isoformat()
            return daily_pnl.get(today, {}).get('realized_pnl', 0.0)
        except Exception:
            return 0.0
    
    def _get_symbol_sector(self, symbol: str) -> str:
        """Get sector for symbol (simplified)"""
        # In real implementation, would use comprehensive sector mapping
        sector_map = {
            'RELIANCE': 'Energy', 'HDFCBANK': 'Banking', 'ICICIBANK': 'Banking',
            'TCS': 'IT', 'INFY': 'IT', 'WIPRO': 'IT',
            'ITC': 'FMCG', 'HINDUNILVR': 'FMCG'
        }
        clean_symbol = symbol.replace('.NS', '').replace('.NSE', '')
        return sector_map.get(clean_symbol, 'Unknown')
    
    def _calculate_sector_exposure(self, positions: List[Position]) -> Dict[str, float]:
        """Calculate current sector exposure"""
        sector_exposure = {}
        for position in positions:
            if position.status.value == "OPEN":
                sector = self._get_symbol_sector(position.symbol)
                sector_exposure[sector] = sector_exposure.get(sector, 0) + position.current_value
        return sector_exposure
    
    def _get_correlated_symbols(self, symbol: str) -> List[str]:
        """Get symbols correlated with the given symbol"""
        # Simplified correlation mapping
        correlation_groups = {
            'BANKING': ['HDFCBANK', 'ICICIBANK', 'KOTAKBANK', 'AXISBANK'],
            'IT': ['TCS', 'INFY', 'WIPRO', 'HCLTECH'],
            'ENERGY': ['RELIANCE', 'ONGC', 'IOC']
        }
        
        clean_symbol = symbol.replace('.NS', '').replace('.NSE', '')
        for group_symbols in correlation_groups.values():
            if clean_symbol in group_symbols:
                return group_symbols
        return []