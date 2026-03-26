"""
Unit tests for ImportanceAnalyzer and ImportanceScore.

Covers:
- Role-based base scoring for all known roles
- Unknown roles default score
- Recent-message boost logic (preserve_recent boundary)
- High-signal keyword detection and additive scoring
- Score clamping at 1.0 (max)
- is_low_importance static method with default and custom thresholds
- Reason list construction (role tag, recent tag, keyword tags)
- Edge cases: empty content, None content, empty message dict
"""

from __future__ import annotations

import pytest

from app.domain.services.agents.memory.importance_analyzer import (
    ImportanceAnalyzer,
    ImportanceScore,
)


# ---------------------------------------------------------------------------
# ImportanceScore dataclass
# ---------------------------------------------------------------------------


class TestImportanceScore:
    """Tests for the ImportanceScore dataclass."""

    def test_score_stores_float(self):
        s = ImportanceScore(score=0.75)
        assert s.score == 0.75

    def test_reasons_defaults_to_empty_list(self):
        s = ImportanceScore(score=0.5)
        assert s.reasons == []

    def test_reasons_accepts_list(self):
        s = ImportanceScore(score=0.9, reasons=["role:system", "recent"])
        assert s.reasons == ["role:system", "recent"]

    def test_score_zero_is_valid(self):
        s = ImportanceScore(score=0.0)
        assert s.score == 0.0

    def test_score_one_is_valid(self):
        s = ImportanceScore(score=1.0)
        assert s.score == 1.0


# ---------------------------------------------------------------------------
# ImportanceAnalyzer.score_message — role-based base scores
# ---------------------------------------------------------------------------


class TestScoreMessageRoleBase:
    """Role-based base score assigned before keyword/recency boosts."""

    @pytest.fixture
    def analyzer(self) -> ImportanceAnalyzer:
        return ImportanceAnalyzer()

    def _score(
        self,
        analyzer: ImportanceAnalyzer,
        role: str,
        index: int = 0,
        total: int = 100,
        preserve_recent: int = 0,
    ) -> float:
        """Helper: score a minimal message at a non-recent position."""
        msg = {"role": role, "content": ""}
        return analyzer.score_message(msg, index, total, preserve_recent).score

    def test_system_role_base_score(self, analyzer):
        score = self._score(analyzer, "system")
        assert score == pytest.approx(0.9)

    def test_user_role_base_score(self, analyzer):
        score = self._score(analyzer, "user")
        assert score == pytest.approx(0.85)

    def test_assistant_role_base_score(self, analyzer):
        score = self._score(analyzer, "assistant")
        assert score == pytest.approx(0.6)

    def test_tool_role_base_score(self, analyzer):
        score = self._score(analyzer, "tool")
        assert score == pytest.approx(0.3)

    def test_unknown_role_defaults_to_0_5(self, analyzer):
        score = self._score(analyzer, "unknown_role")
        assert score == pytest.approx(0.5)

    def test_empty_string_role_defaults_to_0_5(self, analyzer):
        score = self._score(analyzer, "")
        assert score == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# ImportanceAnalyzer.score_message — reasons list
# ---------------------------------------------------------------------------


class TestScoreMessageReasons:
    """Reason tags appended to ImportanceScore.reasons."""

    @pytest.fixture
    def analyzer(self) -> ImportanceAnalyzer:
        return ImportanceAnalyzer()

    def test_role_tag_always_present(self, analyzer):
        msg = {"role": "user", "content": ""}
        result = analyzer.score_message(msg, 0, 100, 0)
        assert "role:user" in result.reasons

    def test_role_tag_reflects_message_role(self, analyzer):
        msg = {"role": "system", "content": ""}
        result = analyzer.score_message(msg, 0, 100, 0)
        assert "role:system" in result.reasons

    def test_recent_tag_added_when_in_window(self, analyzer):
        msg = {"role": "tool", "content": ""}
        # index 95, total 100, preserve_recent 10 → recent window starts at 90
        result = analyzer.score_message(msg, 95, 100, 10)
        assert "recent" in result.reasons

    def test_recent_tag_absent_when_outside_window(self, analyzer):
        msg = {"role": "tool", "content": ""}
        # index 5 is well outside the recent-10 window of a 100-message list
        result = analyzer.score_message(msg, 5, 100, 10)
        assert "recent" not in result.reasons

    def test_keyword_tag_added_for_matching_keyword(self, analyzer):
        msg = {"role": "assistant", "content": "The plan is to proceed."}
        result = analyzer.score_message(msg, 0, 100, 0)
        assert "kw:plan" in result.reasons

    def test_multiple_keyword_tags_added(self, analyzer):
        msg = {"role": "assistant", "content": "The goal failed with an error."}
        result = analyzer.score_message(msg, 0, 100, 0)
        assert "kw:goal" in result.reasons
        assert "kw:failed" in result.reasons
        assert "kw:error" in result.reasons

    def test_no_keyword_tags_when_no_keywords_present(self, analyzer):
        msg = {"role": "assistant", "content": "All is going well."}
        result = analyzer.score_message(msg, 0, 100, 0)
        kw_tags = [r for r in result.reasons if r.startswith("kw:")]
        assert kw_tags == []


# ---------------------------------------------------------------------------
# ImportanceAnalyzer.score_message — recency boost
# ---------------------------------------------------------------------------


class TestScoreMessageRecencyBoost:
    """Recent-message floor at 0.8."""

    @pytest.fixture
    def analyzer(self) -> ImportanceAnalyzer:
        return ImportanceAnalyzer()

    def test_tool_message_in_recent_window_gets_boosted_to_0_8(self, analyzer):
        """Tool base is 0.3; recent boost should floor it to 0.8."""
        msg = {"role": "tool", "content": ""}
        result = analyzer.score_message(msg, 95, 100, 10)
        assert result.score == pytest.approx(0.8)

    def test_system_message_in_recent_window_stays_above_0_8(self, analyzer):
        """System base 0.9 already above 0.8 floor; should stay at 0.9."""
        msg = {"role": "system", "content": ""}
        result = analyzer.score_message(msg, 95, 100, 10)
        assert result.score == pytest.approx(0.9)

    def test_boundary_exactly_at_recent_threshold(self, analyzer):
        """Message at index == total - preserve_recent is still recent."""
        msg = {"role": "tool", "content": ""}
        # total=20, preserve_recent=5 → threshold index is 15
        result = analyzer.score_message(msg, 15, 20, 5)
        assert result.score == pytest.approx(0.8)
        assert "recent" in result.reasons

    def test_one_before_boundary_is_not_recent(self, analyzer):
        """Message at index == total - preserve_recent - 1 is NOT recent."""
        msg = {"role": "tool", "content": ""}
        # total=20, preserve_recent=5 → threshold=15; index 14 is outside
        result = analyzer.score_message(msg, 14, 20, 5)
        assert "recent" not in result.reasons
        assert result.score == pytest.approx(0.3)

    def test_preserve_recent_zero_means_no_recency_boost(self, analyzer):
        """preserve_recent=0 → max(0, total-0)=total → no message qualifies."""
        msg = {"role": "tool", "content": ""}
        result = analyzer.score_message(msg, 99, 100, 0)
        assert "recent" not in result.reasons


# ---------------------------------------------------------------------------
# ImportanceAnalyzer.score_message — keyword scoring
# ---------------------------------------------------------------------------


class TestScoreMessageKeywords:
    """Each matched keyword adds +0.05 to the score."""

    @pytest.fixture
    def analyzer(self) -> ImportanceAnalyzer:
        return ImportanceAnalyzer()

    def test_single_keyword_adds_0_05(self, analyzer):
        msg = {"role": "assistant", "content": "There was an error in step 3."}
        result = analyzer.score_message(msg, 0, 100, 0)
        # assistant base = 0.6, + 0.05 for "error"
        assert result.score == pytest.approx(0.65)

    def test_keywords_are_case_insensitive(self, analyzer):
        msg = {"role": "assistant", "content": "ERROR detected."}
        result = analyzer.score_message(msg, 0, 100, 0)
        assert "kw:error" in result.reasons

    def test_all_high_signal_keywords_recognized(self, analyzer):
        keywords = [
            "decision",
            "plan",
            "goal",
            "blocked",
            "dependency",
            "result",
            "summary",
            "error",
            "failed",
            "success",
            "verification",
        ]
        for kw in keywords:
            msg = {"role": "tool", "content": f"This contains {kw} information."}
            result = analyzer.score_message(msg, 0, 100, 0)
            assert f"kw:{kw}" in result.reasons, f"Expected kw:{kw} in reasons"

    def test_score_capped_at_1_0(self, analyzer):
        """Even with many keywords the score must not exceed 1.0."""
        content = " ".join(
            ["decision", "plan", "goal", "blocked", "dependency", "result", "summary", "error", "failed", "success", "verification"]
        )
        msg = {"role": "system", "content": content}
        # system base = 0.9, 11 keywords * 0.05 = 0.55 → would be 1.45 uncapped
        result = analyzer.score_message(msg, 0, 100, 0)
        assert result.score == pytest.approx(1.0)

    def test_keyword_substring_match_works(self, analyzer):
        """Keywords are matched as substrings of lowercased content."""
        msg = {"role": "assistant", "content": "re-verification complete"}
        result = analyzer.score_message(msg, 0, 100, 0)
        assert "kw:verification" in result.reasons


# ---------------------------------------------------------------------------
# ImportanceAnalyzer.score_message — edge cases
# ---------------------------------------------------------------------------


class TestScoreMessageEdgeCases:
    """Edge cases: missing keys, None, empty message."""

    @pytest.fixture
    def analyzer(self) -> ImportanceAnalyzer:
        return ImportanceAnalyzer()

    def test_empty_message_dict_uses_defaults(self, analyzer):
        """Empty dict → role defaults to 'assistant', content defaults to ''."""
        result = analyzer.score_message({}, 0, 10, 0)
        assert result.score == pytest.approx(0.6)
        assert "role:assistant" in result.reasons

    def test_none_content_treated_as_empty_string(self, analyzer):
        """content=None should not raise; str(None) == 'None' matches nothing."""
        msg = {"role": "tool", "content": None}
        result = analyzer.score_message(msg, 0, 10, 0)
        # 'none' is not a keyword so no keyword boost
        assert result.score == pytest.approx(0.3)

    def test_total_zero_no_crash(self, analyzer):
        """total=0 should not crash (max(0, 0-10)=0, so index>=0 is recent)."""
        msg = {"role": "tool", "content": ""}
        result = analyzer.score_message(msg, 0, 0, 10)
        # index 0 >= max(0, 0-10)=0 → recent
        assert result.score == pytest.approx(0.8)

    def test_very_long_content_does_not_crash(self, analyzer):
        msg = {"role": "assistant", "content": "x" * 100_000}
        result = analyzer.score_message(msg, 0, 100, 0)
        assert 0.0 <= result.score <= 1.0

    def test_numeric_content_coerced_to_string(self, analyzer):
        msg = {"role": "assistant", "content": 12345}
        result = analyzer.score_message(msg, 0, 100, 0)
        assert isinstance(result.score, float)


# ---------------------------------------------------------------------------
# ImportanceAnalyzer.is_low_importance — static method
# ---------------------------------------------------------------------------


class TestIsLowImportance:
    """Static method for threshold gate."""

    def test_score_below_threshold_is_low(self):
        assert ImportanceAnalyzer.is_low_importance(0.3) is True

    def test_score_equal_to_threshold_is_not_low(self):
        # strictly less-than: score < threshold
        assert ImportanceAnalyzer.is_low_importance(0.5) is False

    def test_score_above_threshold_is_not_low(self):
        assert ImportanceAnalyzer.is_low_importance(0.8) is False

    def test_custom_threshold_respected(self):
        assert ImportanceAnalyzer.is_low_importance(0.55, threshold=0.6) is True
        assert ImportanceAnalyzer.is_low_importance(0.65, threshold=0.6) is False

    def test_threshold_zero_means_nothing_is_low(self):
        # score=0.0 is NOT strictly less than 0.0
        assert ImportanceAnalyzer.is_low_importance(0.0, threshold=0.0) is False

    def test_score_one_is_never_low_with_default_threshold(self):
        assert ImportanceAnalyzer.is_low_importance(1.0) is False

    def test_threshold_one_makes_everything_except_one_low(self):
        assert ImportanceAnalyzer.is_low_importance(0.99, threshold=1.0) is True
        assert ImportanceAnalyzer.is_low_importance(1.0, threshold=1.0) is False


# ---------------------------------------------------------------------------
# ImportanceAnalyzer — class variables are read-only (not mutable state)
# ---------------------------------------------------------------------------


class TestClassVariableImmutability:
    """Ensure _ROLE_BASE is shared but read correctly across instances."""

    def test_two_instances_share_same_role_base(self):
        a = ImportanceAnalyzer()
        b = ImportanceAnalyzer()
        assert a._ROLE_BASE is b._ROLE_BASE

    def test_role_base_contains_expected_keys(self):
        expected = {"system", "user", "assistant", "tool"}
        assert set(ImportanceAnalyzer._ROLE_BASE.keys()) == expected
