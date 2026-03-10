"""RequestContract entity extraction (2026-02-13 agent robustness plan).

Deterministic regex-based extraction. No LLM call required.
"""

from __future__ import annotations

import re

from app.domain.models.request_contract import RequestContract

# Model name patterns: Claude Sonnet 4.5, GPT-4, Llama 3.2, etc.
_MODEL_PATTERNS = [
    re.compile(
        r"Claude\s+(?:Sonnet|Opus|Haiku)\s+[\d.]+",
        re.IGNORECASE,
    ),
    re.compile(r"GPT-?\d+(?:\.\d+)?", re.IGNORECASE),
    re.compile(r"Llama\s*\d+(?:\.\d+)?", re.IGNORECASE),
    re.compile(r"Gemini\s*(?:Pro|Flash)?\s*[\d.]*", re.IGNORECASE),
    re.compile(r"Mistral\s*(?:Small|Medium|Large)?\s*[\d.]*", re.IGNORECASE),
    re.compile(r"GLM-?\s*[\d.]+", re.IGNORECASE),
]

# Version numbers: v1.2.3, version 3.12, 0.115
_VERSION_PATTERNS = [
    re.compile(r"v?(\d+\.\d+(?:\.\d+)?)"),
    re.compile(r"version\s+(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE),
]

# Technology names from enhanced validator
_TECH_TERMS = frozenset(
    {
        "qdrant",
        "fastapi",
        "pytest",
        "docker",
        "kubernetes",
        "playwright",
        "vue",
        "pinia",
        "typescript",
        "mongodb",
        "redis",
        "pydantic",
        "python",
        "javascript",
        "react",
        "node",
        "postgresql",
    }
)

# Output filenames: report.md, data.csv, results.json, etc.
_FILENAME_PATTERN = re.compile(r"\b([A-Za-z0-9_][A-Za-z0-9._-]*\.(?:md|txt|csv|json|html|png|pdf))\b")

# Numeric constraints: top 5, 10 items, under $100
_NUMERIC_PATTERNS = [
    re.compile(r"top\s+\d+", re.IGNORECASE),
    re.compile(r"\d+\s*(?:items|results|examples)", re.IGNORECASE),
    re.compile(r"under\s+\$?\d+", re.IGNORECASE),
    re.compile(r"first\s+\d+", re.IGNORECASE),
    re.compile(r"last\s+\d+", re.IGNORECASE),
]


def _extract_quoted_strings(text: str) -> list[str]:
    """Extract quoted exact phrases."""
    quoted: list[str] = []
    for pattern in [r'"([^"]+)"', r"'([^']+)'"]:
        quoted.extend(m.group(1).strip() for m in re.finditer(pattern, text))
    return quoted


def _extract_capitalized_sequences(text: str) -> list[str]:
    """Extract capitalized multi-word sequences (Proper Noun Sequences)."""
    # Match sequences like "Claude Sonnet", "Python 3.12"
    pattern = re.compile(r"\b([A-Z][a-zA-Z0-9]*(?:\s+[A-Za-z0-9.]+)+)\b")
    return list({m.group(1) for m in pattern.finditer(text)})


def extract(
    query: str,
    intent: str = "",
    action_type: str = "general",
) -> RequestContract:
    """Extract RequestContract from user query.

    Deterministic, fast (< 5ms). No LLM call.
    """
    if not query or not query.strip():
        return RequestContract(
            exact_query=query or "",
            intent=intent,
            action_type=action_type,
            locked_entities=[],
            locked_versions=[],
            numeric_constraints=[],
            extraction_method="hybrid",
            extraction_confidence=0.0,
        )

    text = query.strip()
    entities: list[str] = []
    versions: list[str] = []
    numeric: list[str] = []
    method_components: list[str] = []
    confidence = 1.0

    # 1. Regex patterns for known entity types
    for pattern in _MODEL_PATTERNS:
        for m in pattern.finditer(text):
            entities.append(m.group(0))
            method_components.append("regex")
    for pattern in _VERSION_PATTERNS:
        for m in pattern.finditer(text):
            ver = m.group(1) if m.lastindex else m.group(0)
            versions.append(ver)
            method_components.append("regex")
    for pattern in _NUMERIC_PATTERNS:
        for m in pattern.finditer(text):
            numeric.append(m.group(0))
            method_components.append("regex")

    # 2. Technology names (whitelist match)
    words = set(re.findall(r"\b\w+\b", text.lower()))
    for tech in _TECH_TERMS:
        if tech in words:
            # Get the original casing from text
            tech_re = re.compile(rf"\b({re.escape(tech)})\b", re.IGNORECASE)
            for m in tech_re.finditer(text):
                entities.append(m.group(1))
                method_components.append("regex")
                break

    # 3. Python/JavaScript etc. with version
    py_match = re.search(r"Python\s+(\d+\.\d+)", text, re.IGNORECASE)
    if py_match:
        entities.append(py_match.group(0))
        if py_match.group(1) not in versions:
            versions.append(py_match.group(1))
    js_match = re.search(r"JavaScript\s*(?:ES\d+)?\s*(\d+\.\d+)?", text, re.IGNORECASE)
    if js_match:
        entities.append(js_match.group(0).strip())

    # 4. Fallback: quoted strings (lower confidence)
    quoted = _extract_quoted_strings(text)
    for q in quoted:
        if q and q not in entities and len(q) > 2:
            entities.append(q)
            method_components.append("quoted")
            confidence = min(confidence, 0.7)

    # 5. Fallback: capitalized sequences (lower confidence)
    capped = _extract_capitalized_sequences(text)
    for c in capped:
        if c not in entities and len(c.split()) >= 2:
            entities.append(c)
            method_components.append("capitalized")
            confidence = min(confidence, 0.7)

    # Deduplicate preserving order
    seen_e: set[str] = set()
    unique_entities: list[str] = []
    for e in entities:
        key = e.lower()
        if key not in seen_e:
            seen_e.add(key)
            unique_entities.append(e)

    seen_v: set[str] = set()
    unique_versions: list[str] = []
    for v in versions:
        if v not in seen_v:
            seen_v.add(v)
            unique_versions.append(v)

    # 6. Requested output filenames
    filenames: list[str] = list(dict.fromkeys(m.group(1) for m in _FILENAME_PATTERN.finditer(text)))

    extraction_method = (
        "hybrid"
        if "regex" in method_components or len(method_components) > 1
        else (method_components[0] if method_components else "none")
    )

    return RequestContract(
        exact_query=query,
        intent=intent,
        action_type=action_type,
        locked_entities=unique_entities,
        locked_versions=unique_versions,
        numeric_constraints=list(dict.fromkeys(numeric)),
        requested_filenames=filenames,
        extraction_method=extraction_method,
        extraction_confidence=confidence,
    )
