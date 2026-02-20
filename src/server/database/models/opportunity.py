"""Opportunity database model.

Represents a scanned option-selling opportunity from the watchlist scanner.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String

from src.server.database.session import Base


class Opportunity(Base):
    """Scanned opportunity for option selling.

    Stores results from the watchlist opportunity scanner, normalized
    to 1 contract. Supports filtering by symbol, direction, profile,
    and read status.

    Attributes:
        id: Unique identifier
        symbol: Stock ticker symbol
        direction: Trade direction ("put" or "call")
        profile: Risk profile used for scan ("conservative", "aggressive", etc.)
        strike: Strike price
        expiration_date: Option expiration date (YYYY-MM-DD)
        premium_per_share: Bid price per share
        total_premium: Total premium for 1 contract (premium_per_share * 100)
        p_itm: Probability of expiring in-the-money
        sigma_distance: Distance from current price in sigma units
        annualized_yield_pct: Annualized yield percentage
        bias_score: Collection bias score (higher = more likely to expire worthless)
        dte: Calendar days to expiration
        current_price: Stock price at time of scan
        bid: Option bid price
        ask: Option ask price
        is_read: Whether user has viewed this opportunity
        scanned_at: Timestamp when opportunity was scanned
    """

    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    direction = Column(String, nullable=False)  # "put" or "call"
    profile = Column(String, nullable=False)
    strike = Column(Float, nullable=False)
    expiration_date = Column(String, nullable=False)
    premium_per_share = Column(Float, nullable=False)
    total_premium = Column(Float, nullable=False)
    p_itm = Column(Float, nullable=False)
    sigma_distance = Column(Float, nullable=False)
    annualized_yield_pct = Column(Float, nullable=False)
    bias_score = Column(Float, nullable=False, default=0.0)
    dte = Column(Integer, nullable=False)
    current_price = Column(Float, nullable=False)
    bid = Column(Float, nullable=False)
    ask = Column(Float, nullable=False, default=0.0)
    is_read = Column(Boolean, nullable=False, default=False, index=True)
    scanned_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return (
            f"<Opportunity(id={self.id}, symbol={self.symbol}, "
            f"direction={self.direction}, strike={self.strike})>"
        )
