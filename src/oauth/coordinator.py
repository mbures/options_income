"""
OAuth coordinator for high-level OAuth operations.

This module provides the main interface for OAuth operations in the
application. It coordinates the authorization flow, token management,
and provides simple methods for obtaining valid access tokens.
"""

import logging
from typing import Optional

from .auth_server import AuthorizationResult, run_authorization_flow
from .config import SchwabOAuthConfig
from .exceptions import AuthorizationError, TokenNotAvailableError
from .token_manager import TokenManager
from .token_storage import TokenStorage

logger = logging.getLogger(__name__)


class OAuthCoordinator:
    """
    High-level coordinator for OAuth operations.

    This is the main interface that applications should use for OAuth.
    It handles the complete authorization lifecycle and provides simple
    methods for obtaining valid access tokens.

    Example:
        coordinator = OAuthCoordinator()
        if coordinator.ensure_authorized():
            token = coordinator.get_access_token()
            # Use token for API calls
    """

    def __init__(self, config: Optional[SchwabOAuthConfig] = None):
        """
        Initialize OAuth coordinator.

        Args:
            config: OAuth configuration (loads from environment if not provided)
        """
        self.config = config or SchwabOAuthConfig.from_env()
        self.storage = TokenStorage(self.config.token_file)
        self.token_manager = TokenManager(self.config, self.storage)

    def ensure_authorized(self, auto_open_browser: bool = True) -> bool:
        """
        Ensure we have valid authorization, running flow if needed.

        This is the preferred method for applications to ensure they're
        authorized before making API calls. If not currently authorized,
        it will automatically run the authorization flow.

        Args:
            auto_open_browser: Whether to auto-open browser for auth

        Returns:
            True if authorized (or authorization succeeded), False if failed
        """
        # Check if already authorized
        if self.token_manager.is_authorized():
            logger.info("Already authorized")
            return True

        # Need to run authorization flow
        logger.info("No valid tokens found, starting authorization flow")
        return self.run_authorization_flow(auto_open_browser)

    def run_authorization_flow(self, open_browser: bool = True) -> bool:
        """
        Run the complete OAuth authorization flow.

        This orchestrates the full authorization process:
        1. Starts HTTPS callback server
        2. Opens browser for user authorization
        3. Receives authorization code from callback
        4. Exchanges code for access and refresh tokens
        5. Saves tokens to storage

        Args:
            open_browser: Whether to automatically open browser

        Returns:
            True if authorization succeeded, False otherwise
        """
        # Run authorization flow to get code
        result: AuthorizationResult = run_authorization_flow(
            self.config, open_browser=open_browser, timeout=300
        )

        if not result.success:
            logger.error(
                f"Authorization failed: {result.error} - {result.error_description}"
            )
            return False

        # Exchange authorization code for tokens
        try:
            self.token_manager.exchange_code_for_tokens(result.authorization_code)
            logger.info("✅ Authorization complete! Tokens saved successfully.")
            return True
        except Exception as e:
            logger.error(f"Token exchange failed: {e}")
            return False

    def get_access_token(self) -> str:
        """
        Get a valid access token for API calls.

        This method automatically refreshes the token if it's expired or
        expiring soon. Applications should call this method before each
        API request to ensure they have a valid token.

        Returns:
            Valid access token string

        Raises:
            TokenNotAvailableError: If not authorized (need to run authorization flow)
        """
        return self.token_manager.get_valid_access_token()

    def get_authorization_header(self) -> dict:
        """
        Get Authorization header dict for API requests.

        Convenience method that returns a dictionary ready to be merged
        into request headers.

        Returns:
            Dict with Authorization header: {"Authorization": "Bearer <token>"}

        Raises:
            TokenNotAvailableError: If not authorized

        Example:
            headers = coordinator.get_authorization_header()
            response = requests.get(url, headers=headers)
        """
        token = self.get_access_token()
        return {"Authorization": f"Bearer {token}"}

    def is_authorized(self) -> bool:
        """
        Check if currently authorized.

        Returns:
            True if we have valid (or refreshable) tokens, False otherwise
        """
        return self.token_manager.is_authorized()

    def get_status(self) -> dict:
        """
        Get current authorization status for diagnostics.

        Returns:
            Dictionary with status information including:
            - authorized: bool
            - expired: bool (if authorized)
            - expires_at: ISO timestamp (if authorized)
            - expires_in_seconds: int (if authorized)
            - scope: str (if authorized)
            - message: str (if not authorized)

        Example:
            status = coordinator.get_status()
            if status["authorized"]:
                print(f"Token expires in {status['expires_in_seconds']} seconds")
        """
        return self.token_manager.get_token_status()

    def revoke(self) -> None:
        """
        Revoke current authorization.

        This deletes the locally stored tokens. The user will need to
        re-authorize before making API calls again.

        Note: This does NOT revoke the tokens on Schwab's servers. It
        only deletes the local token file.
        """
        self.token_manager.revoke()
        logger.info("Authorization revoked locally. Re-authorization required.")
