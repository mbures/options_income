"""
Filtering functions for the overlay scanner.

This module provides functions for filtering candidate strikes based on
tradability criteria, delta bands, and risk constraints.
"""

import logging
from typing import Optional

from src.models import (
    DELTA_BAND_RANGES,
    CandidateStrike,
    DeltaBand,
    RejectionDetail,
    RejectionReason,
    ScannerConfig,
)

logger = logging.getLogger(__name__)


def get_delta_band(delta: float) -> Optional[DeltaBand]:
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


def calculate_margin(
    actual: float, threshold: float, constraint_type: str
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
    candidate: CandidateStrike, config: ScannerConfig, current_price: float = 0.0
) -> tuple[list[RejectionReason], list[RejectionDetail]]:
    """
    Apply tradability filters to a candidate strike.

    Args:
        candidate: CandidateStrike to filter
        config: ScannerConfig with filter thresholds
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
    elif candidate.bid < config.min_bid_price:
        margin, display = calculate_margin(
            candidate.bid, config.min_bid_price, "min"
        )
        reasons.append(RejectionReason.LOW_PREMIUM)
        details.append(
            RejectionDetail(
                reason=RejectionReason.LOW_PREMIUM,
                actual_value=candidate.bid,
                threshold=config.min_bid_price,
                margin=margin,
                margin_display=f"bid={display}",
            )
        )

    # Spread absolute filter (PRIMARY - always checked)
    if candidate.spread_absolute > config.max_spread_absolute:
        margin, display = calculate_margin(
            candidate.spread_absolute, config.max_spread_absolute, "max"
        )
        reasons.append(RejectionReason.WIDE_SPREAD_ABSOLUTE)
        details.append(
            RejectionDetail(
                reason=RejectionReason.WIDE_SPREAD_ABSOLUTE,
                actual_value=candidate.spread_absolute,
                threshold=config.max_spread_absolute,
                margin=margin,
                margin_display=f"spread=${candidate.spread_absolute:.2f} vs ${config.max_spread_absolute:.2f}",
            )
        )

    # Spread relative filter (SECONDARY - only for mid >= threshold)
    if candidate.mid_price >= config.min_mid_for_relative_spread:
        if candidate.spread_relative_pct > config.max_spread_relative_pct:
            margin, display = calculate_margin(
                candidate.spread_relative_pct, config.max_spread_relative_pct, "max"
            )
            reasons.append(RejectionReason.WIDE_SPREAD_RELATIVE)
            details.append(
                RejectionDetail(
                    reason=RejectionReason.WIDE_SPREAD_RELATIVE,
                    actual_value=candidate.spread_relative_pct,
                    threshold=config.max_spread_relative_pct,
                    margin=margin,
                    margin_display=f"spread%={candidate.spread_relative_pct:.1f}% vs {config.max_spread_relative_pct:.1f}% (mid=${candidate.mid_price:.2f})",
                )
            )

    # Open interest filter
    if candidate.open_interest < config.min_open_interest:
        margin, display = calculate_margin(
            candidate.open_interest, config.min_open_interest, "min"
        )
        reasons.append(RejectionReason.LOW_OPEN_INTEREST)
        details.append(
            RejectionDetail(
                reason=RejectionReason.LOW_OPEN_INTEREST,
                actual_value=candidate.open_interest,
                threshold=config.min_open_interest,
                margin=margin,
                margin_display=f"OI={int(candidate.open_interest)} vs {int(config.min_open_interest)}",
            )
        )

    # Volume filter
    if candidate.volume < config.min_volume:
        margin, display = calculate_margin(
            candidate.volume, config.min_volume, "min"
        )
        reasons.append(RejectionReason.LOW_VOLUME)
        details.append(
            RejectionDetail(
                reason=RejectionReason.LOW_VOLUME,
                actual_value=candidate.volume,
                threshold=config.min_volume,
                margin=margin,
                margin_display=f"vol={int(candidate.volume)} vs {int(config.min_volume)}",
            )
        )

    # Yield-based filter: net_credit / notional >= min_weekly_yield_bps
    if current_price > 0:
        notional_per_contract = current_price * 100
        # Use net_credit_per_share * 100 to get true per-contract credit
        net_credit_per_contract = candidate.cost_estimate.net_credit_per_share * 100
        actual_yield_bps = (net_credit_per_contract / notional_per_contract) * 10000

        if actual_yield_bps < config.min_weekly_yield_bps:
            margin, _ = calculate_margin(
                actual_yield_bps, config.min_weekly_yield_bps, "min"
            )
            min_credit_for_yield = (
                config.min_weekly_yield_bps / 10000
            ) * notional_per_contract
            reasons.append(RejectionReason.YIELD_TOO_LOW)
            details.append(
                RejectionDetail(
                    reason=RejectionReason.YIELD_TOO_LOW,
                    actual_value=actual_yield_bps,
                    threshold=config.min_weekly_yield_bps,
                    margin=margin,
                    margin_display=f"yield={actual_yield_bps:.1f}bps vs {config.min_weekly_yield_bps:.1f}bps (need ${min_credit_for_yield:.2f})",
                )
            )

    # Friction floor: net_credit >= min_friction_multiple * (commission + slippage)
    friction_cost = candidate.cost_estimate.commission + candidate.cost_estimate.slippage
    min_credit_for_friction = config.min_friction_multiple * friction_cost
    net_credit = candidate.cost_estimate.net_credit

    if net_credit < min_credit_for_friction:
        margin, _ = calculate_margin(net_credit, min_credit_for_friction, "min")
        reasons.append(RejectionReason.FRICTION_TOO_HIGH)
        details.append(
            RejectionDetail(
                reason=RejectionReason.FRICTION_TOO_HIGH,
                actual_value=net_credit,
                threshold=min_credit_for_friction,
                margin=margin,
                margin_display=f"net=${net_credit:.2f} vs {config.min_friction_multiple:.1f}x friction (${min_credit_for_friction:.2f})",
            )
        )

    return reasons, details


def apply_delta_band_filter(candidate: CandidateStrike, config: ScannerConfig) -> Optional[RejectionDetail]:
    """
    Check if candidate delta is within the configured delta band.

    Args:
        candidate: CandidateStrike to check
        config: ScannerConfig with delta band settings

    Returns:
        RejectionDetail if outside band, None if within band
    """
    target_band = config.delta_band
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
    candidate: CandidateStrike, max_net_credit: float = 100.0
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
    candidate: CandidateStrike, max_net_credit: float = 100.0
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
    candidate.near_miss_score = calculate_near_miss_score(candidate, max_net_credit)
