"""Provenance Repository Interface.

Abstract interface for storing and retrieving claim provenance data.
"""

from abc import ABC, abstractmethod

from app.domain.models.claim_provenance import ClaimProvenance, ProvenanceStore
from app.domain.models.visited_source import VisitedSource


class ProvenanceRepository(ABC):
    """Repository interface for provenance tracking.

    Provides methods for storing and retrieving:
    - VisitedSource: Records of URLs actually visited
    - ClaimProvenance: Links between claims and sources
    """

    # =========================================================================
    # VisitedSource operations
    # =========================================================================

    @abstractmethod
    async def save_visited_source(self, source: VisitedSource) -> None:
        """Save a visited source record.

        Args:
            source: VisitedSource to save
        """
        ...

    @abstractmethod
    async def find_visited_source_by_id(self, source_id: str) -> VisitedSource | None:
        """Find visited source by ID.

        Args:
            source_id: Source ID to look up

        Returns:
            VisitedSource or None
        """
        ...

    @abstractmethod
    async def find_visited_source_by_url(
        self,
        session_id: str,
        url: str,
    ) -> VisitedSource | None:
        """Find visited source by URL within a session.

        Args:
            session_id: Session ID
            url: URL to find

        Returns:
            VisitedSource or None
        """
        ...

    @abstractmethod
    async def find_visited_sources_by_session(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[VisitedSource]:
        """Get all visited sources for a session.

        Args:
            session_id: Session ID
            limit: Maximum number to return

        Returns:
            List of VisitedSource
        """
        ...

    @abstractmethod
    async def find_visited_source_by_tool_event(
        self,
        tool_event_id: str,
    ) -> VisitedSource | None:
        """Find visited source by tool event ID.

        Args:
            tool_event_id: ToolEvent ID

        Returns:
            VisitedSource or None
        """
        ...

    @abstractmethod
    async def get_session_urls(self, session_id: str) -> set[str]:
        """Get all URLs visited in a session.

        Args:
            session_id: Session ID

        Returns:
            Set of visited URLs
        """
        ...

    # =========================================================================
    # ClaimProvenance operations
    # =========================================================================

    @abstractmethod
    async def save_claim_provenance(self, provenance: ClaimProvenance) -> None:
        """Save a claim provenance record.

        Args:
            provenance: ClaimProvenance to save
        """
        ...

    @abstractmethod
    async def save_claim_provenance_batch(
        self,
        provenances: list[ClaimProvenance],
    ) -> None:
        """Save multiple claim provenance records.

        Args:
            provenances: List of ClaimProvenance to save
        """
        ...

    @abstractmethod
    async def find_provenance_by_id(
        self,
        provenance_id: str,
    ) -> ClaimProvenance | None:
        """Find provenance by ID.

        Args:
            provenance_id: Provenance ID

        Returns:
            ClaimProvenance or None
        """
        ...

    @abstractmethod
    async def find_provenance_by_claim(
        self,
        session_id: str,
        claim_hash: str,
    ) -> ClaimProvenance | None:
        """Find provenance record for a specific claim.

        Args:
            session_id: Session ID
            claim_hash: Hash of the claim text

        Returns:
            ClaimProvenance or None
        """
        ...

    @abstractmethod
    async def find_provenance_by_session(
        self,
        session_id: str,
        limit: int = 500,
    ) -> list[ClaimProvenance]:
        """Get all provenance records for a session.

        Args:
            session_id: Session ID
            limit: Maximum number to return

        Returns:
            List of ClaimProvenance
        """
        ...

    @abstractmethod
    async def find_provenance_by_report(
        self,
        report_id: str,
    ) -> list[ClaimProvenance]:
        """Get all provenance records for a report.

        Args:
            report_id: Report event ID

        Returns:
            List of ClaimProvenance
        """
        ...

    @abstractmethod
    async def find_unverified_claims(
        self,
        session_id: str,
    ) -> list[ClaimProvenance]:
        """Get all unverified/ungrounded claims in a session.

        Args:
            session_id: Session ID

        Returns:
            List of unverified ClaimProvenance
        """
        ...

    @abstractmethod
    async def find_fabricated_claims(
        self,
        session_id: str,
    ) -> list[ClaimProvenance]:
        """Get claims marked as fabricated.

        Args:
            session_id: Session ID

        Returns:
            List of fabricated ClaimProvenance
        """
        ...

    @abstractmethod
    async def find_numeric_claims(
        self,
        session_id: str,
    ) -> list[ClaimProvenance]:
        """Get all numeric claims (need special verification).

        Args:
            session_id: Session ID

        Returns:
            List of numeric ClaimProvenance
        """
        ...

    @abstractmethod
    async def update_claim_verification(
        self,
        provenance_id: str,
        source_id: str,
        excerpt: str | None,
        similarity_score: float,
        verification_status: str,
    ) -> None:
        """Update claim verification status.

        Args:
            provenance_id: ClaimProvenance ID
            source_id: VisitedSource ID that verifies the claim
            excerpt: Supporting excerpt
            similarity_score: Similarity score
            verification_status: New verification status
        """
        ...

    # =========================================================================
    # Audit & Analysis operations
    # =========================================================================

    @abstractmethod
    async def get_verification_summary(
        self,
        session_id: str,
    ) -> dict:
        """Get summary statistics of claim verification.

        Args:
            session_id: Session ID

        Returns:
            Dict with verification statistics
        """
        ...

    @abstractmethod
    async def get_provenance_store(
        self,
        session_id: str,
    ) -> ProvenanceStore:
        """Load full provenance store for a session.

        Args:
            session_id: Session ID

        Returns:
            ProvenanceStore with all claims
        """
        ...

    @abstractmethod
    async def trace_claim_to_source(
        self,
        claim_text: str,
        session_id: str,
    ) -> tuple[ClaimProvenance | None, VisitedSource | None]:
        """Full audit trail from claim to visited source.

        Args:
            claim_text: Claim text to trace
            session_id: Session ID

        Returns:
            Tuple of (ClaimProvenance, VisitedSource) or (None, None)
        """
        ...

    # =========================================================================
    # Cleanup operations
    # =========================================================================

    @abstractmethod
    async def delete_session_provenance(self, session_id: str) -> int:
        """Delete all provenance data for a session.

        Args:
            session_id: Session ID

        Returns:
            Number of records deleted
        """
        ...
