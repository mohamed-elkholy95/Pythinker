"""Memory evidence schema for grounding safety.

Phase 4: Structured evidence with confidence scoring, provenance tracking,
and contradiction detection to reduce hallucinations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class EvidenceConfidence(str, Enum):
    """Confidence level for evidence."""

    HIGH = "high"  # Score >= 0.85, from trusted source
    MEDIUM = "medium"  # Score >= 0.70, decent quality
    LOW = "low"  # Score >= 0.50, weak evidence
    MINIMAL = "minimal"  # Score < 0.50, unreliable


@dataclass
class MemoryEvidence:
    """Structured evidence from memory retrieval with provenance.

    Provides explicit evidence tracking with confidence scoring,
    contradiction detection, and formatted prompt blocks.
    """

    memory_id: str
    content: str
    source_type: str  # "user_knowledge", "task_artifacts", "tool_logs"
    retrieval_score: float  # 0-1 similarity/relevance score
    embedding_quality: float  # Confidence in embedding accuracy (0-1)
    timestamp: datetime
    session_id: str | None
    memory_type: str  # "fact", "preference", "procedure", etc.
    importance: str  # "critical", "high", "medium", "low"

    # Conflict detection
    contradictions: list[str] = field(default_factory=list)  # IDs of conflicting memories
    contradiction_reasons: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> EvidenceConfidence:
        """Compute overall confidence level.

        Combines retrieval score (how relevant) with embedding quality
        (how reliable the embedding is).
        """
        # Combine retrieval score and embedding quality
        combined_score = (self.retrieval_score + self.embedding_quality) / 2

        if combined_score >= 0.85:
            return EvidenceConfidence.HIGH
        elif combined_score >= 0.70:
            return EvidenceConfidence.MEDIUM
        elif combined_score >= 0.50:
            return EvidenceConfidence.LOW
        else:
            return EvidenceConfidence.MINIMAL

    @property
    def needs_caveat(self) -> bool:
        """Check if this evidence needs a caveat."""
        return self.confidence in (EvidenceConfidence.LOW, EvidenceConfidence.MINIMAL) or len(self.contradictions) > 0

    @property
    def should_reject(self) -> bool:
        """Check if this evidence should be rejected entirely."""
        return (
            self.confidence == EvidenceConfidence.MINIMAL
            or len(self.contradictions) >= 2  # Multiple contradictions
        )

    def to_prompt_block(self, include_metadata: bool = True) -> str:
        """Format evidence for LLM prompt injection.

        Args:
            include_metadata: Include confidence and provenance metadata

        Returns:
            Formatted evidence block ready for prompt injection
        """
        if self.should_reject:
            return ""  # Reject unreliable evidence

        # Build evidence block
        lines = []

        if include_metadata:
            confidence_label = self.confidence.value.upper()
            lines.append(f"[EVIDENCE | Confidence: {confidence_label} | Score: {self.retrieval_score:.2f}]")
            lines.append(f"Source: {self.source_type} ({self.timestamp.strftime('%Y-%m-%d')})")

        lines.append(f"Content: {self.content}")

        # Add caveats for low-confidence evidence
        if self.needs_caveat:
            if self.confidence in (EvidenceConfidence.LOW, EvidenceConfidence.MINIMAL):
                lines.append("⚠️ CAVEAT: Low confidence - verify before citing")

            if self.contradictions:
                lines.append(f"⚠️ CONFLICT: Contradicts {len(self.contradictions)} other memories")
                for reason in self.contradiction_reasons[:2]:  # Show top 2
                    lines.append(f"  - {reason}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "source_type": self.source_type,
            "retrieval_score": self.retrieval_score,
            "embedding_quality": self.embedding_quality,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "confidence": self.confidence.value,
            "contradictions": self.contradictions,
            "contradiction_reasons": self.contradiction_reasons,
            "needs_caveat": self.needs_caveat,
            "should_reject": self.should_reject,
        }
