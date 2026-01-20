"""
Unit tests for ladder_builder module.

Tests cover:
- Weekly expiration detection
- Position allocation strategies
- Sigma adjustment by week
- Complete ladder building
- Edge cases and error handling
"""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.ladder_builder import (
    ALLOCATION_WEIGHTS,
    AllocationStrategy,
    LadderBuilder,
    LadderConfig,
    LadderLeg,
    LadderResult,
    WeeklyExpirationDay,
)
from src.models import OptionContract, OptionsChain
from src.strike_optimizer import ProbabilityResult, StrikeOptimizer, StrikeResult

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_finnhub_client():
    """Create a mock Finnhub client."""
    client = Mock()
    client.get_earnings_calendar = Mock(return_value=[])
    return client


@pytest.fixture
def mock_strike_optimizer():
    """Create a mock strike optimizer."""
    optimizer = Mock(spec=StrikeOptimizer)

    # Mock calculate_strike_at_sigma
    optimizer.calculate_strike_at_sigma = Mock(
        return_value=StrikeResult(
            theoretical_strike=190.0,
            tradeable_strike=190.0,
            sigma=1.5,
            current_price=185.0,
            volatility=0.25,
            days_to_expiry=7,
            option_type="call",
            assignment_probability=0.12,
        )
    )

    # Mock calculate_assignment_probability
    optimizer.calculate_assignment_probability = Mock(
        return_value=ProbabilityResult(
            probability=0.12,
            d1=0.5,
            d2=0.4,
            delta=0.12,
            strike=190.0,
            current_price=185.0,
            volatility=0.25,
            time_to_expiry=7 / 365,
            risk_free_rate=0.05,
            option_type="call",
        )
    )

    return optimizer


@pytest.fixture
def default_config():
    """Create default ladder configuration."""
    return LadderConfig()


@pytest.fixture
def sample_options_chain():
    """Create a sample options chain with multiple expirations."""
    today = date.today()

    # Create contracts for 4 weekly expirations (Fridays)
    contracts = []
    for week in range(1, 5):
        # Find next Friday
        exp_date = today + timedelta(days=(4 - today.weekday() + 7 * week) % 7 + 7 * (week - 1))
        if exp_date <= today:
            exp_date += timedelta(days=7)
        exp_str = exp_date.isoformat()

        # Add call contracts at various strikes
        for strike in [180, 185, 190, 195, 200]:
            bid = max(0.05, (200 - strike) * 0.1 - week * 0.02)
            ask = bid + 0.05
            contracts.append(
                OptionContract(
                    symbol="AAPL",
                    strike=float(strike),
                    expiration_date=exp_str,
                    option_type="Call",
                    bid=round(bid, 2),
                    ask=round(ask, 2),
                    last=round((bid + ask) / 2, 2),
                    volume=100 + week * 50,
                    open_interest=500 + week * 100,
                    implied_volatility=0.25,
                )
            )

    return OptionsChain(symbol="AAPL", contracts=contracts, retrieved_at=datetime.now().isoformat())


@pytest.fixture
def ladder_builder(mock_finnhub_client, mock_strike_optimizer, default_config):
    """Create a ladder builder with mocks."""
    return LadderBuilder(
        finnhub_client=mock_finnhub_client,
        strike_optimizer=mock_strike_optimizer,
        config=default_config,
    )


# =============================================================================
# LadderConfig Tests
# =============================================================================


class TestLadderConfig:
    """Tests for LadderConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = LadderConfig()
        assert config.allocation_strategy == AllocationStrategy.EQUAL
        assert config.weeks_to_ladder == 4
        assert config.base_sigma == 1.5
        assert config.sigma_adjustment_per_week == 0.25
        assert config.min_contracts_per_leg == 1
        assert config.skip_earnings_weeks is True
        assert config.overwrite_cap_pct == 100.0

    def test_custom_config(self):
        """Test custom configuration."""
        config = LadderConfig(
            allocation_strategy=AllocationStrategy.FRONT_WEIGHTED,
            weeks_to_ladder=3,
            base_sigma=1.0,
            sigma_adjustment_per_week=0.5,
            min_contracts_per_leg=2,
        )
        assert config.allocation_strategy == AllocationStrategy.FRONT_WEIGHTED
        assert config.weeks_to_ladder == 3
        assert config.base_sigma == 1.0
        assert config.sigma_adjustment_per_week == 0.5
        assert config.min_contracts_per_leg == 2

    def test_invalid_weeks_to_ladder(self):
        """Test validation of weeks_to_ladder."""
        with pytest.raises(ValueError, match="weeks_to_ladder must be >= 1"):
            LadderConfig(weeks_to_ladder=0)

    def test_invalid_base_sigma(self):
        """Test validation of base_sigma."""
        with pytest.raises(ValueError, match="base_sigma must be > 0"):
            LadderConfig(base_sigma=0)

        with pytest.raises(ValueError, match="base_sigma must be > 0"):
            LadderConfig(base_sigma=-1)

    def test_invalid_sigma_adjustment(self):
        """Test validation of sigma_adjustment_per_week."""
        with pytest.raises(ValueError, match="sigma_adjustment_per_week must be >= 0"):
            LadderConfig(sigma_adjustment_per_week=-0.1)

    def test_invalid_overwrite_cap(self):
        """Test validation of overwrite_cap_pct."""
        with pytest.raises(ValueError, match="overwrite_cap_pct must be between 0 and 100"):
            LadderConfig(overwrite_cap_pct=0)

        with pytest.raises(ValueError, match="overwrite_cap_pct must be between 0 and 100"):
            LadderConfig(overwrite_cap_pct=101)


# =============================================================================
# Weekly Expiration Detection Tests
# =============================================================================


class TestWeeklyExpirationDetection:
    """Tests for get_weekly_expirations method."""

    def test_finds_friday_expirations(self, ladder_builder, sample_options_chain):
        """Test that Friday expirations are found."""
        expirations = ladder_builder.get_weekly_expirations(sample_options_chain)
        assert len(expirations) > 0

        # Verify all are Fridays
        for exp_str in expirations:
            exp_date = date.fromisoformat(exp_str)
            assert exp_date.weekday() == WeeklyExpirationDay.FRIDAY.value

    def test_filters_past_expirations(self, ladder_builder):
        """Test that past expirations are filtered out."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        tomorrow_friday = today + timedelta(days=(4 - today.weekday()) % 7 + 7)

        contracts = [
            OptionContract(
                symbol="TEST",
                strike=100.0,
                expiration_date=yesterday.isoformat(),
                option_type="Call",
                bid=1.0,
                ask=1.1,
            ),
            OptionContract(
                symbol="TEST",
                strike=100.0,
                expiration_date=tomorrow_friday.isoformat(),
                option_type="Call",
                bid=1.0,
                ask=1.1,
            ),
        ]
        chain = OptionsChain(
            symbol="TEST", contracts=contracts, retrieved_at=datetime.now().isoformat()
        )

        expirations = ladder_builder.get_weekly_expirations(chain)

        # Should not include past expiration
        assert yesterday.isoformat() not in expirations

    def test_returns_requested_number_of_weeks(self, ladder_builder, sample_options_chain):
        """Test that correct number of weeks is returned."""
        expirations = ladder_builder.get_weekly_expirations(sample_options_chain, weeks=2)
        assert len(expirations) <= 2

    def test_empty_chain_returns_empty_list(self, ladder_builder):
        """Test empty options chain handling."""
        chain = OptionsChain(symbol="TEST", contracts=[], retrieved_at=datetime.now().isoformat())
        expirations = ladder_builder.get_weekly_expirations(chain)
        assert expirations == []

    def test_accepts_wednesday_expirations(self, ladder_builder):
        """Test that Wednesday expirations (index options) are accepted."""
        today = date.today()
        # Find next Wednesday
        next_wednesday = today + timedelta(days=(2 - today.weekday()) % 7)
        if next_wednesday <= today:
            next_wednesday += timedelta(days=7)

        contracts = [
            OptionContract(
                symbol="VIX",
                strike=20.0,
                expiration_date=next_wednesday.isoformat(),
                option_type="Call",
                bid=1.0,
                ask=1.1,
            )
        ]
        chain = OptionsChain(
            symbol="VIX", contracts=contracts, retrieved_at=datetime.now().isoformat()
        )

        expirations = ladder_builder.get_weekly_expirations(chain)
        assert len(expirations) == 1
        assert date.fromisoformat(expirations[0]).weekday() == WeeklyExpirationDay.WEDNESDAY.value


# =============================================================================
# Allocation Strategy Tests
# =============================================================================


class TestAllocationStrategies:
    """Tests for calculate_allocations method."""

    def test_equal_allocation(self, ladder_builder):
        """Test equal allocation across weeks."""
        allocations = ladder_builder.calculate_allocations(
            total_shares=400, num_weeks=4, strategy=AllocationStrategy.EQUAL
        )

        assert len(allocations) == 4
        assert all(a == 100 for a in allocations)
        assert sum(allocations) == 400

    def test_front_weighted_allocation(self, ladder_builder):
        """Test front-weighted allocation (more in near-term)."""
        allocations = ladder_builder.calculate_allocations(
            total_shares=1000, num_weeks=4, strategy=AllocationStrategy.FRONT_WEIGHTED
        )

        assert len(allocations) == 4
        # Front weeks should have more than back weeks
        assert allocations[0] >= allocations[3]
        assert sum(allocations) <= 1000

    def test_back_weighted_allocation(self, ladder_builder):
        """Test back-weighted allocation (more in far-term)."""
        allocations = ladder_builder.calculate_allocations(
            total_shares=1000, num_weeks=4, strategy=AllocationStrategy.BACK_WEIGHTED
        )

        assert len(allocations) == 4
        # Back weeks should have more than front weeks
        assert allocations[3] >= allocations[0]
        assert sum(allocations) <= 1000

    def test_allocation_rounds_to_contract_boundaries(self, ladder_builder):
        """Test that allocations are rounded to 100-share boundaries."""
        allocations = ladder_builder.calculate_allocations(
            total_shares=350, num_weeks=3, strategy=AllocationStrategy.EQUAL
        )

        # All allocations should be divisible by 100
        for alloc in allocations:
            assert alloc % 100 == 0

    def test_allocation_with_overwrite_cap(self, mock_finnhub_client, mock_strike_optimizer):
        """Test allocation respects overwrite cap."""
        config = LadderConfig(overwrite_cap_pct=50.0)
        builder = LadderBuilder(mock_finnhub_client, mock_strike_optimizer, config)

        allocations = builder.calculate_allocations(
            total_shares=400, num_weeks=4, strategy=AllocationStrategy.EQUAL
        )

        # With 50% cap, only 200 shares available
        assert sum(allocations) <= 200

    def test_allocation_insufficient_shares(self, ladder_builder):
        """Test allocation with insufficient shares."""
        allocations = ladder_builder.calculate_allocations(
            total_shares=50,  # Less than 100
            num_weeks=4,
            strategy=AllocationStrategy.EQUAL,
        )

        assert all(a == 0 for a in allocations)

    def test_allocation_zero_weeks(self, ladder_builder):
        """Test allocation with zero weeks."""
        allocations = ladder_builder.calculate_allocations(
            total_shares=400, num_weeks=0, strategy=AllocationStrategy.EQUAL
        )

        assert allocations == []

    def test_allocation_more_weeks_than_weights(self, ladder_builder):
        """Test allocation handles more weeks than predefined weights."""
        allocations = ladder_builder.calculate_allocations(
            total_shares=600,
            num_weeks=6,  # More than the 4 predefined weights
            strategy=AllocationStrategy.FRONT_WEIGHTED,
        )

        assert len(allocations) == 6
        assert sum(allocations) <= 600


# =============================================================================
# Sigma Adjustment Tests
# =============================================================================


class TestSigmaAdjustment:
    """Tests for adjust_sigma_for_week method."""

    def test_week1_more_aggressive(self, ladder_builder):
        """Test that week 1 uses lower sigma (more aggressive)."""
        base_sigma = 1.5
        sigma_week1 = ladder_builder.adjust_sigma_for_week(1, base_sigma)

        assert sigma_week1 < base_sigma
        assert sigma_week1 == base_sigma - ladder_builder.config.sigma_adjustment_per_week

    def test_week2_3_baseline(self, ladder_builder):
        """Test that weeks 2-3 use baseline sigma."""
        base_sigma = 1.5

        sigma_week2 = ladder_builder.adjust_sigma_for_week(2, base_sigma)
        sigma_week3 = ladder_builder.adjust_sigma_for_week(3, base_sigma)

        assert sigma_week2 == base_sigma
        assert sigma_week3 == base_sigma

    def test_week4_plus_more_conservative(self, ladder_builder):
        """Test that week 4+ uses higher sigma (more conservative)."""
        base_sigma = 1.5

        sigma_week4 = ladder_builder.adjust_sigma_for_week(4, base_sigma)
        sigma_week5 = ladder_builder.adjust_sigma_for_week(5, base_sigma)

        assert sigma_week4 > base_sigma
        assert sigma_week5 > base_sigma
        assert sigma_week4 == base_sigma + ladder_builder.config.sigma_adjustment_per_week

    def test_sigma_minimum_floor(self, ladder_builder):
        """Test that sigma has a minimum floor."""
        # With very low base sigma, week 1 adjustment shouldn't go below 0.5
        sigma = ladder_builder.adjust_sigma_for_week(1, base_sigma=0.6)
        assert sigma >= 0.5

    def test_sigma_uses_config_defaults(self, ladder_builder):
        """Test that sigma adjustment uses config defaults."""
        sigma = ladder_builder.adjust_sigma_for_week(1)
        expected = (
            ladder_builder.config.base_sigma - ladder_builder.config.sigma_adjustment_per_week
        )
        assert sigma == max(0.5, expected)


# =============================================================================
# Build Ladder Tests
# =============================================================================


class TestBuildLadder:
    """Tests for build_ladder method."""

    def test_basic_ladder_creation(self, ladder_builder, sample_options_chain):
        """Test basic ladder creation."""
        result = ladder_builder.build_ladder(
            symbol="AAPL",
            shares=400,
            current_price=185.0,
            volatility=0.25,
            options_chain=sample_options_chain,
            option_type="call",
        )

        assert isinstance(result, LadderResult)
        assert result.symbol == "AAPL"
        assert result.option_type == "call"
        assert result.total_shares == 400

    def test_ladder_has_legs(self, ladder_builder, sample_options_chain):
        """Test that ladder contains legs."""
        result = ladder_builder.build_ladder(
            symbol="AAPL",
            shares=400,
            current_price=185.0,
            volatility=0.25,
            options_chain=sample_options_chain,
        )

        assert len(result.legs) > 0

    def test_ladder_skips_earnings_weeks(
        self, mock_finnhub_client, mock_strike_optimizer, sample_options_chain
    ):
        """Test that ladder skips weeks with earnings."""
        # Set up earnings date that spans one of the expirations
        today = date.today()
        earnings_date = (today + timedelta(days=10)).isoformat()
        mock_finnhub_client.get_earnings_calendar = Mock(return_value=[earnings_date])

        config = LadderConfig(skip_earnings_weeks=True)
        builder = LadderBuilder(mock_finnhub_client, mock_strike_optimizer, config)

        result = builder.build_ladder(
            symbol="AAPL",
            shares=400,
            current_price=185.0,
            volatility=0.25,
            options_chain=sample_options_chain,
        )

        # Should have warning about skipped earnings week
        assert result.earnings_dates == [earnings_date]

    def test_ladder_with_override_earnings(
        self, mock_finnhub_client, mock_strike_optimizer, sample_options_chain
    ):
        """Test override_earnings_check parameter."""
        today = date.today()
        earnings_date = (today + timedelta(days=5)).isoformat()
        mock_finnhub_client.get_earnings_calendar = Mock(return_value=[earnings_date])

        config = LadderConfig(skip_earnings_weeks=True)
        builder = LadderBuilder(mock_finnhub_client, mock_strike_optimizer, config)

        result = builder.build_ladder(
            symbol="AAPL",
            shares=400,
            current_price=185.0,
            volatility=0.25,
            options_chain=sample_options_chain,
            override_earnings_check=True,
        )

        # Should not skip weeks since override is True
        assert len(result.legs) > 0

    def test_ladder_calculates_aggregate_metrics(self, ladder_builder, sample_options_chain):
        """Test that aggregate metrics are calculated."""
        result = ladder_builder.build_ladder(
            symbol="AAPL",
            shares=400,
            current_price=185.0,
            volatility=0.25,
            options_chain=sample_options_chain,
        )

        # Check aggregate metrics are present
        assert result.total_gross_premium >= 0
        assert result.total_net_premium >= 0
        assert 0 <= result.weighted_avg_delta <= 1
        assert result.weighted_avg_dte >= 0

    def test_ladder_empty_chain_returns_warning(self, ladder_builder):
        """Test that empty chain returns appropriate warning."""
        empty_chain = OptionsChain(
            symbol="AAPL", contracts=[], retrieved_at=datetime.now().isoformat()
        )

        result = ladder_builder.build_ladder(
            symbol="AAPL",
            shares=400,
            current_price=185.0,
            volatility=0.25,
            options_chain=empty_chain,
        )

        assert result.total_contracts == 0
        assert "No weekly expirations found" in result.warnings[0]

    def test_ladder_insufficient_shares(self, ladder_builder, sample_options_chain):
        """Test ladder with insufficient shares."""
        result = ladder_builder.build_ladder(
            symbol="AAPL",
            shares=50,  # Less than 100
            current_price=185.0,
            volatility=0.25,
            options_chain=sample_options_chain,
        )

        # All legs should be non-actionable
        for leg in result.legs:
            assert not leg.is_actionable

    def test_ladder_symbol_uppercase(self, ladder_builder, sample_options_chain):
        """Test that symbol is uppercased."""
        result = ladder_builder.build_ladder(
            symbol="aapl",  # lowercase
            shares=400,
            current_price=185.0,
            volatility=0.25,
            options_chain=sample_options_chain,
        )

        assert result.symbol == "AAPL"


# =============================================================================
# LadderLeg Tests
# =============================================================================


class TestLadderLeg:
    """Tests for LadderLeg dataclass."""

    def test_annualized_yield_calculation(self):
        """Test annualized yield property calculation."""
        leg = LadderLeg(
            week_number=1,
            expiration_date="2026-01-24",
            days_to_expiry=7,
            strike=190.0,
            sigma_used=1.5,
            contracts=1,
            shares_covered=100,
            gross_premium=50.0,  # $0.50 × 100
        )

        # Expected: (50 / (190 * 100)) * (365 / 7) * 100
        expected_yield = (50 / 19000) * (365 / 7) * 100
        assert abs(leg.annualized_yield_pct - expected_yield) < 0.01

    def test_annualized_yield_zero_shares(self):
        """Test annualized yield with zero shares."""
        leg = LadderLeg(
            week_number=1,
            expiration_date="2026-01-24",
            days_to_expiry=7,
            strike=190.0,
            sigma_used=1.5,
            contracts=0,
            shares_covered=0,
            gross_premium=0.0,
        )

        assert leg.annualized_yield_pct == 0.0

    def test_leg_to_dict(self):
        """Test LadderLeg serialization."""
        leg = LadderLeg(
            week_number=1,
            expiration_date="2026-01-24",
            days_to_expiry=7,
            strike=190.0,
            sigma_used=1.5,
            contracts=2,
            shares_covered=200,
            bid=0.50,
            ask=0.55,
            mid_price=0.525,
            gross_premium=100.0,
            delta=0.12,
            p_itm=0.12,
            warnings=["Test warning"],
        )

        d = leg.to_dict()
        assert d["week_number"] == 1
        assert d["strike"] == 190.0
        assert d["contracts"] == 2
        assert d["bid"] == 0.5
        assert d["warnings"] == ["Test warning"]


# =============================================================================
# LadderResult Tests
# =============================================================================


class TestLadderResult:
    """Tests for LadderResult dataclass."""

    def test_actionable_legs_property(self):
        """Test actionable_legs property."""
        legs = [
            LadderLeg(
                week_number=1,
                expiration_date="2026-01-24",
                days_to_expiry=7,
                strike=190.0,
                sigma_used=1.5,
                contracts=1,
                shares_covered=100,
                is_actionable=True,
            ),
            LadderLeg(
                week_number=2,
                expiration_date="2026-01-31",
                days_to_expiry=14,
                strike=195.0,
                sigma_used=1.5,
                contracts=0,
                shares_covered=0,
                is_actionable=False,
            ),
            LadderLeg(
                week_number=3,
                expiration_date="2026-02-07",
                days_to_expiry=21,
                strike=200.0,
                sigma_used=1.75,
                contracts=1,
                shares_covered=100,
                is_actionable=True,
            ),
        ]

        result = LadderResult(
            symbol="AAPL",
            option_type="call",
            current_price=185.0,
            volatility=0.25,
            total_shares=400,
            shares_to_ladder=200,
            total_contracts=2,
            legs=legs,
            total_gross_premium=100.0,
            total_net_premium=98.70,
            weighted_avg_delta=0.12,
            weighted_avg_dte=14.0,
            weighted_avg_yield_pct=5.0,
        )

        assert result.actionable_count == 2
        assert len(result.actionable_legs) == 2

    def test_result_to_dict(self):
        """Test LadderResult serialization."""
        result = LadderResult(
            symbol="AAPL",
            option_type="call",
            current_price=185.0,
            volatility=0.25,
            total_shares=400,
            shares_to_ladder=400,
            total_contracts=4,
            legs=[],
            total_gross_premium=200.0,
            total_net_premium=197.40,
            weighted_avg_delta=0.12,
            weighted_avg_dte=14.0,
            weighted_avg_yield_pct=5.0,
            warnings=["Test warning"],
        )

        d = result.to_dict()
        assert d["symbol"] == "AAPL"
        assert d["option_type"] == "call"
        assert d["total_shares"] == 400
        assert d["total_contracts"] == 4
        assert d["warnings"] == ["Test warning"]


# =============================================================================
# Format Summary Tests
# =============================================================================


class TestFormatSummary:
    """Tests for format_ladder_summary method."""

    def test_format_summary_output(self, ladder_builder, sample_options_chain):
        """Test that summary is formatted correctly."""
        result = ladder_builder.build_ladder(
            symbol="AAPL",
            shares=400,
            current_price=185.0,
            volatility=0.25,
            options_chain=sample_options_chain,
        )

        summary = ladder_builder.format_ladder_summary(result)

        assert "AAPL" in summary
        assert "CALLS" in summary
        assert "Current Price" in summary
        assert "Total Contracts" in summary
        assert "--- Legs ---" in summary
        assert "--- Summary ---" in summary


# =============================================================================
# Integration Tests
# =============================================================================


class TestLadderBuilderIntegration:
    """Integration tests for LadderBuilder."""

    def test_full_workflow(self, mock_finnhub_client, mock_strike_optimizer, sample_options_chain):
        """Test complete ladder building workflow."""
        config = LadderConfig(
            allocation_strategy=AllocationStrategy.FRONT_WEIGHTED, weeks_to_ladder=3, base_sigma=1.5
        )

        builder = LadderBuilder(mock_finnhub_client, mock_strike_optimizer, config)

        result = builder.build_ladder(
            symbol="AAPL",
            shares=300,
            current_price=185.0,
            volatility=0.25,
            options_chain=sample_options_chain,
            option_type="call",
        )

        # Verify structure
        assert result.symbol == "AAPL"
        assert result.total_shares == 300
        assert len(result.legs) <= 3

        # Verify config was used
        assert result.config_used == config

        # Verify summary can be generated
        summary = builder.format_ladder_summary(result)
        assert len(summary) > 0

    def test_put_ladder(self, ladder_builder, sample_options_chain):
        """Test building a put ladder (cash-secured puts)."""
        # Add put contracts to chain
        today = date.today()
        next_friday = today + timedelta(days=(4 - today.weekday()) % 7 + 7)
        exp_str = next_friday.isoformat()

        put_contracts = [
            OptionContract(
                symbol="AAPL",
                strike=float(strike),
                expiration_date=exp_str,
                option_type="Put",
                bid=round((strike - 170) * 0.1, 2) if strike > 170 else 0.10,
                ask=round((strike - 170) * 0.1 + 0.05, 2) if strike > 170 else 0.15,
                volume=100,
                open_interest=500,
            )
            for strike in [170, 175, 180, 185]
        ]

        chain = OptionsChain(
            symbol="AAPL", contracts=put_contracts, retrieved_at=datetime.now().isoformat()
        )

        result = ladder_builder.build_ladder(
            symbol="AAPL",
            shares=400,
            current_price=185.0,
            volatility=0.25,
            options_chain=chain,
            option_type="put",
        )

        assert result.option_type == "put"
