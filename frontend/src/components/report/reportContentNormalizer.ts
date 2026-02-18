const H1_HEADING_RE = /^#\s+(.+)$/gm;
const UNVERIFIED_MARKER_RE = /\[(?:unverified(?:\s+[^\]\n]*?)?|not verified)\]?/gi;
const VERIFIED_MARKER_RE = /\[(?:verified(?:\s+[^\]\n]*?)?)\]?/gi;
const VERIFICATION_TAG_RE = /\[(?:unverified|verified|not verified)[^\]]*\]?/gi;

const normalizeTitle = (title: string): string => title.trim().toLowerCase();

const qualityScore = (content: string): number => {
  const markerCount = (content.match(VERIFICATION_TAG_RE) || []).length;
  const openBrackets = (content.match(/\[/g) || []).length;
  const closeBrackets = (content.match(/\]/g) || []).length;
  const danglingBrackets = Math.abs(openBrackets - closeBrackets);
  const shortPenalty = content.length < 500 ? 1 : 0;
  return markerCount * 5 + danglingBrackets + shortPenalty;
};

export const collapseDuplicateReportBlocks = (content: string): string => {
  const normalized = (content || '').trim();
  if (normalized.length < 300) return normalized;

  const headings = Array.from(normalized.matchAll(H1_HEADING_RE));
  if (headings.length < 2) return normalized;

  const firstHeading = headings[0];
  const firstTitle = normalizeTitle(firstHeading[1] || '');
  const firstStart = firstHeading.index ?? -1;
  if (firstStart < 0) return normalized;

  const duplicateHeading = headings
    .slice(1)
    .find((heading) => normalizeTitle(heading[1] || '') === firstTitle);

  const duplicateStart = duplicateHeading?.index ?? -1;
  if (duplicateStart <= firstStart) return normalized;

  const firstBlock = normalized.slice(firstStart, duplicateStart).trim();
  const secondBlock = normalized.slice(duplicateStart).trim();
  if (secondBlock.length < 200) return normalized;

  const firstScore = qualityScore(firstBlock);
  const secondScore = qualityScore(secondBlock);
  const chosen =
    secondScore < firstScore || (secondScore === firstScore && secondBlock.length >= firstBlock.length)
      ? secondBlock
      : firstBlock;

  const prefix = normalized.slice(0, firstStart).trim();
  return prefix ? `${prefix}\n\n${chosen}` : chosen;
};

const isTableLine = (line: string): boolean => /^\s*\|.*\|\s*$/.test(line);

export const normalizeVerificationMarkers = (markdown: string): string => {
  if (!markdown) return markdown;

  const lines = markdown.split('\n');
  let inCodeFence = false;

  return lines
    .map((line) => {
      const trimmed = line.trimStart();
      if (trimmed.startsWith('```')) {
        inCodeFence = !inCodeFence;
        return line;
      }
      if (inCodeFence) return line;

      let hasUnverifiedClaim = false;
      let cleaned = line.replace(UNVERIFIED_MARKER_RE, () => {
        hasUnverifiedClaim = true;
        return '';
      });
      cleaned = cleaned.replace(VERIFIED_MARKER_RE, '');

      const leadingWhitespace = cleaned.match(/^\s*/)?.[0] || '';
      const body = cleaned.slice(leadingWhitespace.length).replace(/[ \t]{2,}/g, ' ').trimEnd();
      const normalizedLine = leadingWhitespace + body;

      if (hasUnverifiedClaim && body.length > 0 && !isTableLine(normalizedLine)) {
        return `${normalizedLine} <sup class="verification-marker verification-marker-unverified" title="Unverified claim">†</sup>`;
      }

      return normalizedLine;
    })
    .join('\n');
};
