"""Post-generation citation integrity validator for research reports.

Catches:
- Orphan citations: [N] used inline but not in References
- Phantom references: [N] in References but never cited inline
- Citation gaps: non-sequential numbering
- Duplicate URLs in References

Includes a repair() method that appends missing reference entries from the
known source list when available.
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
    if not report_content or not source_list:
        return report_content

    result = validate_citations(report_content)
    if result.is_valid or not result.orphan_citations:
        return report_content

    # Parse source_list into a lookup: number → full entry line
    source_entries: dict[int, str] = {}
    for m in _REF_ENTRY_RE.finditer(source_list):
        source_entries[int(m.group(1))] = m.group(0).strip()

    # Find entries we can repair
    repairs = [source_entries[num] for num in result.orphan_citations if num in source_entries]

    if not repairs:
        return report_content

    # Append to the References section
    ref_match = _REF_SECTION_RE.search(report_content)
    if ref_match:
        # Append after existing References section
        repaired = report_content.rstrip() + "\n" + "\n".join(repairs) + "\n"
    else:
        # No References section exists — create one
        repaired = report_content.rstrip() + "\n\n## References\n" + "\n".join(repairs) + "\n"

    logger.info(
        "Repaired %d orphan citation(s) by appending reference entries from source list",
        len(repairs),
    )
    return repaired
