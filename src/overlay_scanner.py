"""
Weekly Overlay Scanner for covered call strategies.

This module provides a holdings-driven scanner for generating weekly covered
call recommendations with:
- Portfolio holdings input with overwrite cap sizing (FR-42, FR-43)
- Earnings week exclusion as hard gate (FR-45)
- Execution cost model with fees and slippage (FR-44)
- Delta-band risk profiles for weekly selection (FR-47)
- Tradability filters (FR-49)
- Broker checklist and LLM memo payload output (FR-50)

The scanner is designed for a broker-first workflow where the system generates
recommendations and the user executes trades manually at their broker.

Example:
    from src.overlay_scanner import OverlayScanner
    from src.models import PortfolioHolding, ScannerConfig

    holdings = [
        PortfolioHolding(symbol="AAPL", shares=500),
        PortfolioHolding(symbol="MSFT", shares=300),
    ]

    scanner = OverlayScanner(
        finnhub_client=finnhub_client,
        strike_optimizer=optimizer,
        config=ScannerConfig()
    )

    results = scanner.scan_portfolio(holdings, current_prices)
"""

import logging
from datetime import datetime
from typing import Any, Optional

from .earnings_calendar import EarningsCalendar
from .models import (
    DELTA_BAND_RANGES,
    BrokerChecklist,
    CandidateStrike,
    DeltaBand,
    ExecutionCostEstimate,
    LLMMemoPayload,
    OptionsChain,
    PortfolioHolding,
    RejectionDetail,
    RejectionReason,
    ScannerConfig,
    ScanResult,
    SlippageModel,
)
from .strike_optimizer import StrikeOptimizer
from .utils import calculate_days_to_expiry

logger = logging.getLogger(__name__)


# Re-export commonly used types for backward compatibility
__all__ = [
    "OverlayScanner",
    "EarningsCalendar",
    # Models (re-exported for convenience)
    "DeltaBand",
    "DELTA_BAND_RANGES",
    "SlippageModel",
    "RejectionReason",
    "RejectionDetail",
    "PortfolioHolding",
    "ScannerConfig",
    "ExecutionCostEstimate",
    "CandidateStrike",
    "BrokerChecklist",
    "LLMMemoPayload",
    "ScanResult",
]


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

    def get_delta_band(self, delta: float) -> Optional[DeltaBand]:
        """
        Determine which delta band a given delta falls into.

        Args:
            delta: Option delta (absolute value)

        Returns:
            DeltaBand or None if outside all bands
        """
        delta = abs(delta)
        for band, (min_d, max_d) in DELTA_BAND_RANGES.items():
            if min_d <= delta < max_d:
                return band
        return None

    def _calculate_margin(
        self, actual: float, threshold: float, constraint_type: str
    ) -> tuple[float, str]:
        """
        Calculate normalized margin from threshold.

        Args:
            actual: Actual value
            threshold: Threshold value
            constraint_type: 'min' (actual must be >= threshold) or 'max' (actual must be <= threshold)

        Returns:
            Tuple of (margin, display_string)
            margin: 0 = at threshold, higher = further from passing
        """
        if constraint_type == "min":
            # For minimum constraints: need actual >= threshold
            if threshold == 0:
                margin = 1.0 if actual <= 0 else 0.0
            else:
                gap = threshold - actual
                margin = max(0, gap / threshold)
            shortfall = threshold - actual
            display = f"{actual:.2f} vs {threshold:.2f} (need +{shortfall:.2f})"
        else:  # max
            # For maximum constraints: need actual <= threshold
            if threshold == 0:
                margin = 1.0 if actual > 0 else 0.0
            else:
                excess = actual - threshold
                margin = max(0, excess / threshold)
            excess = actual - threshold
            display = f"{actual:.2f} vs {threshold:.2f} (excess {excess:.2f})"

        return margin, display

    def apply_tradability_filters(
        self, candidate: CandidateStrike, current_price: float = 0.0
    ) -> tuple[list[RejectionReason], list[RejectionDetail]]:
        """
        Apply tradability filters to a candidate strike.

        Args:
            candidate: CandidateStrike to filter
            current_price: Current stock price (for yield calculations)

        Returns:
            Tuple of (rejection_reasons, rejection_details)
            - rejection_reasons: List of RejectionReason enums
            - rejection_details: List of RejectionDetail with margin info
        """
        reasons = []
        details = []

        # Zero bid filter
        if candidate.bid <= 0:
            reasons.append(RejectionReason.ZERO_BID)
            details.append(
                RejectionDetail(
                    reason=RejectionReason.ZERO_BID,
                    actual_value=candidate.bid,
                    threshold=0.01,
                    margin=1.0,
                    margin_display=f"bid=${candidate.bid:.2f} (no market)",
                )
            )

        # Low premium filter
        elif candidate.bid < self.config.min_bid_price:
            margin, display = self._calculate_margin(
                candidate.bid, self.config.min_bid_price, "min"
            )
            reasons.append(RejectionReason.LOW_PREMIUM)
            details.append(
                RejectionDetail(
                    reason=RejectionReason.LOW_PREMIUM,
                    actual_value=candidate.bid,
                    threshold=self.config.min_bid_price,
                    margin=margin,
                    margin_display=f"bid={display}",
                )
            )

        # Spread absolute filter (PRIMARY - always checked)
        if candidate.spread_absolute > self.config.max_spread_absolute:
            margin, display = self._calculate_margin(
                candidate.spread_absolute, self.config.max_spread_absolute, "max"
            )
            reasons.append(RejectionReason.WIDE_SPREAD_ABSOLUTE)
            details.append(
                RejectionDetail(
                    reason=RejectionReason.WIDE_SPREAD_ABSOLUTE,
                    actual_value=candidate.spread_absolute,
                    threshold=self.config.max_spread_absolute,
                    margin=margin,
                    margin_display=f"spread=${candidate.spread_absolute:.2f} vs ${self.config.max_spread_absolute:.2f}",
                )
            )

        # Spread relative filter (SECONDARY - only for mid >= threshold)
        if candidate.mid_price >= self.config.min_mid_for_relative_spread:
            if candidate.spread_relative_pct > self.config.max_spread_relative_pct:
                margin, display = self._calculate_margin(
                    candidate.spread_relative_pct, self.config.max_spread_relative_pct, "max"
                )
                reasons.append(RejectionReason.WIDE_SPREAD_RELATIVE)
                details.append(
                    RejectionDetail(
                        reason=RejectionReason.WIDE_SPREAD_RELATIVE,
                        actual_value=candidate.spread_relative_pct,
                        threshold=self.config.max_spread_relative_pct,
                        margin=margin,
                        margin_display=f"spread%={candidate.spread_relative_pct:.1f}% vs {self.config.max_spread_relative_pct:.1f}% (mid=${candidate.mid_price:.2f})",
                    )
                )

        # Open interest filter
        if candidate.open_interest < self.config.min_open_interest:
            margin, display = self._calculate_margin(
                candidate.open_interest, self.config.min_open_interest, "min"
            )
            reasons.append(RejectionReason.LOW_OPEN_INTEREST)
            details.append(
                RejectionDetail(
                    reason=RejectionReason.LOW_OPEN_INTEREST,
                    actual_value=candidate.open_interest,
                    threshold=self.config.min_open_interest,
                    margin=margin,
                    margin_display=f"OI={int(candidate.open_interest)} vs {int(self.config.min_open_interest)}",
                )
            )

        # Volume filter
        if candidate.volume < self.config.min_volume:
            margin, display = self._calculate_margin(
                candidate.volume, self.config.min_volume, "min"
            )
            reasons.append(RejectionReason.LOW_VOLUME)
            details.append(
                RejectionDetail(
                    reason=RejectionReason.LOW_VOLUME,
                    actual_value=candidate.volume,
                    threshold=self.config.min_volume,
                    margin=margin,
                    margin_display=f"vol={int(candidate.volume)} vs {int(self.config.min_volume)}",
                )
            )

        # Yield-based filter: net_credit / notional >= min_weekly_yield_bps
        if current_price > 0:
            notional_per_contract = current_price * 100
            net_credit_per_contract = candidate.cost_estimate.net_credit
            actual_yield_bps = (net_credit_per_contract / notional_per_contract) * 10000

            if actual_yield_bps < self.config.min_weekly_yield_bps:
                margin, _ = self._calculate_margin(
                    actual_yield_bps, self.config.min_weekly_yield_bps, "min"
                )
                min_credit_for_yield = (
                    self.config.min_weekly_yield_bps / 10000
                ) * notional_per_contract
                reasons.append(RejectionReason.YIELD_TOO_LOW)
                details.append(
                    RejectionDetail(
                        reason=RejectionReason.YIELD_TOO_LOW,
                        actual_value=actual_yield_bps,
                        threshold=self.config.min_weekly_yield_bps,
                        margin=margin,
                        margin_display=f"yield={actual_yield_bps:.1f}bps vs {self.config.min_weekly_yield_bps:.1f}bps (need ${min_credit_for_yield:.2f})",
                    )
                )

        # Friction floor: net_credit >= min_friction_multiple * (commission + slippage)
        friction_cost = candidate.cost_estimate.commission + candidate.cost_estimate.slippage
        min_credit_for_friction = self.config.min_friction_multiple * friction_cost
        net_credit = candidate.cost_estimate.net_credit

        if net_credit < min_credit_for_friction:
            margin, _ = self._calculate_margin(net_credit, min_credit_for_friction, "min")
            reasons.append(RejectionReason.FRICTION_TOO_HIGH)
            details.append(
                RejectionDetail(
                    reason=RejectionReason.FRICTION_TOO_HIGH,
                    actual_value=net_credit,
                    threshold=min_credit_for_friction,
                    margin=margin,
                    margin_display=f"net=${net_credit:.2f} vs {self.config.min_friction_multiple:.1f}x friction (${min_credit_for_friction:.2f})",
                )
            )

        return reasons, details

    def apply_delta_band_filter(self, candidate: CandidateStrike) -> Optional[RejectionDetail]:
        """
        Check if candidate delta is within the configured delta band.

        Args:
            candidate: CandidateStrike to check

        Returns:
            RejectionDetail if outside band, None if within band
        """
        target_band = self.config.delta_band
        min_delta, max_delta = DELTA_BAND_RANGES[target_band]
        delta = abs(candidate.delta)

        if min_delta <= delta < max_delta:
            return None  # Passes filter

        # Calculate margin - how far from the band edges
        if delta < min_delta:
            gap = min_delta - delta
            margin = gap / min_delta if min_delta > 0 else 1.0
            margin_display = f"delta={delta:.3f} < {min_delta:.2f} (need +{gap:.3f})"
        else:  # delta >= max_delta
            gap = delta - max_delta
            margin = gap / max_delta if max_delta > 0 else 1.0
            margin_display = f"delta={delta:.3f} > {max_delta:.2f} (excess {gap:.3f})"

        return RejectionDetail(
            reason=RejectionReason.OUTSIDE_DELTA_BAND,
            actual_value=delta,
            threshold=min_delta if delta < min_delta else max_delta,
            margin=margin,
            margin_display=margin_display,
        )

    def calculate_near_miss_score(
        self, candidate: CandidateStrike, max_net_credit: float = 100.0
    ) -> float:
        """
        Calculate near-miss score for a rejected candidate.

        Higher score = closer to being recommended.
        Score combines:
        - Net credit potential (normalized, weight 0.6)
        - Inverse of rejection count (weight 0.2)
        - Inverse of minimum margin (weight 0.2)

        Args:
            candidate: Rejected CandidateStrike with rejection_details populated
            max_net_credit: Maximum expected net credit for normalization

        Returns:
            Near-miss score (0.0 to 1.0, higher = closer to passing)
        """
        if not candidate.rejection_details:
            return 1.0  # No rejections = perfect score

        # Net credit component (0-0.6): higher credit = better
        credit_score = min(1.0, candidate.total_net_credit / max_net_credit) * 0.6

        # Rejection count component (0-0.2): fewer rejections = better
        num_rejections = len(candidate.rejection_details)
        rejection_penalty = max(0, 1.0 - (num_rejections - 1) * 0.25)
        rejection_score = rejection_penalty * 0.2

        # Minimum margin component (0-0.2): smaller margin = closer to passing
        min_margin = min(d.margin for d in candidate.rejection_details)
        margin_score = max(0, 1.0 - min_margin) * 0.2

        return credit_score + rejection_score + margin_score

    def populate_near_miss_details(
        self, candidate: CandidateStrike, max_net_credit: float = 100.0
    ) -> None:
        """
        Populate near-miss analysis fields on a rejected candidate.

        Sets:
        - rejection_details (already set by caller)
        - binding_constraint (constraint with smallest margin)
        - near_miss_score (weighted score)

        Args:
            candidate: CandidateStrike with rejection_details already populated
            max_net_credit: Maximum expected net credit for normalization
        """
        if not candidate.rejection_details:
            return

        # Find binding constraint (smallest margin)
        candidate.binding_constraint = min(candidate.rejection_details, key=lambda d: d.margin)

        # Calculate near-miss score
        candidate.near_miss_score = self.calculate_near_miss_score(candidate, max_net_credit)

    def generate_broker_checklist(
        self,
        symbol: str,
        candidate: CandidateStrike,
        earnings_clear: bool,
        dividend_verified: bool = False,
    ) -> BrokerChecklist:
        """
        Generate a broker checklist for a recommended trade.

        Args:
            symbol: Stock symbol
            candidate: The recommended strike
            earnings_clear: Whether earnings have been verified clear
            dividend_verified: Whether dividend has been verified

        Returns:
            BrokerChecklist for the trade
        """
        checks = [
            f"Verify current bid >= ${candidate.bid:.2f}",
            f"Verify spread <= ${self.config.max_spread_absolute:.2f} or {self.config.max_spread_relative_pct:.0f}%",
            f"Verify open interest >= {self.config.min_open_interest}",
            f"Confirm {candidate.contracts_to_sell} contracts x ${candidate.strike} strike",
            f"Expected net credit: ${candidate.total_net_credit:.2f}",
        ]

        if earnings_clear:
            checks.append("Earnings: CLEAR (no earnings before expiration)")
        else:
            checks.append("Earnings: VERIFY at broker (data may be stale)")

        if dividend_verified:
            checks.append("Dividend: VERIFIED (no ex-div before expiration)")
        else:
            checks.append("Dividend: UNVERIFIED (check for early exercise risk)")

        warnings = list(candidate.warnings)
        if not dividend_verified:
            warnings.append("Dividend data unverified - check at broker")

        return BrokerChecklist(
            symbol=symbol,
            action="SELL TO OPEN",
            contracts=candidate.contracts_to_sell,
            strike=candidate.strike,
            expiration=candidate.expiration_date,
            option_type="CALL",
            limit_price=candidate.mid_price,
            min_acceptable_credit=candidate.bid,
            checks=checks,
            warnings=warnings,
        )

    def generate_llm_memo_payload(
        self,
        symbol: str,
        current_price: float,
        holding: PortfolioHolding,
        candidate: CandidateStrike,
        earnings_status: str,
        dividend_status: str,
    ) -> LLMMemoPayload:
        """
        Generate structured payload for LLM decision memo.

        Args:
            symbol: Stock symbol
            current_price: Current stock price
            holding: Portfolio holding info
            candidate: Recommended strike
            earnings_status: Earnings verification status
            dividend_status: Dividend verification status

        Returns:
            LLMMemoPayload for memo generation
        """
        holding_dict = {
            "symbol": holding.symbol,
            "shares": holding.shares,
            "cost_basis": holding.cost_basis,
            "acquired_date": holding.acquired_date,
            "account_type": holding.account_type,
        }

        return LLMMemoPayload(
            symbol=symbol,
            current_price=current_price,
            shares_held=holding.shares,
            contracts_to_write=candidate.contracts_to_sell,
            candidate=candidate.to_dict(),
            holding=holding_dict,
            risk_profile=self.config.delta_band.value,
            earnings_status=earnings_status,
            dividend_status=dividend_status,
            account_type=holding.account_type,
            timestamp=datetime.now().isoformat(),
        )

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

                # Compute delta using Black-Scholes
                delta, p_itm = self.compute_delta(
                    strike=contract.strike,
                    current_price=current_price,
                    volatility=volatility,
                    days_to_expiry=days_to_expiry,
                    option_type="call",
                )

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
                delta_band = self.get_delta_band(delta)

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
                )

                # Apply tradability filters (returns tuple of reasons and details)
                rejection_reasons, rejection_details = self.apply_tradability_filters(
                    candidate, current_price
                )

                # Check delta band filter
                delta_detail = self.apply_delta_band_filter(candidate)
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
            self.populate_near_miss_details(candidate, max_net_credit)

        # Get top 5 near-miss candidates (sorted by score, highest first)
        near_misses = sorted(rejected, key=lambda c: c.near_miss_score, reverse=True)[:5]

        result.recommended_strikes = recommended
        result.rejected_strikes = rejected
        result.near_miss_candidates = near_misses

        # Generate broker checklist and LLM memo for top recommendation
        if recommended:
            top = recommended[0]
            earnings_clear = not result.has_earnings_conflict

            result.broker_checklist = self.generate_broker_checklist(
                symbol=symbol,
                candidate=top,
                earnings_clear=earnings_clear,
                dividend_verified=False,
            )

            earnings_status = "CLEAR" if earnings_clear else "UNVERIFIED"
            dividend_status = "UNVERIFIED"

            result.llm_memo_payload = self.generate_llm_memo_payload(
                symbol=symbol,
                current_price=current_price,
                holding=holding,
                candidate=top,
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
