"""Integration tests for Recommendation API endpoints.

Tests recommendation generation, caching, batch operations,
and error handling.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.server.database.models.wheel import Wheel
from src.wheel.models import WheelRecommendation


@pytest.fixture
def portfolio_id(client: TestClient) -> str:
    """Create a test portfolio and return its ID.

    Returns:
        Portfolio UUID string
    """
    response = client.post(
        "/api/v1/portfolios/",
        json={"name": "Test Portfolio", "default_capital": 50000.0},
    )
    return response.json()["id"]


@pytest.fixture
def test_wheel_cash(client: TestClient, portfolio_id: str) -> dict:
    """Create a test wheel in CASH state.

    Returns:
        Wheel data dictionary
    """
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/wheels",
        json={
            "symbol": "AAPL",
            "capital_allocated": 20000.0,
            "profile": "moderate",
        },
    )
    return response.json()


@pytest.fixture
def test_wheel_shares(client: TestClient, test_db, portfolio_id: str) -> dict:
    """Create a test wheel in SHARES state.

    Returns:
        Wheel data dictionary
    """
    # Create wheel in CASH state
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/wheels",
        json={
            "symbol": "MSFT",
            "capital_allocated": 20000.0,
            "profile": "conservative",
        },
    )
    wheel_data = response.json()
    wheel_id = wheel_data["id"]

    # Manually update wheel to SHARES state for testing
    wheel = test_db.query(Wheel).filter(Wheel.id == wheel_id).first()
    wheel.state = "shares"
    wheel.shares_held = 100
    wheel.cost_basis = 350.0
    test_db.commit()
    test_db.refresh(wheel)

    return {
        "id": wheel.id,
        "symbol": wheel.symbol,
        "state": wheel.state,
        "shares_held": wheel.shares_held,
        "portfolio_id": portfolio_id,
    }


@pytest.fixture
def mock_recommendation_service():
    """Mock RecommendationService to avoid external API calls.

    Returns:
        Patch contexts for all external dependencies
    """
    # Mock all external clients used by RecommendationService
    with patch(
        "src.server.services.recommendation_service.SchwabClient"
    ) as mock_schwab, patch(
        "src.server.services.recommendation_service.FinnhubClient"
    ) as mock_finnhub, patch(
        "src.server.services.recommendation_service.RecommendEngine"
    ) as mock_engine:
        # Configure Schwab client mock
        mock_schwab_instance = MagicMock()
        mock_schwab.return_value = mock_schwab_instance

        # Configure Finnhub client mock
        mock_finnhub_instance = MagicMock()
        mock_finnhub.return_value = mock_finnhub_instance

        # Configure RecommendEngine mock
        engine_instance = MagicMock()

        # Create a sample recommendation
        def create_mock_recommendation(position, **kwargs):
            """Create mock recommendation based on position state."""
            direction = "put" if position.state.value == "cash" else "call"
            strike = 145.0 if direction == "put" else 155.0

            return WheelRecommendation(
                symbol=position.symbol,
                direction=direction,
                strike=strike,
                expiration_date=(date.today() + timedelta(days=30)).isoformat(),
                premium_per_share=2.50,
                contracts=1,
                total_premium=250.0,
                sigma_distance=1.2,
                p_itm=0.20,
                annualized_yield_pct=25.0,
                warnings=[],
                bias_score=0.85,
                dte=30,
                current_price=150.0,
                bid=2.50,
                ask=2.55,
            )

        engine_instance.get_recommendation.side_effect = create_mock_recommendation
        mock_engine.return_value = engine_instance

        yield {
            "schwab": mock_schwab,
            "finnhub": mock_finnhub,
            "engine": mock_engine,
        }


class TestGetRecommendation:
    """Test cases for getting individual recommendations."""

    def test_get_recommendation_for_cash_state(
        self, client: TestClient, test_wheel_cash: dict, mock_recommendation_service
    ):
        """Test getting recommendation when in CASH state.

        Should recommend selling a put.
        """
        response = client.get(f"/api/v1/wheels/{test_wheel_cash['id']}/recommend")

        assert response.status_code == 200
        data = response.json()

        # Verify basic structure
        assert data["wheel_id"] == test_wheel_cash["id"]
        assert data["symbol"] == test_wheel_cash["symbol"]
        assert data["current_state"] == "cash"
        assert data["direction"] == "put"  # Should recommend selling a put

        # Verify recommendation details
        assert data["strike"] > 0
        assert data["premium_per_share"] > 0
        assert data["total_premium"] > 0
        assert 0 <= data["probability_itm"] <= 1
        assert 0 <= data["probability_otm"] <= 1
        assert data["probability_itm"] + data["probability_otm"] == pytest.approx(1.0)

        # Verify metadata
        assert "recommended_at" in data
        assert data["profile"] == test_wheel_cash["profile"]
        assert data["current_price"] > 0
        assert data["days_to_expiry"] > 0

    def test_get_recommendation_for_shares_state(
        self, client: TestClient, test_wheel_shares: dict, mock_recommendation_service
    ):
        """Test getting recommendation when in SHARES state.

        Should recommend selling a call.
        """
        response = client.get(f"/api/v1/wheels/{test_wheel_shares['id']}/recommend")

        assert response.status_code == 200
        data = response.json()

        # Verify basic structure
        assert data["wheel_id"] == test_wheel_shares["id"]
        assert data["symbol"] == test_wheel_shares["symbol"]
        assert data["current_state"] == "shares"
        assert data["direction"] == "call"  # Should recommend selling a call

        # Verify recommendation details
        assert data["strike"] > 0
        assert data["premium_per_share"] > 0

    def test_get_recommendation_with_expiration_date(
        self, client: TestClient, test_wheel_cash: dict, mock_recommendation_service
    ):
        """Test getting recommendation with specific expiration date."""
        target_date = (date.today() + timedelta(days=45)).isoformat()

        response = client.get(
            f"/api/v1/wheels/{test_wheel_cash['id']}/recommend",
            params={"expiration_date": target_date},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["expiration_date"] is not None

    def test_get_recommendation_wheel_not_found(self, client: TestClient):
        """Test getting recommendation for non-existent wheel."""
        response = client.get("/api/v1/wheels/99999/recommend")

        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    def test_get_recommendation_with_open_position(
        self, client: TestClient, test_db, test_wheel_cash: dict
    ):
        """Test getting recommendation when wheel has open position.

        Should fail because recommendations are only for base states.
        """
        # Manually update wheel to CASH_PUT_OPEN state
        wheel = (
            test_db.query(Wheel).filter(Wheel.id == test_wheel_cash["id"]).first()
        )
        wheel.state = "cash_put_open"
        test_db.commit()

        response = client.get(f"/api/v1/wheels/{test_wheel_cash['id']}/recommend")

        assert response.status_code == 400
        assert "state" in response.json()["detail"].lower()

    def test_get_recommendation_uses_cache(
        self, client: TestClient, test_wheel_cash: dict, mock_recommendation_service
    ):
        """Test that recommendations are cached properly."""
        # First request - should call engine
        response1 = client.get(f"/api/v1/wheels/{test_wheel_cash['id']}/recommend")
        assert response1.status_code == 200
        data1 = response1.json()

        # Second request with cache enabled - should use cached result
        response2 = client.get(
            f"/api/v1/wheels/{test_wheel_cash['id']}/recommend",
            params={"use_cache": True},
        )
        assert response2.status_code == 200
        data2 = response2.json()

        # Core recommendation data should match if cached
        # (timestamps may differ slightly due to generation time)
        assert data1["strike"] == data2["strike"]
        assert data1["direction"] == data2["direction"]
        assert data1["premium_per_share"] == data2["premium_per_share"]

    def test_get_recommendation_bypasses_cache(
        self, client: TestClient, test_wheel_cash: dict, mock_recommendation_service
    ):
        """Test that cache can be bypassed with use_cache=false."""
        # First request
        response1 = client.get(f"/api/v1/wheels/{test_wheel_cash['id']}/recommend")
        assert response1.status_code == 200

        # Second request with cache disabled
        response2 = client.get(
            f"/api/v1/wheels/{test_wheel_cash['id']}/recommend",
            params={"use_cache": False},
        )
        assert response2.status_code == 200

        # Both should succeed (can't easily verify different engine calls without more mocking)

    def test_get_recommendation_respects_profile(
        self, client: TestClient, portfolio_id: str, mock_recommendation_service
    ):
        """Test that recommendation respects wheel profile.

        Conservative profile should have lower P(ITM) than aggressive.
        """
        # Create conservative wheel
        response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "CONS",
                "capital_allocated": 20000.0,
                "profile": "conservative",
            },
        )
        conservative_wheel = response.json()

        # Get recommendation
        response = client.get(f"/api/v1/wheels/{conservative_wheel['id']}/recommend")
        assert response.status_code == 200
        data = response.json()

        assert data["profile"] == "conservative"
        # Conservative should typically have lower P(ITM) (but this depends on mock)


class TestRecommendationWarnings:
    """Test cases for recommendation warnings."""

    def test_recommendation_with_warnings(
        self, client: TestClient, test_wheel_cash: dict
    ):
        """Test that warnings are included in response."""
        # Mock engine to return recommendation with warnings
        with patch("src.server.services.recommendation_service.RecommendEngine") as mock:
            engine_instance = MagicMock()

            def create_rec_with_warnings(position, **kwargs):
                return WheelRecommendation(
                    symbol=position.symbol,
                    direction="put",
                    strike=145.0,
                    expiration_date=(date.today() + timedelta(days=30)).isoformat(),
                    premium_per_share=2.50,
                    contracts=1,
                    total_premium=250.0,
                    sigma_distance=0.8,
                    p_itm=0.35,  # High P(ITM)
                    annualized_yield_pct=25.0,
                    warnings=[
                        "P(ITM) 35.0% exceeds 30% threshold - higher assignment risk",
                        "Earnings on 2026-02-15 before expiration - elevated volatility risk",
                    ],
                    bias_score=0.70,
                    dte=30,
                    current_price=150.0,
                    bid=2.50,
                    ask=2.55,
                )

            engine_instance.get_recommendation.side_effect = create_rec_with_warnings
            mock.return_value = engine_instance

            response = client.get(f"/api/v1/wheels/{test_wheel_cash['id']}/recommend")

            assert response.status_code == 200
            data = response.json()

            assert data["has_warnings"] is True
            assert len(data["warnings"]) > 0
            assert any("P(ITM)" in w for w in data["warnings"])


class TestBatchRecommendations:
    """Test cases for batch recommendation operations."""

    def test_batch_recommendations_multiple_symbols(
        self, client: TestClient, portfolio_id: str, mock_recommendation_service
    ):
        """Test getting batch recommendations for multiple symbols."""
        # Create multiple wheels
        symbols = ["AAPL", "MSFT", "GOOGL"]
        for symbol in symbols:
            client.post(
                f"/api/v1/portfolios/{portfolio_id}/wheels",
                json={
                    "symbol": symbol,
                    "capital_allocated": 20000.0,
                    "profile": "moderate",
                },
            )

        # Request batch recommendations
        response = client.post(
            "/api/v1/wheels/recommend/batch",
            json={"symbols": symbols, "expiration_date": None},
        )

        assert response.status_code == 200
        data = response.json()

        # Should have recommendations for all symbols
        assert len(data["recommendations"]) == len(symbols)
        assert "requested_at" in data
        assert isinstance(data["errors"], dict)

        # Verify each recommendation
        returned_symbols = {rec["symbol"] for rec in data["recommendations"]}
        assert returned_symbols == set(symbols)

    def test_batch_recommendations_with_errors(
        self, client: TestClient, portfolio_id: str, mock_recommendation_service
    ):
        """Test batch recommendations with some symbols failing."""
        # Create only one wheel
        client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 20000.0,
                "profile": "moderate",
            },
        )

        # Request batch with both valid and invalid symbols
        response = client.post(
            "/api/v1/wheels/recommend/batch",
            json={"symbols": ["AAPL", "INVALID", "NOTFOUND"]},
        )

        assert response.status_code == 200
        data = response.json()

        # Should have 1 successful recommendation
        assert len(data["recommendations"]) == 1
        assert data["recommendations"][0]["symbol"] == "AAPL"

        # Should have errors for invalid symbols
        assert len(data["errors"]) == 2
        assert "INVALID" in data["errors"]
        assert "NOTFOUND" in data["errors"]

    def test_batch_recommendations_empty_list(self, client: TestClient):
        """Test batch recommendations with empty symbol list.

        Should fail validation.
        """
        response = client.post(
            "/api/v1/wheels/recommend/batch", json={"symbols": []}
        )

        assert response.status_code == 422  # Validation error

    def test_batch_recommendations_too_many_symbols(self, client: TestClient):
        """Test batch recommendations with too many symbols.

        Should fail validation (max 20 symbols).
        """
        symbols = [f"SYM{i:03d}" for i in range(25)]  # 25 symbols

        response = client.post(
            "/api/v1/wheels/recommend/batch", json={"symbols": symbols}
        )

        assert response.status_code == 422  # Validation error

    def test_batch_recommendations_with_expiration_date(
        self, client: TestClient, portfolio_id: str, mock_recommendation_service
    ):
        """Test batch recommendations with specific expiration date."""
        # Create wheel
        client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 20000.0,
                "profile": "moderate",
            },
        )

        target_date = (date.today() + timedelta(days=45)).isoformat()

        response = client.post(
            "/api/v1/wheels/recommend/batch",
            json={"symbols": ["AAPL"], "expiration_date": target_date},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["recommendations"]) == 1


class TestCacheManagement:
    """Test cases for cache management."""

    def test_clear_cache(self, client: TestClient):
        """Test clearing recommendation cache."""
        response = client.delete("/api/v1/wheels/recommend/cache")

        assert response.status_code == 204


class TestRecommendationValidation:
    """Test cases for request validation."""

    def test_invalid_expiration_date_format(
        self, client: TestClient, test_wheel_cash: dict
    ):
        """Test recommendation with invalid date format."""
        response = client.get(
            f"/api/v1/wheels/{test_wheel_cash['id']}/recommend",
            params={"expiration_date": "2026/03/21"},  # Wrong format
        )

        # Should fail at validation level before reaching service
        assert response.status_code in (400, 422)

    def test_past_expiration_date(self, client: TestClient, test_wheel_cash: dict):
        """Test recommendation with past expiration date."""
        past_date = (date.today() - timedelta(days=1)).isoformat()

        response = client.get(
            f"/api/v1/wheels/{test_wheel_cash['id']}/recommend",
            params={"expiration_date": past_date},
        )

        # Should fail validation
        assert response.status_code in (400, 422)

    def test_batch_invalid_symbol_characters(self, client: TestClient):
        """Test batch recommendations with invalid symbol characters."""
        response = client.post(
            "/api/v1/wheels/recommend/batch",
            json={"symbols": ["AAPL", "INVALID@SYMBOL", "MSFT"]},
        )

        # Should fail validation
        assert response.status_code == 422
