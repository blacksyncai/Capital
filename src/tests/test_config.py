"""
Configuration Tests

Tests for the configuration system.
"""

import pytest
from pathlib import Path
import tempfile
import os

from src.core.config import (
    Config,
    get_config,
    reset_config,
    expand_environment_variables,
    expand_dict_environment_variables,
    EnvironmentVariableNotSetError
)


@pytest.fixture
def temp_config_dir():
    """Create a temporary config directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "config"
        config_dir.mkdir()
        
        # Create test config files
        broker_config = """
brokers:
  vantage:
    name: "Vantage Markets"
    demo:
      server: "Vantage-Demo"
      login: 12345
      password: test123
  justmarkets:
    name: "JustMarkets"
    demo:
      server: "JustMarkets-Demo"
      login: 54321
      password: test456
"""
        
        with open(config_dir / "broker_config.yaml", "w") as f:
            f.write(broker_config)
        
        yield config_dir


class TestConfig:
    """Test Config class."""
    
    def test_singleton(self):
        """Test that get_config returns the same instance."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2
    
    def test_reset(self):
        """Test that reset_config creates a new instance."""
        config1 = get_config()
        reset_config()
        config2 = get_config()
        assert config1 is not config2
    
    def test_load_all(self, temp_config_dir, monkeypatch):
        """Test loading all configuration files."""
        # Mock config directory
        monkeypatch.setattr(Config, "config_dir", temp_config_dir)
        
        config = Config()
        assert config.broker_config is not None
        assert "brokers" in config.broker_config
    
    def test_get_broker_config(self, temp_config_dir, monkeypatch):
        """Test getting broker configuration."""
        monkeypatch.setattr(Config, "config_dir", temp_config_dir)
        
        config = Config()
        vantage_config = config.get_broker_config("vantage")
        
        assert vantage_config is not None
        assert vantage_config.get("name") == "Vantage Markets"
        assert vantage_config.get("demo", {}).get("server") == "Vantage-Demo"


class TestEnvironmentVariables:
    """Test environment variable expansion."""
    
    def test_expand_simple(self):
        """Test expanding simple environment variable."""
        os.environ["TEST_VAR"] = "test_value"
        result = expand_environment_variables("Hello ${TEST_VAR}")
        assert result == "Hello test_value"
    
    def test_expand_missing(self):
        """Test expanding missing environment variable."""
        if "NONEXISTENT_VAR" in os.environ:
            del os.environ["NONEXISTENT_VAR"]
        
        with pytest.raises(EnvironmentVariableNotSetError):
            expand_environment_variables("Hello ${NONEXISTENT_VAR}")
    
    def test_expand_dict(self):
        """Test expanding environment variables in dictionary."""
        os.environ["TEST_VAR"] = "test_value"
        
        data = {
            "key1": "value1",
            "key2": "${TEST_VAR}",
            "nested": {
                "key3": "${TEST_VAR}_suffix"
            }
        }
        
        result = expand_dict_environment_variables(data)
        
        assert result["key1"] == "value1"
        assert result["key2"] == "test_value"
        assert result["nested"]["key3"] == "test_value_suffix"


class TestConfigAccessors:
    """Test config accessor methods."""
    
    def test_get_trading_mode(self):
        """Test getting trading mode."""
        config = get_config()
        mode = config.get_trading_mode()
        assert mode in ["DEMO", "SIMULATION", "LIVE"]
    
    def test_is_live_trading_enabled(self):
        """Test checking if live trading is enabled."""
        config = get_config()
        enabled = config.is_live_trading_enabled()
        assert isinstance(enabled, bool)
    
    def test_get_primary_instrument(self):
        """Test getting primary instrument."""
        config = get_config()
        instrument = config.get_primary_instrument()
        assert instrument == "XAUUSD"
    
    def test_get_initial_lot_size(self):
        """Test getting initial lot size."""
        config = get_config()
        lot_size = config.get_initial_lot_size()
        assert isinstance(lot_size, float)
        assert lot_size > 0
