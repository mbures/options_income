"""Tests for OAuth exceptions."""

import pytest

from src.oauth.exceptions import (
    AuthorizationError,
    ConfigurationError,
    SchwabOAuthError,
    TokenExchangeError,
    TokenNotAvailableError,
    TokenRefreshError,
    TokenStorageError,
)


class TestOAuthExceptions:
    """Tests for OAuth exception hierarchy."""

    def test_schwab_oauth_error_is_base_exception(self):
        """SchwabOAuthError is base for all OAuth errors."""
        error = SchwabOAuthError("test error")
        assert isinstance(error, Exception)
        assert str(error) == "test error"

    def test_configuration_error_inherits_from_base(self):
        """ConfigurationError inherits from SchwabOAuthError."""
        error = ConfigurationError("config error")
        assert isinstance(error, SchwabOAuthError)
        assert isinstance(error, Exception)
        assert str(error) == "config error"

    def test_authorization_error_inherits_from_base(self):
        """AuthorizationError inherits from SchwabOAuthError."""
        error = AuthorizationError("auth error")
        assert isinstance(error, SchwabOAuthError)
        assert str(error) == "auth error"

    def test_token_exchange_error_inherits_from_base(self):
        """TokenExchangeError inherits from SchwabOAuthError."""
        error = TokenExchangeError("exchange error")
        assert isinstance(error, SchwabOAuthError)
        assert str(error) == "exchange error"

    def test_token_refresh_error_inherits_from_base(self):
        """TokenRefreshError inherits from SchwabOAuthError."""
        error = TokenRefreshError("refresh error")
        assert isinstance(error, SchwabOAuthError)
        assert str(error) == "refresh error"

    def test_token_not_available_error_inherits_from_base(self):
        """TokenNotAvailableError inherits from SchwabOAuthError."""
        error = TokenNotAvailableError("not available")
        assert isinstance(error, SchwabOAuthError)
        assert str(error) == "not available"

    def test_token_storage_error_inherits_from_base(self):
        """TokenStorageError inherits from SchwabOAuthError."""
        error = TokenStorageError("storage error")
        assert isinstance(error, SchwabOAuthError)
        assert str(error) == "storage error"

    def test_exceptions_can_be_caught_as_base_type(self):
        """All OAuth exceptions can be caught as SchwabOAuthError."""
        exceptions = [
            ConfigurationError("error"),
            AuthorizationError("error"),
            TokenExchangeError("error"),
            TokenRefreshError("error"),
            TokenNotAvailableError("error"),
            TokenStorageError("error"),
        ]

        for exc in exceptions:
            try:
                raise exc
            except SchwabOAuthError as caught:
                assert isinstance(caught, SchwabOAuthError)
