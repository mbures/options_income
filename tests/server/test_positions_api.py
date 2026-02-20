"""Integration tests for Position API endpoints.

Tests position monitoring operations including status tracking,
risk assessment, batch operations, and filtering.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.server.database.models.trade import Trade


@pytest.fixture
def portfolio_id(client: TestClient) -> str:
    """Create a test portfolio and return its ID."""
    response = client.post(
        "/api/v1/portfolios/",
        json={"name": "Test Portfolio", "default_capital": 50000.0},
    )
    return response.json()["id"]


@pytest.fixture
def wheel_with_open_put(client: TestClient, portfolio_id: str) -> dict:
    """Create a wheel with an open put trade."""
    # Create wheel
    wheel_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/wheels",
        json={
            "symbol": "AAPL",
            "capital_allocated": 15000.0,
            "profile": "conservative",
        },
    )
    wheel = wheel_response.json()

    # Create open put trade
    expiration = (date.today() + timedelta(days=14)).strftime("%Y-%m-%d")
    trade_response = client.post(
        f"/api/v1/wheels/{wheel['id']}/trades",
        json={
            "direction": "put",
            "strike": 150.0,
            "expiration_date": expiration,
            "premium_per_share": 2.50,
            "contracts": 1,
        },
    )
    trade = trade_response.json()

    return {"wheel": wheel, "trade": trade}


@pytest.fixture
def wheel_with_open_call(client: TestClient, portfolio_id: str, test_db) -> dict:
    """Create a wheel with an open call trade."""
    # Create wheel with shares
    wheel_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/wheels",
        json={
            "symbol": "MSFT",
            "capital_allocated": 20000.0,
            "profile": "moderate",
        },
    )
    wheel = wheel_response.json()

    # Manually set wheel state to shares (simulating assignment)
    from src.server.database.models.wheel import Wheel

    db_wheel = test_db.query(Wheel).filter(Wheel.id == wheel["id"]).first()
    db_wheel.state = "shares"
    db_wheel.shares_held = 100
    db_wheel.cost_basis = 200.0
    test_db.commit()

    # Create open call trade
    expiration = (date.today() + timedelta(days=21)).strftime("%Y-%m-%d")
    trade_response = client.post(
        f"/api/v1/wheels/{wheel['id']}/trades",
        json={
            "direction": "call",
            "strike": 210.0,
            "expiration_date": expiration,
            "premium_per_share": 3.00,
            "contracts": 1,
        },
    )
    trade = trade_response.json()

    return {"wheel": wheel, "trade": trade}


@pytest.fixture
def mock_schwab_price():
    """Mock Schwab client for price and quote data fetching."""
    with patch(
        "src.wheel.monitor.PositionMonitor._fetch_quote_data"
    ) as mock_quote, patch(
        "src.server.tasks.market_hours.is_market_open", return_value=False
    ):
        # Default: return prices >5% from strike for LOW risk
        # AAPL: 160.00 (6.67% above strike of 150.0)
        # MSFT: 200.00 (4.76% below strike of 210.0) = MEDIUM risk
        def side_effect(symbol, force_refresh=False):
            prices = {"AAPL": 160.00, "MSFT": 200.00, "GOOGL": 142.00}
            price = prices.get(symbol, 150.0)
            return {
                "lastPrice": price,
                "openPrice": price - 1.0,
                "highPrice": price + 1.0,
                "lowPrice": price - 2.0,
                "closePrice": price - 0.5,
            }

        mock_quote.side_effect = side_effect
        yield mock_quote


class TestGetPositionStatus:
    """Test cases for getting single position status."""

    def test_get_position_status_otm_put(
        self, client: TestClient, wheel_with_open_put: dict, mock_schwab_price
    ):
        """Test getting status for OTM put position."""
        wheel_id = wheel_with_open_put["wheel"]["id"]

        response = client.get(f"/api/v1/wheels/{wheel_id}/position")
        assert response.status_code == 200

        data = response.json()
        assert data["wheel_id"] == wheel_id
        assert data["symbol"] == "AAPL"
        assert data["direction"] == "put"
        assert data["strike"] == 150.0
        assert data["current_price"] == 160.00  # 6.67% above strike
        assert data["is_otm"] is True
        assert data["is_itm"] is False
        assert data["risk_level"] == "LOW"  # >5% away = LOW risk
        assert data["risk_icon"] == "🟢"
        assert data["dte_calendar"] == 14
        assert "Low risk" in data["risk_description"]
        assert data["premium_collected"] == 250.0

    def test_get_position_status_itm_put(
        self, client: TestClient, wheel_with_open_put: dict
    ):
        """Test getting status for ITM put position."""
        wheel_id = wheel_with_open_put["wheel"]["id"]

        # Mock price below strike (ITM)
        with patch(
            "src.wheel.monitor.PositionMonitor._fetch_quote_data"
        ) as mock_quote, patch(
            "src.server.tasks.market_hours.is_market_open", return_value=False
        ):
            mock_quote.return_value = {
                "lastPrice": 145.0,
                "openPrice": None,
                "highPrice": None,
                "lowPrice": None,
                "closePrice": None,
            }

            response = client.get(f"/api/v1/wheels/{wheel_id}/position")
            assert response.status_code == 200

            data = response.json()
            assert data["is_itm"] is True
            assert data["is_otm"] is False
            assert data["risk_level"] == "HIGH"
            assert data["risk_icon"] == "🔴"
            assert "High risk" in data["risk_description"]
            assert "assignment likely" in data["risk_description"]

    def test_get_position_status_medium_risk(
        self, client: TestClient, wheel_with_open_put: dict
    ):
        """Test getting status for medium risk position (OTM but close to strike)."""
        wheel_id = wheel_with_open_put["wheel"]["id"]

        # Mock price close to strike (3% OTM - within danger zone)
        with patch(
            "src.wheel.monitor.PositionMonitor._fetch_quote_data"
        ) as mock_quote, patch(
            "src.server.tasks.market_hours.is_market_open", return_value=False
        ):
            mock_quote.return_value = {
                "lastPrice": 154.0,
                "openPrice": None,
                "highPrice": None,
                "lowPrice": None,
                "closePrice": None,
            }

            response = client.get(f"/api/v1/wheels/{wheel_id}/position")
            assert response.status_code == 200

            data = response.json()
            assert data["is_otm"] is True
            assert data["risk_level"] == "MEDIUM"
            assert data["risk_icon"] == "🟡"
            assert "Medium risk" in data["risk_description"]

    def test_get_position_status_call_position(
        self, client: TestClient, wheel_with_open_call: dict, mock_schwab_price
    ):
        """Test getting status for call position."""
        wheel_id = wheel_with_open_call["wheel"]["id"]

        response = client.get(f"/api/v1/wheels/{wheel_id}/position")
        assert response.status_code == 200

        data = response.json()
        assert data["symbol"] == "MSFT"
        assert data["direction"] == "call"
        assert data["strike"] == 210.0
        assert data["current_price"] == 200.00  # 4.76% below strike
        assert data["is_otm"] is True
        assert data["risk_level"] == "MEDIUM"  # Within 5% = MEDIUM risk

    def test_get_position_status_force_refresh(
        self, client: TestClient, wheel_with_open_put: dict, mock_schwab_price
    ):
        """Test force refresh parameter."""
        wheel_id = wheel_with_open_put["wheel"]["id"]

        # Call with force_refresh=True
        response = client.get(
            f"/api/v1/wheels/{wheel_id}/position?force_refresh=true"
        )
        assert response.status_code == 200

        # Verify mock was called with force_refresh=True
        mock_schwab_price.assert_called()

    def test_get_position_status_wheel_not_found(self, client: TestClient):
        """Test getting status for non-existent wheel."""
        response = client.get("/api/v1/wheels/99999/position")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_position_status_no_open_position(
        self, client: TestClient, portfolio_id: str
    ):
        """Test getting status for wheel with no open position."""
        # Create wheel without trade
        wheel_response = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "TSLA",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        )
        wheel_id = wheel_response.json()["id"]

        response = client.get(f"/api/v1/wheels/{wheel_id}/position")
        assert response.status_code == 404
        assert "no open position" in response.json()["detail"].lower()


class TestGetPortfolioPositions:
    """Test cases for getting portfolio positions."""

    def test_get_portfolio_positions_empty(
        self, client: TestClient, portfolio_id: str
    ):
        """Test getting positions for portfolio with no open positions."""
        response = client.get(f"/api/v1/portfolios/{portfolio_id}/positions")
        assert response.status_code == 200

        data = response.json()
        assert data["positions"] == []
        assert data["total_count"] == 0
        assert data["high_risk_count"] == 0

    def test_get_portfolio_positions_multiple(
        self,
        client: TestClient,
        portfolio_id: str,
        wheel_with_open_put: dict,
        wheel_with_open_call: dict,
        mock_schwab_price,
    ):
        """Test getting multiple positions in portfolio."""
        response = client.get(f"/api/v1/portfolios/{portfolio_id}/positions")
        assert response.status_code == 200

        data = response.json()
        assert data["total_count"] == 2
        assert len(data["positions"]) == 2
        # AAPL: LOW risk (6.67% from strike), MSFT: MEDIUM risk (4.76% from strike)
        assert data["low_risk_count"] == 1
        assert data["medium_risk_count"] == 1
        assert data["high_risk_count"] == 0

        # Verify summary fields
        symbols = [p["symbol"] for p in data["positions"]]
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    def test_get_portfolio_positions_filter_by_risk(
        self,
        client: TestClient,
        portfolio_id: str,
        wheel_with_open_put: dict,
        mock_schwab_price,
    ):
        """Test filtering positions by risk level."""
        # Get only LOW risk positions
        response = client.get(
            f"/api/v1/portfolios/{portfolio_id}/positions?risk_level=LOW"
        )
        assert response.status_code == 200

        data = response.json()
        assert all(p["risk_level"] == "LOW" for p in data["positions"])

        # Try HIGH risk filter (should return empty)
        response = client.get(
            f"/api/v1/portfolios/{portfolio_id}/positions?risk_level=HIGH"
        )
        assert response.status_code == 200
        assert response.json()["total_count"] == 0

    def test_get_portfolio_positions_filter_by_dte(
        self,
        client: TestClient,
        portfolio_id: str,
        wheel_with_open_put: dict,
        wheel_with_open_call: dict,
        mock_schwab_price,
    ):
        """Test filtering positions by days to expiration."""
        # Filter: 10-20 DTE (should include 14 DTE put, exclude 21 DTE call)
        response = client.get(
            f"/api/v1/portfolios/{portfolio_id}/positions?min_dte=10&max_dte=20"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["total_count"] == 1
        assert data["positions"][0]["symbol"] == "AAPL"
        assert 10 <= data["positions"][0]["dte_calendar"] <= 20

    def test_get_portfolio_positions_invalid_risk_level(
        self, client: TestClient, portfolio_id: str
    ):
        """Test invalid risk level filter."""
        response = client.get(
            f"/api/v1/portfolios/{portfolio_id}/positions?risk_level=INVALID"
        )
        assert response.status_code == 422

    def test_get_portfolio_positions_invalid_dte_range(
        self, client: TestClient, portfolio_id: str
    ):
        """Test invalid DTE range (min > max)."""
        response = client.get(
            f"/api/v1/portfolios/{portfolio_id}/positions?min_dte=20&max_dte=10"
        )
        assert response.status_code == 422


class TestGetAllOpenPositions:
    """Test cases for getting all open positions."""

    def test_get_all_open_positions_empty(self, client: TestClient):
        """Test getting all positions when none exist."""
        response = client.get("/api/v1/positions/open")
        assert response.status_code == 200

        data = response.json()
        assert data["total_count"] == 0

    def test_get_all_open_positions_multiple_portfolios(
        self, client: TestClient, mock_schwab_price
    ):
        """Test getting positions across multiple portfolios."""
        # Create two portfolios with positions
        portfolio1_resp = client.post(
            "/api/v1/portfolios/", json={"name": "Portfolio 1"}
        )
        assert portfolio1_resp.status_code == 201
        portfolio1 = portfolio1_resp.json()["id"]

        portfolio2_resp = client.post(
            "/api/v1/portfolios/", json={"name": "Portfolio 2"}
        )
        assert portfolio2_resp.status_code == 201
        portfolio2 = portfolio2_resp.json()["id"]

        # Create wheels with trades in each portfolio
        for portfolio_id in [portfolio1, portfolio2]:
            wheel_resp = client.post(
                f"/api/v1/portfolios/{portfolio_id}/wheels",
                json={
                    "symbol": f"TST{portfolio_id[:4]}",  # Use first 4 chars of UUID
                    "capital_allocated": 10000.0,
                    "profile": "conservative",
                },
            )
            assert wheel_resp.status_code == 201
            wheel = wheel_resp.json()

            expiration = (date.today() + timedelta(days=14)).strftime("%Y-%m-%d")
            trade_resp = client.post(
                f"/api/v1/wheels/{wheel['id']}/trades",
                json={
                    "direction": "put",
                    "strike": 100.0,
                    "expiration_date": expiration,
                    "premium_per_share": 2.00,
                    "contracts": 1,
                },
            )
            assert trade_resp.status_code == 201

        # Get all open positions
        response = client.get("/api/v1/positions/open")
        assert response.status_code == 200

        data = response.json()
        assert data["total_count"] == 2

    def test_get_all_open_positions_with_filters(
        self,
        client: TestClient,
        wheel_with_open_put: dict,
        wheel_with_open_call: dict,
        mock_schwab_price,
    ):
        """Test getting all positions with filters."""
        # Filter by risk level
        response = client.get("/api/v1/positions/open?risk_level=LOW")
        assert response.status_code == 200
        assert response.json()["total_count"] >= 0

        # Filter by DTE range
        response = client.get("/api/v1/positions/open?min_dte=10&max_dte=30")
        assert response.status_code == 200


class TestGetRiskAssessment:
    """Test cases for risk assessment endpoint."""

    def test_get_risk_assessment_low_risk(
        self, client: TestClient, wheel_with_open_put: dict, mock_schwab_price
    ):
        """Test risk assessment for low risk position."""
        wheel_id = wheel_with_open_put["wheel"]["id"]

        response = client.get(f"/api/v1/wheels/{wheel_id}/risk")
        assert response.status_code == 200

        data = response.json()
        assert data["wheel_id"] == wheel_id
        assert data["symbol"] == "AAPL"
        assert data["risk_level"] == "LOW"
        assert data["risk_icon"] == "🟢"
        assert data["is_itm"] is False
        assert "Low risk" in data["risk_description"]

    def test_get_risk_assessment_high_risk(
        self, client: TestClient, wheel_with_open_put: dict
    ):
        """Test risk assessment for high risk position."""
        wheel_id = wheel_with_open_put["wheel"]["id"]

        # Mock ITM price
        with patch(
            "src.wheel.monitor.PositionMonitor._fetch_quote_data"
        ) as mock_quote, patch(
            "src.server.tasks.market_hours.is_market_open", return_value=False
        ):
            mock_quote.return_value = {
                "lastPrice": 145.0,
                "openPrice": None,
                "highPrice": None,
                "lowPrice": None,
                "closePrice": None,
            }

            response = client.get(f"/api/v1/wheels/{wheel_id}/risk")
            assert response.status_code == 200

            data = response.json()
            assert data["risk_level"] == "HIGH"
            assert data["risk_icon"] == "🔴"
            assert data["is_itm"] is True
            assert "High risk" in data["risk_description"]

    def test_get_risk_assessment_wheel_not_found(self, client: TestClient):
        """Test risk assessment for non-existent wheel."""
        response = client.get("/api/v1/wheels/99999/risk")
        assert response.status_code == 404

    def test_get_risk_assessment_no_open_position(
        self, client: TestClient, portfolio_id: str
    ):
        """Test risk assessment for wheel with no open position."""
        wheel = client.post(
            f"/api/v1/portfolios/{portfolio_id}/wheels",
            json={
                "symbol": "NVDA",
                "capital_allocated": 10000.0,
                "profile": "conservative",
            },
        ).json()

        response = client.get(f"/api/v1/wheels/{wheel['id']}/risk")
        assert response.status_code == 404


class TestPositionStatusFields:
    """Test cases for position status field calculations."""

    def test_moneyness_calculation_put_otm(
        self, client: TestClient, wheel_with_open_put: dict
    ):
        """Test moneyness calculation for OTM put."""
        wheel_id = wheel_with_open_put["wheel"]["id"]

        with patch(
            "src.wheel.monitor.PositionMonitor._fetch_quote_data"
        ) as mock_quote, patch(
            "src.server.tasks.market_hours.is_market_open", return_value=False
        ):
            mock_quote.return_value = {
                "lastPrice": 155.0,
                "openPrice": None,
                "highPrice": None,
                "lowPrice": None,
                "closePrice": None,
            }

            response = client.get(f"/api/v1/wheels/{wheel_id}/position")
            data = response.json()

            # For put: OTM when price > strike, moneyness_pct positive
            assert data["moneyness_pct"] > 0
            assert data["is_otm"] is True
            assert "OTM" in data["moneyness_label"]

    def test_moneyness_calculation_put_itm(
        self, client: TestClient, wheel_with_open_put: dict
    ):
        """Test moneyness calculation for ITM put."""
        wheel_id = wheel_with_open_put["wheel"]["id"]

        with patch(
            "src.wheel.monitor.PositionMonitor._fetch_quote_data"
        ) as mock_quote, patch(
            "src.server.tasks.market_hours.is_market_open", return_value=False
        ):
            mock_quote.return_value = {
                "lastPrice": 145.0,
                "openPrice": None,
                "highPrice": None,
                "lowPrice": None,
                "closePrice": None,
            }

            response = client.get(f"/api/v1/wheels/{wheel_id}/position")
            data = response.json()

            # For put: ITM when price < strike
            assert data["is_itm"] is True
            assert "ITM" in data["moneyness_label"]

    def test_dte_calculations(
        self, client: TestClient, wheel_with_open_put: dict, mock_schwab_price
    ):
        """Test DTE calculations are present."""
        wheel_id = wheel_with_open_put["wheel"]["id"]

        response = client.get(f"/api/v1/wheels/{wheel_id}/position")
        data = response.json()

        # Verify both DTE fields are present and reasonable
        assert data["dte_calendar"] == 14
        assert data["dte_trading"] <= data["dte_calendar"]
        assert data["dte_trading"] >= 0
