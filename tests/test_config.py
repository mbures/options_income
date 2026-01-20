"""Unit tests for configuration module."""

import os

import pytest

from src.config import FinnhubConfig


class TestFinnhubConfig:
    """Test suite for FinnhubConfig class."""

    def test_config_initialization_valid(self):
        """Test successful configuration initialization."""
        config = FinnhubConfig(api_key="test_key_12345")

        assert config.api_key == "test_key_12345"
        assert config.base_url == "https://finnhub.io/api/v1"
        assert config.timeout == 10
        assert config.max_retries == 3
        assert config.retry_delay == 1.0

    def test_config_initialization_custom_values(self):
        """Test configuration with custom values."""
        config = FinnhubConfig(
            api_key="custom_key",
            base_url="https://custom.api.com",
            timeout=20,
            max_retries=5,
            retry_delay=2.0,
        )

        assert config.api_key == "custom_key"
        assert config.base_url == "https://custom.api.com"
        assert config.timeout == 20
        assert config.max_retries == 5
        assert config.retry_delay == 2.0

    def test_config_empty_api_key(self):
        """Test that empty API key raises ValueError."""
        with pytest.raises(ValueError, match="API key cannot be empty"):
            FinnhubConfig(api_key="")

    def test_config_invalid_timeout(self):
        """Test that invalid timeout raises ValueError."""
        with pytest.raises(ValueError, match="Timeout must be positive"):
            FinnhubConfig(api_key="test_key", timeout=0)

        with pytest.raises(ValueError, match="Timeout must be positive"):
            FinnhubConfig(api_key="test_key", timeout=-5)

    def test_config_invalid_max_retries(self):
        """Test that invalid max_retries raises ValueError."""
        with pytest.raises(ValueError, match="Max retries cannot be negative"):
            FinnhubConfig(api_key="test_key", max_retries=-1)

    def test_config_invalid_retry_delay(self):
        """Test that invalid retry_delay raises ValueError."""
        with pytest.raises(ValueError, match="Retry delay must be positive"):
            FinnhubConfig(api_key="test_key", retry_delay=0)

        with pytest.raises(ValueError, match="Retry delay must be positive"):
            FinnhubConfig(api_key="test_key", retry_delay=-1.0)

    def test_config_from_env_success(self, monkeypatch):
        """Test loading configuration from environment variable."""
        monkeypatch.setenv("FINNHUB_API_KEY", "env_test_key")

        config = FinnhubConfig.from_env()

        assert config.api_key == "env_test_key"
        assert config.base_url == "https://finnhub.io/api/v1"

    def test_config_from_env_custom_var_name(self, monkeypatch):
        """Test loading from custom environment variable name."""
        monkeypatch.setenv("CUSTOM_API_KEY", "custom_env_key")

        config = FinnhubConfig.from_env(api_key_var="CUSTOM_API_KEY")

        assert config.api_key == "custom_env_key"

    def test_config_from_env_missing_variable(self):
        """Test that missing environment variable raises ValueError."""
        # Ensure the variable is not set
        if "FINNHUB_API_KEY" in os.environ:
            del os.environ["FINNHUB_API_KEY"]

        with pytest.raises(ValueError, match="FINNHUB_API_KEY environment variable not set"):
            FinnhubConfig.from_env()

    def test_config_from_env_error_message(self):
        """Test that error message includes helpful information."""
        if "FINNHUB_API_KEY" in os.environ:
            del os.environ["FINNHUB_API_KEY"]

        with pytest.raises(ValueError) as exc_info:
            FinnhubConfig.from_env()

        error_message = str(exc_info.value)
        assert "FINNHUB_API_KEY" in error_message
        assert "https://finnhub.io/register" in error_message
