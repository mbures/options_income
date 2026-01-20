"""
Tests for covered options strategy analysis module.

Tests cover:
- CoveredCallAnalyzer: analyze(), get_recommendations()
- CoveredPutAnalyzer: analyze(), get_recommendations()
- WheelStrategy: get_recommendation(), calculate_cycle_metrics()
- Result dataclasses and their to_dict() methods
- Warning generation for liquidity, earnings, early assignment
"""

import pytest
from datetime import datetime, timedelta

from src.covered_strategies import (
    CoveredCallAnalyzer,
    CoveredPutAnalyzer,
    WheelStrategy,
    WheelState,
    CoveredCallResult,
    CoveredPutResult,
    WheelRecommendation,
    WheelCycleMetrics,
    MIN_BID_PRICE,
    MIN_OPEN_INTEREST,
    MAX_BID_ASK_SPREAD_PCT,
)
from src.strike_optimizer import StrikeOptimizer, StrikeProfile
from src.models import OptionContract, OptionsChain


class TestCoveredCallAnalyzer:
    """Tests for CoveredCallAnalyzer class."""

    @pytest.fixture
    def optimizer(self):
        return StrikeOptimizer()

    @pytest.fixture
    def analyzer(self, optimizer):
        return CoveredCallAnalyzer(optimizer)

    @pytest.fixture
    def sample_call_contract(self):
        """Create a sample OTM call contract."""
        # Expiration ~30 days from now
        exp_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        return OptionContract(
            symbol="TEST",
            strike=11.00,
            expiration_date=exp_date,
            option_type="Call",
            bid=0.25,
            ask=0.30,
            volume=500,
            open_interest=2000,
            implied_volatility=0.35,
        )

    def test_analyzer_initialization(self, analyzer, optimizer):
        """Test analyzer initializes with optimizer."""
        assert analyzer.optimizer is optimizer

    def test_analyze_basic_covered_call(self, analyzer, sample_call_contract):
        """Test basic covered call analysis."""
        result = analyzer.analyze(
            contract=sample_call_contract,
            current_price=10.50,
            volatility=0.30,
            shares=100,
        )

        assert isinstance(result, CoveredCallResult)
        assert result.contract is sample_call_contract
        assert result.current_price == 10.50
        assert result.shares == 100
        assert result.premium_per_share == 0.25
        assert result.total_premium == 25.00  # 0.25 * 100

    def test_analyze_profit_calculations(self, analyzer, sample_call_contract):
        """Test profit calculations are correct."""
        result = analyzer.analyze(
            contract=sample_call_contract,
            current_price=10.50,
            volatility=0.30,
            shares=100,
        )

        # Profit if flat = premium
        assert result.profit_if_flat == 25.00

        # Max profit = premium + (strike - current) * shares
        # = 25 + (11 - 10.50) * 100 = 25 + 50 = 75
        assert result.max_profit == 75.00

        # Breakeven = current - premium = 10.50 - 0.25 = 10.25
        assert result.breakeven == 10.25

    def test_analyze_with_cost_basis(self, analyzer, sample_call_contract):
        """Test analysis with different cost basis."""
        # Cost basis lower than current price
        result = analyzer.analyze(
            contract=sample_call_contract,
            current_price=10.50,
            volatility=0.30,
            shares=100,
            cost_basis=9.00,  # Bought at $9
        )

        # Max profit = premium + (strike - cost_basis) * shares
        # = 25 + (11 - 9) * 100 = 25 + 200 = 225
        assert result.max_profit == 225.00

    def test_analyze_assignment_probability(self, analyzer, sample_call_contract):
        """Test assignment probability is calculated."""
        result = analyzer.analyze(
            contract=sample_call_contract,
            current_price=10.50,
            volatility=0.30,
        )

        assert result.assignment_probability is not None
        assert 0 < result.assignment_probability < 1
        assert result.sigma_distance is not None
        assert result.sigma_distance > 0  # OTM call

    def test_analyze_annualized_returns(self, analyzer, sample_call_contract):
        """Test annualized return calculations."""
        result = analyzer.analyze(
            contract=sample_call_contract,
            current_price=10.50,
            volatility=0.30,
        )

        assert result.annualized_return_if_flat > 0
        assert result.annualized_return_if_called > 0
        # Called should be higher because it includes appreciation
        assert result.annualized_return_if_called >= result.annualized_return_if_flat

    def test_analyze_rejects_put_contract(self, analyzer):
        """Test that analyzer rejects put contracts."""
        exp_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        put_contract = OptionContract(
            symbol="TEST",
            strike=10.00,
            expiration_date=exp_date,
            option_type="Put",
            bid=0.20,
            ask=0.25,
        )

        with pytest.raises(ValueError, match="must be a call"):
            analyzer.analyze(
                contract=put_contract,
                current_price=10.50,
                volatility=0.30,
            )

    def test_analyze_rejects_itm_call(self, analyzer):
        """Test that analyzer rejects ITM calls."""
        exp_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        itm_call = OptionContract(
            symbol="TEST",
            strike=10.00,  # Strike below current price
            expiration_date=exp_date,
            option_type="Call",
            bid=0.60,
            ask=0.65,
        )

        with pytest.raises(ValueError, match="must be above current price"):
            analyzer.analyze(
                contract=itm_call,
                current_price=10.50,
                volatility=0.30,
            )

    def test_analyze_low_premium_warning(self, analyzer):
        """Test warning for low premium."""
        exp_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        low_premium_call = OptionContract(
            symbol="TEST",
            strike=15.00,
            expiration_date=exp_date,
            option_type="Call",
            bid=0.01,  # Very low premium
            ask=0.02,
        )

        result = analyzer.analyze(
            contract=low_premium_call,
            current_price=10.50,
            volatility=0.30,
        )

        assert any("Low premium" in w for w in result.warnings)

    def test_analyze_low_open_interest_warning(self, analyzer):
        """Test warning for low open interest."""
        exp_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        low_oi_call = OptionContract(
            symbol="TEST",
            strike=11.00,
            expiration_date=exp_date,
            option_type="Call",
            bid=0.25,
            ask=0.30,
            open_interest=50,  # Below threshold
        )

        result = analyzer.analyze(
            contract=low_oi_call,
            current_price=10.50,
            volatility=0.30,
        )

        assert any("Low open interest" in w for w in result.warnings)

    def test_analyze_wide_spread_warning(self, analyzer):
        """Test warning for wide bid-ask spread."""
        exp_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        wide_spread_call = OptionContract(
            symbol="TEST",
            strike=11.00,
            expiration_date=exp_date,
            option_type="Call",
            bid=0.10,
            ask=0.25,  # 85% spread!
        )

        result = analyzer.analyze(
            contract=wide_spread_call,
            current_price=10.50,
            volatility=0.30,
        )

        assert any("Wide bid-ask spread" in w for w in result.warnings)

    def test_analyze_earnings_warning(self, analyzer, sample_call_contract):
        """Test warning when expiration spans earnings."""
        # Earnings date within expiration period
        earnings_date = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")

        result = analyzer.analyze(
            contract=sample_call_contract,
            current_price=10.50,
            volatility=0.30,
            earnings_dates=[earnings_date],
        )

        assert any("earnings date" in w.lower() for w in result.warnings)

    def test_analyze_profile_assignment(self, analyzer, sample_call_contract):
        """Test that profile is assigned based on sigma distance."""
        result = analyzer.analyze(
            contract=sample_call_contract,
            current_price=10.50,
            volatility=0.30,
        )

        # Profile should be assigned if sigma is in valid range
        if result.sigma_distance and 0.5 <= result.sigma_distance <= 2.5:
            assert result.profile is not None

    def test_result_to_dict(self, analyzer, sample_call_contract):
        """Test CoveredCallResult serialization."""
        result = analyzer.analyze(
            contract=sample_call_contract,
            current_price=10.50,
            volatility=0.30,
        )

        result_dict = result.to_dict()

        assert "strike" in result_dict
        assert "premium_per_share" in result_dict
        assert "max_profit" in result_dict
        assert "annualized_return_if_flat_pct" in result_dict
        assert "warnings" in result_dict


class TestCoveredCallRecommendations:
    """Tests for covered call recommendations."""

    @pytest.fixture
    def optimizer(self):
        return StrikeOptimizer()

    @pytest.fixture
    def analyzer(self, optimizer):
        return CoveredCallAnalyzer(optimizer)

    @pytest.fixture
    def mock_options_chain(self):
        """Create a mock options chain with multiple call contracts."""
        exp_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        contracts = [
            # OTM calls at various strikes
            OptionContract(
                symbol="TEST",
                strike=11.00,
                expiration_date=exp_date,
                option_type="Call",
                bid=0.25,
                ask=0.30,
                open_interest=500,
            ),
            OptionContract(
                symbol="TEST",
                strike=11.50,
                expiration_date=exp_date,
                option_type="Call",
                bid=0.15,
                ask=0.18,
                open_interest=300,
            ),
            OptionContract(
                symbol="TEST",
                strike=12.00,
                expiration_date=exp_date,
                option_type="Call",
                bid=0.08,
                ask=0.10,
                open_interest=200,
            ),
            # ITM call (should be filtered out)
            OptionContract(
                symbol="TEST",
                strike=10.00,
                expiration_date=exp_date,
                option_type="Call",
                bid=0.60,
                ask=0.65,
                open_interest=1000,
            ),
            # Put (should be filtered out)
            OptionContract(
                symbol="TEST",
                strike=10.00,
                expiration_date=exp_date,
                option_type="Put",
                bid=0.20,
                ask=0.25,
                open_interest=500,
            ),
        ]
        return OptionsChain(
            symbol="TEST",
            contracts=contracts,
            retrieved_at=datetime.now().isoformat(),
        )

    def test_get_recommendations_returns_list(self, analyzer, mock_options_chain):
        """Test recommendations returns a list of results."""
        recs = analyzer.get_recommendations(
            options_chain=mock_options_chain,
            current_price=10.50,
            volatility=0.30,
        )

        assert isinstance(recs, list)
        assert len(recs) > 0
        assert all(isinstance(r, CoveredCallResult) for r in recs)

    def test_get_recommendations_filters_itm(self, analyzer, mock_options_chain):
        """Test that ITM calls are filtered out."""
        recs = analyzer.get_recommendations(
            options_chain=mock_options_chain,
            current_price=10.50,
            volatility=0.30,
        )

        # All recommended strikes should be above current price
        for rec in recs:
            assert rec.contract.strike > 10.50

    def test_get_recommendations_sorted_by_return(self, analyzer, mock_options_chain):
        """Test recommendations are sorted by annualized return."""
        recs = analyzer.get_recommendations(
            options_chain=mock_options_chain,
            current_price=10.50,
            volatility=0.30,
        )

        # Should be sorted descending by annualized return
        for i in range(len(recs) - 1):
            assert recs[i].annualized_return_if_flat >= recs[i + 1].annualized_return_if_flat

    def test_get_recommendations_respects_limit(self, analyzer, mock_options_chain):
        """Test limit parameter is respected."""
        recs = analyzer.get_recommendations(
            options_chain=mock_options_chain,
            current_price=10.50,
            volatility=0.30,
            limit=2,
        )

        assert len(recs) <= 2

    def test_get_recommendations_min_premium_filter(self, analyzer, mock_options_chain):
        """Test minimum premium filter."""
        recs = analyzer.get_recommendations(
            options_chain=mock_options_chain,
            current_price=10.50,
            volatility=0.30,
            min_premium=0.20,  # Higher threshold
        )

        # Only the $11 strike should pass (bid=0.25)
        for rec in recs:
            assert rec.premium_per_share >= 0.20


class TestCoveredPutAnalyzer:
    """Tests for CoveredPutAnalyzer class."""

    @pytest.fixture
    def optimizer(self):
        return StrikeOptimizer()

    @pytest.fixture
    def analyzer(self, optimizer):
        return CoveredPutAnalyzer(optimizer)

    @pytest.fixture
    def sample_put_contract(self):
        """Create a sample OTM put contract."""
        exp_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        return OptionContract(
            symbol="TEST",
            strike=10.00,
            expiration_date=exp_date,
            option_type="Put",
            bid=0.20,
            ask=0.25,
            volume=500,
            open_interest=2000,
            implied_volatility=0.35,
        )

    def test_analyzer_initialization(self, analyzer, optimizer):
        """Test analyzer initializes with optimizer."""
        assert analyzer.optimizer is optimizer

    def test_analyze_basic_covered_put(self, analyzer, sample_put_contract):
        """Test basic cash-secured put analysis."""
        result = analyzer.analyze(
            contract=sample_put_contract,
            current_price=10.50,
            volatility=0.30,
        )

        assert isinstance(result, CoveredPutResult)
        assert result.contract is sample_put_contract
        assert result.current_price == 10.50
        assert result.premium_per_share == 0.20
        assert result.total_premium == 20.00  # 0.20 * 100

    def test_analyze_collateral_calculation(self, analyzer, sample_put_contract):
        """Test collateral requirement calculation."""
        result = analyzer.analyze(
            contract=sample_put_contract,
            current_price=10.50,
            volatility=0.30,
        )

        # Collateral = strike * 100
        assert result.collateral_required == 1000.00

    def test_analyze_effective_purchase_price(self, analyzer, sample_put_contract):
        """Test effective purchase price calculation."""
        result = analyzer.analyze(
            contract=sample_put_contract,
            current_price=10.50,
            volatility=0.30,
        )

        # Effective price = strike - premium = 10.00 - 0.20 = 9.80
        assert result.effective_purchase_price == 9.80

    def test_analyze_discount_calculation(self, analyzer, sample_put_contract):
        """Test discount from current price calculation."""
        result = analyzer.analyze(
            contract=sample_put_contract,
            current_price=10.50,
            volatility=0.30,
        )

        # Discount = (current - effective) / current
        # = (10.50 - 9.80) / 10.50 = 0.0667 (6.67%)
        expected_discount = (10.50 - 9.80) / 10.50
        assert abs(result.discount_from_current - expected_discount) < 0.001

    def test_analyze_profit_calculations(self, analyzer, sample_put_contract):
        """Test profit calculations are correct."""
        result = analyzer.analyze(
            contract=sample_put_contract,
            current_price=10.50,
            volatility=0.30,
        )

        # Max profit = premium (if OTM)
        assert result.max_profit == 20.00

        # Profit if flat = premium (put expires worthless)
        assert result.profit_if_flat == 20.00

        # Breakeven = strike - premium = 10.00 - 0.20 = 9.80
        assert result.breakeven == 9.80

        # Max loss = collateral - premium (if stock goes to 0)
        assert result.max_loss == 980.00

    def test_analyze_assignment_probability(self, analyzer, sample_put_contract):
        """Test assignment probability is calculated."""
        result = analyzer.analyze(
            contract=sample_put_contract,
            current_price=10.50,
            volatility=0.30,
        )

        assert result.assignment_probability is not None
        assert 0 < result.assignment_probability < 1
        assert result.sigma_distance is not None
        assert result.sigma_distance > 0  # OTM put

    def test_analyze_rejects_call_contract(self, analyzer):
        """Test that analyzer rejects call contracts."""
        exp_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        call_contract = OptionContract(
            symbol="TEST",
            strike=11.00,
            expiration_date=exp_date,
            option_type="Call",
            bid=0.25,
            ask=0.30,
        )

        with pytest.raises(ValueError, match="must be a put"):
            analyzer.analyze(
                contract=call_contract,
                current_price=10.50,
                volatility=0.30,
            )

    def test_analyze_rejects_itm_put(self, analyzer):
        """Test that analyzer rejects ITM puts."""
        exp_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        itm_put = OptionContract(
            symbol="TEST",
            strike=11.00,  # Strike above current price
            expiration_date=exp_date,
            option_type="Put",
            bid=0.60,
            ask=0.65,
        )

        with pytest.raises(ValueError, match="must be below current price"):
            analyzer.analyze(
                contract=itm_put,
                current_price=10.50,
                volatility=0.30,
            )

    def test_analyze_earnings_warning(self, analyzer, sample_put_contract):
        """Test warning when expiration spans earnings."""
        earnings_date = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")

        result = analyzer.analyze(
            contract=sample_put_contract,
            current_price=10.50,
            volatility=0.30,
            earnings_dates=[earnings_date],
        )

        assert any("earnings date" in w.lower() for w in result.warnings)

    def test_result_to_dict(self, analyzer, sample_put_contract):
        """Test CoveredPutResult serialization."""
        result = analyzer.analyze(
            contract=sample_put_contract,
            current_price=10.50,
            volatility=0.30,
        )

        result_dict = result.to_dict()

        assert "strike" in result_dict
        assert "premium_per_share" in result_dict
        assert "collateral_required" in result_dict
        assert "effective_purchase_price" in result_dict
        assert "discount_from_current_pct" in result_dict
        assert "annualized_return_if_otm_pct" in result_dict


class TestCoveredPutRecommendations:
    """Tests for covered put recommendations."""

    @pytest.fixture
    def optimizer(self):
        return StrikeOptimizer()

    @pytest.fixture
    def analyzer(self, optimizer):
        return CoveredPutAnalyzer(optimizer)

    @pytest.fixture
    def mock_options_chain(self):
        """Create a mock options chain with multiple put contracts."""
        exp_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        contracts = [
            # OTM puts at various strikes
            OptionContract(
                symbol="TEST",
                strike=10.00,
                expiration_date=exp_date,
                option_type="Put",
                bid=0.20,
                ask=0.25,
                open_interest=500,
            ),
            OptionContract(
                symbol="TEST",
                strike=9.50,
                expiration_date=exp_date,
                option_type="Put",
                bid=0.12,
                ask=0.15,
                open_interest=300,
            ),
            OptionContract(
                symbol="TEST",
                strike=9.00,
                expiration_date=exp_date,
                option_type="Put",
                bid=0.06,
                ask=0.08,
                open_interest=200,
            ),
            # ITM put (should be filtered out)
            OptionContract(
                symbol="TEST",
                strike=11.00,
                expiration_date=exp_date,
                option_type="Put",
                bid=0.60,
                ask=0.65,
                open_interest=1000,
            ),
        ]
        return OptionsChain(
            symbol="TEST",
            contracts=contracts,
            retrieved_at=datetime.now().isoformat(),
        )

    def test_get_recommendations_returns_list(self, analyzer, mock_options_chain):
        """Test recommendations returns a list of results."""
        recs = analyzer.get_recommendations(
            options_chain=mock_options_chain,
            current_price=10.50,
            volatility=0.30,
        )

        assert isinstance(recs, list)
        assert len(recs) > 0
        assert all(isinstance(r, CoveredPutResult) for r in recs)

    def test_get_recommendations_filters_itm(self, analyzer, mock_options_chain):
        """Test that ITM puts are filtered out."""
        recs = analyzer.get_recommendations(
            options_chain=mock_options_chain,
            current_price=10.50,
            volatility=0.30,
        )

        # All recommended strikes should be below current price
        for rec in recs:
            assert rec.contract.strike < 10.50

    def test_get_recommendations_target_price_filter(self, analyzer, mock_options_chain):
        """Test target purchase price filter."""
        recs = analyzer.get_recommendations(
            options_chain=mock_options_chain,
            current_price=10.50,
            volatility=0.30,
            target_purchase_price=9.50,  # Only want to buy at $9.50 or less
        )

        for rec in recs:
            assert rec.effective_purchase_price <= 9.50


class TestWheelStrategy:
    """Tests for WheelStrategy class."""

    @pytest.fixture
    def optimizer(self):
        return StrikeOptimizer()

    @pytest.fixture
    def call_analyzer(self, optimizer):
        return CoveredCallAnalyzer(optimizer)

    @pytest.fixture
    def put_analyzer(self, optimizer):
        return CoveredPutAnalyzer(optimizer)

    @pytest.fixture
    def wheel(self, call_analyzer, put_analyzer):
        return WheelStrategy(call_analyzer, put_analyzer)

    @pytest.fixture
    def mock_options_chain(self):
        """Create a mock options chain with both calls and puts."""
        exp_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        contracts = [
            # OTM calls
            OptionContract(
                symbol="TEST",
                strike=11.00,
                expiration_date=exp_date,
                option_type="Call",
                bid=0.25,
                ask=0.30,
                open_interest=500,
            ),
            OptionContract(
                symbol="TEST",
                strike=11.50,
                expiration_date=exp_date,
                option_type="Call",
                bid=0.15,
                ask=0.18,
                open_interest=300,
            ),
            # OTM puts
            OptionContract(
                symbol="TEST",
                strike=10.00,
                expiration_date=exp_date,
                option_type="Put",
                bid=0.20,
                ask=0.25,
                open_interest=500,
            ),
            OptionContract(
                symbol="TEST",
                strike=9.50,
                expiration_date=exp_date,
                option_type="Put",
                bid=0.12,
                ask=0.15,
                open_interest=300,
            ),
        ]
        return OptionsChain(
            symbol="TEST",
            contracts=contracts,
            retrieved_at=datetime.now().isoformat(),
        )

    def test_wheel_initialization(self, wheel, call_analyzer, put_analyzer):
        """Test wheel strategy initializes with analyzers."""
        assert wheel.call_analyzer is call_analyzer
        assert wheel.put_analyzer is put_analyzer

    def test_get_recommendation_cash_state(self, wheel, mock_options_chain):
        """Test recommendation when in CASH state."""
        rec = wheel.get_recommendation(
            state=WheelState.CASH,
            options_chain=mock_options_chain,
            current_price=10.50,
            volatility=0.30,
        )

        assert rec is not None
        assert isinstance(rec, WheelRecommendation)
        assert rec.state == WheelState.CASH
        assert rec.action == "sell_put"
        assert isinstance(rec.analysis, CoveredPutResult)
        assert "put" in rec.rationale.lower()

    def test_get_recommendation_shares_state(self, wheel, mock_options_chain):
        """Test recommendation when in SHARES state."""
        rec = wheel.get_recommendation(
            state=WheelState.SHARES,
            options_chain=mock_options_chain,
            current_price=10.50,
            volatility=0.30,
        )

        assert rec is not None
        assert isinstance(rec, WheelRecommendation)
        assert rec.state == WheelState.SHARES
        assert rec.action == "sell_call"
        assert isinstance(rec.analysis, CoveredCallResult)
        assert "call" in rec.rationale.lower()

    def test_recommendation_to_dict(self, wheel, mock_options_chain):
        """Test WheelRecommendation serialization."""
        rec = wheel.get_recommendation(
            state=WheelState.CASH,
            options_chain=mock_options_chain,
            current_price=10.50,
            volatility=0.30,
        )

        rec_dict = rec.to_dict()

        assert "state" in rec_dict
        assert "action" in rec_dict
        assert "analysis" in rec_dict
        assert "rationale" in rec_dict

    def test_calculate_cycle_metrics_basic(self, wheel):
        """Test cycle metrics calculation."""
        metrics = wheel.calculate_cycle_metrics(
            premiums_collected=[20.0, 25.0],  # Two premiums
            num_puts=1,
            num_calls=1,
        )

        assert isinstance(metrics, WheelCycleMetrics)
        assert metrics.total_premium_collected == 45.0
        assert metrics.num_put_cycles == 1
        assert metrics.num_call_cycles == 1
        assert metrics.cycle_complete is False

    def test_calculate_cycle_metrics_with_assignment(self, wheel):
        """Test cycle metrics with share assignment."""
        metrics = wheel.calculate_cycle_metrics(
            premiums_collected=[20.0, 25.0],
            acquisition_price=10.00,  # Assigned at $10
            num_puts=1,
            num_calls=1,
        )

        # Cost basis = acquisition - (total premium / 100)
        # = 10.00 - (45 / 100) = 10.00 - 0.45 = 9.55
        assert metrics.shares_acquired_price == 10.00
        assert metrics.average_cost_basis == 9.55

    def test_calculate_cycle_metrics_complete_cycle(self, wheel):
        """Test complete wheel cycle metrics."""
        metrics = wheel.calculate_cycle_metrics(
            premiums_collected=[20.0, 25.0, 30.0],  # 3 premiums
            acquisition_price=10.00,
            sale_price=11.00,  # Called away at $11
            num_puts=1,
            num_calls=2,
        )

        assert metrics.cycle_complete is True
        assert metrics.shares_sold_price == 11.00

        # Net profit = (sale - cost_basis) * 100
        # cost_basis = 10.00 - 0.75 = 9.25
        # net_profit = (11.00 - 9.25) * 100 = 175
        assert metrics.average_cost_basis == 9.25
        assert metrics.net_profit == 175.0

    def test_cycle_metrics_to_dict(self, wheel):
        """Test WheelCycleMetrics serialization."""
        metrics = wheel.calculate_cycle_metrics(
            premiums_collected=[20.0],
            num_puts=1,
        )

        metrics_dict = metrics.to_dict()

        assert "total_premium_collected" in metrics_dict
        assert "num_put_cycles" in metrics_dict
        assert "num_call_cycles" in metrics_dict
        assert "cycle_complete" in metrics_dict


class TestWheelState:
    """Tests for WheelState enum."""

    def test_wheel_state_values(self):
        """Test wheel state enum values."""
        assert WheelState.CASH.value == "cash"
        assert WheelState.SHARES.value == "shares"

    def test_wheel_state_members(self):
        """Test wheel state has expected members."""
        assert WheelState.CASH in WheelState
        assert WheelState.SHARES in WheelState


class TestWarningThresholds:
    """Tests for warning threshold constants."""

    def test_warning_constants_defined(self):
        """Test that warning constants are defined."""
        assert MIN_BID_PRICE == 0.05
        assert MIN_OPEN_INTEREST == 100
        assert MAX_BID_ASK_SPREAD_PCT == 10.0


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def optimizer(self):
        return StrikeOptimizer()

    @pytest.fixture
    def call_analyzer(self, optimizer):
        return CoveredCallAnalyzer(optimizer)

    @pytest.fixture
    def put_analyzer(self, optimizer):
        return CoveredPutAnalyzer(optimizer)

    def test_call_analyzer_no_bid(self, call_analyzer):
        """Test call analysis with no bid price."""
        exp_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        contract = OptionContract(
            symbol="TEST",
            strike=11.00,
            expiration_date=exp_date,
            option_type="Call",
            bid=None,
            ask=0.30,
        )

        result = call_analyzer.analyze(
            contract=contract,
            current_price=10.50,
            volatility=0.30,
        )

        assert result.premium_per_share == 0
        assert any("No bid" in w for w in result.warnings)

    def test_put_analyzer_no_bid(self, put_analyzer):
        """Test put analysis with no bid price."""
        exp_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        contract = OptionContract(
            symbol="TEST",
            strike=10.00,
            expiration_date=exp_date,
            option_type="Put",
            bid=None,
            ask=0.25,
        )

        result = put_analyzer.analyze(
            contract=contract,
            current_price=10.50,
            volatility=0.30,
        )

        assert result.premium_per_share == 0
        assert any("No bid" in w for w in result.warnings)

    def test_empty_options_chain_calls(self, call_analyzer):
        """Test recommendations with empty options chain."""
        empty_chain = OptionsChain(
            symbol="TEST",
            contracts=[],
            retrieved_at=datetime.now().isoformat(),
        )

        recs = call_analyzer.get_recommendations(
            options_chain=empty_chain,
            current_price=10.50,
            volatility=0.30,
        )

        assert recs == []

    def test_empty_options_chain_puts(self, put_analyzer):
        """Test put recommendations with empty options chain."""
        empty_chain = OptionsChain(
            symbol="TEST",
            contracts=[],
            retrieved_at=datetime.now().isoformat(),
        )

        recs = put_analyzer.get_recommendations(
            options_chain=empty_chain,
            current_price=10.50,
            volatility=0.30,
        )

        assert recs == []
