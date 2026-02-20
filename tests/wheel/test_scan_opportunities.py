"""Tests for RecommendEngine.scan_opportunities()."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

from src.models.profiles import StrikeProfile
from src.wheel.recommend import RecommendEngine
from src.wheel.models import WheelRecommendation


class TestScanOpportunities:
    """Tests for the scan_opportunities method."""

    @pytest.fixture
    def engine(self):
        """Create a RecommendEngine with mocked clients."""
        engine = RecommendEngine(
            finnhub_client=Mock(),
            price_fetcher=Mock(),
            schwab_client=Mock(),
        )
        return engine

    def _mock_chain(self):
        """Create a mock options chain."""
        chain = Mock()

        # Create mock put and call contracts
        put_contract = Mock()
        put_contract.strike = 145.0
        put_contract.bid = 2.50
        put_contract.ask = 2.75
        put_contract.expiration_date = "2026-03-20"

        call_contract = Mock()
        call_contract.strike = 160.0
        call_contract.bid = 1.80
        call_contract.ask = 2.00
        call_contract.expiration_date = "2026-03-20"

        chain.get_puts.return_value = [put_contract]
        chain.get_calls.return_value = [call_contract]
        return chain

    def test_scan_fetches_data_once(self, engine):
        """Verify market data is fetched once per symbol, not per direction/profile."""
        engine._fetch_options_chain = Mock(return_value=self._mock_chain())
        engine._fetch_current_price = Mock(return_value=155.0)
        engine._estimate_volatility = Mock(return_value=0.30)
        engine._get_candidates = Mock(return_value=[])

        profiles = [StrikeProfile.CONSERVATIVE, StrikeProfile.AGGRESSIVE]
        engine.scan_opportunities("AAPL", profiles, max_dte=45)

        # Should fetch chain, price, volatility exactly once
        engine._fetch_options_chain.assert_called_once_with("AAPL")
        engine._fetch_current_price.assert_called_once_with("AAPL")
        engine._estimate_volatility.assert_called_once()

    def test_scan_calls_get_candidates_for_each_combo(self, engine):
        """Should call _get_candidates for each (direction, profile) pair."""
        engine._fetch_options_chain = Mock(return_value=self._mock_chain())
        engine._fetch_current_price = Mock(return_value=155.0)
        engine._estimate_volatility = Mock(return_value=0.30)
        engine._get_candidates = Mock(return_value=[])

        profiles = [StrikeProfile.CONSERVATIVE, StrikeProfile.AGGRESSIVE]
        engine.scan_opportunities("AAPL", profiles, max_dte=45)

        # 2 directions x 2 profiles = 4 calls
        assert engine._get_candidates.call_count == 4

    def test_scan_normalizes_to_one_contract(self, engine):
        """Results should be normalized to 1 contract."""
        rec = WheelRecommendation(
            symbol="AAPL",
            direction="put",
            strike=150.0,
            expiration_date="2026-03-20",
            premium_per_share=2.50,
            contracts=5,  # Will be normalized
            total_premium=1250.0,  # Will be recalculated
            sigma_distance=1.7,
            p_itm=0.12,
            annualized_yield_pct=18.5,
            dte=30,
            current_price=155.0,
            bid=2.50,
            ask=2.65,
        )

        engine._fetch_options_chain = Mock(return_value=self._mock_chain())
        engine._fetch_current_price = Mock(return_value=155.0)
        engine._estimate_volatility = Mock(return_value=0.30)
        engine._get_candidates = Mock(return_value=[rec])

        results = engine.scan_opportunities(
            "AAPL", [StrikeProfile.CONSERVATIVE], max_dte=45,
        )

        # All results should have contracts=1
        for r in results:
            assert r.contracts == 1
            assert r.total_premium == r.premium_per_share * 100

    def test_scan_returns_empty_when_no_candidates(self, engine):
        engine._fetch_options_chain = Mock(return_value=self._mock_chain())
        engine._fetch_current_price = Mock(return_value=155.0)
        engine._estimate_volatility = Mock(return_value=0.30)
        engine._get_candidates = Mock(return_value=[])

        results = engine.scan_opportunities(
            "AAPL", [StrikeProfile.CONSERVATIVE], max_dte=45,
        )
        assert results == []

    def test_scan_handles_candidate_error_gracefully(self, engine):
        """If _get_candidates raises for one combo, others should still work."""
        rec = WheelRecommendation(
            symbol="AAPL",
            direction="call",
            strike=160.0,
            expiration_date="2026-03-20",
            premium_per_share=1.80,
            contracts=1,
            total_premium=180.0,
            sigma_distance=1.5,
            p_itm=0.10,
            annualized_yield_pct=15.0,
            dte=30,
            current_price=155.0,
            bid=1.80,
            ask=2.00,
        )

        engine._fetch_options_chain = Mock(return_value=self._mock_chain())
        engine._fetch_current_price = Mock(return_value=155.0)
        engine._estimate_volatility = Mock(return_value=0.30)

        # First call raises, second returns results
        engine._get_candidates = Mock(side_effect=[
            Exception("API error"),
            [rec],
        ])

        results = engine.scan_opportunities(
            "AAPL", [StrikeProfile.CONSERVATIVE], max_dte=45,
        )
        # Should still get results from the successful call
        assert len(results) >= 1

    def test_scan_uses_synthetic_positions(self, engine):
        """Verify synthetic positions use correct state and capital."""
        engine._fetch_options_chain = Mock(return_value=self._mock_chain())
        engine._fetch_current_price = Mock(return_value=155.0)
        engine._estimate_volatility = Mock(return_value=0.30)
        engine._get_candidates = Mock(return_value=[])

        engine.scan_opportunities("AAPL", [StrikeProfile.CONSERVATIVE], max_dte=45)

        # Check the synthetic positions passed to _get_candidates
        calls = engine._get_candidates.call_args_list
        for call in calls:
            pos = call.kwargs["position"]
            if call.kwargs["direction"] == "put":
                assert pos.state.value == "cash"
                assert pos.capital_allocated == 999_999_999
            else:
                assert pos.state.value == "shares"
                assert pos.shares_held == 100

    def test_scan_results_sorted_by_bias_score(self, engine):
        """Results should be sorted by bias_score descending."""
        rec1 = WheelRecommendation(
            symbol="AAPL", direction="put", strike=145.0,
            expiration_date="2026-03-20", premium_per_share=2.0,
            contracts=1, total_premium=200.0, sigma_distance=1.5,
            p_itm=0.15, annualized_yield_pct=15.0, dte=30,
            current_price=155.0, bid=2.0, ask=2.2,
        )
        rec2 = WheelRecommendation(
            symbol="AAPL", direction="put", strike=140.0,
            expiration_date="2026-03-20", premium_per_share=1.5,
            contracts=1, total_premium=150.0, sigma_distance=2.0,
            p_itm=0.08, annualized_yield_pct=12.0, dte=30,
            current_price=155.0, bid=1.5, ask=1.7,
        )

        engine._fetch_options_chain = Mock(return_value=self._mock_chain())
        engine._fetch_current_price = Mock(return_value=155.0)
        engine._estimate_volatility = Mock(return_value=0.30)
        engine._get_candidates = Mock(return_value=[rec1, rec2])

        results = engine.scan_opportunities(
            "AAPL", [StrikeProfile.CONSERVATIVE], max_dte=45,
        )

        # Should be sorted by bias_score descending
        if len(results) > 1:
            assert results[0].bias_score >= results[1].bias_score
