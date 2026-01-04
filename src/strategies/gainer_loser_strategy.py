"""
Gainer/Loser Strategy
====================
Custom strategy that trades top NSE gainers and losers using gap-reversal logic.

This strategy:
1. Uses Dynamic Universe Manager for live NSE data
2. Fetches configurable number of top gainers and losers
3. Calculates gap-adjusted entry points with intelligent filtering
4. Implements proper risk management and sector diversification
5. Uses adaptive position sizing based on gap size and market conditions

Author: GitHub Copilot (based on user requirements)
"""

import logging
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, time
from dataclasses import dataclass
import pandas as pd

try:
    from nsetools import Nse
    NSE_AVAILABLE = True
except ImportError:
    NSE_AVAILABLE = False
    logging.warning("nsetools not available. Install with: pip install nsetools")

from src.core.models import ScreenerSignal
from .market_detector import EnhancedMarketDetector, MarketState
from src.universe.dynamic_universe_manager import DynamicUniverseManager


logger = logging.getLogger(__name__)


@dataclass
class GainerLoserSignal:
    """Custom signal for gainer/loser strategy"""
    symbol: str
    prev_price: float
    open_price: float
    ltp: float
    gap_pct: float
    gap_amount: float
    entry_price: float
    target_price: float
    signal_type: str  # 'GAINER' or 'LOSER'
    volume: float = 0.0
    sector: str = "UNKNOWN"


class GainerLoserStrategy:
    """
    Enhanced strategy that trades NSE top gainers and losers using dynamic universe.
    
    Features:
    - Dynamic universe with configurable gainer/loser counts
    - Live NSE data with intelligent filtering and ranking
    - Sector diversification and risk controls
    - Gap-reversal logic with adaptive entry points
    - Real-time market condition awareness
    
    For Gainers (Gap Up):
    - Entry: prev_price + 50% of gap
    - Target: open_price (current)
    - Logic: Expects gap fill (reversal)
    
    For Losers (Gap Down):  
    - Entry: prev_price + 50% of gap (for short)
    - Target: Current open price
    - Logic: Expects bounce back
    """
    
    def __init__(self, market_detector: EnhancedMarketDetector):
        """Initialize the enhanced gainer/loser strategy"""
        self.name = "DYNAMIC_GAINER_LOSER"
        self.market_detector = market_detector
        
        # Initialize Dynamic Universe Manager
        self.universe_manager = DynamicUniverseManager()
        
        # Strategy parameters - Now using dynamic universe configuration
        universe_config = self.universe_manager.universe_config
        self.max_gainers = universe_config.get('max_gainers', 10)
        self.max_losers = universe_config.get('max_losers', 5)
        self.min_gap_pct = universe_config.get('min_gap_percentage', 2.0)
        self.max_gap_pct = universe_config.get('max_gap_percentage', 8.0)
        self.gap_fill_ratio = 0.5     # Use 50% of gap as entry point
        
        # Risk management
        self.max_position_size_pct = 2.0   # Max 2% capital per trade
        self.stop_loss_pct = 1.5           # 1.5% stop loss
        self.target_reward_ratio = 2.0     # 2:1 reward:risk
        
        # Legacy NSE support (for backward compatibility)
        if NSE_AVAILABLE:
            self.nse = Nse()
        else:
            self.nse = None
            
        logger.info(f"Enhanced Dynamic Gainer/Loser strategy initialized - Top {self.max_gainers} gainers + {self.max_losers} losers")
    
    def get_trading_signals(self) -> List[GainerLoserSignal]:
        """
        Get trading signals from dynamic universe (NSE top gainers and losers).
        
        Returns:
            List of GainerLoserSignal objects
        """
        signals = []
        
        try:
            # Get current universe from dynamic manager
            universe = self.universe_manager.get_current_universe()
            
            if not universe:
                logger.warning("No universe data available")
                return []
            
            # Process gainers from dynamic universe
            gainers_data = universe.get('gainers', [])
            if gainers_data:
                gainer_signals = self._process_universe_gainers(gainers_data)
                signals.extend(gainer_signals)
            
            # Process losers from dynamic universe
            losers_data = universe.get('losers', [])
            if losers_data:
                loser_signals = self._process_universe_losers(losers_data)
                signals.extend(loser_signals)
                
            # Log universe stats
            stats = self.universe_manager.get_universe_stats()
            logger.info(f"Generated {len(signals)} signals from dynamic universe:")
            logger.info(f"  - {stats.get('gainers_count', 0)} gainers (avg gap: {stats.get('avg_gainer_gap', 0):.1f}%)")
            logger.info(f"  - {stats.get('losers_count', 0)} losers (avg gap: {stats.get('avg_loser_gap', 0):.1f}%)")
            logger.info(f"  - Data source: {stats.get('data_source', 'Unknown')}")
            logger.info(f"  - Sectors covered: {stats.get('sectors_covered', 0)}")
            
            return signals
            
        except Exception as e:
            logger.error(f"Error generating signals from dynamic universe: {e}")
            return []
    
    def _process_universe_gainers(self, gainers_data: List[Dict]) -> List[GainerLoserSignal]:
        """Process gainers from dynamic universe data"""
        signals = []
        
        for gainer_data in gainers_data:
            try:
                # Data is already processed by universe manager
                symbol = gainer_data['symbol']
                prev_price = gainer_data['prev_price']
                open_price = gainer_data['open_price']
                ltp = gainer_data['ltp']
                gap_pct = gainer_data['gap_pct']
                gap_amount = gainer_data['gap_amount']
                
                # Calculate entry and target (gap fill strategy)
                entry_price = prev_price + (gap_amount * self.gap_fill_ratio)
                target_price = open_price  # Expect to reach open price
                
                signal = GainerLoserSignal(
                    symbol=symbol,
                    prev_price=prev_price,
                    open_price=open_price,
                    ltp=ltp,
                    gap_pct=gap_pct,
                    gap_amount=gap_amount,
                    entry_price=entry_price,
                    target_price=target_price,
                    signal_type='GAINER',
                    volume=gainer_data.get('volume', 0.0),
                    sector=gainer_data.get('sector', 'UNKNOWN')
                )
                
                signals.append(signal)
                
            except Exception as e:
                logger.warning(f"Error processing dynamic gainer {gainer_data}: {e}")
                continue
        
        return signals
    
    def _process_universe_losers(self, losers_data: List[Dict]) -> List[GainerLoserSignal]:
        """Process losers from dynamic universe data"""
        signals = []
        
        for loser_data in losers_data:
            try:
                # Data is already processed by universe manager
                symbol = loser_data['symbol']
                prev_price = loser_data['prev_price']
                open_price = loser_data['open_price']
                ltp = loser_data['ltp']
                gap_pct = loser_data['gap_pct']  # This is negative
                gap_amount = loser_data['gap_amount']  # This is negative
                
                # Calculate entry and target (bounce back strategy)
                entry_price = prev_price + (gap_amount * self.gap_fill_ratio)
                target_price = open_price + abs(gap_amount * 0.3)  # Expect 30% bounce back
                
                signal = GainerLoserSignal(
                    symbol=symbol,
                    prev_price=prev_price,
                    open_price=open_price,
                    ltp=ltp,
                    gap_pct=gap_pct,
                    gap_amount=gap_amount,
                    entry_price=entry_price,
                    target_price=target_price,
                    signal_type='LOSER',
                    volume=loser_data.get('volume', 0.0),
                    sector=loser_data.get('sector', 'UNKNOWN')
                )
                
                signals.append(signal)
                
            except Exception as e:
                logger.warning(f"Error processing dynamic loser {loser_data}: {e}")
                continue
        
        return signals

    # Legacy methods for backward compatibility
    def _process_gainers(self, gainers: List[Dict]) -> List[GainerLoserSignal]:
        """Process top gainers for trading signals"""
        signals = []
        
        for gainer in gainers:
            try:
                symbol = gainer.get('symbol', '').replace(' ', '').upper()
                prev_price = float(gainer.get('prev_price', 0))
                open_price = float(gainer.get('open_price', 0))
                ltp = float(gainer.get('ltp', open_price))
                
                if prev_price <= 0 or open_price <= 0:
                    continue
                
                # Calculate gap
                gap_amount = open_price - prev_price
                gap_pct = (gap_amount / prev_price) * 100
                
                # Filter by gap size
                if gap_pct < self.min_gap_pct or gap_pct > self.max_gap_pct:
                    continue
                
                # Calculate entry and target (gap fill strategy)
                entry_price = prev_price + (gap_amount * self.gap_fill_ratio)
                target_price = open_price  # Expect to reach open price
                
                signal = GainerLoserSignal(
                    symbol=symbol,
                    prev_price=prev_price,
                    open_price=open_price,
                    ltp=ltp,
                    gap_pct=gap_pct,
                    gap_amount=gap_amount,
                    entry_price=entry_price,
                    target_price=target_price,
                    signal_type='GAINER',
                    volume=float(gainer.get('volume', 0)),
                    sector=gainer.get('sector', 'UNKNOWN')
                )
                
                signals.append(signal)
                
            except Exception as e:
                logger.warning(f"Error processing gainer {gainer}: {e}")
                continue
        
        return signals
    
    def _process_losers(self, losers: List[Dict]) -> List[GainerLoserSignal]:
        """Process top losers for trading signals"""
        signals = []
        
        for loser in losers:
            try:
                symbol = loser.get('symbol', '').replace(' ', '').upper()
                prev_price = float(loser.get('prev_price', 0))
                open_price = float(loser.get('open_price', 0))
                ltp = float(loser.get('ltp', open_price))
                
                if prev_price <= 0 or open_price <= 0:
                    continue
                
                # Calculate gap (negative for losers)
                gap_amount = open_price - prev_price  # This will be negative
                gap_pct = (gap_amount / prev_price) * 100  # Negative percentage
                
                # Filter by gap size (use absolute values)
                if abs(gap_pct) < self.min_gap_pct or abs(gap_pct) > self.max_gap_pct:
                    continue
                
                # Calculate entry and target (bounce back strategy)
                entry_price = prev_price + (gap_amount * self.gap_fill_ratio)
                target_price = open_price + abs(gap_amount * 0.3)  # Expect 30% bounce back
                
                signal = GainerLoserSignal(
                    symbol=symbol,
                    prev_price=prev_price,
                    open_price=open_price,
                    ltp=ltp,
                    gap_pct=gap_pct,
                    gap_amount=gap_amount,
                    entry_price=entry_price,
                    target_price=target_price,
                    signal_type='LOSER',
                    volume=float(loser.get('volume', 0)),
                    sector=loser.get('sector', 'UNKNOWN')
                )
                
                signals.append(signal)
                
            except Exception as e:
                logger.warning(f"Error processing loser {loser}: {e}")
                continue
        
        return signals
    
    def should_enter_trade(self, signal: ScreenerSignal) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Evaluate if should enter trade for regular screener signal.
        This integrates with existing screener workflow.
        """
        # For now, this strategy works independently with its own signals
        # Could be integrated with regular screener later
        return False, "Use get_trading_signals() method for gainer/loser strategy", {}
    
    def evaluate_gainer_loser_signal(self, signal: GainerLoserSignal) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Evaluate a gainer/loser specific signal.
        
        Args:
            signal: GainerLoserSignal object
            
        Returns:
            (should_enter, reason, trading_parameters)
        """
        current_time = datetime.now().time()
        
        # 1. Time filter - only trade in first 2 hours
        if current_time < time(9, 15) or current_time > time(11, 30):
            return False, "Outside gainer/loser trading window", {}
        
        # 2. Gap size validation
        abs_gap = abs(signal.gap_pct)
        if abs_gap < self.min_gap_pct:
            return False, f"Gap too small: {abs_gap:.2f}%", {}
        if abs_gap > self.max_gap_pct:
            return False, f"Gap too large: {abs_gap:.2f}%", {}
        
        # 3. Price validation
        if signal.ltp <= 0 or signal.entry_price <= 0:
            return False, "Invalid price data", {}
        
        # 4. Market state check
        market_state = self.market_detector.get_current_market_state()
        if market_state.is_high_volatility():
            return False, "High volatility market - avoiding gainer/loser trades", {}
        
        # 5. Calculate trading parameters
        trading_params = self._calculate_trading_parameters(signal)
        
        reason = f"{signal.signal_type} gap {signal.gap_pct:.1f}% - gap fill strategy"
        
        return True, reason, trading_params
    
    def _calculate_trading_parameters(self, signal: GainerLoserSignal) -> Dict[str, Any]:
        """Calculate trading parameters for the signal"""
        
        # Position sizing based on gap risk
        abs_gap = abs(signal.gap_pct)
        if abs_gap >= 6.0:
            position_mult = 0.5  # Small position for large gaps
        elif abs_gap >= 4.0:
            position_mult = 0.7  # Medium position
        else:
            position_mult = 1.0  # Normal position
        
        # Stop loss and target based on gap size
        if signal.signal_type == 'GAINER':
            # For gainers, expect gap fill (price to come down)
            stop_loss_price = signal.entry_price * (1 + self.stop_loss_pct / 100)
            target_price = signal.target_price
        else:
            # For losers, expect bounce (price to go up)  
            stop_loss_price = signal.entry_price * (1 - self.stop_loss_pct / 100)
            target_price = signal.target_price
        
        return {
            'entry_price': signal.entry_price,
            'stop_loss_price': stop_loss_price,
            'target_price': target_price,
            'position_size_multiplier': position_mult,
            'signal_type': signal.signal_type,
            'gap_pct': signal.gap_pct,
            'strategy': 'GAINER_LOSER',
            'time_limit_hours': 4,  # Close position within 4 hours if not hit
            'partial_exit_enabled': True,
            'partial_exit_ratio': 0.6  # Exit 60% at target, trail remaining
        }
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get current strategy information"""
        return {
            'name': self.name,
            'description': 'Enhanced NSE Gainer/Loser Gap Trading Strategy - Dynamic Universe with Excel Integration',
            'nse_available': NSE_AVAILABLE,
            'universe': {
                'max_gainers': self.max_gainers,
                'max_losers': self.max_losers,
                'dynamic_updates': True,
                'data_source': 'Live NSE feeds via Dynamic Universe Manager',
                'universe_stats': self.universe_manager.get_universe_stats(),
                'excel_integration': self.universe_manager.get_excel_stats()
            },
            'parameters': {
                'min_gap_pct': self.min_gap_pct,
                'max_gap_pct': self.max_gap_pct,
                'gap_fill_ratio': self.gap_fill_ratio,
                'stop_loss_pct': self.stop_loss_pct
            },
            'risk_management': {
                'max_position_size_pct': self.max_position_size_pct,
                'target_reward_ratio': self.target_reward_ratio
            }
        }
    
    def reset_daily_state(self) -> None:
        """Reset daily state for the strategy"""
        logger.info("Gainer/Loser strategy daily state reset")
    
    def force_excel_update(self) -> bool:
        """Force immediate Excel update with current universe"""
        return self.universe_manager.force_excel_update()
    
    def get_excel_integration_status(self) -> Dict[str, Any]:
        """Get detailed Excel integration status"""
        return self.universe_manager.get_excel_stats()