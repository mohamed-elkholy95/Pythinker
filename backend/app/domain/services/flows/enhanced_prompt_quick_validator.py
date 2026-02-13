"""Enhanced prompt quick validator with configurable correction backends.

This validator is deterministic by default and can optionally use:
- RapidFuzz for high-performance similarity scoring
- SymSpell for dictionary-backed correction
- Feedback overrides learned from user corrections

The class remains a drop-in replacement for PromptQuickValidator.
"""

from __future__ import annotations

import difflib
import logging
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import ClassVar, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CorrectionEvent:
    """Represents a single correction decision emitted by the validator."""

    original: str
    corrected: str
    confidence: float
    method: str


class SimilarityMatcher(Protocol):
    """Protocol for optional high-performance fuzzy matching backends."""

    def extract_one(
        self,
        query: str,
        choices: Sequence[str],
        *,
        score_cutoff: float,
    ) -> tuple[str, float] | None:
        """Return best match and score (0-100), or None if below cutoff."""


class SpellCorrectionProvider(Protocol):
    """Protocol for optional word-level spell correction providers."""

    def correct_word(self, word: str) -> tuple[str, float] | None:
        """Return suggested word and confidence (0-1), or None."""


class EnhancedPromptQuickValidator:
    """Apply robust typo/format cleanup pass to user prompts."""

    _TECHNICAL_TERMS: frozenset[str] = frozenset(
        {
            "qdrant",
            "fastapi",
            "pytest",
            "docker",
            "kubernetes",
            "kubectl",
            "playwright",
            "vue",
            "pinia",
            "typescript",
            "mongodb",
            "redis",
            "celery",
            "pydantic",
            "sqlalchemy",
            "httpx",
            "aiohttp",
            "llm",
            "embedding",
            "rag",
            "tokenizer",
            "inference",
            "transformer",
            "attention",
            "multimodal",
            "fine-tuning",
            "fine-tuned",
            "openai",
            "anthropic",
            "huggingface",
            "langchain",
            "pythinker",
            "sandbox",
            "guardrail",
            "replay",
            "supervisor",
            "novnc",
            "prometheus",
            "grafana",
            "loki",
            "promtail",
            "jaeger",
            "opentelemetry",
            "api",
            "sdk",
            "cli",
            "ui",
            "ux",
            "cdp",
            "vnc",
            "xss",
            "csrf",
            "sql",
            "http",
            "https",
            "ws",
            "wss",
            "tcp",
            "udp",
            "ip",
            "dns",
            "ssh",
            "tls",
            "ssl",
        }
    )

    _KNOWN_WORDS: tuple[str, ...] = (
        "analyze",
        "build",
        "compare",
        "comprehensive",
        "create",
        "debug",
        "evaluate",
        "fix",
        "generate",
        "investigate",
        "prompt",
        "report",
        "research",
        "coding",
        "programming",
        "agent",
        "settings",
        "reference",
        "standardized",
        "professional",
        "sonnet",
        "opus",
        "haiku",
        "claude",
        "gpt",
        "gemini",
        "llama",
        "mistral",
        "low",
        "effort",
        "low-effort",
        "deployment",
        "implementation",
        "integration",
        "development",
        "environment",
        "configuration",
        "authentication",
        "authorization",
        "database",
    )

    _FUZZY_SAFE_TARGETS: frozenset[str] = frozenset(
        {
            "analyze",
            "build",
            "compare",
            "comprehensive",
            "create",
            "debug",
            "evaluate",
            "fix",
            "generate",
            "investigate",
            "prompt",
            "report",
            "research",
            "settings",
            "reference",
            "standardized",
            "professional",
            "deployment",
            "implementation",
            "integration",
            "development",
            "environment",
            "configuration",
            "authentication",
            "authorization",
            "database",
            "coding",
            "programming",
        }
    )

    _EXTENDED_TYPO_DICT: ClassVar[dict[str, str]] = {
        "copding": "coding",
        "codding": "coding",
        "progamming": "programming",
        "developement": "development",
        "envrionment": "environment",
        "deploymnet": "deployment",
        "implmentation": "implementation",
        "integraiton": "integration",
        "databse": "database",
        "backgroud": "background",
        "configuraiton": "configuration",
        "authenitcation": "authentication",
        "emebdding": "embedding",
        "tokneizer": "tokenizer",
        "inferecne": "inference",
        "tranformer": "transformer",
        "pythiner": "pythinker",
        "pythinkr": "pythinker",
        "sanbox": "sandbox",
        "gaurdrail": "guardrail",
        "recieve": "receive",
        "seperate": "separate",
        "definately": "definitely",
        "occured": "occurred",
        "accomodate": "accommodate",
        "teh": "the",
        "adn": "and",
        "taht": "that",
        "wiht": "with",
        "fo": "of",
        "ot": "to",
        "ti": "it",
        "nad": "and",
        "thta": "that",
        "waht": "what",
        "whcih": "which",
        "wich": "which",
        "woudl": "would",
        "coudl": "could",
        "shoudl": "should",
        "compoore": "compare",
        "comparre": "compare",
        "resesearch": "research",
        "onlime": "online",
        "standerdized": "standardized",
        "profesisonal": "professional",
        "refrence": "reference",
    }

    _EXACT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
        (r"\blow[\s\-_]*effort\b", "low-effort"),
        (r"\bhigh[\s\-_]*effort\b", "high-effort"),
        (r"\bsonet+\b", "sonnet"),
        (r"\bsonet+([0-9]+(?:\.[0-9]+)+)\b", r"sonnet \1"),
        (r"\bopu+s\b", "opus"),
        (r"\bopu+s([0-9]+(?:\.[0-9]+)+)\b", r"opus \1"),
        (r"\bpromtto\b", "prompt to"),
        (r"\bglm[\s\-_]*([0-9]+(?:\.[0-9]+)?)\b", r"GLM-\1"),
        (r"\bclaude[\s\-_]*([0-9]+(?:\.[0-9]+)?)\b", r"Claude \1"),
        (r"\bgpt[\s\-_]*([0-9]+(?:\.[0-9]+)?)\b", r"GPT-\1"),
    )

    _MODEL_WITH_VERSION = re.compile(
        r"\b(opus|sonnet|haiku|gpt|claude|gemini|llama|mistral)\s*([0-9]+(?:\.[0-9]+)+)\b",
        flags=re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        enabled: bool = True,
        log_corrections: bool = True,
        confidence_threshold: float = 0.90,
        rapidfuzz_score_cutoff: float = 90.0,
        max_suggestions: int = 1,
        rapidfuzz_matcher: SimilarityMatcher | None = None,
        symspell_provider: SpellCorrectionProvider | None = None,
        correction_event_sink: Callable[[CorrectionEvent], None] | None = None,
        feedback_lookup: Callable[[str], str | None] | None = None,
    ):
        self._enabled = enabled
        self._correction_stats: Counter[tuple[str, str]] = Counter()
        self._log_corrections_enabled = log_corrections
        self._confidence_threshold = confidence_threshold
        self._rapidfuzz_score_cutoff = rapidfuzz_score_cutoff
        self._max_suggestions = max(1, max_suggestions)
        self._rapidfuzz_matcher = rapidfuzz_matcher
        self._symspell_provider = symspell_provider
        self._correction_event_sink = correction_event_sink
        self._feedback_lookup = feedback_lookup
        self._locked_entities: frozenset[str] = frozenset()

    def validate(self, text: str, locked_entities: list[str] | None = None) -> str:
        """Return a cleaned prompt for downstream planning/analysis.

        Args:
            text: User prompt to validate.
            locked_entities: Optional list of entity strings that must not be
                corrected (Phase 1 RequestContract). Tokens matching these are
                skipped by fuzzy correction.
        """
        if not text:
            return text

        cleaned = text.strip()
        if not cleaned or not self._enabled:
            return cleaned

        self._locked_entities = frozenset(e.lower() for e in (locked_entities or []))

        cleaned = re.sub(r"\s+", " ", cleaned)

        # Dictionary replacements first for deterministic high-confidence fixes.
        cleaned = self._apply_dictionary_replacements(cleaned)

        for pattern, replacement in self._EXACT_REPLACEMENTS:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

        cleaned = self._fuzzy_word_cleanup(cleaned)

        cleaned = self._MODEL_WITH_VERSION.sub(
            lambda m: f"{m.group(1).capitalize()} {m.group(2)}",
            cleaned,
        )

        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        cleaned = re.sub(r":(?!//)([^\s])", r": \1", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    def _apply_dictionary_replacements(self, text: str) -> str:
        updated = text
        for typo, correction in self._EXTENDED_TYPO_DICT.items():
            pattern = re.compile(r"\b" + re.escape(typo) + r"\b", flags=re.IGNORECASE)

            def replace(match: re.Match[str], default: str = correction) -> str:
                original = match.group(0)
                corrected = self._preserve_case(original, default)
                if self._feedback_lookup:
                    feedback_choice = self._feedback_lookup(original.lower())
                    if feedback_choice:
                        corrected = self._preserve_case(original, feedback_choice)
                self._record_correction(original, corrected, 0.95, "dictionary")
                return corrected

            updated = pattern.sub(replace, updated)
        return updated

    def _fuzzy_word_cleanup(self, text: str) -> str:
        parts = re.split(r"(\W+)", text)
        for idx, part in enumerate(parts):
            if not part or not part.isalpha():
                continue
            corrected_word, confidence, method = self._correct_word(part)
            if corrected_word != part:
                self._record_correction(part, corrected_word, confidence, method)
            parts[idx] = corrected_word
        return "".join(parts)

    def _correct_word(self, token: str) -> tuple[str, float, str]:
        token_lower = token.lower()

        # Phase 1: Skip correction for tokens that match locked entities
        if self._locked_entities:
            for entity in self._locked_entities:
                el = entity.lower()
                if token_lower == el:
                    return token, 1.0, "locked"
                # Token is a word within a multi-word locked entity
                if token_lower in el.split():
                    return token, 1.0, "locked"

        if token_lower in self._TECHNICAL_TERMS:
            return token, 1.0, "technical"

        if len(token_lower) < 4 or token_lower in self._KNOWN_WORDS:
            return token, 1.0, "known"

        if self._feedback_lookup:
            feedback_choice = self._feedback_lookup(token_lower)
            if feedback_choice:
                return self._preserve_case(token, feedback_choice), 1.0, "feedback"

        if token_lower in self._EXTENDED_TYPO_DICT:
            corrected = self._EXTENDED_TYPO_DICT[token_lower]
            return self._preserve_case(token, corrected), 0.95, "dictionary"

        if self._symspell_provider:
            suggestion = self._symspell_provider.correct_word(token_lower)
            if suggestion is not None:
                corrected, confidence = suggestion
                if (
                    corrected != token_lower
                    and confidence >= self._confidence_threshold
                    and self._is_candidate_safe(corrected)
                ):
                    return self._preserve_case(token, corrected), confidence, "symspell"

        if self._rapidfuzz_matcher:
            match = self._rapidfuzz_matcher.extract_one(
                token_lower,
                self._KNOWN_WORDS,
                score_cutoff=self._rapidfuzz_score_cutoff,
            )
            if match is not None:
                corrected, score = match
                confidence = score / 100.0
                if confidence >= self._confidence_threshold and self._is_candidate_safe(corrected):
                    return self._preserve_case(token, corrected), confidence, "rapidfuzz"

        matches = difflib.get_close_matches(
            token_lower,
            self._KNOWN_WORDS,
            n=self._max_suggestions,
            cutoff=min(0.85, self._confidence_threshold),
        )
        if not matches:
            return token, 0.0, "none"

        best_match = matches[0]
        similarity = difflib.SequenceMatcher(None, token_lower, best_match).ratio()
        if self._is_candidate_safe(best_match) and similarity >= self._confidence_threshold:
            return self._preserve_case(token, best_match), similarity, "difflib"

        return token, 0.0, "none"

    def _is_candidate_safe(self, candidate: str) -> bool:
        return candidate in self._FUZZY_SAFE_TARGETS or candidate in self._TECHNICAL_TERMS

    def _record_correction(
        self,
        original: str,
        corrected: str,
        confidence: float,
        method: str,
    ) -> None:
        if original.lower() == corrected.lower():
            return

        if self._log_corrections_enabled:
            key = (original.lower(), corrected.lower())
            self._correction_stats[key] += 1
            logger.debug(
                "Typo corrected: '%s' -> '%s' (confidence=%.3f, method=%s, count=%d)",
                original,
                corrected,
                confidence,
                method,
                self._correction_stats[key],
            )

        if self._correction_event_sink:
            self._correction_event_sink(
                CorrectionEvent(
                    original=original,
                    corrected=corrected,
                    confidence=confidence,
                    method=method,
                )
            )

    def _preserve_case(self, original: str, corrected: str) -> str:
        if original.isupper():
            return corrected.upper()
        if original[0].isupper():
            return corrected.capitalize()
        return corrected

    def get_correction_stats(self) -> dict[tuple[str, str], int]:
        """Return correction statistics for analysis."""
        return dict(self._correction_stats.most_common(100))

    def reset_stats(self) -> None:
        """Reset correction statistics."""
        self._correction_stats.clear()


# Drop-in replacement for backward compatibility
PromptQuickValidator = EnhancedPromptQuickValidator
