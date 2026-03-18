"""Tests for contradiction resolver.

Phase 4: Tests contradiction detection strategies (numeric, negation, LLM-based).
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.memory_evidence import MemoryEvidence
from app.domain.services.retrieval.contradiction_resolver import ContradictionResolver


class TestNumericContradictionDetection:
    """Test numeric contradiction detection."""

    @pytest.mark.asyncio
    async def test_detects_numeric_conflict(self):
        """Test detection of conflicting numeric values."""
        evidence_list = [
            MemoryEvidence(
                memory_id="mem-1",
                content="The price is 100 dollars",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-1",
                memory_type="fact",
                importance="high",
            ),
            MemoryEvidence(
                memory_id="mem-2",
                content="The price is 150 dollars",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-2",
                memory_type="fact",
                importance="high",
            ),
        ]

        resolver = ContradictionResolver()
        result = await resolver.detect_contradictions(evidence_list)

        # Both should have contradictions marked
        assert "mem-2" in result[0].contradictions
        assert "mem-1" in result[1].contradictions
        assert "Numeric conflict" in result[0].contradiction_reasons[0]
        assert "price" in result[0].contradiction_reasons[0].lower()

    @pytest.mark.asyncio
    async def test_ignores_small_numeric_differences(self):
        """Test that small differences (<10%) are not marked as contradictions."""
        evidence_list = [
            MemoryEvidence(
                memory_id="mem-3",
                content="The value is 100",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-3",
                memory_type="fact",
                importance="high",
            ),
            MemoryEvidence(
                memory_id="mem-4",
                content="The value is 105",  # Only 5% difference
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-4",
                memory_type="fact",
                importance="high",
            ),
        ]

        resolver = ContradictionResolver()
        result = await resolver.detect_contradictions(evidence_list)

        # Should not detect contradiction (difference < 10%)
        assert len(result[0].contradictions) == 0
        assert len(result[1].contradictions) == 0

    @pytest.mark.asyncio
    async def test_handles_different_entities(self):
        """Test that different entities don't conflict."""
        evidence_list = [
            MemoryEvidence(
                memory_id="mem-5",
                content="The price is 100",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-5",
                memory_type="fact",
                importance="high",
            ),
            MemoryEvidence(
                memory_id="mem-6",
                content="The cost is 150",  # Different entity
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-6",
                memory_type="fact",
                importance="high",
            ),
        ]

        resolver = ContradictionResolver()
        result = await resolver.detect_contradictions(evidence_list)

        # Should not detect contradiction (different entities)
        assert len(result[0].contradictions) == 0
        assert len(result[1].contradictions) == 0


class TestNegationContradictionDetection:
    """Test negation-based contradiction detection."""

    @pytest.mark.asyncio
    async def test_detects_direct_negation(self):
        """Test detection of direct negations."""
        evidence_list = [
            MemoryEvidence(
                memory_id="mem-7",
                content="User prefers dark mode for development",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-7",
                memory_type="preference",
                importance="high",
            ),
            MemoryEvidence(
                memory_id="mem-8",
                content="User does not prefer dark mode for development",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-8",
                memory_type="preference",
                importance="high",
            ),
        ]

        resolver = ContradictionResolver()
        result = await resolver.detect_contradictions(evidence_list)

        # Both should have negation contradiction marked
        assert "mem-8" in result[0].contradictions
        assert "mem-7" in result[1].contradictions
        assert "Direct negation detected" in result[0].contradiction_reasons[0]

    @pytest.mark.asyncio
    async def test_requires_shared_keywords(self):
        """Test that negation requires shared keywords to be marked."""
        evidence_list = [
            MemoryEvidence(
                memory_id="mem-9",
                content="User likes Python programming",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-9",
                memory_type="preference",
                importance="high",
            ),
            MemoryEvidence(
                memory_id="mem-10",
                content="User does not like JavaScript frameworks",  # Different topic
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-10",
                memory_type="preference",
                importance="high",
            ),
        ]

        resolver = ContradictionResolver()
        result = await resolver.detect_contradictions(evidence_list)

        # Should not detect contradiction (not enough shared keywords)
        assert len(result[0].contradictions) == 0
        assert len(result[1].contradictions) == 0

    @pytest.mark.asyncio
    async def test_detects_never_keyword(self):
        """Test detection of 'never' negations."""
        evidence_list = [
            MemoryEvidence(
                memory_id="mem-11",
                content="User wants email notifications enabled",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-11",
                memory_type="preference",
                importance="high",
            ),
            MemoryEvidence(
                memory_id="mem-12",
                content="User never wants email notifications enabled",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-12",
                memory_type="preference",
                importance="high",
            ),
        ]

        resolver = ContradictionResolver()
        result = await resolver.detect_contradictions(evidence_list)

        # Should detect negation contradiction
        assert "mem-12" in result[0].contradictions
        assert "mem-11" in result[1].contradictions


class TestLLMContradictionDetection:
    """Test LLM-based semantic contradiction detection."""

    @pytest.mark.asyncio
    async def test_llm_detects_semantic_contradiction(self):
        """Test LLM detection of semantic contradictions."""
        # Mock LLM response
        mock_llm = MagicMock()
        mock_llm.ask = AsyncMock(
            return_value={
                "content": '{"contradictions": [{"id1": 0, "id2": 1, "reason": "User cannot live in both cities"}]}'
            }
        )

        evidence_list = [
            MemoryEvidence(
                memory_id="mem-13",
                content="User lives in New York",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-13",
                memory_type="fact",
                importance="high",
            ),
            MemoryEvidence(
                memory_id="mem-14",
                content="User lives in California",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-14",
                memory_type="fact",
                importance="high",
            ),
        ]

        resolver = ContradictionResolver(llm=mock_llm)
        result = await resolver.detect_contradictions(evidence_list)

        # Should detect LLM-based contradiction
        assert "mem-14" in result[0].contradictions
        assert "mem-13" in result[1].contradictions
        assert "cannot live in both cities" in result[0].contradiction_reasons[0]

    @pytest.mark.asyncio
    async def test_llm_skipped_for_large_sets(self):
        """Test that LLM detection is skipped for large evidence sets."""
        mock_llm = MagicMock()
        mock_llm.ask = AsyncMock()

        # Create 11 evidence items (exceeds 10-item limit)
        evidence_list = [
            MemoryEvidence(
                memory_id=f"mem-{i}",
                content=f"Content {i}",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id=f"session-{i}",
                memory_type="fact",
                importance="high",
            )
            for i in range(11)
        ]

        resolver = ContradictionResolver(llm=mock_llm)
        result = await resolver.detect_contradictions(evidence_list)

        # LLM should NOT be called (too many items)
        mock_llm.ask.assert_not_called()
        assert len(result) == 11

    @pytest.mark.asyncio
    async def test_llm_failure_graceful_degradation(self):
        """Test that LLM failures don't break contradiction detection."""
        # Mock LLM that raises exception
        mock_llm = MagicMock()
        mock_llm.ask = AsyncMock(side_effect=Exception("LLM API error"))

        evidence_list = [
            MemoryEvidence(
                memory_id="mem-15",
                content="Test content",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-15",
                memory_type="fact",
                importance="high",
            )
        ]

        resolver = ContradictionResolver(llm=mock_llm)
        result = await resolver.detect_contradictions(evidence_list)

        # Should still return evidence list despite LLM failure
        assert len(result) == 1
        assert result[0].memory_id == "mem-15"

    @pytest.mark.asyncio
    async def test_llm_malformed_json_handling(self):
        """Test handling of malformed JSON from LLM."""
        # Mock LLM with invalid JSON
        mock_llm = MagicMock()
        mock_llm.ask = AsyncMock(return_value={"content": "invalid json"})

        evidence_list = [
            MemoryEvidence(
                memory_id="mem-16",
                content="Test content",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-16",
                memory_type="fact",
                importance="high",
            )
        ]

        resolver = ContradictionResolver(llm=mock_llm)
        result = await resolver.detect_contradictions(evidence_list)

        # Should handle gracefully
        assert len(result) == 1
        assert result[0].memory_id == "mem-16"


class TestContradictionResolverIntegration:
    """Integration tests for full contradiction detection pipeline."""

    @pytest.mark.asyncio
    async def test_multiple_detection_strategies(self):
        """Test that multiple strategies can detect different contradictions."""
        evidence_list = [
            MemoryEvidence(
                memory_id="mem-17",
                content="The price is 100 dollars",  # Numeric conflict with mem-18
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-17",
                memory_type="fact",
                importance="high",
            ),
            MemoryEvidence(
                memory_id="mem-18",
                content="The price is 200 dollars",  # Numeric conflict with mem-17
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-18",
                memory_type="fact",
                importance="high",
            ),
            MemoryEvidence(
                memory_id="mem-19",
                content="User prefers dark mode interface",  # Negation conflict with mem-20
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-19",
                memory_type="preference",
                importance="high",
            ),
            MemoryEvidence(
                memory_id="mem-20",
                content="User does not prefer dark mode interface",  # Negation conflict with mem-19
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-20",
                memory_type="preference",
                importance="high",
            ),
        ]

        resolver = ContradictionResolver()
        result = await resolver.detect_contradictions(evidence_list)

        # Check numeric contradiction
        assert "mem-18" in result[0].contradictions
        assert "mem-17" in result[1].contradictions

        # Check negation contradiction
        assert "mem-20" in result[2].contradictions
        assert "mem-19" in result[3].contradictions

    @pytest.mark.asyncio
    async def test_single_evidence_no_contradictions(self):
        """Test that single evidence has no contradictions."""
        evidence_list = [
            MemoryEvidence(
                memory_id="mem-21",
                content="Single piece of evidence",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-21",
                memory_type="fact",
                importance="high",
            )
        ]

        resolver = ContradictionResolver()
        result = await resolver.detect_contradictions(evidence_list)

        # Should have no contradictions
        assert len(result[0].contradictions) == 0

    @pytest.mark.asyncio
    async def test_empty_evidence_list(self):
        """Test handling of empty evidence list."""
        evidence_list = []

        resolver = ContradictionResolver()
        result = await resolver.detect_contradictions(evidence_list)

        # Should return empty list
        assert len(result) == 0


class TestLLMNullIndexHandling:
    """Test that LLM returning None/invalid indices doesn't crash.

    Regression tests for TypeError: '<=' not supported between
    instances of 'int' and 'NoneType'.
    """

    @staticmethod
    def _make_evidence(memory_id: str, content: str) -> MemoryEvidence:
        return MemoryEvidence(
            memory_id=memory_id,
            content=content,
            source_type="user_knowledge",
            retrieval_score=0.9,
            embedding_quality=0.9,
            timestamp=datetime.now(UTC),
            session_id="session-null",
            memory_type="fact",
            importance="high",
        )

    @pytest.mark.asyncio
    async def test_llm_returns_null_id1(self):
        """LLM returns null for id1 — must not crash."""
        mock_llm = MagicMock()
        mock_llm.ask = AsyncMock(
            return_value={"content": '{"contradictions": [{"id1": null, "id2": 1, "reason": "test"}]}'}
        )
        evidence_list = [
            self._make_evidence("mem-a", "Fact A"),
            self._make_evidence("mem-b", "Fact B"),
        ]
        resolver = ContradictionResolver(llm=mock_llm)
        result = await resolver.detect_contradictions(evidence_list)

        # Should not crash and no contradictions should be marked
        assert len(result[0].contradictions) == 0
        assert len(result[1].contradictions) == 0

    @pytest.mark.asyncio
    async def test_llm_returns_null_id2(self):
        """LLM returns null for id2 — must not crash."""
        mock_llm = MagicMock()
        mock_llm.ask = AsyncMock(
            return_value={"content": '{"contradictions": [{"id1": 0, "id2": null, "reason": "test"}]}'}
        )
        evidence_list = [
            self._make_evidence("mem-a", "Fact A"),
            self._make_evidence("mem-b", "Fact B"),
        ]
        resolver = ContradictionResolver(llm=mock_llm)
        result = await resolver.detect_contradictions(evidence_list)

        assert len(result[0].contradictions) == 0
        assert len(result[1].contradictions) == 0

    @pytest.mark.asyncio
    async def test_llm_returns_missing_id_keys(self):
        """LLM omits id1/id2 keys entirely — must not crash."""
        mock_llm = MagicMock()
        mock_llm.ask = AsyncMock(return_value={"content": '{"contradictions": [{"reason": "they conflict"}]}'})
        evidence_list = [
            self._make_evidence("mem-a", "Fact A"),
            self._make_evidence("mem-b", "Fact B"),
        ]
        resolver = ContradictionResolver(llm=mock_llm)
        result = await resolver.detect_contradictions(evidence_list)

        assert len(result[0].contradictions) == 0
        assert len(result[1].contradictions) == 0

    @pytest.mark.asyncio
    async def test_llm_returns_string_indices(self):
        """LLM returns string numbers — should coerce to int and work."""
        mock_llm = MagicMock()
        mock_llm.ask = AsyncMock(
            return_value={"content": '{"contradictions": [{"id1": "0", "id2": "1", "reason": "conflict"}]}'}
        )
        evidence_list = [
            self._make_evidence("mem-a", "Fact A"),
            self._make_evidence("mem-b", "Fact B"),
        ]
        resolver = ContradictionResolver(llm=mock_llm)
        result = await resolver.detect_contradictions(evidence_list)

        # String "0" and "1" should be coerced and work
        assert "mem-b" in result[0].contradictions
        assert "mem-a" in result[1].contradictions

    @pytest.mark.asyncio
    async def test_llm_returns_out_of_range_indices(self):
        """LLM returns indices beyond evidence list — skip silently."""
        mock_llm = MagicMock()
        mock_llm.ask = AsyncMock(
            return_value={"content": '{"contradictions": [{"id1": 0, "id2": 99, "reason": "conflict"}]}'}
        )
        evidence_list = [
            self._make_evidence("mem-a", "Fact A"),
            self._make_evidence("mem-b", "Fact B"),
        ]
        resolver = ContradictionResolver(llm=mock_llm)
        result = await resolver.detect_contradictions(evidence_list)

        assert len(result[0].contradictions) == 0
        assert len(result[1].contradictions) == 0

    @pytest.mark.asyncio
    async def test_llm_returns_self_contradiction(self):
        """LLM returns id1 == id2 — skip self-contradiction."""
        mock_llm = MagicMock()
        mock_llm.ask = AsyncMock(
            return_value={"content": '{"contradictions": [{"id1": 0, "id2": 0, "reason": "self-conflict"}]}'}
        )
        evidence_list = [
            self._make_evidence("mem-a", "Fact A"),
            self._make_evidence("mem-b", "Fact B"),
        ]
        resolver = ContradictionResolver(llm=mock_llm)
        result = await resolver.detect_contradictions(evidence_list)

        assert len(result[0].contradictions) == 0

    @pytest.mark.asyncio
    async def test_llm_returns_negative_index(self):
        """LLM returns negative index — skip silently."""
        mock_llm = MagicMock()
        mock_llm.ask = AsyncMock(
            return_value={"content": '{"contradictions": [{"id1": -1, "id2": 0, "reason": "test"}]}'}
        )
        evidence_list = [
            self._make_evidence("mem-a", "Fact A"),
            self._make_evidence("mem-b", "Fact B"),
        ]
        resolver = ContradictionResolver(llm=mock_llm)
        result = await resolver.detect_contradictions(evidence_list)

        assert len(result[0].contradictions) == 0

    @pytest.mark.asyncio
    async def test_llm_returns_non_numeric_string_index(self):
        """LLM returns 'first' instead of 0 — skip silently."""
        mock_llm = MagicMock()
        mock_llm.ask = AsyncMock(
            return_value={"content": '{"contradictions": [{"id1": "first", "id2": "second", "reason": "test"}]}'}
        )
        evidence_list = [
            self._make_evidence("mem-a", "Fact A"),
            self._make_evidence("mem-b", "Fact B"),
        ]
        resolver = ContradictionResolver(llm=mock_llm)
        result = await resolver.detect_contradictions(evidence_list)

        assert len(result[0].contradictions) == 0
        assert len(result[1].contradictions) == 0


class TestNumericZeroDivision:
    """Test that zero-valued numeric claims don't cause ZeroDivisionError."""

    @pytest.mark.asyncio
    async def test_both_values_zero(self):
        """Two claims with value 0 — must not crash with ZeroDivisionError."""
        evidence_list = [
            MemoryEvidence(
                memory_id="mem-z1",
                content="The count is 0 items",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-z1",
                memory_type="fact",
                importance="high",
            ),
            MemoryEvidence(
                memory_id="mem-z2",
                content="The count is 0 items",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-z2",
                memory_type="fact",
                importance="high",
            ),
        ]
        resolver = ContradictionResolver()
        result = await resolver.detect_contradictions(evidence_list)

        # Same value — no contradiction
        assert len(result[0].contradictions) == 0

    @pytest.mark.asyncio
    async def test_one_value_zero_other_nonzero(self):
        """One claim is 0, other is nonzero — detects contradiction without crash."""
        evidence_list = [
            MemoryEvidence(
                memory_id="mem-z3",
                content="The score is 0 points",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-z3",
                memory_type="fact",
                importance="high",
            ),
            MemoryEvidence(
                memory_id="mem-z4",
                content="The score is 50 points",
                source_type="user_knowledge",
                retrieval_score=0.9,
                embedding_quality=0.9,
                timestamp=datetime.now(UTC),
                session_id="session-z4",
                memory_type="fact",
                importance="high",
            ),
        ]
        resolver = ContradictionResolver()
        result = await resolver.detect_contradictions(evidence_list)

        # 0 vs 50 is a 100% difference — should detect contradiction
        assert "mem-z4" in result[0].contradictions
        assert "mem-z3" in result[1].contradictions
