"""Unit tests for volatility calculation module."""

import pytest
import math
from src.volatility import (
    VolatilityCalculator,
    VolatilityConfig,
    BlendWeights,
    VolatilityResult,
    PriceData
)


class TestVolatilityConfig:
    """Test suite for VolatilityConfig class."""

    def test_config_default_values(self):
        """Test default configuration values."""
        config = VolatilityConfig()
        assert config.short_window == 20
        assert config.long_window == 60
        assert config.annualization_factor == 252.0
        assert config.min_data_points == 10

    def test_config_custom_values(self):
        """Test custom configuration values."""
        config = VolatilityConfig(
            short_window=10,
            long_window=30,
            annualization_factor=250.0,
            min_data_points=5
        )
        assert config.short_window == 10
        assert config.long_window == 30
        assert config.annualization_factor == 250.0
        assert config.min_data_points == 5

    def test_config_validation_short_window(self):
        """Test that short_window must be at least 2."""
        with pytest.raises(ValueError, match="short_window must be at least 2"):
            VolatilityConfig(short_window=1)

    def test_config_validation_long_window(self):
        """Test that long_window must be >= short_window."""
        with pytest.raises(ValueError, match="long_window must be >= short_window"):
            VolatilityConfig(short_window=30, long_window=20)

    def test_config_validation_annualization(self):
        """Test that annualization_factor must be positive."""
        with pytest.raises(ValueError, match="annualization_factor must be positive"):
            VolatilityConfig(annualization_factor=0)


class TestBlendWeights:
    """Test suite for BlendWeights class."""

    def test_default_weights(self):
        """Test default blend weights."""
        weights = BlendWeights()
        assert weights.realized_short == 0.30
        assert weights.realized_long == 0.20
        assert weights.implied == 0.50

    def test_weights_sum_to_one(self):
        """Test that weights must sum to 1.0."""
        # Valid weights
        weights = BlendWeights(realized_short=0.4, realized_long=0.3, implied=0.3)
        assert abs(sum([weights.realized_short, weights.realized_long, weights.implied]) - 1.0) < 0.001

    def test_weights_validation_sum(self):
        """Test that weights must sum to 1.0."""
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            BlendWeights(realized_short=0.5, realized_long=0.3, implied=0.3)

    def test_weights_validation_negative(self):
        """Test that weights cannot be negative."""
        with pytest.raises(ValueError, match="All weights must be non-negative"):
            BlendWeights(realized_short=-0.1, realized_long=0.6, implied=0.5)


class TestPriceData:
    """Test suite for PriceData class."""

    def test_price_data_minimal(self):
        """Test PriceData with minimal required fields."""
        dates = ["2026-01-01", "2026-01-02", "2026-01-03"]
        closes = [100.0, 101.0, 102.0]

        data = PriceData(dates=dates, closes=closes)
        assert len(data.dates) == 3
        assert len(data.closes) == 3
        assert data.opens is None

    def test_price_data_with_ohlc(self):
        """Test PriceData with full OHLC data."""
        dates = ["2026-01-01", "2026-01-02"]
        opens = [100.0, 101.0]
        highs = [102.0, 103.0]
        lows = [99.0, 100.0]
        closes = [101.0, 102.0]

        data = PriceData(
            dates=dates,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes
        )
        assert len(data.opens) == 2
        assert len(data.highs) == 2

    def test_price_data_length_mismatch(self):
        """Test that all arrays must have same length."""
        with pytest.raises(ValueError, match="closes must match dates length"):
            PriceData(
                dates=["2026-01-01", "2026-01-02"],
                closes=[100.0]  # Wrong length
            )

    def test_price_data_invalid_prices(self):
        """Test that prices must be positive."""
        with pytest.raises(ValueError, match="All prices must be positive"):
            PriceData(
                dates=["2026-01-01", "2026-01-02"],
                closes=[100.0, -50.0]  # Negative price
            )

    def test_price_data_high_low_validation(self):
        """Test that high must be >= low."""
        with pytest.raises(ValueError, match="High < Low at index"):
            PriceData(
                dates=["2026-01-01"],
                closes=[100.0],
                highs=[99.0],  # High < Low
                lows=[100.0]
            )


class TestVolatilityCalculator:
    """Test suite for VolatilityCalculator class."""

    def test_calculator_initialization(self):
        """Test calculator initialization."""
        calc = VolatilityCalculator()
        assert calc.config is not None
        assert calc.config.short_window == 20

    def test_calculator_custom_config(self):
        """Test calculator with custom config."""
        config = VolatilityConfig(short_window=10)
        calc = VolatilityCalculator(config=config)
        assert calc.config.short_window == 10

    def test_close_to_close_basic(self):
        """Test basic close-to-close volatility calculation."""
        calc = VolatilityCalculator()

        # Test data with varying returns (creates volatility)
        prices = [100.0]
        for i in range(20):
            # Alternate between +1% and -0.5% returns to create variance
            if i % 2 == 0:
                prices.append(prices[-1] * 1.01)
            else:
                prices.append(prices[-1] * 0.995)

        result = calc.calculate_close_to_close(prices, annualize=False)

        assert isinstance(result, VolatilityResult)
        assert result.method == "close_to_close"
        assert result.data_points == 20  # Windowed to 20 days
        assert result.volatility > 0

    def test_close_to_close_annualized(self):
        """Test annualized close-to-close volatility."""
        calc = VolatilityCalculator()

        prices = [100.0 + i for i in range(30)]

        result_annual = calc.calculate_close_to_close(prices, annualize=True)
        result_daily = calc.calculate_close_to_close(prices, annualize=False)

        # Annualized should be roughly sqrt(252) times daily
        ratio = result_annual.volatility / result_daily.volatility
        assert 15 < ratio < 17  # sqrt(252) ≈ 15.87

    def test_close_to_close_with_dates(self):
        """Test close-to-close with date tracking."""
        calc = VolatilityCalculator()

        # Need at least 10 data points
        dates = [f"2026-01-{i:02d}" for i in range(1, 16)]
        prices = [100.0 + i * 0.5 for i in range(15)]

        result = calc.calculate_close_to_close(prices, dates=dates, annualize=False)

        assert result.start_date == "2026-01-01"
        assert result.end_date == "2026-01-15"

    def test_close_to_close_insufficient_data(self):
        """Test that insufficient data raises error."""
        calc = VolatilityCalculator()

        with pytest.raises(ValueError, match="Insufficient data"):
            calc.calculate_close_to_close([100.0], annualize=False)

    def test_parkinson_basic(self):
        """Test basic Parkinson volatility calculation."""
        calc = VolatilityCalculator()

        # Create test data with 2% daily range
        highs = [102.0 + i for i in range(20)]
        lows = [100.0 + i for i in range(20)]

        result = calc.calculate_parkinson(highs, lows, annualize=False)

        assert isinstance(result, VolatilityResult)
        assert result.method == "parkinson"
        assert result.volatility > 0
        assert result.metadata["efficiency_ratio"] == 5.2

    def test_parkinson_length_mismatch(self):
        """Test that highs and lows must have same length."""
        calc = VolatilityCalculator()

        with pytest.raises(ValueError, match="highs and lows must have same length"):
            calc.calculate_parkinson([100.0, 101.0], [99.0])

    def test_parkinson_high_less_than_low(self):
        """Test that high must be >= low."""
        calc = VolatilityCalculator()

        # Need at least 10 data points, with one having high < low
        highs = [102.0] * 9 + [99.0]  # Last one is invalid
        lows = [100.0] * 10

        with pytest.raises(ValueError, match="High .* < Low"):
            calc.calculate_parkinson(highs, lows)

    def test_garman_klass_basic(self):
        """Test basic Garman-Klass volatility calculation."""
        calc = VolatilityCalculator()

        n = 20
        opens = [100.0 + i for i in range(n)]
        highs = [102.0 + i for i in range(n)]
        lows = [99.0 + i for i in range(n)]
        closes = [101.0 + i for i in range(n)]

        result = calc.calculate_garman_klass(opens, highs, lows, closes, annualize=False)

        assert isinstance(result, VolatilityResult)
        assert result.method == "garman_klass"
        assert result.volatility > 0
        assert result.metadata["efficiency_ratio"] == 7.4

    def test_garman_klass_length_mismatch(self):
        """Test that all OHLC arrays must have same length."""
        calc = VolatilityCalculator()

        with pytest.raises(ValueError, match="All OHLC arrays must have same length"):
            calc.calculate_garman_klass(
                opens=[100.0, 101.0],
                highs=[102.0],  # Wrong length
                lows=[99.0, 100.0],
                closes=[101.0, 102.0]
            )

    def test_yang_zhang_basic(self):
        """Test basic Yang-Zhang volatility calculation."""
        calc = VolatilityCalculator()

        n = 20
        opens = [100.0 + i * 0.5 for i in range(n)]
        highs = [102.0 + i * 0.5 for i in range(n)]
        lows = [99.0 + i * 0.5 for i in range(n)]
        closes = [101.0 + i * 0.5 for i in range(n)]

        result = calc.calculate_yang_zhang(opens, highs, lows, closes, annualize=False)

        assert isinstance(result, VolatilityResult)
        assert result.method == "yang_zhang"
        assert result.volatility > 0
        assert result.metadata["efficiency_ratio"] == 8.0
        assert "k_parameter" in result.metadata

    def test_blended_volatility(self):
        """Test blended volatility calculation."""
        calc = VolatilityCalculator()

        # Create price data
        dates = [f"2026-01-{i:02d}" for i in range(1, 62)]
        closes = [100.0 + i * 0.1 for i in range(61)]

        price_data = PriceData(dates=dates, closes=closes)
        implied_vol = 0.30  # 30% IV

        result = calc.calculate_blended(price_data, implied_vol)

        assert isinstance(result, VolatilityResult)
        assert result.method == "blended"
        assert result.volatility > 0
        assert "rv_short" in result.metadata
        assert "rv_long" in result.metadata
        assert "implied_vol" in result.metadata
        assert result.metadata["implied_vol"] == implied_vol

    def test_blended_custom_weights(self):
        """Test blended volatility with custom weights."""
        calc = VolatilityCalculator()

        dates = [f"2026-01-{i:02d}" for i in range(1, 62)]
        closes = [100.0 + i * 0.1 for i in range(61)]
        price_data = PriceData(dates=dates, closes=closes)

        # Custom weights: equal blend
        weights = BlendWeights(realized_short=0.33, realized_long=0.34, implied=0.33)

        result = calc.calculate_blended(price_data, implied_volatility=0.25, weights=weights)

        assert result.method == "blended"
        assert result.metadata["weights"]["realized_short"] == 0.33

    def test_calculate_from_price_data(self):
        """Test convenience method for calculating from PriceData."""
        calc = VolatilityCalculator()

        dates = [f"2026-01-{i:02d}" for i in range(1, 31)]
        opens = [100.0 + i * 0.2 for i in range(30)]
        highs = [102.0 + i * 0.2 for i in range(30)]
        lows = [99.0 + i * 0.2 for i in range(30)]
        closes = [101.0 + i * 0.2 for i in range(30)]

        price_data = PriceData(
            dates=dates,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes
        )

        # Test each method
        for method in ["close_to_close", "parkinson", "garman_klass", "yang_zhang"]:
            result = calc.calculate_from_price_data(price_data, method=method, annualize=False)
            assert result.method == method
            assert result.volatility > 0

    def test_calculate_from_price_data_missing_data(self):
        """Test that error is raised when required data is missing."""
        calc = VolatilityCalculator()

        # Price data without OHLC
        price_data = PriceData(
            dates=["2026-01-01", "2026-01-02"],
            closes=[100.0, 101.0]
        )

        with pytest.raises(ValueError, match="Parkinson method requires high and low"):
            calc.calculate_from_price_data(price_data, method="parkinson")

    def test_volatility_result_to_dict(self):
        """Test VolatilityResult to_dict conversion."""
        result = VolatilityResult(
            volatility=0.2534,
            method="close_to_close",
            window=20,
            data_points=20,
            start_date="2026-01-01",
            end_date="2026-01-20",
            annualized=True,
            metadata={"test": "value"}
        )

        d = result.to_dict()

        assert d["volatility"] == 0.2534
        assert d["volatility_percent"] == 25.34
        assert d["method"] == "close_to_close"
        assert d["metadata"]["test"] == "value"


class TestVolatilityMathematicalProperties:
    """Test mathematical properties of volatility estimators."""

    def test_volatility_increases_with_variance(self):
        """Test that volatility increases with price variance."""
        calc = VolatilityCalculator()

        # Low variance prices
        low_var_prices = [100.0 + i * 0.1 for i in range(30)]

        # High variance prices
        high_var_prices = [100.0]
        for i in range(29):
            high_var_prices.append(high_var_prices[-1] * (1.02 if i % 2 == 0 else 0.98))

        vol_low = calc.calculate_close_to_close(low_var_prices, annualize=False)
        vol_high = calc.calculate_close_to_close(high_var_prices, annualize=False)

        assert vol_high.volatility > vol_low.volatility

    def test_parkinson_more_efficient_than_close(self):
        """Test that Parkinson uses more information and can be more stable."""
        calc = VolatilityCalculator()

        n = 30
        closes = [100.0 + i * 0.5 for i in range(n)]
        highs = [c + 2.0 for c in closes]
        lows = [c - 2.0 for c in closes]

        # Both methods should produce positive volatility
        vol_close = calc.calculate_close_to_close(closes, annualize=False)
        vol_park = calc.calculate_parkinson(highs, lows, annualize=False)

        assert vol_close.volatility > 0
        assert vol_park.volatility > 0
