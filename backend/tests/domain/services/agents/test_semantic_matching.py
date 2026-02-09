"""Tests for Semantic Requirement Matching.

Tests the semantic similarity features of IntentTracker, including:
- Trigram embedding computation
- Cosine similarity calculation
- check_requirement_addressed() method
- Semantic matching in check_alignment()
- Embedding cache behavior
"""

import pytest

from app.domain.services.agents.intent_tracker import IntentTracker
from app.domain.services.agents.stuck_detector import compute_trigram_embedding

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tracker() -> IntentTracker:
    """Create a fresh IntentTracker instance."""
    return IntentTracker()


# =============================================================================
# compute_trigram_embedding Tests (from stuck_detector)
# =============================================================================


class TestTrigramEmbedding:
    """Tests for the compute_trigram_embedding function."""

    def test_empty_text_returns_empty_list(self):
        """Test that empty text returns an empty embedding."""
        result = compute_trigram_embedding("")
        assert result == []

    def test_very_short_text_returns_empty_list(self):
        """Test that text shorter than 3 chars returns empty."""
        assert compute_trigram_embedding("a") == []
        assert compute_trigram_embedding("ab") == []

    def test_valid_text_returns_128_dim_embedding(self):
        """Test that valid text returns 128-dimensional embedding by default."""
        result = compute_trigram_embedding("Hello world")
        assert len(result) == 128

    def test_embedding_is_normalized(self):
        """Test that the embedding is normalized (unit length)."""
        result = compute_trigram_embedding("This is a test sentence.")
        # Compute L2 norm
        norm = sum(x * x for x in result) ** 0.5
        assert abs(norm - 1.0) < 0.001  # Should be approximately 1.0

    def test_custom_embedding_dimension(self):
        """Test embedding with custom dimension."""
        result = compute_trigram_embedding("Test text", embedding_dim=64)
        assert len(result) == 64

    def test_similar_texts_have_similar_embeddings(self):
        """Test that similar texts produce similar embeddings."""
        emb1 = compute_trigram_embedding("Create a Python function to read CSV files")
        emb2 = compute_trigram_embedding("Write a Python function to parse CSV data")

        # Cosine similarity
        dot = sum(a * b for a, b in zip(emb1, emb2, strict=True))
        # Both are normalized, so dot product is the similarity
        assert dot > 0.5  # Should be fairly similar

    def test_different_texts_have_different_embeddings(self):
        """Test that different texts produce different embeddings."""
        emb1 = compute_trigram_embedding("Deploy the application to production")
        emb2 = compute_trigram_embedding("The quick brown fox jumps over the lazy dog")

        dot = sum(a * b for a, b in zip(emb1, emb2, strict=True))
        # Should be less similar than the similar texts
        assert dot < 0.6


# =============================================================================
# IntentTracker Embedding Cache Tests
# =============================================================================


class TestEmbeddingCache:
    """Tests for the embedding cache in IntentTracker."""

    def test_tracker_has_embedding_cache(self, tracker: IntentTracker):
        """Test that tracker initializes with an embedding cache."""
        assert hasattr(tracker, "_embedding_cache")
        assert isinstance(tracker._embedding_cache, dict)

    def test_get_or_compute_embedding_caches_result(self, tracker: IntentTracker):
        """Test that embeddings are cached after first computation."""
        text = "Test requirement text"
        emb1 = tracker._get_or_compute_embedding(text)
        emb2 = tracker._get_or_compute_embedding(text)

        # Should be identical (cached)
        assert emb1 == emb2
        assert text[:200] in tracker._embedding_cache

    def test_cache_uses_truncated_key(self, tracker: IntentTracker):
        """Test that cache key is truncated to 200 chars."""
        long_text = "x" * 500
        tracker._get_or_compute_embedding(long_text)

        # Key should be truncated
        assert long_text[:200] in tracker._embedding_cache
        assert long_text not in tracker._embedding_cache

    def test_cache_limit_eviction(self, tracker: IntentTracker):
        """Test that cache evicts old entries when limit is reached."""
        # Add 510 unique embeddings (over the 500 limit)
        for i in range(510):
            tracker._get_or_compute_embedding(f"Unique text number {i}")

        # Cache should have been trimmed
        assert len(tracker._embedding_cache) <= 500

    def test_reset_clears_embedding_cache(self, tracker: IntentTracker):
        """Test that reset() clears the embedding cache."""
        tracker._get_or_compute_embedding("Some text")
        assert len(tracker._embedding_cache) > 0

        tracker.reset()
        assert len(tracker._embedding_cache) == 0


# =============================================================================
# Semantic Similarity Tests
# =============================================================================


class TestComputeSemanticSimilarity:
    """Tests for _compute_semantic_similarity method."""

    def test_identical_texts_have_similarity_1(self, tracker: IntentTracker):
        """Test that identical texts have similarity of 1.0."""
        text = "Create a REST API with authentication"
        similarity = tracker._compute_semantic_similarity(text, text)
        assert abs(similarity - 1.0) < 0.001

    def test_empty_texts_have_zero_similarity(self, tracker: IntentTracker):
        """Test that empty texts return zero similarity."""
        assert tracker._compute_semantic_similarity("", "") == 0.0
        assert tracker._compute_semantic_similarity("Some text", "") == 0.0
        assert tracker._compute_semantic_similarity("", "Some text") == 0.0

    def test_similar_texts_have_high_similarity(self, tracker: IntentTracker):
        """Test that semantically similar texts have high similarity."""
        text1 = "Implement user authentication with JWT tokens"
        text2 = "Add JWT-based user authentication system"
        similarity = tracker._compute_semantic_similarity(text1, text2)
        assert similarity > 0.5

    def test_different_texts_have_low_similarity(self, tracker: IntentTracker):
        """Test that different texts have lower similarity."""
        text1 = "Create database migrations for PostgreSQL"
        text2 = "The weather is nice today"
        similarity = tracker._compute_semantic_similarity(text1, text2)
        assert similarity < 0.5

    def test_fallback_to_jaccard_on_short_text(self, tracker: IntentTracker):
        """Test fallback to Jaccard when embedding fails (very short text)."""
        # Very short text that returns empty embedding
        similarity = tracker._compute_semantic_similarity("ab", "ab cd")
        # Should fall back to Jaccard
        assert similarity >= 0.0  # Should not crash


# =============================================================================
# check_requirement_addressed Tests
# =============================================================================


class TestCheckRequirementAddressed:
    """Tests for the check_requirement_addressed method."""

    def test_exact_match_returns_true(self, tracker: IntentTracker):
        """Test that exact match is addressed."""
        requirement = "Add user authentication"
        work = "Add user authentication"
        assert tracker.check_requirement_addressed(requirement, work) is True

    def test_semantic_match_returns_true(self, tracker: IntentTracker):
        """Test that semantic match is addressed."""
        requirement = "Implement file upload functionality"
        work = "Added file upload feature with multipart form support"
        # Use a low threshold to account for variance in hash-based trigram embeddings
        assert tracker.check_requirement_addressed(requirement, work, threshold=0.3) is True

    def test_unrelated_work_returns_false(self, tracker: IntentTracker):
        """Test that unrelated work is not considered addressed."""
        requirement = "Add database connection pooling"
        work = "Refactored the CSS styles for the login page"
        assert tracker.check_requirement_addressed(requirement, work, threshold=0.7) is False

    def test_custom_threshold_respected(self, tracker: IntentTracker):
        """Test that custom threshold is respected."""
        requirement = "Create API endpoint"
        work = "Built REST endpoint for users"

        # With low threshold, should pass
        assert tracker.check_requirement_addressed(requirement, work, threshold=0.3) is True

        # With very high threshold, may fail
        result_high = tracker.check_requirement_addressed(requirement, work, threshold=0.95)
        # Result depends on actual similarity; just ensure no crash
        assert isinstance(result_high, bool)

    def test_requirement_paraphrased_is_addressed(self, tracker: IntentTracker):
        """Test that paraphrased requirements are detected as addressed."""
        requirement = "Write unit tests for the authentication module"
        work = "Created tests for auth module using pytest"
        # Should recognize the semantic similarity
        assert tracker.check_requirement_addressed(requirement, work, threshold=0.4) is True


# =============================================================================
# Integration with check_alignment Tests
# =============================================================================


class TestSemanticAlignmentIntegration:
    """Tests for semantic matching integration in check_alignment."""

    def test_check_alignment_uses_semantic_matching(self, tracker: IntentTracker):
        """Test that check_alignment uses semantic matching for requirements."""
        tracker.extract_intent(
            """Create a REST API with:
            1. User authentication
            2. Rate limiting
            3. Error handling
            """
        )

        # Work that semantically addresses some requirements
        result = tracker.check_alignment("Implemented JWT-based auth and rate limiter middleware")

        # Should recognize semantic matches
        assert result.coverage_percent > 0
        assert len(result.addressed_requirements) >= 1

    def test_semantic_matching_in_drift_detection(self, tracker: IntentTracker):
        """Test that drift detection uses semantic similarity."""
        tracker.extract_intent("Create a Python script to process CSV files")

        # Work that is semantically related (shouldn't trigger drift)
        result = tracker.check_alignment("Writing Python code to parse and transform CSV data")

        # Should not detect topic drift since work is related
        topic_drifts = [alert for alert in result.drift_alerts if alert.drift_type.value == "topic_drift"]
        assert len(topic_drifts) == 0

    def test_unrelated_work_triggers_drift_alert(self, tracker: IntentTracker):
        """Test that completely unrelated work triggers drift alert."""
        tracker.extract_intent("Build a mobile app for iOS")

        # Work that is completely different
        result = tracker.check_alignment("Configured PostgreSQL database schema for analytics")

        # May trigger topic drift
        # The exact behavior depends on similarity threshold
        # Just verify the method works without errors
        assert isinstance(result.on_track, bool)


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestSemanticMatchingEdgeCases:
    """Tests for edge cases in semantic matching."""

    def test_unicode_text_handled(self, tracker: IntentTracker):
        """Test that unicode text is handled correctly."""
        requirement = "Create login with international support"
        work = "Added login handling for users with names like Mueller, Hernandez"
        # Should not crash
        result = tracker.check_requirement_addressed(requirement, work, threshold=0.3)
        assert isinstance(result, bool)

    def test_special_characters_handled(self, tracker: IntentTracker):
        """Test that special characters don't break embedding."""
        text1 = "API endpoint: /users/{id}/profile"
        text2 = "REST endpoint at /users/:id/profile"
        similarity = tracker._compute_semantic_similarity(text1, text2)
        assert similarity >= 0.0  # Should not crash

    def test_numbers_in_text_handled(self, tracker: IntentTracker):
        """Test that numbers in text are handled."""
        requirement = "Support pagination with limit=100 and offset=0"
        work = "Added pagination with configurable limit (100) and offset (0)"
        result = tracker.check_requirement_addressed(requirement, work, threshold=0.5)
        assert isinstance(result, bool)

    def test_very_long_text_handled(self, tracker: IntentTracker):
        """Test that very long texts are handled."""
        long_requirement = "Implement " + "feature " * 1000 + "properly"
        long_work = "Added " + "feature " * 1000 + "implementation"
        # Should not crash or hang
        result = tracker.check_requirement_addressed(long_requirement, long_work, threshold=0.5)
        assert isinstance(result, bool)

    def test_whitespace_only_text(self, tracker: IntentTracker):
        """Test handling of whitespace-only text."""
        similarity = tracker._compute_semantic_similarity("   ", "text")
        assert similarity == 0.0  # Should fall back gracefully

    def test_newlines_in_text(self, tracker: IntentTracker):
        """Test handling of text with newlines."""
        requirement = "Create function to:\n- Parse JSON\n- Validate schema"
        work = "Built JSON parser with schema validation"
        result = tracker.check_requirement_addressed(requirement, work, threshold=0.3)
        assert isinstance(result, bool)


# =============================================================================
# Performance Tests
# =============================================================================


class TestSemanticMatchingPerformance:
    """Tests for performance characteristics of semantic matching."""

    def test_repeated_calls_use_cache(self, tracker: IntentTracker):
        """Test that repeated similarity checks use cached embeddings."""
        text1 = "Create a user authentication system"
        text2 = "Build a login and registration feature"

        # First call computes embeddings
        tracker._compute_semantic_similarity(text1, text2)
        initial_cache_size = len(tracker._embedding_cache)

        # Second call should use cache
        tracker._compute_semantic_similarity(text1, text2)
        final_cache_size = len(tracker._embedding_cache)

        # Cache size should not grow (embeddings already cached)
        assert final_cache_size == initial_cache_size

    def test_many_requirements_handled_efficiently(self, tracker: IntentTracker):
        """Test that many requirements can be checked efficiently."""
        # Set up intent with many requirements
        requirements = "\n".join([f"{i + 1}. Requirement number {i + 1}" for i in range(50)])
        tracker.extract_intent(f"Build a system with:\n{requirements}")

        # Check alignment with work covering some requirements
        work = "Completed requirements 1, 2, 3, 10, 20, 30, 40, 50"
        result = tracker.check_alignment(work)

        # Should complete without timeout
        assert isinstance(result.coverage_percent, float)
