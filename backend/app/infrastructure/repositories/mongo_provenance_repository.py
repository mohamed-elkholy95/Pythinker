"""MongoDB Implementation of Provenance Repository.

Implements storage and retrieval of claim provenance data using MongoDB.
"""

import hashlib
import logging
from datetime import UTC, datetime

from app.domain.models.claim_provenance import (
    ClaimProvenance,
    ClaimVerificationStatus,
    ProvenanceStore,
)
from app.domain.models.visited_source import VisitedSource
from app.domain.repositories.provenance_repository import ProvenanceRepository
from app.infrastructure.models.documents import (
    ClaimProvenanceDocument,
    VisitedSourceDocument,
)

logger = logging.getLogger(__name__)


class MongoProvenanceRepository(ProvenanceRepository):
    """MongoDB implementation of provenance repository.

    Provides storage and retrieval for:
    - VisitedSource: Records of URLs actually visited
    - ClaimProvenance: Links between claims and sources
    """

    # =========================================================================
    # VisitedSource operations
    # =========================================================================

    async def save_visited_source(self, source: VisitedSource) -> None:
        """Save a visited source record.

        Args:
            source: VisitedSource to save
        """
        try:
            # Check if already exists
            existing = await VisitedSourceDocument.find_one(
                VisitedSourceDocument.source_id == source.id
            )

            if existing:
                existing.update_from_domain(source)
                await existing.save()
            else:
                doc = VisitedSourceDocument.from_domain(source)
                await doc.insert()

            logger.debug(f"Saved visited source: {source.id} for URL: {source.url}")
        except Exception as e:
            logger.error(f"Failed to save visited source {source.id}: {e}")
            raise

    async def find_visited_source_by_id(self, source_id: str) -> VisitedSource | None:
        """Find visited source by ID.

        Args:
            source_id: Source ID to look up

        Returns:
            VisitedSource or None
        """
        doc = await VisitedSourceDocument.find_one(
            VisitedSourceDocument.source_id == source_id
        )
        return doc.to_domain() if doc else None

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
        doc = await VisitedSourceDocument.find_one(
            VisitedSourceDocument.session_id == session_id,
            VisitedSourceDocument.url == url,
        )
        return doc.to_domain() if doc else None

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
        docs = await VisitedSourceDocument.find(
            VisitedSourceDocument.session_id == session_id
        ).sort("-access_time").limit(limit).to_list()

        return [doc.to_domain() for doc in docs]

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
        doc = await VisitedSourceDocument.find_one(
            VisitedSourceDocument.tool_event_id == tool_event_id
        )
        return doc.to_domain() if doc else None

    async def get_session_urls(self, session_id: str) -> set[str]:
        """Get all URLs visited in a session.

        Args:
            session_id: Session ID

        Returns:
            Set of visited URLs
        """
        docs = await VisitedSourceDocument.find(
            VisitedSourceDocument.session_id == session_id
        ).to_list()

        urls = set()
        for doc in docs:
            urls.add(doc.url)
            if doc.final_url:
                urls.add(doc.final_url)

        return urls

    # =========================================================================
    # ClaimProvenance operations
    # =========================================================================

    async def save_claim_provenance(self, provenance: ClaimProvenance) -> None:
        """Save a claim provenance record.

        Args:
            provenance: ClaimProvenance to save
        """
        try:
            # Check if already exists
            existing = await ClaimProvenanceDocument.find_one(
                ClaimProvenanceDocument.provenance_id == provenance.id
            )

            if existing:
                existing.update_from_domain(provenance)
                await existing.save()
            else:
                doc = ClaimProvenanceDocument.from_domain(provenance)
                await doc.insert()

            logger.debug(f"Saved claim provenance: {provenance.id}")
        except Exception as e:
            logger.error(f"Failed to save claim provenance {provenance.id}: {e}")
            raise

    async def save_claim_provenance_batch(
        self,
        provenances: list[ClaimProvenance],
    ) -> None:
        """Save multiple claim provenance records.

        Args:
            provenances: List of ClaimProvenance to save
        """
        if not provenances:
            return

        try:
            docs = [ClaimProvenanceDocument.from_domain(p) for p in provenances]
            await ClaimProvenanceDocument.insert_many(docs)
            logger.debug(f"Saved {len(provenances)} claim provenance records")
        except Exception as e:
            logger.error(f"Failed to save claim provenance batch: {e}")
            raise

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
        doc = await ClaimProvenanceDocument.find_one(
            ClaimProvenanceDocument.provenance_id == provenance_id
        )
        return doc.to_domain() if doc else None

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
        doc = await ClaimProvenanceDocument.find_one(
            ClaimProvenanceDocument.session_id == session_id,
            ClaimProvenanceDocument.claim_hash == claim_hash,
        )
        return doc.to_domain() if doc else None

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
        docs = await ClaimProvenanceDocument.find(
            ClaimProvenanceDocument.session_id == session_id
        ).sort("-created_at").limit(limit).to_list()

        return [doc.to_domain() for doc in docs]

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
        docs = await ClaimProvenanceDocument.find(
            ClaimProvenanceDocument.report_id == report_id
        ).to_list()

        return [doc.to_domain() for doc in docs]

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
        docs = await ClaimProvenanceDocument.find(
            ClaimProvenanceDocument.session_id == session_id,
            ClaimProvenanceDocument.verification_status.in_([
                ClaimVerificationStatus.UNVERIFIED,
                ClaimVerificationStatus.INFERRED,
            ]),
        ).to_list()

        return [doc.to_domain() for doc in docs]

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
        docs = await ClaimProvenanceDocument.find(
            ClaimProvenanceDocument.session_id == session_id,
            ClaimProvenanceDocument.is_fabricated == True,  # noqa: E712
        ).to_list()

        return [doc.to_domain() for doc in docs]

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
        docs = await ClaimProvenanceDocument.find(
            ClaimProvenanceDocument.session_id == session_id,
            ClaimProvenanceDocument.is_numeric == True,  # noqa: E712
        ).to_list()

        return [doc.to_domain() for doc in docs]

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
        doc = await ClaimProvenanceDocument.find_one(
            ClaimProvenanceDocument.provenance_id == provenance_id
        )

        if not doc:
            logger.warning(f"Provenance not found for update: {provenance_id}")
            return

        doc.source_id = source_id
        doc.supporting_excerpt = excerpt
        doc.similarity_score = similarity_score
        doc.verification_status = ClaimVerificationStatus(verification_status)
        doc.verified_at = datetime.now(UTC)
        doc.is_fabricated = verification_status == ClaimVerificationStatus.FABRICATED.value

        await doc.save()
        logger.debug(f"Updated claim verification: {provenance_id} -> {verification_status}")

    # =========================================================================
    # Audit & Analysis operations
    # =========================================================================

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
        docs = await ClaimProvenanceDocument.find(
            ClaimProvenanceDocument.session_id == session_id
        ).to_list()

        total = len(docs)
        if total == 0:
            return {
                "total_claims": 0,
                "verified": 0,
                "partial": 0,
                "inferred": 0,
                "unverified": 0,
                "fabricated": 0,
                "contradicted": 0,
                "grounded_rate": 0.0,
                "has_critical_issues": False,
            }

        verified = sum(1 for d in docs if d.verification_status == ClaimVerificationStatus.VERIFIED)
        partial = sum(1 for d in docs if d.verification_status == ClaimVerificationStatus.PARTIAL)
        inferred = sum(1 for d in docs if d.verification_status == ClaimVerificationStatus.INFERRED)
        unverified = sum(1 for d in docs if d.verification_status == ClaimVerificationStatus.UNVERIFIED)
        fabricated = sum(1 for d in docs if d.is_fabricated)
        contradicted = sum(1 for d in docs if d.verification_status == ClaimVerificationStatus.CONTRADICTED)

        grounded_rate = (verified + partial) / total if total > 0 else 0.0

        return {
            "total_claims": total,
            "verified": verified,
            "partial": partial,
            "inferred": inferred,
            "unverified": unverified,
            "fabricated": fabricated,
            "contradicted": contradicted,
            "grounded_rate": grounded_rate,
            "has_critical_issues": fabricated > 0 or contradicted > 0,
        }

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
        store = ProvenanceStore(session_id=session_id)

        docs = await ClaimProvenanceDocument.find(
            ClaimProvenanceDocument.session_id == session_id
        ).to_list()

        for doc in docs:
            provenance = doc.to_domain()
            store.add_claim(provenance)

        return store

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
        # Generate claim hash
        normalized = claim_text.lower().strip()
        claim_hash = hashlib.sha256(normalized.encode()).hexdigest()[:16]

        # Find provenance
        provenance = await self.find_provenance_by_claim(session_id, claim_hash)
        if not provenance:
            return None, None

        # Find source if linked
        source = None
        if provenance.source_id:
            source = await self.find_visited_source_by_id(provenance.source_id)

        return provenance, source

    # =========================================================================
    # Cleanup operations
    # =========================================================================

    async def delete_session_provenance(self, session_id: str) -> int:
        """Delete all provenance data for a session.

        Args:
            session_id: Session ID

        Returns:
            Number of records deleted
        """
        # Delete visited sources
        source_result = await VisitedSourceDocument.find(
            VisitedSourceDocument.session_id == session_id
        ).delete()
        source_count = source_result.deleted_count if source_result else 0

        # Delete claim provenance
        claim_result = await ClaimProvenanceDocument.find(
            ClaimProvenanceDocument.session_id == session_id
        ).delete()
        claim_count = claim_result.deleted_count if claim_result else 0

        total = source_count + claim_count
        logger.info(f"Deleted {total} provenance records for session {session_id}")
        return total
