"""RapidFuzz-based similarity matcher adapter."""

from __future__ import annotations

from collections.abc import Sequence


class RapidFuzzMatcher:
    """Adapter exposing a tiny interface over RapidFuzz process matching."""

    def __init__(self) -> None:
        from rapidfuzz import fuzz, process, utils

        self._fuzz = fuzz
        self._process = process
        self._utils = utils

    def extract_one(
        self,
        query: str,
        choices: Sequence[str],
        *,
        score_cutoff: float,
    ) -> tuple[str, float] | None:
        result = self._process.extractOne(
            query,
            choices,
            scorer=self._fuzz.WRatio,
            processor=self._utils.default_process,
            score_cutoff=score_cutoff,
        )
        if result is None:
            return None

        match, score, _ = result
        return str(match), float(score)
