"""Strategy result dataclasses for covered calls and puts."""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .base import OptionContract
    from .profiles import StrikeProfile


class WheelState(Enum):
    """
    Current state in the wheel strategy cycle.

    The wheel strategy alternates between:
    - CASH: No shares owned, sell cash-secured puts to potentially acquire
    - SHARES: Shares owned (from assignment), sell covered calls to exit or collect premium
    """

    CASH = "cash"  # Ready to sell puts
    SHARES = "shares"  # Ready to sell calls


@dataclass
class CoveredCallResult:
    """
    Result of a covered call analysis.

    Attributes:
        contract: The call option contract analyzed
        current_price: Stock price at time of analysis
        shares: Number of shares covered (typically 100 per contract)
        premium_per_share: Premium received per share (bid price)
        total_premium: Total premium for all shares
        max_profit: Maximum profit if called away (premium + appreciation)
        max_profit_pct: Maximum profit as percentage of stock value
        breakeven: Stock price at breakeven (current - premium)
        profit_if_flat: Profit if stock unchanged at expiry
        profit_if_flat_pct: Flat profit as percentage
        assignment_probability: Probability of being called away
        days_to_expiry: Days until expiration
        annualized_return_if_flat: Annualized return if not called
        annualized_return_if_called: Annualized return if called
        sigma_distance: Distance from current price in sigmas
        profile: Risk profile this strike fits
        warnings: List of warning messages
    """

    contract: "OptionContract"
    current_price: float
    shares: int
    premium_per_share: float
    total_premium: float
    max_profit: float
    max_profit_pct: float
    breakeven: float
    profit_if_flat: float
    profit_if_flat_pct: float
    assignment_probability: Optional[float]
    days_to_expiry: int
    annualized_return_if_flat: float
    annualized_return_if_called: float
    sigma_distance: Optional[float]
    profile: Optional["StrikeProfile"]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "strike": self.contract.strike,
            "expiration_date": self.contract.expiration_date,
            "current_price": self.current_price,
            "shares": self.shares,
            "premium_per_share": round(self.premium_per_share, 4),
            "total_premium": round(self.total_premium, 2),
            "max_profit": round(self.max_profit, 2),
            "max_profit_pct": round(self.max_profit_pct, 2),
            "breakeven": round(self.breakeven, 4),
            "profit_if_flat": round(self.profit_if_flat, 2),
            "profit_if_flat_pct": round(self.profit_if_flat_pct, 2),
            "assignment_probability_pct": round(self.assignment_probability * 100, 2)
            if self.assignment_probability
            else None,
            "days_to_expiry": self.days_to_expiry,
            "annualized_return_if_flat_pct": round(self.annualized_return_if_flat * 100, 2),
            "annualized_return_if_called_pct": round(self.annualized_return_if_called * 100, 2),
            "sigma_distance": round(self.sigma_distance, 2) if self.sigma_distance else None,
            "profile": self.profile.value if self.profile else None,
            "warnings": self.warnings,
        }


@dataclass
class CoveredPutResult:
    """
    Result of a cash-secured put analysis.

    Attributes:
        contract: The put option contract analyzed
        current_price: Stock price at time of analysis
        premium_per_share: Premium received per share (bid price)
        total_premium: Total premium for contract
        collateral_required: Cash required to secure the put (strike x 100)
        effective_purchase_price: Net cost if assigned (strike - premium)
        discount_from_current: Percentage discount from current price if assigned
        max_profit: Maximum profit if OTM at expiry (premium)
        max_profit_pct: Max profit as percentage of collateral
        max_loss: Maximum loss if stock goes to zero
        breakeven: Stock price at breakeven (strike - premium)
        profit_if_flat: Profit if stock unchanged at expiry (premium)
        profit_if_flat_pct: Flat profit as percentage of collateral
        assignment_probability: Probability of being assigned
        days_to_expiry: Days until expiration
        annualized_return_if_otm: Annualized return if not assigned
        sigma_distance: Distance from current price in sigmas
        profile: Risk profile this strike fits
        warnings: List of warning messages
    """

    contract: "OptionContract"
    current_price: float
    premium_per_share: float
    total_premium: float
    collateral_required: float
    effective_purchase_price: float
    discount_from_current: float
    max_profit: float
    max_profit_pct: float
    max_loss: float
    breakeven: float
    profit_if_flat: float
    profit_if_flat_pct: float
    assignment_probability: Optional[float]
    days_to_expiry: int
    annualized_return_if_otm: float
    sigma_distance: Optional[float]
    profile: Optional["StrikeProfile"]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "strike": self.contract.strike,
            "expiration_date": self.contract.expiration_date,
            "current_price": self.current_price,
            "premium_per_share": round(self.premium_per_share, 4),
            "total_premium": round(self.total_premium, 2),
            "collateral_required": round(self.collateral_required, 2),
            "effective_purchase_price": round(self.effective_purchase_price, 4),
            "discount_from_current_pct": round(self.discount_from_current * 100, 2),
            "max_profit": round(self.max_profit, 2),
            "max_profit_pct": round(self.max_profit_pct, 2),
            "max_loss": round(self.max_loss, 2),
            "breakeven": round(self.breakeven, 4),
            "profit_if_flat": round(self.profit_if_flat, 2),
            "profit_if_flat_pct": round(self.profit_if_flat_pct, 2),
            "assignment_probability_pct": round(self.assignment_probability * 100, 2)
            if self.assignment_probability
            else None,
            "days_to_expiry": self.days_to_expiry,
            "annualized_return_if_otm_pct": round(self.annualized_return_if_otm * 100, 2),
            "sigma_distance": round(self.sigma_distance, 2) if self.sigma_distance else None,
            "profile": self.profile.value if self.profile else None,
            "warnings": self.warnings,
        }


@dataclass
class WheelRecommendation:
    """
    Recommendation for wheel strategy action.

    Attributes:
        state: Current wheel state (CASH or SHARES)
        action: Recommended action ("sell_put" or "sell_call")
        analysis: The analysis result (CoveredCallResult or CoveredPutResult)
        rationale: Explanation of the recommendation
    """

    state: WheelState
    action: str
    analysis: Any  # CoveredCallResult or CoveredPutResult
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "state": self.state.value,
            "action": self.action,
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "rationale": self.rationale,
        }


@dataclass
class WheelCycleMetrics:
    """
    Metrics for tracking a complete wheel cycle.

    Attributes:
        total_premium_collected: Sum of all premiums from puts and calls
        num_put_cycles: Number of puts sold
        num_call_cycles: Number of calls sold
        shares_acquired_price: Price paid when assigned on put (None if not assigned)
        shares_sold_price: Price received when called away (None if not called)
        average_cost_basis: Adjusted cost basis after premiums
        net_profit: Total profit/loss for the cycle
        cycle_complete: Whether the cycle is complete (shares sold)
    """

    total_premium_collected: float = 0.0
    num_put_cycles: int = 0
    num_call_cycles: int = 0
    shares_acquired_price: Optional[float] = None
    shares_sold_price: Optional[float] = None
    average_cost_basis: Optional[float] = None
    net_profit: Optional[float] = None
    cycle_complete: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_premium_collected": round(self.total_premium_collected, 2),
            "num_put_cycles": self.num_put_cycles,
            "num_call_cycles": self.num_call_cycles,
            "shares_acquired_price": round(self.shares_acquired_price, 4)
            if self.shares_acquired_price
            else None,
            "shares_sold_price": round(self.shares_sold_price, 4)
            if self.shares_sold_price
            else None,
            "average_cost_basis": round(self.average_cost_basis, 4)
            if self.average_cost_basis
            else None,
            "net_profit": round(self.net_profit, 2) if self.net_profit else None,
            "cycle_complete": self.cycle_complete,
        }
