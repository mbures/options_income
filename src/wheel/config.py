"""Configuration management for Wheel Strategy CLI.

This module provides configuration loading, validation, and management
for the Wheel Strategy CLI, including API settings, defaults, and
CLI-specific options.
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Exception raised for configuration errors."""

    pass


class WheelStrategyConfig:
    """Configuration for Wheel Strategy CLI.

    Manages configuration from files, environment variables, and defaults
    for the Wheel Strategy CLI application.

    Attributes:
        api_url: API server URL
        api_timeout: API request timeout in seconds
        use_api_mode: Whether to use API mode (True) or direct mode (False)
        default_portfolio_id: Default portfolio identifier
        default_profile: Default strike selection profile
        max_dte: Maximum days to expiration for recommendation search window
        verbose: Enable verbose logging
        json_output: Output in JSON format
    """

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        api_timeout: int = 30,
        use_api_mode: bool = True,
        default_portfolio_id: Optional[str] = None,
        default_profile: str = "conservative",
        max_dte: int = 14,
        verbose: bool = False,
        json_output: bool = False,
    ):
        """Initialize configuration.

        Args:
            api_url: API server URL
            api_timeout: API request timeout in seconds
            use_api_mode: Whether to use API mode
            default_portfolio_id: Default portfolio identifier
            default_profile: Default strike selection profile
            max_dte: Maximum days to expiration for recommendation search window
            verbose: Enable verbose logging
            json_output: Output in JSON format

        Example:
            >>> config = WheelStrategyConfig(
            ...     api_url="http://localhost:8000",
            ...     default_profile="moderate"
            ... )
        """
        self.api_url = api_url
        self.api_timeout = api_timeout
        self.use_api_mode = use_api_mode
        self.default_portfolio_id = default_portfolio_id
        self.default_profile = default_profile
        self.max_dte = max_dte
        self.verbose = verbose
        self.json_output = json_output

        self._validate()

    def _validate(self):
        """Validate configuration values.

        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Validate API timeout
        if self.api_timeout <= 0:
            raise ConfigurationError("api_timeout must be positive")

        # Validate profile
        valid_profiles = ["conservative", "moderate", "aggressive"]
        if self.default_profile not in valid_profiles:
            raise ConfigurationError(
                f"default_profile must be one of: {', '.join(valid_profiles)}"
            )

        # Validate max_dte
        if self.max_dte < 1 or self.max_dte > 90:
            raise ConfigurationError("max_dte must be between 1 and 90")

        # Validate API URL format
        if not self.api_url.startswith(("http://", "https://")):
            raise ConfigurationError("api_url must start with http:// or https://")

    @classmethod
    def get_default_config_path(cls) -> Path:
        """Get default configuration file path.

        Returns:
            Path to default config file (~/.wheel_strategy/config.yaml)

        Example:
            >>> path = WheelStrategyConfig.get_default_config_path()
            >>> print(path)
            /home/user/.wheel_strategy/config.yaml
        """
        return Path.home() / ".wheel_strategy" / "config.yaml"

    @classmethod
    def load_from_file(cls, path: Optional[Path] = None) -> "WheelStrategyConfig":
        """Load configuration from YAML file.

        Loads configuration from the specified path or the default path.
        If the file doesn't exist, returns default configuration.
        Merges file configuration with environment variable overrides.

        Args:
            path: Optional path to config file (default: ~/.wheel_strategy/config.yaml)

        Returns:
            Configuration instance

        Raises:
            ConfigurationError: If configuration file is invalid

        Example:
            >>> config = WheelStrategyConfig.load_from_file()
            >>> print(f"API URL: {config.api_url}")
        """
        config_path = path or cls.get_default_config_path()

        # Start with defaults
        config_dict: dict[str, Any] = {}

        # Load from file if it exists
        if config_path.exists():
            try:
                with open(config_path) as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        config_dict = file_config
                logger.debug(f"Loaded configuration from {config_path}")
            except yaml.YAMLError as e:
                raise ConfigurationError(
                    f"Invalid YAML in configuration file: {e}"
                ) from e
            except Exception as e:
                raise ConfigurationError(
                    f"Failed to load configuration file: {e}"
                ) from e
        else:
            logger.debug(f"Configuration file not found at {config_path}, using defaults")

        # Merge with defaults and environment variables
        return cls.merge_with_defaults(config_dict)

    @classmethod
    def merge_with_defaults(cls, config_dict: dict[str, Any]) -> "WheelStrategyConfig":
        """Merge configuration dictionary with defaults and environment variables.

        Precedence order (highest to lowest):
        1. Environment variables
        2. Config file values
        3. Default values

        Args:
            config_dict: Configuration dictionary from file

        Returns:
            Configuration instance

        Raises:
            ConfigurationError: If configuration is invalid

        Example:
            >>> config = WheelStrategyConfig.merge_with_defaults({
            ...     "api": {"url": "http://example.com:8000"}
            ... })
        """
        # Extract nested config structure (support both flat and nested)
        api_config = config_dict.get("api", {})
        defaults_config = config_dict.get("defaults", {})
        cli_config = config_dict.get("cli", {})

        # Build configuration with precedence: env vars > file > defaults
        api_url = os.getenv(
            "WHEEL_API_URL",
            api_config.get("url", "http://localhost:8000"),
        )
        api_timeout = int(
            os.getenv(
                "WHEEL_API_TIMEOUT",
                api_config.get("timeout", 30),
            )
        )
        use_api_mode = os.getenv("WHEEL_USE_API_MODE") is not None or api_config.get(
            "use_api_mode", True
        )

        default_portfolio_id = os.getenv(
            "WHEEL_DEFAULT_PORTFOLIO_ID",
            defaults_config.get("portfolio_id"),
        )
        default_profile = os.getenv(
            "WHEEL_DEFAULT_PROFILE",
            defaults_config.get("profile", "conservative"),
        )
        max_dte = int(
            os.getenv(
                "WHEEL_MAX_DTE",
                defaults_config.get("max_dte", 14),
            )
        )

        verbose = os.getenv("WHEEL_VERBOSE") is not None or cli_config.get("verbose", False)
        json_output = os.getenv("WHEEL_JSON_OUTPUT") is not None or cli_config.get(
            "json_output", False
        )

        try:
            return cls(
                api_url=api_url,
                api_timeout=api_timeout,
                use_api_mode=use_api_mode,
                default_portfolio_id=default_portfolio_id,
                default_profile=default_profile,
                max_dte=max_dte,
                verbose=verbose,
                json_output=json_output,
            )
        except Exception as e:
            raise ConfigurationError(f"Invalid configuration: {e}") from e

    def save_to_file(self, path: Optional[Path] = None):
        """Save configuration to YAML file.

        Args:
            path: Optional path to save to (default: ~/.wheel_strategy/config.yaml)

        Raises:
            ConfigurationError: If save fails

        Example:
            >>> config = WheelStrategyConfig(api_url="http://localhost:8000")
            >>> config.save_to_file()
        """
        config_path = path or self.get_default_config_path()

        # Create directory if it doesn't exist
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Build config structure
        config_dict = {
            "api": {
                "url": self.api_url,
                "timeout": self.api_timeout,
                "use_api_mode": self.use_api_mode,
            },
            "defaults": {
                "portfolio_id": self.default_portfolio_id,
                "profile": self.default_profile,
                "max_dte": self.max_dte,
            },
            "cli": {
                "verbose": self.verbose,
                "json_output": self.json_output,
            },
        }

        try:
            with open(config_path, "w") as f:
                yaml.dump(config_dict, f, default_flow_style=False)
            logger.info(f"Configuration saved to {config_path}")
        except Exception as e:
            raise ConfigurationError(f"Failed to save configuration: {e}") from e

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary.

        Returns:
            Configuration as dictionary

        Example:
            >>> config = WheelStrategyConfig()
            >>> config_dict = config.to_dict()
        """
        return {
            "api": {
                "url": self.api_url,
                "timeout": self.api_timeout,
                "use_api_mode": self.use_api_mode,
            },
            "defaults": {
                "portfolio_id": self.default_portfolio_id,
                "profile": self.default_profile,
                "max_dte": self.max_dte,
            },
            "cli": {
                "verbose": self.verbose,
                "json_output": self.json_output,
            },
        }

    def __repr__(self) -> str:
        """String representation of configuration.

        Returns:
            String representation

        Example:
            >>> config = WheelStrategyConfig()
            >>> print(config)
        """
        return (
            f"WheelStrategyConfig("
            f"api_url={self.api_url!r}, "
            f"api_timeout={self.api_timeout}, "
            f"use_api_mode={self.use_api_mode}, "
            f"default_portfolio_id={self.default_portfolio_id!r}, "
            f"default_profile={self.default_profile!r}, "
            f"max_dte={self.max_dte}, "
            f"verbose={self.verbose}, "
            f"json_output={self.json_output}"
            ")"
        )


def load_config(config_path: Optional[Path] = None) -> WheelStrategyConfig:
    """Load configuration from file or defaults.

    Convenience function for loading configuration.

    Args:
        config_path: Optional path to config file

    Returns:
        Configuration instance

    Example:
        >>> from src.wheel.config import load_config
        >>> config = load_config()
        >>> print(config.api_url)
    """
    return WheelStrategyConfig.load_from_file(config_path)
