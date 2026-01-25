"""
Token storage for Schwab OAuth integration.

This module provides file-based token persistence with expiry tracking.
Tokens are stored in plaintext JSON in the project directory for
devcontainer compatibility (same path accessible to host and container).
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .exceptions import TokenStorageError

logger = logging.getLogger(__name__)


@dataclass
class TokenData:
    """
    Stored OAuth token data.

    Attributes:
        access_token: Short-lived access token for API calls
        refresh_token: Long-lived token for obtaining new access tokens
        token_type: Token type (typically "Bearer")
        expires_in: Token lifetime in seconds from issue time
        scope: Granted OAuth scopes
        issued_at: ISO timestamp of when tokens were issued/refreshed
    """

    access_token: str
    refresh_token: str
    token_type: str  # "Bearer"
    expires_in: int  # seconds from issue
    scope: str
    issued_at: str  # ISO timestamp

    @property
    def expires_at(self) -> datetime:
        """
        Calculate expiration datetime.

        Returns:
            Datetime when access token expires (timezone-aware UTC)
        """
        issued = datetime.fromisoformat(self.issued_at)
        # Ensure timezone-aware
        if issued.tzinfo is None:
            issued = issued.replace(tzinfo=timezone.utc)
        return issued + timedelta(seconds=self.expires_in)

    @property
    def is_expired(self) -> bool:
        """
        Check if access token is expired.

        Returns:
            True if token has expired, False otherwise
        """
        return datetime.now(timezone.utc) >= self.expires_at

    def expires_within(self, seconds: int) -> bool:
        """
        Check if token expires within given seconds.

        Useful for proactive token refresh (e.g., refresh if expires within 5 minutes).

        Args:
            seconds: Number of seconds to check

        Returns:
            True if token will expire within the specified time, False otherwise
        """
        buffer_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        return buffer_time >= self.expires_at

    def to_dict(self) -> dict:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of token data
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TokenData":
        """
        Create TokenData from dictionary.

        Args:
            data: Dictionary with token data fields

        Returns:
            TokenData instance

        Raises:
            KeyError: If required fields are missing
            TypeError: If fields have wrong types
        """
        return cls(**data)


class TokenStorage:
    """
    File-based token storage (plaintext JSON).

    Stores tokens in project directory for devcontainer compatibility.
    Token file is accessible to both host (for authorization) and
    container (for application usage and token refresh).

    The token file path is absolute and works identically in both
    host and container contexts.
    """

    def __init__(self, token_file: str):
        """
        Initialize token storage.

        Args:
            token_file: Absolute path to token storage file
                       (e.g., /workspaces/options_income/.schwab_tokens.json)
        """
        self.token_file = Path(token_file)
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Create parent directory if needed."""
        self.token_file.parent.mkdir(parents=True, exist_ok=True)

    def _set_secure_permissions(self) -> None:
        """Set file permissions to user-only read/write (600)."""
        try:
            self.token_file.chmod(0o600)
            logger.debug(f"Set secure permissions (600) on {self.token_file}")
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not set secure permissions: {e}")

    def save(self, token_data: TokenData) -> None:
        """
        Save tokens to file.

        Writes tokens as JSON with secure permissions (chmod 600).
        File is accessible to both host and container contexts.

        Args:
            token_data: Token data to save

        Raises:
            TokenStorageError: If save operation fails
        """
        try:
            with open(self.token_file, "w") as f:
                json.dump(token_data.to_dict(), f, indent=2)

            # Set secure permissions after writing
            self._set_secure_permissions()

            logger.info(f"Tokens saved to {self.token_file}")
        except (IOError, OSError) as e:
            logger.error(f"Failed to save tokens: {e}")
            raise TokenStorageError(f"Failed to save tokens: {e}") from e

    def load(self) -> Optional[TokenData]:
        """
        Load tokens from file.

        Returns:
            TokenData if file exists and is valid, None otherwise

        Notes:
            - Returns None if file doesn't exist (normal on first run)
            - Returns None if file is corrupted (logs warning)
            - Does not raise exceptions for missing/corrupted files
        """
        if not self.token_file.exists():
            logger.debug(f"No token file found at {self.token_file}")
            return None

        try:
            with open(self.token_file, "r") as f:
                data = json.load(f)

            token_data = TokenData.from_dict(data)
            logger.debug(f"Tokens loaded from {self.token_file}")
            return token_data

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(
                f"Invalid token file at {self.token_file}, "
                f"will need re-authorization: {e}"
            )
            return None
        except (IOError, OSError) as e:
            logger.warning(f"Could not read token file: {e}")
            return None

    def delete(self) -> bool:
        """
        Delete token file.

        Returns:
            True if file was deleted, False if file didn't exist

        Notes:
            Does not raise exceptions if file doesn't exist
        """
        if self.token_file.exists():
            try:
                self.token_file.unlink()
                logger.info(f"Token file deleted: {self.token_file}")
                return True
            except (OSError, PermissionError) as e:
                logger.error(f"Failed to delete token file: {e}")
                raise TokenStorageError(f"Failed to delete token file: {e}") from e

        logger.debug(f"Token file does not exist: {self.token_file}")
        return False

    def exists(self) -> bool:
        """
        Check if token file exists.

        Returns:
            True if token file exists, False otherwise
        """
        return self.token_file.exists()
