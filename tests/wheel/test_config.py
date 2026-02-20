"""Tests for Wheel Strategy Configuration.

Comprehensive test suite for configuration loading, validation,
and environment variable overrides.
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from src.wheel.config import (
    ConfigurationError,
    WheelStrategyConfig,
    load_config,
)


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create temporary config directory.

    Args:
        tmp_path: pytest tmp_path fixture

    Returns:
        Path to temporary config directory
    """
    config_dir = tmp_path / ".wheel_strategy"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def temp_config_file(temp_config_dir):
    """Create temporary config file.

    Args:
        temp_config_dir: Temporary config directory

    Returns:
        Path to temporary config file
    """
    config_file = temp_config_dir / "config.yaml"
    return config_file


@pytest.fixture
def sample_config_dict():
    """Sample configuration dictionary.

    Returns:
        Dictionary with sample configuration
    """
    return {
        "api": {
            "url": "http://localhost:8000",
            "timeout": 30,
            "use_api_mode": True,
        },
        "defaults": {
            "portfolio_id": "test-portfolio-id",
            "profile": "moderate",
        },
        "cli": {
            "verbose": False,
            "json_output": False,
        },
    }


@pytest.fixture
def clear_env_vars():
    """Clear environment variables before and after test.

    Yields:
        None
    """
    env_vars = [
        "WHEEL_API_URL",
        "WHEEL_API_TIMEOUT",
        "WHEEL_USE_API_MODE",
        "WHEEL_DEFAULT_PORTFOLIO_ID",
        "WHEEL_DEFAULT_PROFILE",
        "WHEEL_MAX_DTE",
        "WHEEL_VERBOSE",
        "WHEEL_JSON_OUTPUT",
    ]

    # Clear before test
    original_values = {}
    for var in env_vars:
        original_values[var] = os.getenv(var)
        if var in os.environ:
            del os.environ[var]

    yield

    # Restore after test
    for var, value in original_values.items():
        if value is not None:
            os.environ[var] = value
        elif var in os.environ:
            del os.environ[var]


# Initialization Tests


def test_default_initialization():
    """Test configuration with default values."""
    config = WheelStrategyConfig()
    assert config.api_url == "http://localhost:8000"
    assert config.api_timeout == 30
    assert config.use_api_mode is True
    assert config.default_portfolio_id is None
    assert config.default_profile == "conservative"
    assert config.max_dte == 14
    assert config.verbose is False
    assert config.json_output is False


def test_custom_initialization():
    """Test configuration with custom values."""
    config = WheelStrategyConfig(
        api_url="http://example.com:8000",
        api_timeout=60,
        use_api_mode=False,
        default_portfolio_id="custom-portfolio-id",
        default_profile="aggressive",
        verbose=True,
        json_output=True,
    )
    assert config.api_url == "http://example.com:8000"
    assert config.api_timeout == 60
    assert config.use_api_mode is False
    assert config.default_portfolio_id == "custom-portfolio-id"
    assert config.default_profile == "aggressive"
    assert config.verbose is True
    assert config.json_output is True


# Validation Tests


def test_validation_invalid_timeout():
    """Test validation fails with invalid timeout."""
    with pytest.raises(ConfigurationError) as exc_info:
        WheelStrategyConfig(api_timeout=0)
    assert "timeout must be positive" in str(exc_info.value)


def test_validation_invalid_profile():
    """Test validation fails with invalid profile."""
    with pytest.raises(ConfigurationError) as exc_info:
        WheelStrategyConfig(default_profile="invalid")
    assert "default_profile must be one of" in str(exc_info.value)


def test_validation_invalid_url():
    """Test validation fails with invalid URL."""
    with pytest.raises(ConfigurationError) as exc_info:
        WheelStrategyConfig(api_url="not-a-url")
    assert "must start with http://" in str(exc_info.value)


# File Loading Tests


def test_load_from_nonexistent_file(temp_config_file, clear_env_vars):
    """Test loading from non-existent file returns defaults."""
    config = WheelStrategyConfig.load_from_file(temp_config_file)
    assert config.api_url == "http://localhost:8000"
    assert config.default_profile == "conservative"


def test_load_from_valid_file(temp_config_file, sample_config_dict, clear_env_vars):
    """Test loading from valid config file."""
    with open(temp_config_file, "w") as f:
        yaml.dump(sample_config_dict, f)

    config = WheelStrategyConfig.load_from_file(temp_config_file)
    assert config.api_url == "http://localhost:8000"
    assert config.api_timeout == 30
    assert config.default_portfolio_id == "test-portfolio-id"
    assert config.default_profile == "moderate"


def test_load_from_file_with_invalid_yaml(temp_config_file, clear_env_vars):
    """Test loading from file with invalid YAML."""
    with open(temp_config_file, "w") as f:
        f.write("invalid: yaml: content:\n  - broken")

    with pytest.raises(ConfigurationError) as exc_info:
        WheelStrategyConfig.load_from_file(temp_config_file)
    assert "Invalid YAML" in str(exc_info.value)


def test_load_from_file_with_invalid_values(temp_config_file, clear_env_vars):
    """Test loading from file with invalid configuration values."""
    invalid_config = {
        "api": {"timeout": -5},  # Invalid timeout
    }
    with open(temp_config_file, "w") as f:
        yaml.dump(invalid_config, f)

    with pytest.raises(ConfigurationError) as exc_info:
        WheelStrategyConfig.load_from_file(temp_config_file)
    assert "Invalid configuration" in str(exc_info.value)


# Environment Variable Tests


def test_env_var_api_url(clear_env_vars):
    """Test API URL from environment variable."""
    os.environ["WHEEL_API_URL"] = "http://custom.com:8000"

    config = WheelStrategyConfig.merge_with_defaults({})
    assert config.api_url == "http://custom.com:8000"


def test_env_var_api_timeout(clear_env_vars):
    """Test API timeout from environment variable."""
    os.environ["WHEEL_API_TIMEOUT"] = "60"

    config = WheelStrategyConfig.merge_with_defaults({})
    assert config.api_timeout == 60


def test_env_var_default_portfolio_id(clear_env_vars):
    """Test default portfolio ID from environment variable."""
    os.environ["WHEEL_DEFAULT_PORTFOLIO_ID"] = "env-portfolio-id"

    config = WheelStrategyConfig.merge_with_defaults({})
    assert config.default_portfolio_id == "env-portfolio-id"


def test_env_var_default_profile(clear_env_vars):
    """Test default profile from environment variable."""
    os.environ["WHEEL_DEFAULT_PROFILE"] = "aggressive"

    config = WheelStrategyConfig.merge_with_defaults({})
    assert config.default_profile == "aggressive"


def test_env_var_verbose(clear_env_vars):
    """Test verbose flag from environment variable."""
    os.environ["WHEEL_VERBOSE"] = "1"

    config = WheelStrategyConfig.merge_with_defaults({})
    assert config.verbose is True


def test_env_var_json_output(clear_env_vars):
    """Test JSON output flag from environment variable."""
    os.environ["WHEEL_JSON_OUTPUT"] = "true"

    config = WheelStrategyConfig.merge_with_defaults({})
    assert config.json_output is True


def test_env_var_override_file(temp_config_file, sample_config_dict, clear_env_vars):
    """Test environment variables override file config."""
    with open(temp_config_file, "w") as f:
        yaml.dump(sample_config_dict, f)

    os.environ["WHEEL_API_URL"] = "http://override.com:8000"
    os.environ["WHEEL_DEFAULT_PROFILE"] = "aggressive"

    config = WheelStrategyConfig.load_from_file(temp_config_file)
    assert config.api_url == "http://override.com:8000"
    assert config.default_profile == "aggressive"
    # File values should still be used for non-overridden fields
    assert config.default_portfolio_id == "test-portfolio-id"


# Merge with Defaults Tests


def test_merge_empty_dict(clear_env_vars):
    """Test merging empty dictionary uses defaults."""
    config = WheelStrategyConfig.merge_with_defaults({})
    assert config.api_url == "http://localhost:8000"
    assert config.default_profile == "conservative"


def test_merge_partial_config(clear_env_vars):
    """Test merging partial configuration."""
    partial_config = {
        "api": {"url": "http://partial.com:8000"},
        "defaults": {"profile": "moderate"},
    }

    config = WheelStrategyConfig.merge_with_defaults(partial_config)
    assert config.api_url == "http://partial.com:8000"
    assert config.default_profile == "moderate"
    assert config.api_timeout == 30  # Default value


def test_merge_nested_config(clear_env_vars):
    """Test merging nested configuration structure."""
    nested_config = {
        "api": {
            "url": "http://nested.com:8000",
            "timeout": 45,
            "use_api_mode": False,
        },
        "defaults": {
            "portfolio_id": "nested-portfolio",
            "profile": "aggressive",
        },
        "cli": {
            "verbose": True,
            "json_output": True,
        },
    }

    config = WheelStrategyConfig.merge_with_defaults(nested_config)
    assert config.api_url == "http://nested.com:8000"
    assert config.api_timeout == 45
    assert config.use_api_mode is False
    assert config.default_portfolio_id == "nested-portfolio"
    assert config.default_profile == "aggressive"
    assert config.verbose is True
    assert config.json_output is True


# Save Tests


def test_save_to_file(temp_config_file):
    """Test saving configuration to file."""
    config = WheelStrategyConfig(
        api_url="http://saved.com:8000",
        default_profile="moderate",
        verbose=True,
    )

    config.save_to_file(temp_config_file)

    # Load and verify
    with open(temp_config_file) as f:
        saved_data = yaml.safe_load(f)

    assert saved_data["api"]["url"] == "http://saved.com:8000"
    assert saved_data["defaults"]["profile"] == "moderate"
    assert saved_data["cli"]["verbose"] is True


def test_save_creates_directory(tmp_path):
    """Test saving creates directory if it doesn't exist."""
    config_file = tmp_path / "new_dir" / "config.yaml"

    config = WheelStrategyConfig()
    config.save_to_file(config_file)

    assert config_file.exists()
    assert config_file.parent.exists()


def test_save_to_default_path(monkeypatch, tmp_path):
    """Test saving to default path."""
    # Mock home directory
    tmp_path / ".wheel_strategy"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    config = WheelStrategyConfig()
    config.save_to_file()

    default_path = config.get_default_config_path()
    assert default_path.exists()


# Utility Tests


def test_to_dict():
    """Test converting configuration to dictionary."""
    config = WheelStrategyConfig(
        api_url="http://test.com:8000",
        default_profile="moderate",
    )

    config_dict = config.to_dict()
    assert config_dict["api"]["url"] == "http://test.com:8000"
    assert config_dict["defaults"]["profile"] == "moderate"


def test_repr():
    """Test string representation."""
    config = WheelStrategyConfig(api_url="http://test.com:8000")

    repr_str = repr(config)
    assert "WheelStrategyConfig" in repr_str
    assert "http://test.com:8000" in repr_str


def test_get_default_config_path():
    """Test getting default config path."""
    path = WheelStrategyConfig.get_default_config_path()
    assert path.name == "config.yaml"
    assert path.parent.name == ".wheel_strategy"


# max_dte Tests


def test_max_dte_default():
    """Test max_dte defaults to 14."""
    config = WheelStrategyConfig()
    assert config.max_dte == 14


def test_max_dte_custom():
    """Test max_dte with custom value."""
    config = WheelStrategyConfig(max_dte=30)
    assert config.max_dte == 30


def test_max_dte_validation_too_low():
    """Test max_dte validation rejects values below 1."""
    with pytest.raises(ConfigurationError) as exc_info:
        WheelStrategyConfig(max_dte=0)
    assert "max_dte must be between 1 and 90" in str(exc_info.value)


def test_max_dte_validation_too_high():
    """Test max_dte validation rejects values above 90."""
    with pytest.raises(ConfigurationError) as exc_info:
        WheelStrategyConfig(max_dte=91)
    assert "max_dte must be between 1 and 90" in str(exc_info.value)


def test_max_dte_from_env_var(clear_env_vars):
    """Test max_dte from environment variable."""
    os.environ["WHEEL_MAX_DTE"] = "21"

    config = WheelStrategyConfig.merge_with_defaults({})
    assert config.max_dte == 21


def test_max_dte_from_config_file(temp_config_file, clear_env_vars):
    """Test max_dte from config file."""
    config_dict = {
        "defaults": {
            "profile": "conservative",
            "max_dte": 28,
        },
    }
    with open(temp_config_file, "w") as f:
        yaml.dump(config_dict, f)

    config = WheelStrategyConfig.load_from_file(temp_config_file)
    assert config.max_dte == 28


def test_max_dte_in_to_dict():
    """Test max_dte appears in to_dict output."""
    config = WheelStrategyConfig(max_dte=21)
    config_dict = config.to_dict()
    assert config_dict["defaults"]["max_dte"] == 21


def test_max_dte_in_save_and_load(temp_config_file, clear_env_vars):
    """Test max_dte round-trips through save and load."""
    config = WheelStrategyConfig(max_dte=30)
    config.save_to_file(temp_config_file)

    loaded = WheelStrategyConfig.load_from_file(temp_config_file)
    assert loaded.max_dte == 30


# Convenience Function Tests


def test_load_config_convenience(temp_config_file, sample_config_dict, clear_env_vars):
    """Test load_config convenience function."""
    with open(temp_config_file, "w") as f:
        yaml.dump(sample_config_dict, f)

    config = load_config(temp_config_file)
    assert isinstance(config, WheelStrategyConfig)
    assert config.api_url == "http://localhost:8000"


def test_load_config_default_path(clear_env_vars):
    """Test load_config without path uses default."""
    config = load_config()
    assert isinstance(config, WheelStrategyConfig)


# Edge Cases


def test_empty_config_file(temp_config_file, clear_env_vars):
    """Test loading empty config file."""
    with open(temp_config_file, "w") as f:
        f.write("")

    config = WheelStrategyConfig.load_from_file(temp_config_file)
    assert config.api_url == "http://localhost:8000"  # Default


def test_config_with_extra_fields(temp_config_file, clear_env_vars):
    """Test loading config with extra unknown fields."""
    config_with_extra = {
        "api": {"url": "http://localhost:8000"},
        "unknown_section": {"unknown_field": "value"},
    }
    with open(temp_config_file, "w") as f:
        yaml.dump(config_with_extra, f)

    # Should not fail, extra fields are ignored
    config = WheelStrategyConfig.load_from_file(temp_config_file)
    assert config.api_url == "http://localhost:8000"


def test_config_with_none_values(clear_env_vars):
    """Test configuration with explicit None values."""
    config_dict = {
        "api": {"url": "http://localhost:8000"},
        "defaults": {
            "portfolio_id": None,  # Explicit None
            "profile": "conservative",
        },
    }

    config = WheelStrategyConfig.merge_with_defaults(config_dict)
    assert config.default_portfolio_id is None


def test_case_sensitive_profile():
    """Test profile is case-sensitive (lowercase required)."""
    # Profile must be lowercase
    with pytest.raises(ConfigurationError) as exc_info:
        WheelStrategyConfig(default_profile="MODERATE")
    assert "default_profile must be one of" in str(exc_info.value)


def test_url_with_trailing_slash():
    """Test URL with trailing slash."""
    config = WheelStrategyConfig(api_url="http://localhost:8000/")
    # The API client strips trailing slashes
    assert config.api_url == "http://localhost:8000/"


def test_config_roundtrip(temp_config_file):
    """Test saving and loading configuration produces same values."""
    original = WheelStrategyConfig(
        api_url="http://roundtrip.com:8000",
        api_timeout=45,
        default_portfolio_id="roundtrip-portfolio",
        default_profile="aggressive",
        verbose=True,
        json_output=True,
    )

    original.save_to_file(temp_config_file)
    loaded = WheelStrategyConfig.load_from_file(temp_config_file)

    assert loaded.api_url == original.api_url
    assert loaded.api_timeout == original.api_timeout
    assert loaded.default_portfolio_id == original.default_portfolio_id
    assert loaded.default_profile == original.default_profile
    assert loaded.verbose == original.verbose
    assert loaded.json_output == original.json_output
