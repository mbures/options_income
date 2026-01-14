"""Configuration management for Finnhub Options Chain retrieval."""

import os
import re
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


@dataclass
class FinnhubConfig:
    """
    Configuration for Finnhub API client.

    Attributes:
        api_key: Finnhub API key for authentication
        base_url: Base URL for Finnhub API
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts for failed requests
        retry_delay: Initial delay between retries (seconds)
    """

    api_key: str
    base_url: str = "https://finnhub.io/api/v1"
    timeout: int = 10
    max_retries: int = 3
    retry_delay: float = 1.0

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.api_key:
            raise ValueError("API key cannot be empty")

        if self.timeout <= 0:
            raise ValueError("Timeout must be positive")

        if self.max_retries < 0:
            raise ValueError("Max retries cannot be negative")

        if self.retry_delay <= 0:
            raise ValueError("Retry delay must be positive")

    @classmethod
    def from_env(cls, api_key_var: str = "FINNHUB_API_KEY") -> "FinnhubConfig":
        """
        Load configuration from environment variables.

        Args:
            api_key_var: Name of environment variable containing API key

        Returns:
            FinnhubConfig instance

        Raises:
            ValueError: If API key environment variable is not set
        """
        api_key = os.getenv(api_key_var)
        if not api_key:
            raise ValueError(
                f"{api_key_var} environment variable not set. "
                f"Get your API key from https://finnhub.io/register"
            )

        return cls(api_key=api_key)

    @classmethod
    def from_file(cls, file_path: str = "config/finhub_api_key.txt") -> "FinnhubConfig":
        """
        Load configuration from a file.

        The file should contain a line in the format:
        finhub_api_key = 'value'

        Args:
            file_path: Path to the API key file (relative to project root)

        Returns:
            FinnhubConfig instance

        Raises:
            ValueError: If file not found or API key cannot be parsed
            FileNotFoundError: If the file does not exist
        """
        # Get the project root (parent of src directory)
        project_root = Path(__file__).parent.parent
        full_path = project_root / file_path

        if not full_path.exists():
            raise FileNotFoundError(
                f"API key file not found at {full_path}. "
                f"Please create the file with format: finhub_api_key = 'your_key'"
            )

        # Read the file and parse the API key
        content = full_path.read_text().strip()

        # Parse the format: finhub_api_key = 'value' or finhub_api_key = "value"
        match = re.match(r"finhub_api_key\s*=\s*['\"](.+?)['\"]", content)
        if not match:
            raise ValueError(
                f"Could not parse API key from {file_path}. "
                f"Expected format: finhub_api_key = 'your_key'"
            )

        api_key = match.group(1)
        if not api_key:
            raise ValueError("API key is empty in config file")

        return cls(api_key=api_key)
