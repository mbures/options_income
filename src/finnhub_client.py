"""
Finnhub API client for options chain and price data.

This module provides the Finnhub data provider adapter, handling all
HTTP communication with the Finnhub API.

API Documentation: https://finnhub.io/docs/api

Endpoints used:
- /stock/option-chain: Options chain data (free tier)
- /stock/candle: Historical OHLC data (requires premium for most symbols)

Note: The /stock/candle endpoint requires a paid Finnhub subscription
for most symbols. Free tier will return 403 Forbidden error.
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import requests

from .config import FinnhubConfig
from .volatility import PriceData


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FinnhubAPIError(Exception):
    """Custom exception for Finnhub API errors."""

    pass


class FinnhubClient:
    """
    Client for interacting with Finnhub API.

    This client handles:
    - HTTP requests with proper authentication
    - Retry logic with exponential backoff
    - Error handling and logging
    - Connection pooling via requests.Session
    """

    def __init__(self, config: FinnhubConfig):
        """
        Initialize client with configuration.

        Args:
            config: FinnhubConfig instance with API credentials and settings
        """
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": "FinnhubOptionsClient/1.0"}
        )
        logger.info("Finnhub client initialized")

    def get_option_chain(self, symbol: str) -> Dict[str, Any]:
        """
        Retrieve options chain for a given symbol.

        Args:
            symbol: Stock ticker symbol (e.g., "F", "AAPL")

        Returns:
            API response as dictionary

        Raises:
            FinnhubAPIError: If API request fails
            ValueError: If symbol is invalid
        """
        # Validate symbol
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"Invalid symbol: {symbol}")

        symbol = symbol.upper().strip()
        if not symbol.isalnum():
            raise ValueError(f"Symbol must be alphanumeric: {symbol}")

        # Construct request
        url = f"{self.config.base_url}/stock/option-chain"
        params = {"symbol": symbol, "token": self.config.api_key}

        logger.info(f"Fetching options chain for {symbol}")

        try:
            response = self._make_request_with_retry(url, params)

            # Check HTTP status
            if response.status_code == 401:
                raise FinnhubAPIError(
                    "Authentication failed. Check your API key. "
                    "Get a free API key at https://finnhub.io/register"
                )
            elif response.status_code == 429:
                raise FinnhubAPIError(
                    "Rate limit exceeded. Finnhub free tier allows 60 calls/minute."
                )
            elif response.status_code >= 500:
                raise FinnhubAPIError(
                    f"Finnhub server error (HTTP {response.status_code}). " "Try again later."
                )

            response.raise_for_status()

            data = response.json()
            logger.info(f"Successfully retrieved data for {symbol}")
            return data

        except requests.exceptions.Timeout as e:
            raise FinnhubAPIError(
                f"Request timeout after {self.config.timeout}s for symbol {symbol}"
            ) from e
        except requests.exceptions.ConnectionError as e:
            raise FinnhubAPIError("Connection error. Check your internet connection.") from e
        except requests.exceptions.RequestException as e:
            raise FinnhubAPIError(f"API request failed: {str(e)}") from e
        except ValueError as e:
            raise FinnhubAPIError(f"Invalid JSON response from API: {str(e)}") from e

    def _make_request_with_retry(
        self, url: str, params: Dict[str, str], attempt: int = 1
    ) -> requests.Response:
        """
        Make HTTP request with exponential backoff retry.

        Args:
            url: Request URL
            params: Query parameters
            attempt: Current attempt number (used for recursion)

        Returns:
            HTTP response object

        Raises:
            FinnhubAPIError: If all retry attempts fail
        """
        try:
            response = self.session.get(url, params=params, timeout=self.config.timeout)
            return response

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt >= self.config.max_retries:
                logger.error(f"All {self.config.max_retries} retry attempts failed")
                raise

            # Calculate exponential backoff delay
            delay = self.config.retry_delay * (2 ** (attempt - 1))

            logger.warning(
                f"Request failed (attempt {attempt}/{self.config.max_retries}). "
                f"Retrying in {delay:.1f}s... Error: {str(e)}"
            )

            time.sleep(delay)
            return self._make_request_with_retry(url, params, attempt + 1)

    def close(self) -> None:
        """
        Close the HTTP session and cleanup resources.

        Should be called when done using the client.
        """
        self.session.close()
        logger.info("Finnhub client closed")

    def get_candle_data(
        self,
        symbol: str,
        lookback_days: int = 60,
        resolution: str = "D"
    ) -> PriceData:
        """
        Fetch historical OHLC candle data for a symbol.

        IMPORTANT: This endpoint requires a paid Finnhub subscription for most symbols.
        Free tier will return 403 Forbidden error.

        Args:
            symbol: Stock ticker symbol (e.g., "F", "AAPL")
            lookback_days: Number of days of historical data (default: 60)
            resolution: Data resolution ("D" for daily)

        Returns:
            PriceData with OHLC data

        Raises:
            FinnhubAPIError: If API call fails (including 403 for free tier)
            ValueError: If response is invalid or empty
        """
        symbol = symbol.upper()

        # Calculate date range
        end_date = datetime.now()
        # Add extra days to account for weekends/holidays
        start_date = end_date - timedelta(days=int(lookback_days * 1.5))

        from_timestamp = int(start_date.timestamp())
        to_timestamp = int(end_date.timestamp())

        logger.info(
            f"Fetching {lookback_days} days of candle data for {symbol} "
            f"from {start_date.date()} to {end_date.date()}"
        )

        # Call candle API
        url = f"{self.config.base_url}/stock/candle"
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "from": from_timestamp,
            "to": to_timestamp,
            "token": self.config.api_key
        }

        try:
            response = self._make_request_with_retry(url, params)

            if response.status_code == 403:
                raise FinnhubAPIError(
                    f"Access forbidden for {symbol} candle data. "
                    "This endpoint requires a paid Finnhub subscription. "
                    "Consider using Alpha Vantage (free tier) instead."
                )

            response.raise_for_status()
            data = response.json()

        except requests.exceptions.RequestException as e:
            raise FinnhubAPIError(f"Failed to fetch candle data: {e}")

        # Parse response
        return self._parse_candle_response(data, symbol, lookback_days)

    def _parse_candle_response(
        self,
        response: Dict[str, Any],
        symbol: str,
        requested_days: int
    ) -> PriceData:
        """
        Parse Finnhub candle response into PriceData.

        Finnhub returns arrays:
        - t: Unix timestamps
        - o: Open prices
        - h: High prices
        - l: Low prices
        - c: Close prices
        - v: Volumes
        - s: Status ("ok" or "no_data")

        Args:
            response: API response dictionary
            symbol: Stock ticker symbol
            requested_days: Number of days requested

        Returns:
            PriceData with parsed OHLC data

        Raises:
            ValueError: If response is invalid or empty
        """
        status = response.get("s")
        if status == "no_data":
            raise ValueError(f"No price data available for {symbol}")
        elif status != "ok":
            raise ValueError(f"Invalid response status: {status}")

        timestamps = response.get("t", [])
        opens = response.get("o", [])
        highs = response.get("h", [])
        lows = response.get("l", [])
        closes = response.get("c", [])
        volumes = response.get("v", [])

        if not timestamps or not closes:
            raise ValueError(f"Empty price data for {symbol}")

        # Verify all arrays have same length
        lengths = [len(timestamps), len(opens), len(highs), len(lows), len(closes)]
        if len(set(lengths)) != 1:
            raise ValueError(f"Inconsistent data array lengths: {lengths}")

        # Convert timestamps to dates and filter to requested window
        dates = []
        filtered_opens = []
        filtered_highs = []
        filtered_lows = []
        filtered_closes = []
        filtered_volumes = []

        # Take the most recent N days
        n_points = min(len(timestamps), requested_days)
        start_idx = len(timestamps) - n_points

        for i in range(start_idx, len(timestamps)):
            date_str = datetime.fromtimestamp(timestamps[i]).strftime("%Y-%m-%d")
            dates.append(date_str)
            filtered_opens.append(round(opens[i], 2))
            filtered_highs.append(round(highs[i], 2))
            filtered_lows.append(round(lows[i], 2))
            filtered_closes.append(round(closes[i], 2))
            if volumes:
                filtered_volumes.append(int(volumes[i]))

        logger.info(
            f"Parsed {len(dates)} days of price data for {symbol} "
            f"({dates[0]} to {dates[-1]})"
        )

        # Validate data quality
        self._validate_price_data(filtered_opens, filtered_highs, filtered_lows, filtered_closes)

        return PriceData(
            dates=dates,
            opens=filtered_opens,
            highs=filtered_highs,
            lows=filtered_lows,
            closes=filtered_closes,
            volumes=filtered_volumes if filtered_volumes else None
        )

    def _validate_price_data(
        self,
        opens: list,
        highs: list,
        lows: list,
        closes: list
    ) -> None:
        """
        Validate price data quality.

        Args:
            opens: Opening prices
            highs: High prices
            lows: Low prices
            closes: Closing prices

        Raises:
            ValueError: If data quality issues detected
        """
        for i in range(len(opens)):
            if any(p <= 0 for p in [opens[i], highs[i], lows[i], closes[i]]):
                raise ValueError(f"Non-positive price detected at index {i}")

            if highs[i] < lows[i]:
                raise ValueError(f"High < Low at index {i}: {highs[i]} < {lows[i]}")

            if highs[i] / lows[i] > 1.5:
                logger.warning(
                    f"Large intraday range at index {i}: "
                    f"high={highs[i]}, low={lows[i]} ({highs[i]/lows[i]:.2f}x)"
                )

    def get_earnings_calendar(
        self,
        symbol: str,
        from_date: str,
        to_date: str
    ) -> list:
        """
        Fetch earnings calendar dates for a symbol.

        Args:
            symbol: Stock ticker symbol (e.g., "F", "AAPL")
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format

        Returns:
            List of earnings dates (YYYY-MM-DD format)

        Raises:
            FinnhubAPIError: If API request fails
        """
        symbol = symbol.upper().strip()

        url = f"{self.config.base_url}/calendar/earnings"
        params = {
            "symbol": symbol,
            "from": from_date,
            "to": to_date,
            "token": self.config.api_key
        }

        logger.info(f"Fetching earnings calendar for {symbol} from {from_date} to {to_date}")

        try:
            response = self._make_request_with_retry(url, params)

            if response.status_code == 401:
                raise FinnhubAPIError(
                    "Authentication failed. Check your API key."
                )
            elif response.status_code == 429:
                raise FinnhubAPIError(
                    "Rate limit exceeded. Finnhub free tier allows 60 calls/minute."
                )
            elif response.status_code >= 500:
                raise FinnhubAPIError(
                    f"Finnhub server error (HTTP {response.status_code})."
                )

            response.raise_for_status()
            data = response.json()

            # Parse earnings dates from response
            earnings_dates = []
            earnings_calendar = data.get("earningsCalendar", [])
            for entry in earnings_calendar:
                if entry.get("symbol") == symbol:
                    date = entry.get("date")
                    if date:
                        earnings_dates.append(date)

            logger.info(f"Found {len(earnings_dates)} earnings dates for {symbol}")
            return sorted(earnings_dates)

        except requests.exceptions.Timeout as e:
            raise FinnhubAPIError(
                f"Request timeout after {self.config.timeout}s for earnings calendar {symbol}"
            ) from e
        except requests.exceptions.ConnectionError as e:
            raise FinnhubAPIError(
                f"Connection error fetching earnings for {symbol}"
            ) from e
        except requests.exceptions.RequestException as e:
            raise FinnhubAPIError(f"Earnings API request failed: {str(e)}") from e

    def __enter__(self) -> "FinnhubClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensures cleanup."""
        self.close()
