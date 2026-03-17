"""SymSpell-backed correction provider adapter."""

from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SymSpellProvider:
    """Word-level correction provider using SymSpellPy."""

    def __init__(
        self,
        *,
        dictionary_path: str,
        bigram_path: str,
        max_edit_distance: int,
        prefix_length: int,
    ) -> None:
        from symspellpy import SymSpell

        self._max_edit_distance = max_edit_distance
        self._sym_spell = SymSpell(
            max_dictionary_edit_distance=max_edit_distance,
            prefix_length=prefix_length,
        )

        dictionary_loaded = self._load_dictionary(dictionary_path)
        bigram_loaded = self._load_bigram_dictionary(bigram_path)
        if not dictionary_loaded:
            raise RuntimeError("SymSpell dictionary could not be loaded")

        if not bigram_loaded:
            logger.warning("SymSpell bigram dictionary not loaded; compound correction quality may be reduced")

        self._add_technical_terms()

    def correct_word(self, word: str) -> tuple[str, float] | None:
        from symspellpy import Verbosity

        suggestions = self._sym_spell.lookup(
            word,
            Verbosity.CLOSEST,
            max_edit_distance=self._max_edit_distance,
            include_unknown=False,
        )
        if not suggestions:
            return None

        best = suggestions[0]
        if best.term == word:
            return None

        confidence = max(0.0, 1.0 - (best.distance / max(1, self._max_edit_distance + 1)))
        return best.term, confidence

    def correct_text(self, text: str) -> str:
        suggestions = self._sym_spell.lookup_compound(
            text,
            max_edit_distance=self._max_edit_distance,
            transfer_casing=True,
        )
        if not suggestions:
            return text
        return suggestions[0].term

    def _load_dictionary(self, dictionary_path: str) -> bool:
        path = Path(dictionary_path)
        if path.exists():
            return self._sym_spell.load_dictionary(str(path), term_index=0, count_index=1)

        fallback = importlib.resources.files("symspellpy") / "frequency_dictionary_en_82_765.txt"
        return self._sym_spell.load_dictionary(fallback, term_index=0, count_index=1)

    def _load_bigram_dictionary(self, bigram_path: str) -> bool:
        path = Path(bigram_path)
        if path.exists():
            return self._sym_spell.load_bigram_dictionary(str(path), term_index=0, count_index=2)

        fallback = importlib.resources.files("symspellpy") / "frequency_bigramdictionary_en_243_342.txt"
        return self._sym_spell.load_bigram_dictionary(fallback, term_index=0, count_index=2)

    def _add_technical_terms(self) -> None:
        technical_terms = {
            "pythinker": 10000,
            "qdrant": 8000,
            "fastapi": 8000,
            "playwright": 7000,
            "docker": 10000,
            "kubernetes": 9000,
            "pytest": 7000,
            "llm": 9000,
            "embedding": 8000,
            "tokenizer": 6000,
            "inference": 7000,
            "transformer": 7000,
            "async": 9000,
            "await": 9000,
            "asyncio": 7000,
        }

        for term, frequency in technical_terms.items():
            self._sym_spell.create_dictionary_entry(term, frequency)
