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
from urllib.parse import urljoin

import requests

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

logger = logging.getLogger(__name__)


class SchwabClient:
    """
    Authenticated HTTP client for Schwab APIs.

    This client handles OAuth authentication, automatic token refresh,
    and error handling for all Schwab API calls.

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
        self.oauth = oauth_coordinator or OAuthCoordinator()
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        self.enable_cache = enable_cache
        # Use simple dict for in-memory caching with timestamps
        self.cache: Dict[str, tuple[Any, float]] = {} if enable_cache else {}

        logger.info("SchwabClient initialized")

    def _get_full_url(self, endpoint: str) -> str:
        """
        Construct full API URL from endpoint path.

        Args:
            endpoint: API endpoint path (e.g., "/marketdata/v1/quotes")

        Returns:
            Full URL with base URL (endpoints already include version)
        """
        # Ensure endpoint starts with /
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"

        # Endpoints already include version in path (e.g., /marketdata/v1/quotes)
        # Just join with base URL
        return urljoin(self.BASE_URL, endpoint)

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
    ) -> requests.Response:
        """
        Make authenticated HTTP request to Schwab API.

        This method handles:
        - OAuth token retrieval with automatic refresh
        - Request retry logic with exponential backoff
        - 401 authentication error handling
        - 429 rate limit handling
        - 404 invalid symbol handling

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON request body
            retry_count: Current retry attempt (for internal use)

        Returns:
            Response object

        Raises:
            SchwabAuthenticationError: If authentication fails (401)
            SchwabRateLimitError: If rate limit exceeded (429)
            SchwabInvalidSymbolError: If symbol not found (404)
            SchwabAPIError: For other API errors
            TokenNotAvailableError: If not authorized (need to run auth flow)
        """
        # Get authorization header with fresh token
        try:
            headers = self.oauth.get_authorization_header()
        except TokenNotAvailableError as e:
            logger.error(f"Not authorized: {e}")
            raise SchwabAuthenticationError(
                "No valid OAuth tokens available. "
                "Run authorization script on HOST: python scripts/authorize_schwab_host.py"
            ) from e

        # Add other headers
        headers.update({"Accept": "application/json"})

        # Only add Content-Type for requests with a body
        if method in ["POST", "PUT", "PATCH"] or json_data is not None:
            headers["Content-Type"] = "application/json"

        # Construct full URL
        url = self._get_full_url(endpoint)

        # Log request (excluding sensitive headers)
        logger.debug(f"{method} {url}")
        if params:
            logger.debug(f"  Params: {params}")

        try:
            # Make request
            response = self.session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=30,
            )

            # Handle specific status codes
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
                logger.warning(f"Resource not found (404): {url}")
                # Could be invalid symbol or endpoint
                raise SchwabInvalidSymbolError(
                    f"Resource not found. Check symbol or endpoint: {endpoint}"
                )

            elif response.status_code >= 500:
                # Server error - retry with exponential backoff
                if retry_count < self.max_retries:
                    delay = self.retry_delay * (2**retry_count)
                    logger.warning(
                        f"Server error ({response.status_code}). "
                        f"Retrying in {delay}s (attempt {retry_count + 1}/{self.max_retries})"
                    )
                    time.sleep(delay)
                    return self._request(
                        method, endpoint, params, json_data, retry_count + 1
                    )
                else:
                    logger.error(
                        f"Server error ({response.status_code}) after {self.max_retries} retries"
                    )
                    raise SchwabAPIError(
                        f"Schwab API server error ({response.status_code}): {response.text}"
                    )

            elif not response.ok:
                logger.error(f"API error ({response.status_code}): {response.text}")
                raise SchwabAPIError(
                    f"Schwab API error ({response.status_code}): {response.text}"
                )

            # Success
            logger.debug(f"Response: {response.status_code}")
            return response

        except requests.exceptions.Timeout:
            if retry_count < self.max_retries:
                delay = self.retry_delay * (2**retry_count)
                logger.warning(
                    f"Request timeout. Retrying in {delay}s "
                    f"(attempt {retry_count + 1}/{self.max_retries})"
                )
                time.sleep(delay)
                return self._request(method, endpoint, params, json_data, retry_count + 1)
            else:
                logger.error(f"Request timeout after {self.max_retries} retries")
                raise SchwabAPIError("Request to Schwab API timed out")

        except requests.exceptions.RequestException as e:
            if retry_count < self.max_retries:
                delay = self.retry_delay * (2**retry_count)
                logger.warning(
                    f"Network error: {e}. Retrying in {delay}s "
                    f"(attempt {retry_count + 1}/{self.max_retries})"
                )
                time.sleep(delay)
                return self._request(method, endpoint, params, json_data, retry_count + 1)
            else:
                logger.error(f"Network error after {self.max_retries} retries: {e}")
                raise SchwabAPIError(f"Network error: {e}") from e

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
        # Check cache first (5-minute TTL for quotes)
        if use_cache and self.enable_cache:
            cache_key = f"schwab_quote_{symbol}"
            if cache_key in self.cache:
                cached_data, cached_time = self.cache[cache_key]
                age_seconds = time.time() - cached_time
                if age_seconds < 300:  # 5 minutes
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

        # Check cache first (15-minute TTL for options chain)
        if use_cache and self.enable_cache:
            if cache_key in self.cache:
                cached_data, cached_time = self.cache[cache_key]
                age_seconds = time.time() - cached_time
                if age_seconds < 900:  # 15 minutes
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
            options_chain = self._parse_schwab_option_chain(symbol, response_data)

            # Cache the result (15 minute TTL for options chains)
            if self.enable_cache:
                self.cache[cache_key] = (options_chain, time.time())

            return options_chain

        except SchwabInvalidSymbolError:
            raise
        except SchwabAPIError as e:
            logger.error(f"Failed to fetch options chain for {symbol}: {e}")
            raise

    def _parse_schwab_option_chain(
        self, symbol: str, data: Dict[str, Any]
    ) -> OptionsChain:
        """
        Parse Schwab options chain format to internal OptionsChain model.

        Args:
            symbol: Underlying symbol
            data: Raw Schwab API response

        Returns:
            OptionsChain object with contracts in internal format
        """
        contracts: List[OptionContract] = []

        # Parse call contracts
        call_exp_map = data.get("callExpDateMap", {})
        for exp_date_key, strikes in call_exp_map.items():
            # exp_date_key format: "2026-02-21:30" (expiration:daysToExpiration)
            exp_date = exp_date_key.split(":")[0]

            for strike_price, option_list in strikes.items():
                for option_data in option_list:
                    contract = self._parse_schwab_contract(
                        symbol, exp_date, float(strike_price), "Call", option_data
                    )
                    contracts.append(contract)

        # Parse put contracts
        put_exp_map = data.get("putExpDateMap", {})
        for exp_date_key, strikes in put_exp_map.items():
            exp_date = exp_date_key.split(":")[0]

            for strike_price, option_list in strikes.items():
                for option_data in option_list:
                    contract = self._parse_schwab_contract(
                        symbol, exp_date, float(strike_price), "Put", option_data
                    )
                    contracts.append(contract)

        return OptionsChain(
            symbol=symbol,
            contracts=contracts,
            retrieved_at=datetime.now().isoformat(),
        )

    def _parse_schwab_contract(
        self,
        symbol: str,
        expiration_date: str,
        strike: float,
        option_type: str,
        data: Dict[str, Any],
    ) -> OptionContract:
        """
        Parse a single Schwab option contract to internal format.

        Args:
            symbol: Underlying symbol
            expiration_date: Expiration date (YYYY-MM-DD)
            strike: Strike price
            option_type: "Call" or "Put"
            data: Schwab contract data

        Returns:
            OptionContract in internal format
        """
        return OptionContract(
            symbol=symbol,
            expiration_date=expiration_date,
            strike=strike,
            option_type=option_type,
            bid=data.get("bid", 0.0),
            ask=data.get("ask", 0.0),
            last=data.get("last", 0.0),
            volume=data.get("totalVolume", 0),
            open_interest=data.get("openInterest", 0),
            implied_volatility=data.get("volatility", 0.0) / 100.0,  # Schwab returns as percentage
            delta=data.get("delta", 0.0),
            gamma=data.get("gamma", 0.0),
            theta=data.get("theta", 0.0),
            vega=data.get("vega", 0.0),
        )

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
                account = self._parse_schwab_account(account_data)
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
            account = self._parse_schwab_account(response_data)

            logger.info(f"Retrieved {len(account.positions)} position(s)")
            return account

        except SchwabAPIError as e:
            logger.error(f"Failed to fetch positions for account {account_hash}: {e}")
            raise

    def _parse_schwab_account(self, data: Dict[str, Any]) -> SchwabAccount:
        """
        Parse Schwab account data to internal SchwabAccount model.

        Args:
            data: Raw Schwab API account response

        Returns:
            SchwabAccount object
        """
        # Account data is nested under "securitiesAccount" key
        account_data = data.get("securitiesAccount", data)

        # Parse positions
        positions = []
        positions_data = account_data.get("positions", [])
        for position_data in positions_data:
            position = self._parse_schwab_position(position_data)
            positions.append(position)

        # Parse balances
        balances_data = account_data.get("currentBalances", {})
        balances = self._parse_schwab_balances(balances_data)

        return SchwabAccount(
            account_number=account_data.get("accountNumber", ""),
            account_type=account_data.get("type", ""),
            account_nickname=account_data.get("nickname"),
            positions=positions,
            balances=balances,
            is_closing_only=account_data.get("isClosingOnlyRestricted", False),
            is_day_trader=account_data.get("isDayTrader", False),
        )

    def _parse_schwab_position(self, data: Dict[str, Any]) -> SchwabPosition:
        """
        Parse a single Schwab position to internal format.

        Args:
            data: Schwab position data

        Returns:
            SchwabPosition object
        """
        instrument = data.get("instrument", {})
        symbol = instrument.get("symbol", "")
        asset_type = instrument.get("assetType", "")

        return SchwabPosition(
            symbol=symbol,
            quantity=data.get("longQuantity", 0.0) + data.get("shortQuantity", 0.0),
            average_price=data.get("averagePrice", 0.0),
            current_price=data.get("marketValue", 0.0) / max(data.get("longQuantity", 0.0) + data.get("shortQuantity", 0.0), 1),
            market_value=data.get("marketValue", 0.0),
            day_gain=data.get("currentDayProfitLoss", 0.0),
            day_gain_percent=data.get("currentDayProfitLossPercentage", 0.0),
            total_gain=data.get("marketValue", 0.0) - (data.get("averagePrice", 0.0) * (data.get("longQuantity", 0.0) + data.get("shortQuantity", 0.0))),
            total_gain_percent=None,  # Calculated separately if needed
            instrument_type=instrument.get("instrumentType", ""),
            asset_type=asset_type,
        )

    def _parse_schwab_balances(self, data: Dict[str, Any]) -> SchwabAccountBalances:
        """
        Parse Schwab account balance data to internal format.

        Args:
            data: Schwab balance data

        Returns:
            SchwabAccountBalances object
        """
        return SchwabAccountBalances(
            cash_balance=data.get("cashBalance", 0.0),
            cash_available_for_trading=data.get("cashAvailableForTrading", 0.0),
            cash_available_for_withdrawal=data.get("cashAvailableForWithdrawal", 0.0),
            market_value=data.get("liquidationValue", 0.0),
            total_cash=data.get("totalCash", 0.0),
            account_value=data.get("liquidationValue", 0.0),
            buying_power=data.get("buyingPower"),
        )

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

        # Check cache first (24-hour TTL for price history)
        if use_cache and self.enable_cache:
            if cache_key in self.cache:
                cached_data, cached_time = self.cache[cache_key]
                age_seconds = time.time() - cached_time
                if age_seconds < 86400:  # 24 hours
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
            price_data = self._parse_schwab_price_history(symbol, response_data)

            # Cache the result (24-hour TTL for price history, matching AlphaVantage)
            if self.enable_cache:
                self.cache[cache_key] = (price_data, time.time())

            return price_data

        except SchwabInvalidSymbolError:
            raise
        except SchwabAPIError as e:
            logger.error(f"Failed to fetch price history for {symbol}: {e}")
            raise

    def _parse_schwab_price_history(
        self, symbol: str, data: Dict[str, Any]
    ) -> PriceData:
        """
        Parse Schwab price history response to PriceData model.

        Schwab returns candles in format:
        {
            "candles": [
                {
                    "open": 150.0,
                    "high": 152.5,
                    "low": 149.0,
                    "close": 151.0,
                    "volume": 1000000,
                    "datetime": 1704067200000  # milliseconds since epoch
                },
                ...
            ],
            "symbol": "AAPL",
            "empty": false
        }

        Args:
            symbol: Stock symbol
            data: Raw Schwab API response

        Returns:
            PriceData object with parsed OHLCV data
        """
        candles = data.get("candles", [])

        if not candles:
            raise SchwabAPIError(f"No price data returned for {symbol}")

        # Parse candles into lists
        dates: List[str] = []
        opens: List[float] = []
        highs: List[float] = []
        lows: List[float] = []
        closes: List[float] = []
        volumes: List[int] = []

        for candle in candles:
            # Convert milliseconds timestamp to date string
            timestamp_ms = candle.get("datetime", 0)
            dt = datetime.fromtimestamp(timestamp_ms / 1000)
            dates.append(dt.strftime("%Y-%m-%d"))

            opens.append(float(candle.get("open", 0.0)))
            highs.append(float(candle.get("high", 0.0)))
            lows.append(float(candle.get("low", 0.0)))
            closes.append(float(candle.get("close", 0.0)))
            volumes.append(int(candle.get("volume", 0)))

        logger.debug(f"Parsed {len(candles)} candles for {symbol}")

        return PriceData(
            dates=dates,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
        )
