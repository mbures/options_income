"""Tests for OAuth token manager module."""

import tempfile
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
import requests

from src.oauth.config import SchwabOAuthConfig
from src.oauth.exceptions import (
    TokenExchangeError,
    TokenNotAvailableError,
    TokenRefreshError,
)
from src.oauth.token_manager import TokenManager
from src.oauth.token_storage import TokenData, TokenStorage


class TestTokenManager:
    """Tests for TokenManager class."""

    @pytest.fixture
    def config(self):
        """Create test OAuth config."""
        return SchwabOAuthConfig(
            client_id="test_client_id",
            client_secret="test_client_secret",
            token_file="/tmp/test_tokens.json",
        )

    @pytest.fixture
    def temp_storage(self):
        """Create temporary token storage."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            storage = TokenStorage(f.name)
        yield storage
        # Cleanup
        try:
            storage.delete()
        except Exception:
            pass

    @pytest.fixture
    def valid_token_data(self):
        """Create valid token data (not expired)."""
        return TokenData(
            access_token="valid_access_token",
            refresh_token="valid_refresh_token",
            token_type="Bearer",
            expires_in=1800,  # 30 minutes
            scope="trading market_data",
            issued_at=datetime.now(timezone.utc).isoformat(),
        )

    @pytest.fixture
    def expired_token_data(self):
        """Create expired token data."""
        issued = datetime.now(timezone.utc) - timedelta(hours=1)
        return TokenData(
            access_token="expired_access_token",
            refresh_token="valid_refresh_token",
            token_type="Bearer",
            expires_in=1800,  # Expired 30 minutes ago
            scope="trading",
            issued_at=issued.isoformat(),
        )

    def test_manager_initialization(self, config):
        """TokenManager can be initialized."""
        manager = TokenManager(config)

        assert manager.config == config
        assert isinstance(manager.storage, TokenStorage)
        assert manager._cached_token is None

    def test_manager_with_custom_storage(self, config, temp_storage):
        """TokenManager accepts custom storage."""
        manager = TokenManager(config, storage=temp_storage)

        assert manager.storage == temp_storage

    @mock.patch("requests.post")
    def test_exchange_code_for_tokens_success(self, mock_post, config, temp_storage):
        """exchange_code_for_tokens successfully exchanges code for tokens."""
        # Mock successful token response
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "token_type": "Bearer",
            "expires_in": 1800,
            "scope": "trading market_data",
        }
        mock_post.return_value = mock_response

        manager = TokenManager(config, storage=temp_storage)
        token_data = manager.exchange_code_for_tokens("auth_code_123")

        # Verify API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == config.token_url
        assert "Authorization" in call_args[1]["headers"]
        assert "Basic" in call_args[1]["headers"]["Authorization"]
        assert call_args[1]["data"]["grant_type"] == "authorization_code"
        assert call_args[1]["data"]["code"] == "auth_code_123"

        # Verify token data
        assert token_data.access_token == "new_access_token"
        assert token_data.refresh_token == "new_refresh_token"

        # Verify tokens were saved
        loaded = temp_storage.load()
        assert loaded is not None
        assert loaded.access_token == "new_access_token"

    @mock.patch("requests.post")
    def test_exchange_code_handles_400_error(self, mock_post, config):
        """exchange_code_for_tokens raises TokenExchangeError on 400."""
        mock_response = mock.Mock()
        mock_response.status_code = 400
        mock_response.text = "invalid_grant"
        mock_post.return_value = mock_response

        manager = TokenManager(config)

        with pytest.raises(TokenExchangeError, match="Token exchange failed"):
            manager.exchange_code_for_tokens("bad_code")

    @mock.patch("requests.post")
    def test_exchange_code_handles_network_error(self, mock_post, config):
        """exchange_code_for_tokens raises TokenExchangeError on network error."""
        mock_post.side_effect = requests.RequestException("Network error")

        manager = TokenManager(config)

        with pytest.raises(TokenExchangeError, match="Network error"):
            manager.exchange_code_for_tokens("auth_code")

    @mock.patch("requests.post")
    def test_refresh_tokens_success(
        self, mock_post, config, temp_storage, valid_token_data
    ):
        """refresh_tokens successfully refreshes access token."""
        # Save existing token
        temp_storage.save(valid_token_data)

        # Mock successful refresh response
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "refreshed_access_token",
            "refresh_token": "refreshed_refresh_token",
            "token_type": "Bearer",
            "expires_in": 1800,
            "scope": "trading market_data",
        }
        mock_post.return_value = mock_response

        manager = TokenManager(config, storage=temp_storage)
        token_data = manager.refresh_tokens()

        # Verify API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["data"]["grant_type"] == "refresh_token"
        assert call_args[1]["data"]["refresh_token"] == "valid_refresh_token"

        # Verify new token
        assert token_data.access_token == "refreshed_access_token"

    @mock.patch("requests.post")
    def test_refresh_tokens_preserves_refresh_token_if_not_returned(
        self, mock_post, config, temp_storage, valid_token_data
    ):
        """refresh_tokens keeps existing refresh_token if not in response."""
        temp_storage.save(valid_token_data)

        # Mock response without refresh_token
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "token_type": "Bearer",
            "expires_in": 1800,
            # No refresh_token in response
        }
        mock_post.return_value = mock_response

        manager = TokenManager(config, storage=temp_storage)
        token_data = manager.refresh_tokens()

        # Should keep original refresh_token
        assert token_data.refresh_token == "valid_refresh_token"

    def test_refresh_tokens_raises_if_no_tokens(self, config):
        """refresh_tokens raises TokenNotAvailableError if no tokens."""
        manager = TokenManager(config)

        with pytest.raises(TokenNotAvailableError, match="No refresh token available"):
            manager.refresh_tokens()

    @mock.patch("requests.post")
    def test_refresh_tokens_raises_on_400_error(
        self, mock_post, config, temp_storage, valid_token_data
    ):
        """refresh_tokens raises TokenRefreshError on 400 (bad refresh token)."""
        temp_storage.save(valid_token_data)

        mock_response = mock.Mock()
        mock_response.status_code = 400
        mock_response.text = "invalid_grant"
        mock_post.return_value = mock_response

        manager = TokenManager(config, storage=temp_storage)

        with pytest.raises(TokenRefreshError, match="refresh token may have expired"):
            manager.refresh_tokens()

    @mock.patch("requests.post")
    @mock.patch("time.sleep")  # Mock sleep to speed up test
    def test_refresh_tokens_retries_on_500_error(
        self, mock_sleep, mock_post, config, temp_storage, valid_token_data
    ):
        """refresh_tokens retries on 500 server error."""
        temp_storage.save(valid_token_data)

        # First 2 calls fail with 500, third succeeds
        mock_response_fail = mock.Mock()
        mock_response_fail.status_code = 500
        mock_response_fail.text = "Internal Server Error"

        mock_response_success = mock.Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "access_token": "new_token",
            "refresh_token": "new_refresh",
            "token_type": "Bearer",
            "expires_in": 1800,
        }

        mock_post.side_effect = [
            mock_response_fail,
            mock_response_fail,
            mock_response_success,
        ]

        manager = TokenManager(config, storage=temp_storage)
        token_data = manager.refresh_tokens()

        # Should have retried and eventually succeeded
        assert mock_post.call_count == 3
        assert token_data.access_token == "new_token"

    @mock.patch("requests.post")
    @mock.patch("time.sleep")
    def test_refresh_tokens_retries_on_network_error(
        self, mock_sleep, mock_post, config, temp_storage, valid_token_data
    ):
        """refresh_tokens retries on network error."""
        temp_storage.save(valid_token_data)

        # First 2 calls fail with network error, third succeeds
        mock_response_success = mock.Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "access_token": "new_token",
            "refresh_token": "new_refresh",
            "token_type": "Bearer",
            "expires_in": 1800,
        }

        mock_post.side_effect = [
            requests.RequestException("Network error"),
            requests.RequestException("Network error"),
            mock_response_success,
        ]

        manager = TokenManager(config, storage=temp_storage)
        token_data = manager.refresh_tokens()

        assert mock_post.call_count == 3
        assert token_data.access_token == "new_token"

    @mock.patch("requests.post")
    @mock.patch("time.sleep")
    def test_refresh_tokens_fails_after_max_retries(
        self, mock_sleep, mock_post, config, temp_storage, valid_token_data
    ):
        """refresh_tokens fails after max retries exceeded."""
        temp_storage.save(valid_token_data)

        # All calls fail
        mock_post.side_effect = requests.RequestException("Network error")

        manager = TokenManager(config, storage=temp_storage)

        with pytest.raises(TokenRefreshError, match="after 4 attempts"):
            manager.refresh_tokens()

        # Should have tried 4 times (initial + 3 retries)
        assert mock_post.call_count == 4

    def test_get_valid_access_token_with_valid_token(
        self, config, temp_storage, valid_token_data
    ):
        """get_valid_access_token returns token if still valid."""
        temp_storage.save(valid_token_data)

        manager = TokenManager(config, storage=temp_storage)
        token = manager.get_valid_access_token()

        assert token == "valid_access_token"

    @mock.patch("requests.post")
    def test_get_valid_access_token_refreshes_if_expired(
        self, mock_post, config, temp_storage, expired_token_data
    ):
        """get_valid_access_token auto-refreshes expired token."""
        temp_storage.save(expired_token_data)

        # Mock refresh response
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "refreshed_token",
            "refresh_token": "refreshed_refresh",
            "token_type": "Bearer",
            "expires_in": 1800,
        }
        mock_post.return_value = mock_response

        manager = TokenManager(config, storage=temp_storage)
        token = manager.get_valid_access_token()

        # Should have refreshed and returned new token
        assert token == "refreshed_token"
        mock_post.assert_called_once()

    def test_get_valid_access_token_raises_if_no_tokens(self, config):
        """get_valid_access_token raises TokenNotAvailableError if no tokens."""
        manager = TokenManager(config)

        with pytest.raises(TokenNotAvailableError, match="No tokens available"):
            manager.get_valid_access_token()

    def test_is_authorized_true_when_tokens_exist(
        self, config, temp_storage, valid_token_data
    ):
        """is_authorized returns True when tokens exist."""
        temp_storage.save(valid_token_data)

        manager = TokenManager(config, storage=temp_storage)

        assert manager.is_authorized() is True

    def test_is_authorized_false_when_no_tokens(self, config):
        """is_authorized returns False when no tokens."""
        manager = TokenManager(config)

        assert manager.is_authorized() is False

    def test_get_token_status_when_authorized(
        self, config, temp_storage, valid_token_data
    ):
        """get_token_status returns status dict when authorized."""
        temp_storage.save(valid_token_data)

        manager = TokenManager(config, storage=temp_storage)
        status = manager.get_token_status()

        assert status["authorized"] is True
        assert status["expired"] is False
        assert "expires_at" in status
        assert status["expires_in_seconds"] > 0
        assert status["scope"] == "trading market_data"

    def test_get_token_status_when_not_authorized(self, config):
        """get_token_status returns not authorized when no tokens."""
        manager = TokenManager(config)
        status = manager.get_token_status()

        assert status["authorized"] is False
        assert "message" in status

    def test_revoke_deletes_tokens(self, config, temp_storage, valid_token_data):
        """revoke() deletes stored tokens."""
        temp_storage.save(valid_token_data)

        manager = TokenManager(config, storage=temp_storage)
        assert manager.is_authorized() is True

        manager.revoke()

        assert manager.is_authorized() is False
        assert not temp_storage.exists()

    def test_cached_token_used_on_subsequent_calls(
        self, config, temp_storage, valid_token_data
    ):
        """Token is cached after first load."""
        temp_storage.save(valid_token_data)

        manager = TokenManager(config, storage=temp_storage)

        # First call loads from storage
        token1 = manager.get_valid_access_token()

        # Delete the file
        temp_storage.delete()

        # Second call should use cache (not fail even though file deleted)
        token2 = manager.get_valid_access_token()

        assert token1 == token2 == "valid_access_token"
