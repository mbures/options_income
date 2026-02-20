"""Tests for WatchlistRepository and OpportunityRepository."""

import pytest
from datetime import datetime, timedelta

from src.server.database.models.opportunity import Opportunity
from src.server.database.models.watchlist import WatchlistItem
from src.server.repositories.watchlist import WatchlistRepository
from src.server.repositories.opportunity import OpportunityRepository


class TestWatchlistRepository:
    """Tests for WatchlistRepository CRUD."""

    def test_add_symbol(self, test_db):
        repo = WatchlistRepository(test_db)
        item = repo.add_symbol("AAPL", "Tech stock")
        assert item.symbol == "AAPL"
        assert item.notes == "Tech stock"
        assert item.id is not None

    def test_add_duplicate_raises(self, test_db):
        repo = WatchlistRepository(test_db)
        repo.add_symbol("AAPL")
        with pytest.raises(ValueError, match="already on the watchlist"):
            repo.add_symbol("AAPL")

    def test_remove_symbol(self, test_db):
        repo = WatchlistRepository(test_db)
        repo.add_symbol("AAPL")
        assert repo.remove_symbol("AAPL") is True
        assert repo.get_by_symbol("AAPL") is None

    def test_remove_nonexistent(self, test_db):
        repo = WatchlistRepository(test_db)
        assert repo.remove_symbol("NOPE") is False

    def test_list_all_sorted(self, test_db):
        repo = WatchlistRepository(test_db)
        repo.add_symbol("MSFT")
        repo.add_symbol("AAPL")
        repo.add_symbol("TSLA")
        items = repo.list_all()
        assert [i.symbol for i in items] == ["AAPL", "MSFT", "TSLA"]

    def test_get_by_symbol(self, test_db):
        repo = WatchlistRepository(test_db)
        repo.add_symbol("AAPL")
        item = repo.get_by_symbol("aapl")  # case insensitive lookup
        assert item is not None
        assert item.symbol == "AAPL"


class TestOpportunityRepository:
    """Tests for OpportunityRepository."""

    def _make_opportunity(self, symbol="AAPL", direction="put", profile="conservative",
                          is_read=False, scanned_at=None):
        return Opportunity(
            symbol=symbol,
            direction=direction,
            profile=profile,
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
            is_read=is_read,
            scanned_at=scanned_at or datetime.utcnow(),
        )

    def test_bulk_create(self, test_db):
        repo = OpportunityRepository(test_db)
        opps = [self._make_opportunity(), self._make_opportunity(symbol="MSFT")]
        count = repo.bulk_create(opps)
        assert count == 2

    def test_list_all(self, test_db):
        repo = OpportunityRepository(test_db)
        repo.bulk_create([self._make_opportunity(), self._make_opportunity(symbol="MSFT")])
        results = repo.list_opportunities()
        assert len(results) == 2

    def test_filter_by_symbol(self, test_db):
        repo = OpportunityRepository(test_db)
        repo.bulk_create([
            self._make_opportunity(symbol="AAPL"),
            self._make_opportunity(symbol="MSFT"),
        ])
        results = repo.list_opportunities(symbol="AAPL")
        assert len(results) == 1
        assert results[0].symbol == "AAPL"

    def test_filter_by_direction(self, test_db):
        repo = OpportunityRepository(test_db)
        repo.bulk_create([
            self._make_opportunity(direction="put"),
            self._make_opportunity(direction="call"),
        ])
        results = repo.list_opportunities(direction="call")
        assert len(results) == 1
        assert results[0].direction == "call"

    def test_filter_unread_only(self, test_db):
        repo = OpportunityRepository(test_db)
        repo.bulk_create([
            self._make_opportunity(is_read=False),
            self._make_opportunity(is_read=True),
        ])
        results = repo.list_opportunities(unread_only=True)
        assert len(results) == 1
        assert results[0].is_read is False

    def test_get_unread_count(self, test_db):
        repo = OpportunityRepository(test_db)
        repo.bulk_create([
            self._make_opportunity(is_read=False),
            self._make_opportunity(is_read=False),
            self._make_opportunity(is_read=True),
        ])
        assert repo.get_unread_count() == 2

    def test_mark_read(self, test_db):
        repo = OpportunityRepository(test_db)
        opp = self._make_opportunity()
        test_db.add(opp)
        test_db.commit()
        test_db.refresh(opp)

        assert repo.mark_read(opp.id) is True
        test_db.refresh(opp)
        assert opp.is_read is True

    def test_mark_read_not_found(self, test_db):
        repo = OpportunityRepository(test_db)
        assert repo.mark_read(9999) is False

    def test_mark_all_read(self, test_db):
        repo = OpportunityRepository(test_db)
        repo.bulk_create([
            self._make_opportunity(is_read=False),
            self._make_opportunity(is_read=False),
        ])
        count = repo.mark_all_read()
        assert count == 2
        assert repo.get_unread_count() == 0

    def test_purge_stale(self, test_db):
        repo = OpportunityRepository(test_db)
        old_time = datetime.utcnow() - timedelta(hours=25)
        repo.bulk_create([
            self._make_opportunity(scanned_at=old_time),
            self._make_opportunity(scanned_at=datetime.utcnow()),
        ])
        purged = repo.purge_stale(max_age_hours=24)
        assert purged == 1
        assert len(repo.list_opportunities()) == 1

    def test_delete_all_for_symbol(self, test_db):
        repo = OpportunityRepository(test_db)
        repo.bulk_create([
            self._make_opportunity(symbol="AAPL"),
            self._make_opportunity(symbol="AAPL"),
            self._make_opportunity(symbol="MSFT"),
        ])
        count = repo.delete_all_for_symbol("AAPL")
        assert count == 2
        assert len(repo.list_opportunities()) == 1
