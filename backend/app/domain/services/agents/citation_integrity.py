"""Post-generation citation integrity validator for research reports.

Catches:
- Orphan citations: [N] used inline but not in References
- Phantom references: [N] in References but never cited inline
- Citation gaps: non-sequential numbering
- Duplicate URLs in References

Includes repair helpers that:
- append missing reference entries from the known source list when available
- prune phantom references
- normalize numbering to a contiguous [1..N] sequence when gaps remain
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Pre-compiled patterns
_INLINE_CITATION_RE = re.compile(r"\[(\d+)\]")
_REF_ENTRY_RE = re.compile(r"^\s*\[(\d+)\]\s+(.+)$", re.MULTILINE)
_REF_SECTION_RE = re.compile(r"^##\s+References?\s*$", re.MULTILINE | re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s)>\]]+")


@dataclass
class CitationIntegrityResult:
    """Result of citation integrity validation."""

    is_valid: bool
    orphan_citations: list[int] = field(default_factory=list)
    phantom_references: list[int] = field(default_factory=list)
    citation_gaps: list[int] = field(default_factory=list)
    duplicate_urls: list[str] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return (
            len(self.orphan_citations)
            + len(self.phantom_references)
            + len(self.citation_gaps)
            + len(self.duplicate_urls)
        )


def validate_citations(report_content: str) -> CitationIntegrityResult:
    """Validate citation integrity in a research report.

    Args:
        report_content: Full markdown report text.

    Returns:
        CitationIntegrityResult with any detected issues.
    """
    if not report_content:
        return CitationIntegrityResult(is_valid=True)

    # Split report into body and references section
    ref_match = _REF_SECTION_RE.search(report_content)
    if ref_match:
        body = report_content[: ref_match.start()]
        ref_section = report_content[ref_match.end() :]
    else:
        body = report_content
        ref_section = ""

    # Extract inline citation numbers from body (exclude the References section itself)
    inline_nums: set[int] = set()
    for m in _INLINE_CITATION_RE.finditer(body):
        inline_nums.add(int(m.group(1)))

    # Extract reference entry numbers and URLs
    ref_nums: set[int] = set()
    ref_urls: list[str] = []
    for m in _REF_ENTRY_RE.finditer(ref_section):
        num = int(m.group(1))
        ref_nums.add(num)
        entry_text = m.group(2)
        url_match = _URL_RE.search(entry_text)
        if url_match:
            ref_urls.append(url_match.group(0))

    # Orphan citations: used inline but not in References
    orphan = sorted(inline_nums - ref_nums)

    # Phantom references: in References but never cited
    phantom = sorted(ref_nums - inline_nums)

    # Citation gaps: check sequential numbering
    all_nums = sorted(inline_nums | ref_nums)
    gaps: list[int] = []
    if all_nums:
        expected = set(range(1, max(all_nums) + 1))
        gaps = sorted(expected - (inline_nums | ref_nums))

    # Duplicate URLs
    seen_urls: set[str] = set()
    dupe_urls: list[str] = []
    for url in ref_urls:
        normalized = url.rstrip("/")
        if normalized in seen_urls:
            dupe_urls.append(url)
        else:
            seen_urls.add(normalized)

    is_valid = not orphan and not phantom and not gaps and not dupe_urls
    return CitationIntegrityResult(
        is_valid=is_valid,
        orphan_citations=orphan,
        phantom_references=phantom,
        citation_gaps=gaps,
        duplicate_urls=dupe_urls,
    )


def prune_phantom_references(report_content: str) -> str:
    """Remove reference entries that are never cited inline."""
    if not report_content:
        return report_content

    validation = validate_citations(report_content)
    if not validation.phantom_references:
        return report_content

    ref_match = _REF_SECTION_RE.search(report_content)
    if not ref_match:
        return report_content

    body = report_content[: ref_match.start()]
    ref_section = report_content[ref_match.end() :]
    phantom_set = set(validation.phantom_references)

    kept_lines: list[str] = []
    removed = 0
    for line in ref_section.splitlines():
        entry_match = _REF_ENTRY_RE.match(line)
        if entry_match and int(entry_match.group(1)) in phantom_set:
            removed += 1
            continue
        kept_lines.append(line)

    kept_ref_block = "\n".join(kept_lines).strip()
    repaired = f"{body.rstrip()}\n\n## References\n{kept_ref_block}\n" if kept_ref_block else body.rstrip() + "\n"

    logger.info("Pruned %d phantom reference(s)", removed)
    return repaired


def normalize_citation_numbering(report_content: str) -> str:
    """Reindex citation numbers to a contiguous [1..N] sequence.

    This is useful after truncation/continuation stitching where both inline
    citations and reference entries may be internally consistent but sparse
    (for example: [4], [6], [7]). The function remaps all citation tokens
    deterministically while preserving relative ordering.
    """
    if not report_content:
        return report_content

    observed_numbers = sorted({int(m.group(1)) for m in _INLINE_CITATION_RE.finditer(report_content)})
    if not observed_numbers:
        return report_content

    expected_numbers = list(range(1, len(observed_numbers) + 1))
    if observed_numbers == expected_numbers:
        return report_content

    remap = {old_num: new_num for new_num, old_num in enumerate(observed_numbers, start=1)}

    def _renumber(match: re.Match) -> str:
        old_num = int(match.group(1))
        return f"[{remap.get(old_num, old_num)}]"

    normalized = _INLINE_CITATION_RE.sub(_renumber, report_content)
    logger.info(
        "Normalized citation numbering to contiguous range [1..%d] (observed=%s)",
        len(observed_numbers),
        observed_numbers,
    )
    return normalized


def rebase_continuation_citations(base_text: str, continuation_text: str) -> str:
    """Shift [N] citation numbers in continuation_text to be sequential after base_text.

    When an LLM continuation restarts citation numbering from [1], merging it
    directly with the base chunk produces citation collisions (two different sources
    both labelled [1]).  This function detects that case and shifts every [N] in
    continuation_text — both inline references and ## References entries — by the
    maximum citation number already present in base_text.

    Example:
        base ends with … [3] Smith 2024 …
        continuation starts [1] Jones 2025 …
        → continuation is rebased to [4] Jones 2025 …

    No-ops when:
    - Either argument is empty
    - base_text contains no citations (no conflict possible)
    - continuation_text contains no citations
    - continuation numbering is already sequential (min > max_base)
    """
    if not base_text or not continuation_text:
        return continuation_text

    base_nums = [int(m) for m in _INLINE_CITATION_RE.findall(base_text)]
    if not base_nums:
        return continuation_text  # No citations in base — no conflict possible

    max_base = max(base_nums)

    cont_nums = [int(m) for m in _INLINE_CITATION_RE.findall(continuation_text)]
    if not cont_nums:
        return continuation_text  # Continuation has no citations — nothing to rebase

    min_cont = min(cont_nums)
    if min_cont > max_base:
        return continuation_text  # Already sequential — no action needed

    offset = max_base

    def _shift(m: re.Match) -> str:
        return f"[{int(m.group(1)) + offset}]"

    rebased = _INLINE_CITATION_RE.sub(_shift, continuation_text)
    logger.debug(
        "rebase_continuation_citations: offset=%d, cont_range=[%d..%d] → [%d..%d]",
        offset,
        min_cont,
        max(cont_nums),
        min_cont + offset,
        max(cont_nums) + offset,
    )
    return rebased


def repair_citations(report_content: str, source_list: str) -> str:
    """Attempt to repair citation integrity issues by appending missing reference entries.

    Only repairs orphan citations (inline [N] without matching Reference entry)
    when a source_list is available with the corresponding [N] entry.

    Args:
        report_content: Full markdown report text.
        source_list: Numbered bibliography (e.g. "[1] Title - URL\\n[2] ...").

    Returns:
        Report with missing reference entries appended, or original if no repairs needed.
    """
    if not report_content:
        return report_content

    result = validate_citations(report_content)
    if result.is_valid:
        return report_content

    repaired = report_content

    # Repair orphan citations from provided source list when possible.
    if result.orphan_citations and source_list:
        source_entries: dict[int, str] = {}
        for m in _REF_ENTRY_RE.finditer(source_list):
            source_entries[int(m.group(1))] = m.group(0).strip()

        repairs = [source_entries[num] for num in result.orphan_citations if num in source_entries]
        if repairs:
            ref_match = _REF_SECTION_RE.search(repaired)
            if ref_match:
                repaired = repaired.rstrip() + "\n" + "\n".join(repairs) + "\n"
            else:
                repaired = repaired.rstrip() + "\n\n## References\n" + "\n".join(repairs) + "\n"

            logger.info(
                "Repaired %d orphan citation(s) by appending reference entries from source list",
                len(repairs),
            )

    # Remove references that are never cited inline.
    repaired = prune_phantom_references(repaired)

    # Normalize sparse numbering caused by continuation stitching when all
    # inline citations are still backed by References entries.
    post_prune = validate_citations(repaired)
    if post_prune.citation_gaps and not post_prune.orphan_citations:
        repaired = normalize_citation_numbering(repaired)

    return repaired


class SourceRegistry:
    """Pre-generation stable source numbering. Deduplicates by URL."""

    def __init__(self) -> None:
        self._url_to_id: dict[str, int] = {}
        self._id_to_entry: dict[int, tuple[str, str]] = {}
        self._next_id: int = 1

    def register(self, url: str, title: str = "") -> int:
        """Register a source URL. Returns stable ID (reuses if URL seen before)."""
        normalized = url.strip().rstrip("/").lower()
        if normalized in self._url_to_id:
            return self._url_to_id[normalized]
        sid = self._next_id
        self._url_to_id[normalized] = sid
        self._id_to_entry[sid] = (title, url)
        self._next_id += 1
        return sid

    def get_id(self, url: str) -> int | None:
        """Get ID for a URL, or None if not registered."""
        return self._url_to_id.get(url.strip().rstrip("/").lower())

    @property
    def count(self) -> int:
        return len(self._id_to_entry)

    def build_references_section(self) -> str:
        """Generate a ## References section from registered sources."""
        lines = ["## References"]
        for sid in sorted(self._id_to_entry):
            title, url = self._id_to_entry[sid]
            lines.append(f"[{sid}] {title} - {url}")
        return "\n".join(lines)


def fuzzy_match_orphan(
    orphan_text: str, references: dict[int, str], threshold: float = 0.6
) -> int | None:
    """Try to fuzzy-match an orphan citation to an existing reference.

    Returns reference ID if match found above threshold, else None.
    Simple word-overlap scoring (no external dependencies).
    """
    orphan_words = set(orphan_text.lower().split())
    if not orphan_words:
        return None

    best_id = None
    best_score = 0.0

    for ref_id, ref_text in references.items():
        ref_words = set(ref_text.lower().split())
        if not ref_words:
            continue
        overlap = len(orphan_words & ref_words)
        score = overlap / max(len(orphan_words), len(ref_words))
        if score > best_score and score >= threshold:
            best_score = score
            best_id = ref_id

    return best_id
