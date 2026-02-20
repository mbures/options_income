"""Integration tests for Watchlist and Opportunity API endpoints."""

import pytest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient


class TestWatchlistEndpoints:
    """Tests for watchlist CRUD endpoints."""

    def test_list_empty_watchlist(self, client: TestClient):
        response = client.get("/api/v1/watchlist")
        assert response.status_code == 200
        assert response.json() == []

    def test_add_to_watchlist(self, client: TestClient):
        response = client.post(
            "/api/v1/watchlist",
            json={"symbol": "AAPL", "notes": "Tech stock"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["notes"] == "Tech stock"
        assert "id" in data
        assert "created_at" in data

    def test_add_duplicate_returns_409(self, client: TestClient):
        client.post("/api/v1/watchlist", json={"symbol": "AAPL"})
        response = client.post("/api/v1/watchlist", json={"symbol": "AAPL"})
        assert response.status_code == 409

    def test_add_lowercase_uppercased(self, client: TestClient):
        response = client.post("/api/v1/watchlist", json={"symbol": "aapl"})
        assert response.status_code == 201
        assert response.json()["symbol"] == "AAPL"

    def test_list_watchlist(self, client: TestClient):
        client.post("/api/v1/watchlist", json={"symbol": "AAPL"})
        client.post("/api/v1/watchlist", json={"symbol": "MSFT"})
        response = client.get("/api/v1/watchlist")
        assert response.status_code == 200
        symbols = [item["symbol"] for item in response.json()]
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    def test_remove_from_watchlist(self, client: TestClient):
        client.post("/api/v1/watchlist", json={"symbol": "AAPL"})
        response = client.delete("/api/v1/watchlist/AAPL")
        assert response.status_code == 204

        # Verify removed
        response = client.get("/api/v1/watchlist")
        assert len(response.json()) == 0

    def test_remove_nonexistent_returns_404(self, client: TestClient):
        response = client.delete("/api/v1/watchlist/NOPE")
        assert response.status_code == 404


class TestOpportunityEndpoints:
    """Tests for opportunity endpoints."""

    def test_list_opportunities_empty(self, client: TestClient):
        response = client.get("/api/v1/opportunities")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_unread_count_zero(self, client: TestClient):
        response = client.get("/api/v1/opportunities/count")
        assert response.status_code == 200
        assert response.json()["unread_count"] == 0

    def test_mark_nonexistent_returns_404(self, client: TestClient):
        response = client.post("/api/v1/opportunities/9999/read")
        assert response.status_code == 404

    def test_mark_all_read_empty(self, client: TestClient):
        response = client.post("/api/v1/opportunities/read-all")
        assert response.status_code == 204

    def test_trigger_scan_empty_watchlist(self, client: TestClient):
        """Scan with empty watchlist should return 0 results."""
        response = client.post("/api/v1/watchlist/scan")
        assert response.status_code == 200
        data = response.json()
        assert data["symbols_scanned"] == 0
        assert data["opportunities_found"] == 0

    def test_invalid_symbol_rejected(self, client: TestClient):
        response = client.post("/api/v1/watchlist", json={"symbol": ""})
        assert response.status_code == 422
