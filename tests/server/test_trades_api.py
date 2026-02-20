"""Integration tests for Trade API endpoints.

Tests all trade operations including creation, expiration, early close,
state machine validation, and error handling.
"""

import pytest
from datetime import date, timedelta
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


@pytest.fixture
def test_wheel_with_shares(client: TestClient, test_db, portfolio_id: str) -> dict:
    """Create a test wheel in SHARES state."""
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
    wheel.cost_basis = 150.0
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
def test_trade(client: TestClient, test_wheel: dict) -> dict:
    """Create a test trade (open put)."""
    future_date = (date.today() + timedelta(days=30)).isoformat()
    response = client.post(
        f"/api/v1/wheels/{test_wheel['id']}/trades",
        json={
            "direction": "put",
            "strike": 150.0,
            "expiration_date": future_date,
            "premium_per_share": 2.50,
            "contracts": 1,
        },
    )
    return response.json()


class TestTradeCreate:
    """Test cases for creating trades."""

    def test_create_put_trade_success(self, client: TestClient, test_wheel: dict):
        """Test creating a put trade from CASH state."""
        future_date = (date.today() + timedelta(days=30)).isoformat()
        response = client.post(
            f"/api/v1/wheels/{test_wheel['id']}/trades",
            json={
                "direction": "put",
                "strike": 150.0,
                "expiration_date": future_date,
                "premium_per_share": 2.50,
                "contracts": 1,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["direction"] == "put"
        assert data["strike"] == 150.0
        assert data["premium_per_share"] == 2.50
        assert data["contracts"] == 1
        assert data["total_premium"] == 250.0  # 2.50 * 100
        assert data["outcome"] == "open"
        assert data["symbol"] == test_wheel["symbol"]
        assert data["wheel_id"] == test_wheel["id"]
        assert "id" in data
        assert "opened_at" in data

    def test_create_call_trade_success(self, client: TestClient, test_wheel_with_shares: dict):
        """Test creating a call trade from SHARES state."""
        future_date = (date.today() + timedelta(days=30)).isoformat()
        response = client.post(
            f"/api/v1/wheels/{test_wheel_with_shares['id']}/trades",
            json={
                "direction": "call",
                "strike": 160.0,
                "expiration_date": future_date,
                "premium_per_share": 3.00,
                "contracts": 1,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["direction"] == "call"
        assert data["strike"] == 160.0
        assert data["total_premium"] == 300.0  # 3.00 * 100

    def test_create_trade_invalid_wheel(self, client: TestClient):
        """Test creating trade for non-existent wheel fails."""
        future_date = (date.today() + timedelta(days=30)).isoformat()
        response = client.post(
            "/api/v1/wheels/99999/trades",
            json={
                "direction": "put",
                "strike": 150.0,
                "expiration_date": future_date,
                "premium_per_share": 2.50,
                "contracts": 1,
            },
        )
        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    def test_create_trade_invalid_direction(self, client: TestClient, test_wheel: dict):
        """Test creating trade with invalid direction fails validation."""
        future_date = (date.today() + timedelta(days=30)).isoformat()
        response = client.post(
            f"/api/v1/wheels/{test_wheel['id']}/trades",
            json={
                "direction": "invalid",
                "strike": 150.0,
                "expiration_date": future_date,
                "premium_per_share": 2.50,
                "contracts": 1,
            },
        )
        assert response.status_code == 422

    def test_create_trade_invalid_strike(self, client: TestClient, test_wheel: dict):
        """Test creating trade with zero/negative strike fails validation."""
        future_date = (date.today() + timedelta(days=30)).isoformat()
        response = client.post(
            f"/api/v1/wheels/{test_wheel['id']}/trades",
            json={
                "direction": "put",
                "strike": 0.0,
                "expiration_date": future_date,
                "premium_per_share": 2.50,
                "contracts": 1,
            },
        )
        assert response.status_code == 422

    def test_create_trade_past_expiration_date(self, client: TestClient, test_wheel: dict):
        """Test creating trade with past expiration date fails validation."""
        past_date = (date.today() - timedelta(days=1)).isoformat()
        response = client.post(
            f"/api/v1/wheels/{test_wheel['id']}/trades",
            json={
                "direction": "put",
                "strike": 150.0,
                "expiration_date": past_date,
                "premium_per_share": 2.50,
                "contracts": 1,
            },
        )
        assert response.status_code == 422

    def test_create_trade_invalid_expiration_format(self, client: TestClient, test_wheel: dict):
        """Test creating trade with invalid date format fails validation."""
        response = client.post(
            f"/api/v1/wheels/{test_wheel['id']}/trades",
            json={
                "direction": "put",
                "strike": 150.0,
                "expiration_date": "2026-13-45",  # Invalid date
                "premium_per_share": 2.50,
                "contracts": 1,
            },
        )
        assert response.status_code == 422

    def test_create_put_from_shares_state_fails(self, client: TestClient, test_wheel_with_shares: dict):
        """Test creating put from SHARES state fails state validation."""
        future_date = (date.today() + timedelta(days=30)).isoformat()
        response = client.post(
            f"/api/v1/wheels/{test_wheel_with_shares['id']}/trades",
            json={
                "direction": "put",
                "strike": 150.0,
                "expiration_date": future_date,
                "premium_per_share": 2.50,
                "contracts": 1,
            },
        )
        assert response.status_code == 400
        assert "Cannot sell put" in response.json()["detail"]

    def test_create_call_from_cash_state_fails(self, client: TestClient, test_wheel: dict):
        """Test creating call from CASH state fails state validation."""
        future_date = (date.today() + timedelta(days=30)).isoformat()
        response = client.post(
            f"/api/v1/wheels/{test_wheel['id']}/trades",
            json={
                "direction": "call",
                "strike": 150.0,
                "expiration_date": future_date,
                "premium_per_share": 2.50,
                "contracts": 1,
            },
        )
        assert response.status_code == 400
        assert "Cannot sell call" in response.json()["detail"]

    def test_create_trade_insufficient_capital(self, client: TestClient, test_wheel: dict):
        """Test creating put with insufficient capital fails."""
        future_date = (date.today() + timedelta(days=30)).isoformat()
        response = client.post(
            f"/api/v1/wheels/{test_wheel['id']}/trades",
            json={
                "direction": "put",
                "strike": 500.0,  # 500 * 100 = 50000 > 20000 capital
                "expiration_date": future_date,
                "premium_per_share": 2.50,
                "contracts": 1,
            },
        )
        assert response.status_code == 400
        assert "capital" in response.json()["detail"].lower()

    def test_create_trade_insufficient_shares(self, client: TestClient, test_wheel_with_shares: dict):
        """Test creating call with insufficient shares fails."""
        future_date = (date.today() + timedelta(days=30)).isoformat()
        response = client.post(
            f"/api/v1/wheels/{test_wheel_with_shares['id']}/trades",
            json={
                "direction": "call",
                "strike": 150.0,
                "expiration_date": future_date,
                "premium_per_share": 2.50,
                "contracts": 2,  # Need 200 shares, only have 100
            },
        )
        assert response.status_code == 400
        assert "shares" in response.json()["detail"].lower()


class TestTradeList:
    """Test cases for listing trades."""

    def test_list_wheel_trades_empty(self, client: TestClient, test_wheel: dict):
        """Test listing trades for wheel with no trades."""
        response = client.get(f"/api/v1/wheels/{test_wheel['id']}/trades")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_wheel_trades_multiple(self, client: TestClient, test_wheel: dict, test_db):
        """Test listing multiple trades for a wheel."""
        # Create first trade
        future_date = (date.today() + timedelta(days=30)).isoformat()
        client.post(
            f"/api/v1/wheels/{test_wheel['id']}/trades",
            json={
                "direction": "put",
                "strike": 150.0,
                "expiration_date": future_date,
                "premium_per_share": 2.50,
                "contracts": 1,
            },
        )

        # Close it and create another
        wheel = test_db.query(Wheel).filter(Wheel.id == test_wheel["id"]).first()
        wheel.state = "cash"
        test_db.commit()

        client.post(
            f"/api/v1/wheels/{test_wheel['id']}/trades",
            json={
                "direction": "put",
                "strike": 145.0,
                "expiration_date": future_date,
                "premium_per_share": 3.00,
                "contracts": 1,
            },
        )

        # List trades
        response = client.get(f"/api/v1/wheels/{test_wheel['id']}/trades")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_wheel_trades_filter_by_outcome(self, client: TestClient, test_wheel: dict, test_db):
        """Test filtering trades by outcome."""
        # Create trade
        future_date = (date.today() + timedelta(days=30)).isoformat()
        response = client.post(
            f"/api/v1/wheels/{test_wheel['id']}/trades",
            json={
                "direction": "put",
                "strike": 150.0,
                "expiration_date": future_date,
                "premium_per_share": 2.50,
                "contracts": 1,
            },
        )

        # Filter for open trades
        response = client.get(f"/api/v1/wheels/{test_wheel['id']}/trades?outcome=open")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["outcome"] == "open"

        # Filter for closed trades
        response = client.get(f"/api/v1/wheels/{test_wheel['id']}/trades?outcome=closed_early")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    def test_list_wheel_trades_pagination(self, client: TestClient, test_wheel: dict, test_db):
        """Test pagination for listing trades."""
        # Create trade
        future_date = (date.today() + timedelta(days=30)).isoformat()
        client.post(
            f"/api/v1/wheels/{test_wheel['id']}/trades",
            json={
                "direction": "put",
                "strike": 150.0,
                "expiration_date": future_date,
                "premium_per_share": 2.50,
                "contracts": 1,
            },
        )

        # Test pagination
        response = client.get(f"/api/v1/wheels/{test_wheel['id']}/trades?skip=0&limit=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    def test_list_all_trades(self, client: TestClient, test_wheel: dict, test_wheel_with_shares: dict):
        """Test listing all trades across wheels."""
        future_date = (date.today() + timedelta(days=30)).isoformat()

        # Create trade for first wheel
        client.post(
            f"/api/v1/wheels/{test_wheel['id']}/trades",
            json={
                "direction": "put",
                "strike": 150.0,
                "expiration_date": future_date,
                "premium_per_share": 2.50,
                "contracts": 1,
            },
        )

        # Create trade for second wheel
        client.post(
            f"/api/v1/wheels/{test_wheel_with_shares['id']}/trades",
            json={
                "direction": "call",
                "strike": 160.0,
                "expiration_date": future_date,
                "premium_per_share": 3.00,
                "contracts": 1,
            },
        )

        # List all trades
        response = client.get("/api/v1/trades")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_all_trades_with_date_filter(self, client: TestClient, test_wheel: dict):
        """Test filtering trades by date range."""
        future_date = (date.today() + timedelta(days=30)).isoformat()

        # Create trade
        client.post(
            f"/api/v1/wheels/{test_wheel['id']}/trades",
            json={
                "direction": "put",
                "strike": 150.0,
                "expiration_date": future_date,
                "premium_per_share": 2.50,
                "contracts": 1,
            },
        )

        # Filter by date
        today_str = date.today().isoformat()
        response = client.get(f"/api/v1/trades?from_date={today_str}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1


class TestTradeGetUpdateDelete:
    """Test cases for get, update, and delete operations."""

    def test_get_trade_success(self, client: TestClient, test_trade: dict):
        """Test getting trade by ID."""
        response = client.get(f"/api/v1/trades/{test_trade['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_trade["id"]
        assert data["direction"] == test_trade["direction"]

    def test_get_trade_not_found(self, client: TestClient):
        """Test getting non-existent trade returns 404."""
        response = client.get("/api/v1/trades/99999")
        assert response.status_code == 404

    def test_update_trade_success(self, client: TestClient, test_trade: dict):
        """Test updating trade details."""
        response = client.put(
            f"/api/v1/trades/{test_trade['id']}",
            json={"premium_per_share": 3.00},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["premium_per_share"] == 3.00
        assert data["total_premium"] == 300.0  # Recalculated

    def test_update_trade_not_found(self, client: TestClient):
        """Test updating non-existent trade returns 404."""
        response = client.put(
            "/api/v1/trades/99999",
            json={"premium_per_share": 3.00},
        )
        assert response.status_code == 404

    def test_delete_trade_success(self, client: TestClient, test_trade: dict):
        """Test deleting trade."""
        response = client.delete(f"/api/v1/trades/{test_trade['id']}")
        assert response.status_code == 204

        # Verify deleted
        response = client.get(f"/api/v1/trades/{test_trade['id']}")
        assert response.status_code == 404

    def test_delete_trade_not_found(self, client: TestClient):
        """Test deleting non-existent trade returns 404."""
        response = client.delete("/api/v1/trades/99999")
        assert response.status_code == 404


class TestTradeExpiration:
    """Test cases for trade expiration with state machine validation."""

    def test_expire_put_assigned(self, client: TestClient, test_trade: dict, test_db):
        """Test expiring a put that gets assigned (price <= strike)."""
        response = client.post(
            f"/api/v1/trades/{test_trade['id']}/expire",
            json={"price_at_expiry": 145.0},  # Below strike of 150
        )
        assert response.status_code == 200
        data = response.json()
        assert data["outcome"] == "assigned"
        assert data["price_at_expiry"] == 145.0
        assert data["closed_at"] is not None

        # Verify wheel state updated to SHARES with shares
        wheel = test_db.query(Wheel).filter(Wheel.id == test_trade["wheel_id"]).first()
        assert wheel.state == "shares"
        assert wheel.shares_held == 100
        assert wheel.cost_basis == 150.0

    def test_expire_put_worthless(self, client: TestClient, test_trade: dict, test_db):
        """Test expiring a put that expires worthless (price > strike)."""
        response = client.post(
            f"/api/v1/trades/{test_trade['id']}/expire",
            json={"price_at_expiry": 155.0},  # Above strike of 150
        )
        assert response.status_code == 200
        data = response.json()
        assert data["outcome"] == "expired_worthless"
        assert data["price_at_expiry"] == 155.0

        # Verify wheel state stays CASH
        wheel = test_db.query(Wheel).filter(Wheel.id == test_trade["wheel_id"]).first()
        assert wheel.state == "cash"
        assert wheel.shares_held == 0

    def test_expire_call_assigned(self, client: TestClient, test_wheel_with_shares: dict, test_db):
        """Test expiring a call that gets assigned (price >= strike)."""
        # Create call trade
        future_date = (date.today() + timedelta(days=30)).isoformat()
        response = client.post(
            f"/api/v1/wheels/{test_wheel_with_shares['id']}/trades",
            json={
                "direction": "call",
                "strike": 160.0,
                "expiration_date": future_date,
                "premium_per_share": 3.00,
                "contracts": 1,
            },
        )
        trade_id = response.json()["id"]

        # Expire with price >= strike
        response = client.post(
            f"/api/v1/trades/{trade_id}/expire",
            json={"price_at_expiry": 165.0},  # Above strike of 160
        )
        assert response.status_code == 200
        data = response.json()
        assert data["outcome"] == "called_away"

        # Verify wheel state updated to CASH with no shares
        wheel = test_db.query(Wheel).filter(Wheel.id == test_wheel_with_shares["id"]).first()
        assert wheel.state == "cash"
        assert wheel.shares_held == 0
        assert wheel.cost_basis is None

    def test_expire_call_worthless(self, client: TestClient, test_wheel_with_shares: dict, test_db):
        """Test expiring a call that expires worthless (price < strike)."""
        # Create call trade
        future_date = (date.today() + timedelta(days=30)).isoformat()
        response = client.post(
            f"/api/v1/wheels/{test_wheel_with_shares['id']}/trades",
            json={
                "direction": "call",
                "strike": 160.0,
                "expiration_date": future_date,
                "premium_per_share": 3.00,
                "contracts": 1,
            },
        )
        trade_id = response.json()["id"]

        # Expire with price < strike
        response = client.post(
            f"/api/v1/trades/{trade_id}/expire",
            json={"price_at_expiry": 155.0},  # Below strike of 160
        )
        assert response.status_code == 200
        data = response.json()
        assert data["outcome"] == "expired_worthless"

        # Verify wheel state stays SHARES
        wheel = test_db.query(Wheel).filter(Wheel.id == test_wheel_with_shares["id"]).first()
        assert wheel.state == "shares"
        assert wheel.shares_held == 100

    def test_expire_trade_not_open(self, client: TestClient, test_trade: dict, test_db):
        """Test expiring already expired trade fails."""
        # Expire trade first time
        client.post(
            f"/api/v1/trades/{test_trade['id']}/expire",
            json={"price_at_expiry": 145.0},
        )

        # Try to expire again
        response = client.post(
            f"/api/v1/trades/{test_trade['id']}/expire",
            json={"price_at_expiry": 145.0},
        )
        assert response.status_code == 400
        assert "not open" in response.json()["detail"].lower()


class TestTradeEarlyClose:
    """Test cases for closing trades early."""

    def test_close_trade_early_success(self, client: TestClient, test_trade: dict, test_db):
        """Test closing trade early."""
        response = client.post(
            f"/api/v1/trades/{test_trade['id']}/close",
            json={"close_price": 1.25},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["outcome"] == "closed_early"
        assert data["close_price"] == 1.25
        assert data["closed_at"] is not None

        # Verify wheel state back to CASH
        wheel = test_db.query(Wheel).filter(Wheel.id == test_trade["wheel_id"]).first()
        assert wheel.state == "cash"

    def test_close_trade_not_open(self, client: TestClient, test_trade: dict):
        """Test closing already closed trade fails."""
        # Close trade first time
        client.post(
            f"/api/v1/trades/{test_trade['id']}/close",
            json={"close_price": 1.25},
        )

        # Try to close again
        response = client.post(
            f"/api/v1/trades/{test_trade['id']}/close",
            json={"close_price": 1.25},
        )
        assert response.status_code == 400
        assert "not open" in response.json()["detail"].lower()

    def test_close_call_early(self, client: TestClient, test_wheel_with_shares: dict, test_db):
        """Test closing call trade early returns to SHARES state."""
        # Create call trade
        future_date = (date.today() + timedelta(days=30)).isoformat()
        response = client.post(
            f"/api/v1/wheels/{test_wheel_with_shares['id']}/trades",
            json={
                "direction": "call",
                "strike": 160.0,
                "expiration_date": future_date,
                "premium_per_share": 3.00,
                "contracts": 1,
            },
        )
        trade_id = response.json()["id"]

        # Close early
        response = client.post(
            f"/api/v1/trades/{trade_id}/close",
            json={"close_price": 1.50},
        )
        assert response.status_code == 200

        # Verify wheel state back to SHARES
        wheel = test_db.query(Wheel).filter(Wheel.id == test_wheel_with_shares["id"]).first()
        assert wheel.state == "shares"
        assert wheel.shares_held == 100
