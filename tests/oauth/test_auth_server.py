"""Tests for OAuth authorization server module."""

import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.oauth.auth_server import (
    AuthorizationResult,
    OAuthCallbackServer,
    run_authorization_flow,
)
from src.oauth.config import SchwabOAuthConfig


class TestAuthorizationResult:
    """Tests for AuthorizationResult dataclass."""

    def test_authorization_result_success(self):
        """AuthorizationResult can represent success."""
        result = AuthorizationResult(success=True, authorization_code="code_123")

        assert result.success is True
        assert result.authorization_code == "code_123"
        assert result.error is None
        assert result.error_description is None

    def test_authorization_result_failure(self):
        """AuthorizationResult can represent failure."""
        result = AuthorizationResult(
            success=False, error="access_denied", error_description="User denied access"
        )

        assert result.success is False
        assert result.authorization_code is None
        assert result.error == "access_denied"
        assert result.error_description == "User denied access"


class TestOAuthCallbackServer:
    """Tests for OAuthCallbackServer class."""

    @pytest.fixture
    def config(self):
        """Create test OAuth config."""
        return SchwabOAuthConfig(
            client_id="test_client_id",
            client_secret="test_client_secret",
            callback_host="localhost",
            callback_port=9443,
            token_file="/tmp/test_tokens.json",
        )

    def test_server_initialization(self, config):
        """OAuthCallbackServer can be initialized."""
        server = OAuthCallbackServer(config)

        assert server.config == config
        assert server.app is not None
        assert server.result is None
        assert server.server is None

    def test_generate_authorization_url(self, config):
        """generate_authorization_url creates correct URL."""
        server = OAuthCallbackServer(config)
        url = server.generate_authorization_url()

        assert url.startswith(config.authorization_url)
        assert "client_id=test_client_id" in url
        assert f"redirect_uri=https%3A%2F%2Flocalhost%3A9443%2Foauth%2Fcallback" in url
        assert "response_type=code" in url

    def test_handle_callback_success(self, config):
        """_handle_callback processes successful callback."""
        server = OAuthCallbackServer(config)

        with server.app.test_request_context("/?code=auth_code_123"):
            response = server._handle_callback()

            assert response.status_code == 200
            assert "text/html" in response.content_type
            assert "Authorization Successful" in response.get_data(as_text=True)
            assert server.result is not None
            assert server.result.success is True
            assert server.result.authorization_code == "auth_code_123"

    def test_handle_callback_with_error(self, config):
        """_handle_callback processes error callback."""
        server = OAuthCallbackServer(config)

        with server.app.test_request_context(
            "/?error=access_denied&error_description=User%20denied"
        ):
            response = server._handle_callback()

            assert response.status_code == 400
            assert "Authorization Failed" in response.get_data(as_text=True)
            assert server.result is not None
            assert server.result.success is False
            assert server.result.error == "access_denied"
            assert "User denied" in server.result.error_description

    def test_handle_callback_missing_code(self, config):
        """_handle_callback handles missing code."""
        server = OAuthCallbackServer(config)

        with server.app.test_request_context("/"):  # No code parameter
            response = server._handle_callback()

            assert response.status_code == 400
            assert "Authorization Failed" in response.get_data(as_text=True)
            assert server.result is not None
            assert server.result.success is False
            assert server.result.error == "missing_code"

    def test_handle_status(self, config):
        """_handle_status returns status JSON."""
        server = OAuthCallbackServer(config)

        with server.app.test_request_context("/oauth/status"):
            response = server._handle_status()

            assert response.status_code == 200
            assert "application/json" in response.content_type
            data = response.get_data(as_text=True)
            assert "running" in data
            assert "oauth_callback" in data

    @mock.patch("pathlib.Path")
    def test_start_raises_if_cert_not_found(self, mock_path, config):
        """start() raises FileNotFoundError if SSL cert missing."""
        # Mock Path to return non-existent files
        mock_cert = mock.Mock()
        mock_cert.exists.return_value = False
        mock_path.return_value = mock_cert

        server = OAuthCallbackServer(config)

        with pytest.raises(FileNotFoundError, match="SSL certificate not found"):
            server.start()

    @mock.patch("pathlib.Path")
    def test_start_raises_if_key_not_found(self, mock_path, config):
        """start() raises FileNotFoundError if SSL key missing."""
        # Mock Path: cert exists, key doesn't
        def path_side_effect(path_str):
            mock_file = mock.Mock()
            if "fullchain" in str(path_str):
                mock_file.exists.return_value = True
            else:
                mock_file.exists.return_value = False
            return mock_file

        mock_path.side_effect = path_side_effect

        server = OAuthCallbackServer(config)

        with pytest.raises(FileNotFoundError, match="SSL key not found"):
            server.start()

    def test_wait_for_callback_returns_result_on_success(self, config):
        """wait_for_callback returns result when received."""
        server = OAuthCallbackServer(config)

        # Simulate receiving a callback
        server.result = AuthorizationResult(success=True, authorization_code="code_123")
        server._shutdown_event.set()

        result = server.wait_for_callback(timeout=1)

        assert result.success is True
        assert result.authorization_code == "code_123"

    def test_wait_for_callback_times_out(self, config):
        """wait_for_callback returns timeout result if no callback."""
        server = OAuthCallbackServer(config)

        # Don't set shutdown event, so it times out
        result = server.wait_for_callback(timeout=1)

        assert result.success is False
        assert result.error == "timeout"
        assert "No callback received" in result.error_description

    def test_stop_sets_shutdown_event(self, config):
        """stop() sets shutdown event."""
        server = OAuthCallbackServer(config)
        server.server = mock.Mock()  # Simulate running server

        assert not server._shutdown_event.is_set()

        server.stop()

        assert server._shutdown_event.is_set()


class TestRunAuthorizationFlow:
    """Tests for run_authorization_flow function."""

    @pytest.fixture
    def config(self):
        """Create test OAuth config with temporary cert files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create dummy cert files
            cert_file = Path(tmpdir) / "cert.pem"
            key_file = Path(tmpdir) / "key.pem"
            cert_file.write_text("dummy cert")
            key_file.write_text("dummy key")

            yield SchwabOAuthConfig(
                client_id="test_client_id",
                client_secret="test_client_secret",
                callback_host="localhost",
                callback_port=9443,
                ssl_cert_path=str(cert_file),
                ssl_key_path=str(key_file),
                token_file="/tmp/test_tokens.json",
            )

    @mock.patch("src.oauth.auth_server.webbrowser")
    @mock.patch.object(OAuthCallbackServer, "start")
    @mock.patch.object(OAuthCallbackServer, "wait_for_callback")
    @mock.patch.object(OAuthCallbackServer, "stop")
    def test_run_authorization_flow_success(
        self, mock_stop, mock_wait, mock_start, mock_browser, config
    ):
        """run_authorization_flow completes successfully."""
        # Mock successful callback
        mock_wait.return_value = AuthorizationResult(
            success=True, authorization_code="code_123"
        )

        result = run_authorization_flow(config, open_browser=True, timeout=300)

        assert result.success is True
        assert result.authorization_code == "code_123"
        mock_start.assert_called_once()
        mock_wait.assert_called_once_with(300)
        mock_stop.assert_called_once()
        mock_browser.open.assert_called_once()

    @mock.patch("src.oauth.auth_server.webbrowser")
    @mock.patch.object(OAuthCallbackServer, "start")
    @mock.patch.object(OAuthCallbackServer, "wait_for_callback")
    @mock.patch.object(OAuthCallbackServer, "stop")
    def test_run_authorization_flow_no_browser(
        self, mock_stop, mock_wait, mock_start, mock_browser, config
    ):
        """run_authorization_flow works without opening browser."""
        mock_wait.return_value = AuthorizationResult(
            success=True, authorization_code="code_123"
        )

        result = run_authorization_flow(config, open_browser=False, timeout=300)

        assert result.success is True
        mock_browser.open.assert_not_called()

    @mock.patch("src.oauth.auth_server.webbrowser")
    @mock.patch.object(OAuthCallbackServer, "start")
    @mock.patch.object(OAuthCallbackServer, "wait_for_callback")
    @mock.patch.object(OAuthCallbackServer, "stop")
    def test_run_authorization_flow_handles_error(
        self, mock_stop, mock_wait, mock_start, mock_browser, config
    ):
        """run_authorization_flow handles authorization error."""
        mock_wait.return_value = AuthorizationResult(
            success=False, error="access_denied", error_description="User denied"
        )

        result = run_authorization_flow(config, open_browser=True, timeout=300)

        assert result.success is False
        assert result.error == "access_denied"
        mock_stop.assert_called_once()  # Server still stopped

    @mock.patch("src.oauth.auth_server.webbrowser")
    @mock.patch.object(OAuthCallbackServer, "start")
    @mock.patch.object(OAuthCallbackServer, "wait_for_callback")
    @mock.patch.object(OAuthCallbackServer, "stop")
    def test_run_authorization_flow_handles_timeout(
        self, mock_stop, mock_wait, mock_start, mock_browser, config
    ):
        """run_authorization_flow handles timeout."""
        mock_wait.return_value = AuthorizationResult(
            success=False,
            error="timeout",
            error_description="No callback received within 300 seconds",
        )

        result = run_authorization_flow(config, open_browser=True, timeout=300)

        assert result.success is False
        assert result.error == "timeout"
        mock_stop.assert_called_once()

    @mock.patch("src.oauth.auth_server.webbrowser")
    @mock.patch.object(OAuthCallbackServer, "start")
    @mock.patch.object(OAuthCallbackServer, "wait_for_callback")
    @mock.patch.object(OAuthCallbackServer, "stop")
    def test_run_authorization_flow_stops_server_on_exception(
        self, mock_stop, mock_wait, mock_start, mock_browser, config
    ):
        """run_authorization_flow stops server even if exception occurs."""
        mock_wait.side_effect = Exception("Unexpected error")

        with pytest.raises(Exception, match="Unexpected error"):
            run_authorization_flow(config, open_browser=True, timeout=300)

        # Server should still be stopped
        mock_stop.assert_called_once()
