"""Integration tests for Portfolio API endpoints.

Tests all portfolio CRUD operations including validation,
error handling, and cascade deletes.
"""

import pytest
from fastapi.testclient import TestClient

from src.server.database.models.portfolio import Portfolio
from src.server.database.models.wheel import Wheel


class TestPortfolioCreate:
    """Test cases for creating portfolios."""

    def test_create_portfolio_success(self, client: TestClient):
        """Test creating a portfolio with valid data."""
        response = client.post(
            "/api/v1/portfolios/",
            json={
                "name": "Test Portfolio",
                "description": "Test description",
                "default_capital": 10000.0,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Portfolio"
        assert data["description"] == "Test description"
        assert data["default_capital"] == 10000.0
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data
        assert data["wheel_count"] == 0

    def test_create_portfolio_minimal(self, client: TestClient):
        """Test creating a portfolio with only required fields."""
        response = client.post(
            "/api/v1/portfolios/",
            json={"name": "Minimal Portfolio"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Portfolio"
        assert data["description"] is None
        assert data["default_capital"] is None
        assert data["wheel_count"] == 0

    def test_create_portfolio_blank_name(self, client: TestClient):
        """Test creating portfolio with blank name fails."""
        response = client.post(
            "/api/v1/portfolios/",
            json={"name": "   "},
        )
        assert response.status_code == 422

    def test_create_portfolio_negative_capital(self, client: TestClient):
        """Test creating portfolio with negative capital fails."""
        response = client.post(
            "/api/v1/portfolios/",
            json={
                "name": "Test Portfolio",
                "default_capital": -1000.0,
            },
        )
        assert response.status_code == 422


class TestPortfolioList:
    """Test cases for listing portfolios."""

    def test_list_portfolios_empty(self, client: TestClient):
        """Test listing portfolios when none exist."""
        response = client.get("/api/v1/portfolios/")
        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_list_portfolios(self, client: TestClient):
        """Test listing multiple portfolios."""
        # Create portfolios
        for i in range(3):
            client.post(
                "/api/v1/portfolios/",
                json={"name": f"Portfolio {i}"},
            )

        response = client.get("/api/v1/portfolios/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert all("id" in p for p in data)
        assert all("wheel_count" in p for p in data)

    def test_list_portfolios_pagination(self, client: TestClient):
        """Test portfolio listing pagination."""
        # Create 5 portfolios
        for i in range(5):
            client.post(
                "/api/v1/portfolios/",
                json={"name": f"Portfolio {i}"},
            )

        # Test skip and limit
        response = client.get("/api/v1/portfolios/?skip=2&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


class TestPortfolioGet:
    """Test cases for getting a specific portfolio."""

    def test_get_portfolio_success(self, client: TestClient):
        """Test getting an existing portfolio."""
        # Create portfolio
        create_response = client.post(
            "/api/v1/portfolios/",
            json={"name": "Test Portfolio", "default_capital": 5000.0},
        )
        portfolio_id = create_response.json()["id"]

        # Get portfolio
        response = client.get(f"/api/v1/portfolios/{portfolio_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == portfolio_id
        assert data["name"] == "Test Portfolio"
        assert data["default_capital"] == 5000.0

    def test_get_portfolio_not_found(self, client: TestClient):
        """Test getting a non-existent portfolio."""
        response = client.get("/api/v1/portfolios/non-existent-id")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestPortfolioUpdate:
    """Test cases for updating portfolios."""

    def test_update_portfolio_success(self, client: TestClient):
        """Test updating a portfolio."""
        # Create portfolio
        create_response = client.post(
            "/api/v1/portfolios/",
            json={"name": "Original Name", "default_capital": 5000.0},
        )
        portfolio_id = create_response.json()["id"]

        # Update portfolio
        response = client.put(
            f"/api/v1/portfolios/{portfolio_id}",
            json={"name": "Updated Name", "default_capital": 10000.0},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["default_capital"] == 10000.0

    def test_update_portfolio_partial(self, client: TestClient):
        """Test updating only some fields."""
        # Create portfolio
        create_response = client.post(
            "/api/v1/portfolios/",
            json={"name": "Original Name", "default_capital": 5000.0},
        )
        portfolio_id = create_response.json()["id"]

        # Update only name
        response = client.put(
            f"/api/v1/portfolios/{portfolio_id}",
            json={"name": "New Name"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["default_capital"] == 5000.0  # Unchanged

    def test_update_portfolio_not_found(self, client: TestClient):
        """Test updating a non-existent portfolio."""
        response = client.put(
            "/api/v1/portfolios/non-existent-id",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 404


class TestPortfolioDelete:
    """Test cases for deleting portfolios."""

    def test_delete_portfolio_success(self, client: TestClient):
        """Test deleting a portfolio."""
        # Create portfolio
        create_response = client.post(
            "/api/v1/portfolios/",
            json={"name": "Test Portfolio"},
        )
        portfolio_id = create_response.json()["id"]

        # Delete portfolio
        response = client.delete(f"/api/v1/portfolios/{portfolio_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/api/v1/portfolios/{portfolio_id}")
        assert get_response.status_code == 404

    def test_delete_portfolio_cascades_to_wheels(self, client: TestClient, test_db):
        """Test that deleting portfolio also deletes associated wheels."""
        # Create portfolio
        create_response = client.post(
            "/api/v1/portfolios/",
            json={"name": "Test Portfolio"},
        )
        portfolio_id = create_response.json()["id"]

        # Create wheel in portfolio
        client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        )

        # Verify wheel exists
        wheels_before = (
            test_db.query(Wheel).filter(Wheel.portfolio_id == portfolio_id).all()
        )
        assert len(wheels_before) == 1

        # Delete portfolio
        response = client.delete(f"/api/v1/portfolios/{portfolio_id}")
        assert response.status_code == 204

        # Verify wheels are deleted
        wheels_after = (
            test_db.query(Wheel).filter(Wheel.portfolio_id == portfolio_id).all()
        )
        assert len(wheels_after) == 0

    def test_delete_portfolio_not_found(self, client: TestClient):
        """Test deleting a non-existent portfolio."""
        response = client.delete("/api/v1/portfolios/non-existent-id")
        assert response.status_code == 404


class TestPortfolioSummary:
    """Test cases for portfolio summary endpoint."""

    def test_get_portfolio_summary(self, client: TestClient):
        """Test getting portfolio summary with statistics."""
        # Create portfolio
        create_response = client.post(
            "/api/v1/portfolios/",
            json={"name": "Test Portfolio"},
        )
        portfolio_id = create_response.json()["id"]

        # Create wheels
        client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        )
        client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "MSFT",
                "capital_allocated": 15000.0,
                "profile": "moderate",
            },
        )

        # Get summary
        response = client.get(f"/api/v1/portfolios/{portfolio_id}/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == portfolio_id
        assert data["total_wheels"] == 2
        assert data["active_wheels"] == 2
        assert data["total_capital_allocated"] == 25000.0

    def test_get_portfolio_summary_not_found(self, client: TestClient):
        """Test getting summary for non-existent portfolio."""
        response = client.get("/api/v1/portfolios/non-existent-id/summary")
        assert response.status_code == 404
