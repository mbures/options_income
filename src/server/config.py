"""Configuration management for the FastAPI server.

This module handles configuration loading from environment variables and
provides sensible defaults for development and production environments.
"""

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


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

    # CORS configuration - allow local development origins
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
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


# Global settings instance
settings = Settings()
