"""Tests for watchlist and opportunity ORM models and Pydantic schemas."""

import pytest
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from src.server.database.models.watchlist import WatchlistItem
from src.server.database.models.opportunity import Opportunity
from src.server.models.watchlist import (
    WatchlistItemCreate,
    OpportunityResponse,
    OpportunityCountResponse,
    ScanResultResponse,
)


class TestWatchlistItemModel:
    """Tests for WatchlistItem ORM model."""

    def test_create_watchlist_item(self, test_db):
        item = WatchlistItem(symbol="AAPL", notes="Tech stock")
        test_db.add(item)
        test_db.commit()
        test_db.refresh(item)

        assert item.id is not None
        assert item.symbol == "AAPL"
        assert item.notes == "Tech stock"
        assert item.created_at is not None

    def test_create_watchlist_item_no_notes(self, test_db):
        item = WatchlistItem(symbol="MSFT")
        test_db.add(item)
        test_db.commit()
        test_db.refresh(item)

        assert item.notes is None

    def test_unique_symbol_constraint(self, test_db):
        item1 = WatchlistItem(symbol="AAPL")
        test_db.add(item1)
        test_db.commit()

        item2 = WatchlistItem(symbol="AAPL")
        test_db.add(item2)
        with pytest.raises(IntegrityError):
            test_db.commit()

    def test_repr(self, test_db):
        item = WatchlistItem(symbol="TSLA")
        test_db.add(item)
        test_db.commit()
        test_db.refresh(item)
        assert "TSLA" in repr(item)


class TestOpportunityModel:
    """Tests for Opportunity ORM model."""

    def test_create_opportunity(self, test_db):
        opp = Opportunity(
            symbol="AAPL",
            direction="put",
            profile="conservative",
            strike=150.0,
            expiration_date="2026-03-20",
            premium_per_share=2.50,
            total_premium=250.0,
            p_itm=0.12,
            sigma_distance=1.7,
            annualized_yield_pct=18.5,
            bias_score=0.75,
            dte=30,
            current_price=155.0,
            bid=2.50,
            ask=2.65,
            is_read=False,
            scanned_at=datetime.utcnow(),
        )
        test_db.add(opp)
        test_db.commit()
        test_db.refresh(opp)

        assert opp.id is not None
        assert opp.symbol == "AAPL"
        assert opp.direction == "put"
        assert opp.is_read is False

    def test_default_values(self, test_db):
        opp = Opportunity(
            symbol="MSFT",
            direction="call",
            profile="aggressive",
            strike=400.0,
            expiration_date="2026-03-20",
            premium_per_share=3.0,
            total_premium=300.0,
            p_itm=0.25,
            sigma_distance=0.8,
            annualized_yield_pct=25.0,
            dte=14,
            current_price=395.0,
            bid=3.0,
            ask=3.20,
        )
        test_db.add(opp)
        test_db.commit()
        test_db.refresh(opp)

        assert opp.is_read is False
        assert opp.scanned_at is not None

    def test_repr(self, test_db):
        opp = Opportunity(
            symbol="TSLA",
            direction="put",
            profile="conservative",
            strike=200.0,
            expiration_date="2026-03-20",
            premium_per_share=5.0,
            total_premium=500.0,
            p_itm=0.10,
            sigma_distance=1.8,
            annualized_yield_pct=20.0,
            dte=25,
            current_price=210.0,
            bid=5.0,
            ask=5.30,
        )
        test_db.add(opp)
        test_db.commit()
        test_db.refresh(opp)
        assert "TSLA" in repr(opp)


class TestPydanticModels:
    """Tests for Pydantic watchlist/opportunity models."""

    def test_watchlist_item_create_uppercases(self):
        item = WatchlistItemCreate(symbol="aapl")
        assert item.symbol == "AAPL"

    def test_watchlist_item_create_strips(self):
        item = WatchlistItemCreate(symbol="  msft  ")
        assert item.symbol == "MSFT"

    def test_watchlist_item_create_invalid_symbol(self):
        with pytest.raises(ValueError):
            WatchlistItemCreate(symbol="")

    def test_watchlist_item_create_with_notes(self):
        item = WatchlistItemCreate(symbol="AAPL", notes="Good for puts")
        assert item.notes == "Good for puts"

    def test_opportunity_count_response(self):
        resp = OpportunityCountResponse(unread_count=5)
        assert resp.unread_count == 5

    def test_scan_result_response(self):
        resp = ScanResultResponse(
            opportunities_found=10,
            symbols_scanned=3,
            errors={"BAD": "Not found"},
        )
        assert resp.opportunities_found == 10
        assert resp.symbols_scanned == 3
        assert resp.errors == {"BAD": "Not found"}
