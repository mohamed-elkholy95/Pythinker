"""Content confidence assessor for the deterministic research pipeline.

Assesses extraction quality using tiered hard-fail / soft-fail rules.
Purely rule-based — no LLM calls, no I/O.

Decision matrix
---------------
hard_fails present          → LOW / REQUIRED
soft_total >= required_thr  → LOW / REQUIRED
soft_total >= verify_thr    → MEDIUM / VERIFY_IF_HIGH_IMPORTANCE
otherwise                   → HIGH / NO_VERIFY

Shadow score (telemetry only, never used for gating):
  score = 1.0 - (0.4 * hard_fail_count) - (0.1 * soft_total), clamped [0, 1]
"""

from __future__ import annotations

import re
from typing import Any, Literal

from app.domain.models.evidence import (
    ConfidenceAssessment,
    ConfidenceBucket,
    HardFailReason,
    PromotionDecision,
    QueryContext,
    SoftFailReason,
)

# ---------------------------------------------------------------------------
# Pre-compiled patterns
# ---------------------------------------------------------------------------

# Paywall / challenge / bot-detection phrases (case-insensitive)
_PAYWALL_PATTERNS: re.Pattern[str] = re.compile(
    r"subscribe\s+to\s+(continue|read)"
    r"|enable\s+javascript"
    r"|access\s+denied"
    r"|captcha"
    r"|verify\s+you\s+are\s+human"
    r"|please\s+turn\s+on\s+javascript"
    r"|cf-browser-verification"
    r"|checking\s+your\s+browser",
    re.IGNORECASE,
)

# JS SPA shell markers that appear when JS is disabled/not rendered
_JS_SHELL_MARKERS: re.Pattern[str] = re.compile(
    r"\bloading\b"
    r"|enable\s+javascript"
    r"|\bapp-root\b"
    r"|\breact-root\b"
    r"|\b__next\b"
    r"|\bnoscript\b",
    re.IGNORECASE,
)

# Boilerplate line indicators
_BOILERPLATE_PHRASES: tuple[str, ...] = (
    "©",
    "copyright",
    "privacy policy",
    "cookie",
    "terms of service",
    "all rights reserved",
    "sign up",
    "newsletter",
    "follow us",
    "share this",
)

# Date-like patterns for freshness detection
_DATE_PATTERNS: re.Pattern[str] = re.compile(
    r"\d{4}-\d{2}-\d{2}"                   # ISO: 2024-03-15
    r"|\b(Published|Updated|Date:)\b"       # Labels
    r"|\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{4}\b",  # Month YYYY
    re.IGNORECASE,
)

# Title token extraction — strip common stopwords from title for mismatch check
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at",
        "is", "it", "its", "for", "with", "by", "from", "that", "this",
        "are", "was", "were", "be", "been", "being", "have", "has", "had",
        "do", "does", "did", "will", "would", "could", "should", "may",
        "can", "not", "no", "nor", "so", "yet", "both", "either",
    }
)

# Max chars for the JS shell check (content must be shorter than this)
_JS_SHELL_MAX_CHARS: int = 100

# Minimum stripped content chars to pass extraction failure check
_MIN_CONTENT_CHARS: int = 50

# Minimum unique-word density threshold for content quality
_WEAK_DENSITY_THRESHOLD: float = 0.3

# Title-content overlap threshold (fraction of title tokens that must appear)
_MISMATCH_OVERLAP_THRESHOLD: float = 0.20

# Minimum meaningful title tokens needed before mismatch check fires
_MIN_TITLE_TOKENS: int = 3

# Entity presence fraction threshold: below this → missing entities signal
_ENTITY_MISSING_HARD_THRESHOLD: float = 0.50  # > 50% absent → hard fail (high importance)
_ENTITY_MISSING_SOFT_THRESHOLD: float = 0.70  # > 70% absent → soft fail (non-high importance)


class ContentConfidenceAssessor:
    """Assesses web page extraction quality using tiered hard-fail / soft-fail rules.

    All checks are deterministic regex / heuristic — no LLM calls.

    Args:
        config: Any object exposing the four research pipeline config fields:
            - research_soft_fail_verify_threshold (int)
            - research_soft_fail_required_threshold (int)
            - research_thin_content_chars (int)
            - research_boilerplate_ratio_threshold (float)
    """

    def __init__(self, config: Any) -> None:
        self._verify_threshold: int = config.research_soft_fail_verify_threshold
        self._required_threshold: int = config.research_soft_fail_required_threshold
        self._thin_chars: int = config.research_thin_content_chars
        self._boilerplate_threshold: float = config.research_boilerplate_ratio_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess(
        self,
        content: str,
        url: str,
        domain: str,
        title: str,
        source_importance: Literal["high", "medium", "low"],
        query_context: QueryContext | None = None,
    ) -> ConfidenceAssessment:
        """Run all confidence checks and return a ConfidenceAssessment.

        Args:
            content: Extracted page text.
            url: Source URL (used for paywall URL-pattern checks).
            domain: Hostname of the source (informational).
            title: Page title as supplied by the search result.
            source_importance: Tier assigned by the source selector.
            query_context: Optional intent context for entity/date checks.

        Returns:
            A ConfidenceAssessment with hard_fails, soft_fails, bucket, decision,
            shadow_score, content_length, boilerplate_ratio, entity_match_ratio.
        """
        stripped = content.strip() if content else ""
        content_length = len(stripped)

        # -- Hard-fail checks -------------------------------------------
        hard_fails: list[HardFailReason] = []

        # 1. Paywall / challenge page — checked before JS shell because "enable
        #    javascript" phrasing can appear in both contexts; the paywall
        #    pattern is the more authoritative signal when content is short.
        if stripped and self._detect_block_paywall_challenge(stripped, url):
            hard_fails.append(HardFailReason.block_paywall_challenge)

        # 2. JS shell — tiny content with SPA marker, only if not already a
        #    paywall (paywall takes priority for overlapping "enable javascript").
        if stripped and not hard_fails and self._detect_js_shell_empty(stripped):
            hard_fails.append(HardFailReason.js_shell_empty)

        # 3. Extraction failure (empty / too short) — only if no prior hard fail.
        if not hard_fails and self._detect_extraction_failure(stripped):
            hard_fails.append(HardFailReason.extraction_failure)

        # 4. Severe content mismatch (only run if we have real content)
        if stripped and not hard_fails and self._detect_severe_mismatch(stripped, title, domain):
            hard_fails.append(HardFailReason.severe_content_mismatch)

        # 5. Required field missing (importance-aware)
        entity_match_ratio = 1.0  # default: full match
        if query_context and query_context.required_entities:
            entity_match_ratio = self._compute_entity_ratio(stripped, query_context.required_entities)
            absent_ratio = 1.0 - entity_match_ratio
            if (
                source_importance == "high"
                and absent_ratio > _ENTITY_MISSING_HARD_THRESHOLD
                and HardFailReason.required_field_missing not in hard_fails
            ):
                hard_fails.append(HardFailReason.required_field_missing)

        # -- Soft-fail checks (only if no hard fails) --------------------
        soft_fails: list[SoftFailReason] = []
        boilerplate_ratio = 0.0

        if not hard_fails and stripped:
            # 1. Thin content
            if len(stripped) < self._thin_chars:
                soft_fails.append(SoftFailReason.thin_content)

            # 2. Boilerplate-heavy
            boilerplate_ratio = self._compute_boilerplate_ratio(stripped)
            if boilerplate_ratio > self._boilerplate_threshold:
                soft_fails.append(SoftFailReason.boilerplate_heavy)

            # 3. Missing entities (non-high importance OR medium/low importance)
            if query_context and query_context.required_entities:
                absent_ratio = 1.0 - entity_match_ratio
                if source_importance != "high" and absent_ratio > (1.0 - _ENTITY_MISSING_SOFT_THRESHOLD):
                    # absent > 30% of entities
                    soft_fails.append(SoftFailReason.missing_entities)

            # 4. No publish date (only for time-sensitive queries)
            if query_context and query_context.time_sensitive and not _DATE_PATTERNS.search(stripped):
                soft_fails.append(SoftFailReason.no_publish_date)

            # 5. Weak content density
            if self._detect_weak_density(stripped):
                soft_fails.append(SoftFailReason.weak_content_density)

        soft_total = len(soft_fails)

        # -- Decision matrix --------------------------------------------
        if hard_fails or soft_total >= self._required_threshold:
            bucket = ConfidenceBucket.low
            decision = PromotionDecision.required
        elif soft_total >= self._verify_threshold:
            bucket = ConfidenceBucket.medium
            decision = PromotionDecision.verify_if_high_importance
        else:
            bucket = ConfidenceBucket.high
            decision = PromotionDecision.no_verify

        # -- Shadow score (telemetry only) ------------------------------
        shadow = 1.0 - 0.4 * len(hard_fails) - 0.1 * soft_total
        shadow = max(0.0, min(1.0, shadow))

        return ConfidenceAssessment(
            hard_fails=hard_fails,
            soft_fails=soft_fails,
            soft_point_total=soft_total,
            confidence_bucket=bucket,
            promotion_decision=decision,
            shadow_score=shadow,
            content_length=content_length,
            boilerplate_ratio=boilerplate_ratio,
            entity_match_ratio=entity_match_ratio,
        )

    # ------------------------------------------------------------------
    # Hard-fail helpers
    # ------------------------------------------------------------------

    def _detect_extraction_failure(self, stripped: str) -> bool:
        """Return True if content is absent or too short to be useful."""
        return len(stripped) < _MIN_CONTENT_CHARS

    def _detect_block_paywall_challenge(self, content: str, url: str) -> bool:
        """Return True if the page appears to be a paywall or bot challenge."""
        return bool(_PAYWALL_PATTERNS.search(content))

    def _detect_js_shell_empty(self, stripped: str) -> bool:
        """Return True if content looks like an un-rendered JavaScript SPA shell.

        Only fires when the content is shorter than _JS_SHELL_MAX_CHARS AND
        contains one of the known SPA shell markers.
        """
        if len(stripped) >= _JS_SHELL_MAX_CHARS:
            return False
        return bool(_JS_SHELL_MARKERS.search(stripped))

    def _detect_severe_mismatch(self, content: str, title: str, domain: str) -> bool:
        """Return True when the page title tokens are largely absent from the content.

        Algorithm:
        1. Tokenise title into lowercase words > 3 chars, excluding stopwords.
        2. If fewer than _MIN_TITLE_TOKENS meaningful tokens, skip check.
        3. Compute overlap fraction of title tokens present in content.
        4. If overlap < _MISMATCH_OVERLAP_THRESHOLD → mismatch.
        """
        title_tokens = [
            w.lower()
            for w in re.findall(r"\b\w+\b", title)
            if len(w) > 3 and w.lower() not in _STOPWORDS
        ]
        if len(title_tokens) < _MIN_TITLE_TOKENS:
            return False

        content_lower = content.lower()
        matched = sum(1 for tok in title_tokens if tok in content_lower)
        overlap = matched / len(title_tokens)
        return overlap < _MISMATCH_OVERLAP_THRESHOLD

    def _compute_entity_ratio(self, content: str, required_entities: list[str]) -> float:
        """Return fraction of required_entities found in content (case-insensitive).

        Returns 1.0 when required_entities is empty (no missing entities).
        """
        if not required_entities:
            return 1.0
        content_lower = content.lower()
        found = sum(
            1 for entity in required_entities if entity.lower() in content_lower
        )
        return found / len(required_entities)

    # ------------------------------------------------------------------
    # Soft-fail helpers
    # ------------------------------------------------------------------

    def _compute_boilerplate_ratio(self, content: str) -> float:
        """Return the fraction of lines that contain a boilerplate phrase."""
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        if not lines:
            return 0.0
        boilerplate_count = sum(
            1
            for line in lines
            if any(phrase in line.lower() for phrase in _BOILERPLATE_PHRASES)
        )
        return boilerplate_count / len(lines)

    def _detect_weak_density(self, content: str) -> bool:
        """Return True when unique-word ratio is below the density threshold.

        Density = unique_words / total_words.  Values < 0.3 indicate highly
        repetitive content (often scraped boilerplate or placeholder text).
        """
        words = re.findall(r"\b\w+\b", content.lower())
        if not words:
            return False
        density = len(set(words)) / len(words)
        return density < _WEAK_DENSITY_THRESHOLD
