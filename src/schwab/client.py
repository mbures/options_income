"""
Schwab API client with OAuth authentication.

This module provides an authenticated HTTP client for Schwab's Trading and
Market Data APIs. It handles:

- OAuth token management with automatic refresh
- Request retry logic for transient errors
- Error handling and logging
- 401 response handling with clear re-authorization guidance

The client must be initialized with an OAuthCoordinator that manages
OAuth tokens. Tokens are automatically refreshed when expired.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from src.api.base_client import BaseAPIClient
from src.constants import (
    CACHE_TTL_QUOTE_SECONDS,
    CACHE_TTL_OPTIONS_CHAIN_SECONDS,
    CACHE_TTL_PRICE_HISTORY_SECONDS,
)
from src.models.base import OptionContract, OptionsChain
from src.oauth.coordinator import OAuthCoordinator
from src.volatility_models import PriceData
from src.oauth.exceptions import TokenNotAvailableError

from . import endpoints
from .exceptions import (
    SchwabAPIError,
    SchwabAuthenticationError,
    SchwabInvalidSymbolError,
    SchwabRateLimitError,
)
from .models import SchwabAccount, SchwabAccountBalances, SchwabPosition
from .parsers import (
    parse_schwab_account,
    parse_schwab_balances,
    parse_schwab_contract,
    parse_schwab_option_chain,
    parse_schwab_position,
    parse_schwab_price_history,
)

logger = logging.getLogger(__name__)


class SchwabClient(BaseAPIClient):
    """
    Authenticated HTTP client for Schwab APIs.

    This client inherits from BaseAPIClient and adds Schwab-specific
    functionality including OAuth authentication, caching, and
    Schwab API-specific error handling.

    Inherited features from BaseAPIClient:
    - HTTP requests with connection pooling
    - Retry logic with exponential backoff
    - Error handling and logging

    Example:
        from src.oauth.coordinator import OAuthCoordinator
        from src.schwab.client import SchwabClient

        oauth = OAuthCoordinator()
        client = SchwabClient(oauth)

        # Get quote
        quote = client.get_quote("AAPL")

        # Get options chain
        chain = client.get_option_chain("AAPL")
    """

    # Schwab API base URL
    BASE_URL = "https://api.schwabapi.com"

    # Schwab API version prefix
    API_VERSION = "/v1"

    def __init__(
        self,
        oauth_coordinator: Optional[OAuthCoordinator] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        enable_cache: bool = True,
    ):
        """
        Initialize Schwab API client.

        Args:
            oauth_coordinator: OAuth coordinator for authentication
                              (creates default if not provided)
            max_retries: Maximum number of retries for transient errors
            retry_delay: Base delay between retries in seconds (exponential backoff)
            enable_cache: Whether to enable in-memory response caching
        """
        # Initialize base client
        super().__init__(max_retries=max_retries, retry_delay=retry_delay, timeout=30)

        self.oauth = oauth_coordinator or OAuthCoordinator()
        self.enable_cache = enable_cache
        # Use simple dict for in-memory caching with timestamps
        self.cache: Dict[str, tuple[Any, float]] = {} if enable_cache else {}

        logger.info("SchwabClient initialized")

    def _get_auth_headers(self) -> Dict[str, str]:
        """
        Get OAuth authorization headers for Schwab API requests.

        Returns:
            Dictionary with Authorization header

        Raises:
            SchwabAuthenticationError: If OAuth tokens not available
        """
        try:
            return self.oauth.get_authorization_header()
        except TokenNotAvailableError as e:
            logger.error(f"Not authorized: {e}")
            raise SchwabAuthenticationError(
                "No valid OAuth tokens available. "
                "Run authorization script on HOST: python scripts/authorize_schwab_host.py"
            ) from e

    def _handle_error_response(self, response: requests.Response) -> None:
        """
        Handle Schwab-specific error responses.

        Args:
            response: HTTP response with error status code

        Raises:
            SchwabAuthenticationError: For 401 errors
            SchwabRateLimitError: For 429 errors
            SchwabInvalidSymbolError: For 404 errors
            SchwabAPIError: For other errors
        """
        if response.status_code == 401:
            logger.error(f"Authentication failed (401): {response.text}")
            raise SchwabAuthenticationError(
                "Authentication failed. OAuth token may be expired or revoked. "
                "Re-authorize on HOST: python scripts/authorize_schwab_host.py --revoke && "
                "python scripts/authorize_schwab_host.py"
            )

        elif response.status_code == 429:
            logger.warning("Rate limit exceeded (429)")
            raise SchwabRateLimitError(
                "Schwab API rate limit exceeded. Please wait before retrying."
            )

        elif response.status_code == 404:
            logger.warning(f"Resource not found (404): {response.url}")
            raise SchwabInvalidSymbolError(
                f"Resource not found. Check symbol or endpoint"
            )

        elif not response.ok:
            logger.error(f"API error ({response.status_code}): {response.text}")
            raise SchwabAPIError(
                f"Schwab API error ({response.status_code}): {response.text}"
            )

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        """
        Make authenticated HTTP request to Schwab API.

        This method wraps the base client's request method with OAuth authentication.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON request body

        Returns:
            Response object

        Raises:
            SchwabAuthenticationError: If authentication fails (401)
            SchwabRateLimitError: If rate limit exceeded (429)
            SchwabInvalidSymbolError: If symbol not found (404)
            SchwabAPIError: For other API errors
        """
        # Get OAuth authorization headers
        auth_headers = self._get_auth_headers()

        # Get full URL
        url = self._get_full_url(endpoint)

        try:
            # Use base client's retry logic
            response = self._make_request_with_retry(
                method, url, params=params, json_data=json_data, headers=auth_headers
            )

            # Handle Schwab-specific errors
            self._handle_error_response(response)

            return response

        except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
            logger.error(f"Request failed: {e}")
            raise SchwabAPIError(f"Request to Schwab API failed: {e}") from e

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make authenticated GET request.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response as dictionary

        Raises:
            SchwabAuthenticationError: If authentication fails
            SchwabAPIError: For API errors
        """
        response = self._request("GET", endpoint, params=params)
        return response.json()

    def post(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make authenticated POST request.

        Args:
            endpoint: API endpoint path
            json_data: JSON request body
            params: Query parameters

        Returns:
            JSON response as dictionary

        Raises:
            SchwabAuthenticationError: If authentication fails
            SchwabAPIError: For API errors
        """
        response = self._request("POST", endpoint, params=params, json_data=json_data)
        return response.json()

    def get_quote(self, symbol: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Get real-time quote for a symbol.

        Args:
            symbol: Stock symbol (e.g., "AAPL")
            use_cache: Whether to use cached data if available (default: True)

        Returns:
            Quote data dictionary with keys:
            - symbol: str
            - lastPrice: float
            - openPrice: float
            - highPrice: float
            - lowPrice: float
            - closePrice: float
            - bidPrice: float
            - askPrice: float
            - totalVolume: int
            - quoteTime: int (Unix timestamp in milliseconds)
            - tradeTime: int (Unix timestamp in milliseconds)

        Raises:
            SchwabAuthenticationError: If authentication fails
            SchwabInvalidSymbolError: If symbol not found
            SchwabAPIError: For other API errors

        Example:
            quote = client.get_quote("AAPL")
            print(f"Last price: ${quote['lastPrice']}")
        """
        # Check cache first
        if use_cache and self.enable_cache:
            cache_key = f"schwab_quote_{symbol}"
            if cache_key in self.cache:
                cached_data, cached_time = self.cache[cache_key]
                age_seconds = time.time() - cached_time
                if age_seconds < CACHE_TTL_QUOTE_SECONDS:
                    logger.debug(f"Using cached quote for {symbol} (age: {age_seconds:.1f}s)")
                    return cached_data

        # Fetch from API
        logger.info(f"Fetching quote for {symbol}")

        # Use the quotes endpoint (plural) with symbols query parameter
        endpoint = endpoints.MARKETDATA_QUOTES
        params = {"symbols": symbol}

        try:
            response_data = self.get(endpoint, params=params)

            # Response format: {symbol: {quote: {...}, extended: {...}, ...}}
            # Extract the data for our symbol
            symbol_data = response_data.get(symbol)
            if not symbol_data:
                raise SchwabInvalidSymbolError(
                    f"Symbol {symbol} not found in response"
                )

            # Extract the quote data from the nested 'quote' dictionary
            # Schwab response has: {quote: {lastPrice, closePrice, ...}, extended: {...}, ...}
            quote_data = symbol_data.get("quote", {})

            # Merge in some useful top-level fields for completeness
            quote_data["symbol"] = symbol_data.get("symbol", symbol)
            quote_data["quoteType"] = symbol_data.get("quoteType")
            quote_data["realtime"] = symbol_data.get("realtime")

            # Cache the result (5 minute TTL for quotes)
            if self.enable_cache:
                self.cache[f"schwab_quote_{symbol}"] = (quote_data, time.time())

            return quote_data

        except SchwabInvalidSymbolError:
            raise
        except SchwabAPIError as e:
            logger.error(f"Failed to fetch quote for {symbol}: {e}")
            raise

    def get_option_chain(
        self,
        symbol: str,
        contract_type: Optional[str] = None,
        strike_count: Optional[int] = None,
        include_quotes: bool = True,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        use_cache: bool = True,
    ) -> OptionsChain:
        """
        Get options chain for a symbol.

        Args:
            symbol: Underlying stock symbol (e.g., "AAPL")
            contract_type: Filter by "CALL", "PUT", or None for both (default: None)
            strike_count: Number of strikes to return (default: None for all)
            include_quotes: Include underlying quote data (default: True)
            from_date: Start date for expiration filter (YYYY-MM-DD)
            to_date: End date for expiration filter (YYYY-MM-DD)
            use_cache: Whether to use cached data if available (default: True)

        Returns:
            OptionsChain object with contracts parsed to internal format

        Raises:
            SchwabAuthenticationError: If authentication fails
            SchwabInvalidSymbolError: If symbol not found
            SchwabAPIError: For other API errors

        Example:
            chain = client.get_option_chain("AAPL", contract_type="CALL", strike_count=10)
            print(f"Found {len(chain.contracts)} call contracts")
        """
        # Build cache key
        cache_params = f"{symbol}_{contract_type}_{strike_count}_{from_date}_{to_date}"
        cache_key = f"schwab_chain_{cache_params}"

        # Check cache first
        if use_cache and self.enable_cache:
            if cache_key in self.cache:
                cached_data, cached_time = self.cache[cache_key]
                age_seconds = time.time() - cached_time
                if age_seconds < CACHE_TTL_OPTIONS_CHAIN_SECONDS:
                    logger.debug(f"Using cached options chain for {symbol} (age: {age_seconds:.1f}s)")
                    return cached_data

        # Build request parameters
        params: Dict[str, Any] = {
            "symbol": symbol,
            "includeQuotes": str(include_quotes).lower(),
        }

        if contract_type:
            params["contractType"] = contract_type.upper()
        if strike_count:
            params["strikeCount"] = strike_count
        if from_date:
            params["fromDate"] = from_date
        if to_date:
            params["toDate"] = to_date

        # Fetch from API
        logger.info(f"Fetching options chain for {symbol}")

        try:
            response_data = self.get(endpoints.MARKETDATA_OPTION_CHAINS, params=params)

            # Parse Schwab format to internal OptionsChain
            options_chain = parse_schwab_option_chain(symbol, response_data)

            # Cache the result (15 minute TTL for options chains)
            if self.enable_cache:
                self.cache[cache_key] = (options_chain, time.time())

            return options_chain

        except SchwabInvalidSymbolError:
            raise
        except SchwabAPIError as e:
            logger.error(f"Failed to fetch options chain for {symbol}: {e}")
            raise


    def get_accounts(self) -> List[SchwabAccount]:
        """
        Get all accounts for the authenticated user.

        Returns:
            List of SchwabAccount objects

        Raises:
            SchwabAuthenticationError: If authentication fails
            SchwabAPIError: For other API errors

        Example:
            accounts = client.get_accounts()
            for account in accounts:
                print(f"{account.account_type}: {account.balances.account_value}")
        """
        logger.info("Fetching accounts")

        try:
            response_data = self.get(endpoints.ACCOUNTS)

            # Parse each account
            accounts = []
            for account_data in response_data:
                account = parse_schwab_account(account_data)
                accounts.append(account)

            logger.info(f"Retrieved {len(accounts)} account(s)")
            return accounts

        except SchwabAPIError as e:
            logger.error(f"Failed to fetch accounts: {e}")
            raise

    def get_account_positions(self, account_hash: str) -> SchwabAccount:
        """
        Get account details including positions for a specific account.

        Args:
            account_hash: Encrypted account number from get_accounts()

        Returns:
            SchwabAccount object with positions

        Raises:
            SchwabAuthenticationError: If authentication fails
            SchwabAPIError: For other API errors

        Example:
            accounts = client.get_accounts()
            account_hash = accounts[0].account_number
            account_details = client.get_account_positions(account_hash)
            print(f"Found {len(account_details.positions)} positions")
        """
        logger.info(f"Fetching positions for account {account_hash}")

        try:
            endpoint = endpoints.ACCOUNT_DETAILS.format(accountHash=account_hash)
            response_data = self.get(endpoint, params={"fields": "positions"})

            # Parse account with positions
            account = parse_schwab_account(response_data)

            logger.info(f"Retrieved {len(account.positions)} position(s)")
            return account

        except SchwabAPIError as e:
            logger.error(f"Failed to fetch positions for account {account_hash}: {e}")
            raise


    def get_price_history(
        self,
        symbol: str,
        period_type: str = "month",
        period: int = 3,
        frequency_type: str = "daily",
        frequency: int = 1,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        use_cache: bool = True,
    ) -> PriceData:
        """
        Get historical price data for a symbol.

        Args:
            symbol: Stock symbol (e.g., "AAPL")
            period_type: Type of period ("day", "month", "year", "ytd")
            period: Number of periods (depends on period_type)
            frequency_type: Type of frequency ("minute", "daily", "weekly", "monthly")
            frequency: Frequency interval (1 for daily)
            start_date: Optional start date (overrides period if provided)
            end_date: Optional end date (defaults to now)
            use_cache: Whether to use cached data if available (default: True)

        Returns:
            PriceData object with OHLCV data

        Raises:
            SchwabAuthenticationError: If authentication fails
            SchwabInvalidSymbolError: If symbol not found
            SchwabAPIError: For other API errors

        Example:
            price_data = client.get_price_history("AAPL", period_type="month", period=3)
            print(f"Got {len(price_data.closes)} days of price data")
        """
        symbol = symbol.upper()

        # Build cache key
        cache_params = (
            f"{symbol}_{period_type}_{period}_{frequency_type}_{frequency}_"
            f"{start_date}_{end_date}"
        )
        cache_key = f"schwab_price_history_{cache_params}"

        # Check cache first
        if use_cache and self.enable_cache:
            if cache_key in self.cache:
                cached_data, cached_time = self.cache[cache_key]
                age_seconds = time.time() - cached_time
                if age_seconds < CACHE_TTL_PRICE_HISTORY_SECONDS:
                    logger.debug(f"Using cached price history for {symbol} (age: {age_seconds:.1f}s)")
                    return cached_data

        # Build request parameters
        params: Dict[str, Any] = {
            "symbol": symbol,
            "periodType": period_type,
            "period": period,
            "frequencyType": frequency_type,
            "frequency": frequency,
        }

        # Add date parameters if provided
        if start_date:
            # Schwab expects milliseconds since epoch
            params["startDate"] = int(start_date.timestamp() * 1000)
        if end_date:
            params["endDate"] = int(end_date.timestamp() * 1000)

        # Fetch from API
        logger.info(f"Fetching price history for {symbol}")
        logger.debug(f"Price history params: {params}")
        logger.debug(f"Price history endpoint: {endpoints.MARKETDATA_PRICE_HISTORY}")

        try:
            response_data = self.get(endpoints.MARKETDATA_PRICE_HISTORY, params=params)

            # Parse Schwab response to PriceData
            price_data = parse_schwab_price_history(symbol, response_data)

            # Cache the result (24-hour TTL for price history, matching AlphaVantage)
            if self.enable_cache:
                self.cache[cache_key] = (price_data, time.time())

            return price_data

        except SchwabInvalidSymbolError:
            raise
        except SchwabAPIError as e:
            logger.error(f"Failed to fetch price history for {symbol}: {e}")
            raise

