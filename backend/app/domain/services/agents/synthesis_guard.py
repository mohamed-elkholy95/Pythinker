"""Synthesis gate: blocks report generation unless evidence meets policy thresholds.

The guard evaluates a list of EvidenceRecords against configurable quality
thresholds and issues one of three verdicts:

- PASS     — all default thresholds satisfied; synthesis may proceed.
- SOFT_FAIL — one or more default thresholds violated, but the evaluation was
              relaxed (niche topic / official-source failure) and the minimum
              relaxed thresholds are met; synthesis proceeds with a warning.
- HARD_FAIL — thresholds not met even after relaxation, or relaxation disabled;
              synthesis is blocked.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from app.domain.models.evidence import (
    ConfidenceBucket,
    EvidenceRecord,
    QueryContext,
    SourceType,
    SynthesisGateResult,
    SynthesisGateVerdict,
)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Config protocol
# ---------------------------------------------------------------------------


class _SynthesisGuardConfig(Protocol):
    """Structural type for the config object expected by SynthesisGuard.

    Any object with these attributes satisfies the protocol — the full
    Settings class, a SimpleNamespace from tests, or a dataclass will all work.
    """

    research_min_fetched_sources: int
    research_min_high_confidence: int
    research_require_official_source: bool
    research_require_independent_source: bool
    research_relaxation_enabled: bool
    research_relaxed_min_fetched_sources: int
    research_relaxed_min_high_confidence: int
    research_relaxed_require_official_source: bool


# ---------------------------------------------------------------------------
# SynthesisGuard
# ---------------------------------------------------------------------------

_INDEPENDENT_TYPES: frozenset[SourceType] = frozenset(
    {SourceType.independent, SourceType.authoritative_neutral}
)


class SynthesisGuard:
    """Pre-synthesis quality gate driven by policy thresholds.

    Args:
        config: Configuration object that exposes the research pipeline
            synthesis gate fields (see :class:`_SynthesisGuardConfig`).
    """

    def __init__(self, config: Any) -> None:
        self._cfg = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        evidence: list[EvidenceRecord],
        total_search_results: int,
        query_context: QueryContext | None = None,  # reserved for future query-aware threshold adjustments
    ) -> SynthesisGateResult:
        """Evaluate evidence quality and return a verdict.

        Args:
            evidence: All EvidenceRecords produced by the acquisition stage.
            total_search_results: Number of raw search results returned by the
                search engine.  Used for niche-topic detection (<5 → relax).
            query_context: Optional task context (not used yet; reserved for
                future query-aware threshold adjustments).

        Returns:
            A :class:`SynthesisGateResult` carrying the verdict, failure
            reasons, evidence statistics, and the thresholds that were applied.
        """
        # 1. Compute evidence landscape
        successful = [r for r in evidence if r.content_length > 0]
        high_conf = [
            r for r in successful if r.confidence_bucket == ConfidenceBucket.high
        ]
        has_official = any(r.source_type == SourceType.official for r in successful)
        has_independent = any(r.source_type in _INDEPENDENT_TYPES for r in successful)
        official_attempted = any(r.source_type == SourceType.official for r in evidence)

        # 2. Determine whether to relax
        relaxed = self._should_relax(
            total_search_results=total_search_results,
            official_attempted=official_attempted,
            has_official=has_official,
        )

        # 3. Evaluate gates against *default* thresholds.
        #    Reasons always reflect the default policy violations so that
        #    callers can log or surface why synthesis quality is below ideal.
        default_min_fetched = self._cfg.research_min_fetched_sources
        default_min_high = self._cfg.research_min_high_confidence
        default_require_official = self._cfg.research_require_official_source
        default_require_independent = self._cfg.research_require_independent_source

        reasons: list[str] = []

        if len(successful) < default_min_fetched:
            reasons.append(
                f"Insufficient sources: {len(successful)}/{default_min_fetched} fetched successfully"
            )

        if len(high_conf) < default_min_high:
            reasons.append(
                f"Insufficient high-confidence sources: {len(high_conf)}/{default_min_high}"
            )

        if default_require_official and not has_official:
            if official_attempted:
                reasons.append(
                    "Official source attempted but extraction failed"
                )
            else:
                reasons.append(
                    "No official source found in search results"
                )

        if default_require_independent and not has_independent:
            reasons.append("No independent source acquired successfully")

        # 4. Determine verdict.
        #    - No default violations → PASS (relaxation irrelevant).
        #    - Relaxed mode: check relaxed thresholds; if met → SOFT_FAIL (warns
        #      caller that quality is below ideal but synthesis can proceed).
        #    - Otherwise → HARD_FAIL.
        if not reasons:
            verdict = SynthesisGateVerdict.pass_
        elif relaxed:
            relaxed_min_fetched = self._cfg.research_relaxed_min_fetched_sources
            relaxed_min_high = self._cfg.research_relaxed_min_high_confidence
            relaxed_require_official = self._cfg.research_relaxed_require_official_source

            relaxed_ok = (
                len(successful) >= relaxed_min_fetched
                and len(high_conf) >= relaxed_min_high
                and (not relaxed_require_official or has_official)
                and (not default_require_independent or has_independent)
            )
            verdict = SynthesisGateVerdict.soft_fail if relaxed_ok else SynthesisGateVerdict.hard_fail
        else:
            verdict = SynthesisGateVerdict.hard_fail

        # 5. Record thresholds applied.
        #    When relaxed, record the *relaxed* values so the caller knows
        #    which thresholds were actually enforced for the verdict decision.
        if relaxed:
            thresholds_applied: dict[str, int | bool] = {
                "min_fetched": self._cfg.research_relaxed_min_fetched_sources,
                "min_high_confidence": self._cfg.research_relaxed_min_high_confidence,
                "require_official": self._cfg.research_relaxed_require_official_source,
                "require_independent": default_require_independent,
                "relaxed": True,
            }
        else:
            thresholds_applied = {
                "min_fetched": default_min_fetched,
                "min_high_confidence": default_min_high,
                "require_official": default_require_official,
                "require_independent": default_require_independent,
                "relaxed": False,
            }

        return SynthesisGateResult(
            verdict=verdict,
            reasons=reasons,
            total_fetched=len(successful),
            high_confidence_count=len(high_conf),
            official_source_found=has_official,
            independent_source_found=has_independent,
            thresholds_applied=thresholds_applied,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _should_relax(
        self,
        total_search_results: int,
        official_attempted: bool,
        has_official: bool,
    ) -> bool:
        """Return True when threshold relaxation should be applied.

        Relaxation is triggered by:
        - Niche topic: fewer than 5 total search results returned.
        - Official source unavailability: an official source was attempted but
          none succeeded (extraction failure / hard fail).

        Relaxation is never applied when ``research_relaxation_enabled`` is
        False, regardless of topic niche or official failure.

        Args:
            total_search_results: Count of raw results from the search engine.
            official_attempted: Whether any official-typed record is present
                (including failed / zero-content records).
            has_official: Whether at least one official record was successfully
                fetched (content_length > 0).

        Returns:
            True when the relaxed threshold set should be applied.
        """
        if not self._cfg.research_relaxation_enabled:
            return False

        if total_search_results < 5:
            return True

        return bool(official_attempted and not has_official)
