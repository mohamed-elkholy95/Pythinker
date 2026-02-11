"""Fast, deterministic prompt cleanup for typos and formatting noise."""

from __future__ import annotations

import difflib
import re


class PromptQuickValidator:
    """Apply a lightweight typo/format cleanup pass to user prompts.

    This is intentionally conservative and deterministic: it targets common
    mistakes in task verbs, research wording, and model names/version formats.
    """

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
        "settings",
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
    )

    _EXACT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
        (r"\blow[\s\-_]*effort\b", "low-effort"),
        (r"\bcompo+re\b", "compare"),
        (r"\bcomparre\b", "compare"),
        (r"\bsonet+\b", "sonnet"),
        (r"\bopu+s\b", "opus"),
        (r"\bpromtto\b", "prompt to"),
    )

    _MODEL_WITH_VERSION = re.compile(
        r"\b(opus|sonnet|haiku|gpt|claude|gemini|llama|mistral)\s*([0-9]+(?:\.[0-9]+)+)\b",
        flags=re.IGNORECASE,
    )

    def validate(self, text: str) -> str:
        """Return a cleaned prompt for downstream planning/analysis."""
        if not text:
            return text

        cleaned = text.strip()
        if not cleaned:
            return cleaned

        # Collapse repeated whitespace first.
        cleaned = re.sub(r"\s+", " ", cleaned)

        # Fast explicit typo replacements.
        for pattern, replacement in self._EXACT_REPLACEMENTS:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

        # Token-level conservative fuzzy correction.
        cleaned = self._fuzzy_word_cleanup(cleaned)

        # Normalize model/version adjacency and casing.
        cleaned = self._MODEL_WITH_VERSION.sub(lambda m: f"{m.group(1).capitalize()} {m.group(2)}", cleaned)

        # Punctuation spacing cleanup.
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        cleaned = re.sub(r"([:])([^\s])", r"\1 \2", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _fuzzy_word_cleanup(self, text: str) -> str:
        parts = re.split(r"(\W+)", text)
        for idx, part in enumerate(parts):
            if not part or not part.isalpha():
                continue
            parts[idx] = self._correct_word(part)
        return "".join(parts)

    def _correct_word(self, token: str) -> str:
        token_lower = token.lower()
        if len(token_lower) < 4 or token_lower in self._KNOWN_WORDS:
            return token

        match = difflib.get_close_matches(token_lower, self._KNOWN_WORDS, n=1, cutoff=0.88)
        if not match:
            return token

        corrected = match[0]
        if token.isupper():
            return corrected.upper()
        if token[0].isupper():
            return corrected.capitalize()
        return corrected
