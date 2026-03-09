"""Tests for deal search title relevance matching."""

from app.infrastructure.external.deal_finder.adapter import _title_matches_query


class TestTitleMatchesQuery:
    """Verify multi-signal relevance filter."""

    # ── Should MATCH ──

    def test_exact_phrase_match(self):
        assert _title_matches_query("Buy GLM 5 AI at Best Price", "GLM 5 AI")

    def test_majority_word_match(self):
        assert _title_matches_query("Sony WH-1000XM5 Headphones", "Sony WH-1000XM5 Black")

    def test_single_word_query(self):
        assert _title_matches_query("PlayStation 5 Console", "PlayStation")

    def test_case_insensitive(self):
        assert _title_matches_query("glm-5 ai model pricing", "GLM 5 AI")

    # ── Should NOT match ──

    def test_rejects_single_word_overlap_on_multiword_query(self):
        """Only 1 of 3 words matching should fail (33% < 50%)."""
        assert not _title_matches_query("Green Lipped Mussel Supplement", "GLM 5 AI")

    def test_rejects_numeric_mismatch(self):
        """Query has '5' but title has '400' — numeric token enforcement."""
        assert not _title_matches_query("Bosch GLM 400C Laser Measure", "GLM 5 AI")

    def test_rejects_completely_unrelated(self):
        assert not _title_matches_query("Organic Dog Food Premium", "GLM 5 AI")

    def test_empty_inputs(self):
        assert not _title_matches_query("", "GLM 5 AI")
        assert not _title_matches_query("Some Title", "")

    def test_all_stop_words_query(self):
        assert not _title_matches_query("The Best Deal Ever", "the best")

    def test_numeric_token_present_in_both(self):
        assert _title_matches_query("GLM 5 for Developers Book", "GLM 5 AI")

    def test_numeric_token_absent_from_title(self):
        assert not _title_matches_query("GLM AI Model Overview", "GLM 5 AI")
