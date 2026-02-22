const H1_HEADING_RE = /^#\s+(.+)$/gm;
const UNVERIFIED_MARKER_RE = /\[(?:unverified(?:\s+[^\]\n]*?)?|not verified)\]?/gi;
const VERIFIED_MARKER_RE = /\[(?:verified(?:\s+[^\]\n]*?)?)\]?/gi;
const VERIFICATION_TAG_RE = /\[(?:unverified|verified|not verified)[^\]]*\]?/gi;

// Matches [N] where N is 1–3 digits, not preceded by ^ (footnote) and not followed by ( or :
// Note: [ is intentionally NOT excluded so consecutive citations [1][2][3] all get linkified
const INLINE_CITATION_RE = /(?<!\^)\[(\d{1,3})\](?![(:])/g;
// Detects a "references/sources/bibliography" section heading (markdown heading)
const REFERENCES_HEADING_RE = /^#{1,4}\s*(references?|sources?|bibliography|citations?)\s*$/i;
// Detects bold-text reference headers: **Sources:** or **References** (common in chat messages)
const BOLD_REFERENCES_RE = /^\*{2}(references?|sources?|bibliography|citations?):?\*{2}\s*$/i;
// Ordered list item at the start of a line: "3. text"
const ORDERED_LIST_RE = /^(\s*)(\d+)\.\s+/;
// Bracket-style reference at the start of a line: "[3] text"
const BRACKET_REF_LINE_RE = /^(\s*)\[(\d+)\]\s+/;
const EXCESS_BLANK_LINES_RE = /\n{3,}/g;

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

const normalizeLineEndings = (content: string): string => content.replace(/\r\n?/g, '\n');

/**
 * Transforms inline citation numbers [N] into clickable anchor links and adds
 * id anchors to reference list items in the References/Sources section.
 *
 * Outside the references section: [5] becomes a superscript anchor link.
 * Inside an ordered references section: prepends list items with an id anchor span.
 * Skips code blocks entirely.
 */
export const linkifyInlineCitations = (markdown: string): string => {
  if (!markdown) return markdown;

  const lines = markdown.split('\n');
  let inCodeFence = false;
  let inReferencesSection = false;

  return lines
    .map((line) => {
      const trimmed = line.trimStart();

      if (trimmed.startsWith('```')) {
        inCodeFence = !inCodeFence;
        return line;
      }
      if (inCodeFence) return line;

      // Detect references/sources/bibliography heading (markdown heading or bold text)
      if (REFERENCES_HEADING_RE.test(trimmed) || BOLD_REFERENCES_RE.test(trimmed)) {
        inReferencesSection = true;
        return line;
      }

      // Any other heading exits the references section
      if (trimmed.startsWith('#')) {
        inReferencesSection = false;
        return line;
      }

      // A bold-text section header (with colon, e.g. "**Conclusion:**") exits the references section.
      // Only match lines ending with ":**" to avoid false exits on bold content within references
      // (e.g. "**Important**" used as emphasis within a reference entry).
      if (inReferencesSection && /^\*{2}[^*]+:\*{2}\s*$/.test(trimmed) && !BOLD_REFERENCES_RE.test(trimmed)) {
        inReferencesSection = false;
      }

      if (inReferencesSection) {
        // Ordered list item "1. text" — inject id anchor before the content
        const olMatch = ORDERED_LIST_RE.exec(line);
        if (olMatch) {
          const indent = olMatch[1];
          const num = olMatch[2];
          const rest = line.slice(olMatch[0].length);
          return `${indent}${num}. <span id="ref-${num}"></span>${rest}`;
        }

        // Bracket-style "[1] text" — replace with id anchor
        const bracketMatch = BRACKET_REF_LINE_RE.exec(line);
        if (bracketMatch) {
          const indent = bracketMatch[1];
          const num = bracketMatch[2];
          const rest = line.slice(bracketMatch[0].length);
          return `${indent}<span id="ref-${num}">[${num}]</span> ${rest}`;
        }

        return line;
      }

      // Outside references section: linkify inline [N] patterns.
      // First move sentence-ending punctuation from after citation groups to before them
      // so citations always sit AFTER punctuation. e.g. "word [1]." → "word.[1]"
      const punct_normalized = line.replace(
        / *((?:\[\d{1,3}\]\s*)+)([.!?,;])\s*$/g,
        (_, cites: string, punct: string) => `${punct}${cites.trimEnd()}`,
      );
      return punct_normalized.replace(INLINE_CITATION_RE, (_, num) => {
        return `<a href="#ref-${num}" class="inline-citation">${num}</a>`;
      });
    })
    .join('\n');
};

export const stripLeadingMainTitle = (markdown: string): string => {
  if (!markdown) return markdown;
  const lines = markdown.split('\n');
  const filtered = lines.filter((line) => !line.match(/^#\s+/));
  return filtered.join('\n');
};

export const normalizeMarkdownLayout = (markdown: string): string => {
  if (!markdown) return markdown;
  return normalizeLineEndings(markdown).replace(EXCESS_BLANK_LINES_RE, '\n\n').trim();
};

export const prepareMarkdownForViewer = (
  markdown: string,
  options?: { stripMainTitle?: boolean; collapseDuplicateBlocks?: boolean }
): string => {
  if (!markdown) return '';
  const shouldCollapse = options?.collapseDuplicateBlocks ?? true;
  const shouldStripMainTitle = options?.stripMainTitle ?? false;

  let normalized = normalizeMarkdownLayout(markdown);
  if (shouldCollapse) {
    normalized = collapseDuplicateReportBlocks(normalized);
  }
  normalized = normalizeVerificationMarkers(normalized);
  if (shouldStripMainTitle) {
    normalized = stripLeadingMainTitle(normalized);
  }
  return normalizeMarkdownLayout(normalized);
};

export const preparePlainTextForViewer = (text: string): string => {
  if (!text) return '';
  const normalized = normalizeLineEndings(text).replace(/\t/g, '    ').trimEnd();
  const escapedFenceContent = normalized.replace(/```/g, '``\\`');
  return `\`\`\`text\n${escapedFenceContent}\n\`\`\``;
};
