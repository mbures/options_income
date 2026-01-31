"""
Weekly Overlay Scanner for covered call strategies.

This module provides the main OverlayScanner class for generating weekly covered
call recommendations with a holdings-driven broker-first workflow.
"""

import logging
from typing import Any, Dict, List, Optional

from ..earnings_calendar import EarningsCalendar
from ..models import (
    CandidateStrike,
    ExecutionCostEstimate,
    OptionsChain,
    PortfolioHolding,
    RejectionDetail,
    RejectionReason,
    ScannerConfig,
    ScanResult,
    SlippageModel,
)
from ..strike_optimizer import StrikeOptimizer
from ..utils import calculate_days_to_expiry
from .filters import (
    apply_delta_band_filter,
    apply_tradability_filters,
    get_delta_band,
    populate_near_miss_details,
)
from .formatters import generate_broker_checklist, generate_llm_memo_payload

logger = logging.getLogger(__name__)


class OverlayScanner:
    """
    Weekly covered call overlay scanner.

    Scans portfolio holdings and generates ranked covered call recommendations
    with a broker-first workflow.

    Features:
    - Holdings-driven scanning with overwrite cap sizing
    - Delta-band primary selection for weekly calls
    - Earnings-week exclusion by default (hard gate)
    - Net-credit ranking using execution cost model
    - Tradability filters with explicit rejection reasons
    - Broker checklist and LLM memo payload generation

    Example:
        scanner = OverlayScanner(
            finnhub_client=client,
            strike_optimizer=optimizer,
            config=ScannerConfig()
        )

        holdings = [PortfolioHolding("AAPL", 500)]
        prices = {"AAPL": 185.50}

        results = scanner.scan_portfolio(holdings, prices, options_chains)
    """

    def __init__(
        self,
        finnhub_client: Any,
        strike_optimizer: StrikeOptimizer,
        config: Optional[ScannerConfig] = None,
    ):
        """
        Initialize the overlay scanner.

        Args:
            finnhub_client: FinnhubClient instance for API calls
            strike_optimizer: StrikeOptimizer for probability calculations
            config: Scanner configuration (uses defaults if None)
        """
        self.finnhub_client = finnhub_client
        self.optimizer = strike_optimizer
        self.config = config or ScannerConfig()
        self.earnings_calendar = EarningsCalendar(finnhub_client)

        logger.info(
            f"OverlayScanner initialized with config: "
            f"delta_band={self.config.delta_band.value}, "
            f"overwrite_cap={self.config.overwrite_cap_pct}%"
        )

    def calculate_contracts_to_sell(self, shares: int) -> int:
        """
        Calculate number of contracts to sell based on overwrite cap.

        Formula: floor(shares x overwrite_cap_pct / 100 / 100)

        If result is 0, the holding is non-actionable.

        Args:
            shares: Number of shares held

        Returns:
            Number of contracts to sell (may be 0)
        """
        if shares < 100:
            return 0

        contracts = int(shares * self.config.overwrite_cap_pct / 100 / 100)
        return max(0, contracts)

    def calculate_execution_cost(
        self, bid: float, ask: float, contracts: int = 1
    ) -> ExecutionCostEstimate:
        """
        Calculate estimated execution costs for a trade.

        Args:
            bid: Bid price per share
            ask: Ask price per share
            contracts: Number of contracts (default 1)

        Returns:
            ExecutionCostEstimate with all cost components
        """
        gross_premium = bid * 100 * contracts
        commission = self.config.per_contract_fee * contracts

        # Calculate slippage based on model
        spread = ask - bid
        if self.config.slippage_model == SlippageModel.NONE:
            slippage_per_share = 0
        elif self.config.slippage_model == SlippageModel.FULL_SPREAD:
            slippage_per_share = 0  # Already using bid price
        elif self.config.slippage_model == SlippageModel.HALF_SPREAD:
            slippage_per_share = spread / 2
        else:  # HALF_SPREAD_CAPPED
            slippage_per_share = min(spread / 2, self.config.max_slippage_per_contract)

        slippage = slippage_per_share * 100 * contracts
        net_credit = gross_premium - commission - slippage
        net_credit_per_share = net_credit / (100 * contracts) if contracts > 0 else 0

        return ExecutionCostEstimate(
            gross_premium=gross_premium,
            commission=commission,
            slippage=slippage,
            net_credit=net_credit,
            net_credit_per_share=net_credit_per_share,
        )

    def compute_delta(
        self,
        strike: float,
        current_price: float,
        volatility: float,
        days_to_expiry: int,
        option_type: str = "call",
    ) -> tuple[float, float]:
        """
        Compute Black-Scholes delta and P(ITM) for a strike.

        Args:
            strike: Strike price
            current_price: Current stock price
            volatility: Annualized volatility as decimal
            days_to_expiry: Days until expiration
            option_type: "call" or "put"

        Returns:
            Tuple of (delta, p_itm)
        """
        prob_result = self.optimizer.calculate_assignment_probability(
            strike=strike,
            current_price=current_price,
            volatility=volatility,
            days_to_expiry=max(1, days_to_expiry),
            option_type=option_type,
        )
        return abs(prob_result.delta), prob_result.probability

    def scan_holding(
        self,
        holding: PortfolioHolding,
        current_price: float,
        options_chain: OptionsChain,
        volatility: float,
        override_earnings_check: bool = False,
    ) -> ScanResult:
        """
        Scan a single holding for covered call opportunities.

        Args:
            holding: Portfolio holding to scan
            current_price: Current stock price
            options_chain: Options chain for the symbol
            volatility: Annualized volatility for delta calculations
            override_earnings_check: If True, include earnings-week expirations

        Returns:
            ScanResult with recommendations and rejected strikes
        """
        symbol = holding.symbol
        contracts_available = self.calculate_contracts_to_sell(holding.shares)

        result = ScanResult(
            symbol=symbol,
            current_price=current_price,
            shares_held=holding.shares,
            contracts_available=contracts_available,
        )

        # Check if holding is actionable
        if contracts_available == 0:
            result.error = f"Non-actionable: {holding.shares} shares < 100 shares minimum for 1 contract with {self.config.overwrite_cap_pct}% cap"
            result.warnings.append("Insufficient shares for contract sizing")
            return result

        # Get earnings dates
        earnings_dates = self.earnings_calendar.get_earnings_dates(symbol)
        result.earnings_dates = earnings_dates

        # Get call options
        calls = options_chain.get_calls()
        if not calls:
            result.error = "No call options found in chain"
            return result

        # Get weekly expirations
        expirations = sorted({c.expiration_date for c in calls})[: self.config.weeks_to_scan]

        recommended = []
        rejected = []

        for exp_date in expirations:
            # Check earnings exclusion
            spans_earnings, earn_date = self.earnings_calendar.expiration_spans_earnings(
                symbol, exp_date
            )

            if spans_earnings and not override_earnings_check and self.config.skip_earnings_default:
                result.has_earnings_conflict = True
                logger.info(f"Skipping {exp_date} - spans earnings on {earn_date}")
                continue

            # Calculate days to expiry (calendar days, not trading days)
            days_to_expiry = calculate_days_to_expiry(exp_date, default=7)

            # Get calls for this expiration
            exp_calls = [c for c in calls if c.expiration_date == exp_date]

            for contract in exp_calls:
                # Skip ITM calls
                if contract.strike <= current_price:
                    continue

                # Skip if no bid/ask
                if contract.bid is None or contract.ask is None:
                    continue

                bid = contract.bid or 0
                ask = contract.ask or 0

                if ask <= 0:
                    continue

                mid_price = (bid + ask) / 2
                spread_absolute = ask - bid
                spread_relative_pct = (spread_absolute / mid_price * 100) if mid_price > 0 else 100

                # Compute delta using Black-Scholes model
                delta_model, p_itm_model = self.compute_delta(
                    strike=contract.strike,
                    current_price=current_price,
                    volatility=volatility,
                    days_to_expiry=days_to_expiry,
                    option_type="call",
                )

                # Get chain-provided delta (if available)
                delta_chain = abs(contract.delta) if contract.delta is not None else None
                # P(ITM) approximation from chain delta: |delta| for calls
                p_itm_from_delta = delta_chain if delta_chain is not None else None

                # Primary delta and p_itm use model values (consistent across all strikes)
                delta = delta_model
                p_itm = p_itm_model

                # Compute sigma distance for diagnostic
                try:
                    sigma_distance = self.optimizer.get_sigma_for_strike(
                        strike=contract.strike,
                        current_price=current_price,
                        volatility=volatility,
                        days_to_expiry=days_to_expiry,
                        option_type="call",
                    )
                except (ValueError, ZeroDivisionError):
                    sigma_distance = None

                # Get delta band
                delta_band = get_delta_band(delta)

                # Calculate execution cost
                cost_estimate = self.calculate_execution_cost(
                    bid=bid, ask=ask, contracts=contracts_available
                )

                # Calculate annualized yield
                position_value = current_price * 100 * contracts_available
                if position_value > 0 and days_to_expiry > 0:
                    annualized_yield = (
                        (cost_estimate.net_credit / position_value) * (365 / days_to_expiry) * 100
                    )
                else:
                    annualized_yield = 0

                candidate = CandidateStrike(
                    contract=contract,
                    strike=contract.strike,
                    expiration_date=exp_date,
                    delta=delta,
                    p_itm=p_itm,
                    sigma_distance=sigma_distance,
                    bid=bid,
                    ask=ask,
                    mid_price=mid_price,
                    spread_absolute=spread_absolute,
                    spread_relative_pct=spread_relative_pct,
                    open_interest=contract.open_interest or 0,
                    volume=contract.volume or 0,
                    cost_estimate=cost_estimate,
                    delta_band=delta_band,
                    contracts_to_sell=contracts_available,
                    total_net_credit=cost_estimate.net_credit,
                    annualized_yield_pct=annualized_yield,
                    days_to_expiry=days_to_expiry,
                    delta_model=delta_model,
                    p_itm_model=p_itm_model,
                    delta_chain=delta_chain,
                    p_itm_from_delta=p_itm_from_delta,
                )

                # Apply tradability filters (returns tuple of reasons and details)
                rejection_reasons, rejection_details = apply_tradability_filters(
                    candidate, self.config, current_price
                )

                # Check delta band filter
                delta_detail = apply_delta_band_filter(candidate, self.config)
                if delta_detail:
                    rejection_reasons.append(RejectionReason.OUTSIDE_DELTA_BAND)
                    rejection_details.append(delta_detail)

                # Check earnings if applicable
                if spans_earnings:
                    rejection_reasons.append(RejectionReason.EARNINGS_WEEK)
                    rejection_details.append(
                        RejectionDetail(
                            reason=RejectionReason.EARNINGS_WEEK,
                            actual_value=1.0,
                            threshold=0.0,
                            margin=1.0,  # Hard gate - no partial margin
                            margin_display=f"earnings on {earn_date} before {exp_date}",
                        )
                    )
                    candidate.warnings.append(f"Expiration spans earnings on {earn_date}")

                if rejection_reasons:
                    candidate.rejection_reasons = rejection_reasons
                    candidate.rejection_details = rejection_details
                    candidate.is_recommended = False
                    rejected.append(candidate)
                else:
                    recommended.append(candidate)

        # Sort recommended by net credit (highest first)
        recommended.sort(key=lambda c: c.total_net_credit, reverse=True)

        # Calculate near-miss scores for rejected candidates
        max_net_credit = max((c.total_net_credit for c in rejected), default=100.0) or 100.0

        for candidate in rejected:
            populate_near_miss_details(candidate, max_net_credit)

        # Get top 5 near-miss candidates (sorted by score, highest first)
        near_misses = sorted(rejected, key=lambda c: c.near_miss_score, reverse=True)[:5]

        result.recommended_strikes = recommended
        result.rejected_strikes = rejected
        result.near_miss_candidates = near_misses

        # Generate broker checklist and LLM memo for top recommendation
        if recommended:
            top = recommended[0]
            earnings_clear = not result.has_earnings_conflict

            result.broker_checklist = generate_broker_checklist(
                symbol=symbol,
                candidate=top,
                config=self.config,
                earnings_clear=earnings_clear,
                dividend_verified=False,
            )

            earnings_status = "CLEAR" if earnings_clear else "UNVERIFIED"
            dividend_status = "UNVERIFIED"

            result.llm_memo_payload = generate_llm_memo_payload(
                symbol=symbol,
                current_price=current_price,
                holding=holding,
                candidate=top,
                config=self.config,
                earnings_status=earnings_status,
                dividend_status=dividend_status,
            )

        logger.info(
            f"Scanned {symbol}: {len(recommended)} recommended, "
            f"{len(rejected)} rejected, contracts={contracts_available}"
        )

        return result

    def scan_portfolio(
        self,
        holdings: list[PortfolioHolding],
        current_prices: dict[str, float],
        options_chains: dict[str, OptionsChain],
        volatilities: dict[str, float],
        override_earnings_check: bool = False,
    ) -> dict[str, ScanResult]:
        """
        Scan entire portfolio for covered call opportunities.

        Args:
            holdings: List of portfolio holdings
            current_prices: Map of symbol -> current price
            options_chains: Map of symbol -> options chain
            volatilities: Map of symbol -> annualized volatility
            override_earnings_check: If True, include earnings-week expirations

        Returns:
            Dictionary mapping symbol to ScanResult
        """
        results = {}

        for holding in holdings:
            symbol = holding.symbol

            # Check if we have required data
            if symbol not in current_prices:
                results[symbol] = ScanResult(
                    symbol=symbol,
                    current_price=0,
                    shares_held=holding.shares,
                    contracts_available=0,
                    error=f"No price data for {symbol}",
                )
                continue

            if symbol not in options_chains:
                results[symbol] = ScanResult(
                    symbol=symbol,
                    current_price=current_prices[symbol],
                    shares_held=holding.shares,
                    contracts_available=0,
                    error=f"No options chain for {symbol}",
                )
                continue

            if symbol not in volatilities:
                results[symbol] = ScanResult(
                    symbol=symbol,
                    current_price=current_prices[symbol],
                    shares_held=holding.shares,
                    contracts_available=0,
                    error=f"No volatility data for {symbol}",
                )
                continue

            # Scan the holding
            result = self.scan_holding(
                holding=holding,
                current_price=current_prices[symbol],
                options_chain=options_chains[symbol],
                volatility=volatilities[symbol],
                override_earnings_check=override_earnings_check,
            )

            results[symbol] = result

        logger.info(f"Scanned {len(holdings)} holdings, {len(results)} results")
        return results

    def generate_trade_blotter(
        self, scan_results: dict[str, ScanResult], top_n: int = 3
    ) -> list[dict[str, Any]]:
        """
        Generate a trade blotter from scan results.

        The blotter shows the top N recommendations per symbol,
        ranked by net credit.

        Args:
            scan_results: Dictionary of scan results
            top_n: Maximum recommendations per symbol

        Returns:
            List of trade entries for the blotter
        """
        blotter = []

        for symbol, result in scan_results.items():
            if result.error:
                blotter.append(
                    {
                        "symbol": symbol,
                        "status": "ERROR",
                        "error": result.error,
                        "recommendations": [],
                    }
                )
                continue

            if not result.recommended_strikes:
                blotter.append(
                    {
                        "symbol": symbol,
                        "status": "NO_RECOMMENDATIONS",
                        "rejected_count": len(result.rejected_strikes),
                        "recommendations": [],
                    }
                )
                continue

            recommendations = []
            for strike in result.recommended_strikes[:top_n]:
                recommendations.append(
                    {
                        "strike": strike.strike,
                        "expiration": strike.expiration_date,
                        "contracts": strike.contracts_to_sell,
                        "net_credit": round(strike.total_net_credit, 2),
                        "delta": round(strike.delta, 3),
                        "annualized_yield_pct": round(strike.annualized_yield_pct, 2),
                        "delta_band": strike.delta_band.value if strike.delta_band else None,
                    }
                )

            blotter.append(
                {
                    "symbol": symbol,
                    "status": "OK",
                    "current_price": round(result.current_price, 2),
                    "shares": result.shares_held,
                    "contracts_available": result.contracts_available,
                    "earnings_clear": not result.has_earnings_conflict,
                    "recommendations": recommendations,
                    "broker_checklist": result.broker_checklist.to_dict()
                    if result.broker_checklist
                    else None,
                }
            )

        # Sort by total potential net credit
        blotter.sort(
            key=lambda x: x.get("recommendations", [{}])[0].get("net_credit", 0)
            if x.get("recommendations")
            else 0,
            reverse=True,
        )

        return blotter
