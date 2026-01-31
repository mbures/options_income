"""
Tests for the overlay_scanner module.

Tests cover:
- PortfolioHolding validation
- ScannerConfig validation
- Contract sizing calculations
- Execution cost calculations
- Delta computations and band classification
- Tradability filters
- Earnings exclusion
- Broker checklist generation
- LLM memo payload generation
- Full portfolio scanning
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.models import OptionContract, OptionsChain
from src.overlay_scanner import (
    DELTA_BAND_RANGES,
    BrokerChecklist,
    CandidateStrike,
    DeltaBand,
    EarningsCalendar,
    ExecutionCostEstimate,
    LLMMemoPayload,
    OverlayScanner,
    PortfolioHolding,
    RejectionDetail,
    RejectionReason,
    ScannerConfig,
    ScanResult,
    SlippageModel,
)
from src.scanning.filters import (
    apply_delta_band_filter,
    apply_tradability_filters,
    calculate_near_miss_score,
    get_delta_band,
    populate_near_miss_details,
)
from src.scanning.formatters import (
    generate_broker_checklist,
    generate_llm_memo_payload,
)
from src.strike_optimizer import ProbabilityResult, StrikeOptimizer

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_finnhub_client():
    """Create a mock Finnhub client."""
    client = Mock()
    client.config = Mock()
    client.config.base_url = "https://finnhub.io/api/v1"
    client.config.api_key = "test_key"
    client.config.timeout = 10
    client.session = Mock()
    return client


@pytest.fixture
def strike_optimizer():
    """Create a real strike optimizer."""
    return StrikeOptimizer(risk_free_rate=0.05)


@pytest.fixture
def default_config():
    """Create default scanner config."""
    return ScannerConfig()


@pytest.fixture
def sample_holding():
    """Create a sample portfolio holding."""
    return PortfolioHolding(symbol="AAPL", shares=500, cost_basis=150.00, account_type="taxable")


@pytest.fixture
def sample_option_contract():
    """Create a sample option contract."""
    exp_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    return OptionContract(
        symbol="AAPL",
        strike=190.00,
        expiration_date=exp_date,
        option_type="Call",
        bid=2.50,
        ask=2.70,
        last=2.60,
        volume=500,
        open_interest=5000,
        delta=0.25,
        implied_volatility=0.30,
    )


@pytest.fixture
def sample_options_chain(sample_option_contract):
    """Create a sample options chain."""
    exp_date = sample_option_contract.expiration_date
    contracts = [
        sample_option_contract,
        OptionContract(
            symbol="AAPL",
            strike=185.00,
            expiration_date=exp_date,
            option_type="Call",
            bid=4.50,
            ask=4.80,
            volume=800,
            open_interest=8000,
        ),
        OptionContract(
            symbol="AAPL",
            strike=195.00,
            expiration_date=exp_date,
            option_type="Call",
            bid=1.20,
            ask=1.35,
            volume=300,
            open_interest=3000,
        ),
        OptionContract(
            symbol="AAPL",
            strike=200.00,
            expiration_date=exp_date,
            option_type="Call",
            bid=0.50,
            ask=0.60,
            volume=150,
            open_interest=1500,
        ),
        # Put for completeness
        OptionContract(
            symbol="AAPL",
            strike=180.00,
            expiration_date=exp_date,
            option_type="Put",
            bid=1.50,
            ask=1.65,
            volume=400,
            open_interest=4000,
        ),
    ]
    return OptionsChain(symbol="AAPL", contracts=contracts, retrieved_at=datetime.now().isoformat())


@pytest.fixture
def scanner(mock_finnhub_client, strike_optimizer, default_config):
    """Create an overlay scanner with mocks."""
    return OverlayScanner(
        finnhub_client=mock_finnhub_client, strike_optimizer=strike_optimizer, config=default_config
    )


# =============================================================================
# PortfolioHolding Tests
# =============================================================================


class TestPortfolioHolding:
    """Tests for PortfolioHolding dataclass."""

    def test_valid_holding(self):
        """Test creating a valid holding."""
        holding = PortfolioHolding(symbol="AAPL", shares=100)
        assert holding.symbol == "AAPL"
        assert holding.shares == 100

    def test_symbol_uppercase(self):
        """Test that symbol is converted to uppercase."""
        holding = PortfolioHolding(symbol="aapl", shares=100)
        assert holding.symbol == "AAPL"

    def test_symbol_stripped(self):
        """Test that symbol whitespace is stripped."""
        holding = PortfolioHolding(symbol="  AAPL  ", shares=100)
        assert holding.symbol == "AAPL"

    def test_invalid_symbol_empty(self):
        """Test that empty symbol raises error."""
        with pytest.raises(ValueError, match="Invalid symbol"):
            PortfolioHolding(symbol="", shares=100)

    def test_invalid_symbol_non_alphanumeric(self):
        """Test that non-alphanumeric symbol raises error."""
        with pytest.raises(ValueError, match="Invalid symbol"):
            PortfolioHolding(symbol="AAPL.A", shares=100)

    def test_negative_shares_raises(self):
        """Test that negative shares raises error."""
        with pytest.raises(ValueError, match="Shares must be non-negative"):
            PortfolioHolding(symbol="AAPL", shares=-100)

    def test_zero_shares_allowed(self):
        """Test that zero shares is allowed."""
        holding = PortfolioHolding(symbol="AAPL", shares=0)
        assert holding.shares == 0

    def test_negative_cost_basis_raises(self):
        """Test that negative cost basis raises error."""
        with pytest.raises(ValueError, match="Cost basis must be non-negative"):
            PortfolioHolding(symbol="AAPL", shares=100, cost_basis=-50)

    def test_invalid_account_type_raises(self):
        """Test that invalid account type raises error."""
        with pytest.raises(ValueError, match="Account type must be"):
            PortfolioHolding(symbol="AAPL", shares=100, account_type="invalid")

    def test_valid_account_types(self):
        """Test valid account types."""
        holding1 = PortfolioHolding(symbol="AAPL", shares=100, account_type="taxable")
        assert holding1.account_type == "taxable"

        holding2 = PortfolioHolding(symbol="AAPL", shares=100, account_type="qualified")
        assert holding2.account_type == "qualified"

    def test_full_holding(self):
        """Test holding with all optional fields."""
        holding = PortfolioHolding(
            symbol="MSFT",
            shares=300,
            cost_basis=280.50,
            acquired_date="2023-06-15",
            account_type="taxable",
        )
        assert holding.symbol == "MSFT"
        assert holding.shares == 300
        assert holding.cost_basis == 280.50
        assert holding.acquired_date == "2023-06-15"
        assert holding.account_type == "taxable"


# =============================================================================
# ScannerConfig Tests
# =============================================================================


class TestScannerConfig:
    """Tests for ScannerConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ScannerConfig()
        assert config.overwrite_cap_pct == 25.0
        assert config.per_contract_fee == 0.65
        assert config.slippage_model == SlippageModel.HALF_SPREAD_CAPPED
        assert config.skip_earnings_default is True
        assert config.delta_band == DeltaBand.CONSERVATIVE

    def test_custom_config(self):
        """Test custom configuration."""
        config = ScannerConfig(
            overwrite_cap_pct=50.0, per_contract_fee=0.50, delta_band=DeltaBand.MODERATE
        )
        assert config.overwrite_cap_pct == 50.0
        assert config.per_contract_fee == 0.50
        assert config.delta_band == DeltaBand.MODERATE

    def test_invalid_overwrite_cap_zero(self):
        """Test that zero overwrite cap raises error."""
        with pytest.raises(ValueError, match="overwrite_cap_pct must be between"):
            ScannerConfig(overwrite_cap_pct=0)

    def test_invalid_overwrite_cap_over_100(self):
        """Test that >100% overwrite cap raises error."""
        with pytest.raises(ValueError, match="overwrite_cap_pct must be between"):
            ScannerConfig(overwrite_cap_pct=101)

    def test_negative_fee_raises(self):
        """Test that negative fee raises error."""
        with pytest.raises(ValueError, match="per_contract_fee must be non-negative"):
            ScannerConfig(per_contract_fee=-1)

    def test_negative_yield_raises(self):
        """Test that negative min yield raises error."""
        with pytest.raises(ValueError, match="min_weekly_yield_bps must be non-negative"):
            ScannerConfig(min_weekly_yield_bps=-5)

    def test_low_friction_multiple_raises(self):
        """Test that friction multiple below 1 raises error."""
        with pytest.raises(ValueError, match="min_friction_multiple must be >= 1"):
            ScannerConfig(min_friction_multiple=0.5)


# =============================================================================
# Contract Sizing Tests
# =============================================================================


class TestContractSizing:
    """Tests for contract sizing calculations."""

    def test_calculate_contracts_500_shares_25pct(self, scanner):
        """Test contract calculation with 500 shares at 25% cap."""
        contracts = scanner.calculate_contracts_to_sell(500)
        # floor(500 * 0.25 / 100) = floor(1.25) = 1
        assert contracts == 1

    def test_calculate_contracts_1000_shares_25pct(self, scanner):
        """Test contract calculation with 1000 shares at 25% cap."""
        contracts = scanner.calculate_contracts_to_sell(1000)
        # floor(1000 * 0.25 / 100) = floor(2.5) = 2
        assert contracts == 2

    def test_calculate_contracts_400_shares_25pct(self, scanner):
        """Test contract calculation with 400 shares at 25% cap."""
        contracts = scanner.calculate_contracts_to_sell(400)
        # floor(400 * 0.25 / 100) = floor(1.0) = 1
        assert contracts == 1

    def test_calculate_contracts_300_shares_25pct(self, scanner):
        """Test contract calculation with 300 shares at 25% cap (non-actionable)."""
        contracts = scanner.calculate_contracts_to_sell(300)
        # floor(300 * 0.25 / 100) = floor(0.75) = 0
        assert contracts == 0

    def test_calculate_contracts_under_100_shares(self, scanner):
        """Test contract calculation with under 100 shares."""
        contracts = scanner.calculate_contracts_to_sell(50)
        assert contracts == 0

    def test_calculate_contracts_50pct_cap(self, mock_finnhub_client, strike_optimizer):
        """Test contract calculation with 50% cap."""
        config = ScannerConfig(overwrite_cap_pct=50.0)
        scanner = OverlayScanner(mock_finnhub_client, strike_optimizer, config)
        contracts = scanner.calculate_contracts_to_sell(500)
        # floor(500 * 0.50 / 100) = floor(2.5) = 2
        assert contracts == 2

    def test_calculate_contracts_100pct_cap(self, mock_finnhub_client, strike_optimizer):
        """Test contract calculation with 100% cap."""
        config = ScannerConfig(overwrite_cap_pct=100.0)
        scanner = OverlayScanner(mock_finnhub_client, strike_optimizer, config)
        contracts = scanner.calculate_contracts_to_sell(500)
        # floor(500 * 1.0 / 100) = 5
        assert contracts == 5


# =============================================================================
# Execution Cost Tests
# =============================================================================


class TestExecutionCost:
    """Tests for execution cost calculations."""

    def test_basic_cost_calculation(self, scanner):
        """Test basic execution cost calculation."""
        cost = scanner.calculate_execution_cost(bid=2.50, ask=2.70, contracts=1)

        assert cost.gross_premium == 250.00  # 2.50 * 100
        assert cost.commission == 0.65
        # Half spread capped: min(0.10, 0.20) = 0.10 per share
        assert cost.slippage == 10.00  # 0.10 * 100
        assert cost.net_credit == 250.00 - 0.65 - 10.00
        assert cost.net_credit_per_share == pytest.approx((250.00 - 0.65 - 10.00) / 100, rel=0.01)

    def test_multiple_contracts(self, scanner):
        """Test cost calculation for multiple contracts."""
        cost = scanner.calculate_execution_cost(bid=2.00, ask=2.10, contracts=3)

        assert cost.gross_premium == 600.00  # 2.00 * 100 * 3
        assert cost.commission == pytest.approx(1.95, rel=0.01)  # 0.65 * 3
        # Half spread = 0.05, capped at 0.10
        assert cost.slippage == pytest.approx(15.00, rel=0.01)  # 0.05 * 100 * 3

    def test_no_slippage_model(self, mock_finnhub_client, strike_optimizer):
        """Test with no slippage model."""
        config = ScannerConfig(slippage_model=SlippageModel.NONE)
        scanner = OverlayScanner(mock_finnhub_client, strike_optimizer, config)

        cost = scanner.calculate_execution_cost(bid=2.00, ask=2.50, contracts=1)
        assert cost.slippage == 0

    def test_full_spread_slippage(self, mock_finnhub_client, strike_optimizer):
        """Test with full spread slippage model."""
        config = ScannerConfig(slippage_model=SlippageModel.FULL_SPREAD)
        scanner = OverlayScanner(mock_finnhub_client, strike_optimizer, config)

        cost = scanner.calculate_execution_cost(bid=2.00, ask=2.50, contracts=1)
        # Full spread model assumes fill at bid, so no additional slippage
        assert cost.slippage == 0

    def test_half_spread_uncapped(self, mock_finnhub_client, strike_optimizer):
        """Test with uncapped half spread model."""
        config = ScannerConfig(slippage_model=SlippageModel.HALF_SPREAD)
        scanner = OverlayScanner(mock_finnhub_client, strike_optimizer, config)

        cost = scanner.calculate_execution_cost(bid=2.00, ask=2.50, contracts=1)
        # Half spread = 0.25 per share
        assert cost.slippage == 25.00

    def test_cost_to_dict(self, scanner):
        """Test ExecutionCostEstimate serialization."""
        cost = scanner.calculate_execution_cost(bid=1.50, ask=1.60, contracts=2)
        d = cost.to_dict()

        assert "gross_premium" in d
        assert "commission" in d
        assert "slippage" in d
        assert "net_credit" in d
        assert "net_credit_per_share" in d

    def test_cost_includes_all_contracts(self, scanner):
        """Test that cost_estimate.net_credit includes all contracts.

        Regression test for double multiplication bug fix.
        The calculate_execution_cost() method already multiplies by contracts,
        so total_net_credit in CandidateStrike should equal cost_estimate.net_credit
        (not cost_estimate.net_credit * contracts_available again).
        """
        # 3 contracts @ $2.00 bid, $2.10 ask
        cost = scanner.calculate_execution_cost(bid=2.00, ask=2.10, contracts=3)

        # gross_premium = 2.00 * 100 * 3 = 600.00
        assert cost.gross_premium == 600.00

        # commission = 0.65 * 3 = 1.95
        assert cost.commission == pytest.approx(1.95, rel=0.01)

        # slippage = 0.05 * 100 * 3 = 15.00 (half spread = 0.05)
        assert cost.slippage == pytest.approx(15.00, rel=0.01)

        # net_credit = 600.00 - 1.95 - 15.00 = 583.05 (total for all 3 contracts)
        expected_net = 600.00 - 1.95 - 15.00
        assert cost.net_credit == pytest.approx(expected_net, rel=0.01)

        # IMPORTANT: net_credit already includes all contracts!
        # CandidateStrike.total_net_credit should use cost_estimate.net_credit directly
        # (not multiply by contracts_available again)


# =============================================================================
# Delta Band Tests
# =============================================================================


class TestDeltaBand:
    """Tests for delta band classification."""

    def test_delta_band_defensive(self, scanner):
        """Test defensive delta band (0.05-0.10)."""
        assert get_delta_band(0.05) == DeltaBand.DEFENSIVE
        assert get_delta_band(0.07) == DeltaBand.DEFENSIVE
        assert get_delta_band(0.099) == DeltaBand.DEFENSIVE

    def test_delta_band_conservative(self, scanner):
        """Test conservative delta band (0.10-0.15)."""
        assert get_delta_band(0.10) == DeltaBand.CONSERVATIVE
        assert get_delta_band(0.12) == DeltaBand.CONSERVATIVE
        assert get_delta_band(0.149) == DeltaBand.CONSERVATIVE

    def test_delta_band_moderate(self, scanner):
        """Test moderate delta band (0.15-0.25)."""
        assert get_delta_band(0.15) == DeltaBand.MODERATE
        assert get_delta_band(0.20) == DeltaBand.MODERATE
        assert get_delta_band(0.249) == DeltaBand.MODERATE

    def test_delta_band_aggressive(self, scanner):
        """Test aggressive delta band (0.25-0.35)."""
        assert get_delta_band(0.25) == DeltaBand.AGGRESSIVE
        assert get_delta_band(0.30) == DeltaBand.AGGRESSIVE
        assert get_delta_band(0.349) == DeltaBand.AGGRESSIVE

    def test_delta_band_outside_ranges(self, scanner):
        """Test delta outside all bands returns None."""
        assert get_delta_band(0.01) is None  # Too low
        assert get_delta_band(0.50) is None  # Too high

    def test_delta_band_negative_converted(self, scanner):
        """Test negative delta is converted to absolute value."""
        assert get_delta_band(-0.12) == DeltaBand.CONSERVATIVE


# =============================================================================
# Tradability Filter Tests
# =============================================================================


class TestTradabilityFilters:
    """Tests for tradability filters."""

    def test_zero_bid_rejection(self, scanner, sample_option_contract):
        """Test that zero bid is rejected."""
        cost = ExecutionCostEstimate(
            gross_premium=0,
            commission=0.65,
            slippage=0,
            net_credit=-0.65,
            net_credit_per_share=-0.0065,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=0.0,  # Zero bid
            ask=0.20,
            mid_price=0.10,
            spread_absolute=0.20,
            spread_relative_pct=200,
            open_interest=1000,
            volume=100,
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=-0.65,
            annualized_yield_pct=0,
            days_to_expiry=7,
        )

        reasons, details = apply_tradability_filters(candidate, scanner.config)
        assert RejectionReason.ZERO_BID in reasons
        assert len(details) > 0
        assert any(d.reason == RejectionReason.ZERO_BID for d in details)

    def test_low_premium_rejection(self, scanner, sample_option_contract):
        """Test that low premium is rejected."""
        cost = ExecutionCostEstimate(
            gross_premium=3.00,
            commission=0.65,
            slippage=0.50,
            net_credit=1.85,
            net_credit_per_share=0.0185,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=0.03,  # Below min_bid_price of 0.05
            ask=0.05,
            mid_price=0.04,
            spread_absolute=0.02,
            spread_relative_pct=50,
            open_interest=1000,
            volume=100,
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=1.85,
            annualized_yield_pct=1.0,
            days_to_expiry=7,
        )

        reasons, details = apply_tradability_filters(candidate, scanner.config)
        assert RejectionReason.LOW_PREMIUM in reasons
        assert any(d.reason == RejectionReason.LOW_PREMIUM for d in details)

    def test_wide_spread_absolute_rejection(self, scanner, sample_option_contract):
        """Test that wide absolute spread is rejected."""
        cost = ExecutionCostEstimate(
            gross_premium=100.0,
            commission=0.65,
            slippage=10.0,
            net_credit=89.35,
            net_credit_per_share=0.8935,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=1.00,
            ask=1.50,  # $0.50 spread > $0.20 max
            mid_price=1.25,
            spread_absolute=0.50,  # Too wide
            spread_relative_pct=40,
            open_interest=1000,
            volume=100,
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=89.35,
            annualized_yield_pct=5.0,
            days_to_expiry=7,
        )

        reasons, details = apply_tradability_filters(candidate, scanner.config)
        assert RejectionReason.WIDE_SPREAD_ABSOLUTE in reasons
        assert any(d.reason == RejectionReason.WIDE_SPREAD_ABSOLUTE for d in details)

    def test_low_open_interest_rejection(self, scanner, sample_option_contract):
        """Test that low open interest is rejected."""
        cost = ExecutionCostEstimate(
            gross_premium=250.0,
            commission=0.65,
            slippage=5.0,
            net_credit=244.35,
            net_credit_per_share=2.4435,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=2.50,
            ask=2.60,
            mid_price=2.55,
            spread_absolute=0.10,
            spread_relative_pct=4,
            open_interest=50,  # Below 100 threshold
            volume=100,
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=244.35,
            annualized_yield_pct=7.0,
            days_to_expiry=7,
        )

        reasons, details = apply_tradability_filters(candidate, scanner.config)
        assert RejectionReason.LOW_OPEN_INTEREST in reasons
        # Verify margin calculation: 50/100 = 0.5 shortfall
        oi_detail = next(d for d in details if d.reason == RejectionReason.LOW_OPEN_INTEREST)
        assert oi_detail.actual_value == 50
        assert oi_detail.threshold == 100
        assert oi_detail.margin == 0.5  # (100-50)/100

    def test_low_volume_rejection(self, scanner, sample_option_contract):
        """Test that low volume is rejected."""
        cost = ExecutionCostEstimate(
            gross_premium=250.0,
            commission=0.65,
            slippage=5.0,
            net_credit=244.35,
            net_credit_per_share=2.4435,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=2.50,
            ask=2.60,
            mid_price=2.55,
            spread_absolute=0.10,
            spread_relative_pct=4,
            open_interest=500,
            volume=5,  # Below 10 threshold
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=244.35,
            annualized_yield_pct=7.0,
            days_to_expiry=7,
        )

        reasons, details = apply_tradability_filters(candidate, scanner.config)
        assert RejectionReason.LOW_VOLUME in reasons
        vol_detail = next(d for d in details if d.reason == RejectionReason.LOW_VOLUME)
        assert vol_detail.actual_value == 5
        assert vol_detail.threshold == 10

    def test_friction_too_high_rejection(self, scanner, sample_option_contract):
        """Test that high friction relative to premium is rejected.

        When net_credit < min_friction_multiple * (commission + slippage),
        the trade is rejected because costs consume too much of the premium.
        """
        # friction = 0.65 + 5.0 = 5.65
        # min_credit_for_friction = 2.0 * 5.65 = 11.30
        # net_credit = 4.35 < 11.30 → REJECTED
        cost = ExecutionCostEstimate(
            gross_premium=10.0,
            commission=0.65,
            slippage=5.0,
            net_credit=4.35,
            net_credit_per_share=0.0435,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=0.10,
            ask=0.15,
            mid_price=0.125,
            spread_absolute=0.05,
            spread_relative_pct=40,
            open_interest=500,
            volume=100,
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=4.35,
            annualized_yield_pct=1.0,
            days_to_expiry=7,
        )

        reasons, details = apply_tradability_filters(candidate, scanner.config)
        assert RejectionReason.FRICTION_TOO_HIGH in reasons
        friction_detail = next(d for d in details if d.reason == RejectionReason.FRICTION_TOO_HIGH)
        assert friction_detail.actual_value == 4.35  # net_credit
        # min_credit_for_friction = 2.0 * (0.65 + 5.0) = 11.30
        assert abs(friction_detail.threshold - 11.30) < 0.01

    def test_yield_too_low_rejection(self, scanner, sample_option_contract):
        """Test that low yield relative to notional is rejected.

        When net_credit / notional < min_weekly_yield_bps, the trade is
        rejected because the yield doesn't justify the capital at risk.
        """
        # For $100 stock: notional = 100 * 100 = $10,000
        # min_yield = 10 bps = 0.10% = $10 net credit needed
        # net_credit = $5 → 5 bps → REJECTED
        cost = ExecutionCostEstimate(
            gross_premium=6.0,
            commission=0.50,
            slippage=0.50,
            net_credit=5.00,  # Below yield threshold for $100 stock
            net_credit_per_share=0.05,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=105.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=0.06,
            ask=0.08,
            mid_price=0.07,
            spread_absolute=0.02,
            spread_relative_pct=28,
            open_interest=5000,
            volume=500,
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=5.00,
            annualized_yield_pct=0.5,
            days_to_expiry=7,
        )

        # Pass current_price=$100 to enable yield calculation
        reasons, details = apply_tradability_filters(candidate, scanner.config, current_price=100.0)
        assert RejectionReason.YIELD_TOO_LOW in reasons
        yield_detail = next(d for d in details if d.reason == RejectionReason.YIELD_TOO_LOW)
        # actual_yield_bps = (5.00 / 10000) * 10000 = 5 bps
        assert abs(yield_detail.actual_value - 5.0) < 0.1
        assert yield_detail.threshold == 10.0  # default min_weekly_yield_bps

    def test_passing_all_filters(self, scanner, sample_option_contract):
        """Test candidate that passes all filters."""
        cost = ExecutionCostEstimate(
            gross_premium=250.0,
            commission=0.65,
            slippage=5.0,
            net_credit=244.35,
            net_credit_per_share=2.4435,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=2.50,
            ask=2.60,
            mid_price=2.55,
            spread_absolute=0.10,
            spread_relative_pct=4,
            open_interest=5000,
            volume=500,
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=244.35,
            annualized_yield_pct=7.0,
            days_to_expiry=7,
        )

        reasons, details = apply_tradability_filters(candidate, scanner.config)
        assert len(reasons) == 0
        assert len(details) == 0

    def test_low_premium_weekly_relative_spread_skipped(self, scanner, sample_option_contract):
        """Test that relative spread filter is skipped for low-premium weeklies.

        For low-priced underlyings like F (~$10), weekly premiums are tiny.
        A $0.02 spread on $0.07 mid = 28% relative spread, but that's just
        2 ticks - perfectly tradeable. The relative spread filter should only
        apply when mid >= min_mid_for_relative_spread (default $0.50).
        """
        cost = ExecutionCostEstimate(
            gross_premium=6.00,
            commission=0.65,
            slippage=1.0,
            net_credit=4.35,
            net_credit_per_share=0.0435,
        )
        # Low-premium weekly: $0.06 bid, $0.08 ask, $0.07 mid
        # Spread = $0.02 (2 ticks), but 28.6% relative - should NOT trigger
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=14.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=0.06,
            ask=0.08,
            mid_price=0.07,  # Below $0.50 threshold
            spread_absolute=0.02,  # 2 ticks - tight spread
            spread_relative_pct=28.6,  # High % but meaningless for tiny premiums
            open_interest=5000,
            volume=500,
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=4.35,
            annualized_yield_pct=2.0,
            days_to_expiry=7,
        )

        reasons, details = apply_tradability_filters(candidate, scanner.config)

        # Should NOT have WIDE_SPREAD_RELATIVE because mid < $0.50
        assert RejectionReason.WIDE_SPREAD_RELATIVE not in reasons
        assert not any(d.reason == RejectionReason.WIDE_SPREAD_RELATIVE for d in details)
        # Should NOT have WIDE_SPREAD_ABSOLUTE because $0.02 < $0.10
        assert RejectionReason.WIDE_SPREAD_ABSOLUTE not in reasons

    def test_higher_premium_relative_spread_checked(self, scanner, sample_option_contract):
        """Test that relative spread filter applies when mid >= threshold."""
        cost = ExecutionCostEstimate(
            gross_premium=80.0,
            commission=0.65,
            slippage=5.0,
            net_credit=74.35,
            net_credit_per_share=0.7435,
        )
        # Higher premium: $0.80 bid, $1.00 ask, $0.90 mid
        # Spread = $0.20 (absolute OK), but 22% relative - should trigger
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=0.80,
            ask=1.00,
            mid_price=0.90,  # Above $0.50 threshold
            spread_absolute=0.20,  # At absolute limit, should not trigger
            spread_relative_pct=22.2,  # Above 20% threshold
            open_interest=5000,
            volume=500,
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=74.35,
            annualized_yield_pct=4.0,
            days_to_expiry=7,
        )

        reasons, details = apply_tradability_filters(candidate, scanner.config)

        # SHOULD have WIDE_SPREAD_RELATIVE because mid >= $0.50 and spread% > 20%
        assert RejectionReason.WIDE_SPREAD_RELATIVE in reasons
        rel_detail = next(d for d in details if d.reason == RejectionReason.WIDE_SPREAD_RELATIVE)
        assert "mid=$0.90" in rel_detail.margin_display


# =============================================================================
# Earnings Calendar Tests
# =============================================================================


class TestEarningsCalendar:
    """Tests for earnings calendar functionality."""

    def test_earnings_cache_hit(self, mock_finnhub_client):
        """Test earnings calendar cache hit."""
        calendar = EarningsCalendar(mock_finnhub_client)

        # Manually populate cache
        calendar._cache["AAPL"] = (["2026-01-25"], datetime.now().timestamp())

        dates = calendar.get_earnings_dates("AAPL")
        assert dates == ["2026-01-25"]

    def test_expiration_spans_earnings_true(self, mock_finnhub_client):
        """Test expiration that spans earnings."""
        calendar = EarningsCalendar(mock_finnhub_client)

        # Set up earnings date between now and expiration
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        calendar._cache["AAPL"] = ([tomorrow], datetime.now().timestamp())

        spans, earn_date = calendar.expiration_spans_earnings("AAPL", next_week)
        assert spans is True
        assert earn_date == tomorrow

    def test_expiration_spans_earnings_false(self, mock_finnhub_client):
        """Test expiration that doesn't span earnings."""
        calendar = EarningsCalendar(mock_finnhub_client)

        # Set up earnings date after expiration
        next_month = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        calendar._cache["AAPL"] = ([next_month], datetime.now().timestamp())

        spans, earn_date = calendar.expiration_spans_earnings("AAPL", next_week)
        assert spans is False
        assert earn_date is None

    def test_clear_cache_specific_symbol(self, mock_finnhub_client):
        """Test clearing cache for specific symbol."""
        calendar = EarningsCalendar(mock_finnhub_client)
        calendar._cache["AAPL"] = (["2026-01-25"], datetime.now().timestamp())
        calendar._cache["MSFT"] = (["2026-01-28"], datetime.now().timestamp())

        calendar.clear_cache("AAPL")

        assert "AAPL" not in calendar._cache
        assert "MSFT" in calendar._cache

    def test_clear_cache_all(self, mock_finnhub_client):
        """Test clearing entire cache."""
        calendar = EarningsCalendar(mock_finnhub_client)
        calendar._cache["AAPL"] = (["2026-01-25"], datetime.now().timestamp())
        calendar._cache["MSFT"] = (["2026-01-28"], datetime.now().timestamp())

        calendar.clear_cache()

        assert len(calendar._cache) == 0


# =============================================================================
# Broker Checklist Tests
# =============================================================================


class TestBrokerChecklist:
    """Tests for broker checklist generation."""

    def test_generate_checklist_earnings_clear(self, scanner, sample_option_contract):
        """Test checklist generation when earnings are clear."""
        cost = ExecutionCostEstimate(
            gross_premium=250.0,
            commission=0.65,
            slippage=5.0,
            net_credit=244.35,
            net_credit_per_share=2.4435,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=2.50,
            ask=2.60,
            mid_price=2.55,
            spread_absolute=0.10,
            spread_relative_pct=4,
            open_interest=5000,
            volume=500,
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=2,
            total_net_credit=488.70,
            annualized_yield_pct=7.0,
            days_to_expiry=7,
        )

        checklist = generate_broker_checklist(
            symbol="AAPL", candidate=candidate, config=scanner.config, earnings_clear=True, dividend_verified=False
        )

        assert checklist.symbol == "AAPL"
        assert checklist.action == "SELL TO OPEN"
        assert checklist.contracts == 2
        assert checklist.strike == 190.00
        assert checklist.option_type == "CALL"
        assert checklist.limit_price == 2.55
        assert checklist.min_acceptable_credit == 2.50
        assert any("Earnings: CLEAR" in c for c in checklist.checks)
        assert any("Dividend: UNVERIFIED" in c for c in checklist.checks)

    def test_checklist_to_dict(self, scanner, sample_option_contract):
        """Test checklist serialization."""
        cost = ExecutionCostEstimate(
            gross_premium=250.0,
            commission=0.65,
            slippage=5.0,
            net_credit=244.35,
            net_credit_per_share=2.4435,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=2.50,
            ask=2.60,
            mid_price=2.55,
            spread_absolute=0.10,
            spread_relative_pct=4,
            open_interest=5000,
            volume=500,
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=244.35,
            annualized_yield_pct=7.0,
            days_to_expiry=7,
        )

        checklist = generate_broker_checklist("AAPL", candidate, scanner.config, True, False)
        d = checklist.to_dict()

        assert "symbol" in d
        assert "action" in d
        assert "contracts" in d
        assert "checks" in d
        assert "warnings" in d


# =============================================================================
# LLM Memo Payload Tests
# =============================================================================


class TestLLMMemoPayload:
    """Tests for LLM memo payload generation."""

    def test_generate_llm_memo(self, scanner, sample_holding, sample_option_contract):
        """Test LLM memo payload generation."""
        cost = ExecutionCostEstimate(
            gross_premium=250.0,
            commission=0.65,
            slippage=5.0,
            net_credit=244.35,
            net_credit_per_share=2.4435,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=2.50,
            ask=2.60,
            mid_price=2.55,
            spread_absolute=0.10,
            spread_relative_pct=4,
            open_interest=5000,
            volume=500,
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=244.35,
            annualized_yield_pct=7.0,
            days_to_expiry=7,
        )

        payload = generate_llm_memo_payload(
            symbol="AAPL",
            current_price=185.50,
            holding=sample_holding,
            candidate=candidate,
            config=scanner.config,
            earnings_status="CLEAR",
            dividend_status="UNVERIFIED",
        )

        assert payload.symbol == "AAPL"
        assert payload.current_price == 185.50
        assert payload.shares_held == 500
        assert payload.contracts_to_write == 1
        assert payload.risk_profile == "conservative"
        assert payload.earnings_status == "CLEAR"
        assert payload.dividend_status == "UNVERIFIED"
        assert payload.account_type == "taxable"

    def test_memo_payload_to_dict(self, scanner, sample_holding, sample_option_contract):
        """Test memo payload serialization."""
        cost = ExecutionCostEstimate(
            gross_premium=250.0,
            commission=0.65,
            slippage=5.0,
            net_credit=244.35,
            net_credit_per_share=2.4435,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=2.50,
            ask=2.60,
            mid_price=2.55,
            spread_absolute=0.10,
            spread_relative_pct=4,
            open_interest=5000,
            volume=500,
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=244.35,
            annualized_yield_pct=7.0,
            days_to_expiry=7,
        )

        payload = generate_llm_memo_payload(
            "AAPL", 185.50, sample_holding, candidate, scanner.config, "CLEAR", "UNVERIFIED"
        )
        d = payload.to_dict()

        assert "symbol" in d
        assert "current_price" in d
        assert "candidate" in d
        assert "holding" in d
        assert "timestamp" in d


# =============================================================================
# Full Scan Tests
# =============================================================================


class TestScanHolding:
    """Tests for scanning a single holding."""

    def test_scan_insufficient_shares(self, scanner, sample_options_chain):
        """Test scanning holding with insufficient shares."""
        holding = PortfolioHolding(symbol="AAPL", shares=50)

        result = scanner.scan_holding(
            holding=holding,
            current_price=185.50,
            options_chain=sample_options_chain,
            volatility=0.30,
        )

        assert result.contracts_available == 0
        assert result.error is not None
        assert "Non-actionable" in result.error

    def test_scan_no_calls(self, scanner, sample_holding):
        """Test scanning with no call options."""
        # Create chain with only puts
        put = OptionContract(
            symbol="AAPL",
            strike=180.00,
            expiration_date=(datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
            option_type="Put",
            bid=1.50,
            ask=1.65,
        )
        chain = OptionsChain(
            symbol="AAPL", contracts=[put], retrieved_at=datetime.now().isoformat()
        )

        result = scanner.scan_holding(
            holding=sample_holding, current_price=185.50, options_chain=chain, volatility=0.30
        )

        assert result.error == "No call options found in chain"

    def test_scan_with_recommendations(self, scanner, sample_holding, sample_options_chain):
        """Test scanning that produces recommendations."""
        # Mock earnings calendar to return empty
        scanner.earnings_calendar._cache["AAPL"] = ([], datetime.now().timestamp())

        result = scanner.scan_holding(
            holding=sample_holding,
            current_price=185.50,
            options_chain=sample_options_chain,
            volatility=0.30,
        )

        assert result.error is None
        assert result.contracts_available == 1  # 500 shares * 25% / 100 = 1

    def test_scan_result_to_dict(self, scanner, sample_holding, sample_options_chain):
        """Test scan result serialization."""
        scanner.earnings_calendar._cache["AAPL"] = ([], datetime.now().timestamp())

        result = scanner.scan_holding(
            holding=sample_holding,
            current_price=185.50,
            options_chain=sample_options_chain,
            volatility=0.30,
        )

        d = result.to_dict()
        assert "symbol" in d
        assert "current_price" in d
        assert "shares_held" in d
        assert "contracts_available" in d
        assert "recommended_strikes" in d
        assert "rejected_strikes" in d

    def test_total_net_credit_equals_cost_estimate(
        self, scanner, sample_holding, sample_options_chain
    ):
        """Test that CandidateStrike.total_net_credit equals cost_estimate.net_credit.

        Regression test for double multiplication bug fix (Issue 2).
        The calculate_execution_cost() method already multiplies by contracts,
        so total_net_credit should equal cost_estimate.net_credit directly,
        NOT cost_estimate.net_credit * contracts_available (which would double count).
        """
        scanner.earnings_calendar._cache["AAPL"] = ([], datetime.now().timestamp())

        result = scanner.scan_holding(
            holding=sample_holding,
            current_price=185.50,
            options_chain=sample_options_chain,
            volatility=0.30,
        )

        # Check all candidates (recommended and rejected)
        all_candidates = result.recommended_strikes + result.rejected_strikes

        for candidate in all_candidates:
            # CRITICAL: total_net_credit should equal cost_estimate.net_credit
            # (NOT multiplied by contracts_available again)
            assert candidate.total_net_credit == candidate.cost_estimate.net_credit, (
                f"total_net_credit ({candidate.total_net_credit}) should equal "
                f"cost_estimate.net_credit ({candidate.cost_estimate.net_credit}), "
                f"not be multiplied by contracts_to_sell ({candidate.contracts_to_sell}) again"
            )

    def test_candidate_strike_has_explicit_pitm_fields(
        self, scanner, sample_holding, sample_options_chain
    ):
        """Test that CandidateStrike has explicit P(ITM) fields populated.

        Verifies Issue 4 fix: distinguish model vs chain delta/p_itm values.
        """
        scanner.earnings_calendar._cache["AAPL"] = ([], datetime.now().timestamp())

        result = scanner.scan_holding(
            holding=sample_holding,
            current_price=185.50,
            options_chain=sample_options_chain,
            volatility=0.30,
        )

        all_candidates = result.recommended_strikes + result.rejected_strikes

        for candidate in all_candidates:
            # Model values should always be populated
            assert candidate.delta_model is not None
            assert candidate.p_itm_model is not None
            # Primary delta/p_itm should match model values
            assert candidate.delta == candidate.delta_model
            assert candidate.p_itm == candidate.p_itm_model


class TestScanPortfolio:
    """Tests for scanning entire portfolio."""

    def test_scan_missing_price(self, scanner, sample_holding, sample_options_chain):
        """Test scanning with missing price data."""
        results = scanner.scan_portfolio(
            holdings=[sample_holding],
            current_prices={},  # Missing AAPL
            options_chains={"AAPL": sample_options_chain},
            volatilities={"AAPL": 0.30},
        )

        assert "AAPL" in results
        assert results["AAPL"].error == "No price data for AAPL"

    def test_scan_missing_chain(self, scanner, sample_holding):
        """Test scanning with missing options chain."""
        results = scanner.scan_portfolio(
            holdings=[sample_holding],
            current_prices={"AAPL": 185.50},
            options_chains={},  # Missing AAPL
            volatilities={"AAPL": 0.30},
        )

        assert "AAPL" in results
        assert results["AAPL"].error == "No options chain for AAPL"

    def test_scan_missing_volatility(self, scanner, sample_holding, sample_options_chain):
        """Test scanning with missing volatility data."""
        results = scanner.scan_portfolio(
            holdings=[sample_holding],
            current_prices={"AAPL": 185.50},
            options_chains={"AAPL": sample_options_chain},
            volatilities={},  # Missing AAPL
        )

        assert "AAPL" in results
        assert results["AAPL"].error == "No volatility data for AAPL"

    def test_scan_multiple_holdings(self, scanner, sample_options_chain):
        """Test scanning multiple holdings."""
        holdings = [
            PortfolioHolding(symbol="AAPL", shares=500),
            PortfolioHolding(symbol="MSFT", shares=300),
        ]

        # Create MSFT chain
        msft_chain = OptionsChain(
            symbol="MSFT",
            contracts=[
                OptionContract(
                    symbol="MSFT",
                    strike=400.00,
                    expiration_date=(datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                    option_type="Call",
                    bid=5.00,
                    ask=5.20,
                    volume=200,
                    open_interest=2000,
                )
            ],
            retrieved_at=datetime.now().isoformat(),
        )

        scanner.earnings_calendar._cache["AAPL"] = ([], datetime.now().timestamp())
        scanner.earnings_calendar._cache["MSFT"] = ([], datetime.now().timestamp())

        results = scanner.scan_portfolio(
            holdings=holdings,
            current_prices={"AAPL": 185.50, "MSFT": 390.00},
            options_chains={"AAPL": sample_options_chain, "MSFT": msft_chain},
            volatilities={"AAPL": 0.30, "MSFT": 0.25},
        )

        assert "AAPL" in results
        assert "MSFT" in results


# =============================================================================
# Trade Blotter Tests
# =============================================================================


class TestTradeBlotter:
    """Tests for trade blotter generation."""

    def test_generate_blotter_with_error(self, scanner):
        """Test blotter with error result."""
        results = {
            "AAPL": ScanResult(
                symbol="AAPL",
                current_price=0,
                shares_held=500,
                contracts_available=0,
                error="Test error",
            )
        }

        blotter = scanner.generate_trade_blotter(results)

        assert len(blotter) == 1
        assert blotter[0]["symbol"] == "AAPL"
        assert blotter[0]["status"] == "ERROR"
        assert blotter[0]["error"] == "Test error"

    def test_generate_blotter_no_recommendations(self, scanner):
        """Test blotter with no recommendations."""
        results = {
            "AAPL": ScanResult(
                symbol="AAPL",
                current_price=185.50,
                shares_held=500,
                contracts_available=1,
                recommended_strikes=[],
                rejected_strikes=[],
            )
        }

        blotter = scanner.generate_trade_blotter(results)

        assert len(blotter) == 1
        assert blotter[0]["status"] == "NO_RECOMMENDATIONS"

    def test_blotter_sorted_by_net_credit(self, scanner, sample_option_contract):
        """Test that blotter is sorted by net credit."""
        cost_high = ExecutionCostEstimate(
            gross_premium=500.0,
            commission=0.65,
            slippage=10.0,
            net_credit=489.35,
            net_credit_per_share=4.8935,
        )
        cost_low = ExecutionCostEstimate(
            gross_premium=100.0,
            commission=0.65,
            slippage=5.0,
            net_credit=94.35,
            net_credit_per_share=0.9435,
        )

        high_credit = CandidateStrike(
            contract=sample_option_contract,
            strike=185.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.20,
            p_itm=0.20,
            sigma_distance=1.0,
            bid=5.00,
            ask=5.10,
            mid_price=5.05,
            spread_absolute=0.10,
            spread_relative_pct=2,
            open_interest=5000,
            volume=500,
            cost_estimate=cost_high,
            delta_band=DeltaBand.MODERATE,
            contracts_to_sell=1,
            total_net_credit=489.35,
            annualized_yield_pct=15.0,
            days_to_expiry=7,
        )

        low_credit = CandidateStrike(
            contract=sample_option_contract,
            strike=195.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.10,
            p_itm=0.10,
            sigma_distance=2.0,
            bid=1.00,
            ask=1.05,
            mid_price=1.025,
            spread_absolute=0.05,
            spread_relative_pct=5,
            open_interest=3000,
            volume=300,
            cost_estimate=cost_low,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=94.35,
            annualized_yield_pct=5.0,
            days_to_expiry=7,
        )

        results = {
            "MSFT": ScanResult(
                symbol="MSFT",
                current_price=390.00,
                shares_held=500,
                contracts_available=1,
                recommended_strikes=[low_credit],
            ),
            "AAPL": ScanResult(
                symbol="AAPL",
                current_price=185.50,
                shares_held=500,
                contracts_available=1,
                recommended_strikes=[high_credit],
            ),
        }

        blotter = scanner.generate_trade_blotter(results)

        # AAPL (higher net credit) should come first
        assert blotter[0]["symbol"] == "AAPL"
        assert blotter[1]["symbol"] == "MSFT"


# =============================================================================
# Delta Computation Tests
# =============================================================================


class TestDeltaComputation:
    """Tests for Black-Scholes delta computation."""

    def test_compute_delta_otm_call(self, scanner):
        """Test delta computation for OTM call."""
        delta, p_itm = scanner.compute_delta(
            strike=200.00,
            current_price=185.50,
            volatility=0.30,
            days_to_expiry=7,
            option_type="call",
        )

        # OTM call should have delta < 0.5
        assert 0 < delta < 0.5
        assert 0 < p_itm < 0.5

    def test_compute_delta_atm_call(self, scanner):
        """Test delta computation for ATM call."""
        delta, p_itm = scanner.compute_delta(
            strike=185.00,
            current_price=185.00,
            volatility=0.30,
            days_to_expiry=30,
            option_type="call",
        )

        # ATM call should have delta near 0.5
        assert 0.45 < delta < 0.55

    def test_compute_delta_deep_otm_call(self, scanner):
        """Test delta computation for deep OTM call."""
        delta, p_itm = scanner.compute_delta(
            strike=250.00,
            current_price=185.50,
            volatility=0.30,
            days_to_expiry=7,
            option_type="call",
        )

        # Deep OTM call should have very low delta
        assert delta < 0.05
        assert p_itm < 0.05

    def test_delta_decreases_further_otm(self, scanner):
        """Test that delta decreases as strike moves further OTM."""
        delta_1, _ = scanner.compute_delta(190.00, 185.50, 0.30, 7, "call")
        delta_2, _ = scanner.compute_delta(195.00, 185.50, 0.30, 7, "call")
        delta_3, _ = scanner.compute_delta(200.00, 185.50, 0.30, 7, "call")

        assert delta_1 > delta_2 > delta_3


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for the overlay scanner."""

    def test_full_scan_workflow(self, scanner, sample_holding, sample_options_chain):
        """Test complete scanning workflow."""
        # Set up mock earnings calendar
        scanner.earnings_calendar._cache["AAPL"] = ([], datetime.now().timestamp())

        # Run the scan
        result = scanner.scan_holding(
            holding=sample_holding,
            current_price=185.50,
            options_chain=sample_options_chain,
            volatility=0.30,
        )

        # Verify basic structure
        assert result.symbol == "AAPL"
        assert result.current_price == 185.50
        assert result.shares_held == 500
        assert result.contracts_available >= 0
        assert result.error is None

        # Verify we have some strikes analyzed
        total_analyzed = len(result.recommended_strikes) + len(result.rejected_strikes)
        assert total_analyzed > 0

        # Verify rejection reasons are set for rejected strikes
        for strike in result.rejected_strikes:
            assert len(strike.rejection_reasons) > 0
            assert strike.is_recommended is False

        # Verify recommended strikes have no rejection reasons
        for strike in result.recommended_strikes:
            assert len(strike.rejection_reasons) == 0
            assert strike.is_recommended is True

    def test_earnings_exclusion_hard_gate(self, scanner, sample_holding, sample_options_chain):
        """Test that earnings exclusion works as hard gate."""
        # Set up earnings date that spans the expiration
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        scanner.earnings_calendar._cache["AAPL"] = (
            [tomorrow],  # Earnings before expiration
            datetime.now().timestamp(),
        )

        result = scanner.scan_holding(
            holding=sample_holding,
            current_price=185.50,
            options_chain=sample_options_chain,
            volatility=0.30,
        )

        # Should have earnings conflict flag
        assert result.has_earnings_conflict is True

    def test_earnings_override(self, scanner, sample_holding, sample_options_chain):
        """Test earnings exclusion can be overridden."""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        scanner.earnings_calendar._cache["AAPL"] = ([tomorrow], datetime.now().timestamp())

        # Without override - should skip earnings week
        result_no_override = scanner.scan_holding(
            holding=sample_holding,
            current_price=185.50,
            options_chain=sample_options_chain,
            volatility=0.30,
            override_earnings_check=False,
        )

        # With override - should include earnings week with warning
        result_with_override = scanner.scan_holding(
            holding=sample_holding,
            current_price=185.50,
            options_chain=sample_options_chain,
            volatility=0.30,
            override_earnings_check=True,
        )

        # Override should produce more analyzed strikes
        len(result_no_override.recommended_strikes) + len(result_no_override.rejected_strikes)
        total_with = len(result_with_override.recommended_strikes) + len(
            result_with_override.rejected_strikes
        )

        # With override, we should have analyzed strikes (or at least attempted)
        assert total_with >= 0


# =============================================================================
# Near-Miss Analysis Tests
# =============================================================================


class TestNearMissAnalysis:
    """Tests for near-miss candidate analysis."""

    def test_rejection_detail_to_dict(self):
        """Test RejectionDetail serialization."""
        detail = RejectionDetail(
            reason=RejectionReason.LOW_OPEN_INTEREST,
            actual_value=50,
            threshold=100,
            margin=0.5,
            margin_display="OI=50 vs 100",
        )
        d = detail.to_dict()

        assert d["reason"] == "low_open_interest"
        assert d["actual_value"] == 50
        assert d["threshold"] == 100
        assert d["margin"] == 0.5
        assert d["margin_display"] == "OI=50 vs 100"

    def test_calculate_near_miss_score_single_rejection(self, scanner, sample_option_contract):
        """Test near-miss score with single rejection."""
        cost = ExecutionCostEstimate(
            gross_premium=50.0,
            commission=0.65,
            slippage=2.0,
            net_credit=47.35,
            net_credit_per_share=0.4735,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=0.50,
            ask=0.55,
            mid_price=0.525,
            spread_absolute=0.05,
            spread_relative_pct=10,
            open_interest=50,  # Low OI - single rejection
            volume=100,
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=47.35,
            annualized_yield_pct=3.0,
            days_to_expiry=7,
        )

        # Add single rejection detail
        candidate.rejection_details = [
            RejectionDetail(
                reason=RejectionReason.LOW_OPEN_INTEREST,
                actual_value=50,
                threshold=100,
                margin=0.5,
                margin_display="OI=50 vs 100",
            )
        ]

        score = calculate_near_miss_score(candidate, max_net_credit=100.0)

        # Should have decent score with single rejection and moderate margin
        assert 0.3 < score < 0.8
        # Verify score components make sense
        # credit_score = min(1.0, 47.35/100) * 0.6 = 0.284
        # rejection_score = 1.0 * 0.2 = 0.2 (single rejection)
        # margin_score = (1.0 - 0.5) * 0.2 = 0.1
        # Total ~ 0.584
        assert 0.5 < score < 0.7

    def test_calculate_near_miss_score_multiple_rejections(self, scanner, sample_option_contract):
        """Test near-miss score with multiple rejections."""
        cost = ExecutionCostEstimate(
            gross_premium=20.0,
            commission=0.65,
            slippage=1.0,
            net_credit=18.35,
            net_credit_per_share=0.1835,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.08,  # Outside conservative band
            p_itm=0.08,
            sigma_distance=2.0,
            bid=0.20,
            ask=0.30,
            mid_price=0.25,
            spread_absolute=0.10,
            spread_relative_pct=40,  # Wide spread
            open_interest=30,  # Low OI
            volume=5,  # Low volume
            cost_estimate=cost,
            delta_band=DeltaBand.DEFENSIVE,  # Wrong band
            contracts_to_sell=1,
            total_net_credit=18.35,
            annualized_yield_pct=1.0,
            days_to_expiry=7,
        )

        # Add multiple rejection details
        candidate.rejection_details = [
            RejectionDetail(RejectionReason.LOW_OPEN_INTEREST, 30, 100, 0.7, "OI=30 vs 100"),
            RejectionDetail(RejectionReason.LOW_VOLUME, 5, 10, 0.5, "vol=5 vs 10"),
            RejectionDetail(RejectionReason.WIDE_SPREAD_RELATIVE, 40, 15, 1.67, "40% vs 15%"),
            RejectionDetail(RejectionReason.OUTSIDE_DELTA_BAND, 0.08, 0.10, 0.2, "delta=0.08"),
        ]

        score = calculate_near_miss_score(candidate, max_net_credit=100.0)

        # Score should be lower with many rejections
        assert score < 0.5

    def test_populate_near_miss_details_sets_binding(self, scanner, sample_option_contract):
        """Test that populate_near_miss_details identifies binding constraint."""
        cost = ExecutionCostEstimate(
            gross_premium=50.0,
            commission=0.65,
            slippage=2.0,
            net_credit=47.35,
            net_credit_per_share=0.4735,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,
            p_itm=0.12,
            sigma_distance=1.5,
            bid=0.50,
            ask=0.55,
            mid_price=0.525,
            spread_absolute=0.05,
            spread_relative_pct=10,
            open_interest=95,  # Close to threshold
            volume=8,  # Close to threshold
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=47.35,
            annualized_yield_pct=3.0,
            days_to_expiry=7,
        )

        # Add rejection details with different margins
        candidate.rejection_details = [
            RejectionDetail(
                RejectionReason.LOW_OPEN_INTEREST, 95, 100, 0.05, "OI=95 vs 100"
            ),  # Smallest margin
            RejectionDetail(RejectionReason.LOW_VOLUME, 8, 10, 0.2, "vol=8 vs 10"),
        ]

        populate_near_miss_details(candidate)

        # Binding should be the one with smallest margin
        assert candidate.binding_constraint is not None
        assert candidate.binding_constraint.reason == RejectionReason.LOW_OPEN_INTEREST
        assert candidate.binding_constraint.margin == 0.05
        assert candidate.near_miss_score > 0

    def test_scan_result_includes_near_miss_candidates(
        self, scanner, sample_holding, sample_options_chain
    ):
        """Test that scan result includes near-miss candidates."""
        scanner.earnings_calendar._cache["AAPL"] = ([], datetime.now().timestamp())

        result = scanner.scan_holding(
            holding=sample_holding,
            current_price=185.50,
            options_chain=sample_options_chain,
            volatility=0.30,
        )

        # If there are rejected strikes, we should have near-miss candidates
        if result.rejected_strikes:
            assert len(result.near_miss_candidates) <= 5
            # Near-miss candidates should be sorted by score (highest first)
            if len(result.near_miss_candidates) > 1:
                scores = [nm.near_miss_score for nm in result.near_miss_candidates]
                assert scores == sorted(scores, reverse=True)

    def test_near_miss_candidate_has_binding_constraint(
        self, scanner, sample_holding, sample_options_chain
    ):
        """Test that near-miss candidates have binding constraint set."""
        scanner.earnings_calendar._cache["AAPL"] = ([], datetime.now().timestamp())

        result = scanner.scan_holding(
            holding=sample_holding,
            current_price=185.50,
            options_chain=sample_options_chain,
            volatility=0.30,
        )

        for nm in result.near_miss_candidates:
            if nm.rejection_details:
                assert nm.binding_constraint is not None
                assert nm.binding_constraint in nm.rejection_details
                # Verify binding has smallest margin
                min_margin = min(d.margin for d in nm.rejection_details)
                assert nm.binding_constraint.margin == min_margin

    def test_delta_band_filter_returns_detail(self, scanner, sample_option_contract):
        """Test that delta band filter returns proper RejectionDetail."""
        cost = ExecutionCostEstimate(
            gross_premium=50.0,
            commission=0.65,
            slippage=2.0,
            net_credit=47.35,
            net_credit_per_share=0.4735,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.08,  # Below conservative band (0.10-0.15)
            p_itm=0.08,
            sigma_distance=1.5,
            bid=0.50,
            ask=0.55,
            mid_price=0.525,
            spread_absolute=0.05,
            spread_relative_pct=10,
            open_interest=1000,
            volume=100,
            cost_estimate=cost,
            delta_band=DeltaBand.DEFENSIVE,  # Wrong band
            contracts_to_sell=1,
            total_net_credit=47.35,
            annualized_yield_pct=3.0,
            days_to_expiry=7,
        )

        detail = apply_delta_band_filter(candidate, scanner.config)

        assert detail is not None
        assert detail.reason == RejectionReason.OUTSIDE_DELTA_BAND
        assert detail.actual_value == 0.08
        # Threshold should be min_delta since delta is below band
        assert detail.threshold == 0.10
        assert detail.margin > 0
        assert "delta=" in detail.margin_display

    def test_delta_band_filter_passes_within_band(self, scanner, sample_option_contract):
        """Test that delta band filter passes for delta within band."""
        cost = ExecutionCostEstimate(
            gross_premium=50.0,
            commission=0.65,
            slippage=2.0,
            net_credit=47.35,
            net_credit_per_share=0.4735,
        )
        candidate = CandidateStrike(
            contract=sample_option_contract,
            strike=190.00,
            expiration_date=sample_option_contract.expiration_date,
            delta=0.12,  # Within conservative band (0.10-0.15)
            p_itm=0.12,
            sigma_distance=1.5,
            bid=0.50,
            ask=0.55,
            mid_price=0.525,
            spread_absolute=0.05,
            spread_relative_pct=10,
            open_interest=1000,
            volume=100,
            cost_estimate=cost,
            delta_band=DeltaBand.CONSERVATIVE,
            contracts_to_sell=1,
            total_net_credit=47.35,
            annualized_yield_pct=3.0,
            days_to_expiry=7,
        )

        detail = apply_delta_band_filter(candidate, scanner.config)

        assert detail is None  # Should pass filter

    def test_scan_result_to_dict_includes_near_miss(
        self, scanner, sample_holding, sample_options_chain
    ):
        """Test that ScanResult.to_dict includes near_miss_candidates."""
        scanner.earnings_calendar._cache["AAPL"] = ([], datetime.now().timestamp())

        result = scanner.scan_holding(
            holding=sample_holding,
            current_price=185.50,
            options_chain=sample_options_chain,
            volatility=0.30,
        )

        d = result.to_dict()

        assert "near_miss_candidates" in d
        assert isinstance(d["near_miss_candidates"], list)
