"""Repository for opportunity data access operations."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from src.server.database.models.opportunity import Opportunity

logger = logging.getLogger(__name__)


class OpportunityRepository:
    """Repository for opportunity CRUD operations."""

    def __init__(self, db: Session):
        self.db = db

    def bulk_create(self, opportunities: List[Opportunity]) -> int:
        """Insert multiple opportunities at once.

        Returns:
            Number of opportunities inserted
        """
        self.db.add_all(opportunities)
        self.db.commit()
        return len(opportunities)

    def list_opportunities(
        self,
        symbol: Optional[str] = None,
        direction: Optional[str] = None,
        profile: Optional[str] = None,
        unread_only: bool = False,
        limit: int = 100,
    ) -> List[Opportunity]:
        """List opportunities with optional filters.

        Args:
            symbol: Filter by symbol
            direction: Filter by direction ("put" or "call")
            profile: Filter by profile
            unread_only: Only return unread opportunities
            limit: Maximum results

        Returns:
            List of matching opportunities sorted by bias_score descending
        """
        query = self.db.query(Opportunity)

        if symbol:
            query = query.filter(Opportunity.symbol == symbol.upper())
        if direction:
            query = query.filter(Opportunity.direction == direction)
        if profile:
            query = query.filter(Opportunity.profile == profile)
        if unread_only:
            query = query.filter(Opportunity.is_read == False)

        return (
            query.order_by(Opportunity.bias_score.desc())
            .limit(limit)
            .all()
        )

    def get_unread_count(self) -> int:
        """Get count of unread opportunities."""
        return (
            self.db.query(Opportunity)
            .filter(Opportunity.is_read == False)
            .count()
        )

    def mark_read(self, opportunity_id: int) -> bool:
        """Mark a single opportunity as read.

        Returns:
            True if found and updated, False if not found
        """
        opp = self.db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
        if not opp:
            return False
        opp.is_read = True
        self.db.commit()
        return True

    def mark_all_read(self) -> int:
        """Mark all unread opportunities as read.

        Returns:
            Number of opportunities marked as read
        """
        count = (
            self.db.query(Opportunity)
            .filter(Opportunity.is_read == False)
            .update({"is_read": True})
        )
        self.db.commit()
        return count

    def purge_stale(self, max_age_hours: int = 24) -> int:
        """Delete opportunities older than max_age_hours.

        Returns:
            Number of opportunities deleted
        """
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        count = (
            self.db.query(Opportunity)
            .filter(Opportunity.scanned_at < cutoff)
            .delete()
        )
        self.db.commit()
        logger.info(f"Purged {count} stale opportunities older than {max_age_hours}h")
        return count

    def delete_all_for_symbol(self, symbol: str) -> int:
        """Delete all opportunities for a symbol.

        Returns:
            Number of opportunities deleted
        """
        count = (
            self.db.query(Opportunity)
            .filter(Opportunity.symbol == symbol.upper())
            .delete()
        )
        self.db.commit()
        return count
