"""HTTP client for Finnhub API interaction."""

import time
import logging
from typing import Dict, Any
import requests

from .config import FinnhubConfig


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

    def __enter__(self) -> "FinnhubClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensures cleanup."""
        self.close()
