"""Unit tests for SynthesisGuard — pre-synthesis quality gate.

Tests cover:
- Pass conditions: enough good sources, including official and independent
- Hard fail conditions: too few sources, too few high-confidence, failed counts
- Relaxation: niche topic (<5 results), all-official-failed, relaxation disabled
- Soft fail: missing official with enough good sources
- Threshold recording: thresholds_applied dict has expected keys
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from app.domain.models.evidence import (
    AccessMethod,
    ConfidenceBucket,
    EvidenceRecord,
    QueryContext,
    SourceType,
    SynthesisGateVerdict,
)
from app.domain.services.agents.synthesis_guard import SynthesisGuard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)


def _record(
    source_type: SourceType = SourceType.independent,
    confidence: ConfidenceBucket = ConfidenceBucket.high,
    content_length: int = 5000,
    **kw: Any,
) -> EvidenceRecord:
    """Build an EvidenceRecord with sensible defaults."""
    defaults: dict[str, Any] = {
        "url": f"https://example.com/{source_type}/{confidence}",
        "domain": "example.com",
        "title": "Test Source",
        "source_type": source_type,
        "authority_score": 0.8,
        "source_importance": "high",
        "excerpt": "Some content excerpt.",
        "content_length": content_length,
        "access_method": AccessMethod.scrapling_http,
        "fetch_tier_reached": 1,
        "extraction_duration_ms": 200,
        "timestamp": _NOW,
        "confidence_bucket": confidence,
        "hard_fail_reasons": [],
        "soft_fail_reasons": [],
        "soft_point_total": 0,
    }
    defaults.update(kw)
    return EvidenceRecord(**defaults)


def _config(
    min_fetched: int = 3,
    min_high: int = 2,
    require_official: bool = True,
    require_independent: bool = True,
    relaxation_enabled: bool = True,
    relaxed_min_fetched: int = 2,
    relaxed_min_high: int = 1,
    relaxed_require_official: bool = False,
) -> SimpleNamespace:
    """Build a minimal config namespace matching what SynthesisGuard expects."""
    return SimpleNamespace(
        research_min_fetched_sources=min_fetched,
        research_min_high_confidence=min_high,
        research_require_official_source=require_official,
        research_require_independent_source=require_independent,
        research_relaxation_enabled=relaxation_enabled,
        research_relaxed_min_fetched_sources=relaxed_min_fetched,
        research_relaxed_min_high_confidence=relaxed_min_high,
        research_relaxed_require_official_source=relaxed_require_official,
    )


# ---------------------------------------------------------------------------
# TestPassConditions
# ---------------------------------------------------------------------------


class TestPassConditions:
    """Gate should PASS when evidence meets all default thresholds."""

    def test_pass_with_four_good_sources(self) -> None:
        """4 successful sources: 1 official, 2 independent, 1 authoritative_neutral."""
        cfg = _config()
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.official, confidence=ConfidenceBucket.high),
            _record(source_type=SourceType.independent, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://b.com/",
                domain="b.com",
            ),
            _record(
                source_type=SourceType.authoritative_neutral,
                confidence=ConfidenceBucket.medium,
                url="https://c.com/",
                domain="c.com",
            ),
        ]
        result = guard.evaluate(evidence, total_search_results=20)

        assert result.verdict == SynthesisGateVerdict.pass_
        assert result.reasons == []
        assert result.total_fetched == 4
        assert result.official_source_found is True
        assert result.independent_source_found is True

    def test_pass_counts_only_successful_sources(self) -> None:
        """Failed (content_length=0) records are excluded from fetched count."""
        cfg = _config(min_fetched=3, min_high=2)
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.official, confidence=ConfidenceBucket.high),
            _record(source_type=SourceType.independent, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://b.com/",
                domain="b.com",
            ),
            # Failed record — should not count toward fetched
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.low,
                content_length=0,
                url="https://fail.com/",
                domain="fail.com",
            ),
        ]
        result = guard.evaluate(evidence, total_search_results=20)

        assert result.verdict == SynthesisGateVerdict.pass_
        assert result.total_fetched == 3

    def test_pass_authoritative_neutral_counts_as_independent(self) -> None:
        """AUTHORITATIVE_NEUTRAL satisfies the independent source requirement."""
        cfg = _config(require_independent=True)
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.official, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.authoritative_neutral,
                confidence=ConfidenceBucket.high,
                url="https://neutral.org/",
                domain="neutral.org",
            ),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.medium,
                url="https://d.com/",
                domain="d.com",
            ),
        ]
        result = guard.evaluate(evidence, total_search_results=15)

        assert result.verdict == SynthesisGateVerdict.pass_
        assert result.independent_source_found is True

    def test_pass_without_requiring_official(self) -> None:
        """Gate passes when official not required and only independent sources present."""
        cfg = _config(require_official=False, require_independent=True)
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.independent, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://b.com/",
                domain="b.com",
            ),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.medium,
                url="https://c.com/",
                domain="c.com",
            ),
        ]
        result = guard.evaluate(evidence, total_search_results=10)

        assert result.verdict == SynthesisGateVerdict.pass_


# ---------------------------------------------------------------------------
# TestHardFailConditions
# ---------------------------------------------------------------------------


class TestHardFailConditions:
    """Gate should HARD_FAIL when evidence fails default thresholds."""

    def test_hard_fail_insufficient_sources(self) -> None:
        """Only 1 successful source when min is 3 → HARD_FAIL."""
        cfg = _config(min_fetched=3)
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.official, confidence=ConfidenceBucket.high),
        ]
        result = guard.evaluate(evidence, total_search_results=10)

        assert result.verdict == SynthesisGateVerdict.hard_fail
        assert any("Insufficient sources" in r for r in result.reasons)

    def test_hard_fail_reason_includes_counts(self) -> None:
        """Failure reason must include N/M counts."""
        cfg = _config(min_fetched=3)
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.official, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://b.com/",
                domain="b.com",
            ),
        ]
        result = guard.evaluate(evidence, total_search_results=10)

        assert result.verdict == SynthesisGateVerdict.hard_fail
        reason = next(r for r in result.reasons if "Insufficient sources" in r)
        assert "2" in reason  # actual
        assert "3" in reason  # minimum

    def test_hard_fail_insufficient_high_confidence(self) -> None:
        """3 successful but only 0 high-confidence → HARD_FAIL."""
        cfg = _config(min_fetched=3, min_high=2)
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.official, confidence=ConfidenceBucket.medium),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.medium,
                url="https://b.com/",
                domain="b.com",
            ),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.low,
                url="https://c.com/",
                domain="c.com",
            ),
        ]
        result = guard.evaluate(evidence, total_search_results=10)

        assert result.verdict == SynthesisGateVerdict.hard_fail
        assert any("high-confidence" in r for r in result.reasons)

    def test_failed_records_not_counted_as_successful(self) -> None:
        """content_length=0 records do not count toward successful fetched."""
        cfg = _config(min_fetched=3)
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(
                source_type=SourceType.official,
                confidence=ConfidenceBucket.high,
                content_length=0,
            ),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                content_length=0,
                url="https://b.com/",
                domain="b.com",
            ),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                content_length=0,
                url="https://c.com/",
                domain="c.com",
            ),
        ]
        result = guard.evaluate(evidence, total_search_results=10)

        assert result.verdict == SynthesisGateVerdict.hard_fail
        assert result.total_fetched == 0

    def test_hard_fail_no_official_source_found(self) -> None:
        """Official required, none in results → HARD_FAIL with appropriate reason."""
        cfg = _config(require_official=True)
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.independent, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://b.com/",
                domain="b.com",
            ),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://c.com/",
                domain="c.com",
            ),
        ]
        result = guard.evaluate(evidence, total_search_results=10)

        assert result.verdict == SynthesisGateVerdict.hard_fail
        assert any("official" in r.lower() for r in result.reasons)

    def test_hard_fail_official_attempted_but_failed_reason(self) -> None:
        """Official was attempted (content_length=0) → specific failure reason."""
        cfg = _config(require_official=True)
        guard = SynthesisGuard(cfg)
        evidence = [
            # Official attempted but failed
            _record(
                source_type=SourceType.official,
                confidence=ConfidenceBucket.low,
                content_length=0,
            ),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://b.com/",
                domain="b.com",
            ),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://c.com/",
                domain="c.com",
            ),
        ]
        # Use enough total_search_results to not trigger relaxation
        result = guard.evaluate(evidence, total_search_results=10)

        # Should have a reason mentioning extraction failure
        assert any("extraction failed" in r.lower() for r in result.reasons)

    def test_hard_fail_no_independent_source(self) -> None:
        """Independent required, none present → HARD_FAIL."""
        cfg = _config(require_independent=True)
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.official, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.official,
                confidence=ConfidenceBucket.high,
                url="https://gov2.gov/",
                domain="gov2.gov",
            ),
            _record(
                source_type=SourceType.ugc_low_trust,
                confidence=ConfidenceBucket.medium,
                url="https://forum.com/",
                domain="forum.com",
            ),
        ]
        result = guard.evaluate(evidence, total_search_results=10)

        assert result.verdict == SynthesisGateVerdict.hard_fail
        assert any("independent" in r.lower() for r in result.reasons)


# ---------------------------------------------------------------------------
# TestRelaxation
# ---------------------------------------------------------------------------


class TestRelaxation:
    """Niche topic / official failure scenarios trigger threshold relaxation."""

    def test_niche_topic_triggers_relaxation(self) -> None:
        """total_search_results < 5 should relax thresholds."""
        cfg = _config(
            min_fetched=3,
            min_high=2,
            require_official=True,
            relaxation_enabled=True,
            relaxed_min_fetched=2,
            relaxed_min_high=1,
            relaxed_require_official=False,
        )
        guard = SynthesisGuard(cfg)
        # 2 good independent sources — passes relaxed thresholds
        evidence = [
            _record(source_type=SourceType.independent, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://b.com/",
                domain="b.com",
            ),
        ]
        result = guard.evaluate(evidence, total_search_results=3)

        # Should be SOFT_FAIL (relaxed) not HARD_FAIL
        assert result.verdict == SynthesisGateVerdict.soft_fail
        assert result.thresholds_applied["relaxed"] is True

    def test_all_official_failed_triggers_relaxation(self) -> None:
        """If official was attempted but all failed, relax thresholds."""
        cfg = _config(
            require_official=True,
            relaxation_enabled=True,
            relaxed_require_official=False,
            relaxed_min_fetched=2,
            relaxed_min_high=1,
        )
        guard = SynthesisGuard(cfg)
        evidence = [
            # Official attempted but content_length=0 → failed
            _record(
                source_type=SourceType.official,
                confidence=ConfidenceBucket.low,
                content_length=0,
            ),
            _record(source_type=SourceType.independent, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://b.com/",
                domain="b.com",
            ),
        ]
        # Enough search results to not trigger niche-topic path
        result = guard.evaluate(evidence, total_search_results=15)

        assert result.thresholds_applied["relaxed"] is True

    def test_relaxation_disabled_keeps_hard_fail(self) -> None:
        """When relaxation_enabled=False, niche topic still gets HARD_FAIL."""
        cfg = _config(
            min_fetched=3,
            relaxation_enabled=False,
        )
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.independent, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://b.com/",
                domain="b.com",
            ),
        ]
        # Only 3 search results → would normally relax
        result = guard.evaluate(evidence, total_search_results=3)

        assert result.verdict == SynthesisGateVerdict.hard_fail
        assert result.thresholds_applied["relaxed"] is False

    def test_relaxation_applied_uses_relaxed_thresholds(self) -> None:
        """Relaxed evaluation uses relaxed_min_fetched and relaxed_min_high."""
        cfg = _config(
            min_fetched=5,
            min_high=4,
            relaxation_enabled=True,
            relaxed_min_fetched=2,
            relaxed_min_high=1,
            relaxed_require_official=False,
        )
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.independent, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.medium,
                url="https://b.com/",
                domain="b.com",
            ),
        ]
        # Niche topic → relax
        result = guard.evaluate(evidence, total_search_results=2)

        # 2 fetched ≥ relaxed_min_fetched(2), 1 high ≥ relaxed_min_high(1)
        assert result.verdict == SynthesisGateVerdict.soft_fail
        assert result.thresholds_applied["min_fetched"] == 2
        assert result.thresholds_applied["min_high_confidence"] == 1


# ---------------------------------------------------------------------------
# TestSoftFail
# ---------------------------------------------------------------------------


class TestSoftFail:
    """SOFT_FAIL issued when relaxed and minimum sources present."""

    def test_soft_fail_missing_official_relaxed_mode(self) -> None:
        """No official source; relaxed threshold doesn't require one → SOFT_FAIL."""
        cfg = _config(
            require_official=True,
            relaxation_enabled=True,
            relaxed_require_official=False,
            relaxed_min_fetched=2,
            relaxed_min_high=1,
        )
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.independent, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://b.com/",
                domain="b.com",
            ),
        ]
        # Niche topic → relax
        result = guard.evaluate(evidence, total_search_results=2)

        assert result.verdict == SynthesisGateVerdict.soft_fail

    def test_soft_fail_has_reasons_but_minimum_met(self) -> None:
        """SOFT_FAIL still records the unmet reason from default policy."""
        cfg = _config(
            require_official=True,
            relaxation_enabled=True,
            relaxed_require_official=False,
            relaxed_min_fetched=2,
            relaxed_min_high=1,
        )
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.independent, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://b.com/",
                domain="b.com",
            ),
        ]
        result = guard.evaluate(evidence, total_search_results=2)

        # Verdict is SOFT_FAIL (relaxed minimum met), but reason is still recorded
        assert result.verdict == SynthesisGateVerdict.soft_fail
        assert len(result.reasons) > 0

    def test_still_hard_fails_if_relaxed_minimum_not_met(self) -> None:
        """Even relaxed mode, if relaxed minimum unmet → HARD_FAIL."""
        cfg = _config(
            relaxation_enabled=True,
            relaxed_min_fetched=2,
            relaxed_min_high=1,
        )
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.independent, confidence=ConfidenceBucket.high),
        ]
        # Only 1 successful source, relaxed minimum is 2
        result = guard.evaluate(evidence, total_search_results=2)

        assert result.verdict == SynthesisGateVerdict.hard_fail


# ---------------------------------------------------------------------------
# TestThresholdsRecording
# ---------------------------------------------------------------------------


class TestThresholdsRecording:
    """thresholds_applied must always be present with expected keys."""

    def test_default_thresholds_recorded(self) -> None:
        """Default evaluation records all expected threshold keys."""
        cfg = _config(
            min_fetched=3,
            min_high=2,
            require_official=True,
            require_independent=True,
        )
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.official, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://b.com/",
                domain="b.com",
            ),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://c.com/",
                domain="c.com",
            ),
        ]
        result = guard.evaluate(evidence, total_search_results=15)

        thresholds = result.thresholds_applied
        assert "min_fetched" in thresholds
        assert "min_high_confidence" in thresholds
        assert "require_official" in thresholds
        assert "require_independent" in thresholds
        assert "relaxed" in thresholds

    def test_default_thresholds_values_match_config(self) -> None:
        """Threshold values in result match the config provided."""
        cfg = _config(
            min_fetched=4,
            min_high=3,
            require_official=True,
            require_independent=False,
        )
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.official, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.official,
                confidence=ConfidenceBucket.high,
                url="https://b.gov/",
                domain="b.gov",
            ),
            _record(
                source_type=SourceType.official,
                confidence=ConfidenceBucket.high,
                url="https://c.gov/",
                domain="c.gov",
            ),
            _record(
                source_type=SourceType.official,
                confidence=ConfidenceBucket.high,
                url="https://d.gov/",
                domain="d.gov",
            ),
        ]
        result = guard.evaluate(evidence, total_search_results=20)

        assert result.thresholds_applied["min_fetched"] == 4
        assert result.thresholds_applied["min_high_confidence"] == 3
        assert result.thresholds_applied["require_official"] is True
        assert result.thresholds_applied["require_independent"] is False
        assert result.thresholds_applied["relaxed"] is False

    def test_relaxed_thresholds_recorded_when_relaxed(self) -> None:
        """When relaxed, threshold values should reflect relaxed config."""
        cfg = _config(
            min_fetched=5,
            relaxed_min_fetched=2,
            relaxed_min_high=1,
            relaxed_require_official=False,
        )
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.independent, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://b.com/",
                domain="b.com",
            ),
        ]
        # Niche topic → relax
        result = guard.evaluate(evidence, total_search_results=3)

        thresholds = result.thresholds_applied
        assert thresholds["relaxed"] is True
        assert thresholds["min_fetched"] == 2
        assert thresholds["min_high_confidence"] == 1
        assert thresholds["require_official"] is False

    def test_query_context_accepted_without_error(self) -> None:
        """evaluate() accepts optional QueryContext without raising."""
        cfg = _config()
        guard = SynthesisGuard(cfg)
        evidence = [
            _record(source_type=SourceType.official, confidence=ConfidenceBucket.high),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://b.com/",
                domain="b.com",
            ),
            _record(
                source_type=SourceType.independent,
                confidence=ConfidenceBucket.high,
                url="https://c.com/",
                domain="c.com",
            ),
        ]
        ctx = QueryContext(task_intent="compare pricing", time_sensitive=True)
        # Should not raise
        result = guard.evaluate(evidence, total_search_results=20, query_context=ctx)

        assert result.verdict == SynthesisGateVerdict.pass_
