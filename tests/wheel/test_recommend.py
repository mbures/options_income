"""Tests for wheel recommendation engine."""

import pytest

from src.models.profiles import StrikeProfile
from src.wheel.exceptions import InvalidStateError
from src.wheel.models import WheelPosition, WheelRecommendation
from src.wheel.recommend import PITM_WARNING_THRESHOLDS, RecommendEngine
from src.wheel.state import WheelState


class TestPITMThresholds:
    """Tests for P(ITM) warning thresholds."""

    def test_thresholds_exist_for_all_profiles(self) -> None:
        """All profiles should have thresholds defined."""
        for profile in StrikeProfile:
            assert profile in PITM_WARNING_THRESHOLDS

    def test_thresholds_ordered_correctly(self) -> None:
        """More aggressive profiles should have higher thresholds."""
        assert PITM_WARNING_THRESHOLDS[StrikeProfile.AGGRESSIVE] > \
               PITM_WARNING_THRESHOLDS[StrikeProfile.MODERATE]
        assert PITM_WARNING_THRESHOLDS[StrikeProfile.MODERATE] > \
               PITM_WARNING_THRESHOLDS[StrikeProfile.CONSERVATIVE]
        assert PITM_WARNING_THRESHOLDS[StrikeProfile.CONSERVATIVE] > \
               PITM_WARNING_THRESHOLDS[StrikeProfile.DEFENSIVE]


class TestRecommendEngine:
    """Tests for RecommendEngine."""

    def test_init_without_clients(self) -> None:
        """Engine can be initialized without API clients."""
        engine = RecommendEngine()
        assert engine.finnhub is None
        assert engine.price_fetcher is None

    def test_invalid_state_for_recommendation(self) -> None:
        """Cannot recommend when position has open trade."""
        engine = RecommendEngine()

        # Position with open put
        position = WheelPosition(
            symbol="AAPL",
            state=WheelState.CASH_PUT_OPEN,
            capital_allocated=10000.0,
        )

        with pytest.raises(InvalidStateError):
            engine.get_recommendation(position)

        # Position with open call
        position.state = WheelState.SHARES_CALL_OPEN
        with pytest.raises(InvalidStateError):
            engine.get_recommendation(position)


class TestBiasScoring:
    """Tests for collection bias scoring."""

    def test_bias_score_prefers_higher_sigma(self) -> None:
        """Higher sigma distance should score higher."""
        engine = RecommendEngine()

        # Create two recommendations with different sigma
        rec1 = WheelRecommendation(
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-21",
            premium_per_share=1.50,
            contracts=1,
            total_premium=150.0,
            sigma_distance=1.5,  # Lower
            p_itm=0.15,
            annualized_yield_pct=10.0,
            dte=30,
        )

        rec2 = WheelRecommendation(
            symbol="AAPL",
            direction="put",
            strike=140.0,
            expiration_date="2025-02-21",
            premium_per_share=1.00,
            contracts=1,
            total_premium=100.0,
            sigma_distance=2.0,  # Higher
            p_itm=0.08,
            annualized_yield_pct=8.0,
            dte=30,
        )

        biased = engine._apply_collection_bias([rec1, rec2])

        # Higher sigma should come first
        assert biased[0].sigma_distance > biased[1].sigma_distance

    def test_bias_score_prefers_lower_dte(self) -> None:
        """Shorter DTE should score higher (less time for adverse moves)."""
        engine = RecommendEngine()

        rec1 = WheelRecommendation(
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-21",
            premium_per_share=1.50,
            contracts=1,
            total_premium=150.0,
            sigma_distance=1.5,
            p_itm=0.15,
            annualized_yield_pct=10.0,
            dte=45,  # Longer
        )

        rec2 = WheelRecommendation(
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-14",
            premium_per_share=0.75,
            contracts=1,
            total_premium=75.0,
            sigma_distance=1.5,
            p_itm=0.12,
            annualized_yield_pct=12.0,
            dte=14,  # Shorter
        )

        biased = engine._apply_collection_bias([rec1, rec2])

        # Shorter DTE should come first (higher bias score)
        assert biased[0].dte < biased[1].dte

    def test_bias_score_prefers_lower_pitm(self) -> None:
        """Lower P(ITM) should score higher."""
        engine = RecommendEngine()

        rec1 = WheelRecommendation(
            symbol="AAPL",
            direction="put",
            strike=150.0,
            expiration_date="2025-02-21",
            premium_per_share=2.00,
            contracts=1,
            total_premium=200.0,
            sigma_distance=1.0,
            p_itm=0.30,  # Higher P(ITM)
            annualized_yield_pct=15.0,
            dte=30,
        )

        rec2 = WheelRecommendation(
            symbol="AAPL",
            direction="put",
            strike=140.0,
            expiration_date="2025-02-21",
            premium_per_share=1.00,
            contracts=1,
            total_premium=100.0,
            sigma_distance=2.0,
            p_itm=0.08,  # Lower P(ITM)
            annualized_yield_pct=8.0,
            dte=30,
        )

        biased = engine._apply_collection_bias([rec1, rec2])

        # Lower P(ITM) should come first
        assert biased[0].p_itm < biased[1].p_itm


class TestWarnings:
    """Tests for recommendation warnings."""

    def test_high_pitm_warning_added(self) -> None:
        """High P(ITM) should add warning."""
        engine = RecommendEngine()

        # Conservative profile with P(ITM) above threshold
        rec = WheelRecommendation(
            symbol="AAPL",
            direction="put",
            strike=150.0,
            expiration_date="2025-02-21",
            premium_per_share=2.00,
            contracts=1,
            total_premium=200.0,
            sigma_distance=1.6,  # Conservative range
            p_itm=0.25,  # Above 15% threshold
            annualized_yield_pct=15.0,
            dte=30,
        )

        engine._add_warnings([rec], "AAPL")

        assert any("P(ITM)" in w for w in rec.warnings)

    def test_low_yield_warning_added(self) -> None:
        """Low annualized yield should add warning."""
        engine = RecommendEngine()

        rec = WheelRecommendation(
            symbol="AAPL",
            direction="put",
            strike=140.0,
            expiration_date="2025-02-21",
            premium_per_share=0.20,
            contracts=1,
            total_premium=20.0,
            sigma_distance=2.0,
            p_itm=0.05,
            annualized_yield_pct=3.0,  # Below 5% threshold
            dte=30,
        )

        engine._add_warnings([rec], "AAPL")

        assert any("Low annualized yield" in w for w in rec.warnings)

    def test_short_dte_warning_added(self) -> None:
        """Short DTE (<=7) should add warning."""
        engine = RecommendEngine()

        rec = WheelRecommendation(
            symbol="AAPL",
            direction="put",
            strike=145.0,
            expiration_date="2025-02-07",
            premium_per_share=0.50,
            contracts=1,
            total_premium=50.0,
            sigma_distance=1.5,
            p_itm=0.10,
            annualized_yield_pct=20.0,
            dte=5,  # Very short
        )

        engine._add_warnings([rec], "AAPL")

        assert any("Short DTE" in w for w in rec.warnings)
