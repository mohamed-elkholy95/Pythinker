"""Tests for memory evidence schema.

Phase 4: Tests evidence-based memory with confidence scoring and caveat detection.
"""

from datetime import datetime

from app.domain.models.memory_evidence import EvidenceConfidence, MemoryEvidence


class TestEvidenceConfidence:
    """Test evidence confidence calculation."""

    def test_high_confidence(self):
        """Test high confidence evidence."""
        evidence = MemoryEvidence(
            memory_id="mem-1",
            content="Test content",
            source_type="user_knowledge",
            retrieval_score=0.9,
            embedding_quality=0.9,
            timestamp=datetime.utcnow(),
            session_id="session-1",
            memory_type="fact",
            importance="high",
        )

        assert evidence.confidence == EvidenceConfidence.HIGH
        assert not evidence.needs_caveat
        assert not evidence.should_reject

    def test_medium_confidence(self):
        """Test medium confidence evidence."""
        evidence = MemoryEvidence(
            memory_id="mem-2",
            content="Test content",
            source_type="user_knowledge",
            retrieval_score=0.75,
            embedding_quality=0.70,
            timestamp=datetime.utcnow(),
            session_id="session-2",
            memory_type="fact",
            importance="medium",
        )

        assert evidence.confidence == EvidenceConfidence.MEDIUM
        assert not evidence.needs_caveat
        assert not evidence.should_reject

    def test_low_confidence(self):
        """Test low confidence evidence."""
        evidence = MemoryEvidence(
            memory_id="mem-3",
            content="Test content",
            source_type="user_knowledge",
            retrieval_score=0.6,
            embedding_quality=0.5,
            timestamp=datetime.utcnow(),
            session_id="session-3",
            memory_type="fact",
            importance="low",
        )

        assert evidence.confidence == EvidenceConfidence.LOW
        assert evidence.needs_caveat  # Low confidence needs caveat
        assert not evidence.should_reject

    def test_minimal_confidence(self):
        """Test minimal confidence evidence."""
        evidence = MemoryEvidence(
            memory_id="mem-4",
            content="Test content",
            source_type="user_knowledge",
            retrieval_score=0.3,
            embedding_quality=0.4,
            timestamp=datetime.utcnow(),
            session_id="session-4",
            memory_type="fact",
            importance="low",
        )

        assert evidence.confidence == EvidenceConfidence.MINIMAL
        assert evidence.needs_caveat
        assert evidence.should_reject  # Minimal confidence should be rejected


class TestContradictionDetection:
    """Test contradiction marking."""

    def test_single_contradiction_needs_caveat(self):
        """Test evidence with one contradiction needs caveat."""
        evidence = MemoryEvidence(
            memory_id="mem-5",
            content="Test content",
            source_type="user_knowledge",
            retrieval_score=0.9,
            embedding_quality=0.9,
            timestamp=datetime.utcnow(),
            session_id="session-5",
            memory_type="fact",
            importance="high",
            contradictions=["mem-6"],
            contradiction_reasons=["Numeric conflict"],
        )

        assert evidence.confidence == EvidenceConfidence.HIGH
        assert evidence.needs_caveat  # Has contradiction
        assert not evidence.should_reject  # Only 1 contradiction

    def test_multiple_contradictions_rejected(self):
        """Test evidence with multiple contradictions is rejected."""
        evidence = MemoryEvidence(
            memory_id="mem-7",
            content="Test content",
            source_type="user_knowledge",
            retrieval_score=0.9,
            embedding_quality=0.9,
            timestamp=datetime.utcnow(),
            session_id="session-7",
            memory_type="fact",
            importance="high",
            contradictions=["mem-8", "mem-9"],
            contradiction_reasons=["Numeric conflict", "Negation detected"],
        )

        assert evidence.confidence == EvidenceConfidence.HIGH
        assert evidence.needs_caveat
        assert evidence.should_reject  # 2+ contradictions


class TestPromptBlockFormatting:
    """Test evidence formatting for prompt injection."""

    def test_high_confidence_formatting(self):
        """Test formatting high-confidence evidence."""
        evidence = MemoryEvidence(
            memory_id="mem-10",
            content="Python is a programming language",
            source_type="user_knowledge",
            retrieval_score=0.95,
            embedding_quality=0.90,
            timestamp=datetime(2024, 1, 1),
            session_id="session-10",
            memory_type="fact",
            importance="high",
        )

        block = evidence.to_prompt_block(include_metadata=True)

        assert "[EVIDENCE" in block
        assert "Confidence: HIGH" in block
        assert "Score: 0.95" in block
        assert "user_knowledge" in block
        assert "2024-01-01" in block
        assert "Python is a programming language" in block
        assert "⚠️" not in block  # No caveats for high confidence

    def test_low_confidence_formatting_with_caveat(self):
        """Test formatting low-confidence evidence with caveat."""
        evidence = MemoryEvidence(
            memory_id="mem-11",
            content="Uncertain claim",
            source_type="user_knowledge",
            retrieval_score=0.6,
            embedding_quality=0.5,
            timestamp=datetime(2024, 1, 1),
            session_id="session-11",
            memory_type="fact",
            importance="low",
        )

        block = evidence.to_prompt_block(include_metadata=True)

        assert "Confidence: LOW" in block
        assert "⚠️ CAVEAT: Low confidence" in block

    def test_contradiction_formatting(self):
        """Test formatting evidence with contradictions."""
        evidence = MemoryEvidence(
            memory_id="mem-12",
            content="Contradicted claim",
            source_type="user_knowledge",
            retrieval_score=0.8,
            embedding_quality=0.8,
            timestamp=datetime(2024, 1, 1),
            session_id="session-12",
            memory_type="fact",
            importance="medium",
            contradictions=["mem-13"],
            contradiction_reasons=["Numeric conflict: value = 100 vs 150"],
        )

        block = evidence.to_prompt_block(include_metadata=True)

        assert "⚠️ CONFLICT: Contradicts 1 other memories" in block
        assert "Numeric conflict" in block

    def test_rejected_evidence_returns_empty_block(self):
        """Test rejected evidence returns empty string."""
        evidence = MemoryEvidence(
            memory_id="mem-14",
            content="Should be rejected",
            source_type="user_knowledge",
            retrieval_score=0.3,
            embedding_quality=0.3,
            timestamp=datetime.utcnow(),
            session_id="session-14",
            memory_type="fact",
            importance="low",
        )

        block = evidence.to_prompt_block(include_metadata=True)

        assert block == ""  # Minimal confidence rejected

    def test_metadata_can_be_excluded(self):
        """Test formatting without metadata."""
        evidence = MemoryEvidence(
            memory_id="mem-15",
            content="Simple content",
            source_type="user_knowledge",
            retrieval_score=0.9,
            embedding_quality=0.9,
            timestamp=datetime.utcnow(),
            session_id="session-15",
            memory_type="fact",
            importance="high",
        )

        block = evidence.to_prompt_block(include_metadata=False)

        assert "[EVIDENCE" not in block
        assert "Confidence:" not in block
        assert "Simple content" in block


class TestEvidenceSerialization:
    """Test evidence to_dict serialization."""

    def test_to_dict(self):
        """Test evidence serialization to dictionary."""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        evidence = MemoryEvidence(
            memory_id="mem-16",
            content="Test serialization",
            source_type="user_knowledge",
            retrieval_score=0.85,
            embedding_quality=0.80,
            timestamp=timestamp,
            session_id="session-16",
            memory_type="fact",
            importance="high",
            contradictions=["mem-17"],
            contradiction_reasons=["Test reason"],
        )

        data = evidence.to_dict()

        assert data["memory_id"] == "mem-16"
        assert data["content"] == "Test serialization"
        assert data["retrieval_score"] == 0.85
        assert data["embedding_quality"] == 0.80
        assert data["timestamp"] == timestamp.isoformat()
        assert data["confidence"] == "medium"
        assert data["contradictions"] == ["mem-17"]
        assert data["needs_caveat"] is True
        assert data["should_reject"] is False
