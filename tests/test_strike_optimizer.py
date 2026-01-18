"""Tests for the strike optimizer module."""

import math
import pytest
from unittest.mock import MagicMock

from src.strike_optimizer import (
    StrikeOptimizer,
    StrikeProfile,
    StrikeResult,
    ProbabilityResult,
    StrikeRecommendation,
    PROFILE_SIGMA_RANGES,
)
from src.models import OptionsChain, OptionContract


class TestStrikeOptimizer:
    """Tests for StrikeOptimizer class."""

    @pytest.fixture
    def optimizer(self):
        """Create a StrikeOptimizer instance."""
        return StrikeOptimizer(risk_free_rate=0.05)

    def test_optimizer_initialization(self, optimizer):
        """Test optimizer initializes with correct risk-free rate."""
        assert optimizer.risk_free_rate == 0.05

    def test_optimizer_default_risk_free_rate(self):
        """Test optimizer uses default risk-free rate when not specified."""
        opt = StrikeOptimizer()
        assert opt.risk_free_rate == 0.05


class TestCalculateStrikeAtSigma:
    """Tests for calculate_strike_at_sigma method."""

    @pytest.fixture
    def optimizer(self):
        return StrikeOptimizer()

    def test_calculate_call_strike_positive_sigma(self, optimizer):
        """Test call strike at 1 sigma above current price."""
        result = optimizer.calculate_strike_at_sigma(
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            sigma=1.0,
            option_type="call",
            round_strike=False
        )

        # K = S × exp(n × σ × √T)
        # K = 100 × exp(1.0 × 0.30 × √(30/365))
        T = 30 / 365
        expected = 100.0 * math.exp(1.0 * 0.30 * math.sqrt(T))

        assert result.theoretical_strike == pytest.approx(expected, rel=1e-6)
        assert result.option_type == "call"
        assert result.sigma == 1.0
        assert result.current_price == 100.0
        assert result.volatility == 0.30
        assert result.days_to_expiry == 30

    def test_calculate_put_strike_negative_sigma(self, optimizer):
        """Test put strike at 1 sigma below current price."""
        result = optimizer.calculate_strike_at_sigma(
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            sigma=1.0,
            option_type="put",
            round_strike=False
        )

        # For puts, we use negative sigma
        T = 30 / 365
        expected = 100.0 * math.exp(-1.0 * 0.30 * math.sqrt(T))

        assert result.theoretical_strike == pytest.approx(expected, rel=1e-6)
        assert result.option_type == "put"
        # Theoretical strike should be below current price
        assert result.theoretical_strike < 100.0

    def test_calculate_strike_with_rounding(self, optimizer):
        """Test strike rounding to tradeable increments."""
        result = optimizer.calculate_strike_at_sigma(
            current_price=10.50,
            volatility=0.35,
            days_to_expiry=30,
            sigma=1.5,
            option_type="call",
            round_strike=True
        )

        # Tradeable strike should be rounded to nearest $0.50
        assert result.tradeable_strike % 0.50 == 0
        # For calls, round UP (conservative)
        assert result.tradeable_strike >= result.theoretical_strike

    def test_calculate_strike_includes_assignment_probability(self, optimizer):
        """Test that result includes assignment probability."""
        result = optimizer.calculate_strike_at_sigma(
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            sigma=1.5,
            option_type="call"
        )

        assert result.assignment_probability is not None
        assert 0 <= result.assignment_probability <= 1
        # 1.5 sigma OTM should have low probability
        assert result.assignment_probability < 0.30

    def test_calculate_strike_invalid_price(self, optimizer):
        """Test error on invalid current price."""
        with pytest.raises(ValueError, match="positive"):
            optimizer.calculate_strike_at_sigma(
                current_price=-10.0,
                volatility=0.30,
                days_to_expiry=30,
                sigma=1.0,
                option_type="call"
            )

    def test_calculate_strike_invalid_volatility(self, optimizer):
        """Test error on invalid volatility."""
        with pytest.raises(ValueError, match="positive"):
            optimizer.calculate_strike_at_sigma(
                current_price=100.0,
                volatility=0,
                days_to_expiry=30,
                sigma=1.0,
                option_type="call"
            )

    def test_calculate_strike_invalid_days(self, optimizer):
        """Test error on invalid days to expiry."""
        with pytest.raises(ValueError, match="positive"):
            optimizer.calculate_strike_at_sigma(
                current_price=100.0,
                volatility=0.30,
                days_to_expiry=0,
                sigma=1.0,
                option_type="call"
            )

    def test_calculate_strike_invalid_option_type(self, optimizer):
        """Test error on invalid option type."""
        with pytest.raises(ValueError, match="'call' or 'put'"):
            optimizer.calculate_strike_at_sigma(
                current_price=100.0,
                volatility=0.30,
                days_to_expiry=30,
                sigma=1.0,
                option_type="invalid"
            )

    def test_strike_result_to_dict(self, optimizer):
        """Test StrikeResult serialization."""
        result = optimizer.calculate_strike_at_sigma(
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            sigma=1.0,
            option_type="call"
        )

        d = result.to_dict()

        assert "theoretical_strike" in d
        assert "tradeable_strike" in d
        assert "volatility_pct" in d
        assert d["volatility_pct"] == 30.0
        assert "assignment_probability_pct" in d


class TestRoundToTradeableStrike:
    """Tests for round_to_tradeable_strike method."""

    @pytest.fixture
    def optimizer(self):
        return StrikeOptimizer()

    def test_round_call_up(self, optimizer):
        """Test call strike rounds UP (conservative)."""
        result = optimizer.round_to_tradeable_strike(
            strike=10.23,
            current_price=10.0,
            option_type="call"
        )
        assert result == 10.50  # Rounds up to $0.50 increment

    def test_round_put_down(self, optimizer):
        """Test put strike rounds DOWN (conservative)."""
        result = optimizer.round_to_tradeable_strike(
            strike=9.77,
            current_price=10.0,
            option_type="put"
        )
        assert result == 9.50  # Rounds down to $0.50 increment

    def test_round_with_available_strikes_call(self, optimizer):
        """Test rounding with available strikes for calls."""
        available = [9.0, 9.5, 10.0, 10.5, 11.0, 11.5, 12.0]

        result = optimizer.round_to_tradeable_strike(
            strike=10.23,
            current_price=10.0,
            option_type="call",
            available_strikes=available
        )

        assert result == 10.5  # Smallest available >= 10.23

    def test_round_with_available_strikes_put(self, optimizer):
        """Test rounding with available strikes for puts."""
        available = [8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0]

        result = optimizer.round_to_tradeable_strike(
            strike=9.77,
            current_price=10.0,
            option_type="put",
            available_strikes=available
        )

        assert result == 9.5  # Largest available <= 9.77

    def test_strike_increment_by_price_level(self, optimizer):
        """Test correct increment is used based on price level."""
        # Low price: $0.50 increments
        result_low = optimizer.round_to_tradeable_strike(
            strike=5.23,
            current_price=5.0,
            option_type="call"
        )
        assert result_low == 5.50

        # Higher price: $1.00 increments
        result_high = optimizer.round_to_tradeable_strike(
            strike=50.23,
            current_price=50.0,
            option_type="call"
        )
        assert result_high == 51.0

    def test_get_strike_increment(self, optimizer):
        """Test _get_strike_increment for various price levels."""
        assert optimizer._get_strike_increment(3.0) == 0.50
        assert optimizer._get_strike_increment(15.0) == 0.50
        assert optimizer._get_strike_increment(75.0) == 1.00
        assert optimizer._get_strike_increment(300.0) == 2.50
        assert optimizer._get_strike_increment(600.0) == 5.00


class TestAssignmentProbability:
    """Tests for assignment probability calculation."""

    @pytest.fixture
    def optimizer(self):
        return StrikeOptimizer(risk_free_rate=0.05)

    def test_calculate_call_probability(self, optimizer):
        """Test call assignment probability calculation."""
        result = optimizer.calculate_assignment_probability(
            strike=110.0,
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            option_type="call"
        )

        assert isinstance(result, ProbabilityResult)
        assert 0 <= result.probability <= 1
        assert result.option_type == "call"
        # OTM call should have probability < 50%
        assert result.probability < 0.5

    def test_calculate_put_probability(self, optimizer):
        """Test put assignment probability calculation."""
        result = optimizer.calculate_assignment_probability(
            strike=90.0,
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            option_type="put"
        )

        assert isinstance(result, ProbabilityResult)
        assert 0 <= result.probability <= 1
        assert result.option_type == "put"
        # OTM put should have probability < 50%
        assert result.probability < 0.5

    def test_atm_call_probability_near_50(self, optimizer):
        """Test ATM call has probability near 50% (slightly less due to drift)."""
        result = optimizer.calculate_assignment_probability(
            strike=100.0,
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            option_type="call"
        )

        # ATM should be close to 50% (drift causes slight asymmetry)
        assert 0.40 <= result.probability <= 0.60

    def test_deep_itm_call_probability_high(self, optimizer):
        """Test deep ITM call has high assignment probability."""
        result = optimizer.calculate_assignment_probability(
            strike=80.0,  # 20% ITM
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            option_type="call"
        )

        # Deep ITM should have high probability
        assert result.probability > 0.90

    def test_deep_otm_call_probability_low(self, optimizer):
        """Test deep OTM call has low assignment probability."""
        result = optimizer.calculate_assignment_probability(
            strike=130.0,  # 30% OTM
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            option_type="call"
        )

        # Deep OTM should have low probability
        assert result.probability < 0.10

    def test_longer_expiry_higher_probability(self, optimizer):
        """Test longer time to expiry increases ITM probability for OTM options."""
        # Short term
        short = optimizer.calculate_assignment_probability(
            strike=110.0,
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=7,
            option_type="call"
        )

        # Long term
        long = optimizer.calculate_assignment_probability(
            strike=110.0,
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=90,
            option_type="call"
        )

        # More time = more chance to reach strike
        assert long.probability > short.probability

    def test_higher_volatility_higher_probability_otm(self, optimizer):
        """Test higher volatility increases ITM probability for OTM options."""
        # Low vol
        low_vol = optimizer.calculate_assignment_probability(
            strike=110.0,
            current_price=100.0,
            volatility=0.15,
            days_to_expiry=30,
            option_type="call"
        )

        # High vol
        high_vol = optimizer.calculate_assignment_probability(
            strike=110.0,
            current_price=100.0,
            volatility=0.50,
            days_to_expiry=30,
            option_type="call"
        )

        # More vol = more chance of large move
        assert high_vol.probability > low_vol.probability

    def test_delta_calculation(self, optimizer):
        """Test delta is calculated correctly."""
        result = optimizer.calculate_assignment_probability(
            strike=100.0,
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            option_type="call"
        )

        # ATM call delta should be around 0.5
        assert 0.45 <= result.delta <= 0.55

    def test_put_delta_negative(self, optimizer):
        """Test put delta is negative."""
        result = optimizer.calculate_assignment_probability(
            strike=100.0,
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            option_type="put"
        )

        # Put delta is negative
        assert result.delta < 0
        # ATM put delta should be around -0.5
        assert -0.55 <= result.delta <= -0.45

    def test_probability_result_to_dict(self, optimizer):
        """Test ProbabilityResult serialization."""
        result = optimizer.calculate_assignment_probability(
            strike=105.0,
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            option_type="call"
        )

        d = result.to_dict()

        assert "probability" in d
        assert "probability_pct" in d
        assert "d1" in d
        assert "d2" in d
        assert "delta" in d
        assert d["probability_pct"] == pytest.approx(d["probability"] * 100, rel=1e-4)

    def test_invalid_inputs_raise_errors(self, optimizer):
        """Test invalid inputs raise appropriate errors."""
        with pytest.raises(ValueError, match="positive"):
            optimizer.calculate_assignment_probability(
                strike=-100, current_price=100, volatility=0.3,
                days_to_expiry=30, option_type="call"
            )

        with pytest.raises(ValueError, match="positive"):
            optimizer.calculate_assignment_probability(
                strike=100, current_price=-100, volatility=0.3,
                days_to_expiry=30, option_type="call"
            )


class TestNormCdf:
    """Tests for the normal CDF helper function."""

    def test_norm_cdf_at_zero(self):
        """Test N(0) = 0.5."""
        assert StrikeOptimizer._norm_cdf(0) == pytest.approx(0.5, rel=1e-6)

    def test_norm_cdf_symmetry(self):
        """Test N(-x) = 1 - N(x)."""
        x = 1.5
        assert StrikeOptimizer._norm_cdf(-x) == pytest.approx(
            1 - StrikeOptimizer._norm_cdf(x), rel=1e-6
        )

    def test_norm_cdf_known_values(self):
        """Test against known statistical values."""
        # N(1.0) ≈ 0.8413
        assert StrikeOptimizer._norm_cdf(1.0) == pytest.approx(0.8413, rel=1e-3)
        # N(2.0) ≈ 0.9772
        assert StrikeOptimizer._norm_cdf(2.0) == pytest.approx(0.9772, rel=1e-3)
        # N(-1.0) ≈ 0.1587
        assert StrikeOptimizer._norm_cdf(-1.0) == pytest.approx(0.1587, rel=1e-3)


class TestSigmaCalculations:
    """Tests for sigma distance calculations."""

    @pytest.fixture
    def optimizer(self):
        return StrikeOptimizer()

    def test_get_sigma_for_strike_call(self, optimizer):
        """Test calculating sigma distance for a call strike."""
        # First calculate a strike at known sigma
        result = optimizer.calculate_strike_at_sigma(
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            sigma=1.5,
            option_type="call",
            round_strike=False
        )

        # Now reverse-calculate the sigma
        sigma = optimizer.get_sigma_for_strike(
            strike=result.theoretical_strike,
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            option_type="call"
        )

        assert sigma == pytest.approx(1.5, rel=1e-6)

    def test_get_sigma_for_strike_put(self, optimizer):
        """Test calculating sigma distance for a put strike."""
        result = optimizer.calculate_strike_at_sigma(
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            sigma=1.5,
            option_type="put",
            round_strike=False
        )

        sigma = optimizer.get_sigma_for_strike(
            strike=result.theoretical_strike,
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            option_type="put"
        )

        assert sigma == pytest.approx(1.5, rel=1e-6)


class TestStrikeProfiles:
    """Tests for strike profile functionality."""

    @pytest.fixture
    def optimizer(self):
        return StrikeOptimizer()

    def test_get_profile_for_sigma_aggressive(self, optimizer):
        """Test aggressive profile detection."""
        profile = optimizer.get_profile_for_sigma(0.75)
        assert profile == StrikeProfile.AGGRESSIVE

    def test_get_profile_for_sigma_moderate(self, optimizer):
        """Test moderate profile detection."""
        profile = optimizer.get_profile_for_sigma(1.25)
        assert profile == StrikeProfile.MODERATE

    def test_get_profile_for_sigma_conservative(self, optimizer):
        """Test conservative profile detection."""
        profile = optimizer.get_profile_for_sigma(1.75)
        assert profile == StrikeProfile.CONSERVATIVE

    def test_get_profile_for_sigma_defensive(self, optimizer):
        """Test defensive profile detection."""
        profile = optimizer.get_profile_for_sigma(2.25)
        assert profile == StrikeProfile.DEFENSIVE

    def test_get_profile_for_sigma_out_of_range(self, optimizer):
        """Test sigma outside all profile ranges."""
        profile = optimizer.get_profile_for_sigma(3.0)
        assert profile is None

    def test_calculate_strikes_for_profiles(self, optimizer):
        """Test calculating strikes for all profiles."""
        results = optimizer.calculate_strikes_for_profiles(
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            option_type="call"
        )

        # Results is now ProfileStrikesResult with .strikes dict
        assert len(results.strikes) == 4
        assert StrikeProfile.AGGRESSIVE in results
        assert StrikeProfile.MODERATE in results
        assert StrikeProfile.CONSERVATIVE in results
        assert StrikeProfile.DEFENSIVE in results

        # Verify strike ordering (more aggressive = closer to current price)
        assert results[StrikeProfile.AGGRESSIVE].tradeable_strike < results[StrikeProfile.MODERATE].tradeable_strike
        assert results[StrikeProfile.MODERATE].tradeable_strike < results[StrikeProfile.CONSERVATIVE].tradeable_strike
        assert results[StrikeProfile.CONSERVATIVE].tradeable_strike < results[StrikeProfile.DEFENSIVE].tradeable_strike

        # Verify warnings and metadata fields exist
        assert isinstance(results.warnings, list)
        assert isinstance(results.collapsed_profiles, list)
        assert isinstance(results.is_short_dte, bool)

    def test_calculate_strikes_short_dte_warning(self, optimizer):
        """Test that short DTE triggers warning."""
        results = optimizer.calculate_strikes_for_profiles(
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=7,  # Short DTE
            option_type="call"
        )

        assert results.is_short_dte is True
        assert any("Short DTE" in w for w in results.warnings)

    def test_calculate_strikes_collapse_warning(self, optimizer):
        """Test that strike collisions trigger warnings."""
        # Very short DTE and low volatility should cause strike collisions
        results = optimizer.calculate_strikes_for_profiles(
            current_price=15.00,
            volatility=0.25,
            days_to_expiry=4,
            option_type="put"
        )

        # With short DTE and low vol, multiple profiles likely collapse
        # At minimum, we should have the short DTE warning
        assert results.is_short_dte is True
        # Check if any collapse warnings exist (may or may not depending on exact params)
        if results.collapsed_profiles:
            assert any("collapse to same strike" in w for w in results.warnings)

    def test_profile_sigma_ranges_valid(self):
        """Test that profile sigma ranges are valid."""
        for profile, (min_sig, max_sig) in PROFILE_SIGMA_RANGES.items():
            assert min_sig >= 0
            assert max_sig > min_sig


class TestStrikeRecommendations:
    """Tests for strike recommendation generation."""

    @pytest.fixture
    def optimizer(self):
        return StrikeOptimizer()

    @pytest.fixture
    def mock_options_chain(self):
        """Create a mock options chain with test contracts."""
        contracts = [
            OptionContract(
                symbol="TEST",
                strike=95.0,
                expiration_date="2026-02-21",
                option_type="Put",
                bid=0.50,
                ask=0.55,
                volume=500,
                open_interest=2000,
                implied_volatility=0.32
            ),
            OptionContract(
                symbol="TEST",
                strike=97.5,
                expiration_date="2026-02-21",
                option_type="Put",
                bid=0.85,
                ask=0.90,
                volume=300,
                open_interest=1500,
                implied_volatility=0.30
            ),
            OptionContract(
                symbol="TEST",
                strike=100.0,
                expiration_date="2026-02-21",
                option_type="Call",
                bid=1.50,
                ask=1.55,
                volume=1000,
                open_interest=5000,
                implied_volatility=0.28
            ),
            OptionContract(
                symbol="TEST",
                strike=102.5,
                expiration_date="2026-02-21",
                option_type="Call",
                bid=0.75,
                ask=0.80,
                volume=800,
                open_interest=3000,
                implied_volatility=0.29
            ),
            OptionContract(
                symbol="TEST",
                strike=105.0,
                expiration_date="2026-02-21",
                option_type="Call",
                bid=0.35,
                ask=0.40,
                volume=600,
                open_interest=2500,
                implied_volatility=0.30
            ),
            OptionContract(
                symbol="TEST",
                strike=107.5,
                expiration_date="2026-02-21",
                option_type="Call",
                bid=0.15,
                ask=0.20,
                volume=200,
                open_interest=50,  # Low OI
                implied_volatility=0.31
            ),
        ]

        return OptionsChain(
            symbol="TEST",
            contracts=contracts,
            retrieved_at="2026-01-18T12:00:00"
        )

    def test_get_recommendations_calls(self, optimizer, mock_options_chain):
        """Test getting call recommendations."""
        recs = optimizer.get_strike_recommendations(
            options_chain=mock_options_chain,
            current_price=100.0,
            volatility=0.30,
            option_type="call"
        )

        assert len(recs) > 0
        assert all(r.option_type == "call" for r in recs)
        # All should be OTM (strike > current price)
        assert all(r.strike > 100.0 for r in recs)

    def test_get_recommendations_puts(self, optimizer, mock_options_chain):
        """Test getting put recommendations."""
        recs = optimizer.get_strike_recommendations(
            options_chain=mock_options_chain,
            current_price=100.0,
            volatility=0.30,
            option_type="put"
        )

        assert len(recs) > 0
        assert all(r.option_type == "put" for r in recs)
        # All should be OTM (strike < current price)
        assert all(r.strike < 100.0 for r in recs)

    def test_get_recommendations_with_profile(self, optimizer, mock_options_chain):
        """Test filtering recommendations by profile."""
        recs = optimizer.get_strike_recommendations(
            options_chain=mock_options_chain,
            current_price=100.0,
            volatility=0.30,
            option_type="call",
            profile=StrikeProfile.MODERATE
        )

        # All recommendations should be in moderate range
        for rec in recs:
            if rec.profile:
                assert rec.profile == StrikeProfile.MODERATE

    def test_get_recommendations_low_oi_warning(self, optimizer, mock_options_chain):
        """Test low open interest triggers warning."""
        recs = optimizer.get_strike_recommendations(
            options_chain=mock_options_chain,
            current_price=100.0,
            volatility=0.30,
            option_type="call",
            min_open_interest=100
        )

        # Find the 107.5 strike with low OI
        low_oi_rec = next((r for r in recs if r.strike == 107.5), None)
        if low_oi_rec:
            assert any("open interest" in w.lower() for w in low_oi_rec.warnings)

    def test_recommendation_includes_metrics(self, optimizer, mock_options_chain):
        """Test recommendations include all metrics."""
        recs = optimizer.get_strike_recommendations(
            options_chain=mock_options_chain,
            current_price=100.0,
            volatility=0.30,
            option_type="call"
        )

        assert len(recs) > 0
        rec = recs[0]

        assert rec.strike > 0
        assert rec.expiration_date
        assert rec.sigma_distance > 0
        assert 0 <= rec.assignment_probability <= 1
        assert rec.bid is not None
        assert rec.mid_price is not None

    def test_recommendation_to_dict(self, optimizer, mock_options_chain):
        """Test recommendation serialization."""
        recs = optimizer.get_strike_recommendations(
            options_chain=mock_options_chain,
            current_price=100.0,
            volatility=0.30,
            option_type="call"
        )

        assert len(recs) > 0
        d = recs[0].to_dict()

        assert "strike" in d
        assert "sigma_distance" in d
        assert "assignment_probability_pct" in d
        assert "bid" in d
        assert "profile" in d

    def test_get_recommendations_empty_chain(self, optimizer):
        """Test with empty options chain."""
        empty_chain = OptionsChain(
            symbol="TEST",
            contracts=[],
            retrieved_at="2026-01-18T12:00:00"
        )

        recs = optimizer.get_strike_recommendations(
            options_chain=empty_chain,
            current_price=100.0,
            volatility=0.30,
            option_type="call"
        )

        assert recs == []

    def test_get_recommendations_limit(self, optimizer, mock_options_chain):
        """Test recommendation limit."""
        recs = optimizer.get_strike_recommendations(
            options_chain=mock_options_chain,
            current_price=100.0,
            volatility=0.30,
            option_type="call",
            limit=2
        )

        assert len(recs) <= 2


class TestMathematicalAccuracy:
    """Tests to verify mathematical accuracy of calculations."""

    @pytest.fixture
    def optimizer(self):
        return StrikeOptimizer(risk_free_rate=0.05)

    def test_strike_at_sigma_mathematical_identity(self, optimizer):
        """Test that calculate and inverse are mathematical inverses."""
        current_price = 100.0
        volatility = 0.30
        days = 30

        for sigma in [0.5, 1.0, 1.5, 2.0, 2.5]:
            for opt_type in ["call", "put"]:
                result = optimizer.calculate_strike_at_sigma(
                    current_price=current_price,
                    volatility=volatility,
                    days_to_expiry=days,
                    sigma=sigma,
                    option_type=opt_type,
                    round_strike=False
                )

                # Reverse calculate
                calc_sigma = optimizer.get_sigma_for_strike(
                    strike=result.theoretical_strike,
                    current_price=current_price,
                    volatility=volatility,
                    days_to_expiry=days,
                    option_type=opt_type
                )

                assert calc_sigma == pytest.approx(sigma, rel=1e-6)

    def test_call_put_strike_symmetry(self, optimizer):
        """Test call and put strikes are symmetric around current price."""
        result_call = optimizer.calculate_strike_at_sigma(
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            sigma=1.0,
            option_type="call",
            round_strike=False
        )

        result_put = optimizer.calculate_strike_at_sigma(
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            sigma=1.0,
            option_type="put",
            round_strike=False
        )

        # Call strike * Put strike should equal S^2 for lognormal symmetry
        # K_call = S * exp(+σ√T), K_put = S * exp(-σ√T)
        # K_call * K_put = S^2
        assert result_call.theoretical_strike * result_put.theoretical_strike == pytest.approx(
            100.0 * 100.0, rel=1e-6
        )

    def test_black_scholes_put_call_parity(self, optimizer):
        """Test delta satisfies put-call parity: delta_call - delta_put = 1."""
        call_result = optimizer.calculate_assignment_probability(
            strike=100.0,
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            option_type="call"
        )

        put_result = optimizer.calculate_assignment_probability(
            strike=100.0,
            current_price=100.0,
            volatility=0.30,
            days_to_expiry=30,
            option_type="put"
        )

        # delta_call - delta_put = 1
        # N(d1) - (N(d1) - 1) = 1
        assert call_result.delta - put_result.delta == pytest.approx(1.0, rel=1e-6)
