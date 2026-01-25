"""Tests for OAuth coordinator module."""

import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.oauth.coordinator import OAuthCoordinator
from src.oauth.auth_server import AuthorizationResult
from src.oauth.config import SchwabOAuthConfig
from src.oauth.exceptions import TokenNotAvailableError
from src.oauth.token_storage import TokenData


class TestOAuthCoordinator:
    """Tests for OAuthCoordinator class."""

    @pytest.fixture
    def config(self):
        """Create test OAuth config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield SchwabOAuthConfig(
                client_id="test_client_id",
                client_secret="test_client_secret",
                callback_host="localhost",
                callback_port=9443,
                token_file=str(Path(tmpdir) / "tokens.json"),
            )

    def test_coordinator_initialization(self, config):
        """OAuthCoordinator initializes correctly."""
        coordinator = OAuthCoordinator(config)

        assert coordinator.config == config
        assert coordinator.storage is not None
        assert coordinator.token_manager is not None

    @mock.patch.dict("os.environ", {"SCHWAB_CLIENT_ID": "env_id", "SCHWAB_CLIENT_SECRET": "env_secret"})
    def test_coordinator_loads_config_from_env(self):
        """OAuthCoordinator loads config from environment if not provided."""
        coordinator = OAuthCoordinator()

        assert coordinator.config.client_id == "env_id"
        assert coordinator.config.client_secret == "env_secret"

    def test_ensure_authorized_returns_true_when_already_authorized(self, config):
        """ensure_authorized returns True if already authorized."""
        coordinator = OAuthCoordinator(config)

        # Mock token manager to indicate authorized
        coordinator.token_manager.is_authorized = mock.Mock(return_value=True)

        result = coordinator.ensure_authorized()

        assert result is True
        coordinator.token_manager.is_authorized.assert_called_once()

    @mock.patch("src.oauth.coordinator.run_authorization_flow")
    def test_ensure_authorized_runs_flow_when_not_authorized(self, mock_run_flow, config):
        """ensure_authorized runs authorization flow if not authorized."""
        coordinator = OAuthCoordinator(config)

        # Mock token manager to indicate not authorized initially
        coordinator.token_manager.is_authorized = mock.Mock(return_value=False)

        # Mock successful authorization flow
        mock_run_flow.return_value = AuthorizationResult(
            success=True, authorization_code="code_123"
        )
        coordinator.token_manager.exchange_code_for_tokens = mock.Mock()

        result = coordinator.ensure_authorized(auto_open_browser=True)

        assert result is True
        mock_run_flow.assert_called_once_with(config, open_browser=True, timeout=300)
        coordinator.token_manager.exchange_code_for_tokens.assert_called_once_with("code_123")

    @mock.patch("src.oauth.coordinator.run_authorization_flow")
    def test_ensure_authorized_returns_false_on_flow_failure(self, mock_run_flow, config):
        """ensure_authorized returns False if authorization flow fails."""
        coordinator = OAuthCoordinator(config)
        coordinator.token_manager.is_authorized = mock.Mock(return_value=False)

        # Mock failed authorization
        mock_run_flow.return_value = AuthorizationResult(
            success=False, error="access_denied", error_description="User denied"
        )

        result = coordinator.ensure_authorized()

        assert result is False

    @mock.patch("src.oauth.coordinator.run_authorization_flow")
    def test_run_authorization_flow_success(self, mock_run_flow, config):
        """run_authorization_flow completes successfully."""
        coordinator = OAuthCoordinator(config)

        # Mock successful flow
        mock_run_flow.return_value = AuthorizationResult(
            success=True, authorization_code="code_123"
        )
        coordinator.token_manager.exchange_code_for_tokens = mock.Mock()

        result = coordinator.run_authorization_flow(open_browser=True)

        assert result is True
        mock_run_flow.assert_called_once_with(config, open_browser=True, timeout=300)
        coordinator.token_manager.exchange_code_for_tokens.assert_called_once_with("code_123")

    @mock.patch("src.oauth.coordinator.run_authorization_flow")
    def test_run_authorization_flow_handles_authorization_error(self, mock_run_flow, config):
        """run_authorization_flow handles authorization error."""
        coordinator = OAuthCoordinator(config)

        mock_run_flow.return_value = AuthorizationResult(
            success=False, error="invalid_request", error_description="Bad request"
        )

        result = coordinator.run_authorization_flow()

        assert result is False

    @mock.patch("src.oauth.coordinator.run_authorization_flow")
    def test_run_authorization_flow_handles_token_exchange_error(self, mock_run_flow, config):
        """run_authorization_flow handles token exchange error."""
        coordinator = OAuthCoordinator(config)

        mock_run_flow.return_value = AuthorizationResult(
            success=True, authorization_code="code_123"
        )
        coordinator.token_manager.exchange_code_for_tokens = mock.Mock(
            side_effect=Exception("Token exchange failed")
        )

        result = coordinator.run_authorization_flow()

        assert result is False

    def test_get_access_token_returns_valid_token(self, config):
        """get_access_token returns valid access token."""
        coordinator = OAuthCoordinator(config)

        # Mock token manager
        coordinator.token_manager.get_valid_access_token = mock.Mock(
            return_value="valid_access_token_123"
        )

        token = coordinator.get_access_token()

        assert token == "valid_access_token_123"
        coordinator.token_manager.get_valid_access_token.assert_called_once()

    def test_get_access_token_raises_if_not_authorized(self, config):
        """get_access_token raises TokenNotAvailableError if not authorized."""
        coordinator = OAuthCoordinator(config)

        # Mock token manager to raise exception
        coordinator.token_manager.get_valid_access_token = mock.Mock(
            side_effect=TokenNotAvailableError("No tokens available")
        )

        with pytest.raises(TokenNotAvailableError, match="No tokens available"):
            coordinator.get_access_token()

    def test_get_authorization_header_returns_correct_format(self, config):
        """get_authorization_header returns correctly formatted header."""
        coordinator = OAuthCoordinator(config)

        coordinator.token_manager.get_valid_access_token = mock.Mock(
            return_value="token_abc_123"
        )

        header = coordinator.get_authorization_header()

        assert header == {"Authorization": "Bearer token_abc_123"}

    def test_is_authorized_returns_true_when_authorized(self, config):
        """is_authorized returns True when authorized."""
        coordinator = OAuthCoordinator(config)

        coordinator.token_manager.is_authorized = mock.Mock(return_value=True)

        assert coordinator.is_authorized() is True

    def test_is_authorized_returns_false_when_not_authorized(self, config):
        """is_authorized returns False when not authorized."""
        coordinator = OAuthCoordinator(config)

        coordinator.token_manager.is_authorized = mock.Mock(return_value=False)

        assert coordinator.is_authorized() is False

    def test_get_status_returns_authorized_status(self, config):
        """get_status returns status information when authorized."""
        coordinator = OAuthCoordinator(config)

        expected_status = {
            "authorized": True,
            "expired": False,
            "expires_at": "2026-01-26T12:00:00+00:00",
            "expires_in_seconds": 3600,
            "scope": "api",
        }
        coordinator.token_manager.get_token_status = mock.Mock(return_value=expected_status)

        status = coordinator.get_status()

        assert status == expected_status

    def test_get_status_returns_not_authorized_status(self, config):
        """get_status returns status information when not authorized."""
        coordinator = OAuthCoordinator(config)

        expected_status = {"authorized": False, "message": "No tokens stored"}
        coordinator.token_manager.get_token_status = mock.Mock(return_value=expected_status)

        status = coordinator.get_status()

        assert status == expected_status

    def test_revoke_deletes_tokens(self, config):
        """revoke deletes stored tokens."""
        coordinator = OAuthCoordinator(config)

        coordinator.token_manager.revoke = mock.Mock()

        coordinator.revoke()

        coordinator.token_manager.revoke.assert_called_once()

    @mock.patch("src.oauth.coordinator.run_authorization_flow")
    def test_full_authorization_workflow(self, mock_run_flow, config):
        """Complete authorization workflow from start to finish."""
        coordinator = OAuthCoordinator(config)

        # Initially not authorized
        assert coordinator.is_authorized() is False

        # Mock successful authorization
        mock_run_flow.return_value = AuthorizationResult(
            success=True, authorization_code="test_code"
        )

        # Mock token data
        token_data = TokenData(
            access_token="access_123",
            refresh_token="refresh_456",
            token_type="Bearer",
            expires_in=1800,
            scope="api",
            issued_at="2026-01-25T12:00:00+00:00",
        )
        coordinator.token_manager.exchange_code_for_tokens = mock.Mock(return_value=token_data)
        coordinator.token_manager.is_authorized = mock.Mock(return_value=True)
        coordinator.token_manager.get_valid_access_token = mock.Mock(
            return_value="access_123"
        )

        # Run authorization
        success = coordinator.ensure_authorized()
        assert success is True

        # Now authorized
        assert coordinator.is_authorized() is True

        # Can get access token
        token = coordinator.get_access_token()
        assert token == "access_123"

        # Can get authorization header
        header = coordinator.get_authorization_header()
        assert header["Authorization"] == "Bearer access_123"

    def test_ensure_authorized_respects_auto_open_browser_flag(self, config):
        """ensure_authorized passes auto_open_browser flag correctly."""
        coordinator = OAuthCoordinator(config)
        coordinator.token_manager.is_authorized = mock.Mock(return_value=False)

        with mock.patch.object(coordinator, "run_authorization_flow") as mock_run:
            mock_run.return_value = True

            # Test with auto_open_browser=False
            coordinator.ensure_authorized(auto_open_browser=False)
            mock_run.assert_called_once_with(False)

            mock_run.reset_mock()

            # Test with auto_open_browser=True (default)
            coordinator.ensure_authorized(auto_open_browser=True)
            mock_run.assert_called_once_with(True)
