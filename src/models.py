"""Data models for options chain representation."""

from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any


@dataclass
class OptionContract:
    """
    Represents a single option contract.

    Attributes:
        symbol: Underlying stock ticker symbol
        strike: Strike price of the option
        expiration_date: Expiration date (ISO format: YYYY-MM-DD)
        option_type: "Call" or "Put"
        bid: Bid price (highest price buyer willing to pay)
        ask: Ask price (lowest price seller willing to accept)
        last: Last traded price
        volume: Trading volume for the day
        open_interest: Total number of outstanding contracts
        delta: Rate of change of option price relative to stock price
        gamma: Rate of change of delta
        theta: Rate of change of option price relative to time decay
        vega: Rate of change of option price relative to volatility
        rho: Rate of change of option price relative to interest rate
        implied_volatility: Market's forecast of likely movement in stock price
    """

    symbol: str
    strike: float
    expiration_date: str
    option_type: str  # "Call" or "Put"
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    implied_volatility: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the contract
        """
        return asdict(self)

    @property
    def bid_ask_spread(self) -> Optional[float]:
        """
        Calculate bid-ask spread.

        Returns:
            Spread between ask and bid prices, or None if either is missing
        """
        if self.bid is not None and self.ask is not None:
            return self.ask - self.bid
        return None

    @property
    def mid_price(self) -> Optional[float]:
        """
        Calculate mid-point between bid and ask.

        Returns:
            Average of bid and ask prices, or None if either is missing
        """
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return None

    @property
    def is_call(self) -> bool:
        """Check if this is a call option."""
        return self.option_type.lower() == "call"

    @property
    def is_put(self) -> bool:
        """Check if this is a put option."""
        return self.option_type.lower() == "put"

    def __repr__(self) -> str:
        """String representation of the contract."""
        return (
            f"OptionContract({self.symbol} {self.expiration_date} "
            f"${self.strike} {self.option_type})"
        )


@dataclass
class OptionsChain:
    """
    Represents a complete options chain for a ticker.

    Attributes:
        symbol: Stock ticker symbol
        contracts: List of all option contracts
        retrieved_at: ISO timestamp when data was retrieved
    """

    symbol: str
    contracts: List[OptionContract]
    retrieved_at: str

    def get_calls(self) -> List[OptionContract]:
        """
        Get all call options.

        Returns:
            List of call option contracts
        """
        return [c for c in self.contracts if c.is_call]

    def get_puts(self) -> List[OptionContract]:
        """
        Get all put options.

        Returns:
            List of put option contracts
        """
        return [c for c in self.contracts if c.is_put]

    def get_by_expiration(self, date: str) -> List[OptionContract]:
        """
        Get all contracts for a specific expiration date.

        Args:
            date: Expiration date in YYYY-MM-DD format

        Returns:
            List of contracts expiring on the given date
        """
        return [c for c in self.contracts if c.expiration_date == date]

    def get_expirations(self) -> List[str]:
        """
        Get unique expiration dates sorted chronologically.

        Returns:
            Sorted list of unique expiration dates
        """
        return sorted(list(set(c.expiration_date for c in self.contracts)))

    def get_strikes(self, expiration: Optional[str] = None) -> List[float]:
        """
        Get unique strike prices, optionally filtered by expiration.

        Args:
            expiration: Optional expiration date to filter by

        Returns:
            Sorted list of unique strike prices
        """
        if expiration:
            contracts = self.get_by_expiration(expiration)
        else:
            contracts = self.contracts

        return sorted(list(set(c.strike for c in contracts)))

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the options chain
        """
        return {
            "symbol": self.symbol,
            "retrieved_at": self.retrieved_at,
            "total_contracts": len(self.contracts),
            "total_calls": len(self.get_calls()),
            "total_puts": len(self.get_puts()),
            "expirations": self.get_expirations(),
            "contracts": [c.to_dict() for c in self.contracts],
        }

    def __repr__(self) -> str:
        """String representation of the options chain."""
        return (
            f"OptionsChain({self.symbol}: {len(self.contracts)} contracts, "
            f"{len(self.get_expirations())} expirations)"
        )
