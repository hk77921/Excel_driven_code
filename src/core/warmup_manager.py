"""
Warmup Manager - Strategy & Indicator Initialization
===================================================

Implements the "Warm-up Strategies & Indicators" phase to prevent cold start issues.
Pre-calculates technical indicators and initializes strategies with historical data.

This ensures the system starts with reliable indicator values instead of NaN/empty data.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class WarmupStatus(Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS" 
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class WarmupTask:
    """Individual warmup task"""
    name: str
    component: str
    status: WarmupStatus
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    data_points: int = 0
    
    def mark_completed(self, duration: float, data_points: int = 0):
        self.status = WarmupStatus.COMPLETED
        self.duration_seconds = duration
        self.data_points = data_points
    
    def mark_failed(self, error: str):
        self.status = WarmupStatus.FAILED
        self.error_message = error


@dataclass
class WarmupResult:
    """Result of warmup process"""
    success: bool
    total_duration: float
    tasks: List[WarmupTask]
    symbols_warmed: List[str]
    indicators_ready: Dict[str, bool]
    
    @property
    def failed_tasks(self) -> List[WarmupTask]:
        return [task for task in self.tasks if task.status == WarmupStatus.FAILED]
    
    @property
    def completed_tasks(self) -> List[WarmupTask]:
        return [task for task in self.tasks if task.status == WarmupStatus.COMPLETED]


class WarmupManager:
    """
    Strategy and Indicator Warmup Manager.
    
    Key responsibilities:
    1. Pre-load historical data for all trading symbols
    2. Calculate technical indicators with sufficient history
    3. Initialize strategy managers with market context
    4. Warm up timing filters and regime detection
    5. Validate all components are ready before trading
    """
    
    def __init__(self, symbols: List[str], lookback_days: int = 60):
        self.symbols = symbols
        self.lookback_days = lookback_days
        
        # Warmup state
        self.status = WarmupStatus.NOT_STARTED
        self.tasks: List[WarmupTask] = []
        self.warmed_data: Dict[str, pd.DataFrame] = {}
        self.indicator_cache: Dict[str, Dict[str, Any]] = {}
        
        # Warmup configuration
        self.required_indicators = [
            'SMA_20', 'SMA_50', 'EMA_12', 'EMA_26',
            'RSI_14', 'MACD', 'ATR_14' 
        ]
        
        self.min_data_points = 100  # Minimum data points needed for reliable indicators
        
        logger.info(f"WarmupManager initialized for {len(symbols)} symbols with {lookback_days} days lookback")
    
    def execute_warmup(self, force_refresh: bool = False) -> WarmupResult:
        """
        Execute complete warmup sequence.
        
        Args:
            force_refresh: Force refresh of all cached data
            
        Returns:
            WarmupResult with success status and details
        """
        start_time = datetime.now()
        self.status = WarmupStatus.IN_PROGRESS
        self.tasks = []
        
        logger.info("🔥 Starting system warmup sequence...")
        
        try:
            # Task 1: Load historical market data
            self._add_and_execute_task(
                "load_market_data",
                "MarketData",
                lambda: self._load_historical_data(force_refresh)
            )
            
            # Task 2: Calculate technical indicators
            self._add_and_execute_task(
                "calculate_indicators", 
                "TechnicalIndicators",
                lambda: self._calculate_indicators()
            )
            
            # Task 3: Initialize timing components
            self._add_and_execute_task(
                "warmup_timing",
                "TimingFilter",
                lambda: self._warmup_timing_components()
            )
            
            # Task 4: Initialize market regime detection
            self._add_and_execute_task(
                "warmup_regime",
                "MarketRegime", 
                lambda: self._warmup_market_regime()
            )
            
            # Task 5: Initialize strategy managers
            self._add_and_execute_task(
                "warmup_strategies",
                "StrategyManagers",
                lambda: self._warmup_strategy_managers()
            )
            
            # Task 6: Validate warmup completeness
            self._add_and_execute_task(
                "validate_warmup",
                "Validation",
                lambda: self._validate_warmup_completeness()
            )
            
            # Calculate results
            total_duration = (datetime.now() - start_time).total_seconds()
            failed_tasks = self.failed_tasks
            
            if failed_tasks:
                self.status = WarmupStatus.FAILED
                success = False
                logger.error(f"❌ Warmup FAILED with {len(failed_tasks)} task failures")
            else:
                self.status = WarmupStatus.COMPLETED  
                success = True
                logger.info(f"✅ Warmup COMPLETED in {total_duration:.2f} seconds")
            
            result = WarmupResult(
                success=success,
                total_duration=total_duration,
                tasks=self.tasks.copy(),
                symbols_warmed=list(self.warmed_data.keys()),
                indicators_ready=self._get_indicator_status()
            )
            
            # Log summary
            self._log_warmup_summary(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Warmup sequence failed with exception: {e}")
            self.status = WarmupStatus.FAILED
            
            return WarmupResult(
                success=False,
                total_duration=(datetime.now() - start_time).total_seconds(), 
                tasks=self.tasks.copy(),
                symbols_warmed=[],
                indicators_ready={}
            )
    
    def _add_and_execute_task(self, name: str, component: str, task_function):
        """Add and execute a warmup task"""
        task = WarmupTask(name, component, WarmupStatus.IN_PROGRESS)
        self.tasks.append(task)
        
        logger.info(f"  🔄 Executing: {name}")
        task_start = datetime.now()
        
        try:
            result = task_function()
            duration = (datetime.now() - task_start).total_seconds()
            
            # Extract data points if returned
            data_points = 0
            if isinstance(result, tuple) and len(result) == 2:
                success, data_points = result
            elif isinstance(result, int):
                data_points = result
            
            task.mark_completed(duration, data_points)
            logger.info(f"  ✅ Completed: {name} ({duration:.2f}s, {data_points} data points)")
            
        except Exception as e:
            duration = (datetime.now() - task_start).total_seconds()
            task.mark_failed(str(e))
            logger.error(f"  ❌ Failed: {name} ({duration:.2f}s) - {e}")
    
    def _load_historical_data(self, force_refresh: bool = False) -> Tuple[bool, int]:
        """Load historical market data for all symbols"""
        try:
            import yfinance as yf
            
            total_data_points = 0
            successful_symbols = 0
            
            for symbol in self.symbols:
                try:
                    # Skip if already warmed and not forcing refresh
                    if not force_refresh and symbol in self.warmed_data:
                        continue
                    
                    # Calculate date range
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=self.lookback_days)
                    
                    # Download data
                    #ticker = yf.Ticker(symbol)
                    ticker = yf.Ticker(f"{symbol}.NS")
                    data = ticker.history(
                        start=start_date.strftime('%Y-%m-%d'),
                        end=end_date.strftime('%Y-%m-%d'),
                        interval='1d'
                    )
                    
                    if data.empty or len(data) < 20:  # Need minimum data
                        logger.warning(f"Insufficient data for {symbol}: {len(data)} days")
                        continue
                    
                     # --- CANONICALIZE OHLCV ---
                    data.columns = data.columns.str.lower()

                    required = ['open', 'high', 'low', 'close', 'volume']
                    missing = [c for c in required if c not in data.columns]

                    if missing:
                        raise ValueError(f"Missing columns for {symbol}: {missing}")

                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        data[col] = pd.to_numeric(data  [col], errors='coerce')

                    if data[['open','high','low','close']].isna().any().any():
                        raise ValueError("NaNs found in OHLC data after coercion")


                    # Store warmed data
                    self.warmed_data[symbol] = data
                    total_data_points += len(data)
                    successful_symbols += 1
                    
                    logger.debug(f"Loaded {len(data)} days for {symbol}")
                    
                except Exception as e:
                    logger.error(f"Failed to load data for {symbol}: {e}")



           
            
            if successful_symbols == 0:
                raise Exception("No symbols successfully loaded")
            
            logger.info(f"Market data loaded: {successful_symbols}/{len(self.symbols)} symbols, {total_data_points} total data points")
            return True, total_data_points
            
        except Exception as e:
            logger.error(f"Historical data loading failed: {e}")
            raise e
    
    def _calculate_indicators(self) -> Tuple[bool, int]:
        """Calculate technical indicators for all warmed symbols"""
        try:
            import talib
            
            total_indicators = 0
            
            for symbol, data in self.warmed_data.items():
                try:
                    indicators = {}
                    
                    #logger.info(f"Calculating indicators for {symbol} with top data:\n{data.head()}")
                    # Price data
                    high = np.asarray(data['high'].values, dtype=np.float64)
                    low = np.asarray(data['low'].values, dtype=np.float64)
                    close = np.asarray(data['close'].values, dtype=np.float64)  # Fill missing values using forward fill or backward fill, depending on which is closest in time
                    volume = np.asarray(data['volume'].values, dtype=np.float64)

                    
                    # Moving Averages
                    indicators['SMA_20'] = talib.SMA(close, timeperiod=20)
                    indicators['SMA_50'] = talib.SMA(close, timeperiod=50)  
                    indicators['EMA_12'] = talib.EMA(close, timeperiod=12)
                    indicators['EMA_26'] = talib.EMA(close, timeperiod=26)
                    
                    # Momentum Indicators
                    indicators['RSI_14'] = talib.RSI(close, timeperiod=14)
                    
                    # MACD
                    macd, macd_signal, macd_hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
                    indicators['MACD'] = macd
                    indicators['MACD_Signal'] = macd_signal
                    indicators['MACD_Histogram'] = macd_hist
                    
                    # Volatility Indicators
                    indicators['ATR_14'] = talib.ATR(np.asarray(high), np.asarray(low), np.asarray(close), timeperiod=14)
                    
                    # Bollinger Bands  
                    bb_upper, bb_middle, bb_lower = talib.BBANDS(np.asarray(close), timeperiod=20, nbdevup=2, nbdevdn=2)
                    indicators['BB_Upper'] = bb_upper
                    indicators['BB_Middle'] = bb_middle
                    indicators['BB_Lower'] = bb_lower
                    
                    # Volume Indicators
                    indicators['Volume_SMA'] = talib.SMA(np.asarray(volume), timeperiod=20)
                    
                    # Store indicators
                    self.indicator_cache[symbol] = indicators
                    total_indicators += len(indicators)
                    
                    # Validate indicators (check for sufficient non-NaN values)
                    valid_indicators = 0
                    for name, values in indicators.items():
                        if values is not None:
                            non_nan_count = pd.Series(values).count()
                            if non_nan_count >= 20:  # Minimum valid values
                                valid_indicators += 1
                    
                    logger.debug(f"Calculated {valid_indicators}/{len(indicators)} valid indicators for {symbol}")
                    
                except Exception as e:
                    logger.error(f"Indicator calculation failed for {symbol}: {e}")
            
            logger.info(f"Technical indicators calculated: {total_indicators} total indicators")
            return True, total_indicators
            
        except ImportError:
            logger.warning("TA-Lib not available, using simplified indicators")
            return self._calculate_simple_indicators()
        except Exception as e:
            logger.error(f"Indicator calculation failed: {e}")
            raise e
    
    def _calculate_simple_indicators(self) -> Tuple[bool, int]:
        """Calculate simplified indicators without TA-Lib"""
        try:
            total_indicators = 0
            
           

            for symbol, data in self.warmed_data.items():
                try:
                    indicators = {}
                    
                    
                    # Simple moving averages
                    indicators['SMA_20'] = data['close'].rolling(window=20).mean()
                    indicators['SMA_50'] = data['close'].rolling(window=50).mean()
                    
                    # Exponential moving averages
                    indicators['EMA_12'] = data['close'].ewm(span=12).mean()
                    indicators['EMA_26'] = data['close'].ewm(span=26).mean()
                    
                    # Simple RSI
                    delta = data['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    indicators['RSI_14'] = 100 - (100 / (1 + rs))
                    
                    # Simple ATR (True Range)
                    high_low = data['high'] - data['low']
                    high_close = (data['high'] - data['close'].shift()).abs()
                    low_close = (data['low'] - data['close'].shift()).abs()
                    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                    indicators['ATR_14'] = true_range.rolling(window=14).mean()
                    

                    # Bollinger Bands
                    sma_20 = data['close'].rolling(window=20).mean()
                    std_20 = data['close'].rolling(window=20).std()
                    indicators['BB_Upper'] = sma_20 + (2 * std_20)
                    indicators['BB_Middle'] = sma_20
                    indicators['BB_Lower'] = sma_20 - (2 * std_20)




                    # Store indicators
                    self.indicator_cache[symbol] = indicators
                    total_indicators += len(indicators)
                    
                except Exception as e:
                    logger.error(f"Simple indicator calculation failed for {symbol}: {e}")
            
            logger.info(f"Simple indicators calculated: {total_indicators} total indicators")
            return True, total_indicators
            
        except Exception as e:
            logger.error(f"Simple indicator calculation failed: {e}")
            raise e
    
    def _warmup_timing_components(self) -> Tuple[bool, int]:
        """Initialize timing filter components"""
        try:
            # This would initialize timing filters with historical data
            # For now, just verify timing components can be imported and initialized
            
            from src.timing.market_regime import MarketRegimeManager
            from src.timing.timing_filter import TimingFilter
            
            # Initialize components (they will warm themselves up)
            regime_manager = MarketRegimeManager()
            
            # Get timing info to trigger initialization
            timing_info = regime_manager.get_market_regime()
            
            logger.info(f"Timing components warmed up - Current regime: {timing_info}")
            return True, 1
            
        except Exception as e:
            logger.error(f"Timing warmup failed: {e}")
            raise e
    
    def _warmup_market_regime(self) -> Tuple[bool, int]:
        """Initialize market regime detection with historical context"""
        try:
            # Initialize regime detection with market data
            regimes_detected = 0
            
            # Use the warmed data to detect recent market regimes
            for symbol, data in self.warmed_data.items():
                if len(data) < 30:  # Need sufficient data
                    continue
                
                # Simple regime detection based on volatility and trends
                returns = data['close'].pct_change().dropna()
                volatility = returns.rolling(window=20).std()
                
                recent_vol = volatility.iloc[-5:].mean() if len(volatility) > 5 else 0.02
                recent_return = returns.iloc[-10:].mean() if len(returns) > 10 else 0.0
                
                # Classify regime (simplified)
                if recent_vol > 0.03:
                    regime = "HIGH_VOLATILITY"
                elif recent_return > 0.01:
                    regime = "BULLISH"
                elif recent_return < -0.01:
                    regime = "BEARISH"
                else:
                    regime = "NEUTRAL"
                
                regimes_detected += 1
                logger.debug(f"{symbol} regime: {regime} (vol: {recent_vol:.3f})")
                
                # Only process first few symbols for warmup
                if regimes_detected >= 5:
                    break
            
            logger.info(f"Market regime detection warmed up for {regimes_detected} symbols")
            return True, regimes_detected
            
        except Exception as e:
            logger.error(f"Market regime warmup failed: {e}")
            raise e
    
    def _warmup_strategy_managers(self) -> Tuple[bool, int]:
        """Initialize strategy managers with market context"""
        try:
            strategies_warmed = 0
            
            # Initialize adaptive strategy manager if available
            try:
                from src.strategies.adaptive_manager import AdaptiveStrategyManager
                
                adaptive_manager = AdaptiveStrategyManager()
                
                # Warm up with a sample signal for each symbol
                for symbol in list(self.warmed_data.keys())[:3]:  # Limit to first 3 symbols
                    try:
                        # Create a sample signal for warmup
                        from src.core.models import ScreenerSignal
                        
                        data = self.warmed_data[symbol]
                        latest_price = data['close'].iloc[-1]
                        
                        sample_signal = ScreenerSignal(
                            symbol=symbol,
                            score=75.0,
                            atr=1.0,
                            adx=25.0,
                            volume_ratio=1.2,
                            trend="BULLISH",
                            price=float(latest_price),
                            sector="Technology",
                            timestamp=datetime.now()
                        )
                        
                        # Evaluate the signal to warm up the strategy
                        decision = adaptive_manager.evaluate_trade_entry(sample_signal)
                        strategies_warmed += 1
                        
                        logger.debug(f"Strategy warmup for {symbol}: confidence {decision.confidence_score:.2f}")
                        
                    except Exception as e:
                        logger.warning(f"Strategy warmup failed for {symbol}: {e}")
                
            except ImportError:
                logger.info("Adaptive strategy manager not available for warmup")
            
            logger.info(f"Strategy managers warmed up for {strategies_warmed} symbols")
            return True, strategies_warmed
            
        except Exception as e:
            logger.error(f"Strategy warmup failed: {e}")
            raise e
    
    def _validate_warmup_completeness(self) -> Tuple[bool, int]:
        """Validate that warmup is complete and components are ready"""
        try:
            validations_passed = 0
            
            # Check 1: Sufficient symbols warmed
            if len(self.warmed_data) < len(self.symbols) * 0.8:  # At least 80% success
                raise Exception(f"Only {len(self.warmed_data)}/{len(self.symbols)} symbols warmed")
            validations_passed += 1
            
            # Check 2: Indicators calculated
            if len(self.indicator_cache) == 0:
                raise Exception("No indicators calculated")
            validations_passed += 1
            
            # Check 3: Validate indicator quality
            for symbol, indicators in self.indicator_cache.items():
                for name, values in indicators.items():
                    if values is not None and hasattr(values, '__len__'):
                        valid_count = pd.Series(values).count()
                        if valid_count < 10:  # Minimum valid data points
                            logger.warning(f"Low data quality for {symbol}.{name}: {valid_count} points")
            validations_passed += 1
            
            # Check 4: Verify data recency
            for symbol, data in self.warmed_data.items():
                latest_date = data.index[-1]
                days_old = (datetime.now().date() - latest_date.date()).days
                if days_old > 3:  # Data should be recent (within 3 days)
                    logger.warning(f"Stale data for {symbol}: {days_old} days old")
            validations_passed += 1
            
            logger.info(f"Warmup validation passed: {validations_passed}/4 checks")
            return True, validations_passed
            
        except Exception as e:
            logger.error(f"Warmup validation failed: {e}")
            raise e
    
    def get_warmed_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Get warmed historical data for a symbol"""
        return self.warmed_data.get(symbol)
    
    def get_indicator_values(self, symbol: str, indicator: str) -> Optional[Any]:
        """Get calculated indicator values for a symbol"""
        return self.indicator_cache.get(symbol, {}).get(indicator)
    
    def is_symbol_ready(self, symbol: str) -> bool:
        """Check if a symbol is fully warmed up and ready"""
        if symbol not in self.warmed_data:
            return False
        
        if symbol not in self.indicator_cache:
            return False
        
        # Check if we have sufficient data
        data = self.warmed_data[symbol]
        if len(data) < 30:  # Minimum data requirement
            return False
        
        # Check if indicators have sufficient valid data
        indicators = self.indicator_cache[symbol]
        for name, values in indicators.items():
            if values is not None and hasattr(values, '__len__'):
                valid_count = pd.Series(values).count()
                if valid_count < 20:  # Minimum for reliable indicators
                    return False
        
        return True
    
    def get_warmup_status(self) -> Dict:
        """Get comprehensive warmup status"""
        ready_symbols = [s for s in self.symbols if self.is_symbol_ready(s)]
        
        indicator_status = {}
        for indicator in self.required_indicators:
            symbols_with_indicator = 0
            for symbol in self.symbols:
                if self.get_indicator_values(symbol, indicator) is not None:
                    symbols_with_indicator += 1
            indicator_status[indicator] = f"{symbols_with_indicator}/{len(self.symbols)}"
        
        return {
            'status': self.status.value,
            'symbols_ready': f"{len(ready_symbols)}/{len(self.symbols)}",
            'ready_symbols': ready_symbols,
            'indicators_calculated': len(self.indicator_cache),
            'indicator_status': indicator_status,
            'total_data_points': sum(len(data) for data in self.warmed_data.values()),
            'tasks': [
                {
                    'name': task.name,
                    'status': task.status.value,
                    'duration': task.duration_seconds,
                    'data_points': task.data_points,
                    'error': task.error_message
                }
                for task in self.tasks
            ]
        }
    
    def _get_indicator_status(self) -> Dict[str, bool]:
        """Get status of all required indicators"""
        status = {}
        for indicator in self.required_indicators:
            symbols_ready = 0
            for symbol in self.symbols:
                if self.get_indicator_values(symbol, indicator) is not None:
                    symbols_ready += 1
            
            # Consider ready if at least 80% of symbols have the indicator
            status[indicator] = symbols_ready >= len(self.symbols) * 0.8
        
        return status
    
    def _log_warmup_summary(self, result: WarmupResult):
        """Log detailed warmup summary"""
        logger.info("="*60)
        logger.info("WARMUP SUMMARY")
        logger.info("="*60)
        logger.info(f"Status: {'SUCCESS' if result.success else 'FAILED'}")
        logger.info(f"Duration: {result.total_duration:.2f} seconds")
        logger.info(f"Symbols warmed: {len(result.symbols_warmed)}/{len(self.symbols)}")
        logger.info(f"Tasks completed: {len(result.completed_tasks)}/{len(result.tasks)}")
        
        if result.failed_tasks:
            logger.info(f"Failed tasks: {len(result.failed_tasks)}")
            for task in result.failed_tasks:
                logger.error(f"  - {task.name}: {task.error_message}")
        
        logger.info("Indicator Status:")
        for indicator, ready in result.indicators_ready.items():
            status_icon = "✅" if ready else "❌"
            logger.info(f"  {status_icon} {indicator}")
        
        logger.info("="*60)
    
    @property 
    def failed_tasks(self) -> List[WarmupTask]:
        return [task for task in self.tasks if task.status == WarmupStatus.FAILED]