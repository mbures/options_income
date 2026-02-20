"""Service layer for watchlist management and opportunity scanning.

Coordinates watchlist CRUD, opportunity scanning via RecommendEngine,
and opportunity storage/retrieval.
"""

import logging
import os
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from src.config import FinnhubConfig
from src.market_data.finnhub_client import FinnhubClient
from src.market_data.price_fetcher import SchwabPriceDataFetcher
from src.models.profiles import StrikeProfile
from src.schwab.client import SchwabClient
from src.server.database.models.opportunity import Opportunity
from src.server.database.models.watchlist import WatchlistItem
from src.server.repositories.opportunity import OpportunityRepository
from src.server.repositories.watchlist import WatchlistRepository
from src.wheel.recommend import RecommendEngine

logger = logging.getLogger(__name__)

DEFAULT_PROFILES = [StrikeProfile.CONSERVATIVE, StrikeProfile.AGGRESSIVE]


class WatchlistService:
    """Service for watchlist management and opportunity scanning.

    Attributes:
        db: SQLAlchemy database session
        watchlist_repo: Watchlist data access
        opportunity_repo: Opportunity data access
        recommend_engine: Core recommendation engine for scanning
    """

    def __init__(self, db: Session, schwab_client: Optional[SchwabClient] = None):
        self.db = db
        self.watchlist_repo = WatchlistRepository(db)
        self.opportunity_repo = OpportunityRepository(db)

        # Initialize clients (same pattern as RecommendationService)
        if schwab_client:
            self._schwab = schwab_client
        else:
            try:
                self._schwab = SchwabClient()
            except Exception as e:
                logger.warning(f"Failed to initialize SchwabClient: {e}")
                self._schwab = None

        price_fetcher = (
            SchwabPriceDataFetcher(self._schwab) if self._schwab else None
        )

        try:
            finnhub_api_key = os.environ.get("FINNHUB_API_KEY", "")
            if finnhub_api_key:
                finnhub_client = FinnhubClient(FinnhubConfig(api_key=finnhub_api_key))
            else:
                finnhub_client = None
        except Exception:
            finnhub_client = None

        self.recommend_engine = RecommendEngine(
            finnhub_client=finnhub_client,
            price_fetcher=price_fetcher,
            schwab_client=self._schwab,
        )

    # --- Watchlist CRUD ---

    def add_symbol(self, symbol: str, notes: Optional[str] = None) -> WatchlistItem:
        """Add a symbol to the watchlist."""
        return self.watchlist_repo.add_symbol(symbol.upper(), notes)

    def remove_symbol(self, symbol: str) -> bool:
        """Remove a symbol from the watchlist and its opportunities."""
        symbol = symbol.upper()
        self.opportunity_repo.delete_all_for_symbol(symbol)
        return self.watchlist_repo.remove_symbol(symbol)

    def list_watchlist(self) -> List[WatchlistItem]:
        """List all watchlist symbols."""
        return self.watchlist_repo.list_all()

    # --- Opportunity Scanning ---

    def scan_all(
        self,
        profiles: Optional[List[StrikeProfile]] = None,
        max_dte: int = 45,
    ) -> dict:
        """Scan all watchlist symbols for opportunities.

        Args:
            profiles: Risk profiles to scan (defaults to conservative + aggressive)
            max_dte: Maximum days to expiration

        Returns:
            Dict with symbols_scanned, opportunities_found, errors
        """
        if profiles is None:
            profiles = DEFAULT_PROFILES

        watchlist = self.watchlist_repo.list_all()
        if not watchlist:
            logger.info("Watchlist is empty, nothing to scan")
            return {"symbols_scanned": 0, "opportunities_found": 0, "errors": {}}

        # Purge stale opportunities before inserting new ones
        self.opportunity_repo.purge_stale(max_age_hours=24)

        errors: dict[str, str] = {}
        total_found = 0

        for item in watchlist:
            try:
                recs = self.recommend_engine.scan_opportunities(
                    symbol=item.symbol,
                    profiles=profiles,
                    max_dte=max_dte,
                )

                if not recs:
                    logger.info(f"No opportunities found for {item.symbol}")
                    continue

                # Convert WheelRecommendation objects to Opportunity ORM objects
                now = datetime.utcnow()
                opps = []
                for r in recs:
                    # Determine profile string from the recommendation's sigma distance
                    profile_str = self._profile_from_recommendation(r, profiles)
                    opps.append(
                        Opportunity(
                            symbol=r.symbol,
                            direction=r.direction,
                            profile=profile_str,
                            strike=r.strike,
                            expiration_date=r.expiration_date,
                            premium_per_share=r.premium_per_share,
                            total_premium=r.total_premium,
                            p_itm=r.p_itm,
                            sigma_distance=r.sigma_distance,
                            annualized_yield_pct=r.annualized_yield_pct,
                            bias_score=r.bias_score,
                            dte=r.dte,
                            current_price=r.current_price,
                            bid=r.bid,
                            ask=r.ask,
                            is_read=False,
                            scanned_at=now,
                        )
                    )

                self.opportunity_repo.bulk_create(opps)
                total_found += len(opps)
                logger.info(f"Found {len(opps)} opportunities for {item.symbol}")

            except Exception as e:
                logger.error(f"Failed to scan {item.symbol}: {e}", exc_info=True)
                errors[item.symbol] = str(e)

        result = {
            "symbols_scanned": len(watchlist),
            "opportunities_found": total_found,
            "errors": errors,
        }
        logger.info(
            f"Scan complete: {result['symbols_scanned']} symbols, "
            f"{result['opportunities_found']} opportunities, "
            f"{len(errors)} errors"
        )
        return result

    def _profile_from_recommendation(self, rec, profiles: List[StrikeProfile]) -> str:
        """Determine the profile string for a recommendation based on its sigma distance.

        Matches the recommendation's sigma_distance to the closest scanned profile.
        """
        from src.models.profiles import PROFILE_SIGMA_RANGES

        best_profile = profiles[0].value
        best_distance = float("inf")

        for profile in profiles:
            min_sigma, max_sigma = PROFILE_SIGMA_RANGES[profile]
            mid = (min_sigma + max_sigma) / 2
            distance = abs(rec.sigma_distance - mid)
            if distance < best_distance:
                best_distance = distance
                best_profile = profile.value

        return best_profile

    # --- Opportunity Retrieval ---

    def get_opportunities(
        self,
        symbol: Optional[str] = None,
        direction: Optional[str] = None,
        profile: Optional[str] = None,
        unread_only: bool = False,
        limit: int = 100,
    ) -> list:
        """Get filtered opportunities."""
        return self.opportunity_repo.list_opportunities(
            symbol=symbol,
            direction=direction,
            profile=profile,
            unread_only=unread_only,
            limit=limit,
        )

    def get_unread_count(self) -> int:
        """Get count of unread opportunities."""
        return self.opportunity_repo.get_unread_count()

    def mark_read(self, opportunity_id: int) -> bool:
        """Mark a single opportunity as read."""
        return self.opportunity_repo.mark_read(opportunity_id)

    def mark_all_read(self) -> int:
        """Mark all opportunities as read."""
        return self.opportunity_repo.mark_all_read()
