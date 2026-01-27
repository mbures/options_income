"""Tests for Schwab API client."""

from unittest import mock

import pytest
import requests

from src.oauth.coordinator import OAuthCoordinator
from src.oauth.exceptions import TokenNotAvailableError
from src.schwab.client import SchwabClient
from src.schwab.exceptions import (
    SchwabAPIError,
    SchwabAuthenticationError,
    SchwabInvalidSymbolError,
    SchwabRateLimitError,
)


class TestSchwabClient:
    """Tests for SchwabClient class."""

    @pytest.fixture
    def mock_oauth(self):
        """Create mock OAuth coordinator."""
        oauth = mock.Mock(spec=OAuthCoordinator)
        oauth.get_authorization_header.return_value = {
            "Authorization": "Bearer test_token_123"
        }
        return oauth

    @pytest.fixture
    def client(self, mock_oauth):
        """Create Schwab client with mocked OAuth."""
        return SchwabClient(oauth_coordinator=mock_oauth, max_retries=2, retry_delay=0.1)

    def test_client_initialization(self, mock_oauth):
        """SchwabClient initializes correctly."""
        client = SchwabClient(oauth_coordinator=mock_oauth)

        assert client.oauth == mock_oauth
        assert client.max_retries == 3
        assert client.retry_delay == 1.0
        assert client.session is not None

    def test_client_creates_default_oauth_if_not_provided(self):
        """SchwabClient creates default OAuth coordinator if not provided."""
        with mock.patch("src.schwab.client.OAuthCoordinator") as mock_coordinator_class:
            mock_instance = mock.Mock()
            mock_coordinator_class.return_value = mock_instance

            client = SchwabClient()

            mock_coordinator_class.assert_called_once()
            assert client.oauth == mock_instance

    def test_get_full_url_constructs_correct_url(self, client):
        """_get_full_url constructs correct API URLs."""
        # With leading slash
        url = client._get_full_url("/marketdata/quotes")
        assert url == "https://api.schwabapi.com/v1/marketdata/quotes"

        # Without leading slash
        url = client._get_full_url("marketdata/quotes")
        assert url == "https://api.schwabapi.com/v1/marketdata/quotes"

        # With version already included
        url = client._get_full_url("/v1/marketdata/quotes")
        assert url == "https://api.schwabapi.com/v1/marketdata/quotes"

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_request_success(self, mock_request, client):
        """_request makes successful API call."""
        # Mock successful response
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {"data": "test"}
        mock_request.return_value = mock_response

        response = client._request("GET", "/marketdata/quotes", params={"symbol": "AAPL"})

        assert response.status_code == 200
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer test_token_123"
        assert call_kwargs["params"] == {"symbol": "AAPL"}

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_request_raises_on_401(self, mock_request, client):
        """_request raises SchwabAuthenticationError on 401."""
        mock_response = mock.Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_request.return_value = mock_response

        with pytest.raises(SchwabAuthenticationError, match="Authentication failed"):
            client._request("GET", "/marketdata/quotes")

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_request_raises_on_429(self, mock_request, client):
        """_request raises SchwabRateLimitError on 429."""
        mock_response = mock.Mock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_request.return_value = mock_response

        with pytest.raises(SchwabRateLimitError, match="rate limit exceeded"):
            client._request("GET", "/marketdata/quotes")

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_request_raises_on_404(self, mock_request, client):
        """_request raises SchwabInvalidSymbolError on 404."""
        mock_response = mock.Mock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        mock_request.return_value = mock_response

        with pytest.raises(SchwabInvalidSymbolError, match="Resource not found"):
            client._request("GET", "/marketdata/quotes")

    @mock.patch("src.schwab.client.requests.Session.request")
    @mock.patch("src.schwab.client.time.sleep")  # Mock sleep to speed up test
    def test_request_retries_on_500(self, mock_sleep, mock_request, client):
        """_request retries on 500 server error."""
        # First two calls fail with 500, third succeeds
        mock_response_500 = mock.Mock()
        mock_response_500.status_code = 500
        mock_response_500.text = "Internal server error"

        mock_response_200 = mock.Mock()
        mock_response_200.status_code = 200
        mock_response_200.ok = True
        mock_response_200.json.return_value = {"data": "success"}

        mock_request.side_effect = [mock_response_500, mock_response_500, mock_response_200]

        response = client._request("GET", "/marketdata/quotes")

        assert response.status_code == 200
        assert mock_request.call_count == 3
        assert mock_sleep.call_count == 2  # Slept twice (after first two failures)

    @mock.patch("src.schwab.client.requests.Session.request")
    @mock.patch("src.schwab.client.time.sleep")
    def test_request_fails_after_max_retries(self, mock_sleep, mock_request, client):
        """_request fails after max retries on 500."""
        mock_response = mock.Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_request.return_value = mock_response

        with pytest.raises(SchwabAPIError, match="server error"):
            client._request("GET", "/marketdata/quotes")

        # Should try initial + 2 retries = 3 total
        assert mock_request.call_count == 3

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_request_handles_timeout_with_retry(self, mock_request, client):
        """_request retries on timeout."""
        # First call times out, second succeeds
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {"data": "success"}

        mock_request.side_effect = [requests.exceptions.Timeout(), mock_response]

        with mock.patch("src.schwab.client.time.sleep"):
            response = client._request("GET", "/marketdata/quotes")

        assert response.status_code == 200
        assert mock_request.call_count == 2

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_request_handles_network_error_with_retry(self, mock_request, client):
        """_request retries on network error."""
        # First call fails with network error, second succeeds
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {"data": "success"}

        mock_request.side_effect = [
            requests.exceptions.ConnectionError("Connection failed"),
            mock_response,
        ]

        with mock.patch("src.schwab.client.time.sleep"):
            response = client._request("GET", "/marketdata/quotes")

        assert response.status_code == 200
        assert mock_request.call_count == 2

    def test_request_raises_when_not_authorized(self, client):
        """_request raises SchwabAuthenticationError when no OAuth tokens."""
        client.oauth.get_authorization_header.side_effect = TokenNotAvailableError(
            "No tokens"
        )

        with pytest.raises(SchwabAuthenticationError, match="No valid OAuth tokens"):
            client._request("GET", "/marketdata/quotes")

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_method(self, mock_request, client):
        """get() method works correctly."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {"symbol": "AAPL", "price": 150.0}
        mock_request.return_value = mock_response

        result = client.get("/marketdata/quotes", params={"symbol": "AAPL"})

        assert result == {"symbol": "AAPL", "price": 150.0}
        mock_request.assert_called_once()

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_post_method(self, mock_request, client):
        """post() method works correctly."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {"success": True}
        mock_request.return_value = mock_response

        result = client.post("/orders", json_data={"symbol": "AAPL", "quantity": 100})

        assert result == {"success": True}
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs["json"] == {"symbol": "AAPL", "quantity": 100}

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_exponential_backoff_timing(self, mock_request, client):
        """Retry delay increases exponentially."""
        mock_response = mock.Mock()
        mock_response.status_code = 500
        mock_response.text = "Error"
        mock_request.return_value = mock_response

        with mock.patch("src.schwab.client.time.sleep") as mock_sleep:
            with pytest.raises(SchwabAPIError):
                client._request("GET", "/test")

            # Check exponential backoff: 0.1s, 0.2s
            calls = mock_sleep.call_args_list
            assert len(calls) == 2
            assert calls[0][0][0] == 0.1  # First retry: 0.1 * 2^0
            assert calls[1][0][0] == 0.2  # Second retry: 0.1 * 2^1


class TestSchwabClientPriceHistory:
    """Tests for SchwabClient.get_price_history() method."""

    @pytest.fixture
    def mock_oauth(self):
        """Create mock OAuth coordinator."""
        oauth = mock.Mock(spec=OAuthCoordinator)
        oauth.get_authorization_header.return_value = {
            "Authorization": "Bearer test_token_123"
        }
        return oauth

    @pytest.fixture
    def client(self, mock_oauth):
        """Create Schwab client with mocked OAuth and no cache."""
        return SchwabClient(
            oauth_coordinator=mock_oauth,
            max_retries=2,
            retry_delay=0.1,
            enable_cache=False,
        )

    @pytest.fixture
    def mock_price_history_response(self):
        """Create mock Schwab price history response."""
        return {
            "symbol": "AAPL",
            "empty": False,
            "candles": [
                {
                    "open": 150.0,
                    "high": 152.5,
                    "low": 149.0,
                    "close": 151.0,
                    "volume": 1000000,
                    "datetime": 1704067200000,  # 2024-01-01
                },
                {
                    "open": 151.0,
                    "high": 153.0,
                    "low": 150.5,
                    "close": 152.5,
                    "volume": 1100000,
                    "datetime": 1704153600000,  # 2024-01-02
                },
                {
                    "open": 152.5,
                    "high": 154.0,
                    "low": 151.0,
                    "close": 153.0,
                    "volume": 1200000,
                    "datetime": 1704240000000,  # 2024-01-03
                },
            ],
        }

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_price_history_success(self, mock_request, client, mock_price_history_response):
        """get_price_history returns PriceData on successful API call."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = mock_price_history_response
        mock_request.return_value = mock_response

        price_data = client.get_price_history("AAPL")

        # Verify PriceData structure
        assert len(price_data.dates) == 3
        assert len(price_data.opens) == 3
        assert len(price_data.highs) == 3
        assert len(price_data.lows) == 3
        assert len(price_data.closes) == 3
        assert len(price_data.volumes) == 3

        # Verify data values
        assert price_data.opens[0] == 150.0
        assert price_data.closes[0] == 151.0
        assert price_data.highs[1] == 153.0
        assert price_data.lows[2] == 151.0
        assert price_data.volumes[0] == 1000000

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_price_history_date_parsing(self, mock_request, client, mock_price_history_response):
        """get_price_history correctly parses timestamps to date strings."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = mock_price_history_response
        mock_request.return_value = mock_response

        price_data = client.get_price_history("AAPL")

        # Dates should be in YYYY-MM-DD format
        assert all("-" in d for d in price_data.dates)
        assert all(len(d) == 10 for d in price_data.dates)

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_price_history_normalizes_symbol(self, mock_request, client, mock_price_history_response):
        """get_price_history normalizes symbol to uppercase."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = mock_price_history_response
        mock_request.return_value = mock_response

        client.get_price_history("aapl")

        # Check the API was called with uppercase symbol in params
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs["params"]["symbol"] == "AAPL"

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_price_history_default_params(self, mock_request, client, mock_price_history_response):
        """get_price_history uses correct default parameters."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = mock_price_history_response
        mock_request.return_value = mock_response

        client.get_price_history("AAPL")

        call_kwargs = mock_request.call_args[1]
        params = call_kwargs["params"]
        assert params["periodType"] == "month"
        assert params["period"] == 3
        assert params["frequencyType"] == "daily"
        assert params["frequency"] == 1

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_price_history_custom_params(self, mock_request, client, mock_price_history_response):
        """get_price_history accepts custom parameters."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = mock_price_history_response
        mock_request.return_value = mock_response

        client.get_price_history(
            "AAPL",
            period_type="year",
            period=1,
            frequency_type="weekly",
            frequency=1,
        )

        call_kwargs = mock_request.call_args[1]
        params = call_kwargs["params"]
        assert params["periodType"] == "year"
        assert params["period"] == 1
        assert params["frequencyType"] == "weekly"

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_price_history_empty_response(self, mock_request, client):
        """get_price_history raises error on empty candles."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {
            "symbol": "INVALID",
            "empty": True,
            "candles": [],
        }
        mock_request.return_value = mock_response

        with pytest.raises(SchwabAPIError, match="No price data returned"):
            client.get_price_history("INVALID")

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_price_history_invalid_symbol(self, mock_request, client):
        """get_price_history raises error on 404."""
        mock_response = mock.Mock()
        mock_response.status_code = 404
        mock_response.text = "Symbol not found"
        mock_request.return_value = mock_response

        with pytest.raises(SchwabInvalidSymbolError):
            client.get_price_history("INVALID123")

    def test_get_price_history_uses_cache(self, mock_oauth, mock_price_history_response):
        """get_price_history uses cache when enabled."""
        client = SchwabClient(
            oauth_coordinator=mock_oauth,
            enable_cache=True,
        )

        with mock.patch("src.schwab.client.requests.Session.request") as mock_request:
            mock_response = mock.Mock()
            mock_response.status_code = 200
            mock_response.ok = True
            mock_response.json.return_value = mock_price_history_response
            mock_request.return_value = mock_response

            # First call - should hit API
            client.get_price_history("AAPL")
            assert mock_request.call_count == 1

            # Second call - should use cache
            client.get_price_history("AAPL")
            assert mock_request.call_count == 1  # No additional API call
