"""Contradiction detection and resolution for memory evidence.

Phase 4: Detects contradictions in retrieved memories using rule-based
and LLM-based approaches to prevent conflicting information injection.
"""

import logging
import re
from typing import TYPE_CHECKING

from app.domain.exceptions.base import LLMKeysExhaustedError

if TYPE_CHECKING:
    from app.domain.external.llm import LLM
    from app.domain.models.memory_evidence import MemoryEvidence

logger = logging.getLogger(__name__)


class ContradictionResolver:
    """Detect and resolve contradictions in retrieved memories."""

    def __init__(self, llm: "LLM | None" = None):
        """Initialize contradiction resolver.

        Args:
            llm: Optional LLM for semantic contradiction detection
        """
        self.llm = llm

    async def detect_contradictions(
        self,
        evidence_list: list["MemoryEvidence"],
    ) -> list["MemoryEvidence"]:
        """Detect contradictions between memories.

        Uses multiple strategies:
        1. Rule-based numeric contradiction detection (fast)
        2. Rule-based negation detection (fast)
        3. LLM-based semantic detection (optional, slower)

        Args:
            evidence_list: List of memory evidence to check

        Returns:
            Evidence list with contradictions marked
        """
        if len(evidence_list) < 2:
            return evidence_list

        # 1. Rule-based contradiction detection (fast)
        evidence_list = self._detect_numeric_contradictions(evidence_list)
        evidence_list = self._detect_negation_contradictions(evidence_list)

        # 2. LLM-based contradiction detection (optional, slower)
        # Only use for small sets to avoid performance issues
        if self.llm and len(evidence_list) <= 10:
            try:
                evidence_list = await self._detect_llm_contradictions(evidence_list)
            except Exception as e:
                logger.debug(f"LLM contradiction detection failed: {e}")

        return evidence_list

    def _detect_numeric_contradictions(
        self,
        evidence_list: list["MemoryEvidence"],
    ) -> list["MemoryEvidence"]:
        """Detect contradicting numeric claims.

        Example: "Price is 100" vs "Price is 150"
        """
        # Extract numeric claims: "X is Y" where Y is a number
        numeric_pattern = r"(\w+)\s+(?:is|are|was|were)\s+(\d+(?:\.\d+)?)"

        claims = []
        for evidence in evidence_list:
            matches = re.findall(numeric_pattern, evidence.content, re.IGNORECASE)
            for entity, value in matches:
                claims.append(
                    {
                        "evidence": evidence,
                        "entity": entity.lower(),
                        "value": float(value),
                    }
                )

        # Check for contradictions
        for i, claim1 in enumerate(claims):
            for claim2 in claims[i + 1 :]:
                if claim1["entity"] == claim2["entity"]:
                    # Same entity with different numeric values
                    value1 = claim1["value"]
                    value2 = claim2["value"]
                    max_val = max(value1, value2)
                    if max_val == 0:
                        # Both zero — identical, not a contradiction
                        continue
                    diff_pct = abs(value1 - value2) / max_val

                    if diff_pct > 0.1:  # 10% difference threshold
                        # Mark contradiction
                        ev1 = claim1["evidence"]
                        ev2 = claim2["evidence"]

                        if ev2.memory_id not in ev1.contradictions:
                            ev1.contradictions.append(ev2.memory_id)
                            ev1.contradiction_reasons.append(
                                f"Numeric conflict: {claim1['entity']} = {value1} vs {value2}"
                            )

                        if ev1.memory_id not in ev2.contradictions:
                            ev2.contradictions.append(ev1.memory_id)
                            ev2.contradiction_reasons.append(
                                f"Numeric conflict: {claim2['entity']} = {value2} vs {value1}"
                            )

        return evidence_list

    def _detect_negation_contradictions(
        self,
        evidence_list: list["MemoryEvidence"],
    ) -> list["MemoryEvidence"]:
        """Detect direct negations (X vs not X).

        Example: "User prefers dark mode" vs "User does not prefer dark mode"
        """
        for i, ev1 in enumerate(evidence_list):
            for ev2 in evidence_list[i + 1 :]:
                # Simple negation check
                content1 = ev1.content.lower()
                content2 = ev2.content.lower()

                # Check for "not" or "never" in one but not the other
                has_negation_1 = "not " in content1 or "never " in content1
                has_negation_2 = "not " in content2 or "never " in content2

                if has_negation_1 != has_negation_2 and self._shares_keywords(content1, content2, min_shared=3):
                    # One has negation, other doesn't - potential contradiction
                    if ev2.memory_id not in ev1.contradictions:
                        ev1.contradictions.append(ev2.memory_id)
                        ev1.contradiction_reasons.append("Direct negation detected")

                    if ev1.memory_id not in ev2.contradictions:
                        ev2.contradictions.append(ev1.memory_id)
                        ev2.contradiction_reasons.append("Direct negation detected")

        return evidence_list

    def _shares_keywords(self, text1: str, text2: str, min_shared: int = 3) -> bool:
        """Check if two texts share significant keywords.

        Args:
            text1: First text
            text2: Second text
            min_shared: Minimum number of shared keywords

        Returns:
            True if texts share at least min_shared keywords
        """
        # Extract words of 4+ characters (filter out common small words)
        words1 = set(re.findall(r"\b\w{4,}\b", text1.lower()))
        words2 = set(re.findall(r"\b\w{4,}\b", text2.lower()))

        return len(words1 & words2) >= min_shared

    @staticmethod
    def _safe_index(value: object, upper_bound: int) -> int | None:
        """Coerce an LLM-returned value to a valid list index.

        LLM JSON may return None, strings ("0"), floats (1.0), or
        garbage for index fields.  This safely converts to int and
        validates the range [0, upper_bound).

        Returns:
            Valid int index, or None if the value is unusable.
        """
        if value is None:
            return None
        try:
            idx = int(value)
        except (TypeError, ValueError):
            return None
        if 0 <= idx < upper_bound:
            return idx
        return None

    async def _detect_llm_contradictions(
        self,
        evidence_list: list["MemoryEvidence"],
    ) -> list["MemoryEvidence"]:
        """Use LLM to detect semantic contradictions.

        Example: "User lives in New York" vs "User lives in California"
        """
        if not self.llm:
            return evidence_list

        # Format evidence for LLM
        evidence_text = "\n\n".join([f"[{i}] {ev.content}" for i, ev in enumerate(evidence_list)])

        prompt = f"""Analyze the following pieces of evidence and identify contradictions.

Evidence:
{evidence_text}

Return JSON: {{"contradictions": [{{"id1": 0, "id2": 1, "reason": "explanation"}}, ...]}}

Only report clear contradictions, not just different perspectives.
For example, "User prefers Python" and "User also uses JavaScript" are NOT contradictions."""

        try:
            response = await self.llm.ask(
                messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"}
            )

            import json

            data = json.loads(response.get("content", "{}"))
            n = len(evidence_list)

            for contradiction in data.get("contradictions", []):
                id1 = self._safe_index(contradiction.get("id1"), n)
                id2 = self._safe_index(contradiction.get("id2"), n)
                reason = contradiction.get("reason", "Semantic contradiction")

                if id1 is None or id2 is None or id1 == id2:
                    continue

                ev1 = evidence_list[id1]
                ev2 = evidence_list[id2]

                if ev2.memory_id not in ev1.contradictions:
                    ev1.contradictions.append(ev2.memory_id)
                    ev1.contradiction_reasons.append(reason)

                if ev1.memory_id not in ev2.contradictions:
                    ev2.contradictions.append(ev1.memory_id)
                    ev2.contradiction_reasons.append(reason)

        except Exception as e:
            if isinstance(e, LLMKeysExhaustedError):
                logger.debug("LLM contradiction detection skipped: %s", e)
            else:
                logger.warning("LLM contradiction detection failed: %s", e)

        return evidence_list


# Singleton instance
_resolver: ContradictionResolver | None = None


def get_contradiction_resolver(llm: "LLM | None" = None) -> ContradictionResolver:
    """Get singleton contradiction resolver instance.

    Args:
        llm: Optional LLM for semantic contradiction detection

    Returns:
        ContradictionResolver instance
    """
    global _resolver
    if _resolver is None:
        _resolver = ContradictionResolver(llm=llm)
    return _resolver
