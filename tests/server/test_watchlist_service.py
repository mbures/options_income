"""Tests for WatchlistService."""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from src.server.database.models.watchlist import WatchlistItem
from src.server.repositories.watchlist import WatchlistRepository
from src.server.repositories.opportunity import OpportunityRepository
from src.server.services.watchlist_service import WatchlistService
from src.wheel.models import WheelRecommendation


class TestWatchlistService:
    """Tests for WatchlistService with mocked engine."""

    @pytest.fixture
    def service(self, test_db):
        """Create a WatchlistService with mocked external clients."""
        with patch("src.server.services.watchlist_service.SchwabClient"):
            with patch("src.server.services.watchlist_service.SchwabPriceDataFetcher"):
                svc = WatchlistService(test_db, schwab_client=Mock())
                svc.recommend_engine = Mock()
                return svc

    def test_add_symbol(self, service):
        item = service.add_symbol("aapl", "Test notes")
        assert item.symbol == "AAPL"
        assert item.notes == "Test notes"

    def test_add_duplicate_raises(self, service):
        service.add_symbol("AAPL")
        with pytest.raises(ValueError):
            service.add_symbol("AAPL")

    def test_remove_symbol(self, service):
        service.add_symbol("AAPL")
        assert service.remove_symbol("AAPL") is True

    def test_list_watchlist(self, service):
        service.add_symbol("AAPL")
        service.add_symbol("MSFT")
        items = service.list_watchlist()
        assert len(items) == 2

    def test_scan_all_empty_watchlist(self, service):
        result = service.scan_all()
        assert result["symbols_scanned"] == 0
        assert result["opportunities_found"] == 0

    def test_scan_all_with_results(self, service):
        service.add_symbol("AAPL")

        mock_rec = WheelRecommendation(
            symbol="AAPL",
            direction="put",
            strike=150.0,
            expiration_date="2026-03-20",
            premium_per_share=2.50,
            contracts=1,
            total_premium=250.0,
            sigma_distance=1.7,
            p_itm=0.12,
            annualized_yield_pct=18.5,
            bias_score=0.75,
            dte=30,
            current_price=155.0,
            bid=2.50,
            ask=2.65,
        )
        service.recommend_engine.scan_opportunities.return_value = [mock_rec]

        result = service.scan_all()
        assert result["symbols_scanned"] == 1
        assert result["opportunities_found"] == 1
        assert result["errors"] == {}

        # Verify opportunities were persisted
        opps = service.get_opportunities()
        assert len(opps) == 1
        assert opps[0].symbol == "AAPL"
        assert opps[0].is_read is False

    def test_scan_all_handles_engine_error(self, service):
        service.add_symbol("AAPL")
        service.recommend_engine.scan_opportunities.side_effect = Exception("API error")

        result = service.scan_all()
        assert result["symbols_scanned"] == 1
        assert result["opportunities_found"] == 0
        assert "AAPL" in result["errors"]

    def test_scan_all_no_results_for_symbol(self, service):
        service.add_symbol("AAPL")
        service.recommend_engine.scan_opportunities.return_value = []

        result = service.scan_all()
        assert result["symbols_scanned"] == 1
        assert result["opportunities_found"] == 0

    def test_get_unread_count(self, service):
        assert service.get_unread_count() == 0

    def test_mark_read(self, service):
        assert service.mark_read(9999) is False

    def test_mark_all_read(self, service):
        count = service.mark_all_read()
        assert count == 0

    def test_remove_symbol_deletes_opportunities(self, service):
        """Removing a symbol should also delete its opportunities."""
        service.add_symbol("AAPL")

        mock_rec = WheelRecommendation(
            symbol="AAPL",
            direction="put",
            strike=150.0,
            expiration_date="2026-03-20",
            premium_per_share=2.50,
            contracts=1,
            total_premium=250.0,
            sigma_distance=1.7,
            p_itm=0.12,
            annualized_yield_pct=18.5,
            bias_score=0.75,
            dte=30,
            current_price=155.0,
            bid=2.50,
            ask=2.65,
        )
        service.recommend_engine.scan_opportunities.return_value = [mock_rec]
        service.scan_all()

        assert len(service.get_opportunities(symbol="AAPL")) == 1

        service.remove_symbol("AAPL")
        assert len(service.get_opportunities(symbol="AAPL")) == 0
