"""
OAuth exception classes for Schwab API integration.

This module defines the exception hierarchy for all OAuth-related errors,
providing clear error messages and recovery guidance.
"""


class SchwabOAuthError(Exception):
    """Base exception for all Schwab OAuth errors."""

    pass


class ConfigurationError(SchwabOAuthError):
    """OAuth configuration error (missing or invalid configuration)."""

    pass


class AuthorizationError(SchwabOAuthError):
    """OAuth authorization flow error."""

    pass


class TokenExchangeError(SchwabOAuthError):
    """Failed to exchange authorization code for tokens."""

    pass


class TokenRefreshError(SchwabOAuthError):
    """Failed to refresh access token using refresh token."""

    pass


class TokenNotAvailableError(SchwabOAuthError):
    """No valid tokens available (need to authorize first)."""

    pass


class TokenStorageError(SchwabOAuthError):
    """Token storage operation failed (file I/O error)."""

    pass
