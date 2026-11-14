"""
Configuration Management Module

Centralized configuration system using environment variables and YAML files.
Supports validation, type conversion, and environment variable expansion.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field

import yaml
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv


# Load environment variables from .env file
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")


class EnvironmentVariableNotSetError(Exception):
    """Raised when a required environment variable is not set."""
    pass


class ConfigurationError(Exception):
    """Raised when there's a configuration error."""
    pass


def expand_environment_variables(value: str, allow_missing: bool = False) -> str:
    """
    Expand environment variables in a string.
    
    Supports ${VAR_NAME} syntax.
    
    Args:
        value: String potentially containing environment variable references
        allow_missing: If True, leave variable references as-is when not set
        
    Returns:
        String with environment variables expanded
        
    Raises:
        EnvironmentVariableNotSetError: If a referenced variable is not set and allow_missing is False
    """
    pattern = r'\$\{([^}]+)\}'
    
    def replace_var(match: re.Match[str]) -> str:
        var_name = match.group(1)
        var_value = os.environ.get(var_name)
        if var_value is None:
            if allow_missing:
                return match.group(0)  # Return the original reference
            raise EnvironmentVariableNotSetError(
                f"Environment variable '{var_name}' is not set"
            )
        return var_value
    
    return re.sub(pattern, replace_var, value)


def expand_dict_environment_variables(data: Dict[str, Any], allow_missing: bool = False) -> Dict[str, Any]:
    """
    Recursively expand environment variables in a dictionary.
    
    Args:
        data: Dictionary potentially containing environment variable references
        allow_missing: If True, leave variable references as-is when not set
        
    Returns:
        Dictionary with all environment variables expanded
    """
    expanded = {}
    for key, value in data.items():
        if isinstance(value, str):
            expanded[key] = expand_environment_variables(value, allow_missing=allow_missing)
        elif isinstance(value, dict):
            expanded[key] = expand_dict_environment_variables(value, allow_missing=allow_missing)
        elif isinstance(value, list):
            expanded[key] = [
                expand_environment_variables(item, allow_missing=allow_missing) if isinstance(item, str) else item
                for item in value
            ]
        else:
            expanded[key] = value
    return expanded


class DatabaseConnectionConfig(BaseModel):
    """Database connection configuration."""
    host: str
    port: int
    name: str
    user: str
    password: str
    ssl_enabled: bool = False
    ssl_mode: Optional[str] = None


@dataclass
class Config:
    """
    Main configuration class that loads and manages all configuration.
    
    Supports loading from YAML files and environment variables.
    """
    
    # Configuration directories
    config_dir: Path = Path(__file__).parent.parent.parent / "config"
    
    # Individual configuration objects
    broker_config: Optional[Dict[str, Any]] = None
    risk_config: Optional[Dict[str, Any]] = None
    strategy_config: Optional[Dict[str, Any]] = None
    database_config: Optional[Dict[str, Any]] = None
    
    # Loaded flag
    _loaded: bool = False
    
    def __post_init__(self):
        """Initialize configuration after creation."""
        if not self._loaded:
            self.load_all()
    
    def load_yaml(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Load a YAML configuration file.
        
        Args:
            file_path: Path to the YAML file
            
        Returns:
            Dictionary containing the configuration
            
        Raises:
            ConfigurationError: If file cannot be loaded or parsed
        """
        path = Path(file_path)
        if not path.exists():
            raise ConfigurationError(f"Configuration file not found: {path}")
        
        try:
            with open(path, 'r') as f:
                config = yaml.safe_load(f)
                if config is None:
                    return {}
                return config
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Error parsing YAML file {path}: {e}")
        except Exception as e:
            raise ConfigurationError(f"Error loading file {path}: {e}")
    
    def load_all(self) -> None:
        """Load all configuration files."""
        try:
            # Load broker configuration
            self.broker_config = self.load_yaml(self.config_dir / "broker_config.yaml")
            self.broker_config = expand_dict_environment_variables(self.broker_config, allow_missing=True)
            
            # Load risk configuration
            self.risk_config = self.load_yaml(self.config_dir / "risk_parameters.yaml")
            self.risk_config = expand_dict_environment_variables(self.risk_config, allow_missing=True)
            
            # Load strategy configuration
            self.strategy_config = self.load_yaml(self.config_dir / "strategy_config.yaml")
            self.strategy_config = expand_dict_environment_variables(self.strategy_config, allow_missing=True)
            
            # Load database configuration
            self.database_config = self.load_yaml(self.config_dir / "database_config.yaml")
            self.database_config = expand_dict_environment_variables(self.database_config, allow_missing=True)
            
            self._loaded = True
            
        except Exception as e:
            raise ConfigurationError(f"Error loading configuration: {e}")
    
    def reload(self) -> None:
        """Reload all configuration files."""
        self._loaded = False
        self.load_all()
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            section: Configuration section (broker, risk, strategy, database)
            key: Key within the section
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        config_map = {
            "broker": self.broker_config,
            "risk": self.risk_config,
            "strategy": self.strategy_config,
            "database": self.database_config,
        }
        
        config = config_map.get(section)
        if config is None:
            return default
        
        # Navigate nested keys
        keys = key.split('.')
        value = config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        # Handle environment variable references that weren't expanded
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            return default
        
        return value
    
    def get_database_connection_config(self) -> DatabaseConnectionConfig:
        db_config = self.get("database", "database", {})
        host = db_config.get("host", "localhost")
        port = db_config.get("port", 5432)
        name = db_config.get("name", "cross_broker_trading")
        user = db_config.get("user", "postgres")
        password = db_config.get("password", "")
        ssl_config = db_config.get("ssl", {})
        ssl_enabled = ssl_config.get("enabled", False)
        ssl_mode = ssl_config.get("mode", None)
        if isinstance(host, str) and host.startswith("${"):
            host = "localhost"
        if isinstance(port, str) and port.startswith("${"):
            port = 5432
        if isinstance(name, str) and name.startswith("${"):
            name = "cross_broker_trading"
        if isinstance(user, str) and user.startswith("${"):
            user = "postgres"
        if isinstance(password, str) and password.startswith("${"):
            password = ""
        return DatabaseConnectionConfig(
            host=host,
            port=int(port) if not isinstance(port, int) else port,
            name=name,
            user=user,
            password=password,
            ssl_enabled=ssl_enabled,
            ssl_mode=ssl_mode,
        )
    
    def get_broker_config(self, broker_id: str) -> Dict[str, Any]:
        """
        Get configuration for a specific broker.
        
        Args:
            broker_id: Broker identifier (vantage, justmarkets)
            
        Returns:
            Broker configuration dictionary
        """
        if self.broker_config is None:
            self.load_all()
        
        return self.broker_config.get("brokers", {}).get(broker_id, {})
    
    def get_trading_mode(self) -> str:
        """Get the current trading mode."""
        return self.get("broker", "settings.trading_mode", "DEMO")
    
    def is_live_trading_enabled(self) -> bool:
        """Check if live trading is enabled."""
        mode = self.get_trading_mode()
        enabled = self.get("broker", "settings.live_trading_enabled", False)
        return mode == "LIVE" and enabled
    
    def get_primary_instrument(self) -> str:
        """Get the primary trading instrument."""
        return self.get("broker", "settings.primary_instrument", "XAUUSD")
    
    def get_initial_lot_size(self) -> float:
        """Get the initial lot size."""
        return float(self.get("broker", "settings.lot_sizes.initial", 0.01))


# Pydantic models for type-safe configuration

class BrokerConnectionConfig(BaseModel):
    """Broker connection configuration."""
    server: str
    server_address: str
    login: str
    password: str
    account_type: str


class BrokerConfig(BaseModel):
    """Complete broker configuration."""
    name: str
    broker_id: str
    demo: BrokerConnectionConfig
    live: Optional[BrokerConnectionConfig] = None
    mt5_path: Optional[str] = None
    instrument_mapping: Dict[str, str] = Field(default_factory=dict)
    contract_specs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    execution: Dict[str, Any] = Field(default_factory=dict)
    market_data: Dict[str, Any] = Field(default_factory=dict)
    ib_rebate: Dict[str, Any] = Field(default_factory=dict)
    risk: Dict[str, Any] = Field(default_factory=dict)


class RiskParameters(BaseModel):
    """Risk management parameters."""
    max_loss_per_cycle_usd: float
    max_daily_loss_usd: float
    max_open_exposure_usd: float
    max_holding_time_hours: float
    min_free_margin_percent: float
    max_spread_points: float
    max_execution_delay_seconds: float
    max_slippage_points: float
    emergency_stop_enabled: bool = True
    manual_kill_switch: bool = False


class StrategyParameters(BaseModel):
    """Strategy-specific parameters."""
    enabled: bool = True
    description: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)
    risk_overrides: Dict[str, Any] = Field(default_factory=dict)
    weights: Dict[str, float] = Field(default_factory=dict)


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """
    Get the global configuration instance.
    
    Returns:
        Global Config instance
    """
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config() -> None:
    """Reset the global configuration instance."""
    global _config
    _config = None


# Convenience functions
def get_broker_config(broker_id: str) -> Dict[str, Any]:
    """Get configuration for a specific broker."""
    return get_config().get_broker_config(broker_id)


def get_trading_mode() -> str:
    """Get the current trading mode."""
    return get_config().get_trading_mode()


def is_live_trading_enabled() -> bool:
    """Check if live trading is enabled."""
    return get_config().is_live_trading_enabled()


def get_primary_instrument() -> str:
    """Get the primary trading instrument."""
    return get_config().get_primary_instrument()


def get_initial_lot_size() -> float:
    """Get the initial lot size."""
    return get_config().get_initial_lot_size()
