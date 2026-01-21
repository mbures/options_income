"""Tests for the risk analyzer module."""

import pytest

from src.risk_analyzer import (
    CombinedAnalysis,
    IncomeMetrics,
    RiskAnalyzer,
    RiskMetrics,
    ScenarioOutcome,
    ScenarioResult,
)


class TestIncomeMetrics:
    """Tests for IncomeMetrics dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        metrics = IncomeMetrics(
            premium_per_share=2.50,
            total_premium=250.0,
            annualized_yield_pct=30.42,
            return_if_flat_pct=2.50,
            return_if_called_pct=7.50,
            breakeven=97.50,
            days_to_expiry=30,
            max_profit=750.0,
            max_loss=9750.0,
        )

        d = metrics.to_dict()
        assert d["premium_per_share"] == 2.50
        assert d["total_premium"] == 250.0
        assert d["annualized_yield_pct"] == 30.42
        assert d["days_to_expiry"] == 30


class TestRiskMetrics:
    """Tests for RiskMetrics dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        metrics = RiskMetrics(
            probability_profit=0.75,
            probability_max_profit=0.25,
            expected_value=187.50,
            expected_return_pct=1.875,
            opportunity_cost=50.0,
            opportunity_cost_pct=0.5,
            downside_protection_pct=2.5,
            risk_reward_ratio=0.0769,
            sharpe_like_ratio=0.85,
        )

        d = metrics.to_dict()
        assert d["probability_profit_pct"] == 75.0
        assert d["probability_max_profit_pct"] == 25.0
        assert d["expected_value"] == 187.50


class TestScenarioOutcome:
    """Tests for ScenarioOutcome dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        outcome = ScenarioOutcome(
            price_level=105.0,
            price_change_pct=5.0,
            stock_pnl=500.0,
            option_pnl=250.0,
            total_pnl=750.0,
            total_return_pct=7.5,
            buy_hold_pnl=500.0,
            buy_hold_return_pct=5.0,
            strategy_vs_hold=250.0,
        )

        d = outcome.to_dict()
        assert d["price_level"] == 105.0
        assert d["total_pnl"] == 750.0
        assert d["strategy_vs_hold"] == 250.0


class TestRiskAnalyzerIncomeMetrics:
    """Tests for RiskAnalyzer income metrics calculations."""

    @pytest.fixture
    def analyzer(self):
        """Create a RiskAnalyzer instance."""
        return RiskAnalyzer(risk_free_rate=0.05)

    def test_covered_call_income_metrics(self, analyzer):
        """Test income metrics for covered call."""
        metrics = analyzer.calculate_income_metrics(
            current_price=100.0,
            strike=105.0,
            premium=2.50,
            days_to_expiry=30,
            option_type="call",
            shares=100,
        )

        # Total premium = 2.50 * 100 = 250
        assert metrics.total_premium == 250.0
        assert metrics.premium_per_share == 2.50

        # Annualized yield = (250 / 10000) * (365/30) * 100 = 30.42%
        assert metrics.annualized_yield_pct == pytest.approx(30.42, rel=0.01)

        # Return if flat = 250 / 10000 * 100 = 2.5%
        assert metrics.return_if_flat_pct == pytest.approx(2.5, rel=0.01)

        # Breakeven = 100 - 2.50 = 97.50
        assert metrics.breakeven == pytest.approx(97.50, rel=0.01)

        # Max profit = 250 + (105 - 100) * 100 = 750
        assert metrics.max_profit == pytest.approx(750.0, rel=0.01)

    def test_covered_call_income_with_cost_basis(self, analyzer):
        """Test income metrics with different cost basis."""
        metrics = analyzer.calculate_income_metrics(
            current_price=100.0,
            strike=105.0,
            premium=2.50,
            days_to_expiry=30,
            option_type="call",
            shares=100,
            cost_basis=95.0,  # Bought at $95
        )

        # Max profit = premium + (strike - cost_basis) * shares
        # = 250 + (105 - 95) * 100 = 250 + 1000 = 1250
        assert metrics.max_profit == pytest.approx(1250.0, rel=0.01)

    def test_cash_secured_put_income_metrics(self, analyzer):
        """Test income metrics for cash-secured put."""
        metrics = analyzer.calculate_income_metrics(
            current_price=100.0,
            strike=95.0,
            premium=2.00,
            days_to_expiry=30,
            option_type="put",
            shares=100,
        )

        # Total premium = 2.00 * 100 = 200
        assert metrics.total_premium == 200.0

        # Breakeven = 95 - 2 = 93
        assert metrics.breakeven == pytest.approx(93.0, rel=0.01)

        # Max profit = premium (when OTM)
        assert metrics.max_profit == pytest.approx(200.0, rel=0.01)

    def test_zero_days_to_expiry(self, analyzer):
        """Test handling of zero days to expiry."""
        metrics = analyzer.calculate_income_metrics(
            current_price=100.0,
            strike=105.0,
            premium=2.50,
            days_to_expiry=0,
            option_type="call",
        )

        assert metrics.annualized_yield_pct == 0.0


class TestRiskAnalyzerRiskMetrics:
    """Tests for RiskAnalyzer risk metrics calculations."""

    @pytest.fixture
    def analyzer(self):
        """Create a RiskAnalyzer instance."""
        return RiskAnalyzer(risk_free_rate=0.05)

    def test_covered_call_risk_metrics(self, analyzer):
        """Test risk metrics for covered call."""
        metrics = analyzer.calculate_risk_metrics(
            current_price=100.0,
            strike=105.0,
            premium=2.50,
            probability_itm=0.25,
            days_to_expiry=30,
            option_type="call",
            shares=100,
        )

        # P(profit) = P(OTM) = 0.75
        assert metrics.probability_profit == pytest.approx(0.75, rel=0.01)

        # P(max profit) = P(ITM) = 0.25 (called away at strike)
        assert metrics.probability_max_profit == pytest.approx(0.25, rel=0.01)

        # Expected value should be positive for typical covered call
        assert metrics.expected_value > 0

        # Downside protection = premium / price = 2.50 / 100 = 2.5%
        assert metrics.downside_protection_pct == pytest.approx(2.5, rel=0.01)

    def test_covered_call_with_price_target(self, analyzer):
        """Test opportunity cost with price target."""
        metrics = analyzer.calculate_risk_metrics(
            current_price=100.0,
            strike=105.0,
            premium=2.50,
            probability_itm=0.25,
            days_to_expiry=30,
            option_type="call",
            shares=100,
            price_target=115.0,  # Higher than strike
        )

        # Opportunity cost = (115 - 105) * 100 * 0.25 = 250
        assert metrics.opportunity_cost == pytest.approx(250.0, rel=0.01)
        assert metrics.opportunity_cost_pct > 0

    def test_cash_secured_put_risk_metrics(self, analyzer):
        """Test risk metrics for cash-secured put."""
        metrics = analyzer.calculate_risk_metrics(
            current_price=100.0,
            strike=95.0,
            premium=2.00,
            probability_itm=0.20,
            days_to_expiry=30,
            option_type="put",
            shares=100,
        )

        # P(profit) = P(OTM) = 0.80
        assert metrics.probability_profit == pytest.approx(0.80, rel=0.01)

        # P(max profit) = P(OTM) = 0.80 (max profit when put expires OTM)
        assert metrics.probability_max_profit == pytest.approx(0.80, rel=0.01)

        # Expected value should be positive for typical CSP
        assert metrics.expected_value > 0

    def test_sharpe_like_ratio(self, analyzer):
        """Test Sharpe-like ratio calculation."""
        metrics = analyzer.calculate_risk_metrics(
            current_price=100.0,
            strike=105.0,
            premium=2.50,
            probability_itm=0.25,
            days_to_expiry=30,
            option_type="call",
            shares=100,
            expected_volatility=0.20,
        )

        # Sharpe-like ratio should be calculated
        assert metrics.sharpe_like_ratio != 0


class TestRiskAnalyzerScenarios:
    """Tests for RiskAnalyzer scenario analysis."""

    @pytest.fixture
    def analyzer(self):
        """Create a RiskAnalyzer instance."""
        return RiskAnalyzer()

    def test_covered_call_scenarios(self, analyzer):
        """Test scenario analysis for covered call."""
        result = analyzer.calculate_scenarios(
            current_price=100.0,
            strike=105.0,
            premium=2.50,
            option_type="call",
            shares=100,
        )

        assert isinstance(result, ScenarioResult)
        assert len(result.scenarios) > 0
        assert result.best_scenario is not None
        assert result.worst_scenario is not None

        # Breakeven for call = current - premium = 97.50
        assert result.breakeven_price == pytest.approx(97.50, rel=0.01)

    def test_covered_call_scenario_outcomes(self, analyzer):
        """Test specific scenario outcomes for covered call."""
        result = analyzer.calculate_scenarios(
            current_price=100.0,
            strike=105.0,
            premium=2.50,
            option_type="call",
            shares=100,
            custom_levels=[90.0, 100.0, 105.0, 110.0],
        )

        # Find scenario at strike (105)
        at_strike = next(s for s in result.scenarios if s.price_level == 105.0)

        # At strike: stock called away at 105, total = (105-100)*100 + 250 = 750
        assert at_strike.total_pnl == pytest.approx(750.0, rel=0.01)

        # Find scenario above strike (110)
        above_strike = next(s for s in result.scenarios if s.price_level == 110.0)

        # Above strike: capped at strike, total still 750
        assert above_strike.total_pnl == pytest.approx(750.0, rel=0.01)

        # Strategy underperforms buy-hold above strike
        assert above_strike.strategy_vs_hold < 0

    def test_cash_secured_put_scenarios(self, analyzer):
        """Test scenario analysis for cash-secured put."""
        result = analyzer.calculate_scenarios(
            current_price=100.0,
            strike=95.0,
            premium=2.00,
            option_type="put",
            shares=100,
        )

        assert isinstance(result, ScenarioResult)

        # Breakeven for put = strike - premium = 93
        assert result.breakeven_price == pytest.approx(93.0, rel=0.01)

    def test_cash_secured_put_scenario_outcomes(self, analyzer):
        """Test specific scenario outcomes for CSP."""
        result = analyzer.calculate_scenarios(
            current_price=100.0,
            strike=95.0,
            premium=2.00,
            option_type="put",
            shares=100,
            custom_levels=[85.0, 95.0, 100.0, 105.0],
        )

        # Find scenario above strike (put expires worthless)
        above_strike = next(s for s in result.scenarios if s.price_level == 105.0)

        # Put OTM: keep premium = 200
        assert above_strike.total_pnl == pytest.approx(200.0, rel=0.01)

        # Find scenario below strike (put assigned)
        below_strike = next(s for s in result.scenarios if s.price_level == 85.0)

        # Put ITM: assigned at 95, stock now worth 85
        # P&L = (85 - 95) * 100 + 200 = -1000 + 200 = -800
        assert below_strike.total_pnl == pytest.approx(-800.0, rel=0.01)


class TestRiskAnalyzerCombinedAnalysis:
    """Tests for complete analysis methods."""

    @pytest.fixture
    def analyzer(self):
        """Create a RiskAnalyzer instance."""
        return RiskAnalyzer()

    def test_analyze_covered_call(self, analyzer):
        """Test complete covered call analysis."""
        analysis = analyzer.analyze_covered_call(
            current_price=100.0,
            strike=105.0,
            premium=2.50,
            days_to_expiry=30,
            probability_itm=0.25,
            shares=100,
        )

        assert isinstance(analysis, CombinedAnalysis)
        assert isinstance(analysis.income_metrics, IncomeMetrics)
        assert isinstance(analysis.risk_metrics, RiskMetrics)
        assert isinstance(analysis.scenario_analysis, ScenarioResult)

    def test_analyze_covered_call_without_scenarios(self, analyzer):
        """Test covered call analysis without scenarios."""
        analysis = analyzer.analyze_covered_call(
            current_price=100.0,
            strike=105.0,
            premium=2.50,
            days_to_expiry=30,
            probability_itm=0.25,
            include_scenarios=False,
        )

        assert analysis.scenario_analysis is None

    def test_analyze_covered_call_itm_warning(self, analyzer):
        """Test warning for ITM call."""
        analysis = analyzer.analyze_covered_call(
            current_price=100.0,
            strike=95.0,  # ITM
            premium=5.50,
            days_to_expiry=30,
            probability_itm=0.75,
        )

        assert any("ITM" in w for w in analysis.warnings)

    def test_analyze_covered_call_low_yield_warning(self, analyzer):
        """Test warning for low yield."""
        analysis = analyzer.analyze_covered_call(
            current_price=100.0,
            strike=120.0,  # Far OTM
            premium=0.10,  # Very low premium
            days_to_expiry=30,
            probability_itm=0.01,
        )

        assert any("Low annualized yield" in w for w in analysis.warnings)

    def test_analyze_cash_secured_put(self, analyzer):
        """Test complete CSP analysis."""
        analysis = analyzer.analyze_cash_secured_put(
            current_price=100.0,
            strike=95.0,
            premium=2.00,
            days_to_expiry=30,
            probability_itm=0.20,
        )

        assert isinstance(analysis, CombinedAnalysis)
        assert isinstance(analysis.income_metrics, IncomeMetrics)
        assert isinstance(analysis.risk_metrics, RiskMetrics)

    def test_analyze_csp_itm_warning(self, analyzer):
        """Test warning for ITM put."""
        analysis = analyzer.analyze_cash_secured_put(
            current_price=100.0,
            strike=105.0,  # ITM
            premium=5.50,
            days_to_expiry=30,
            probability_itm=0.75,
        )

        assert any("ITM" in w for w in analysis.warnings)

    def test_to_dict_full_analysis(self, analyzer):
        """Test complete serialization."""
        analysis = analyzer.analyze_covered_call(
            current_price=100.0,
            strike=105.0,
            premium=2.50,
            days_to_expiry=30,
            probability_itm=0.25,
        )

        d = analysis.to_dict()
        assert "income_metrics" in d
        assert "risk_metrics" in d
        assert "scenario_analysis" in d
        assert "warnings" in d


class TestRiskAnalyzerComparison:
    """Tests for strategy comparison."""

    @pytest.fixture
    def analyzer(self):
        """Create a RiskAnalyzer instance."""
        return RiskAnalyzer()

    def test_compare_strategies(self, analyzer):
        """Test strategy comparison."""
        comparison = analyzer.compare_strategies(
            current_price=100.0,
            call_strike=105.0,
            call_premium=2.50,
            put_strike=95.0,
            put_premium=2.00,
            days_to_expiry=30,
            call_prob_itm=0.25,
            put_prob_itm=0.20,
        )

        assert "covered_call" in comparison
        assert "cash_secured_put" in comparison
        assert "recommendation" in comparison
        assert "reason" in comparison
        assert comparison["recommendation"] in ["covered_call", "cash_secured_put", "either"]

    def test_compare_strategies_ev_difference(self, analyzer):
        """Test EV difference in comparison."""
        comparison = analyzer.compare_strategies(
            current_price=100.0,
            call_strike=105.0,
            call_premium=2.50,
            put_strike=95.0,
            put_premium=2.00,
            days_to_expiry=30,
            call_prob_itm=0.25,
            put_prob_itm=0.20,
        )

        # EV difference should reflect the better strategy
        ev_diff = comparison["ev_difference"]
        if comparison["recommendation"] == "covered_call":
            assert ev_diff > 0
        elif comparison["recommendation"] == "cash_secured_put":
            assert ev_diff < 0


class TestRiskAnalyzerEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def analyzer(self):
        """Create a RiskAnalyzer instance."""
        return RiskAnalyzer()

    def test_zero_premium(self, analyzer):
        """Test handling of zero premium."""
        analysis = analyzer.analyze_covered_call(
            current_price=100.0,
            strike=105.0,
            premium=0.0,
            days_to_expiry=30,
            probability_itm=0.25,
        )

        assert any("Zero or negative premium" in w for w in analysis.warnings)

    def test_very_short_dte(self, analyzer):
        """Test with 1 day to expiry."""
        analysis = analyzer.analyze_covered_call(
            current_price=100.0,
            strike=105.0,
            premium=0.50,
            days_to_expiry=1,
            probability_itm=0.05,
        )

        # Annualized yield will be very high
        assert analysis.income_metrics.annualized_yield_pct > 100

    def test_very_high_premium(self, analyzer):
        """Test with high premium (deep ITM simulation)."""
        analysis = analyzer.analyze_covered_call(
            current_price=100.0,
            strike=105.0,
            premium=10.0,  # 10% premium
            days_to_expiry=30,
            probability_itm=0.50,
        )

        # Should calculate without errors
        assert analysis.income_metrics.total_premium == 1000.0
        assert analysis.income_metrics.annualized_yield_pct > 100

    def test_high_opportunity_cost_warning(self, analyzer):
        """Test warning for high opportunity cost."""
        analysis = analyzer.analyze_covered_call(
            current_price=100.0,
            strike=102.0,  # Close to ATM
            premium=3.00,
            days_to_expiry=30,
            probability_itm=0.45,
            price_target=120.0,  # High price target
        )

        assert any("opportunity cost" in w.lower() for w in analysis.warnings)

    def test_small_discount_warning_csp(self, analyzer):
        """Test warning for small discount on CSP."""
        analysis = analyzer.analyze_cash_secured_put(
            current_price=100.0,
            strike=99.0,  # Only 1% below current
            premium=0.50,  # Small premium
            days_to_expiry=30,
            probability_itm=0.45,  # High P(ITM)
        )

        # Effective purchase = 99 - 0.50 = 98.50
        # Discount = (100 - 98.50) / 100 = 1.5%
        assert any("Small discount" in w for w in analysis.warnings)


class TestRiskAnalyzerInitialization:
    """Tests for RiskAnalyzer initialization."""

    def test_default_risk_free_rate(self):
        """Test default risk-free rate."""
        analyzer = RiskAnalyzer()
        assert analyzer.risk_free_rate == 0.05

    def test_custom_risk_free_rate(self):
        """Test custom risk-free rate."""
        analyzer = RiskAnalyzer(risk_free_rate=0.03)
        assert analyzer.risk_free_rate == 0.03
