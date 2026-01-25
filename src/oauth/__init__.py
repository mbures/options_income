"""
OAuth 2.0 module for Schwab API integration.

This module provides OAuth 2.0 Authorization Code flow implementation
for authenticating with Charles Schwab's Trading and Market Data APIs.

The module supports a devcontainer deployment model:
- Authorization (callback server) runs on HOST machine
- Application runs in DEVCONTAINER
- Token file is in project directory (accessible to both contexts)

Public API:
    SchwabOAuthConfig: OAuth configuration management
    TokenData: Token data structure
    TokenStorage: File-based token persistence
    TokenManager: Token lifecycle management
    OAuthCoordinator: High-level OAuth interface

Exceptions:
    SchwabOAuthError: Base exception
    ConfigurationError: Configuration error
    AuthorizationError: Authorization flow error
    TokenExchangeError: Token exchange failed
    TokenRefreshError: Token refresh failed
    TokenNotAvailableError: No valid tokens
    TokenStorageError: Storage operation failed
"""

from .auth_server import AuthorizationResult, OAuthCallbackServer, run_authorization_flow
from .config import SchwabOAuthConfig
from .coordinator import OAuthCoordinator
from .exceptions import (
    AuthorizationError,
    ConfigurationError,
    SchwabOAuthError,
    TokenExchangeError,
    TokenNotAvailableError,
    TokenRefreshError,
    TokenStorageError,
)
from .token_manager import TokenManager
from .token_storage import TokenData, TokenStorage

__all__ = [
    # Configuration
    "SchwabOAuthConfig",
    # Token Storage
    "TokenData",
    "TokenStorage",
    # Token Manager
    "TokenManager",
    # Authorization Server
    "OAuthCallbackServer",
    "AuthorizationResult",
    "run_authorization_flow",
    # Coordinator
    "OAuthCoordinator",
    # Exceptions
    "SchwabOAuthError",
    "ConfigurationError",
    "AuthorizationError",
    "TokenExchangeError",
    "TokenRefreshError",
    "TokenNotAvailableError",
    "TokenStorageError",
]
