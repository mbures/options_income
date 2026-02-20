"""API Client for Wheel Strategy Server.

This module provides a comprehensive HTTP client for interacting with the
Wheel Strategy API server, including portfolio, wheel, trade, recommendation,
and position management.
"""

import logging
import time
from typing import Any, Optional

import httpx

from src.server.models import (
    PortfolioCreate,
    PortfolioResponse,
    PortfolioSummary,
    WheelCreate,
    WheelResponse,
    WheelState,
    WheelUpdate,
)
from src.server.models.position import (
    BatchPositionResponse,
    PositionStatusResponse,
    RiskAssessmentResponse,
)
from src.server.models.recommendation import (
    BatchRecommendationResponse,
    RecommendationResponse,
)
from src.server.models.trade import (
    TradeCloseRequest,
    TradeCreate,
    TradeExpireRequest,
    TradeResponse,
)

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base exception for API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, detail: Any = None):
        """Initialize API error.

        Args:
            message: Error message
            status_code: HTTP status code if applicable
            detail: Additional error details
        """
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.message)


class APIConnectionError(APIError):
    """Exception raised when connection to API fails."""

    pass


class APIValidationError(APIError):
    """Exception raised when API returns validation error (422)."""

    pass


class APIServerError(APIError):
    """Exception raised when API returns server error (5xx)."""

    pass


class WheelStrategyAPIClient:
    """HTTP client for Wheel Strategy API.

    Provides methods for interacting with all API endpoints including
    portfolios, wheels, trades, recommendations, and positions.

    Attributes:
        base_url: Base URL for API server
        timeout: Request timeout in seconds
        _client: Underlying httpx Client
        _last_health_check: Timestamp of last health check
        _is_healthy: Cached health status
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: int = 30,
    ):
        """Initialize API client.

        Args:
            base_url: Base URL for API server (default: http://localhost:8000)
            timeout: Request timeout in seconds (default: 30)

        Example:
            >>> client = WheelStrategyAPIClient("http://localhost:8000")
            >>> portfolios = client.list_portfolios()
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            follow_redirects=True,
        )
        self._last_health_check: Optional[float] = None
        self._is_healthy: bool = False

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def close(self):
        """Close the underlying HTTP client."""
        self._client.close()

    def _make_request(
        self,
        method: str,
        endpoint: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Any:
        """Make HTTP request and handle errors.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            json: JSON request body
            params: Query parameters

        Returns:
            Response data (dict, list, or None)

        Raises:
            APIConnectionError: If connection fails
            APIValidationError: If validation fails (422)
            APIServerError: If server error occurs (5xx)
            APIError: For other HTTP errors
        """
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}{endpoint}"

        try:
            response = self._client.request(
                method=method,
                url=url,
                json=json,
                params=params,
            )

            # Handle successful responses
            if response.status_code in (200, 201):
                return response.json() if response.text else None

            # Handle no content (204)
            if response.status_code == 204:
                return None

            # Handle errors
            error_detail = None
            try:
                error_data = response.json()
                if isinstance(error_data, dict):
                    error_detail = error_data.get("detail", error_data.get("message"))
            except Exception:
                error_detail = response.text

            # Validation errors (422)
            if response.status_code == 422:
                raise APIValidationError(
                    message=f"Validation error: {error_detail}",
                    status_code=422,
                    detail=error_detail,
                )

            # Client errors (4xx)
            if 400 <= response.status_code < 500:
                raise APIError(
                    message=f"API error: {error_detail}",
                    status_code=response.status_code,
                    detail=error_detail,
                )

            # Server errors (5xx)
            if response.status_code >= 500:
                raise APIServerError(
                    message=f"Server error: {error_detail}",
                    status_code=response.status_code,
                    detail=error_detail,
                )

            # Other errors
            response.raise_for_status()
            return response.json() if response.text else None

        except httpx.ConnectError as e:
            raise APIConnectionError(
                message=f"Failed to connect to API server at {self.base_url}: {str(e)}"
            ) from e
        except httpx.TimeoutException as e:
            raise APIConnectionError(
                message=f"Request timed out after {self.timeout}s: {str(e)}"
            ) from e
        except (APIError, APIConnectionError, APIValidationError, APIServerError):
            raise
        except Exception as e:
            raise APIError(
                message=f"Unexpected error during API request: {str(e)}"
            ) from e

    # Health and connectivity methods

    def health_check(self) -> bool:
        """Check if API server is healthy and responding.

        Uses a short timeout (5 seconds) and caches result for 30 seconds
        to avoid repeated checks.

        Returns:
            True if server is healthy, False otherwise

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> if client.health_check():
            ...     print("Server is healthy")
        """
        # Return cached result if recent (within 30 seconds)
        if self._last_health_check and (time.time() - self._last_health_check) < 30:
            return self._is_healthy

        try:
            # Use short timeout for health check
            response = self._client.get("/health", timeout=5.0)
            self._is_healthy = response.status_code == 200
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            self._is_healthy = False

        self._last_health_check = time.time()
        return self._is_healthy

    def is_connected(self) -> bool:
        """Check if API server is reachable.

        Alias for health_check() for clarity.

        Returns:
            True if server is reachable, False otherwise

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> if not client.is_connected():
            ...     print("Server is not available")
        """
        return self.health_check()

    @classmethod
    def create_with_fallback(
        cls, api_url: str, timeout: int = 30
    ) -> Optional["WheelStrategyAPIClient"]:
        """Create client if API is available, return None for fallback mode.

        Attempts to connect to the API server and returns a client instance
        if successful. Returns None if the server is unavailable, allowing
        the caller to fall back to direct mode.

        Args:
            api_url: API server URL
            timeout: Request timeout in seconds

        Returns:
            WheelStrategyAPIClient instance if server is available, None otherwise

        Example:
            >>> client = WheelStrategyAPIClient.create_with_fallback("http://localhost:8000")
            >>> if client:
            ...     # Use API mode
            ...     portfolios = client.list_portfolios()
            ... else:
            ...     # Fall back to direct mode
            ...     print("API not available, using direct mode")
        """
        try:
            client = cls(base_url=api_url, timeout=timeout)
            if client.health_check():
                logger.info(f"Successfully connected to API server at {api_url}")
                return client
            else:
                logger.warning(f"API server at {api_url} is not healthy")
                client.close()
                return None
        except Exception as e:
            logger.warning(f"Failed to connect to API server: {e}")
            return None

    # Portfolio methods

    def list_portfolios(self) -> list[PortfolioResponse]:
        """List all portfolios.

        Returns:
            List of portfolio data

        Raises:
            APIError: If request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> portfolios = client.list_portfolios()
            >>> for p in portfolios:
            ...     print(f"{p.name}: {p.wheel_count} wheels")
        """
        data = self._make_request("GET", "/api/v1/portfolios/")
        return [PortfolioResponse(**item) for item in data]

    def create_portfolio(
        self, name: str, description: Optional[str] = None, default_capital: Optional[float] = None
    ) -> PortfolioResponse:
        """Create a new portfolio.

        Args:
            name: Portfolio name
            description: Optional description
            default_capital: Optional default capital allocation

        Returns:
            Created portfolio data

        Raises:
            APIValidationError: If validation fails
            APIError: If request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> portfolio = client.create_portfolio(
            ...     name="Trading Portfolio",
            ...     default_capital=50000.0
            ... )
        """
        payload = PortfolioCreate(
            name=name,
            description=description,
            default_capital=default_capital,
        ).model_dump(exclude_none=True)
        data = self._make_request("POST", "/api/v1/portfolios/", json=payload)
        return PortfolioResponse(**data)

    def get_portfolio(self, portfolio_id: str) -> PortfolioResponse:
        """Get portfolio by ID.

        Args:
            portfolio_id: Portfolio identifier

        Returns:
            Portfolio data

        Raises:
            APIError: If portfolio not found or request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> portfolio = client.get_portfolio("123e4567-e89b-12d3-a456-426614174000")
        """
        data = self._make_request("GET", f"/api/v1/portfolios/{portfolio_id}")
        return PortfolioResponse(**data)

    def get_portfolio_summary(self, portfolio_id: str) -> PortfolioSummary:
        """Get portfolio with summary statistics.

        Args:
            portfolio_id: Portfolio identifier

        Returns:
            Portfolio summary data

        Raises:
            APIError: If portfolio not found or request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> summary = client.get_portfolio_summary("123e4567-e89b-12d3-a456-426614174000")
            >>> print(f"Active wheels: {summary.active_wheels}/{summary.total_wheels}")
        """
        data = self._make_request("GET", f"/api/v1/portfolios/{portfolio_id}/summary")
        return PortfolioSummary(**data)

    def delete_portfolio(self, portfolio_id: str) -> None:
        """Delete portfolio and all associated wheels.

        Args:
            portfolio_id: Portfolio identifier

        Raises:
            APIError: If portfolio not found or request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> client.delete_portfolio("123e4567-e89b-12d3-a456-426614174000")
        """
        self._make_request("DELETE", f"/api/v1/portfolios/{portfolio_id}")

    # Wheel methods

    def create_wheel(
        self,
        portfolio_id: str,
        symbol: str,
        capital: float,
        profile: str = "conservative",
    ) -> WheelResponse:
        """Create a new wheel in portfolio.

        Args:
            portfolio_id: Parent portfolio identifier
            symbol: Stock ticker symbol
            capital: Capital allocated to wheel
            profile: Strike selection profile (conservative, moderate, aggressive)

        Returns:
            Created wheel data

        Raises:
            APIValidationError: If validation fails
            APIError: If request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> wheel = client.create_wheel(
            ...     portfolio_id="123e4567-e89b-12d3-a456-426614174000",
            ...     symbol="AAPL",
            ...     capital=10000.0,
            ...     profile="moderate"
            ... )
        """
        payload = WheelCreate(
            symbol=symbol,
            capital_allocated=capital,
            profile=profile,
        ).model_dump()
        data = self._make_request(
            "POST",
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json=payload,
        )
        return WheelResponse(**data)

    def list_wheels(
        self, portfolio_id: str, active_only: bool = True
    ) -> list[WheelResponse]:
        """List wheels in portfolio.

        Args:
            portfolio_id: Parent portfolio identifier
            active_only: If True, only return active wheels

        Returns:
            List of wheel data

        Raises:
            APIError: If request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> wheels = client.list_wheels("123e4567-e89b-12d3-a456-426614174000")
            >>> for w in wheels:
            ...     print(f"{w.symbol}: {w.state}")
        """
        params = {"active_only": active_only}
        data = self._make_request(
            "GET",
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            params=params,
        )
        return [WheelResponse(**item) for item in data]

    def get_wheel(self, wheel_id: int) -> WheelResponse:
        """Get wheel by ID.

        Args:
            wheel_id: Wheel identifier

        Returns:
            Wheel data

        Raises:
            APIError: If wheel not found or request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> wheel = client.get_wheel(1)
        """
        data = self._make_request("GET", f"/api/v1/wheels/{wheel_id}")
        return WheelResponse(**data)

    def get_wheel_state(self, wheel_id: int) -> WheelState:
        """Get wheel current state.

        Args:
            wheel_id: Wheel identifier

        Returns:
            Wheel state data

        Raises:
            APIError: If wheel not found or request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> state = client.get_wheel_state(1)
            >>> print(f"State: {state.state}, Shares: {state.shares_held}")
        """
        data = self._make_request("GET", f"/api/v1/wheels/{wheel_id}/state")
        return WheelState(**data)

    def update_wheel(self, wheel_id: int, updates: dict[str, Any]) -> WheelResponse:
        """Update wheel.

        Args:
            wheel_id: Wheel identifier
            updates: Dictionary of fields to update

        Returns:
            Updated wheel data

        Raises:
            APIValidationError: If validation fails
            APIError: If wheel not found or request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> wheel = client.update_wheel(1, {"capital_allocated": 15000.0})
        """
        payload = WheelUpdate(**updates).model_dump(exclude_none=True)
        data = self._make_request("PUT", f"/api/v1/wheels/{wheel_id}", json=payload)
        return WheelResponse(**data)

    def delete_wheel(self, wheel_id: int) -> None:
        """Delete wheel and all associated trades.

        Args:
            wheel_id: Wheel identifier

        Raises:
            APIError: If wheel not found or request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> client.delete_wheel(1)
        """
        self._make_request("DELETE", f"/api/v1/wheels/{wheel_id}")

    def get_wheel_by_symbol(
        self, symbol: str, portfolio_id: Optional[str] = None
    ) -> Optional[WheelResponse]:
        """Get wheel by symbol (helper method).

        Args:
            symbol: Stock ticker symbol
            portfolio_id: Optional portfolio to search in

        Returns:
            Wheel data if found, None otherwise

        Raises:
            APIError: If request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> wheel = client.get_wheel_by_symbol("AAPL")
            >>> if wheel:
            ...     print(f"Found wheel: {wheel.id}")
        """
        if portfolio_id:
            wheels = self.list_wheels(portfolio_id, active_only=False)
        else:
            # Get all portfolios and search through wheels
            portfolios = self.list_portfolios()
            wheels = []
            for portfolio in portfolios:
                wheels.extend(self.list_wheels(portfolio.id, active_only=False))

        symbol_upper = symbol.upper()
        for wheel in wheels:
            if wheel.symbol == symbol_upper:
                return wheel
        return None

    # Trade methods

    def record_trade(
        self,
        wheel_id: int,
        direction: str,
        strike: float,
        expiration: str,
        premium: float,
        contracts: int = 1,
    ) -> TradeResponse:
        """Record a new trade.

        Args:
            wheel_id: Parent wheel identifier
            direction: Trade direction (put or call)
            strike: Strike price
            expiration: Expiration date (YYYY-MM-DD)
            premium: Premium per share
            contracts: Number of contracts (default: 1)

        Returns:
            Created trade data

        Raises:
            APIValidationError: If validation fails
            APIError: If request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> trade = client.record_trade(
            ...     wheel_id=1,
            ...     direction="put",
            ...     strike=150.0,
            ...     expiration="2026-03-20",
            ...     premium=2.50
            ... )
        """
        payload = TradeCreate(
            direction=direction,
            strike=strike,
            expiration_date=expiration,
            premium_per_share=premium,
            contracts=contracts,
        ).model_dump()
        data = self._make_request("POST", f"/api/v1/wheels/{wheel_id}/trades", json=payload)
        return TradeResponse(**data)

    def list_trades(
        self, wheel_id: int, outcome: Optional[str] = None
    ) -> list[TradeResponse]:
        """List trades for wheel.

        Args:
            wheel_id: Parent wheel identifier
            outcome: Optional filter by outcome

        Returns:
            List of trade data

        Raises:
            APIError: If request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> trades = client.list_trades(1, outcome="open")
        """
        params = {}
        if outcome:
            params["outcome"] = outcome
        data = self._make_request("GET", f"/api/v1/wheels/{wheel_id}/trades", params=params)
        return [TradeResponse(**item) for item in data]

    def get_trade(self, trade_id: int) -> TradeResponse:
        """Get trade by ID.

        Args:
            trade_id: Trade identifier

        Returns:
            Trade data

        Raises:
            APIError: If trade not found or request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> trade = client.get_trade(1)
        """
        data = self._make_request("GET", f"/api/v1/trades/{trade_id}")
        return TradeResponse(**data)

    def expire_trade(self, trade_id: int, price_at_expiry: float) -> TradeResponse:
        """Record trade expiration.

        Args:
            trade_id: Trade identifier
            price_at_expiry: Stock price at expiration

        Returns:
            Updated trade data

        Raises:
            APIError: If request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> trade = client.expire_trade(1, 148.50)
        """
        payload = TradeExpireRequest(price_at_expiry=price_at_expiry).model_dump()
        data = self._make_request("POST", f"/api/v1/trades/{trade_id}/expire", json=payload)
        return TradeResponse(**data)

    def close_trade(self, trade_id: int, close_price: float) -> TradeResponse:
        """Close trade early.

        Args:
            trade_id: Trade identifier
            close_price: Price paid to close position (per share)

        Returns:
            Updated trade data

        Raises:
            APIError: If request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> trade = client.close_trade(1, 1.25)
        """
        payload = TradeCloseRequest(close_price=close_price).model_dump()
        data = self._make_request("POST", f"/api/v1/trades/{trade_id}/close", json=payload)
        return TradeResponse(**data)

    # Recommendation methods

    def get_recommendation(
        self,
        wheel_id: int,
        expiration_date: Optional[str] = None,
        use_cache: bool = True,
        max_dte: int = 14,
    ) -> RecommendationResponse:
        """Get recommendation for wheel.

        Args:
            wheel_id: Wheel identifier
            expiration_date: Optional target expiration date (YYYY-MM-DD)
            use_cache: Whether to use cached recommendations
            max_dte: Maximum days to expiration search window

        Returns:
            Recommendation data

        Raises:
            APIError: If request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> rec = client.get_recommendation(1)
            >>> print(f"{rec.direction} @ ${rec.strike}")
        """
        params = {"use_cache": use_cache, "max_dte": max_dte}
        if expiration_date:
            params["expiration_date"] = expiration_date
        data = self._make_request("GET", f"/api/v1/wheels/{wheel_id}/recommend", params=params)
        return RecommendationResponse(**data)

    def get_batch_recommendations(
        self,
        symbols: list[str],
        expiration_date: Optional[str] = None,
        profile: str = "conservative",
    ) -> BatchRecommendationResponse:
        """Get batch recommendations for multiple symbols.

        Args:
            symbols: List of stock ticker symbols
            expiration_date: Optional target expiration date
            profile: Strike selection profile

        Returns:
            Batch recommendation response

        Raises:
            APIError: If request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> batch = client.get_batch_recommendations(["AAPL", "MSFT"])
        """
        payload = {
            "symbols": symbols,
            "expiration_date": expiration_date,
            "profile": profile,
        }
        data = self._make_request("POST", "/api/v1/wheels/recommend/batch", json=payload)
        return BatchRecommendationResponse(**data)

    # Position methods

    def get_position_status(
        self, wheel_id: int, force_refresh: bool = False
    ) -> PositionStatusResponse:
        """Get position status for wheel.

        Args:
            wheel_id: Wheel identifier
            force_refresh: Bypass cache and fetch fresh price data

        Returns:
            Position status data

        Raises:
            APIError: If wheel not found or has no open position

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> status = client.get_position_status(1)
            >>> print(f"Risk: {status.risk_level}, Moneyness: {status.moneyness_pct}%")
        """
        params = {"force_refresh": force_refresh}
        data = self._make_request("GET", f"/api/v1/wheels/{wheel_id}/position", params=params)
        return PositionStatusResponse(**data)

    def get_portfolio_positions(
        self, portfolio_id: str, filters: Optional[dict[str, Any]] = None
    ) -> BatchPositionResponse:
        """Get all open positions in portfolio.

        Args:
            portfolio_id: Portfolio identifier
            filters: Optional filters (risk_level, min_dte, max_dte)

        Returns:
            Batch position response

        Raises:
            APIError: If request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> positions = client.get_portfolio_positions(
            ...     "123e4567-e89b-12d3-a456-426614174000",
            ...     filters={"risk_level": "HIGH"}
            ... )
        """
        params = filters or {}
        data = self._make_request(
            "GET",
            f"/api/v1/portfolios/{portfolio_id}/positions",
            params=params,
        )
        return BatchPositionResponse(**data)

    def get_all_positions(
        self, filters: Optional[dict[str, Any]] = None
    ) -> BatchPositionResponse:
        """Get all open positions across all portfolios.

        Args:
            filters: Optional filters (risk_level, min_dte, max_dte)

        Returns:
            Batch position response

        Raises:
            APIError: If request fails

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> positions = client.get_all_positions(filters={"risk_level": "HIGH"})
            >>> print(f"High risk positions: {positions.high_risk_count}")
        """
        params = filters or {}
        data = self._make_request("GET", "/api/v1/positions/open", params=params)
        return BatchPositionResponse(**data)

    def get_risk_assessment(
        self, wheel_id: int, force_refresh: bool = False
    ) -> RiskAssessmentResponse:
        """Get risk assessment for wheel.

        Args:
            wheel_id: Wheel identifier
            force_refresh: Bypass cache and fetch fresh price data

        Returns:
            Risk assessment data

        Raises:
            APIError: If wheel not found or has no open position

        Example:
            >>> client = WheelStrategyAPIClient()
            >>> risk = client.get_risk_assessment(1)
            >>> print(f"{risk.risk_icon} {risk.risk_description}")
        """
        params = {"force_refresh": force_refresh}
        data = self._make_request("GET", f"/api/v1/wheels/{wheel_id}/risk", params=params)
        return RiskAssessmentResponse(**data)
