"""Tests for OAuth configuration module."""

import os
from unittest import mock

import pytest

from src.oauth.config import SchwabOAuthConfig
from src.oauth.exceptions import ConfigurationError


class TestSchwabOAuthConfig:
    """Tests for SchwabOAuthConfig class."""

    def test_config_with_required_params(self):
        """Config can be created with just required parameters."""
        config = SchwabOAuthConfig(
            client_id="test_client_id", client_secret="test_client_secret"
        )

        assert config.client_id == "test_client_id"
        assert config.client_secret == "test_client_secret"
        assert config.callback_host == "dirtydata.ai"
        assert config.callback_port == 8443
        assert config.callback_path == "/oauth/callback"
        assert config.token_file == "/workspaces/options_income/.schwab_tokens.json"
        assert config.refresh_buffer_seconds == 300

    def test_config_with_all_params(self):
        """Config can be created with all parameters."""
        config = SchwabOAuthConfig(
            client_id="test_id",
            client_secret="test_secret",
            callback_host="example.com",
            callback_port=9000,
            callback_path="/custom/callback",
            token_file="/custom/path/tokens.json",
            refresh_buffer_seconds=600,
        )

        assert config.client_id == "test_id"
        assert config.client_secret == "test_secret"
        assert config.callback_host == "example.com"
        assert config.callback_port == 9000
        assert config.callback_path == "/custom/callback"
        assert config.token_file == "/custom/path/tokens.json"
        assert config.refresh_buffer_seconds == 600

    def test_config_validates_empty_client_id(self):
        """Config raises error for empty client_id."""
        with pytest.raises(ConfigurationError, match="client_id cannot be empty"):
            SchwabOAuthConfig(client_id="", client_secret="secret")

    def test_config_validates_empty_client_secret(self):
        """Config raises error for empty client_secret."""
        with pytest.raises(ConfigurationError, match="client_secret cannot be empty"):
            SchwabOAuthConfig(client_id="id", client_secret="")

    def test_config_validates_port_range(self):
        """Config validates callback port is in valid range."""
        with pytest.raises(
            ConfigurationError, match="callback_port must be between 1 and 65535"
        ):
            SchwabOAuthConfig(
                client_id="id", client_secret="secret", callback_port=0
            )

        with pytest.raises(
            ConfigurationError, match="callback_port must be between 1 and 65535"
        ):
            SchwabOAuthConfig(
                client_id="id", client_secret="secret", callback_port=70000
            )

    def test_config_validates_negative_refresh_buffer(self):
        """Config validates refresh_buffer_seconds is non-negative."""
        with pytest.raises(
            ConfigurationError, match="refresh_buffer_seconds cannot be negative"
        ):
            SchwabOAuthConfig(
                client_id="id", client_secret="secret", refresh_buffer_seconds=-1
            )

    def test_callback_url_property(self):
        """callback_url property generates correct URL."""
        config = SchwabOAuthConfig(
            client_id="id",
            client_secret="secret",
            callback_host="example.com",
            callback_port=9000,
            callback_path="/test/path",
        )

        assert config.callback_url == "https://example.com:9000/test/path"

    def test_callback_url_with_defaults(self):
        """callback_url property works with default values."""
        config = SchwabOAuthConfig(client_id="id", client_secret="secret")

        assert config.callback_url == "https://dirtydata.ai:8443/oauth/callback"

    @mock.patch.dict(
        os.environ,
        {
            "SCHWAB_CLIENT_ID": "env_client_id",
            "SCHWAB_CLIENT_SECRET": "env_client_secret",
        },
        clear=False,
    )
    def test_from_env_with_minimal_config(self):
        """from_env loads configuration from environment variables."""
        config = SchwabOAuthConfig.from_env()

        assert config.client_id == "env_client_id"
        assert config.client_secret == "env_client_secret"
        assert config.callback_host == "dirtydata.ai"  # default
        assert config.callback_port == 8443  # default
        assert (
            config.token_file == "/workspaces/options_income/.schwab_tokens.json"
        )  # default

    @mock.patch.dict(
        os.environ,
        {
            "SCHWAB_CLIENT_ID": "env_id",
            "SCHWAB_CLIENT_SECRET": "env_secret",
            "SCHWAB_CALLBACK_HOST": "custom.example.com",
            "SCHWAB_CALLBACK_PORT": "9443",
            "SCHWAB_TOKEN_FILE": "/custom/tokens.json",
        },
        clear=False,
    )
    def test_from_env_with_full_config(self):
        """from_env respects optional environment variables."""
        config = SchwabOAuthConfig.from_env()

        assert config.client_id == "env_id"
        assert config.client_secret == "env_secret"
        assert config.callback_host == "custom.example.com"
        assert config.callback_port == 9443
        assert config.token_file == "/custom/tokens.json"

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_from_env_missing_client_id(self):
        """from_env raises error when CLIENT_ID missing."""
        with pytest.raises(
            ConfigurationError, match="Missing Schwab OAuth credentials"
        ):
            SchwabOAuthConfig.from_env()

    @mock.patch.dict(os.environ, {"SCHWAB_CLIENT_ID": "id"}, clear=True)
    def test_from_env_missing_client_secret(self):
        """from_env raises error when CLIENT_SECRET missing."""
        with pytest.raises(
            ConfigurationError, match="Missing Schwab OAuth credentials"
        ):
            SchwabOAuthConfig.from_env()

    @mock.patch.dict(
        os.environ, {"SCHWAB_CLIENT_ID": "", "SCHWAB_CLIENT_SECRET": ""}, clear=True
    )
    def test_from_env_empty_credentials(self):
        """from_env raises error when credentials are empty strings."""
        with pytest.raises(
            ConfigurationError, match="Missing Schwab OAuth credentials"
        ):
            SchwabOAuthConfig.from_env()

    def test_configuration_error_message_helpful(self):
        """ConfigurationError from from_env includes helpful guidance."""
        with mock.patch.dict(os.environ, {}, clear=True):
            try:
                SchwabOAuthConfig.from_env()
                pytest.fail("Should have raised ConfigurationError")
            except ConfigurationError as e:
                error_message = str(e)
                assert "SCHWAB_CLIENT_ID" in error_message
                assert "SCHWAB_CLIENT_SECRET" in error_message
                assert "developer.schwab.com" in error_message

    def test_ssl_certificate_paths_configurable(self):
        """SSL certificate paths can be customized."""
        config = SchwabOAuthConfig(
            client_id="id",
            client_secret="secret",
            ssl_cert_path="/custom/cert.pem",
            ssl_key_path="/custom/key.pem",
        )

        assert config.ssl_cert_path == "/custom/cert.pem"
        assert config.ssl_key_path == "/custom/key.pem"

    def test_ssl_certificate_paths_defaults(self):
        """SSL certificate paths have sensible defaults."""
        config = SchwabOAuthConfig(client_id="id", client_secret="secret")

        assert "/etc/letsencrypt" in config.ssl_cert_path
        assert "dirtydata.ai" in config.ssl_cert_path
        assert "fullchain.pem" in config.ssl_cert_path
        assert "/etc/letsencrypt" in config.ssl_key_path
        assert "dirtydata.ai" in config.ssl_key_path
        assert "privkey.pem" in config.ssl_key_path
