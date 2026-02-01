"""Integration tests for Wheel API endpoints.

Tests all wheel CRUD operations including validation,
error handling, and cascade deletes.
"""

import pytest
from fastapi.testclient import TestClient

from src.server.database.models.trade import Trade
from src.server.database.models.wheel import Wheel


@pytest.fixture
def portfolio_id(client: TestClient) -> str:
    """Create a test portfolio and return its ID."""
    response = client.post(
        "/api/v1/portfolios/",
        json={"name": "Test Portfolio", "default_capital": 50000.0},
    )
    return response.json()["id"]


class TestWheelCreate:
    """Test cases for creating wheels."""

    def test_create_wheel_success(self, client: TestClient, portfolio_id: str):
        """Test creating a wheel with valid data."""
        response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["capital_allocated"] == 10000.0
        assert data["profile"] == "conservative"
        assert data["state"] == "cash"
        assert data["shares_held"] == 0
        assert data["is_active"] is True
        assert data["trade_count"] == 0
        assert "id" in data
        assert data["portfolio_id"] == portfolio_id

    def test_create_wheel_lowercase_symbol(self, client: TestClient, portfolio_id: str):
        """Test that lowercase symbols are converted to uppercase."""
        response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "msft",
                "capital_allocated": 15000.0,
                "profile": "moderate",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["symbol"] == "MSFT"

    def test_create_wheel_duplicate_symbol_same_portfolio(
        self, client: TestClient, portfolio_id: str
    ):
        """Test that duplicate symbols in same portfolio are rejected."""
        # Create first wheel
        client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        )

        # Try to create duplicate
        response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 15000.0,
                "profile": "moderate",
            },
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_create_wheel_same_symbol_different_portfolios(self, client: TestClient):
        """Test that same symbol can exist in different portfolios."""
        # Create two portfolios
        portfolio1 = client.post(
            "/api/v1/portfolios/",
            json={"name": "Portfolio 1"},
        ).json()["id"]

        portfolio2 = client.post(
            "/api/v1/portfolios/",
            json={"name": "Portfolio 2"},
        ).json()["id"]

        # Create wheel in first portfolio
        response1 = client.post(
            f"/api/v1/portfolios/{portfolio1}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        )
        assert response1.status_code == 201

        # Create wheel with same symbol in second portfolio
        response2 = client.post(
            f"/api/v1/portfolios/{portfolio2}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 15000.0,
                "profile": "aggressive",
            },
        )
        assert response2.status_code == 201

    def test_create_wheel_portfolio_not_found(self, client: TestClient):
        """Test creating wheel in non-existent portfolio fails."""
        response = client.post(
            "/api/v1/portfolios/non-existent-id/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        )
        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    def test_create_wheel_invalid_profile(self, client: TestClient, portfolio_id: str):
        """Test creating wheel with invalid profile fails."""
        response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "invalid_profile",
            },
        )
        assert response.status_code == 422

    def test_create_wheel_zero_capital(self, client: TestClient, portfolio_id: str):
        """Test creating wheel with zero capital fails."""
        response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 0.0,
                "profile": "conservative",
            },
        )
        assert response.status_code == 422

    def test_create_wheel_negative_capital(self, client: TestClient, portfolio_id: str):
        """Test creating wheel with negative capital fails."""
        response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": -1000.0,
                "profile": "conservative",
            },
        )
        assert response.status_code == 422


class TestWheelList:
    """Test cases for listing wheels."""

    def test_list_wheels_empty(self, client: TestClient, portfolio_id: str):
        """Test listing wheels when none exist."""
        response = client.get(f"/api/v1/portfolios/{portfolio_id}/wheels")
        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_list_wheels_by_portfolio(self, client: TestClient, portfolio_id: str):
        """Test listing wheels in a portfolio."""
        # Create wheels
        for symbol in ["AAPL", "MSFT", "GOOGL"]:
            client.post(
                f"/api/v1/portfolios/{portfolio_id}/wheels",
                json={
                    "symbol": symbol,
                    "capital_allocated": 10000.0,
                    "profile": "conservative",
                },
            )

        response = client.get(f"/api/v1/portfolios/{portfolio_id}/wheels")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        # Check they're sorted by symbol
        symbols = [w["symbol"] for w in data]
        assert symbols == sorted(symbols)

    def test_list_wheels_active_only(self, client: TestClient, portfolio_id: str):
        """Test listing only active wheels."""
        # Create active wheel
        wheel1_response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        )
        wheel1_id = wheel1_response.json()["id"]

        # Create inactive wheel
        wheel2_response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "MSFT",
                "capital_allocated": 15000.0,
                "profile": "moderate",
            },
        )
        wheel2_id = wheel2_response.json()["id"]

        # Deactivate wheel2
        client.put(
            f"/api/v1/wheels/{wheel2_id}",
            json={"is_active": False},
        )

        # List all wheels
        all_response = client.get(f"/api/v1/portfolios/{portfolio_id}/wheels")
        assert len(all_response.json()) == 2

        # List active only
        active_response = client.get(
            f"/api/v1/portfolios/{portfolio_id}/wheels?active_only=true"
        )
        assert len(active_response.json()) == 1
        assert active_response.json()[0]["id"] == wheel1_id

    def test_list_wheels_pagination(self, client: TestClient, portfolio_id: str):
        """Test wheel listing pagination."""
        # Create 5 wheels
        for i in range(5):
            client.post(
                f"/api/v1/portfolios/{portfolio_id}/wheels",
                json={
                    "symbol": f"SYM{i}",
                    "capital_allocated": 10000.0,
                    "profile": "conservative",
                },
            )

        # Test skip and limit
        response = client.get(
            f"/api/v1/portfolios/{portfolio_id}/wheels?skip=2&limit=2"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


class TestWheelGet:
    """Test cases for getting a specific wheel."""

    def test_get_wheel_success(self, client: TestClient, portfolio_id: str):
        """Test getting an existing wheel."""
        # Create wheel
        create_response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        )
        wheel_id = create_response.json()["id"]

        # Get wheel
        response = client.get(f"/api/v1/wheels/{wheel_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == wheel_id
        assert data["symbol"] == "AAPL"
        assert data["capital_allocated"] == 10000.0

    def test_get_wheel_not_found(self, client: TestClient):
        """Test getting a non-existent wheel."""
        response = client.get("/api/v1/wheels/99999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestWheelUpdate:
    """Test cases for updating wheels."""

    def test_update_wheel_success(self, client: TestClient, portfolio_id: str):
        """Test updating a wheel."""
        # Create wheel
        create_response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        )
        wheel_id = create_response.json()["id"]

        # Update wheel
        response = client.put(
            f"/api/v1/wheels/{wheel_id}",
            json={
                "capital_allocated": 15000.0,
                "profile": "aggressive",
                "is_active": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["capital_allocated"] == 15000.0
        assert data["profile"] == "aggressive"
        assert data["is_active"] is False

    def test_update_wheel_partial(self, client: TestClient, portfolio_id: str):
        """Test updating only some fields."""
        # Create wheel
        create_response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        )
        wheel_id = create_response.json()["id"]

        # Update only capital
        response = client.put(
            f"/api/v1/wheels/{wheel_id}",
            json={"capital_allocated": 20000.0},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["capital_allocated"] == 20000.0
        assert data["profile"] == "conservative"  # Unchanged

    def test_update_wheel_not_found(self, client: TestClient):
        """Test updating a non-existent wheel."""
        response = client.put(
            "/api/v1/wheels/99999",
            json={"capital_allocated": 15000.0},
        )
        assert response.status_code == 404


class TestWheelDelete:
    """Test cases for deleting wheels."""

    def test_delete_wheel_success(self, client: TestClient, portfolio_id: str):
        """Test deleting a wheel."""
        # Create wheel
        create_response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        )
        wheel_id = create_response.json()["id"]

        # Delete wheel
        response = client.delete(f"/api/v1/wheels/{wheel_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/api/v1/wheels/{wheel_id}")
        assert get_response.status_code == 404

    def test_delete_wheel_cascades_to_trades(
        self, client: TestClient, portfolio_id: str, test_db
    ):
        """Test that deleting wheel also deletes associated trades."""
        # Create wheel
        create_response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        )
        wheel_id = create_response.json()["id"]

        # Manually create a trade (no API endpoint yet)
        from datetime import datetime

        trade = Trade(
            wheel_id=wheel_id,
            symbol="AAPL",
            direction="put",
            strike=150.0,
            expiration_date="2026-03-01",
            premium_per_share=2.50,
            contracts=1,
            total_premium=250.0,
            outcome="open",
        )
        test_db.add(trade)
        test_db.commit()

        # Verify trade exists
        trades_before = test_db.query(Trade).filter(Trade.wheel_id == wheel_id).all()
        assert len(trades_before) == 1

        # Delete wheel
        response = client.delete(f"/api/v1/wheels/{wheel_id}")
        assert response.status_code == 204

        # Verify trades are deleted
        trades_after = test_db.query(Trade).filter(Trade.wheel_id == wheel_id).all()
        assert len(trades_after) == 0

    def test_delete_wheel_not_found(self, client: TestClient):
        """Test deleting a non-existent wheel."""
        response = client.delete("/api/v1/wheels/99999")
        assert response.status_code == 404


class TestWheelState:
    """Test cases for wheel state endpoint."""

    def test_get_wheel_state_no_trades(self, client: TestClient, portfolio_id: str):
        """Test getting wheel state with no trades."""
        # Create wheel
        create_response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        )
        wheel_id = create_response.json()["id"]

        # Get state
        response = client.get(f"/api/v1/wheels/{wheel_id}/state")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == wheel_id
        assert data["symbol"] == "AAPL"
        assert data["state"] == "cash"
        assert data["shares_held"] == 0
        assert data["open_trade"] is None

    def test_get_wheel_state_with_open_trade(
        self, client: TestClient, portfolio_id: str, test_db
    ):
        """Test getting wheel state with an open trade."""
        # Create wheel
        create_response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        )
        wheel_id = create_response.json()["id"]

        # Create open trade
        trade = Trade(
            wheel_id=wheel_id,
            symbol="AAPL",
            direction="put",
            strike=150.0,
            expiration_date="2026-03-01",
            premium_per_share=2.50,
            contracts=1,
            total_premium=250.0,
            outcome="open",
        )
        test_db.add(trade)
        test_db.commit()

        # Get state
        response = client.get(f"/api/v1/wheels/{wheel_id}/state")
        assert response.status_code == 200
        data = response.json()
        assert data["open_trade"] is not None
        assert data["open_trade"]["option_type"] == "put"
        assert data["open_trade"]["strike"] == 150.0

    def test_get_wheel_state_not_found(self, client: TestClient):
        """Test getting state for non-existent wheel."""
        response = client.get("/api/v1/wheels/99999/state")
        assert response.status_code == 404
