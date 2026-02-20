"""Integration tests for Performance API endpoints.

Tests the GET /api/v1/performance aggregate endpoint and
GET /api/v1/wheels/{id}/performance per-wheel endpoint including
all-time metrics, trended windows, wheel not found, and empty trades.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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


@pytest.fixture
def test_wheel(client: TestClient, portfolio_id: str) -> dict:
    """Create a test wheel in CASH state."""
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/wheels",
        json={
            "symbol": "AAPL",
            "capital_allocated": 20000.0,
            "profile": "conservative",
        },
    )
    return response.json()


class TestGetWheelPerformance:
    """Tests for GET /api/v1/wheels/{id}/performance."""

    def test_wheel_not_found(self, client):
        response = client.get("/api/v1/wheels/9999/performance")
        assert response.status_code == 404

    def test_wheel_with_no_trades(self, client, test_wheel):
        response = client.get(f"/api/v1/wheels/{test_wheel['id']}/performance")
        assert response.status_code == 200
        data = response.json()
        assert data["wheel_id"] == test_wheel["id"]
        assert data["symbol"] == "AAPL"
        assert data["all_time"]["trades_closed"] == 0
        assert data["all_time"]["option_premium_pnl"] == 0.0
        assert data["all_time"]["stock_pnl"] == 0.0
        assert data["all_time"]["win_rate"] == 0.0

    def test_all_time_metrics(self, client, test_db, test_wheel):
        now = datetime.utcnow()
        # Add closed trades directly to DB
        trade = Trade(
            wheel_id=test_wheel["id"],
            symbol="AAPL",
            direction="put",
            strike=150.0,
            expiration_date="2026-03-21",
            premium_per_share=2.5,
            contracts=1,
            total_premium=250.0,
            outcome="expired_worthless",
            opened_at=now - timedelta(days=20),
            closed_at=now - timedelta(days=6),
        )
        test_db.add(trade)
        test_db.commit()

        response = client.get(f"/api/v1/wheels/{test_wheel['id']}/performance")
        assert response.status_code == 200
        data = response.json()
        assert data["all_time"]["option_premium_pnl"] == 250.0
        assert data["all_time"]["trades_closed"] == 1
        assert data["all_time"]["win_rate"] == 1.0
        assert data["all_time"]["contracts_traded"] == 1

    def test_trended_windows(self, client, test_db, test_wheel):
        now = datetime.utcnow()

        # Trade closed 3 days ago (in 1W, 1M, 1Q)
        t1 = Trade(
            wheel_id=test_wheel["id"],
            symbol="AAPL",
            direction="put",
            strike=150.0,
            expiration_date="2026-03-21",
            premium_per_share=2.0,
            contracts=1,
            total_premium=200.0,
            outcome="expired_worthless",
            opened_at=now - timedelta(days=10),
            closed_at=now - timedelta(days=3),
        )
        # Trade closed 50 days ago (in 1Q only)
        t2 = Trade(
            wheel_id=test_wheel["id"],
            symbol="AAPL",
            direction="put",
            strike=148.0,
            expiration_date="2026-01-15",
            premium_per_share=1.5,
            contracts=1,
            total_premium=150.0,
            outcome="expired_worthless",
            opened_at=now - timedelta(days=60),
            closed_at=now - timedelta(days=50),
        )
        test_db.add_all([t1, t2])
        test_db.commit()

        response = client.get(f"/api/v1/wheels/{test_wheel['id']}/performance")
        assert response.status_code == 200
        data = response.json()

        assert data["all_time"]["trades_closed"] == 2
        assert data["all_time"]["option_premium_pnl"] == 350.0

        assert data["one_week"]["trades_closed"] == 1
        assert data["one_week"]["option_premium_pnl"] == 200.0

        assert data["one_quarter"]["trades_closed"] == 2
        assert data["one_quarter"]["option_premium_pnl"] == 350.0

    def test_response_shape(self, client, test_wheel):
        """Verify JSON response has all expected fields."""
        response = client.get(f"/api/v1/wheels/{test_wheel['id']}/performance")
        assert response.status_code == 200
        data = response.json()

        assert "wheel_id" in data
        assert "symbol" in data
        for period_key in ["all_time", "one_week", "one_month", "one_quarter"]:
            assert period_key in data
            period = data[period_key]
            assert "option_premium_pnl" in period
            assert "stock_pnl" in period
            assert "total_pnl" in period
            assert "trades_closed" in period
            assert "contracts_traded" in period
            assert "win_rate" in period


class TestGetAggregatePerformance:
    """Tests for GET /api/v1/performance."""

    def test_response_shape(self, client, test_wheel):
        """Verify aggregate JSON has period fields but no wheel_id/symbol."""
        response = client.get("/api/v1/performance")
        assert response.status_code == 200
        data = response.json()

        assert "wheel_id" not in data
        assert "symbol" not in data
        for period_key in ["all_time", "one_week", "one_month", "one_quarter"]:
            assert period_key in data
            period = data[period_key]
            assert "option_premium_pnl" in period
            assert "stock_pnl" in period
            assert "total_pnl" in period
            assert "trades_closed" in period
            assert "contracts_traded" in period
            assert "win_rate" in period

    def test_no_trades(self, client):
        """Returns zero metrics when no trades exist."""
        response = client.get("/api/v1/performance")
        assert response.status_code == 200
        data = response.json()
        assert data["all_time"]["trades_closed"] == 0
        assert data["all_time"]["option_premium_pnl"] == 0.0
        assert data["all_time"]["stock_pnl"] == 0.0

    def test_aggregate_metrics(self, client, test_db, test_wheel, portfolio_id):
        """Aggregate endpoint sums trades across multiple wheels."""
        now = datetime.utcnow()

        # Create a second wheel
        resp = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "MSFT",
                "capital_allocated": 15000.0,
                "profile": "moderate",
            },
        )
        wheel2 = resp.json()

        # Add trades to both wheels
        t1 = Trade(
            wheel_id=test_wheel["id"],
            symbol="AAPL",
            direction="put",
            strike=150.0,
            expiration_date="2026-03-21",
            premium_per_share=2.0,
            contracts=1,
            total_premium=200.0,
            outcome="expired_worthless",
            opened_at=now - timedelta(days=10),
            closed_at=now - timedelta(days=3),
        )
        t2 = Trade(
            wheel_id=wheel2["id"],
            symbol="MSFT",
            direction="put",
            strike=300.0,
            expiration_date="2026-03-21",
            premium_per_share=3.0,
            contracts=2,
            total_premium=600.0,
            outcome="expired_worthless",
            opened_at=now - timedelta(days=10),
            closed_at=now - timedelta(days=3),
        )
        test_db.add_all([t1, t2])
        test_db.commit()

        response = client.get("/api/v1/performance")
        assert response.status_code == 200
        data = response.json()

        assert data["all_time"]["trades_closed"] == 2
        assert data["all_time"]["option_premium_pnl"] == 800.0
        assert data["all_time"]["contracts_traded"] == 3
