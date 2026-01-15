#!/usr/bin/env python3
"""
End-to-end example: Complete volatility calculation pipeline with live data.

This example demonstrates:
1. Fetching historical price data from Alpha Vantage (FREE tier)
2. Fetching options chain from Finnhub (FREE tier)
3. Extracting implied volatility
4. Calculating realized volatility (multiple methods)
5. Calculating blended volatility
6. Complete integration workflow

Data Sources:
- Historical OHLCV: Alpha Vantage TIME_SERIES_DAILY (free, 25 req/day)
- Options Chain: Finnhub /stock/option-chain (free tier)

API Documentation:
- Alpha Vantage: https://www.alphavantage.co/documentation/
- Finnhub: https://finnhub.io/docs/api
"""

from src.config import FinnhubConfig, AlphaVantageConfig
from src.finnhub_client import FinnhubClient
from src.options_service import OptionsChainService
from src.price_fetcher import AlphaVantagePriceDataFetcher
from src.volatility import VolatilityCalculator, BlendWeights
from src.volatility_integration import (
    extract_atm_implied_volatility,
    calculate_iv_term_structure
)


def main():
    """Run complete end-to-end volatility calculation."""
    print("=" * 70)
    print("END-TO-END VOLATILITY CALCULATION WITH LIVE DATA")
    print("=" * 70)

    # Ticker to analyze
    symbol = "F"  # Ford
    print(f"\nAnalyzing: {symbol}")

    try:
        # Step 1: Fetch historical price data from Alpha Vantage (FREE tier)
        print("\n" + "-" * 70)
        print("STEP 1: Fetching Historical Price Data (Alpha Vantage)")
        print("-" * 70)

        av_config = AlphaVantageConfig.from_file()
        print("✓ Alpha Vantage configuration loaded")

        price_fetcher = AlphaVantagePriceDataFetcher(av_config, enable_cache=True)

        # Fetch 60 days of price data
        price_data = price_fetcher.fetch_price_data(symbol, lookback_days=60)

        print(f"\n✓ Fetched {len(price_data.dates)} days of price data")
        print(f"  Period: {price_data.dates[0]} to {price_data.dates[-1]}")
        print(f"  Latest Close: ${price_data.closes[-1]:.2f}")
        print(f"  Price Range: ${min(price_data.closes):.2f} - ${max(price_data.closes):.2f}")

        # Step 2: Calculate realized volatility
        print("\n" + "-" * 70)
        print("STEP 2: Calculating Realized Volatility")
        print("-" * 70)

        calculator = VolatilityCalculator()

        # Calculate using different methods
        print("\nVolatility Estimates:")
        print(f"{'Method':<20} {'20-Day':>12} {'60-Day':>12}")
        print("-" * 46)

        methods = [
            ("Close-to-Close", "close_to_close"),
            ("Parkinson", "parkinson"),
            ("Garman-Klass", "garman_klass"),
            ("Yang-Zhang", "yang_zhang")
        ]

        results_20d = {}
        results_60d = {}

        for name, method in methods:
            # 20-day
            result_20 = calculator.calculate_from_price_data(
                price_data=price_data,
                method=method,
                window=20,
                annualize=True
            )
            results_20d[method] = result_20

            # 60-day
            result_60 = calculator.calculate_from_price_data(
                price_data=price_data,
                method=method,
                window=60,
                annualize=True
            )
            results_60d[method] = result_60

            print(
                f"{name:<20} {result_20.volatility*100:>11.2f}% "
                f"{result_60.volatility*100:>11.2f}%"
            )

        # Step 3: Initialize Finnhub and fetch options chain
        print("\n" + "-" * 70)
        print("STEP 3: Fetching Options Chain (Finnhub FREE tier)")
        print("-" * 70)

        config = FinnhubConfig.from_file()
        print("✓ Finnhub configuration loaded")

        with FinnhubClient(config) as client:
            service = OptionsChainService(client)
            options_chain = service.get_options_chain(symbol)

            print(f"\n✓ Fetched options chain")
            print(f"  Total Contracts: {len(options_chain.contracts)}")
            print(f"  Calls: {len(options_chain.get_calls())}")
            print(f"  Puts: {len(options_chain.get_puts())}")
            print(f"  Expirations: {len(options_chain.get_expirations())}")

        # Step 4: Extract implied volatility from options
        print("\n" + "-" * 70)
        print("STEP 4: Extracting Implied Volatility")
        print("-" * 70)

        current_price = price_data.closes[-1]
        atm_iv = extract_atm_implied_volatility(
            options_chain=options_chain,
            current_price=current_price
        )

        if atm_iv:
            print(f"\n✓ ATM Implied Volatility: {atm_iv*100:.2f}%")

            # Show IV term structure
            print("\nIV Term Structure:")
            term_structure = calculate_iv_term_structure(
                options_chain=options_chain,
                current_price=current_price,
                num_expirations=4
            )

            print(f"{'Expiration':<12} {'DTE':>5} {'IV':>8}")
            print("-" * 27)
            for item in term_structure[:4]:
                dte = item['days_to_expiry']
                iv_pct = item['implied_volatility_pct']
                print(f"{item['expiration_date']:<12} {dte:>5} {iv_pct:>7.2f}%")

            # Step 5: Calculate blended volatility
            print("\n" + "-" * 70)
            print("STEP 5: Calculating Blended Volatility")
            print("-" * 70)

            # Default blend: 30% RV(20d) + 20% RV(60d) + 50% IV
            blended_result = calculator.calculate_blended(
                price_data=price_data,
                implied_volatility=atm_iv
            )

            print("\nDefault Blend (30% / 20% / 50%):")
            print(f"  Short-term RV (20d): {blended_result.metadata['rv_short']*100:>6.2f}%")
            print(f"  Long-term RV (60d):  {blended_result.metadata['rv_long']*100:>6.2f}%")
            print(f"  Implied Volatility:  {atm_iv*100:>6.2f}%")
            print(f"  → Blended Result:    {blended_result.volatility*100:>6.2f}%")

            # Try aggressive blend (more IV weight)
            aggressive_weights = BlendWeights(
                realized_short=0.20,
                realized_long=0.10,
                implied=0.70
            )
            aggressive_result = calculator.calculate_blended(
                price_data=price_data,
                implied_volatility=atm_iv,
                weights=aggressive_weights
            )

            print("\nAggressive Blend (20% / 10% / 70% - more IV):")
            print(f"  → Blended Result:    {aggressive_result.volatility*100:>6.2f}%")

            # Try conservative blend (more RV weight)
            conservative_weights = BlendWeights(
                realized_short=0.40,
                realized_long=0.40,
                implied=0.20
            )
            conservative_result = calculator.calculate_blended(
                price_data=price_data,
                implied_volatility=atm_iv,
                weights=conservative_weights
            )

            print("\nConservative Blend (40% / 40% / 20% - more RV):")
            print(f"  → Blended Result:    {conservative_result.volatility*100:>6.2f}%")

            # Step 6: Summary and recommendations
            print("\n" + "-" * 70)
            print("STEP 6: Summary & Volatility Regime Analysis")
            print("-" * 70)

            # Use Yang-Zhang as the best estimator
            best_rv_20 = results_20d["yang_zhang"]
            best_rv_60 = results_60d["yang_zhang"]

            print(f"\nBest Realized Volatility Estimates (Yang-Zhang):")
            print(f"  20-day: {best_rv_20.volatility*100:.2f}%")
            print(f"  60-day: {best_rv_60.volatility*100:.2f}%")

            print(f"\nImplied vs. Realized:")
            rv_iv_ratio = best_rv_20.volatility / atm_iv
            print(f"  ATM IV: {atm_iv*100:.2f}%")
            print(f"  RV/IV Ratio: {rv_iv_ratio:.2f}")

            if rv_iv_ratio < 0.8:
                regime = "LOW (RV < IV - options expensive)"
            elif rv_iv_ratio < 1.2:
                regime = "NORMAL (RV ≈ IV - fairly priced)"
            else:
                regime = "HIGH (RV > IV - options cheap)"

            print(f"  Volatility Regime: {regime}")

            print(f"\nRecommended Volatility for Calculations:")
            print(f"  → Use Blended: {blended_result.volatility*100:.2f}%")

        else:
            print("\n⚠ Could not extract implied volatility from options chain")

    except FileNotFoundError as e:
        print(f"\n⚠ ERROR: API key file not found - {e}")
        print("  Required API key files:")
        print("    1. alpha_vantage_api_key.txt - Alpha Vantage API key (plain text)")
        print("    2. config/finhub_api_key.txt - Finnhub API key")
        print("       Format: finhub_api_key = 'your_key_here'")
    except Exception as e:
        print(f"\n⚠ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
