"""
Token manager for Schwab OAuth integration.

This module manages the OAuth token lifecycle including:
- Token exchange (authorization code → access/refresh tokens)
- Token refresh (refresh token → new access token)
- Automatic refresh before expiry
- Token validation and status checks
"""

import logging
import time
from base64 import b64encode
from datetime import datetime, timezone
from typing import Optional

import requests

from .config import SchwabOAuthConfig
from .exceptions import TokenExchangeError, TokenNotAvailableError, TokenRefreshError
from .token_storage import TokenData, TokenStorage

logger = logging.getLogger(__name__)


class TokenManager:
    """
    Manages OAuth token lifecycle.

    Responsibilities:
    - Exchange authorization codes for tokens
    - Refresh access tokens before expiry
    - Provide valid access tokens to API clients
    - Track token status
    """

    def __init__(self, config: SchwabOAuthConfig, storage: Optional[TokenStorage] = None):
        """
        Initialize token manager.

        Args:
            config: OAuth configuration
            storage: Token storage (creates default if not provided)
        """
        self.config = config
        self.storage = storage or TokenStorage(config.token_file)
        self._cached_token: Optional[TokenData] = None

    def exchange_code_for_tokens(self, authorization_code: str) -> TokenData:
        """
        Exchange authorization code for access and refresh tokens.

        This is called once after the user authorizes the application.
        The authorization code is obtained from the OAuth callback.

        Args:
            authorization_code: Code received from OAuth callback

        Returns:
            TokenData with access and refresh tokens

        Raises:
            TokenExchangeError: If exchange fails
        """
        logger.info("Exchanging authorization code for tokens")

        # Prepare Basic auth header
        credentials = f"{self.config.client_id}:{self.config.client_secret}"
        auth_header = b64encode(credentials.encode()).decode()

        try:
            response = requests.post(
                self.config.token_url,
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "authorization_code",
                    "code": authorization_code,
                    "redirect_uri": self.config.callback_url,
                },
                timeout=30,
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(
                    f"Token exchange failed: {response.status_code} - {error_detail}"
                )
                raise TokenExchangeError(
                    f"Token exchange failed with status {response.status_code}. "
                    f"Check that your client_id and client_secret are correct."
                )

            data = response.json()

            token_data = TokenData(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                token_type=data.get("token_type", "Bearer"),
                expires_in=data["expires_in"],
                scope=data.get("scope", ""),
                issued_at=datetime.now(timezone.utc).isoformat(),
            )

            # Save tokens
            self.storage.save(token_data)
            self._cached_token = token_data

            logger.info("Successfully obtained and saved tokens")
            return token_data

        except requests.RequestException as e:
            logger.error(f"Network error during token exchange: {e}")
            raise TokenExchangeError(f"Network error during token exchange: {e}") from e
        except (KeyError, ValueError) as e:
            logger.error(f"Invalid response from token endpoint: {e}")
            raise TokenExchangeError(
                f"Invalid response from token endpoint: {e}"
            ) from e

    def refresh_tokens(self, retry_count: int = 0, max_retries: int = 3) -> TokenData:
        """
        Refresh access token using refresh token.

        Implements exponential backoff retry logic for transient network errors.

        Args:
            retry_count: Current retry attempt (used internally)
            max_retries: Maximum number of retry attempts

        Returns:
            New TokenData with fresh access token

        Raises:
            TokenRefreshError: If refresh fails after all retries
            TokenNotAvailableError: If no refresh token available
        """
        current_token = self._get_current_token()
        if not current_token:
            raise TokenNotAvailableError(
                "No refresh token available. Run authorization flow first."
            )

        logger.info(f"Refreshing access token (attempt {retry_count + 1}/{max_retries + 1})")

        # Prepare Basic auth header
        credentials = f"{self.config.client_id}:{self.config.client_secret}"
        auth_header = b64encode(credentials.encode()).decode()

        try:
            response = requests.post(
                self.config.token_url,
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": current_token.refresh_token,
                },
                timeout=30,
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(
                    f"Token refresh failed: {response.status_code} - {error_detail}"
                )

                # Don't retry on 400-level errors (bad refresh token, etc.)
                if 400 <= response.status_code < 500:
                    raise TokenRefreshError(
                        f"Token refresh failed with status {response.status_code}. "
                        f"Your refresh token may have expired. "
                        f"Please run the authorization flow again."
                    )

                # Retry on 500-level errors
                if retry_count < max_retries:
                    delay = 2 ** retry_count  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Retrying after {delay}s due to server error")
                    time.sleep(delay)
                    return self.refresh_tokens(retry_count + 1, max_retries)

                raise TokenRefreshError(
                    f"Token refresh failed after {max_retries + 1} attempts"
                )

            data = response.json()

            token_data = TokenData(
                access_token=data["access_token"],
                # Refresh token may or may not be returned; keep existing if not
                refresh_token=data.get("refresh_token", current_token.refresh_token),
                token_type=data.get("token_type", "Bearer"),
                expires_in=data["expires_in"],
                scope=data.get("scope", current_token.scope),
                issued_at=datetime.now(timezone.utc).isoformat(),
            )

            self.storage.save(token_data)
            self._cached_token = token_data

            logger.info("Successfully refreshed tokens")
            return token_data

        except requests.RequestException as e:
            logger.warning(f"Network error during token refresh: {e}")

            # Retry on network errors
            if retry_count < max_retries:
                delay = 2 ** retry_count  # Exponential backoff
                logger.warning(f"Retrying after {delay}s due to network error")
                time.sleep(delay)
                return self.refresh_tokens(retry_count + 1, max_retries)

            logger.error(f"Token refresh failed after {max_retries + 1} attempts")
            raise TokenRefreshError(
                f"Network error during token refresh after {max_retries + 1} attempts: {e}"
            ) from e

        except (KeyError, ValueError) as e:
            logger.error(f"Invalid response from token endpoint: {e}")
            raise TokenRefreshError(
                f"Invalid response from token endpoint: {e}"
            ) from e

    def get_valid_access_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.

        This is the main method used by API clients. It automatically:
        - Loads tokens from storage
        - Checks expiry
        - Refreshes if needed
        - Returns valid access token

        Returns:
            Valid access token string

        Raises:
            TokenNotAvailableError: If no valid token and can't refresh
                                   (need to run authorization flow)
        """
        token = self._get_current_token()

        if not token:
            raise TokenNotAvailableError(
                "No tokens available. Run authorization flow first."
            )

        # Check if refresh needed (token expires soon or already expired)
        if token.expires_within(self.config.refresh_buffer_seconds):
            logger.info(
                f"Token expires soon "
                f"(within {self.config.refresh_buffer_seconds}s), refreshing..."
            )
            token = self.refresh_tokens()

        return token.access_token

    def is_authorized(self) -> bool:
        """
        Check if we have valid (or refreshable) tokens.

        Returns:
            True if authorized (have tokens), False otherwise
        """
        token = self._get_current_token()
        return token is not None

    def get_token_status(self) -> dict:
        """
        Get current token status for diagnostics.

        Returns:
            Dictionary with token status information:
            - authorized: Whether we have tokens
            - expired: Whether access token is expired (if authorized)
            - expires_at: When access token expires (if authorized)
            - expires_in_seconds: Seconds until expiry (if authorized)
            - scope: OAuth scopes granted (if authorized)
        """
        token = self._get_current_token()

        if not token:
            return {"authorized": False, "message": "No tokens stored"}

        expires_in = (token.expires_at - datetime.now(timezone.utc)).total_seconds()

        return {
            "authorized": True,
            "expired": token.is_expired,
            "expires_at": token.expires_at.isoformat(),
            "expires_in_seconds": max(0, expires_in),
            "scope": token.scope,
        }

    def revoke(self) -> None:
        """
        Delete stored tokens (local revocation).

        This removes tokens from local storage. It does NOT revoke
        tokens on Schwab's servers (would require additional API call).

        After revocation, authorization flow must be run again.
        """
        self.storage.delete()
        self._cached_token = None
        logger.info("Tokens revoked (local)")

    def _get_current_token(self) -> Optional[TokenData]:
        """
        Get current token from cache or storage.

        Returns:
            TokenData if available, None otherwise
        """
        if self._cached_token:
            return self._cached_token

        self._cached_token = self.storage.load()
        return self._cached_token
