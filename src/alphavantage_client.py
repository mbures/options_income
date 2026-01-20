"""
Alpha Vantage API client for historical price data.

This module provides the Alpha Vantage data provider adapter, handling all
HTTP communication with the Alpha Vantage API.

API Documentation: https://www.alphavantage.co/documentation/
Get API Key: https://www.alphavantage.co/support/#api-key

Free tier limits:
- 25 requests/day
- Max 100 data points per request (outputsize=compact)
- TIME_SERIES_DAILY_ADJUSTED requires premium subscription

Usage:
    from src.config import AlphaVantageConfig
    from src.cache import LocalFileCache
    from src.alphavantage_client import AlphaVantageClient

    config = AlphaVantageConfig.from_file()
    file_cache = LocalFileCache()
    client = AlphaVantageClient(config, file_cache=file_cache)

    price_data = client.fetch_daily_prices("AAPL", lookback_days=60)

    # Check API usage
    print(client.get_usage_status())
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

import requests

if TYPE_CHECKING:
    from .cache import LocalFileCache
    from .config import AlphaVantageConfig

from .volatility import PriceData

logger = logging.getLogger(__name__)


class AlphaVantageAPIError(Exception):
    """Exception raised for Alpha Vantage API errors."""

    pass


class AlphaVantageRateLimitError(AlphaVantageAPIError):
    """Exception raised when Alpha Vantage daily rate limit is exceeded."""

    pass


class AlphaVantageClient:
    """
    Client for Alpha Vantage API.

    Handles all HTTP communication with Alpha Vantage, including:
    - TIME_SERIES_DAILY endpoint for OHLC + volume
    - Rate limit tracking and enforcement
    - Response parsing into PriceData objects
    - File-based caching for persistence

    Free tier limits:
    - 25 requests/day
    - Max 100 data points per request (outputsize=compact)

    Note: TIME_SERIES_DAILY_ADJUSTED (with dividends/splits) requires
    premium subscription.
    """

    DAILY_LIMIT = 25  # Free tier daily API call limit
    MAX_LOOKBACK_DAYS = 100  # Free tier max data points (compact output)

    def __init__(self, config: "AlphaVantageConfig", file_cache: Optional["LocalFileCache"] = None):
        """
        Initialize Alpha Vantage client.

        Args:
            config: AlphaVantageConfig instance with API credentials
            file_cache: Optional LocalFileCache for persistent storage and usage tracking
        """
        # Import here to avoid circular imports

        self.config = config
        self._file_cache = file_cache
        self._session = requests.Session()
        self._session.headers.update(
            {"Accept": "application/json", "User-Agent": "AlphaVantageClient/2.0"}
        )
        logger.info(
            f"AlphaVantageClient initialized (file_cache={'enabled' if file_cache else 'disabled'})"
        )

    def fetch_daily_prices(self, symbol: str, lookback_days: int = 60) -> PriceData:
        """
        Fetch historical daily price data for a symbol.

        Uses TIME_SERIES_DAILY endpoint (free tier).

        Args:
            symbol: Stock ticker symbol (e.g., "F", "AAPL")
            lookback_days: Number of days of historical data (default: 60)

        Returns:
            PriceData with OHLC data and volumes.
            Note: adjusted_closes, dividends, split_coefficients will be None
            (require premium TIME_SERIES_DAILY_ADJUSTED endpoint)

        Raises:
            ValueError: If response is invalid or empty
            AlphaVantageRateLimitError: If daily rate limit exceeded
            AlphaVantageAPIError: If API call fails
        """
        symbol = symbol.upper()

        # Check cache for existing stock prices (24-hour TTL)
        if self._file_cache:
            if self._file_cache.has_stock_prices(symbol, max_age_hours=24.0):
                cached_prices = self._file_cache.get_stock_prices(symbol, max_age_hours=24.0)
                if len(cached_prices) >= min(lookback_days, self.MAX_LOOKBACK_DAYS) * 0.8:
                    # Have enough cached data (allow 20% buffer for weekends/holidays)
                    logger.info(f"Using cached price data for {symbol} ({len(cached_prices)} days)")
                    return self._build_price_data_from_cache(cached_prices, lookback_days)

        # Check API usage before making request
        if self._file_cache:
            usage = self._file_cache.get_alpha_vantage_usage_today()
            if usage >= self.DAILY_LIMIT:
                raise AlphaVantageRateLimitError(
                    f"Alpha Vantage daily limit reached ({usage}/{self.DAILY_LIMIT}). "
                    "Resets at midnight. Consider using cached data."
                )
            remaining = self.DAILY_LIMIT - usage
            if remaining <= 5:
                logger.warning(f"Alpha Vantage API: {remaining} calls remaining today")

        # Free tier limitation: compact returns max 100 data points
        if lookback_days > self.MAX_LOOKBACK_DAYS:
            logger.warning(
                f"Requested {lookback_days} days but free tier is limited to "
                f"{self.MAX_LOOKBACK_DAYS} days. Capping request."
            )
            lookback_days = self.MAX_LOOKBACK_DAYS

        logger.info(
            f"Fetching {lookback_days} days of price data for {symbol} "
            f"from Alpha Vantage (TIME_SERIES_DAILY)"
        )

        # Make API request
        data = self._call_time_series_daily(symbol)

        # Increment usage counter after successful request
        if self._file_cache:
            new_usage = self._file_cache.increment_alpha_vantage_usage()
            logger.debug(f"Alpha Vantage API usage today: {new_usage}/{self.DAILY_LIMIT}")

        # Parse response and cache individual price points
        price_data = self._parse_daily_response(data, symbol, lookback_days)

        # Store individual price points in cache
        if self._file_cache:
            self._cache_price_data(symbol, price_data)

        return price_data

    def _cache_price_data(self, symbol: str, price_data: PriceData) -> None:
        """
        Cache individual price data points to the market_data table.

        Args:
            symbol: Stock ticker symbol
            price_data: PriceData object to cache
        """
        prices_dict = {}
        for i, date_str in enumerate(price_data.dates):
            prices_dict[date_str] = {
                "open": price_data.opens[i] if price_data.opens else None,
                "high": price_data.highs[i] if price_data.highs else None,
                "low": price_data.lows[i] if price_data.lows else None,
                "close": price_data.closes[i],
                "volume": price_data.volumes[i] if price_data.volumes else None,
            }

        count = self._file_cache.set_stock_prices(symbol, prices_dict)
        logger.debug(f"Cached {count} price points for {symbol}")

    def _build_price_data_from_cache(
        self, cached_prices: dict[str, dict[str, Any]], lookback_days: int
    ) -> PriceData:
        """
        Build PriceData from cached price points.

        Args:
            cached_prices: Dictionary mapping dates to OHLCV data
            lookback_days: Number of days requested

        Returns:
            PriceData object
        """
        # Sort dates chronologically and take most recent N days
        all_dates = sorted(cached_prices.keys())
        if len(all_dates) > lookback_days:
            all_dates = all_dates[-lookback_days:]

        dates = []
        opens = []
        highs = []
        lows = []
        closes = []
        volumes = []

        for date_str in all_dates:
            day_data = cached_prices[date_str]
            dates.append(date_str)
            opens.append(day_data.get("open"))
            highs.append(day_data.get("high"))
            lows.append(day_data.get("low"))
            closes.append(day_data.get("close"))
            volumes.append(day_data.get("volume"))

        return PriceData(
            dates=dates,
            opens=opens if all(o is not None for o in opens) else None,
            highs=highs if all(h is not None for h in highs) else None,
            lows=lows if all(low is not None for low in lows) else None,
            closes=closes,
            volumes=volumes if all(v is not None for v in volumes) else None,
            adjusted_closes=None,
            dividends=None,
            split_coefficients=None,
        )

    def _call_time_series_daily(self, symbol: str) -> dict[str, Any]:
        """
        Call TIME_SERIES_DAILY API endpoint.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Raw API response dictionary

        Raises:
            AlphaVantageAPIError: If API call fails
            AlphaVantageRateLimitError: If rate limited
        """
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "apikey": self.config.api_key,
            "outputsize": "compact",
        }

        try:
            response = self._session.get(
                self.config.base_url, params=params, timeout=self.config.timeout
            )
            response.raise_for_status()
            data = response.json()

        except requests.exceptions.Timeout as err:
            raise AlphaVantageAPIError(
                f"Request timeout after {self.config.timeout}s for symbol {symbol}"
            ) from err
        except requests.exceptions.RequestException as e:
            raise AlphaVantageAPIError(f"API request failed: {e}") from e

        # Check for API errors in response
        if "Error Message" in data:
            raise AlphaVantageAPIError(f"Alpha Vantage API error: {data['Error Message']}")

        if "Note" in data:
            raise AlphaVantageRateLimitError(f"Alpha Vantage rate limit: {data['Note']}")

        if "Information" in data:
            raise AlphaVantageAPIError(f"Alpha Vantage API info: {data['Information']}")

        return data

    def _parse_daily_response(
        self, data: dict[str, Any], symbol: str, lookback_days: int
    ) -> PriceData:
        """
        Parse TIME_SERIES_DAILY response into PriceData.

        Args:
            data: Raw API response dictionary
            symbol: Stock ticker symbol
            lookback_days: Number of days requested

        Returns:
            PriceData with OHLC and volume.
            adjusted_closes, dividends, split_coefficients are set to None
            (require premium TIME_SERIES_DAILY_ADJUSTED endpoint)

        Raises:
            ValueError: If response data is invalid
        """
        time_series = data.get("Time Series (Daily)")
        if not time_series:
            raise ValueError(f"No price data available for {symbol} from Alpha Vantage")

        # Convert to lists (dates are in reverse chronological order)
        all_dates = sorted(time_series.keys())  # Sort chronologically

        # Take the most recent N days
        if len(all_dates) > lookback_days:
            all_dates = all_dates[-lookback_days:]

        dates = []
        opens = []
        highs = []
        lows = []
        closes = []
        volumes = []

        for date_str in all_dates:
            day_data = time_series[date_str]
            dates.append(date_str)
            opens.append(round(float(day_data["1. open"]), 2))
            highs.append(round(float(day_data["2. high"]), 2))
            lows.append(round(float(day_data["3. low"]), 2))
            closes.append(round(float(day_data["4. close"]), 2))
            volumes.append(int(float(day_data["5. volume"])))

        logger.info(
            f"Parsed {len(dates)} days of price data for {symbol} ({dates[0]} to {dates[-1]})"
        )

        # Validate data quality
        self._validate_price_data(opens, highs, lows, closes)

        return PriceData(
            dates=dates,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            adjusted_closes=None,
            volumes=volumes,
            dividends=None,
            split_coefficients=None,
        )

    def _validate_price_data(self, opens: list, highs: list, lows: list, closes: list) -> None:
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
                    f"high={highs[i]}, low={lows[i]} ({highs[i] / lows[i]:.2f}x)"
                )

    def get_usage_status(self) -> dict[str, Any]:
        """
        Get current Alpha Vantage API usage status.

        Returns:
            Dictionary with usage information:
            - calls_today: Number of API calls made today
            - daily_limit: Maximum allowed calls per day
            - remaining: Calls remaining today
            - percentage_used: Percentage of daily limit used
        """
        if self._file_cache:
            usage = self._file_cache.get_alpha_vantage_usage_today()
        else:
            usage = 0

        return {
            "calls_today": usage,
            "daily_limit": self.DAILY_LIMIT,
            "remaining": self.DAILY_LIMIT - usage,
            "percentage_used": (usage / self.DAILY_LIMIT) * 100,
        }

    def close(self) -> None:
        """Close the HTTP session."""
        self._session.close()
        logger.info("AlphaVantageClient session closed")

    def __enter__(self) -> "AlphaVantageClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensures cleanup."""
        self.close()
