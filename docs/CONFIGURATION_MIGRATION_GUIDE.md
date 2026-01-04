"""
CONFIGURATION CENTRALIZATION - MIGRATION GUIDE
==============================================

This document provides step-by-step instructions for migrating from the scattered
configuration approach to the new centralized configuration system.

## Overview of Changes

### Before: Scattered Configurations
- Hardcoded constants in multiple files
- Environment variables mixed with code
- Configuration duplicated across modules
- No single source of truth

### After: Centralized Configuration
- Single configuration manager for all settings
- Environment-specific configuration files
- Type-safe configuration with validation
- Hot-reload support for development

## Step-by-Step Migration Process

### Step 1: Update Configuration Manager Usage

**OLD CODE:**
```python
from config.config_manager import ConfigManager

config_mgr = ConfigManager()
capital_params = config_mgr.get_capital_parameters()
```

**NEW CODE:**
```python
# Option 1: Use enhanced manager directly
from config.enhanced_config_manager import EnhancedConfigManager

config_mgr = EnhancedConfigManager()
capital_params = config_mgr.get_capital_parameters()  # Backward compatible

# Option 2: Use factory function (recommended)
from config.enhanced_config_manager import create_config_manager

config_mgr = create_config_manager()
capital_params = config_mgr.get_capital_parameters()
```

### Step 2: Replace Hardcoded Constants

**Identify and Replace Scattered Constants:**

#### 2a. Trading Parameters (DONE)
```python
# OLD: Hardcoded in execution files
ATR_PERIOD = 14
SL_ATR_MULT = 1.5
TARGET_ATR_MULT = 2.0

# NEW: From centralized config
trade_params = config_mgr.get_trade_parameters()
atr_period = trade_params.atr_period
sl_mult = trade_params.sl_atr_mult
```

#### 2b. Capital Parameters (DONE) 
```python
# OLD: Hardcoded in execution files
CAPITAL = 5000
RISK_PER_TRADE = 0.005
MAX_OPEN_POSITIONS = 5

# NEW: From centralized config
capital_params = config_mgr.get_capital_parameters()
capital = capital_params.total_capital
risk = capital_params.risk_per_trade
```

#### 2c. Broker Configuration (NEW)
```python
# OLD: Hardcoded API keys and settings
API_KEY = "hardcoded_key"
ORDER_TYPE = "MARKET"
PRODUCT_TYPE = "MIS"

# NEW: From centralized config
broker_config = config_mgr.get_broker_configuration()
api_key = broker_config.api_key  # From environment variable
order_type = broker_config.order_type
```

#### 2d. Logging Configuration (NEW)
```python
# OLD: Hardcoded logging setup in each file
logging.basicConfig(level=logging.INFO, format="%(asctime)s...")

# NEW: From centralized config
log_config = config_mgr.get_logging_configuration()
logging.basicConfig(
    level=getattr(logging, log_config.level),
    format=log_config.format
)
```

### Step 3: Update Environment Variable Handling

**OLD: Manual environment variable loading**
```python
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('KITE_API_KEY')
```

**NEW: Automatic environment variable integration**
```python
# Environment variables automatically loaded and merged
broker_config = config_mgr.get_broker_configuration()
api_key = broker_config.api_key  # Auto-loaded from KITE_API_KEY
```

### Step 4: Update Module-Specific Configurations

#### 4a. Universe Manager Configuration
```python
# OLD: Mixed hardcoded and partial config
class DynamicUniverseManager:
    def __init__(self):
        self.max_gainers = 10  # Hardcoded
        self.min_gap = 2.0     # Hardcoded
        
# NEW: Fully centralized configuration
class DynamicUniverseManager:
    def __init__(self, config_mgr):
        universe_config = config_mgr.get_universe_configuration()
        self.max_gainers = universe_config.max_gainers
        self.min_gap = universe_config.min_gap_percentage
```

#### 4b. Strategy Configuration
```python
# OLD: Default values scattered in strategy files
class AdaptiveStrategyManager:
    def __init__(self):
        self.gap_weight = 0.25      # Hardcoded default
        self.momentum_weight = 0.25  # Hardcoded default
        
# NEW: Centralized strategy configuration
class AdaptiveStrategyManager:
    def __init__(self, config_mgr):
        adaptive_config = config_mgr.load_adaptive_strategies_config()
        manager_config = adaptive_config.get('adaptive_strategies', {}).get('manager', {})
        weights = manager_config.get('strategy_weights', {})
        self.gap_weight = weights.get('gap_weight', 0.25)
```

### Step 5: Update Main Application Entry Points

#### 5a. Update main.py
```python
# OLD: Manual configuration loading
def main():
    config_mgr = ConfigManager()
    
# NEW: Enhanced configuration with validation
def main():
    config_mgr = create_config_manager()
    
    # Validate configuration before starting
    issues = config_mgr.validate_configuration()
    if issues:
        print(f"Configuration issues found: {issues}")
        return 1
```

#### 5b. Update Execution Modes
```python
# OLD: Mixed configuration sources
class PaperTradingMode:
    def __init__(self, capital_params, trade_params):
        self.broker_config = {...}  # Hardcoded
        
# NEW: Centralized configuration
class PaperTradingMode:  
    def __init__(self, config_mgr):
        self.capital_params = config_mgr.get_capital_parameters()
        self.trade_params = config_mgr.get_trade_parameters()
        self.broker_config = config_mgr.get_broker_configuration()
```

### Step 6: Configuration File Structure

**NEW CONFIGURATION FILES:**
```
config/
├── enhanced_config_manager.py    # Enhanced config manager (NEW)
├── environment.yaml              # Environment settings (NEW) 
├── logging.yaml                 # Logging configuration (NEW)
├── broker.yaml                  # Broker settings (NEW)
├── monitoring.yaml              # Monitoring config (NEW)
├── trading_config.yaml          # Trading parameters (EXISTING)
├── adaptive_strategies_config.yaml # Strategy config (EXISTING)
├── timing_config.yaml           # Timing config (EXISTING)  
├── dynamic_universe_config.yaml # Universe config (EXISTING)
├── symbols.yaml                 # Symbol list (EXISTING)
└── rules.yaml                   # Screening rules (EXISTING)
```

### Step 7: Environment Variable Migration

**UPDATE .env FILE:**
```bash
# OLD: Mixed configuration in .env
EXECUTION_MODE=PAPER
KITE_API_KEY=your_key
TRADING_CAPITAL=5000
LOG_LEVEL=INFO

# NEW: Clean separation (keep only secrets in .env)
# Configuration Environment
CONFIG_ENVIRONMENT=development

# Broker Credentials (secrets only)
KITE_API_KEY=your_key
KITE_ACCESS_TOKEN=your_token
KITE_API_SECRET=your_secret

# Optional Overrides (everything else in YAML files)
EXECUTION_MODE=PAPER
LOG_LEVEL=INFO
```

## Migration Benefits

### 1. **Single Source of Truth**
- All configurations in one place
- No more hunting for hardcoded values
- Consistent configuration across environments

### 2. **Type Safety & Validation**
- Configuration validation at startup
- Type hints for better IDE support
- Runtime error detection

### 3. **Environment Management** 
- Easy switching between dev/test/prod
- Environment-specific overrides
- Secure credential management

### 4. **Maintainability**
- Change configuration without touching code
- Version control for configuration changes
- Easy rollback of configuration changes

### 5. **Development Experience**
- Hot-reload for development (optional)
- Configuration export/import for debugging
- Centralized documentation

## Testing the Migration

### 1. **Configuration Validation Test**
```python
def test_configuration_migration():
    config_mgr = create_config_manager()
    
    # Test all configurations load without errors
    issues = config_mgr.validate_configuration()
    assert len(issues) == 0, f"Configuration issues: {issues}"
    
    # Test backward compatibility
    capital_params = config_mgr.get_capital_parameters()
    assert capital_params.total_capital > 0
    
    trade_params = config_mgr.get_trade_parameters()
    assert trade_params.sl_atr_mult > 0
    
    print("✅ Configuration migration test passed!")
```

### 2. **Environment Override Test**
```python
def test_environment_overrides():
    import os
    
    # Test environment variable override
    os.environ['TRADING_CAPITAL'] = '10000'
    
    config_mgr = create_config_manager()
    capital_params = config_mgr.get_capital_parameters()
    
    assert capital_params.total_capital == 10000
    print("✅ Environment override test passed!")
```

### 3. **Backward Compatibility Test**
```python
def test_backward_compatibility():
    # Test that existing code still works
    from config.enhanced_config_manager import ConfigManager  # Alias
    
    config_mgr = ConfigManager()  # Should work like old ConfigManager
    capital_params = config_mgr.get_capital_parameters()
    
    assert hasattr(capital_params, 'total_capital')
    print("✅ Backward compatibility test passed!")
```

## Rollback Plan

If issues occur during migration:

1. **Keep Old ConfigManager**: The old config_manager.py is preserved
2. **Selective Migration**: Migrate one module at a time
3. **Environment Toggle**: Use environment variable to switch managers
4. **Validation**: Extensive testing before full deployment

## Next Steps After Migration

1. **Remove Hardcoded Values**: Systematically eliminate remaining constants
2. **Add Configuration Monitoring**: Track configuration changes in production
3. **Documentation**: Update all documentation to reflect new configuration system
4. **Training**: Update team on new configuration management approach

## Configuration Best Practices

1. **Keep Secrets Secure**: Never commit API keys to version control
2. **Use Environment Variables**: For environment-specific overrides only
3. **Validate Early**: Run configuration validation at application startup
4. **Document Changes**: Comment configuration changes in YAML files  
5. **Test Thoroughly**: Test configuration in all environments before deployment

This migration approach ensures a smooth transition to centralized configuration
while maintaining backward compatibility and system stability.
"""