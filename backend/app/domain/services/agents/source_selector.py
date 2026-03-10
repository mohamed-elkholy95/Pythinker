"""Deterministic source selection from search results.

Pipeline: normalize → score → classify → constrain → select top N.

No LLM calls are made here.  All decisions are rule-based so that the
selection behaviour is reproducible, auditable, and testable.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from app.domain.models.evidence import QueryContext, SelectedSource, SourceType
from app.domain.models.search import SearchResultItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Tracking query-string parameters to strip before deduplication.
_TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "ref",
        "fbclid",
        "gclid",
        "source",
        "medium",
        "campaign",
    }
)

# Domains that are filtered out entirely — no scoring, no selection.
_DENYLIST_DOMAINS: frozenset[str] = frozenset(
    {
        "reddit.com",
        "x.com",
        "twitter.com",
        "instagram.com",
        "facebook.com",
        "tiktok.com",
        "linkedin.com",
        "pinterest.com",
    }
)

# User-generated-content domains with reduced authority scores.
_UGC_DOMAINS: frozenset[str] = frozenset(
    {
        "stackoverflow.com",
        "quora.com",
        "medium.com",
    }
)

# Well-known authoritative-neutral domains.
_AUTHORITATIVE_NEUTRAL_DOMAINS: frozenset[str] = frozenset(
    {
        "wikipedia.org",
        "developer.mozilla.org",
    }
)

# Known tech publications classified as authoritative-neutral.
_TECH_PUBLICATION_DOMAINS: frozenset[str] = frozenset(
    {
        "arstechnica.com",
        "techcrunch.com",
        "theverge.com",
        "wired.com",
        "zdnet.com",
        "cnet.com",
    }
)

# Official subdomain prefixes.
_OFFICIAL_SUBDOMAIN_PREFIXES: tuple[str, ...] = ("docs.", "developer.", "api.")

# Adversarial / comparative intent patterns.
_ADVERSARIAL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bbest alternative\b",
        r"\bvs\b",
        r"\bcompared to\b",
        r"\bcriticism of\b",
        r"\bproblems with\b",
        r"\bindependent benchmark\b",
        r"\breview of\b",
        r"\bversus\b",
    ]
)

# Minimum token length for entity-domain matching.
_MIN_ENTITY_TOKEN_LEN: int = 3


# ---------------------------------------------------------------------------
# SourceSelector
# ---------------------------------------------------------------------------


class SourceSelector:
    """Deterministic, rule-based source selection from search results.

    Attributes:
        _config: Configuration namespace with weights and constraints.
    """

    def __init__(self, config: Any) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select(
        self,
        results: list[SearchResultItem],
        query: str,
        query_context: QueryContext | None = None,
    ) -> list[SelectedSource]:
        """Select the top N sources from *results* for the given *query*.

        Args:
            results: Raw search result items (in provider rank order).
            query: The search query string.
            query_context: Optional intent context to influence constraints.

        Returns:
            Ordered list of SelectedSource objects (best first).
        """
        if not results:
            return []

        query_tokens = self._tokenize(query)

        # 1. Normalise and deduplicate, filtering denylist entries.
        normalised = self._normalize_and_dedupe(results)
        if not normalised:
            return []

        # 2. Score each item.
        scored: list[tuple[SearchResultItem, int, dict[str, float], SourceType, float]] = []
        for item, original_rank in normalised:
            source_type, authority_score = self._classify_source_type(
                item.link, self._extract_domain(item.link), item.title, query_tokens
            )
            scores = self._score(item, query, original_rank, query_context, authority_score)
            scored.append((item, original_rank, scores, source_type, authority_score))

        # 3. Apply diversity constraints and select top N.
        return self._apply_constraints(scored, query, query_context)

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def _normalize_and_dedupe(
        self, results: list[SearchResultItem]
    ) -> list[tuple[SearchResultItem, int]]:
        """Normalise URLs and remove duplicates, keeping first occurrence.

        Filtering steps (in order):
        1. Strip tracking query parameters.
        2. Strip trailing slashes from the path.
        3. Remove ``www.`` prefix from the netloc for deduplication.
        4. Filter denylist domains entirely.
        5. Deduplicate by canonical URL (first occurrence wins).

        Args:
            results: Raw items in provider rank order.

        Returns:
            List of ``(item, original_rank)`` pairs after normalisation.
        """
        seen_canonical: set[str] = set()
        normalised: list[tuple[SearchResultItem, int]] = []

        for rank, item in enumerate(results):
            domain = self._extract_domain(item.link)
            if domain in _DENYLIST_DOMAINS:
                continue

            canonical = self._canonical_url(item.link)
            if canonical in seen_canonical:
                continue
            seen_canonical.add(canonical)
            normalised.append((item, rank))

        return normalised

    def _extract_domain(self, url: str) -> str:
        """Return the bare domain (no ``www.``) for *url*.

        Args:
            url: Absolute URL string.

        Returns:
            Netloc with any ``www.`` prefix removed.
        """
        netloc = urlparse(url).netloc
        return netloc.removeprefix("www.")

    def _canonical_url(self, url: str) -> str:
        """Produce a canonical URL for deduplication purposes.

        Strips tracking parameters, trailing path slash, and normalises the
        netloc to remove ``www.``.

        Args:
            url: Raw URL string.

        Returns:
            Canonical URL string.
        """
        parsed = urlparse(url)

        # Strip www. from netloc
        netloc = parsed.netloc.removeprefix("www.")

        # Strip trailing slash from path
        path = parsed.path.rstrip("/")

        # Strip tracking parameters from query string
        qs_dict = parse_qs(parsed.query, keep_blank_values=True)
        cleaned_qs = {k: v for k, v in qs_dict.items() if k.lower() not in _TRACKING_PARAMS}
        query_string = urlencode(cleaned_qs, doseq=True)

        return urlunparse((parsed.scheme, netloc, path, parsed.params, query_string, ""))

    def _score(
        self,
        item: SearchResultItem,
        query: str,
        rank: int,
        query_context: QueryContext | None,
        authority_score: float,
    ) -> dict[str, float]:
        """Compute all scoring dimensions for a single result item.

        Args:
            item: The search result item.
            query: The user's query string.
            rank: Zero-indexed original position in provider results.
            query_context: Optional intent context (unused in MVP scoring).
            authority_score: Pre-computed authority score from classification.

        Returns:
            Dict with keys ``relevance``, ``authority``, ``freshness``,
            ``rank``, and ``composite``.
        """
        cfg = self._config

        relevance = self._relevance_score(query, item.title, item.snippet)
        freshness = 1.0  # MVP: no date extraction
        rank_sc = 1.0 / (rank + 1)

        composite = (
            relevance * cfg.research_weight_relevance
            + authority_score * cfg.research_weight_authority
            + freshness * cfg.research_weight_freshness
            + rank_sc * cfg.research_weight_rank
        )

        return {
            "relevance": relevance,
            "authority": authority_score,
            "freshness": freshness,
            "rank": rank_sc,
            "composite": composite,
        }

    def _classify_source_type(
        self,
        url: str,
        domain: str,
        title: str,
        query_tokens: set[str],
    ) -> tuple[SourceType, float]:
        """Classify a source into one of four tiers and return its authority score.

        Classification precedence (highest to lowest):
        1. Denylist → excluded earlier in the pipeline; not reached here.
        2. Official indicators (.gov, .edu, docs.*, developer.*, api.*, entity match).
        3. UGC low-trust (stackoverflow, quora, medium).
        4. Authoritative-neutral (wikipedia, MDN, known tech pubs).
        5. Default → INDEPENDENT.

        Args:
            url: Full URL of the source.
            domain: Bare domain (no www.).
            title: Page title from search result.
            query_tokens: Lowercased tokens from the query.

        Returns:
            Tuple of ``(SourceType, authority_score)``.
        """
        tld = domain.rsplit(".", 1)[-1] if "." in domain else ""

        # .gov / .edu TLD
        if tld in ("gov", "edu"):
            return SourceType.official, 0.95

        # Official subdomains
        for prefix in _OFFICIAL_SUBDOMAIN_PREFIXES:
            if domain.startswith(prefix):
                return SourceType.official, 0.90

        # Entity-domain match: if any meaningful query token exactly equals the
        # registrable domain name (second-level domain, e.g. "python" in "python.org").
        # Substring matching is intentionally avoided to prevent false positives
        # like "health" matching "healthline.com".
        sld = domain.split(".")[0] if "." in domain else domain
        if any(tok == sld for tok in query_tokens if len(tok) > _MIN_ENTITY_TOKEN_LEN):
            return SourceType.official, 0.85

        # UGC low-trust
        if domain in _UGC_DOMAINS:
            return SourceType.ugc_low_trust, 0.25

        # Authoritative-neutral — specific well-known domains
        if domain in _AUTHORITATIVE_NEUTRAL_DOMAINS:
            return SourceType.authoritative_neutral, 0.75

        # Tech publications
        if domain in _TECH_PUBLICATION_DOMAINS:
            return SourceType.authoritative_neutral, 0.65

        # Default
        return SourceType.independent, 0.50

    def _apply_constraints(
        self,
        scored: list[tuple[SearchResultItem, int, dict[str, float], SourceType, float]],
        query: str,
        query_context: QueryContext | None,
    ) -> list[SelectedSource]:
        """Apply diversity and count constraints, then build SelectedSource objects.

        Algorithm:
        1. Sort by composite score descending.
        2. Guaranteed slots:
           a. Top-scoring OFFICIAL source → always selected if one exists.
           b. Top-scoring INDEPENDENT or AUTHORITATIVE_NEUTRAL → always selected.
        3. Fill remaining slots up to ``select_count``:
           - Skip already selected items.
           - Skip items whose domain already reached ``max_per_domain``.
           - Add to selection.
        4. If comparative intent and >50% official, swap the lowest-scoring
           official for the best unselected non-official source.

        Args:
            scored: Tuples of ``(item, original_rank, scores, source_type, authority)``.
            query: The user's query string.
            query_context: Optional intent context.

        Returns:
            List of SelectedSource objects ordered by composite score descending.
        """
        cfg = self._config
        select_count: int = cfg.research_source_select_count
        max_per_domain: int = cfg.research_source_max_per_domain

        # Sort descending by composite score
        ranked = sorted(scored, key=lambda t: t[2]["composite"], reverse=True)

        is_comparative = (
            (query_context is not None and query_context.comparative)
            or self._detect_adversarial_intent(query)
        )

        selected_ids: list[int] = []  # indices into *ranked*
        domain_counts: dict[str, int] = {}

        def _eligible(idx: int) -> bool:
            if idx in selected_ids:
                return False
            item, _, _, _, _ = ranked[idx]
            dom = self._extract_domain(item.link)
            return domain_counts.get(dom, 0) < max_per_domain

        def _pick(idx: int) -> None:
            selected_ids.append(idx)
            item, _, _, _, _ = ranked[idx]
            dom = self._extract_domain(item.link)
            domain_counts[dom] = domain_counts.get(dom, 0) + 1

        # --- Guaranteed slot: top OFFICIAL ---
        for i, (_, _, _, stype, _) in enumerate(ranked):
            if stype == SourceType.official and _eligible(i):
                _pick(i)
                break

        # --- Guaranteed slot: top INDEPENDENT or AUTHORITATIVE_NEUTRAL ---
        for i, (_, _, _, stype, _) in enumerate(ranked):
            if stype in (SourceType.independent, SourceType.authoritative_neutral) and _eligible(i):
                _pick(i)
                break

        # --- Fill remaining slots ---
        for i in range(len(ranked)):
            if len(selected_ids) >= select_count:
                break
            if _eligible(i):
                _pick(i)

        # --- Comparative intent: rebalance if >50% are official ---
        if is_comparative and selected_ids:
            official_indices = [i for i in selected_ids if ranked[i][3] == SourceType.official]
            if len(official_indices) > len(selected_ids) / 2 and len(official_indices) > 0:
                # Find the lowest-scoring official in the selection
                worst_official_idx = min(
                    official_indices, key=lambda i: ranked[i][2]["composite"]
                )
                # Find the best unselected non-official source
                best_alternative: int | None = None
                for i in range(len(ranked)):
                    if i not in selected_ids and ranked[i][3] != SourceType.official:
                        dom = self._extract_domain(ranked[i][0].link)
                        if domain_counts.get(dom, 0) < max_per_domain:
                            best_alternative = i
                            break

                if best_alternative is not None:
                    selected_ids.remove(worst_official_idx)
                    old_dom = self._extract_domain(ranked[worst_official_idx][0].link)
                    domain_counts[old_dom] = domain_counts.get(old_dom, 1) - 1
                    _pick(best_alternative)

        # --- Build SelectedSource objects ---
        result_items = [ranked[i] for i in selected_ids]
        result_items.sort(key=lambda t: t[2]["composite"], reverse=True)

        domain_diversity_applied = len(domain_counts) > 0 and any(
            v >= max_per_domain for v in domain_counts.values()
        )

        output: list[SelectedSource] = []
        for item, original_rank, scores, source_type, authority_score in result_items:
            domain = self._extract_domain(item.link)
            importance = self._determine_importance(source_type, authority_score)
            reason = self._build_selection_reason(source_type, authority_score, scores)
            output.append(
                SelectedSource(
                    url=item.link,
                    domain=domain,
                    title=item.title,
                    original_snippet=item.snippet,
                    original_rank=original_rank,
                    query=query,
                    relevance_score=round(scores["relevance"], 6),
                    authority_score=round(scores["authority"], 6),
                    freshness_score=round(scores["freshness"], 6),
                    rank_score=round(scores["rank"], 6),
                    composite_score=round(scores["composite"], 6),
                    source_type=source_type,
                    source_importance=importance,
                    selection_reason=reason,
                    domain_diversity_applied=domain_diversity_applied,
                )
            )

        return output

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _relevance_score(self, query: str, title: str, snippet: str) -> float:
        """Compute token-overlap relevance between query and (title + snippet).

        Args:
            query: The search query.
            title: Page title from search result.
            snippet: Snippet text from search result.

        Returns:
            Float in ``[0.0, 1.0]``.
        """
        query_tokens = self._tokenize(query)
        content_tokens = self._tokenize(f"{title} {snippet}")
        if not query_tokens:
            return 0.0
        overlap = len(query_tokens & content_tokens)
        return min(overlap / max(len(query_tokens), 1), 1.0)

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Lowercase and split text into word tokens.

        Args:
            text: Input string.

        Returns:
            Set of lowercase alphanumeric tokens.
        """
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    def _detect_adversarial_intent(self, query: str) -> bool:
        """Return True if *query* exhibits comparative or adversarial intent.

        Uses pre-compiled regex patterns matching phrases like "vs",
        "compared to", "criticism of", etc.

        Args:
            query: The search query string.

        Returns:
            True when at least one adversarial pattern matches.
        """
        return any(pattern.search(query) for pattern in _ADVERSARIAL_PATTERNS)

    def _determine_importance(
        self,
        source_type: SourceType,
        authority_score: float,
    ) -> Literal["high", "medium", "low"]:
        """Map source type and authority score to an importance tier.

        Rules (evaluated in order):
        - OFFICIAL + authority >= 0.8 → "high"
        - AUTHORITATIVE_NEUTRAL → "medium"
        - INDEPENDENT + authority >= 0.5 → "medium"
        - Everything else → "low"

        Args:
            source_type: Classified source tier.
            authority_score: Numeric authority score in ``[0.0, 1.0]``.

        Returns:
            One of ``"high"``, ``"medium"``, or ``"low"``.
        """
        if source_type == SourceType.official and authority_score >= 0.8:
            return "high"
        if source_type == SourceType.authoritative_neutral:
            return "medium"
        if source_type == SourceType.independent and authority_score >= 0.5:
            return "medium"
        return "low"

    @staticmethod
    def _build_selection_reason(
        source_type: SourceType,
        authority_score: float,
        scores: dict[str, float],
    ) -> str:
        """Build a human-readable reason string explaining why a source was selected.

        Args:
            source_type: Classified source tier.
            authority_score: Numeric authority score.
            scores: Dict of scoring dimensions.

        Returns:
            Non-empty descriptive string.
        """
        composite = scores["composite"]
        match source_type:
            case SourceType.official:
                return (
                    f"Official source (authority={authority_score:.2f}); "
                    f"composite={composite:.3f}"
                )
            case SourceType.authoritative_neutral:
                return (
                    f"Authoritative neutral source (authority={authority_score:.2f}); "
                    f"composite={composite:.3f}"
                )
            case SourceType.ugc_low_trust:
                return (
                    f"UGC/community source included for coverage "
                    f"(authority={authority_score:.2f}); composite={composite:.3f}"
                )
            case _:
                return (
                    f"Independent source (authority={authority_score:.2f}); "
                    f"composite={composite:.3f}"
                )
