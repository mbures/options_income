"""
OAuth configuration for Schwab API integration.

This module provides configuration management for OAuth 2.0 authentication
with Charles Schwab's APIs. Configuration can be loaded from environment
variables or provided programmatically.
"""

import os
from dataclasses import dataclass

from .exceptions import ConfigurationError


@dataclass
class SchwabOAuthConfig:
    """
    Configuration for Schwab OAuth 2.0.

    This configuration supports a devcontainer deployment model where:
    - Authorization (callback server) runs on HOST machine
    - Application runs in DEVCONTAINER
    - Token file is in project directory (accessible to both)

    Attributes:
        client_id: Schwab App client ID from Dev Portal
        client_secret: Schwab App client secret from Dev Portal
        callback_host: Domain for OAuth callback (default: dirtydata.ai)
        callback_port: Port for callback server (default: 8443)
        callback_path: URL path for callback (default: /oauth/callback)
        authorization_url: Schwab OAuth authorization endpoint
        token_url: Schwab OAuth token endpoint
        token_file: Absolute path to token storage file
        ssl_cert_path: Path to SSL certificate (for HOST callback server)
        ssl_key_path: Path to SSL private key (for HOST callback server)
        refresh_buffer_seconds: Refresh tokens this many seconds before expiry
    """

    # Required - from Schwab Dev Portal
    client_id: str
    client_secret: str

    # Callback configuration
    callback_host: str = "dirtydata.ai"
    callback_port: int = 8443
    callback_path: str = "/oauth/callback"

    # Schwab OAuth endpoints
    authorization_url: str = "https://api.schwabapi.com/v1/oauth/authorize"
    token_url: str = "https://api.schwabapi.com/v1/oauth/token"

    # Token storage (project directory for devcontainer compatibility)
    token_file: str = "/workspaces/options_income/.schwab_tokens.json"

    # SSL certificate paths (for callback server on HOST)
    ssl_cert_path: str = "/etc/letsencrypt/live/dirtydata.ai/fullchain.pem"
    ssl_key_path: str = "/etc/letsencrypt/live/dirtydata.ai/privkey.pem"

    # Token refresh settings
    refresh_buffer_seconds: int = 300  # Refresh 5 min before expiry

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.client_id:
            raise ConfigurationError("client_id cannot be empty")

        if not self.client_secret:
            raise ConfigurationError("client_secret cannot be empty")

        if not isinstance(self.callback_port, int) or not (
            1 <= self.callback_port <= 65535
        ):
            raise ConfigurationError(
                f"callback_port must be between 1 and 65535, got {self.callback_port}"
            )

        if self.refresh_buffer_seconds < 0:
            raise ConfigurationError("refresh_buffer_seconds cannot be negative")

    @property
    def callback_url(self) -> str:
        """
        Full callback URL for OAuth redirect.

        Returns:
            Complete HTTPS callback URL (e.g., https://dirtydata.ai:8443/oauth/callback)
        """
        return f"https://{self.callback_host}:{self.callback_port}{self.callback_path}"

    @classmethod
    def from_env(cls) -> "SchwabOAuthConfig":
        """
        Load configuration from environment variables.

        Required environment variables:
            SCHWAB_CLIENT_ID: Schwab App client ID
            SCHWAB_CLIENT_SECRET: Schwab App client secret

        Optional environment variables:
            SCHWAB_CALLBACK_HOST: Callback domain (default: dirtydata.ai)
            SCHWAB_CALLBACK_PORT: Callback port (default: 8443)
            SCHWAB_TOKEN_FILE: Token file path (default: /workspaces/options_income/.schwab_tokens.json)
            SCHWAB_SSL_CERT_PATH: SSL certificate path (default: /etc/letsencrypt/live/dirtydata.ai/fullchain.pem)
            SCHWAB_SSL_KEY_PATH: SSL private key path (default: /etc/letsencrypt/live/dirtydata.ai/privkey.pem)

        Returns:
            SchwabOAuthConfig instance

        Raises:
            ConfigurationError: If required environment variables are missing
        """
        client_id = os.environ.get("SCHWAB_CLIENT_ID")
        client_secret = os.environ.get("SCHWAB_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise ConfigurationError(
                "Missing Schwab OAuth credentials. Set environment variables:\n"
                "  SCHWAB_CLIENT_ID=your_client_id\n"
                "  SCHWAB_CLIENT_SECRET=your_client_secret\n"
                "\n"
                "Get credentials from: https://developer.schwab.com"
            )

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            callback_host=os.environ.get("SCHWAB_CALLBACK_HOST", "dirtydata.ai"),
            callback_port=int(os.environ.get("SCHWAB_CALLBACK_PORT", "8443")),
            token_file=os.environ.get(
                "SCHWAB_TOKEN_FILE", "/workspaces/options_income/.schwab_tokens.json"
            ),
            ssl_cert_path=os.environ.get(
                "SCHWAB_SSL_CERT_PATH", "/etc/letsencrypt/live/dirtydata.ai/fullchain.pem"
            ),
            ssl_key_path=os.environ.get(
                "SCHWAB_SSL_KEY_PATH", "/etc/letsencrypt/live/dirtydata.ai/privkey.pem"
            ),
        )
