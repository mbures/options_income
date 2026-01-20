"""Unit tests for Finnhub API client."""

import contextlib
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from src.config import FinnhubConfig
from src.finnhub_client import FinnhubAPIError, FinnhubClient


class TestFinnhubClient:
    """Test suite for FinnhubClient class."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return FinnhubConfig(api_key="test_api_key", timeout=5, max_retries=2, retry_delay=0.1)

    @pytest.fixture
    def client(self, config):
        """Create test client."""
        return FinnhubClient(config)

    def test_client_initialization(self, client, config):
        """Test client initialization."""
        assert client.config == config
        assert client.session is not None
        assert client.session.headers["Accept"] == "application/json"
        assert "User-Agent" in client.session.headers

    def test_get_option_chain_success(self, client, config):
        """Test successful option chain retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "strike": 10.0,
                    "expirationDate": "2026-01-16",
                    "type": "Call",
                    "bid": 1.25,
                    "ask": 1.30,
                }
            ]
        }

        with patch.object(client, "_make_request_with_retry", return_value=mock_response):
            result = client.get_option_chain("F")

        assert "data" in result
        assert len(result["data"]) == 1

    def test_get_option_chain_invalid_symbol_empty(self, client):
        """Test that empty symbol raises ValueError."""
        with pytest.raises(ValueError, match="Invalid symbol"):
            client.get_option_chain("")

    def test_get_option_chain_invalid_symbol_none(self, client):
        """Test that None symbol raises ValueError."""
        with pytest.raises(ValueError, match="Invalid symbol"):
            client.get_option_chain(None)

    def test_get_option_chain_invalid_symbol_non_alnum(self, client):
        """Test that non-alphanumeric symbol raises ValueError."""
        with pytest.raises(ValueError, match="Symbol must be alphanumeric"):
            client.get_option_chain("F@#$")

    def test_get_option_chain_symbol_normalization(self, client):
        """Test that symbol is normalized to uppercase."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}

        with patch.object(
            client, "_make_request_with_retry", return_value=mock_response
        ) as mock_request:
            client.get_option_chain("  aapl  ")

            # Check that the request was made with normalized symbol
            call_args = mock_request.call_args
            params = call_args[0][1]
            assert params["symbol"] == "AAPL"

    def test_get_option_chain_401_unauthorized(self, client):
        """Test handling of 401 authentication error."""
        mock_response = Mock()
        mock_response.status_code = 401

        with patch.object(client, "_make_request_with_retry", return_value=mock_response):
            with pytest.raises(FinnhubAPIError, match="Authentication failed"):
                client.get_option_chain("F")

    def test_get_option_chain_429_rate_limit(self, client):
        """Test handling of 429 rate limit error."""
        mock_response = Mock()
        mock_response.status_code = 429

        with patch.object(client, "_make_request_with_retry", return_value=mock_response):
            with pytest.raises(FinnhubAPIError, match="Rate limit exceeded"):
                client.get_option_chain("F")

    def test_get_option_chain_500_server_error(self, client):
        """Test handling of 500 server error."""
        mock_response = Mock()
        mock_response.status_code = 500

        with patch.object(client, "_make_request_with_retry", return_value=mock_response):
            with pytest.raises(FinnhubAPIError, match="server error"):
                client.get_option_chain("F")

    def test_get_option_chain_timeout(self, client):
        """Test handling of request timeout."""
        with (
            patch.object(
                client,
                "_make_request_with_retry",
                side_effect=requests.exceptions.Timeout("Timeout"),
            ),
            pytest.raises(FinnhubAPIError, match="Request timeout"),
        ):
            client.get_option_chain("F")

    def test_get_option_chain_connection_error(self, client):
        """Test handling of connection error."""
        with (
            patch.object(
                client,
                "_make_request_with_retry",
                side_effect=requests.exceptions.ConnectionError("Connection failed"),
            ),
            pytest.raises(FinnhubAPIError, match="Connection error"),
        ):
            client.get_option_chain("F")

    def test_get_option_chain_invalid_json(self, client):
        """Test handling of invalid JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status = Mock()

        with patch.object(client, "_make_request_with_retry", return_value=mock_response):
            with pytest.raises(FinnhubAPIError, match="Invalid JSON response"):
                client.get_option_chain("F")

    def test_make_request_with_retry_success_first_attempt(self, client):
        """Test successful request on first attempt."""
        mock_response = Mock()
        mock_response.status_code = 200

        with patch.object(client.session, "get", return_value=mock_response):
            result = client._make_request_with_retry("https://test.com", {"param": "value"})

        assert result == mock_response

    def test_make_request_with_retry_success_after_retry(self, client):
        """Test successful request after retry."""
        mock_response_fail = Mock()
        mock_response_fail.side_effect = requests.exceptions.Timeout()

        mock_response_success = Mock()
        mock_response_success.status_code = 200

        with patch.object(
            client.session,
            "get",
            side_effect=[requests.exceptions.Timeout(), mock_response_success],
        ):
            result = client._make_request_with_retry("https://test.com", {"param": "value"})

        assert result == mock_response_success

    def test_make_request_with_retry_max_retries_exceeded(self, client):
        """Test that max retries is respected."""
        with (
            patch.object(client.session, "get", side_effect=requests.exceptions.Timeout()),
            pytest.raises(requests.exceptions.Timeout),
        ):
            client._make_request_with_retry("https://test.com", {"param": "value"})

    def test_make_request_with_retry_exponential_backoff(self, client):
        """Test exponential backoff timing."""
        with (
            patch.object(client.session, "get", side_effect=requests.exceptions.Timeout()),
            patch("time.sleep") as mock_sleep,
        ):
            with contextlib.suppress(requests.exceptions.Timeout):
                client._make_request_with_retry("https://test.com", {"param": "value"})

            # Should have called sleep with exponential backoff
            # First retry: 0.1 * 2^0 = 0.1
            # We configured max_retries=2, so only 1 sleep call
            calls = mock_sleep.call_args_list
            assert len(calls) >= 1
            assert calls[0][0][0] == 0.1

    def test_close(self, client):
        """Test client cleanup."""
        mock_session = Mock()
        client.session = mock_session

        client.close()

        mock_session.close.assert_called_once()

    def test_context_manager(self, config):
        """Test client as context manager."""
        with FinnhubClient(config) as client:
            assert client is not None
            assert client.session is not None
            mock_close = Mock()
            client.close = mock_close

        # Close should be called on exit
        mock_close.assert_called_once()

    def test_request_includes_api_key(self, client):
        """Test that API key is included in request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch.object(client.session, "get", return_value=mock_response) as mock_get:
            client.get_option_chain("F")

            # Verify API key was included in params
            call_args = mock_get.call_args
            params = call_args[1]["params"]
            assert params["token"] == "test_api_key"

    def test_request_url_construction(self, client):
        """Test correct URL construction."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch.object(client.session, "get", return_value=mock_response) as mock_get:
            client.get_option_chain("F")

            # Verify URL
            call_args = mock_get.call_args
            url = call_args[0][0]
            assert url == "https://finnhub.io/api/v1/stock/option-chain"
