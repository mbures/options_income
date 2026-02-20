"""Tests for Wheel Strategy API Client.

Comprehensive test suite for the API client including successful requests,
error handling, and connection detection.
"""

import json
from datetime import datetime
from typing import Any

import httpx
import pytest
from pytest_httpx import HTTPXMock

from src.wheel.api_client import (
    APIConnectionError,
    APIError,
    APIServerError,
    APIValidationError,
    WheelStrategyAPIClient,
)


@pytest.fixture
def api_client():
    """Create API client for testing.

    Returns:
        WheelStrategyAPIClient instance
    """
    return WheelStrategyAPIClient(base_url="http://testserver", timeout=5)


@pytest.fixture
def mock_portfolio_response() -> dict[str, Any]:
    """Mock portfolio response data.

    Returns:
        Dictionary with portfolio data
    """
    return {
        "id": "test-portfolio-id",
        "name": "Test Portfolio",
        "description": "Test description",
        "default_capital": 50000.0,
        "created_at": "2026-02-01T10:00:00",
        "updated_at": "2026-02-01T10:00:00",
        "wheel_count": 5,
    }


@pytest.fixture
def mock_wheel_response() -> dict[str, Any]:
    """Mock wheel response data.

    Returns:
        Dictionary with wheel data
    """
    return {
        "id": 1,
        "portfolio_id": "test-portfolio-id",
        "symbol": "AAPL",
        "state": "cash",
        "shares_held": 0,
        "capital_allocated": 10000.0,
        "cost_basis": None,
        "profile": "moderate",
        "created_at": "2026-02-01T10:00:00",
        "updated_at": "2026-02-01T10:00:00",
        "is_active": True,
        "trade_count": 0,
    }


@pytest.fixture
def mock_trade_response() -> dict[str, Any]:
    """Mock trade response data.

    Returns:
        Dictionary with trade data
    """
    return {
        "id": 1,
        "wheel_id": 1,
        "symbol": "AAPL",
        "direction": "put",
        "strike": 150.0,
        "expiration_date": "2026-03-20",
        "premium_per_share": 2.50,
        "contracts": 1,
        "total_premium": 250.0,
        "opened_at": "2026-02-01T10:00:00",
        "closed_at": None,
        "outcome": "open",
        "price_at_expiry": None,
        "close_price": None,
    }


# Health Check Tests


def test_health_check_success(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test successful health check."""
    httpx_mock.add_response(
        url="http://testserver/health",
        json={"status": "healthy", "timestamp": "2026-02-01T10:00:00"},
        status_code=200,
    )

    result = api_client.health_check()
    assert result is True
    assert api_client._is_healthy is True


def test_health_check_failure(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test failed health check."""
    httpx_mock.add_response(
        url="http://testserver/health",
        status_code=500,
    )

    result = api_client.health_check()
    assert result is False
    assert api_client._is_healthy is False


def test_health_check_timeout(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test health check timeout handling."""
    httpx_mock.add_exception(httpx.TimeoutException("Timeout"))

    result = api_client.health_check()
    assert result is False


def test_is_connected(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test is_connected method."""
    httpx_mock.add_response(
        url="http://testserver/health",
        json={"status": "healthy"},
        status_code=200,
    )

    assert api_client.is_connected() is True


def test_health_check_caching(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test health check result is cached."""
    httpx_mock.add_response(
        url="http://testserver/health",
        json={"status": "healthy"},
        status_code=200,
    )

    # First call should make request
    result1 = api_client.health_check()
    assert result1 is True

    # Second call within 30 seconds should use cache
    result2 = api_client.health_check()
    assert result2 is True

    # Only one request should have been made
    assert len(httpx_mock.get_requests()) == 1


def test_create_with_fallback_success(httpx_mock: HTTPXMock):
    """Test successful client creation with fallback."""
    httpx_mock.add_response(
        url="http://testserver/health",
        json={"status": "healthy"},
        status_code=200,
    )

    client = WheelStrategyAPIClient.create_with_fallback("http://testserver", timeout=5)
    assert client is not None
    client.close()


def test_create_with_fallback_failure(httpx_mock: HTTPXMock):
    """Test client creation fallback when server unavailable."""
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

    client = WheelStrategyAPIClient.create_with_fallback("http://testserver", timeout=5)
    assert client is None


# Portfolio Tests


def test_list_portfolios_success(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient, mock_portfolio_response: dict
):
    """Test listing portfolios returns correct data."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/portfolios/",
        json=[mock_portfolio_response],
        status_code=200,
    )

    portfolios = api_client.list_portfolios()
    assert len(portfolios) == 1
    assert portfolios[0].id == "test-portfolio-id"
    assert portfolios[0].name == "Test Portfolio"
    assert portfolios[0].wheel_count == 5


def test_create_portfolio_success(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient, mock_portfolio_response: dict
):
    """Test creating portfolio."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/portfolios/",
        json=mock_portfolio_response,
        status_code=201,
    )

    portfolio = api_client.create_portfolio(
        name="Test Portfolio",
        description="Test description",
        default_capital=50000.0,
    )
    assert portfolio.name == "Test Portfolio"
    assert portfolio.default_capital == 50000.0


def test_get_portfolio_success(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient, mock_portfolio_response: dict
):
    """Test getting portfolio by ID."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/portfolios/test-portfolio-id",
        json=mock_portfolio_response,
        status_code=200,
    )

    portfolio = api_client.get_portfolio("test-portfolio-id")
    assert portfolio.id == "test-portfolio-id"


def test_get_portfolio_not_found(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test 404 error when portfolio not found."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/portfolios/invalid-id",
        json={"detail": "Portfolio not found"},
        status_code=404,
    )

    with pytest.raises(APIError) as exc_info:
        api_client.get_portfolio("invalid-id")
    assert exc_info.value.status_code == 404


def test_get_portfolio_summary_success(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient
):
    """Test getting portfolio summary."""
    summary_data = {
        "id": "test-portfolio-id",
        "name": "Test Portfolio",
        "description": "Test",
        "default_capital": 50000.0,
        "created_at": "2026-02-01T10:00:00",
        "updated_at": "2026-02-01T10:00:00",
        "wheel_count": 5,
        "total_wheels": 5,
        "active_wheels": 4,
        "total_capital_allocated": 40000.0,
        "total_positions_value": 35000.0,
    }
    httpx_mock.add_response(
        url="http://testserver/api/v1/portfolios/test-portfolio-id/summary",
        json=summary_data,
        status_code=200,
    )

    summary = api_client.get_portfolio_summary("test-portfolio-id")
    assert summary.active_wheels == 4
    assert summary.total_capital_allocated == 40000.0


def test_delete_portfolio_success(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test deleting portfolio."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/portfolios/test-portfolio-id",
        status_code=204,
    )

    api_client.delete_portfolio("test-portfolio-id")
    # No exception means success


# Wheel Tests


def test_create_wheel_success(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient, mock_wheel_response: dict
):
    """Test creating wheel."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/portfolios/test-portfolio-id/wheels",
        json=mock_wheel_response,
        status_code=201,
    )

    wheel = api_client.create_wheel(
        portfolio_id="test-portfolio-id",
        symbol="AAPL",
        capital=10000.0,
        profile="moderate",
    )
    assert wheel.symbol == "AAPL"
    assert wheel.capital_allocated == 10000.0


def test_create_wheel_validation_error(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test 422 validation error handling from server."""
    error_detail = {
        "detail": [
            {
                "loc": ["body", "capital_allocated"],
                "msg": "value must be greater than 0",
                "type": "value_error.number.not_gt",
            }
        ]
    }
    httpx_mock.add_response(
        url="http://testserver/api/v1/portfolios/test-portfolio-id/wheels",
        json=error_detail,
        status_code=422,
    )

    # This will pass client-side validation but fail server-side
    # We'll mock it to simulate server rejection
    with pytest.raises(APIValidationError) as exc_info:
        # Use a symbol that passes client validation but server will reject
        api_client._make_request(
            "POST",
            "/api/v1/portfolios/test-portfolio-id/wheels",
            json={"symbol": "AAPL", "capital_allocated": -1000, "profile": "moderate"}
        )
    assert exc_info.value.status_code == 422


def test_list_wheels_success(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient, mock_wheel_response: dict
):
    """Test listing wheels."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/portfolios/test-portfolio-id/wheels?active_only=true",
        json=[mock_wheel_response],
        status_code=200,
    )

    wheels = api_client.list_wheels("test-portfolio-id", active_only=True)
    assert len(wheels) == 1
    assert wheels[0].symbol == "AAPL"


def test_get_wheel_success(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient, mock_wheel_response: dict
):
    """Test getting wheel by ID."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/wheels/1",
        json=mock_wheel_response,
        status_code=200,
    )

    wheel = api_client.get_wheel(1)
    assert wheel.id == 1
    assert wheel.symbol == "AAPL"


def test_get_wheel_state_success(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test getting wheel state."""
    state_data = {
        "id": 1,
        "symbol": "AAPL",
        "state": "cash_put_open",
        "shares_held": 0,
        "cost_basis": None,
        "open_trade": None,
    }
    httpx_mock.add_response(
        url="http://testserver/api/v1/wheels/1/state",
        json=state_data,
        status_code=200,
    )

    state = api_client.get_wheel_state(1)
    assert state.state == "cash_put_open"
    assert state.shares_held == 0


def test_update_wheel_success(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient, mock_wheel_response: dict
):
    """Test updating wheel."""
    updated_wheel = mock_wheel_response.copy()
    updated_wheel["capital_allocated"] = 15000.0
    httpx_mock.add_response(
        url="http://testserver/api/v1/wheels/1",
        json=updated_wheel,
        status_code=200,
    )

    wheel = api_client.update_wheel(1, {"capital_allocated": 15000.0})
    assert wheel.capital_allocated == 15000.0


def test_delete_wheel_success(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test deleting wheel."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/wheels/1",
        status_code=204,
    )

    api_client.delete_wheel(1)
    # No exception means success


def test_get_wheel_by_symbol_found(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient, mock_wheel_response: dict
):
    """Test finding wheel by symbol."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/portfolios/test-portfolio-id/wheels?active_only=false",
        json=[mock_wheel_response],
        status_code=200,
    )

    wheel = api_client.get_wheel_by_symbol("AAPL", portfolio_id="test-portfolio-id")
    assert wheel is not None
    assert wheel.symbol == "AAPL"


def test_get_wheel_by_symbol_not_found(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient
):
    """Test symbol not found returns None."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/portfolios/test-portfolio-id/wheels?active_only=false",
        json=[],
        status_code=200,
    )

    wheel = api_client.get_wheel_by_symbol("NOTFOUND", portfolio_id="test-portfolio-id")
    assert wheel is None


# Trade Tests


def test_record_trade_success(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient, mock_trade_response: dict
):
    """Test recording trade."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/wheels/1/trades",
        json=mock_trade_response,
        status_code=201,
    )

    trade = api_client.record_trade(
        wheel_id=1,
        direction="put",
        strike=150.0,
        expiration="2026-03-20",
        premium=2.50,
        contracts=1,
    )
    assert trade.direction == "put"
    assert trade.strike == 150.0


def test_list_trades_success(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient, mock_trade_response: dict
):
    """Test listing trades."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/wheels/1/trades",
        json=[mock_trade_response],
        status_code=200,
    )

    trades = api_client.list_trades(1)
    assert len(trades) == 1
    assert trades[0].direction == "put"


def test_list_trades_with_outcome_filter(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient, mock_trade_response: dict
):
    """Test listing trades with outcome filter."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/wheels/1/trades?outcome=open",
        json=[mock_trade_response],
        status_code=200,
    )

    trades = api_client.list_trades(1, outcome="open")
    assert len(trades) == 1


def test_get_trade_success(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient, mock_trade_response: dict
):
    """Test getting trade by ID."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/trades/1",
        json=mock_trade_response,
        status_code=200,
    )

    trade = api_client.get_trade(1)
    assert trade.id == 1


def test_expire_trade_success(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient, mock_trade_response: dict
):
    """Test expiring trade."""
    expired_trade = mock_trade_response.copy()
    expired_trade["outcome"] = "expired_worthless"
    expired_trade["price_at_expiry"] = 148.50
    httpx_mock.add_response(
        url="http://testserver/api/v1/trades/1/expire",
        json=expired_trade,
        status_code=200,
    )

    trade = api_client.expire_trade(1, 148.50)
    assert trade.outcome == "expired_worthless"


def test_close_trade_success(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient, mock_trade_response: dict
):
    """Test closing trade early."""
    closed_trade = mock_trade_response.copy()
    closed_trade["outcome"] = "closed_early"
    closed_trade["close_price"] = 1.25
    httpx_mock.add_response(
        url="http://testserver/api/v1/trades/1/close",
        json=closed_trade,
        status_code=200,
    )

    trade = api_client.close_trade(1, 1.25)
    assert trade.outcome == "closed_early"


# Recommendation Tests


def test_get_recommendation_success(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test getting recommendation."""
    rec_data = {
        "wheel_id": 1,
        "symbol": "AAPL",
        "current_state": "cash",
        "direction": "put",
        "strike": 145.0,
        "expiration_date": "2026-03-21",
        "premium_per_share": 2.50,
        "total_premium": 250.0,
        "probability_itm": 0.15,
        "probability_otm": 0.85,
        "annualized_return": 24.5,
        "days_to_expiry": 30,
        "warnings": [],
        "has_warnings": False,
        "current_price": 150.0,
        "volatility": 0.28,
        "profile": "moderate",
        "recommended_at": "2026-02-01T10:00:00",
    }
    httpx_mock.add_response(
        url="http://testserver/api/v1/wheels/1/recommend?use_cache=true",
        json=rec_data,
        status_code=200,
    )

    rec = api_client.get_recommendation(1)
    assert rec.direction == "put"
    assert rec.strike == 145.0


def test_get_recommendation_with_expiration(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient
):
    """Test getting recommendation with expiration date."""
    rec_data = {
        "wheel_id": 1,
        "symbol": "AAPL",
        "current_state": "cash",
        "direction": "put",
        "strike": 145.0,
        "expiration_date": "2026-03-21",
        "premium_per_share": 2.50,
        "total_premium": 250.0,
        "probability_itm": 0.15,
        "probability_otm": 0.85,
        "annualized_return": 24.5,
        "days_to_expiry": 30,
        "warnings": [],
        "has_warnings": False,
        "current_price": 150.0,
        "volatility": 0.28,
        "profile": "moderate",
        "recommended_at": "2026-02-01T10:00:00",
    }
    httpx_mock.add_response(
        url="http://testserver/api/v1/wheels/1/recommend?use_cache=true&expiration_date=2026-03-21",
        json=rec_data,
        status_code=200,
    )

    rec = api_client.get_recommendation(1, expiration_date="2026-03-21")
    assert rec.expiration_date == "2026-03-21"


def test_get_batch_recommendations_success(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient
):
    """Test getting batch recommendations."""
    batch_data = {
        "recommendations": [
            {
                "wheel_id": 1,
                "symbol": "AAPL",
                "current_state": "cash",
                "direction": "put",
                "strike": 145.0,
                "expiration_date": "2026-03-21",
                "premium_per_share": 2.50,
                "total_premium": 250.0,
                "probability_itm": 0.15,
                "probability_otm": 0.85,
                "annualized_return": 24.5,
                "days_to_expiry": 30,
                "warnings": [],
                "has_warnings": False,
                "current_price": 150.0,
                "volatility": 0.28,
                "profile": "moderate",
                "recommended_at": "2026-02-01T10:00:00",
            }
        ],
        "errors": {},
        "requested_at": "2026-02-01T10:00:00",
    }
    httpx_mock.add_response(
        url="http://testserver/api/v1/wheels/recommend/batch",
        json=batch_data,
        status_code=200,
    )

    batch = api_client.get_batch_recommendations(["AAPL", "MSFT"])
    assert len(batch.recommendations) == 1
    assert batch.recommendations[0].symbol == "AAPL"


# Position Tests


def test_get_position_status_success(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test getting position status."""
    position_data = {
        "wheel_id": 1,
        "trade_id": 1,
        "symbol": "AAPL",
        "direction": "put",
        "strike": 150.0,
        "expiration_date": "2026-02-15",
        "dte_calendar": 14,
        "dte_trading": 10,
        "current_price": 155.50,
        "price_vs_strike": 5.50,
        "is_itm": False,
        "is_otm": True,
        "moneyness_pct": 3.67,
        "moneyness_label": "OTM by 3.7%",
        "risk_level": "LOW",
        "risk_icon": "🟢",
        "risk_description": "Low risk",
        "last_updated": "2026-02-01T10:00:00",
        "premium_collected": 250.0,
    }
    httpx_mock.add_response(
        url="http://testserver/api/v1/wheels/1/position?force_refresh=false",
        json=position_data,
        status_code=200,
    )

    status = api_client.get_position_status(1)
    assert status.risk_level == "LOW"
    assert status.moneyness_pct == 3.67


def test_get_portfolio_positions_success(
    httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient
):
    """Test getting portfolio positions."""
    batch_data = {
        "positions": [],
        "total_count": 0,
        "high_risk_count": 0,
        "medium_risk_count": 0,
        "low_risk_count": 0,
    }
    httpx_mock.add_response(
        url="http://testserver/api/v1/portfolios/test-portfolio-id/positions",
        json=batch_data,
        status_code=200,
    )

    positions = api_client.get_portfolio_positions("test-portfolio-id")
    assert positions.total_count == 0


def test_get_all_positions_success(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test getting all positions."""
    batch_data = {
        "positions": [],
        "total_count": 0,
        "high_risk_count": 0,
        "medium_risk_count": 0,
        "low_risk_count": 0,
    }
    httpx_mock.add_response(
        url="http://testserver/api/v1/positions/open",
        json=batch_data,
        status_code=200,
    )

    positions = api_client.get_all_positions()
    assert positions.total_count == 0


def test_get_risk_assessment_success(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test getting risk assessment."""
    risk_data = {
        "wheel_id": 1,
        "symbol": "AAPL",
        "risk_level": "LOW",
        "risk_icon": "🟢",
        "risk_description": "Low risk",
        "is_itm": False,
        "moneyness_pct": 3.67,
        "dte_calendar": 14,
        "current_price": 155.50,
        "strike": 150.0,
        "direction": "put",
    }
    httpx_mock.add_response(
        url="http://testserver/api/v1/wheels/1/risk?force_refresh=false",
        json=risk_data,
        status_code=200,
    )

    risk = api_client.get_risk_assessment(1)
    assert risk.risk_level == "LOW"


# Error Handling Tests


def test_connection_error(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test connection error handling."""
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

    with pytest.raises(APIConnectionError) as exc_info:
        api_client.list_portfolios()
    assert "Failed to connect" in str(exc_info.value)


def test_timeout_error(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test timeout error handling."""
    httpx_mock.add_exception(httpx.TimeoutException("Timeout"))

    with pytest.raises(APIConnectionError) as exc_info:
        api_client.list_portfolios()
    assert "timed out" in str(exc_info.value)


def test_server_error_500(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test 500 server error handling."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/portfolios/",
        json={"detail": "Internal server error"},
        status_code=500,
    )

    with pytest.raises(APIServerError) as exc_info:
        api_client.list_portfolios()
    assert exc_info.value.status_code == 500


def test_generic_api_error(httpx_mock: HTTPXMock, api_client: WheelStrategyAPIClient):
    """Test generic API error handling."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/portfolios/",
        json={"detail": "Bad request"},
        status_code=400,
    )

    with pytest.raises(APIError) as exc_info:
        api_client.list_portfolios()
    assert exc_info.value.status_code == 400


# Context Manager Tests


def test_context_manager(httpx_mock: HTTPXMock):
    """Test client as context manager."""
    httpx_mock.add_response(
        url="http://testserver/api/v1/portfolios/",
        json=[],
        status_code=200,
    )

    with WheelStrategyAPIClient("http://testserver") as client:
        portfolios = client.list_portfolios()
        assert portfolios == []


def test_close_method(api_client: WheelStrategyAPIClient):
    """Test explicit close method."""
    api_client.close()
    # Client should be closed, subsequent requests would fail
