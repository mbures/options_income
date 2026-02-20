"""Configuration management for the FastAPI server.

This module handles configuration loading from environment variables and
credential files, providing sensible defaults for development and production.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Project root (three levels up from this file: src/server/config.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application configuration settings.

    Attributes:
        app_name: Application name
        version: Application version
        debug: Debug mode flag
        database_url: SQLAlchemy database URL
        cors_origins: List of allowed CORS origins
        host: Server host address
        port: Server port number
    """

    app_name: str = "Wheel Strategy API"
    version: str = "1.0.0"
    debug: bool = True

    # Database configuration
    database_path: str = "~/.wheel_strategy/trades.db"

    # Credential file paths (relative to project root)
    finnhub_key_file: str = "config/finhub_api_key.txt"
    schwab_key_file: str = "config/charles_schwab_key.txt"

    # CORS configuration - allow local development origins
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ]

    # Server configuration
    host: str = "0.0.0.0"
    port: int = 8000

    class Config:
        """Pydantic configuration."""
        env_prefix = "WHEEL_"
        case_sensitive = False

    @property
    def database_url(self) -> str:
        """Get SQLAlchemy database URL.

        Returns:
            Database URL string for SQLAlchemy
        """
        expanded_path = os.path.expanduser(self.database_path)
        return f"sqlite:///{expanded_path}"

    def get_database_path(self) -> Path:
        """Get expanded database path as Path object.

        Returns:
            Resolved database file path
        """
        return Path(os.path.expanduser(self.database_path))


def _load_credentials() -> None:
    """Load API credentials from config files into environment variables.

    Reads credential files from the config/ directory and sets the
    corresponding environment variables if they are not already set.
    This allows the rest of the codebase to use os.environ consistently.
    """
    # Load Finnhub API key
    if not os.environ.get("FINNHUB_API_KEY"):
        finnhub_path = PROJECT_ROOT / settings.finnhub_key_file
        if finnhub_path.is_file():
            content = finnhub_path.read_text().strip()
            # Parse "key = value" format
            for line in content.splitlines():
                if "=" in line:
                    _, value = line.split("=", 1)
                    os.environ["FINNHUB_API_KEY"] = value.strip().strip("'\"")
                    logger.info("Loaded FINNHUB_API_KEY from %s", finnhub_path)
                    break

    # Load Schwab credentials
    if not os.environ.get("SCHWAB_CLIENT_ID") or not os.environ.get("SCHWAB_CLIENT_SECRET"):
        schwab_path = PROJECT_ROOT / settings.schwab_key_file
        if schwab_path.is_file():
            content = schwab_path.read_text().strip()
            for line in content.splitlines():
                if line.startswith("app_key:"):
                    os.environ["SCHWAB_CLIENT_ID"] = line.split(":", 1)[1].strip()
                elif line.startswith("secret:"):
                    os.environ["SCHWAB_CLIENT_SECRET"] = line.split(":", 1)[1].strip()
            if os.environ.get("SCHWAB_CLIENT_ID"):
                logger.info("Loaded Schwab credentials from %s", schwab_path)


# Global settings instance
settings = Settings()

# Load credentials from files on module import
_load_credentials()
