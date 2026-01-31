"""
Base API client with common HTTP functionality.

This module provides a base class for API clients with shared functionality:
- HTTP session management with connection pooling
- Retry logic with exponential backoff
- Error handling and logging
- Request/response logging
- Timeout handling

All API clients (Schwab, Finnhub, etc.) should inherit from this base class
to avoid code duplication and ensure consistent behavior.
"""

import logging
import time
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


class BaseAPIClient:
    """
    Base class for API clients with common HTTP functionality.

    This class provides:
    - Session management with connection pooling
    - Automatic retry with exponential backoff
    - Consistent error handling and logging
    - Request timeout handling

    Subclasses should:
    - Set BASE_URL class attribute
    - Implement authentication if needed
    - Override _handle_error_response() for custom error handling
    - Add domain-specific methods

    Example:
        class MyAPIClient(BaseAPIClient):
            BASE_URL = "https://api.example.com"

            def get_data(self, resource_id: str) -> Dict[str, Any]:
                endpoint = f"/data/{resource_id}"
                return self.get(endpoint)
    """

    BASE_URL: str = ""  # Subclasses must override this

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: int = 30,
    ):
        """
        Initialize base API client.

        Args:
            max_retries: Maximum number of retry attempts for transient errors
            retry_delay: Base delay in seconds between retries (exponential backoff)
            timeout: Request timeout in seconds
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.session = requests.Session()

        # Set default headers
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": f"{self.__class__.__name__}/1.0"
        })

        logger.info(f"{self.__class__.__name__} initialized")

    def _get_full_url(self, endpoint: str) -> str:
        """
        Construct full API URL from endpoint path.

        Args:
            endpoint: API endpoint path (e.g., "/resource/123")

        Returns:
            Full URL with base URL
        """
        if not self.BASE_URL:
            raise ValueError(f"{self.__class__.__name__} must set BASE_URL class attribute")

        # Ensure endpoint starts with /
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"

        # Combine base URL and endpoint
        return f"{self.BASE_URL.rstrip('/')}{endpoint}"

    def _make_request_with_retry(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        retry_count: int = 0,
    ) -> requests.Response:
        """
        Make HTTP request with exponential backoff retry logic.

        This method handles:
        - Network errors (timeout, connection errors)
        - Transient server errors (5xx)
        - Automatic retry with exponential backoff

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full request URL
            params: Query parameters
            json_data: JSON request body
            headers: Additional request headers
            retry_count: Current retry attempt (for internal use)

        Returns:
            HTTP response object

        Raises:
            requests.exceptions.RequestException: If all retry attempts fail
        """
        # Merge additional headers with session headers
        request_headers = self.session.headers.copy()
        if headers:
            request_headers.update(headers)

        # Log request (excluding sensitive data)
        logger.debug(f"{method} {url}")
        if params:
            logger.debug(f"  Params: {params}")

        try:
            # Make request
            response = self.session.request(
                method,
                url,
                headers=request_headers,
                params=params,
                json=json_data,
                timeout=self.timeout,
            )

            # Handle server errors with retry
            if response.status_code >= 500:
                if retry_count < self.max_retries:
                    delay = self._calculate_backoff_delay(retry_count)
                    logger.warning(
                        f"Server error ({response.status_code}). "
                        f"Retrying in {delay}s (attempt {retry_count + 1}/{self.max_retries})"
                    )
                    time.sleep(delay)
                    return self._make_request_with_retry(
                        method, url, params, json_data, headers, retry_count + 1
                    )
                else:
                    logger.error(
                        f"Server error ({response.status_code}) after {self.max_retries} retries"
                    )
                    # Let subclass handle the error
                    self._handle_error_response(response)

            # Log response
            logger.debug(f"Response: {response.status_code}")
            return response

        except requests.exceptions.Timeout:
            if retry_count < self.max_retries:
                delay = self._calculate_backoff_delay(retry_count)
                logger.warning(
                    f"Request timeout. Retrying in {delay}s "
                    f"(attempt {retry_count + 1}/{self.max_retries})"
                )
                time.sleep(delay)
                return self._make_request_with_retry(
                    method, url, params, json_data, headers, retry_count + 1
                )
            else:
                logger.error(f"Request timeout after {self.max_retries} retries")
                raise

        except (requests.exceptions.ConnectionError, requests.exceptions.RequestException) as e:
            if retry_count < self.max_retries:
                delay = self._calculate_backoff_delay(retry_count)
                logger.warning(
                    f"Network error: {e}. Retrying in {delay}s "
                    f"(attempt {retry_count + 1}/{self.max_retries})"
                )
                time.sleep(delay)
                return self._make_request_with_retry(
                    method, url, params, json_data, headers, retry_count + 1
                )
            else:
                logger.error(f"Network error after {self.max_retries} retries: {e}")
                raise

    def _calculate_backoff_delay(self, retry_count: int) -> float:
        """
        Calculate exponential backoff delay.

        Args:
            retry_count: Current retry attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        return self.retry_delay * (2 ** retry_count)

    def _handle_error_response(self, response: requests.Response) -> None:
        """
        Handle error responses from API.

        This method can be overridden by subclasses to provide
        custom error handling for specific status codes.

        Args:
            response: HTTP response with error status code

        Raises:
            requests.exceptions.HTTPError: For unhandled errors
        """
        response.raise_for_status()

    def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> requests.Response:
        """
        Make authenticated GET request.

        Args:
            endpoint: API endpoint path
            params: Query parameters
            headers: Additional request headers

        Returns:
            HTTP response object

        Raises:
            requests.exceptions.RequestException: For network/API errors
        """
        url = self._get_full_url(endpoint)
        return self._make_request_with_retry("GET", url, params=params, headers=headers)

    def post(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> requests.Response:
        """
        Make authenticated POST request.

        Args:
            endpoint: API endpoint path
            json_data: JSON request body
            params: Query parameters
            headers: Additional request headers

        Returns:
            HTTP response object

        Raises:
            requests.exceptions.RequestException: For network/API errors
        """
        url = self._get_full_url(endpoint)

        # Add Content-Type header for POST requests
        post_headers = {"Content-Type": "application/json"}
        if headers:
            post_headers.update(headers)

        return self._make_request_with_retry(
            "POST", url, params=params, json_data=json_data, headers=post_headers
        )

    def close(self) -> None:
        """
        Close the HTTP session and cleanup resources.

        Should be called when done using the client, or use the client
        as a context manager.
        """
        self.session.close()
        logger.info(f"{self.__class__.__name__} closed")

    def __enter__(self) -> "BaseAPIClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensures cleanup."""
        self.close()
