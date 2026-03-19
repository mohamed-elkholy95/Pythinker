"""Multi-signal skill-task matching service.

Analyzes task descriptions and scores skills across 5 weighted signals to
determine which skills are most relevant before planning begins.  Complements
the existing SkillMatcher (2 signals: regex + keywords) with a richer
composite score suitable for proactive skill-first agent execution.

Signals (total weight = 1.0):
  1. Trigger pattern match   - 0.30  (regex against skill.trigger_patterns)
  2. Category alignment      - 0.25  (task keywords -> SkillCategory)
  3. Tool requirement overlap - 0.20  (inferred tools vs skill.required_tools)
  4. Description similarity  - 0.15  (Jaccard on tokenized task vs skill metadata)
  5. Keyword density         - 0.10  (distinctive words from skill body)

Target latency: <10 ms for ≤50 skills.  Pure Python — no LLM calls, no I/O.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import ClassVar

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass
class SkillAnalysisResult:
    """Composite scoring result for one skill against a task description."""

    skill_id: str
    skill_name: str
    confidence: float  # 0.0-1.0 composite score
    signals: list[str]  # Human-readable per-signal explanations (for debugging)
    activation_recommended: bool  # True when confidence >= configured threshold


# ---------------------------------------------------------------------------
# Cached per-skill metadata computed once at init time
# ---------------------------------------------------------------------------


@dataclass
class _SkillCache:
    """Pre-computed data structures for a single skill (built once at init)."""

    compiled_patterns: list[tuple[re.Pattern[str], str]]  # (compiled, raw)
    description_tokens: frozenset[str]  # tokenized name + description + tags
    keyword_set: frozenset[str]  # top-N distinctive words from system_prompt_addition


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class SkillTaskAnalyzer:
    """Score skills against a task description using 5 weighted signals.

    Usage::

        analyzer = await get_skill_task_analyzer()
        results = await analyzer.analyze("write a web scraper in Python")
        for r in results:
            print(r.skill_id, r.confidence, r.signals)
    """

    # ------------------------------------------------------------------ #
    # Class-level configuration                                           #
    # ------------------------------------------------------------------ #

    DEFAULT_THRESHOLD: ClassVar[float] = 0.25
    TOP_KEYWORDS_PER_SKILL: ClassVar[int] = 30
    MIN_KEYWORD_LENGTH: ClassVar[int] = 4  # ignore short stop-words

    # Signal weights (must sum to 1.0)
    W_TRIGGER: ClassVar[float] = 0.30
    W_CATEGORY: ClassVar[float] = 0.25
    W_TOOLS: ClassVar[float] = 0.20
    W_DESCRIPTION: ClassVar[float] = 0.15
    W_KEYWORD_DENSITY: ClassVar[float] = 0.10

    # Category → task keywords that suggest the category
    CATEGORY_KEYWORDS: ClassVar[dict[str, list[str]]] = {
        "research": ["research", "investigate", "find out", "look up", "search for", "learn about", "explore"],
        "coding": ["code", "implement", "build", "develop", "fix", "debug", "refactor", "program", "script"],
        "browser": ["browse", "navigate", "website", "url", "open page", "web page", "click", "form"],
        "data_analysis": ["analyze", "data", "csv", "chart", "graph", "statistics", "visualization", "dataset"],
        "file_management": ["file", "folder", "organize", "rename", "move", "copy", "directory"],
        "communication": ["email", "message", "notify", "send", "communicate"],
    }

    # Regex → list of tool names inferred when the regex matches the task
    TOOL_INFERENCE_PATTERNS: ClassVar[dict[str, list[str]]] = {
        r"https?://|url|website|browse": ["browser_navigate", "browser_get_content"],
        r"file|read|write|save|create\s+file": ["file_read", "file_write"],
        r"search|find\s+information|look\s+up": ["info_search_web"],
        r"run|execute|script|python|code": ["shell_exec", "code_execute"],
        r"csv|excel|data|pandas|chart": ["code_execute_python", "file_read"],
    }

    # Compiled version of TOOL_INFERENCE_PATTERNS (built once on first use)
    _COMPILED_TOOL_PATTERNS: ClassVar[list[tuple[re.Pattern[str], list[str]]] | None] = None

    # ------------------------------------------------------------------ #
    # Instance state                                                       #
    # ------------------------------------------------------------------ #

    def __init__(self) -> None:
        self._cache: dict[str, _SkillCache] = {}  # skill_id -> _SkillCache
        self._initialized: bool = False

    # ------------------------------------------------------------------ #
    # Lazy initialisation (mirrors SkillTriggerMatcher._ensure_initialized) #
    # ------------------------------------------------------------------ #

    async def _ensure_initialized(self) -> None:
        """Lazily load skills from the registry and pre-compute caches."""
        if self._initialized:
            return

        try:
            from app.domain.models.skill import SkillInvocationType
            from app.domain.services.skill_registry import get_skill_registry

            registry = await get_skill_registry()
            skills = await registry.get_available_skills()

            for skill in skills:
                # Only AI-invokable skills are candidates for auto-activation
                if skill.invocation_type not in (SkillInvocationType.AI, SkillInvocationType.BOTH):
                    continue
                self._cache[skill.id] = self._build_cache(skill)

            self._initialized = True
            logger.info(
                "SkillTaskAnalyzer initialized with %d AI-invokable skill(s)",
                len(self._cache),
            )

        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to initialize SkillTaskAnalyzer: %s", exc)
            self._initialized = False  # allow retry on next call

    @classmethod
    def _build_cache(cls, skill: object) -> _SkillCache:
        """Pre-compute all expensive data for *skill* exactly once."""
        # 1. Compile trigger patterns (same safety checks as SkillTriggerMatcher)
        compiled_patterns: list[tuple[re.Pattern[str], str]] = []
        for raw in getattr(skill, "trigger_patterns", []):
            try:
                compiled_patterns.append((re.compile(raw, re.IGNORECASE), raw))
            except re.error as exc:
                logger.warning("Invalid trigger pattern '%s' for skill '%s': %s", raw, skill.id, exc)  # type: ignore[attr-defined]

        # 2. Tokenize name + description + tags → frozenset for Jaccard
        name_tokens = cls._tokenize(getattr(skill, "name", ""))
        desc_tokens = cls._tokenize(getattr(skill, "description", ""))
        tag_tokens: set[str] = set()
        for tag in getattr(skill, "tags", []):
            tag_tokens.update(cls._tokenize(tag))
        description_tokens = frozenset(name_tokens | desc_tokens | tag_tokens)

        # 3. Extract top-N distinctive words from system_prompt_addition
        prompt_body = getattr(skill, "system_prompt_addition", None) or ""
        keyword_set = cls._extract_keywords(prompt_body, cls.TOP_KEYWORDS_PER_SKILL)

        return _SkillCache(
            compiled_patterns=compiled_patterns,
            description_tokens=description_tokens,
            keyword_set=keyword_set,
        )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def analyze(
        self,
        task: str,
        threshold: float = DEFAULT_THRESHOLD,
        max_results: int = 5,
    ) -> list[SkillAnalysisResult]:
        """Score all AI-invokable skills against *task* and return ranked results.

        Args:
            task: User task description.
            threshold: Minimum composite score to set ``activation_recommended``.
            max_results: Maximum number of results to return (sorted by confidence).

        Returns:
            List of :class:`SkillAnalysisResult` sorted by confidence descending.
        """
        await self._ensure_initialized()

        if not task or not self._cache:
            return []

        task_lower = task.lower()
        task_tokens = self._tokenize(task_lower)
        inferred_tools = self._infer_tools(task_lower)

        results: list[SkillAnalysisResult] = []

        try:
            from app.domain.services.skill_registry import get_skill_registry

            registry = await get_skill_registry()
        except Exception:  # pragma: no cover
            return []

        for skill_id, cached in self._cache.items():
            try:
                skill = await registry.get_skill(skill_id)
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to fetch skill '%s' during analysis: %s", skill_id, exc)
                continue
            if skill is None:
                continue

            confidence, signals = self._score_skill(
                task_lower=task_lower,
                task_tokens=task_tokens,
                inferred_tools=inferred_tools,
                skill=skill,
                cached=cached,
                threshold=threshold,
            )
            results.append(
                SkillAnalysisResult(
                    skill_id=skill_id,
                    skill_name=getattr(skill, "name", skill_id),
                    confidence=round(confidence, 4),
                    signals=signals,
                    activation_recommended=confidence >= threshold,
                )
            )

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[:max_results]

    def invalidate(self) -> None:
        """Clear all cached skill data (next call re-loads from registry)."""
        logger.debug("SkillTaskAnalyzer: invalidating full cache")
        self._cache.clear()
        self._initialized = False

    def invalidate_skill(self, skill_id: str) -> None:
        """Remove a single skill from the cache.

        The skill will be re-loaded from the registry on the next ``analyze()``
        call that encounters it.  More efficient than a full ``invalidate()``
        when only one skill was modified.

        Args:
            skill_id: ID of the skill that changed.
        """
        if skill_id in self._cache:
            del self._cache[skill_id]
            logger.debug("SkillTaskAnalyzer: invalidated cache for skill '%s'", skill_id)

    # ------------------------------------------------------------------ #
    # Scoring — one method per signal                                      #
    # ------------------------------------------------------------------ #

    def _score_skill(
        self,
        *,
        task_lower: str,
        task_tokens: frozenset[str],
        inferred_tools: list[str],
        skill: object,
        cached: _SkillCache,
        threshold: float,
    ) -> tuple[float, list[str]]:
        """Compute composite score and per-signal explanations for one skill."""
        signals: list[str] = []
        composite = 0.0

        # ---- Signal 1: Trigger pattern match (weight 0.30) ---------------
        trigger_score = self._signal_trigger(task_lower, cached.compiled_patterns, signals)
        composite += trigger_score * self.W_TRIGGER

        # ---- Signal 2: Category alignment (weight 0.25) ------------------
        category_val: str = getattr(getattr(skill, "category", None), "value", "custom")
        category_score = self._signal_category(task_lower, category_val, signals)
        composite += category_score * self.W_CATEGORY

        # ---- Signal 3: Tool requirement overlap (weight 0.20) ------------
        required_tools: list[str] = getattr(skill, "required_tools", [])
        tool_score = self._signal_tools(inferred_tools, required_tools, signals)
        composite += tool_score * self.W_TOOLS

        # ---- Signal 4: Description similarity (weight 0.15) --------------
        desc_score = self._signal_description(task_tokens, cached.description_tokens, signals)
        composite += desc_score * self.W_DESCRIPTION

        # ---- Signal 5: Keyword density (weight 0.10) ---------------------
        density_score = self._signal_keyword_density(task_lower, cached.keyword_set, signals)
        composite += density_score * self.W_KEYWORD_DENSITY

        return min(composite, 1.0), signals

    @staticmethod
    def _signal_trigger(
        task_lower: str,
        compiled_patterns: list[tuple[re.Pattern[str], str]],
        signals: list[str],
    ) -> float:
        """Return 0.0-1.0 based on how many trigger patterns match."""
        if not compiled_patterns:
            return 0.0

        hits = sum(1 for pattern, _ in compiled_patterns if pattern.search(task_lower))
        if hits == 0:
            return 0.0

        # Score proportional to fraction of patterns matched, capped at 1.0
        score = min(hits / len(compiled_patterns), 1.0)
        signals.append(f"Trigger: {hits}/{len(compiled_patterns)} pattern(s) matched (score={score:.2f})")
        return score

    @classmethod
    def _signal_category(
        cls,
        task_lower: str,
        category_value: str,
        signals: list[str],
    ) -> float:
        """Return 0.0-1.0 based on task keyword overlap with the skill's category."""
        keywords = cls.CATEGORY_KEYWORDS.get(category_value, [])
        if not keywords:
            return 0.0

        hits = sum(1 for kw in keywords if kw in task_lower)
        if hits == 0:
            return 0.0

        score = min(hits / len(keywords), 1.0)
        signals.append(f"Category '{category_value}': {hits} keyword hit(s) (score={score:.2f})")
        return score

    @staticmethod
    def _signal_tools(
        inferred_tools: list[str],
        required_tools: list[str],
        signals: list[str],
    ) -> float:
        """Return 0.0-1.0 based on overlap between inferred tools and required tools."""
        if not required_tools or not inferred_tools:
            return 0.0

        required_set = set(required_tools)
        inferred_set = set(inferred_tools)
        overlap = required_set & inferred_set

        if not overlap:
            return 0.0

        # Jaccard-like: |overlap| / |union|
        score = len(overlap) / len(required_set | inferred_set)
        signals.append(f"Tools: {len(overlap)} shared tool(s) {sorted(overlap)} (score={score:.2f})")
        return score

    @staticmethod
    def _signal_description(
        task_tokens: frozenset[str],
        description_tokens: frozenset[str],
        signals: list[str],
    ) -> float:
        """Return 0.0-1.0 Jaccard similarity between task tokens and skill metadata tokens."""
        if not task_tokens or not description_tokens:
            return 0.0

        intersection = task_tokens & description_tokens
        union = task_tokens | description_tokens

        if not union:
            return 0.0

        score = len(intersection) / len(union)
        if score > 0:
            signals.append(f"Description similarity: {len(intersection)} shared token(s) (score={score:.2f})")
        return score

    @classmethod
    def _signal_keyword_density(
        cls,
        task_lower: str,
        keyword_set: frozenset[str],
        signals: list[str],
    ) -> float:
        """Return 0.0-1.0 based on how many of the skill's distinctive keywords appear in the task."""
        if not keyword_set:
            return 0.0

        hits = sum(1 for kw in keyword_set if kw in task_lower)
        if hits == 0:
            return 0.0

        score = min(hits / len(keyword_set), 1.0)
        signals.append(f"Keyword density: {hits}/{len(keyword_set)} distinctive word(s) matched (score={score:.2f})")
        return score

    # ------------------------------------------------------------------ #
    # Tool inference                                                        #
    # ------------------------------------------------------------------ #

    @classmethod
    def _infer_tools(cls, task_lower: str) -> list[str]:
        """Infer the set of tool names likely needed for *task_lower*."""
        if cls._COMPILED_TOOL_PATTERNS is None:
            cls._COMPILED_TOOL_PATTERNS = [
                (re.compile(pattern, re.IGNORECASE), tools) for pattern, tools in cls.TOOL_INFERENCE_PATTERNS.items()
            ]

        inferred: set[str] = set()
        for compiled, tools in cls._COMPILED_TOOL_PATTERNS:
            if compiled.search(task_lower):
                inferred.update(tools)
        return list(inferred)

    # ------------------------------------------------------------------ #
    # Text utilities                                                        #
    # ------------------------------------------------------------------ #

    @classmethod
    def _tokenize(cls, text: str) -> frozenset[str]:
        """Lowercase, split on non-alphanumeric chars, drop short tokens."""
        if not text:
            return frozenset()
        tokens = re.split(r"[^a-z0-9]+", text.lower())
        return frozenset(t for t in tokens if len(t) >= cls.MIN_KEYWORD_LENGTH)

    @classmethod
    def _extract_keywords(cls, text: str, top_n: int) -> frozenset[str]:
        """Extract the *top_n* most frequent tokens from *text* as distinctive keywords.

        Uses term frequency as a simple proxy for distinctiveness: words that
        appear multiple times in the skill's prompt body are more characteristic
        than single-occurrence words.
        """
        if not text:
            return frozenset()

        tokens = re.split(r"[^a-z0-9]+", text.lower())
        freq: dict[str, int] = {}
        for token in tokens:
            if len(token) >= cls.MIN_KEYWORD_LENGTH:
                freq[token] = freq.get(token, 0) + 1

        # Sort descending by frequency, take top_n
        sorted_tokens = sorted(freq, key=lambda t: freq[t], reverse=True)
        return frozenset(sorted_tokens[:top_n])


# ---------------------------------------------------------------------------
# Module-level singleton (mirrors get_skill_trigger_matcher pattern)
# ---------------------------------------------------------------------------

_analyzer: SkillTaskAnalyzer | None = None


async def get_skill_task_analyzer() -> SkillTaskAnalyzer:
    """Return the singleton :class:`SkillTaskAnalyzer` instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = SkillTaskAnalyzer()
    return _analyzer


async def invalidate_skill_task_analyzer() -> None:
    """Invalidate the full analyzer cache.

    Call after any skill is created, updated, or deleted.
    """
    analyzer = await get_skill_task_analyzer()
    analyzer.invalidate()


async def invalidate_skill_analysis(skill_id: str) -> None:
    """Invalidate the cached data for a single skill.

    More efficient than a full invalidation when only one skill changed.

    Args:
        skill_id: ID of the skill that was modified.
    """
    analyzer = await get_skill_task_analyzer()
    analyzer.invalidate_skill(skill_id)
