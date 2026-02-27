"""Coverage checks to keep concise responses complete."""

import re
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass(slots=True)
class CoverageValidationResult:
    """Result of output coverage validation."""

    is_valid: bool
    quality_score: float
    missing_requirements: list[str] = field(default_factory=list)
    addresses_user_request: bool = True
    has_artifact_references: bool = False
    has_caveat: bool = False


class OutputCoverageValidator:
    """Validate that compressed output still covers required deliverables."""

    _STOP_WORDS: ClassVar[set[str]] = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "with",
        "you",
        "your",
    }
    _CAVEAT_PATTERN = re.compile(r"\b(caveat|limitation|risk|warning|note)\b", re.IGNORECASE)
    _NO_ARTIFACT_PATTERN = re.compile(
        r"\b(no|none|n/?a)\s+(file\s+)?(artifacts?|files?|paths?|references?)\b",
        re.IGNORECASE,
    )
    _ARTIFACT_PATTERN = re.compile(
        r"(`[^`]+\.(?:py|ts|js|md|json|yaml|yml|txt|sql|sh|tsx?|jsx?)`|"
        r"(?:^|[\s(])(?:[A-Za-z]:\\|\.{0,2}/)?(?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]{1,8}(?::\d+)?)",
        re.IGNORECASE | re.MULTILINE,
    )

    _REQUIREMENT_PATTERNS: ClassVar[dict[str, tuple[str, ...]]] = {
        "final result": (
            r"\b(result|outcome|solution|answer|completed|implemented|updated|fixed|created|added"
            r"|findings|analysis|summary|conclusion|overview|discovered|identified|comparison"
            r"|recommendation|delivered|generated|produced|report|research)\b",
        ),
        "artifact references": (r"\b(file|path|diff|report|artifact)\b",),
        "key caveat": (r"\b(caveat|limitation|risk|warning|note)\b",),
        "next step": (r"\b(next step|follow-up|you can now|recommended)\b",),
    }

    def validate(
        self,
        output: str,
        user_request: str,
        required_sections: list[str] | None = None,
    ) -> CoverageValidationResult:
        """Validate whether output covers required content."""
        text = output or ""
        requirements = required_sections or ["final result"]
        missing: list[str] = [
            requirement for requirement in requirements if not self._contains_requirement(text, requirement)
        ]

        addresses_user_request = self._addresses_user_request(text, user_request)
        has_artifact_references = bool(self._ARTIFACT_PATTERN.search(text))
        has_explicit_no_artifacts = bool(self._NO_ARTIFACT_PATTERN.search(text))
        has_caveat = bool(self._CAVEAT_PATTERN.search(text))

        if "artifact references" in requirements and not (has_artifact_references or has_explicit_no_artifacts):
            missing.append("artifact references")
        if "key caveat" in requirements and not has_caveat:
            missing.append("key caveat")

        # Keep scoring simple and deterministic.
        checks = [
            1.0 if not missing else 0.0,
            1.0 if addresses_user_request else 0.0,
            1.0
            if ("artifact references" not in requirements or has_artifact_references or has_explicit_no_artifacts)
            else 0.0,
            1.0 if ("key caveat" not in requirements or has_caveat) else 0.0,
        ]
        quality_score = sum(checks) / len(checks)

        return CoverageValidationResult(
            is_valid=len(missing) == 0 and addresses_user_request,
            quality_score=quality_score,
            missing_requirements=sorted(set(missing)),
            addresses_user_request=addresses_user_request,
            has_artifact_references=has_artifact_references,
            has_caveat=has_caveat,
        )

    def _contains_requirement(self, text: str, requirement: str) -> bool:
        patterns = self._REQUIREMENT_PATTERNS.get(requirement.lower())
        if not patterns:
            # Unknown requirements are treated as soft checks.
            return True
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)

    def _addresses_user_request(self, output: str, user_request: str) -> bool:
        request_terms = self._extract_terms(user_request)
        if not request_terms:
            return True
        output_terms = self._extract_terms(output)
        if not output_terms:
            return False
        overlap = len(request_terms & output_terms)
        return overlap >= max(1, min(3, len(request_terms) // 3))

    def _extract_terms(self, text: str) -> set[str]:
        terms = set()
        for token in re.findall(r"[a-zA-Z0-9_]+", text.lower()):
            if len(token) < 3 or token in self._STOP_WORDS:
                continue
            terms.add(token)
        return terms
