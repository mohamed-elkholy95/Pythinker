"""Deterministic response compressor used after quality checks."""

import re

from app.domain.services.agents.response_policy import VerbosityMode


class ResponseCompressor:
    """Compresses long markdown output while keeping critical details."""

    _CAVEAT_PATTERN = re.compile(r"\b(caveat|limitation|risk|warning|note)\b", re.IGNORECASE)
    _ACTION_PATTERN = re.compile(r"\b(next step|follow-up|you can now|run|verify)\b", re.IGNORECASE)
    _ARTIFACT_PATTERN = re.compile(
        r"(`[^`]+\.(?:py|ts|js|md|json|yaml|yml|txt|sql|sh|tsx?|jsx?)`|"
        r"(?:^|[\s(])(?:[A-Za-z]:\\|\.{0,2}/)?(?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]{1,8}(?::\d+)?)",
        re.IGNORECASE | re.MULTILINE,
    )

    def compress(self, content: str, mode: VerbosityMode, max_chars: int = 4000) -> str:
        """Compress content only when concise mode is requested."""
        if mode != VerbosityMode.CONCISE:
            return content

        text = (content or "").strip()
        if len(text) <= max_chars:
            return text

        blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
        if not blocks:
            return text[:max_chars].strip()

        heading = ""
        if blocks and blocks[0].startswith("#"):
            heading = blocks.pop(0)

        summary_blocks = blocks[:4]  # Increased from 2 to 4 blocks
        artifact_lines = self._extract_lines(text, self._ARTIFACT_PATTERN, limit=8)  # Increased from 3 to 8
        caveat_line = self._extract_first_matching_line(text, self._CAVEAT_PATTERN)
        next_step_line = self._extract_first_matching_line(text, self._ACTION_PATTERN)

        parts: list[str] = []
        if heading:
            parts.append(heading)
        parts.extend(summary_blocks)

        if artifact_lines:
            artifact_section = "Key artifacts:\n" + "\n".join(f"- {line}" for line in artifact_lines)
            parts.append(artifact_section)

        if caveat_line and caveat_line not in " ".join(parts):
            parts.append(f"Caveat: {caveat_line}")

        if next_step_line and next_step_line not in " ".join(parts):
            parts.append(f"Next step: {next_step_line}")

        compressed = "\n\n".join(part for part in parts if part).strip()
        if len(compressed) > max_chars:
            compressed = compressed[:max_chars].rstrip() + "..."
        return compressed

    def _extract_lines(self, text: str, pattern: re.Pattern[str], limit: int) -> list[str]:
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if pattern.search(stripped):
                lines.append(stripped)
                if len(lines) >= limit:
                    break
        return lines

    def _extract_first_matching_line(self, text: str, pattern: re.Pattern[str]) -> str | None:
        for line in text.splitlines():
            stripped = line.strip(" -\t")
            if stripped and pattern.search(stripped):
                return stripped
        return None
