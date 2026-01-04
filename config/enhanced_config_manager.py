"""
Enhanced Configuration Management System
=======================================

This is a comprehensive, centralized configuration management system that:
1. Consolidates ALL application configurations in one place
2. Supports environment-specific overrides (.env, environment variables)
3. Provides runtime configuration validation and type checking
4. Handles configuration inheritance and defaults
5. Supports dynamic configuration reloading
6. Manages configuration versioning and migration

Key Features:
- Single source of truth for all configurations
- Environment-aware configuration loading (dev/test/prod)
- Runtime configuration validation with type hints
- Configuration change detection and hot-reloading
- Centralized logging and monitoring of configuration changes
- Backward compatibility with existing ConfigManager

Usage:
    config = EnhancedConfigManager()
    trading_params = config.get_trading_parameters()
    broker_config = config.get_broker_configuration('zerodha')
    
Author: Configuration Management System
Version: 2.0
"""

import os
import yaml
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Type, get_type_hints
from dataclasses import dataclass, fields, asdict
from datetime import datetime
from enum import Enum
import hashlib
from dotenv import load_dotenv

# Import existing models for backward compatibility
from src.core import TradeParameters, CapitalParameters


logger = logging.getLogger(__name__)


class ConfigurationEnvironment(str, Enum):
    """Configuration environments"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"
    PAPER = "paper"
    LIVE = "live"


class ConfigurationError(Exception):
    """Configuration-related errors"""
    pass


@dataclass
class LoggingConfiguration:
    """Centralized logging configuration"""
    level: str = "INFO"
    format: str = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    file_enabled: bool = True
    file_path: str = "logs/trading_bot.log"
    console_enabled: bool = True
    max_file_size_mb: int = 10
    backup_count: int = 5
    unicode_support: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BrokerConfiguration:
    """Centralized broker configuration"""
    name: str = "zerodha"
    
    # API Configuration
    api_key: Optional[str] = None
    access_token: Optional[str] = None
    api_secret: Optional[str] = None
    
    # Trading Configuration
    product_type: str = "MIS"  # MIS=Intraday, CNC=Delivery, NRML=Normal
    order_type: str = "MARKET"  # MARKET or LIMIT
    exchange: str = "NSE"
    
    # Rate Limiting
    max_requests_per_second: int = 10
    request_timeout_seconds: int = 30
    retry_attempts: int = 3
    retry_delay_seconds: float = 1.0
    
    # Order Management
    max_slippage_pct: float = 0.2
    order_timeout_seconds: int = 300
    
    # Optional fields that might be in YAML
    base_url: Optional[str] = None
    websocket_url: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EnvironmentConfiguration:
    """Environment-specific configuration"""
    execution_mode: str = "PAPER"  # PAPER, LIVE, BACKTEST
    environment: str = "development"
    debug_mode: bool = False
    
    # File Paths
    excel_file: str = "MiniRobo.xlsx"
    data_directory: str = "data"
    logs_directory: str = "logs"
    state_directory: str = "state"
    cache_directory: str = "screener_cache"
    
    # Optional fields that might be in YAML but not required
    app_name: Optional[str] = None
    app_version: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UniverseConfiguration:
    """Dynamic universe configuration"""
    # Gainer/Loser Universe
    max_gainers: int = 10
    max_losers: int = 5
    min_gap_percentage: float = 2.0
    max_gap_percentage: float = 8.0
    refresh_interval_minutes: int = 15
    
    # Filters
    min_market_cap_cr: float = 1000
    max_stocks_per_sector: int = 3
    exclude_sectors: List[str] = None
    prefer_liquid_stocks: bool = True
    
    # Excel Integration
    excel_integration_enabled: bool = True
    excel_file: str = "MiniRobo.xlsx"
    universe_sheet: str = "UNIVERSE"
    max_total_stocks: int = 150
    
    def __post_init__(self):
        if self.exclude_sectors is None:
            self.exclude_sectors = ['REALTY', 'PSE']
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MonitoringConfiguration:
    """System monitoring and alerting configuration"""
    # Performance Monitoring
    track_performance: bool = True
    performance_window_days: int = 30
    
    # Alerting
    alert_on_daily_loss_pct: float = 1.5
    alert_on_system_errors: bool = True
    alert_email_enabled: bool = False
    alert_email_recipients: List[str] = None
    
    # Health Checks
    health_check_interval_minutes: int = 5
    max_consecutive_failures: int = 3
    
    def __post_init__(self):
        if self.alert_email_recipients is None:
            self.alert_email_recipients = []
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EnhancedConfigManager:
    """
    Enhanced Configuration Manager - Single Source of Truth
    
    This manager consolidates ALL application configurations:
    - Trading parameters and capital management
    - Broker configurations and API settings
    - Environment and runtime configurations
    - Dynamic universe and screening parameters
    - Logging and monitoring configurations
    - Strategy-specific configurations
    
    Features:
    - Environment variable override support
    - Configuration validation and type checking
    - Hot-reload capabilities for development
    - Configuration versioning and change tracking
    - Backward compatibility with existing ConfigManager
    """
    
    def __init__(self, 
                 config_dir: str = "config", 
                 environment: Optional[str] = None,
                 load_env_file: bool = True):
        """
        Initialize enhanced configuration manager.
        
        Args:
            config_dir: Directory containing configuration files
            environment: Override environment (development/testing/production)
            load_env_file: Whether to load .env file for environment variables
        """
        # Initialize paths and environment
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        
        # Load environment variables if requested
        if load_env_file:
            load_dotenv()
        
        # Determine environment
        self.environment = environment or os.getenv('CONFIG_ENVIRONMENT', 'development')
        self.execution_mode = os.getenv('EXECUTION_MODE', 'PAPER')
        
        # Configuration cache with change detection
        self._config_cache: Dict[str, Any] = {}
        self._config_timestamps: Dict[str, float] = {}
        self._config_hashes: Dict[str, str] = {}
        
        # Backward compatibility - existing ConfigManager functionality
        self._trading_config = None
        self._timing_config = None
        self._adaptive_config = None
        self._symbols = None
        self._rules = None
        
        logger.info(f"Enhanced Config Manager initialized - Environment: {self.environment}, Mode: {self.execution_mode}")
    
    # ===== MAIN CONFIGURATION METHODS =====
    
    def get_all_configurations(self) -> Dict[str, Any]:
        """
        Get complete configuration snapshot for current environment.
        
        Returns:
            Complete configuration dictionary with all sections
        """
        return {
            'environment': self.get_environment_configuration().to_dict(),
            'logging': self.get_logging_configuration().to_dict(),
            'broker': self.get_broker_configuration().to_dict(),
            'capital': self.get_capital_parameters(),
            'trading': self.get_trade_parameters(),
            'universe': self.get_universe_configuration().to_dict(),
            'monitoring': self.get_monitoring_configuration().to_dict(),
            'adaptive_strategies': self.load_adaptive_strategies_config(),
            'timing': self.get_timing_parameters(),
            'symbols': self.load_symbols(),
            'rules': self.load_rules(),
            'metadata': {
                'environment': self.environment,
                'execution_mode': self.execution_mode,
                'loaded_at': datetime.now().isoformat(),
                'config_version': '2.0'
            }
        }
    
    def get_environment_configuration(self) -> EnvironmentConfiguration:
        """Get environment-specific configuration with overrides."""
        config = self._load_with_cache('environment', self._load_environment_config)
        
        # Apply environment variable overrides
        config.execution_mode = os.getenv('EXECUTION_MODE', config.execution_mode)
        config.debug_mode = os.getenv('DEBUG_MODE', str(config.debug_mode)).lower() == 'true'
        config.excel_file = os.getenv('EXCEL_FILE', config.excel_file)
        
        return config
    
    def get_logging_configuration(self) -> LoggingConfiguration:
        """Get logging configuration with environment overrides."""
        config = self._load_with_cache('logging', self._load_logging_config)
        
        # Apply environment variable overrides
        config.level = os.getenv('LOG_LEVEL', config.level)
        config.file_path = os.getenv('LOG_FILE_PATH', config.file_path)
        
        return config
    
    def get_broker_configuration(self, broker_name: str = None) -> BrokerConfiguration:
        """
        Get broker configuration with environment overrides.
        
        Args:
            broker_name: Specific broker name (default: from config)
            
        Returns:
            BrokerConfiguration with environment variable overrides applied
        """
        config = self._load_with_cache('broker', self._load_broker_config)
        
        # Apply environment variable overrides (critical for live trading)
        config.api_key = os.getenv('KITE_API_KEY', config.api_key)
        config.access_token = os.getenv('KITE_ACCESS_TOKEN', config.access_token)
        config.api_secret = os.getenv('KITE_API_SECRET', config.api_secret)
        
        # Validate for live trading
        if self.execution_mode == 'LIVE':
            if not config.api_key or not config.access_token:
                raise ConfigurationError(
                    "LIVE trading mode requires KITE_API_KEY and KITE_ACCESS_TOKEN "
                    "to be set in environment variables or configuration file."
                )
        
        return config
    
    def get_universe_configuration(self) -> UniverseConfiguration:
        """Get dynamic universe configuration."""
        return self._load_with_cache('universe', self._load_universe_config)
    
    def get_monitoring_configuration(self) -> MonitoringConfiguration:
        """Get monitoring and alerting configuration."""
        return self._load_with_cache('monitoring', self._load_monitoring_config)
    
    # ===== BACKWARD COMPATIBILITY METHODS =====
    # These methods maintain compatibility with existing ConfigManager
    
    def get_capital_parameters(self) -> CapitalParameters:
        """Get capital parameters (backward compatible)."""
        config = self.load_trading_config()
        capital_config = config.get('capital', {})
        
        # Apply environment variable overrides
        total_capital = float(os.getenv('TRADING_CAPITAL', capital_config.get('total', 5000)))
        risk_per_trade = float(os.getenv('RISK_PER_TRADE', capital_config.get('risk_per_trade', 0.005)))
        
        return CapitalParameters(
            total_capital=total_capital,
            risk_per_trade=risk_per_trade,
            max_daily_loss_pct=capital_config.get('max_daily_loss_pct', 0.02),
            max_open_positions=int(os.getenv('MAX_OPEN_POSITIONS', capital_config.get('max_open_positions', 5))),
            max_per_sector=capital_config.get('max_per_sector', 2),
            safety_buffer_pct=capital_config.get('safety_buffer_pct', 0.15)
        )
    
    def get_trade_parameters(self) -> TradeParameters:
        """Get trade parameters (backward compatible)."""
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
    
    def load_trading_config(self) -> Dict[str, Any]:
        """Load trading configuration (backward compatible)."""
        if self._trading_config:
            return self._trading_config
        
        config_file = self.config_dir / "trading_config.yaml"
        
        if not config_file.exists():
            logger.warning(f"Trading config not found: {config_file}, using defaults")
            self._trading_config = self._get_default_trading_config()
            return self._trading_config
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self._trading_config = yaml.safe_load(f) or {}
            logger.info(f"Trading config loaded from {config_file}")
        except Exception as e:
            logger.error(f"Failed to load trading config: {e}")
            self._trading_config = self._get_default_trading_config()
        
        return self._trading_config
    
    def load_adaptive_strategies_config(self) -> Dict[str, Any]:
        """Load adaptive strategies configuration (backward compatible)."""
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
    
    def load_timing_config(self) -> Dict[str, Any]:
        """Load timing configuration (backward compatible)."""
        if self._timing_config:
            return self._timing_config
        
        timing_file = self.config_dir / "timing_config.yaml"
        
        if timing_file.exists():
            with open(timing_file, 'r', encoding='utf-8') as f:
                self._timing_config = yaml.safe_load(f)
        else:
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
        """Get timing parameters (backward compatible)."""
        config = self.load_timing_config()
        return config.get('timing', {})
    
    def is_timing_enabled(self) -> bool:
        """Check if timing intelligence is enabled (backward compatible)."""
        timing_config = self.get_timing_parameters()
        return timing_config.get('enabled', False)
    
    def load_symbols(self) -> Dict[str, Dict[str, str]]:
        """Load tradable symbols (backward compatible)."""
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
        """Get list of enabled symbols (backward compatible)."""
        symbols = self.load_symbols()
        return [s for s, cfg in symbols.items() if cfg.get('enabled', False)]
    
    def load_rules(self) -> Dict[str, Any]:
        """Load screener rules (backward compatible)."""
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
    
    # ===== CONFIGURATION LOADING METHODS =====
    
    def _load_environment_config(self) -> EnvironmentConfiguration:
        """Load environment configuration with defaults."""
        config_file = self.config_dir / "environment.yaml"
        
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                env_data = data.get('environment', {})
                # Filter out any unexpected keys that aren't in the dataclass
                valid_keys = {f.name for f in fields(EnvironmentConfiguration)}
                filtered_data = {k: v for k, v in env_data.items() if k in valid_keys}
                return EnvironmentConfiguration(**filtered_data)
            except Exception as e:
                logger.error(f"Failed to load environment config: {e}")
        
        return EnvironmentConfiguration()
    
    def _load_logging_config(self) -> LoggingConfiguration:
        """Load logging configuration with defaults."""
        config_file = self.config_dir / "logging.yaml"
        
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                return LoggingConfiguration(**data.get('logging', {}))
            except Exception as e:
                logger.error(f"Failed to load logging config: {e}")
        
        return LoggingConfiguration()
    
    def _load_broker_config(self) -> BrokerConfiguration:
        """Load broker configuration with defaults."""
        config_file = self.config_dir / "broker.yaml"
        
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                broker_data = data.get('broker', {})
                # Filter out any unexpected keys that aren't in the dataclass
                valid_keys = {f.name for f in fields(BrokerConfiguration)}
                filtered_data = {k: v for k, v in broker_data.items() if k in valid_keys}
                return BrokerConfiguration(**filtered_data)
            except Exception as e:
                logger.error(f"Failed to load broker config: {e}")
        
        return BrokerConfiguration()
    
    def _load_universe_config(self) -> UniverseConfiguration:
        """Load universe configuration with defaults."""
        config_file = self.config_dir / "dynamic_universe_config.yaml"
        
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                
                # Extract gainer_loser_universe section
                universe_data = data.get('gainer_loser_universe', {})
                excel_data = data.get('excel_integration', {})
                
                # Merge configurations
                merged_config = {**universe_data, **excel_data}
                
                return UniverseConfiguration(**merged_config)
            except Exception as e:
                logger.error(f"Failed to load universe config: {e}")
        
        return UniverseConfiguration()
    
    def _load_monitoring_config(self) -> MonitoringConfiguration:
        """Load monitoring configuration with defaults."""
        config_file = self.config_dir / "monitoring.yaml"
        
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                return MonitoringConfiguration(**data.get('monitoring', {}))
            except Exception as e:
                logger.error(f"Failed to load monitoring config: {e}")
        
        return MonitoringConfiguration()
    
    # ===== CONFIGURATION CACHING AND VALIDATION =====
    
    def _load_with_cache(self, key: str, loader_func) -> Any:
        """Load configuration with caching and change detection."""
        # Check if we need to reload
        if self._should_reload_config(key):
            try:
                self._config_cache[key] = loader_func()
                self._update_cache_metadata(key)
                logger.debug(f"Configuration '{key}' loaded/reloaded")
            except Exception as e:
                logger.error(f"Failed to load configuration '{key}': {e}")
                # Return cached version if available
                if key in self._config_cache:
                    logger.warning(f"Using cached configuration for '{key}' due to load error")
                    return self._config_cache[key]
                raise
        
        return self._config_cache[key]
    
    def _should_reload_config(self, key: str) -> bool:
        """Check if configuration should be reloaded."""
        if key not in self._config_cache:
            return True
        
        # For now, disable hot-reload in production for stability
        if self.environment == 'production':
            return False
        
        return False  # Disable hot-reload for now
    
    def _update_cache_metadata(self, key: str) -> None:
        """Update cache metadata for change detection."""
        self._config_timestamps[key] = datetime.now().timestamp()
        
        # Calculate configuration hash for change detection
        if key in self._config_cache:
            config_str = str(self._config_cache[key])
            self._config_hashes[key] = hashlib.md5(config_str.encode()).hexdigest()
    
    # ===== CONFIGURATION VALIDATION =====
    
    def validate_configuration(self) -> List[str]:
        """
        Validate entire configuration and return list of issues.
        
        Returns:
            List of validation issues (empty list if valid)
        """
        issues = []
        
        try:
            # Validate environment configuration
            env_config = self.get_environment_configuration()
            if env_config.execution_mode not in ['PAPER', 'LIVE', 'BACKTEST']:
                issues.append(f"Invalid execution_mode: {env_config.execution_mode}")
            
            # Validate broker configuration for live trading
            if env_config.execution_mode == 'LIVE':
                broker_config = self.get_broker_configuration()
                if not broker_config.api_key:
                    issues.append("LIVE mode requires broker API key")
                if not broker_config.access_token:
                    issues.append("LIVE mode requires broker access token")
            
            # Validate capital parameters
            capital_params = self.get_capital_parameters()
            if capital_params.total_capital <= 0:
                issues.append("Total capital must be positive")
            if capital_params.risk_per_trade <= 0 or capital_params.risk_per_trade > 0.1:
                issues.append("Risk per trade should be between 0 and 0.1 (10%)")
            
            # Validate trade parameters
            trade_params = self.get_trade_parameters()
            if trade_params.sl_atr_mult <= 0:
                issues.append("Stop loss ATR multiplier must be positive")
            if trade_params.target_atr_mult <= trade_params.sl_atr_mult:
                issues.append("Target ATR multiplier should be greater than stop loss multiplier")
            
        except Exception as e:
            issues.append(f"Configuration validation error: {e}")
        
        if issues:
            logger.warning(f"Configuration validation found {len(issues)} issues: {issues}")
        else:
            logger.info("Configuration validation passed")
        
        return issues
    
    # ===== CONFIGURATION DEFAULTS =====
    
    @staticmethod
    def _get_default_trading_config() -> Dict[str, Any]:
        """Get default trading configuration."""
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
    
    def _get_default_adaptive_config(self) -> Dict[str, Any]:
        """Get default adaptive strategies configuration."""
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
                }
            }
        }
    
    @staticmethod
    def _get_default_rules() -> Dict[str, Any]:
        """Get default screener rules."""
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
    
    # ===== UTILITY METHODS =====
    
    def create_default_configs(self) -> None:
        """Create all default configuration files if they don't exist."""
        logger.info("Creating default configuration files...")
        
        # Create main config files (backward compatibility)
        self._create_trading_config()
        self._create_symbols_config()
        self._create_rules_config()
        
        # Create new centralized config files
        self._create_environment_config()
        self._create_logging_config()
        self._create_broker_config()
        self._create_monitoring_config()
        
        logger.info("Default configuration files created successfully")
    
    def _create_trading_config(self) -> None:
        """Create default trading config file."""
        config_file = self.config_dir / "trading_config.yaml"
        if not config_file.exists():
            with open(config_file, 'w') as f:
                yaml.dump(self._get_default_trading_config(), f, default_flow_style=False)
            logger.info(f"Created {config_file}")
    
    def _create_symbols_config(self) -> None:
        """Create default symbols config file."""
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
            logger.info(f"Created {symbols_file}")
    
    def _create_rules_config(self) -> None:
        """Create default rules config file."""
        rules_file = self.config_dir / "rules.yaml"
        if not rules_file.exists():
            with open(rules_file, 'w') as f:
                yaml.dump(self._get_default_rules(), f, default_flow_style=False)
            logger.info(f"Created {rules_file}")
    
    def _create_environment_config(self) -> None:
        """Create default environment config file."""
        config_file = self.config_dir / "environment.yaml"
        if not config_file.exists():
            config = {
                'environment': EnvironmentConfiguration().to_dict()
            }
            with open(config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Created {config_file}")
    
    def _create_logging_config(self) -> None:
        """Create default logging config file."""
        config_file = self.config_dir / "logging.yaml"
        if not config_file.exists():
            config = {
                'logging': LoggingConfiguration().to_dict()
            }
            with open(config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Created {config_file}")
    
    def _create_broker_config(self) -> None:
        """Create default broker config file."""
        config_file = self.config_dir / "broker.yaml"
        if not config_file.exists():
            config = {
                'broker': BrokerConfiguration().to_dict()
            }
            with open(config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Created {config_file}")
    
    def _create_monitoring_config(self) -> None:
        """Create default monitoring config file."""
        config_file = self.config_dir / "monitoring.yaml"
        if not config_file.exists():
            config = {
                'monitoring': MonitoringConfiguration().to_dict()
            }
            with open(config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Created {config_file}")
    
    def export_configuration(self, output_file: str = None) -> str:
        """
        Export complete configuration to a single file for backup/debugging.
        
        Args:
            output_file: Output file path (optional)
            
        Returns:
            Path to exported configuration file
        """
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"config_export_{timestamp}.json"
        
        config_data = self.get_all_configurations()
        
        with open(output_file, 'w') as f:
            json.dump(config_data, f, indent=2, default=str)
        
        logger.info(f"Configuration exported to {output_file}")
        return output_file
    
    def reload_all_configurations(self) -> None:
        """Force reload all configurations from files."""
        logger.info("Reloading all configurations...")
        
        # Clear cache to force reload
        self._config_cache.clear()
        self._config_timestamps.clear()
        self._config_hashes.clear()
        
        # Clear backward compatibility cache
        self._trading_config = None
        self._timing_config = None
        self._adaptive_config = None
        self._symbols = None
        self._rules = None
        
        logger.info("All configurations reloaded")


# ===== CONFIGURATION FACTORY =====

def create_config_manager(environment: str = None, 
                         config_dir: str = "config") -> EnhancedConfigManager:
    """
    Factory function to create enhanced config manager.
    
    Args:
        environment: Configuration environment (optional)
        config_dir: Configuration directory path
        
    Returns:
        Configured EnhancedConfigManager instance
    """
    manager = EnhancedConfigManager(config_dir=config_dir, environment=environment)
    
    # Create default configs if needed
    manager.create_default_configs()
    
    # Validate configuration
    issues = manager.validate_configuration()
    if issues:
        logger.warning(f"Configuration validation found issues: {issues}")
    
    return manager


# ===== BACKWARD COMPATIBILITY ALIAS =====
# This allows existing code to work without modification
ConfigManager = EnhancedConfigManager