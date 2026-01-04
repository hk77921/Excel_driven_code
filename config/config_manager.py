"""
Configuration Management
=======================
All trading parameters are configurable via YAML files.
This ensures consistency across all modes (backtest, paper, live).

Files:
- trading_config.yaml: Capital and risk parameters
- timing_config.yaml: Timing intelligence settings  
- symbols.yaml: List of tradable symbols
- rules.yaml: Screener rules
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from src.core import TradeParameters, CapitalParameters


logger = logging.getLogger(__name__)


class ConfigManager:
    """
    Configuration management system.
    
    Loads YAML configs and provides validated parameters
    for trading engine and execution modes.
    """
    
    def __init__(self, config_dir: str = "config"):
        """
        Initialize config manager.
        
        Args:
            config_dir: Directory containing config files
        """
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        
        self._trading_config = None
        self._timing_config = None
        self._adaptive_config = None
        self._symbols = None
        self._rules = None
    
    # ====== TRADING CONFIG ======
    
    def load_trading_config(self) -> Dict[str, Any]:
        """Load trading configuration"""
        if self._trading_config:
            return self._trading_config
        
        config_file = self.config_dir / "trading_config.yaml"
        
        if not config_file.exists():
            logger.warning(f"Config file not found: {config_file}")
            self._trading_config = self._get_default_trading_config()
            return self._trading_config
        
        with open(config_file, 'r', encoding='utf-8') as f:
            self._trading_config = yaml.safe_load(f) or {}
        
        return self._trading_config
    
    def get_capital_parameters(self) -> CapitalParameters:
        """Get capital parameters from config"""
        config = self.load_trading_config()
        capital_config = config.get('capital', {})
        
        return CapitalParameters(
            total_capital=capital_config.get('total', 5000),
            risk_per_trade=capital_config.get('risk_per_trade', 0.005),
            max_daily_loss_pct=capital_config.get('max_daily_loss_pct', 0.02),
            max_open_positions=capital_config.get('max_open_positions', 5),
            max_per_sector=capital_config.get('max_per_sector', 2),
            safety_buffer_pct=capital_config.get('safety_buffer_pct', 0.15)
        )
    
    def get_trade_parameters(self) -> TradeParameters:
        """Get trade parameters from config"""
        config = self.load_trading_config()
        trade_config = config.get('trading', {})
        
        return TradeParameters(
            atr_period=trade_config.get('atr_period', 14),
            sl_atr_mult=trade_config.get('sl_atr_mult', 1.5),
            target_atr_mult=trade_config.get('target_atr_mult', 2.0),
            partial_exit_ratio=trade_config.get('partial_exit_ratio', 0.8),
            partial_exit_qty_pct=trade_config.get('partial_exit_qty_pct', 0.5),
            trailing_sl_atr_mult=trade_config.get('trailing_sl_atr_mult', 1.5),
            order_timeout_seconds=trade_config.get('order_timeout_seconds', 300)
        )
    
    def get_execution_config(self, mode: str = 'PAPER') -> Dict[str, Any]:
        """Get execution mode configuration"""
        config = self.load_trading_config()
        exec_config = config.get('execution', {})
        return exec_config.get(mode, {})
    
    # ====== ADAPTIVE STRATEGIES CONFIG ======
    
    def load_adaptive_strategies_config(self) -> Dict[str, Any]:
        """Load adaptive strategies configuration"""
        if self._adaptive_config is not None:
            return self._adaptive_config
        
        config_file = self.config_dir / "adaptive_strategies_config.yaml"
        
        try:
            if config_file.exists():
                with open(config_file, 'r') as f:
                    self._adaptive_config = yaml.safe_load(f)
                logger.info("Adaptive strategies config loaded")
            else:
                self._adaptive_config = self._get_default_adaptive_config()
                logger.info("Using default adaptive strategies config")
        except Exception as e:
            logger.error(f"Failed to load adaptive strategies config: {e}")
            self._adaptive_config = self._get_default_adaptive_config()
        
        return self._adaptive_config
    
    def _get_default_adaptive_config(self) -> Dict[str, Any]:
        """Get default adaptive strategies configuration"""
        return {
            'adaptive_strategies': {
                'manager': {
                    'mode': 'AUTO',
                    'strategy_weights': {
                        'gap_weight': 0.25,
                        'momentum_weight': 0.25,
                        'volatility_weight': 0.25,
                        'correlation_weight': 0.25
                    },
                    'risk_management': {
                        'max_combined_risk_mult': 2.0,
                        'min_confidence_required': 0.6
                    }
                },
                'gap_trading': {
                    'base_parameters': {
                        'base_atr_mult': 1.5,
                        'base_target_mult': 2.0,
                        'base_partial_exit': 0.8
                    }
                },
                'momentum_adaptive': {
                    'thresholds': {
                        'strong_momentum_threshold': 80.0,
                        'weak_momentum_threshold': 40.0
                    }
                },
                'volatility_regime': {
                    'vix_thresholds': {
                        'low_vix_threshold': 15.0,
                        'normal_vix_threshold': 25.0,
                        'high_vix_threshold': 35.0
                    }
                },
                'correlation_sync': {
                    'thresholds': {
                        'high_correlation_threshold': 0.7,
                        'medium_correlation_threshold': 0.3,
                        'negative_correlation_threshold': -0.3
                    }
                }
            }
        }
    
    # def get_adaptive_manager_config(self) -> Dict[str, Any]:
    #     """Get adaptive strategy manager configuration"""
    #     config = self.load_adaptive_strategies_config()
    #     return config.get('adaptive_strategies', {}).get('manager', {})
    
    # def get_gap_trading_config(self) -> Dict[str, Any]:
    #     """Get gap trading strategy configuration"""
    #     config = self.load_adaptive_strategies_config()
    #     return config.get('adaptive_strategies', {}).get('gap_trading', {})
    
    # def get_momentum_adaptive_config(self) -> Dict[str, Any]:
    #     """Get momentum adaptive strategy configuration"""
    #     config = self.load_adaptive_strategies_config()
    #     return config.get('adaptive_strategies', {}).get('momentum_adaptive', {})
    
    # def get_volatility_regime_config(self) -> Dict[str, Any]:
    #     """Get volatility regime strategy configuration"""
    #     config = self.load_adaptive_strategies_config()
    #     return config.get('adaptive_strategies', {}).get('volatility_regime', {})
    
    # def get_correlation_sync_config(self) -> Dict[str, Any]:
    #     """Get correlation sync strategy configuration"""
    #     config = self.load_adaptive_strategies_config()
    #     return config.get('adaptive_strategies', {}).get('correlation_sync', {})
    
    # def get_market_detector_config(self) -> Dict[str, Any]:
    #     """Get market detector configuration"""
    #     config = self.load_adaptive_strategies_config()
    #     return config.get('adaptive_strategies', {}).get('market_detector', {})
    
    # ====== TIMING CONFIG ======
    
    def load_timing_config(self) -> Dict[str, Any]:
        """Load timing configuration"""
        if self._timing_config:
            return self._timing_config
        
        timing_file = self.config_dir / "timing_config.yaml"
        
        if timing_file.exists():
            with open(timing_file, 'r', encoding='utf-8') as f:
                self._timing_config = yaml.safe_load(f)
        else:
            # Default timing config
            logger.warning(f"Timing config not found at {timing_file}, using defaults")
            self._timing_config = {
                'timing': {
                    'enabled': False,
                    'regime_detection': {
                        'index_symbol': '^NSEI',
                        'lookback_days': 30
                    }
                }
            }
        
        logger.info(f"Timing config loaded: enabled={self._timing_config.get('timing', {}).get('enabled', False)}")
        return self._timing_config
    
    def get_timing_parameters(self) -> Dict[str, Any]:
        """Get timing parameters from config"""
        config = self.load_timing_config()
        return config.get('timing', {})
    
    def is_timing_enabled(self) -> bool:
        """Check if timing intelligence is enabled"""
        timing_config = self.get_timing_parameters()
        return timing_config.get('enabled', False)
    
    # ====== SYMBOLS ======
    
    def load_symbols(self) -> Dict[str, Dict[str, str]]:
        """Load tradable symbols"""
        if self._symbols:
            return self._symbols
        
        symbols_file = self.config_dir / "symbols.yaml"
        
        if not symbols_file.exists():
            logger.warning(f"Symbols file not found: {symbols_file}")
            return {}
        
        with open(symbols_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        
        self._symbols = data.get('symbols', {})
        return self._symbols
    
    def get_enabled_symbols(self) -> list:
        """Get list of enabled symbols"""
        symbols = self.load_symbols()
        return [s for s, cfg in symbols.items() if cfg.get('enabled', False)]
    
    # ====== RULES ======
    
    def load_rules(self) -> Dict[str, Any]:
        """Load screener rules"""
        if self._rules:
            return self._rules
        
        rules_file = self.config_dir / "rules.yaml"
        
        if not rules_file.exists():
            logger.warning(f"Rules file not found: {rules_file}")
            self._rules = self._get_default_rules()
            return self._rules
        
        with open(rules_file, 'r', encoding='utf-8') as f:
            self._rules = yaml.safe_load(f) or {}
        
        return self._rules
    
    # ====== DEFAULTS ======
    
    @staticmethod
    def _get_default_trading_config() -> Dict[str, Any]:
        """Get default trading configuration"""
        return {
            'capital': {
                'total': 5000,
                'risk_per_trade': 0.005,
                'max_daily_loss_pct': 0.02,
                'max_open_positions': 5,
                'max_per_sector': 2,
                'safety_buffer_pct': 0.15
            },
            'trading': {
                'atr_period': 14,
                'sl_atr_mult': 1.5,
                'target_atr_mult': 2.0,
                'partial_exit_ratio': 0.8,
                'partial_exit_qty_pct': 0.5,
                'trailing_sl_atr_mult': 1.5,
                'order_timeout_seconds': 300
            },
            'execution': {
                'BACKTEST': {
                    'mode': 'backtest',
                    'data_source': 'yfinance'
                },
                'PAPER': {
                    'mode': 'paper',
                    'broker': 'paper_broker'
                },
                'LIVE': {
                    'mode': 'live',
                    'broker': 'kite'
                }
            }
        }
    
    @staticmethod
    def _get_default_rules() -> Dict[str, Any]:
        """Get default screener rules"""
        return {
            'screening': {
                'min_adtv_cr': 5.0,
                'min_atr_pct': 2.0,
                'max_atr_pct': 5.0,
                'min_adx': 20.0,
                'min_vol_ratio': 1.0,
                'max_ema50_distance_pct': 5.0,
                'price_ema20_range_pct': 3.0
            },
            'trading_rules': {
                'max_trades_per_day': 5,
                'rel_strength_lookback': 30,
                'trend_required': 'BULLISH',
                'require_atr_contraction': False,
                'require_adx_rising': False,
                'require_rel_strength': False
            }
        }
    
    def create_default_configs(self):
        """Create default config files if they don't exist"""
        # Trading config
        trading_file = self.config_dir / "trading_config.yaml"
        if not trading_file.exists():
            with open(trading_file, 'w') as f:
                yaml.dump(self._get_default_trading_config(), f, default_flow_style=False)
            logger.info(f"Created default config: {trading_file}")
        
        # Rules
        rules_file = self.config_dir / "rules.yaml"
        if not rules_file.exists():
            with open(rules_file, 'w') as f:
                yaml.dump(self._get_default_rules(), f, default_flow_style=False)
            logger.info(f"Created default rules: {rules_file}")
        
        # Symbols (empty template)
        symbols_file = self.config_dir / "symbols.yaml"
        if not symbols_file.exists():
            with open(symbols_file, 'w') as f:
                yaml.dump({
                    'symbols': {
                        'SBIN': {'sector': 'FINANCIALS', 'enabled': True},
                        'INFY': {'sector': 'IT', 'enabled': True},
                        'TCS': {'sector': 'IT', 'enabled': False}
                    }
                }, f, default_flow_style=False)
            logger.info(f"Created default symbols: {symbols_file}")
    
    def get_adaptive_manager_config(self) -> Dict[str, Any]:
        """Get adaptive strategy manager configuration"""
        config = self.load_adaptive_strategies_config()
        return config.get('adaptive_strategies', {}).get('manager', {})
    
    def get_gap_trading_config(self) -> Dict[str, Any]:
        """Get gap trading strategy configuration"""
        config = self.load_adaptive_strategies_config()
        return config.get('adaptive_strategies', {}).get('gap_trading', {})
    
    def get_momentum_adaptive_config(self) -> Dict[str, Any]:
        """Get momentum adaptive strategy configuration"""
        config = self.load_adaptive_strategies_config()
        return config.get('adaptive_strategies', {}).get('momentum_adaptive', {})
    
    def get_volatility_regime_config(self) -> Dict[str, Any]:
        """Get volatility regime strategy configuration"""
        config = self.load_adaptive_strategies_config()
        return config.get('adaptive_strategies', {}).get('volatility_regime', {})
    
    def get_correlation_sync_config(self) -> Dict[str, Any]:
        """Get correlation sync strategy configuration"""
        config = self.load_adaptive_strategies_config()
        return config.get('adaptive_strategies', {}).get('correlation_sync', {})
    
    def get_market_detector_config(self) -> Dict[str, Any]:
        """Get market detector configuration"""
        config = self.load_adaptive_strategies_config()
        return config.get('adaptive_strategies', {}).get('market_detector', {})
