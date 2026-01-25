"""Exceptions for Schwab API client."""


class SchwabAPIError(Exception):
    """Base exception for Schwab API errors."""

    pass


class SchwabAuthenticationError(SchwabAPIError):
    """
    Authentication failure with Schwab API.

    This error indicates that the OAuth token is invalid, expired, or revoked.
    The user needs to re-authorize the application.

    Resolution:
        1. Exit the devcontainer
        2. On the HOST machine, run: python scripts/authorize_schwab_host.py
        3. Complete the authorization flow in your browser
        4. Return to the devcontainer and try again
    """

    pass


class SchwabRateLimitError(SchwabAPIError):
    """API rate limit exceeded."""

    pass


class SchwabInvalidSymbolError(SchwabAPIError):
    """Invalid or unknown symbol."""

    pass
