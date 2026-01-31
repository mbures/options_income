"""Tests for Schwab market data endpoints."""

from datetime import datetime
from unittest import mock

import pytest

from src.models.base import OptionsChain
from src.schwab.client import SchwabClient
from src.schwab.exceptions import SchwabInvalidSymbolError


class TestMarketDataEndpoints:
    """Tests for market data methods."""

    @pytest.fixture
    def mock_oauth(self):
        """Create mock OAuth coordinator."""
        oauth = mock.Mock()
        oauth.get_authorization_header.return_value = {
            "Authorization": "Bearer test_token"
        }
        return oauth

    @pytest.fixture
    def client(self, mock_oauth):
        """Create Schwab client with mocked OAuth and no cache."""
        return SchwabClient(oauth_coordinator=mock_oauth, enable_cache=False)

    @pytest.fixture
    def client_with_cache(self, mock_oauth):
        """Create Schwab client with mocked OAuth and cache enabled."""
        return SchwabClient(
            oauth_coordinator=mock_oauth, enable_cache=True
        )

    @pytest.fixture
    def mock_quote_response(self):
        """Mock Schwab quote response (actual API structure)."""
        return {
            "AAPL": {
                "symbol": "AAPL",
                "quoteType": "NBBO",
                "realtime": True,
                "quote": {
                    "lastPrice": 150.25,
                    "openPrice": 149.50,
                    "highPrice": 151.00,
                    "lowPrice": 149.00,
                    "closePrice": 150.00,
                    "bidPrice": 150.20,
                    "askPrice": 150.30,
                    "totalVolume": 50000000,
                    "quoteTime": 1706198400000,
                    "tradeTime": 1706198400000,
                }
            }
        }

    @pytest.fixture
    def mock_option_chain_response(self):
        """Mock Schwab options chain response."""
        return {
            "symbol": "AAPL",
            "underlyingPrice": 150.25,
            "callExpDateMap": {
                "2026-02-21:30": {
                    "155.0": [
                        {
                            "symbol": "AAPL_022126C155",
                            "bid": 2.50,
                            "ask": 2.60,
                            "last": 2.55,
                            "totalVolume": 1000,
                            "openInterest": 5000,
                            "volatility": 25.5,  # Percentage
                            "delta": 0.35,
                            "gamma": 0.05,
                            "theta": -0.02,
                            "vega": 0.15,
                        }
                    ],
                }
            },
            "putExpDateMap": {
                "2026-02-21:30": {
                    "145.0": [
                        {
                            "symbol": "AAPL_022126P145",
                            "bid": 1.80,
                            "ask": 1.90,
                            "last": 1.85,
                            "totalVolume": 800,
                            "openInterest": 3000,
                            "volatility": 24.0,
                            "delta": -0.30,
                            "gamma": 0.04,
                            "theta": -0.01,
                            "vega": 0.12,
                        }
                    ],
                }
            },
        }

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_quote_success(self, mock_request, client, mock_quote_response):
        """get_quote() returns quote data successfully."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = mock_quote_response
        mock_request.return_value = mock_response

        quote = client.get_quote("AAPL", use_cache=False)

        assert quote["symbol"] == "AAPL"
        assert quote["lastPrice"] == 150.25
        assert quote["bidPrice"] == 150.20
        assert quote["askPrice"] == 150.30
        assert quote["totalVolume"] == 50000000

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_quote_invalid_symbol(self, mock_request, client):
        """get_quote() raises SchwabInvalidSymbolError for invalid symbol."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {}  # Empty response, no symbol
        mock_request.return_value = mock_response

        with pytest.raises(SchwabInvalidSymbolError, match="not found in response"):
            client.get_quote("INVALID")

    @mock.patch("src.schwab.client.time")
    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_quote_uses_cache(self, mock_request, mock_time, client_with_cache, mock_quote_response):
        """get_quote() uses cached data when available."""
        # Set up cache with recent data (within 5-minute TTL)
        current_time = 1000000.0
        mock_time.time.return_value = current_time

        cached_quote = mock_quote_response["AAPL"]["quote"].copy()
        cached_quote["symbol"] = "AAPL"
        cached_quote["quoteType"] = mock_quote_response["AAPL"]["quoteType"]
        cached_quote["realtime"] = mock_quote_response["AAPL"]["realtime"]

        client_with_cache.cache["schwab_quote_AAPL"] = (cached_quote, current_time - 60)  # 1 minute old

        quote = client_with_cache.get_quote("AAPL", use_cache=True)

        # Should use cached data, not make API call
        assert quote == cached_quote
        mock_request.assert_not_called()

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_quote_caches_response(
        self, mock_request, client_with_cache, mock_quote_response
    ):
        """get_quote() caches API response."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = mock_quote_response
        mock_request.return_value = mock_response

        quote = client_with_cache.get_quote("AAPL", use_cache=True)

        # Should cache the result
        assert "schwab_quote_AAPL" in client_with_cache.cache
        cached_quote, cached_time = client_with_cache.cache["schwab_quote_AAPL"]
        assert cached_quote == quote
        assert isinstance(cached_time, float)  # Unix timestamp

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_option_chain_success(
        self, mock_request, client, mock_option_chain_response
    ):
        """get_option_chain() returns parsed OptionsChain."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = mock_option_chain_response
        mock_request.return_value = mock_response

        chain = client.get_option_chain("AAPL", use_cache=False)

        assert isinstance(chain, OptionsChain)
        assert chain.symbol == "AAPL"
        assert len(chain.contracts) == 2  # 1 call + 1 put

        # Check call contract
        call = next(c for c in chain.contracts if c.option_type == "Call")
        assert call.strike == 155.0
        assert call.bid == 2.50
        assert call.ask == 2.60
        assert call.implied_volatility == 0.255  # Converted from 25.5%
        assert call.delta == 0.35

        # Check put contract
        put = next(c for c in chain.contracts if c.option_type == "Put")
        assert put.strike == 145.0
        assert put.bid == 1.80
        assert put.ask == 1.90
        assert put.implied_volatility == 0.24  # Converted from 24.0%
        assert put.delta == -0.30

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_option_chain_with_filters(self, mock_request, client):
        """get_option_chain() sends correct filter parameters."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {
            "symbol": "AAPL",
            "underlyingPrice": 150.0,
            "callExpDateMap": {},
            "putExpDateMap": {},
        }
        mock_request.return_value = mock_response

        chain = client.get_option_chain(
            "AAPL",
            contract_type="CALL",
            strike_count=10,
            from_date="2026-02-01",
            to_date="2026-03-01",
            use_cache=False,
        )

        # Check request parameters
        call_kwargs = mock_request.call_args[1]
        params = call_kwargs["params"]
        assert params["symbol"] == "AAPL"
        assert params["contractType"] == "CALL"
        assert params["strikeCount"] == 10
        assert params["fromDate"] == "2026-02-01"
        assert params["toDate"] == "2026-03-01"

    @mock.patch("src.schwab.client.time")
    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_option_chain_uses_cache(
        self, mock_request, mock_time, client_with_cache, mock_option_chain_response
    ):
        """get_option_chain() uses cached data when available."""
        current_time = 1000000.0
        mock_time.time.return_value = current_time

        # Create a mock OptionsChain to return from cache
        cached_chain = OptionsChain(
            symbol="AAPL",
            contracts=[],
            retrieved_at=datetime.now().isoformat(),
        )

        # Add to cache (within 15-minute TTL)
        cache_key = "schwab_chain_AAPL_None_None_None_None"
        client_with_cache.cache[cache_key] = (cached_chain, current_time - 300)  # 5 minutes old

        chain = client_with_cache.get_option_chain("AAPL", use_cache=True)

        # Should use cached data
        assert chain == cached_chain
        mock_request.assert_not_called()

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_option_chain_caches_response(
        self, mock_request, client_with_cache, mock_option_chain_response
    ):
        """get_option_chain() caches parsed OptionsChain."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = mock_option_chain_response
        mock_request.return_value = mock_response

        chain = client_with_cache.get_option_chain("AAPL", use_cache=True)

        # Should cache the result
        cache_keys = [k for k in client_with_cache.cache.keys() if k.startswith("schwab_chain_")]
        assert len(cache_keys) == 1
        cached_chain, cached_time = client_with_cache.cache[cache_keys[0]]
        assert isinstance(cached_chain, OptionsChain)
        assert isinstance(cached_time, float)  # Unix timestamp

    def test_parse_schwab_contract(self, client):
        """_parse_schwab_contract() correctly parses contract data."""
        contract_data = {
            "symbol": "AAPL_022126C155",
            "bid": 3.50,
            "ask": 3.60,
            "last": 3.55,
            "totalVolume": 2000,
            "openInterest": 10000,
            "volatility": 30.0,  # Percentage
            "delta": 0.45,
            "gamma": 0.06,
            "theta": -0.03,
            "vega": 0.18,
        }

        contract = client._parse_schwab_contract(
            "AAPL", "2026-02-21", 155.0, "Call", contract_data
        )

        assert contract.symbol == "AAPL"
        assert contract.expiration_date == "2026-02-21"
        assert contract.strike == 155.0
        assert contract.option_type == "Call"
        assert contract.bid == 3.50
        assert contract.ask == 3.60
        assert contract.last == 3.55
        assert contract.volume == 2000
        assert contract.open_interest == 10000
        assert contract.implied_volatility == 0.30  # Converted from 30.0%
        assert contract.delta == 0.45
        assert contract.gamma == 0.06
        assert contract.theta == -0.03
        assert contract.vega == 0.18

    @mock.patch("src.schwab.client.requests.Session.request")
    def test_get_option_chain_handles_multiple_strikes(self, mock_request, client):
        """get_option_chain() correctly parses multiple strikes."""
        response_data = {
            "symbol": "AAPL",
            "underlyingPrice": 150.0,
            "callExpDateMap": {
                "2026-02-21:30": {
                    "150.0": [{"bid": 3.0, "ask": 3.1, "last": 3.05, "totalVolume": 100, "openInterest": 500, "volatility": 25.0, "delta": 0.50, "gamma": 0.05, "theta": -0.02, "vega": 0.15}],
                    "155.0": [{"bid": 2.0, "ask": 2.1, "last": 2.05, "totalVolume": 200, "openInterest": 600, "volatility": 26.0, "delta": 0.40, "gamma": 0.04, "theta": -0.01, "vega": 0.12}],
                }
            },
            "putExpDateMap": {},
        }

        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = response_data
        mock_request.return_value = mock_response

        chain = client.get_option_chain("AAPL", use_cache=False)

        assert len(chain.contracts) == 2
        strikes = [c.strike for c in chain.contracts]
        assert 150.0 in strikes
        assert 155.0 in strikes
