#!/usr/bin/env python3
"""
End-to-end example: Complete volatility calculation pipeline with live data.

This example demonstrates:
1. Fetching historical price data from Alpha Vantage (FREE tier)
   - Uses TIME_SERIES_DAILY for OHLC + volume
   - Note: Dividends/splits require premium TIME_SERIES_DAILY_ADJUSTED
2. Fetching options chain from Finnhub (FREE tier)
3. Extracting implied volatility
4. Calculating realized volatility (multiple methods)
5. Calculating blended volatility
6. Volatility regime analysis
7. Strike optimization with sigma-based calculations
8. Strike recommendations with assignment probabilities
9. Covered strategies analysis (calls, puts, wheel)
10. Weekly overlay scanner with portfolio holdings (NEW - Sprint 4)
    - Holdings-driven covered call recommendations
    - Overwrite cap sizing (default 25%)
    - Earnings exclusion as hard gate
    - Net credit ranking after execution costs
    - Delta-band risk profiles
    - Broker checklist generation

Data Sources:
- Historical OHLCV: Alpha Vantage TIME_SERIES_DAILY (free, 25 req/day)
- Options Chain: Finnhub /stock/option-chain (free tier)

API Documentation:
- Alpha Vantage: https://www.alphavantage.co/documentation/
- Finnhub: https://finnhub.io/docs/api
"""

from src.cache import LocalFileCache
from src.config import FinnhubConfig, AlphaVantageConfig
from src.finnhub_client import FinnhubClient
from src.options_service import OptionsChainService
from src.price_fetcher import AlphaVantagePriceDataFetcher
from src.volatility import VolatilityCalculator, BlendWeights
from src.volatility_integration import (
    extract_atm_implied_volatility,
    calculate_iv_term_structure
)
from src.strike_optimizer import StrikeOptimizer, StrikeProfile
from src.covered_strategies import (
    CoveredCallAnalyzer,
    CoveredPutAnalyzer,
    WheelStrategy,
    WheelState,
)
from src.overlay_scanner import (
    OverlayScanner,
    PortfolioHolding,
    ScannerConfig,
    DeltaBand,
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

        # Initialize file cache for persistent storage and API usage tracking
        file_cache = LocalFileCache()
        price_fetcher = AlphaVantagePriceDataFetcher(
            av_config,
            enable_cache=True,
            file_cache=file_cache
        )

        # Show API usage status
        usage = price_fetcher.get_usage_status()
        print(f"  API Usage Today: {usage['calls_today']}/{usage['daily_limit']} "
              f"({usage['remaining']} remaining)")

        # Fetch maximum available price data (100 days for free tier)
        # This ensures sufficient history for 60-day volatility calculations
        price_data = price_fetcher.fetch_price_data(
            symbol,
            lookback_days=price_fetcher.MAX_LOOKBACK_DAYS
        )

        print(f"\n✓ Fetched {len(price_data.dates)} days of price data")
        print(f"  Period: {price_data.dates[0]} to {price_data.dates[-1]}")
        print(f"  Latest Close: ${price_data.closes[-1]:.2f}")
        print(f"  Price Range: ${min(price_data.closes):.2f} - ${max(price_data.closes):.2f}")

        # Note: Dividend and split data requires premium API (TIME_SERIES_DAILY_ADJUSTED)
        # With free tier (TIME_SERIES_DAILY), these fields are not available
        if price_data.dividends is None:
            print("  Dividends: N/A (requires premium API)")
        if price_data.split_coefficients is None:
            print("  Stock Splits: N/A (requires premium API)")

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

            # Step 7: Strike Optimization
            print("\n" + "-" * 70)
            print("STEP 7: Strike Optimization (NEW)")
            print("-" * 70)

            optimizer = StrikeOptimizer()

            # Get nearest expiration for calculations
            expirations = options_chain.get_expirations()
            nearest_exp = expirations[0] if expirations else None
            profile_strikes = None
            put_profile_strikes = None

            if nearest_exp:
                from datetime import datetime
                try:
                    exp_dt = datetime.fromisoformat(nearest_exp)
                    days_to_expiry = max(1, (exp_dt - datetime.now()).days)
                except (ValueError, TypeError):
                    days_to_expiry = 30

                print(f"\nUsing expiration: {nearest_exp} ({days_to_expiry} DTE)")
                print(f"Using blended volatility: {blended_result.volatility*100:.2f}%")

                # Calculate strikes for all risk profiles
                print("\nCall Strikes by Risk Profile:")
                print(f"{'Profile':<14} {'Sigma':>6} {'Strike':>8} {'P(ITM)':>8}")
                print("-" * 40)

                profile_strikes = optimizer.calculate_strikes_for_profiles(
                    current_price=current_price,
                    volatility=blended_result.volatility,
                    days_to_expiry=days_to_expiry,
                    option_type="call"
                )

                for profile in [StrikeProfile.AGGRESSIVE, StrikeProfile.MODERATE,
                               StrikeProfile.CONSERVATIVE, StrikeProfile.DEFENSIVE]:
                    result = profile_strikes[profile]
                    prob_pct = result.assignment_probability * 100 if result.assignment_probability else 0
                    print(
                        f"{profile.value:<14} {result.sigma:>5.1f}σ "
                        f"${result.tradeable_strike:>7.2f} "
                        f"{prob_pct:>7.1f}%"
                    )

                # Display any warnings for call strikes
                if profile_strikes.warnings:
                    print("\n  ⚠ Call Strike Warnings:")
                    for warning in profile_strikes.warnings:
                        print(f"    • {warning}")

                # Show put strikes as well
                print("\nPut Strikes by Risk Profile:")
                print(f"{'Profile':<14} {'Sigma':>6} {'Strike':>8} {'P(ITM)':>8}")
                print("-" * 40)

                put_profile_strikes = optimizer.calculate_strikes_for_profiles(
                    current_price=current_price,
                    volatility=blended_result.volatility,
                    days_to_expiry=days_to_expiry,
                    option_type="put"
                )

                for profile in [StrikeProfile.AGGRESSIVE, StrikeProfile.MODERATE,
                               StrikeProfile.CONSERVATIVE, StrikeProfile.DEFENSIVE]:
                    result = put_profile_strikes[profile]
                    prob_pct = result.assignment_probability * 100 if result.assignment_probability else 0
                    print(
                        f"{profile.value:<14} {result.sigma:>5.1f}σ "
                        f"${result.tradeable_strike:>7.2f} "
                        f"{prob_pct:>7.1f}%"
                    )

                # Display any warnings for put strikes
                if put_profile_strikes.warnings:
                    print("\n  ⚠ Put Strike Warnings:")
                    for warning in put_profile_strikes.warnings:
                        print(f"    • {warning}")

                # Step 8: Get actual recommendations from options chain
                print("\n" + "-" * 70)
                print("STEP 8: Strike Recommendations from Options Chain")
                print("-" * 70)

                # Get call recommendations
                print("\nTop Call Strike Recommendations (Moderate Profile):")
                call_recs = optimizer.get_strike_recommendations(
                    options_chain=options_chain,
                    current_price=current_price,
                    volatility=blended_result.volatility,
                    option_type="call",
                    expiration_date=nearest_exp,
                    profile=StrikeProfile.MODERATE,
                    limit=3
                )

                if call_recs:
                    print(f"{'Strike':>8} {'Sigma':>6} {'P(ITM)':>7} {'Bid':>6} {'OI':>7} {'Warnings'}")
                    print("-" * 55)
                    for rec in call_recs:
                        warnings_str = ", ".join(rec.warnings[:1]) if rec.warnings else "-"
                        print(
                            f"${rec.strike:>7.2f} {rec.sigma_distance:>5.2f}σ "
                            f"{rec.assignment_probability*100:>6.1f}% "
                            f"${rec.bid if rec.bid else 0:>5.2f} "
                            f"{rec.open_interest if rec.open_interest else 0:>6} "
                            f"{warnings_str}"
                        )
                else:
                    print("  No recommendations found for moderate profile")

                # Get put recommendations
                print("\nTop Put Strike Recommendations (Conservative Profile):")
                put_recs = optimizer.get_strike_recommendations(
                    options_chain=options_chain,
                    current_price=current_price,
                    volatility=blended_result.volatility,
                    option_type="put",
                    expiration_date=nearest_exp,
                    profile=StrikeProfile.CONSERVATIVE,
                    limit=3
                )

                if put_recs:
                    print(f"{'Strike':>8} {'Sigma':>6} {'P(ITM)':>7} {'Bid':>6} {'OI':>7} {'Warnings'}")
                    print("-" * 55)
                    for rec in put_recs:
                        warnings_str = ", ".join(rec.warnings[:1]) if rec.warnings else "-"
                        print(
                            f"${rec.strike:>7.2f} {rec.sigma_distance:>5.2f}σ "
                            f"{rec.assignment_probability*100:>6.1f}% "
                            f"${rec.bid if rec.bid else 0:>5.2f} "
                            f"{rec.open_interest if rec.open_interest else 0:>6} "
                            f"{warnings_str}"
                        )
                else:
                    print("  No recommendations found for conservative profile")

                # Step 9: Covered Strategies Analysis
                print("\n" + "-" * 70)
                print("STEP 9: Covered Strategies Analysis (NEW)")
                print("-" * 70)

                # Initialize analyzers
                call_analyzer = CoveredCallAnalyzer(optimizer)
                put_analyzer = CoveredPutAnalyzer(optimizer)
                wheel = WheelStrategy(call_analyzer, put_analyzer)

                # Analyze covered call recommendations
                print("\nCovered Call Analysis (Top 3):")
                cc_recs = call_analyzer.get_recommendations(
                    options_chain=options_chain,
                    current_price=current_price,
                    volatility=blended_result.volatility,
                    expiration_date=nearest_exp,
                    limit=3
                )

                if cc_recs:
                    print(f"{'Strike':>8} {'Premium':>8} {'If Flat':>10} {'If Called':>10} {'Ann.Ret':>8}")
                    print("-" * 50)
                    for cc in cc_recs:
                        print(
                            f"${cc.contract.strike:>7.2f} "
                            f"${cc.premium_per_share:>7.2f} "
                            f"${cc.profit_if_flat:>9.2f} "
                            f"${cc.max_profit:>9.2f} "
                            f"{cc.annualized_return_if_flat*100:>7.1f}%"
                        )
                        if cc.warnings:
                            print(f"         ⚠ {cc.warnings[0]}")
                else:
                    print("  No covered call recommendations available")

                # Analyze cash-secured put recommendations
                print("\nCash-Secured Put Analysis (Top 3):")
                csp_recs = put_analyzer.get_recommendations(
                    options_chain=options_chain,
                    current_price=current_price,
                    volatility=blended_result.volatility,
                    expiration_date=nearest_exp,
                    limit=3
                )

                if csp_recs:
                    print(f"{'Strike':>8} {'Premium':>8} {'Collat':>9} {'Eff.Buy':>8} {'Ann.Ret':>8}")
                    print("-" * 50)
                    for csp in csp_recs:
                        print(
                            f"${csp.contract.strike:>7.2f} "
                            f"${csp.premium_per_share:>7.2f} "
                            f"${csp.collateral_required:>8.0f} "
                            f"${csp.effective_purchase_price:>7.2f} "
                            f"{csp.annualized_return_if_otm*100:>7.1f}%"
                        )
                        if csp.warnings:
                            print(f"         ⚠ {csp.warnings[0]}")
                else:
                    print("  No cash-secured put recommendations available")

                # Wheel strategy recommendation
                print("\nWheel Strategy Recommendation:")
                print("  Current State: CASH (looking to acquire shares)")

                wheel_rec = wheel.get_recommendation(
                    state=WheelState.CASH,
                    options_chain=options_chain,
                    current_price=current_price,
                    volatility=blended_result.volatility,
                    expiration_date=nearest_exp,
                    profile=StrikeProfile.MODERATE
                )

                if wheel_rec:
                    print(f"  Action: {wheel_rec.action.upper()}")
                    print(f"  Rationale: {wheel_rec.rationale}")
                else:
                    print("  No wheel recommendation available")

                # Step 10: Weekly Overlay Scanner
                print("\n" + "-" * 70)
                print("STEP 10: Weekly Overlay Scanner (NEW - Sprint 4)")
                print("-" * 70)

                # Create a sample portfolio
                holdings = [
                    PortfolioHolding(
                        symbol=symbol,
                        shares=500,
                        cost_basis=current_price * 0.9,  # Example: 10% gain
                        account_type="taxable"
                    )
                ]

                # Configure scanner with conservative settings
                scanner_config = ScannerConfig(
                    overwrite_cap_pct=25.0,  # Only overwrite 25% of position
                    per_contract_fee=0.65,
                    delta_band=DeltaBand.CONSERVATIVE,  # Conservative 10-15% P(ITM)
                    skip_earnings_default=True,
                    min_net_credit=5.00
                )

                # Initialize scanner
                with FinnhubClient(config) as scan_client:
                    scanner = OverlayScanner(
                        finnhub_client=scan_client,
                        strike_optimizer=optimizer,
                        config=scanner_config
                    )

                    # Scan the portfolio
                    print(f"\nScanning portfolio with {len(holdings)} holdings:")
                    print(f"  Settings: {scanner_config.overwrite_cap_pct:.0f}% overwrite cap, "
                          f"{scanner_config.delta_band.value} delta band")

                    scan_results = scanner.scan_portfolio(
                        holdings=holdings,
                        current_prices={symbol: current_price},
                        options_chains={symbol: options_chain},
                        volatilities={symbol: blended_result.volatility}
                    )

                    # Display scan results
                    result = scan_results.get(symbol)
                    if result and not result.error:
                        print(f"\n✓ Scan complete for {symbol}:")
                        print(f"  Shares: {result.shares_held}")
                        print(f"  Contracts available: {result.contracts_available}")
                        print(f"  Earnings conflict: {'Yes' if result.has_earnings_conflict else 'No'}")

                        if result.recommended_strikes:
                            print(f"\n  Top Recommendations (ranked by net credit):")
                            print(f"  {'Strike':>8} {'Exp':>12} {'Delta':>6} {'Net $':>8} {'Yield':>7} {'OI':>7}")
                            print("  " + "-" * 58)

                            for strike in result.recommended_strikes[:3]:
                                print(
                                    f"  ${strike.strike:>7.2f} "
                                    f"{strike.expiration_date:>12} "
                                    f"{strike.delta:>5.2f} "
                                    f"${strike.total_net_credit:>7.2f} "
                                    f"{strike.annualized_yield_pct:>6.1f}% "
                                    f"{strike.open_interest:>6}"
                                )

                            # Show broker checklist for top recommendation
                            if result.broker_checklist:
                                print("\n  Broker Checklist (Top Recommendation):")
                                checklist = result.broker_checklist
                                print(f"    Action: {checklist.action}")
                                print(f"    Contracts: {checklist.contracts}")
                                print(f"    Strike: ${checklist.strike:.2f}")
                                print(f"    Expiration: {checklist.expiration}")
                                print(f"    Limit Price: ${checklist.limit_price:.2f}")
                                print(f"    Min Credit: ${checklist.min_acceptable_credit:.2f}")
                                print(f"    Verification steps: {len(checklist.checks)}")
                        else:
                            print("\n  No recommendations - all strikes filtered out")
                            if result.rejected_strikes:
                                print(f"  Rejected {len(result.rejected_strikes)} strikes")

                                # Show rejection reasons summary
                                rejection_counts = {}
                                for strike in result.rejected_strikes:
                                    for reason in strike.rejection_reasons:
                                        rejection_counts[reason.value] = rejection_counts.get(reason.value, 0) + 1
                                print("  Rejection reasons summary:")
                                for reason, count in sorted(rejection_counts.items(), key=lambda x: -x[1])[:5]:
                                    print(f"    • {reason}: {count}")

                                # Near-miss analysis
                                if result.near_miss_candidates:
                                    print("\n  ═══════════════════════════════════════════════════════════════")
                                    print("  NEAR-MISS ANALYSIS (Top 5 closest to passing)")
                                    print("  ═══════════════════════════════════════════════════════════════")
                                    print(f"  {'#':>2} {'Strike':>8} {'Exp':>12} {'Delta':>6} {'Bid':>6} {'Ask':>6} "
                                          f"{'OI':>6} {'Sprd%':>6} {'Net$':>7} {'Score':>5}")
                                    print("  " + "-" * 78)

                                    for i, nm in enumerate(result.near_miss_candidates, 1):
                                        print(
                                            f"  {i:>2} "
                                            f"${nm.strike:>7.2f} "
                                            f"{nm.expiration_date:>12} "
                                            f"{nm.delta:>5.3f} "
                                            f"${nm.bid:>5.2f} "
                                            f"${nm.ask:>5.2f} "
                                            f"{nm.open_interest:>5} "
                                            f"{nm.spread_relative_pct:>5.1f}% "
                                            f"${nm.total_net_credit:>6.2f} "
                                            f"{nm.near_miss_score:>4.2f}"
                                        )

                                        # Show rejection details
                                        print(f"      Rejections ({len(nm.rejection_details)}):")
                                        for detail in nm.rejection_details:
                                            binding_marker = " ◄ BINDING" if nm.binding_constraint and detail.reason == nm.binding_constraint.reason else ""
                                            print(f"        • {detail.reason.value}: {detail.margin_display}{binding_marker}")

                                        print()  # Blank line between candidates
                    elif result and result.error:
                        print(f"\n  ⚠ Error: {result.error}")

            # Final summary
            print("\n" + "=" * 70)
            print("SUMMARY")
            print("=" * 70)
            print(f"\nStock: {symbol} @ ${current_price:.2f}")
            print(f"Blended Volatility: {blended_result.volatility*100:.2f}%")
            print(f"ATM Implied Volatility: {atm_iv*100:.2f}%")
            print(f"Volatility Regime: {regime}")

            if nearest_exp and profile_strikes and put_profile_strikes:
                mod_call = profile_strikes[StrikeProfile.MODERATE]
                cons_put = put_profile_strikes[StrikeProfile.CONSERVATIVE]
                mod_call_prob = mod_call.assignment_probability * 100 if mod_call.assignment_probability else 0
                cons_put_prob = cons_put.assignment_probability * 100 if cons_put.assignment_probability else 0
                print(f"\nSuggested Strikes ({nearest_exp}):")
                print(f"  Covered Call (Moderate): ${mod_call.tradeable_strike:.2f} ({mod_call_prob:.1f}% P(ITM))")
                print(f"  Cash-Secured Put (Conservative): ${cons_put.tradeable_strike:.2f} ({cons_put_prob:.1f}% P(ITM))")

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
