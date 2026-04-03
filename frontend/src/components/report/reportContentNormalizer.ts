const H1_HEADING_RE = /^#\s+(.+)$/gm;
const UNVERIFIED_MARKER_RE = /\[(?:unverified(?:\s+[^\]\n]*?)?|not verified)\]?/gi;
const VERIFIED_MARKER_RE = /\[(?:verified(?:\s+[^\]\n]*?)?)\]?/gi;
const VERIFICATION_TAG_RE = /\[(?:unverified|verified|not verified)[^\]]*\]?/gi;
const LEGACY_PREVIOUSLY_CALLED_RE = /\s*\[Previously called \w+\]/g;

// Matches [N] where N is 1–3 digits, not preceded by ^ (footnote) and not followed by ( or ": "
// The (?!:\s) lookahead prevents matching link-ref-defs "[1]: URL" while still allowing
// citations before sentence colons like "enhances [1]:"
// Note: [ is intentionally NOT excluded so consecutive citations [1][2][3] all get linkified
const INLINE_CITATION_RE = /(?<!\^)\[(\d{1,3})\](?![(])(?!:\s)/g;
// Detects a "references/sources/bibliography" section heading (markdown heading)
const REFERENCES_HEADING_RE = /^#{1,4}\s*(references?|sources?|bibliography|citations?)\s*$/i;
// Detects bold-text reference headers: **Sources:** or **References** (common in chat messages)
const BOLD_REFERENCES_RE = /^\*{2}(references?|sources?|bibliography|citations?):?\*{2}\s*$/i;
// Ordered list item at the start of a line: "3. text"
const ORDERED_LIST_RE = /^(\s*)(\d+)\.\s+/;
// Bracket-style reference at the start of a line: "[3] text"
const BRACKET_REF_LINE_RE = /^(\s*)\[(\d+)\]\s+/;
// Link reference definition at the start of a line: "[3]: URL" (consumed by marked if not converted)
const LINK_REF_DEF_RE = /^(\s*)\[(\d+)\]:\s+(.+)/;
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

export const stripLegacyPreviouslyCalledMarkers = (content: string): string => {
  if (!content) return content;
  return content.replace(LEGACY_PREVIOUSLY_CALLED_RE, '');
};

/**
 * Converts a reference-section line to ordered-list markdown (`N. text`).
 * Returns `{ num, line }` if the line is a reference item, or `null` for
 * blank / non-reference lines (which are emitted as-is).
 */
const toRefItem = (
  line: string,
  trimmed: string,
  nextUnorderedRef: { value: number },
): { num: number; line: string } | null => {
  // Unordered list item "- text"
  const ulMatch = trimmed.match(/^[-*+]\s+(.+)/);
  if (ulMatch) {
    const num = nextUnorderedRef.value++;
    const indent = line.slice(0, line.length - trimmed.length);
    return { num, line: `${indent}${num}. ${ulMatch[1]}` };
  }

  // Ordered list item "3. text"
  const olMatch = ORDERED_LIST_RE.exec(line);
  if (olMatch) {
    return { num: parseInt(olMatch[2], 10), line };
  }

  // Bracket-style "[3] text"
  const bracketMatch = BRACKET_REF_LINE_RE.exec(line);
  if (bracketMatch) {
    const indent = bracketMatch[1];
    const num = parseInt(bracketMatch[2], 10);
    const rest = line.slice(bracketMatch[0].length);
    return { num, line: `${indent}${num}. ${rest}` };
  }

  // Link reference definition "[16]: URL" — marked silently consumes these
  const linkRefMatch = LINK_REF_DEF_RE.exec(line);
  if (linkRefMatch) {
    const indent = linkRefMatch[1];
    const num = parseInt(linkRefMatch[2], 10);
    const rest = linkRefMatch[3];
    return { num, line: `${indent}${num}. ${rest}` };
  }

  return null;
};

/**
 * Emits collected reference items as tight ordered-list groups.
 * When there is a numbering gap between consecutive items, inserts an HTML
 * comment to force marked to create a new `<ol start="N">`,
 * preserving the original reference numbers through the pipeline.
 */
const flushRefItems = (items: Array<{ num: number; line: string }>): string[] => {
  if (items.length === 0) return [];

  const result: string[] = [];
  let expectedNext = items[0].num;

  for (const item of items) {
    if (item.num !== expectedNext && result.length > 0) {
      // Numbering gap — force a new <ol> by inserting an HTML comment separator
      result.push('<!-- -->');
    }
    result.push(item.line);
    expectedNext = item.num + 1;
  }

  return result;
};

/**
 * Transforms inline citation numbers [N] into clickable anchor links and adds
 * id anchors to reference list items in the References/Sources section.
 *
 * Outside the references section: [5] becomes a superscript anchor link.
 * Inside the references section: converts all ref formats to tight ordered
 * lists with HTML comment separators between non-consecutive groups so that
 * marked produces `<ol start="N">` for each group (preserving numbering).
 * Skips code blocks entirely.
 */
export const linkifyInlineCitations = (markdown: string): string => {
  if (!markdown) return markdown;

  const lines = markdown.split('\n');
  const output: string[] = [];
  let inCodeFence = false;
  let inReferencesSection = false;
  const nextUnorderedRef = { value: 1 };

  // Buffer for collecting reference items to emit as tight groups
  let refBuffer: Array<{ num: number; line: string }> = [];

  const flushBuffer = () => {
    if (refBuffer.length > 0) {
      output.push(...flushRefItems(refBuffer));
      refBuffer = [];
    }
  };

  for (const line of lines) {
    const trimmed = line.trimStart();

    if (trimmed.startsWith('```')) {
      if (inReferencesSection) flushBuffer();
      inCodeFence = !inCodeFence;
      output.push(line);
      continue;
    }
    if (inCodeFence) {
      output.push(line);
      continue;
    }

    // Detect references/sources/bibliography heading (markdown heading or bold text)
    if (REFERENCES_HEADING_RE.test(trimmed) || BOLD_REFERENCES_RE.test(trimmed)) {
      flushBuffer();
      inReferencesSection = true;
      nextUnorderedRef.value = 1;
      output.push(line);
      continue;
    }

    // Any other heading exits the references section
    if (trimmed.startsWith('#')) {
      flushBuffer();
      inReferencesSection = false;
      output.push(line);
      continue;
    }

    // A bold-text section header (with colon, e.g. "**Conclusion:**") exits the references section.
    if (inReferencesSection && /^\*{2}[^*]+:\*{2}\s*$/.test(trimmed) && !BOLD_REFERENCES_RE.test(trimmed)) {
      flushBuffer();
      inReferencesSection = false;
    }

    if (inReferencesSection) {
      const refItem = toRefItem(line, trimmed, nextUnorderedRef);
      if (refItem) {
        refBuffer.push(refItem);
      } else {
        // Non-reference line (blank line or plain text) — skip blank lines
        // between reference items to keep lists tight. Emit non-blank lines.
        if (trimmed.length > 0) {
          flushBuffer();
          output.push(line);
        }
        // Blank lines between ref items are intentionally dropped to keep
        // the list tight, which prevents marked from renumbering items.
      }
      continue;
    }

    // Outside references section: linkify inline [N] patterns.
    // First move sentence-ending punctuation from after citation groups to before them
    // so citations always sit AFTER punctuation. e.g. "word [1]." → "word.[1]"
    const punct_normalized = line.replace(
      / *((?:\[\d{1,3}\]\s*)+)([.!?,;])\s*$/g,
      (_, cites: string, punct: string) => `${punct}${cites.trimEnd()}`,
    );
    output.push(
      punct_normalized.replace(INLINE_CITATION_RE, (_, num) => {
        return `<a href="#ref-${num}" class="inline-citation">${num}</a>`;
      }),
    );
  }

  // Flush any remaining buffered reference items
  flushBuffer();

  return output.join('\n');
};

export const stripLeadingMainTitle = (markdown: string): string => {
  if (!markdown) return markdown;
  const lines = markdown.split('\n');
  // Only remove the FIRST h1 heading (the document title).
  // Preserve subsequent h1 headings like "# References" or "# Sources"
  // which are needed by addReferenceAnchors for citation card rendering.
  let foundFirst = false;
  const filtered = lines.filter((line) => {
    if (!foundFirst && /^#\s+/.test(line)) {
      foundFirst = true;
      return false;
    }
    return true;
  });
  return filtered.join('\n');
};

/**
 * Fix malformed GFM alert blockquotes where a label prefix appears before the `>` marker.
 * LLMs sometimes generate `Caveat: > [!WARNING]` or `Next step: > Students must...`
 * instead of putting `>` at the start of the line. This normalizer moves such lines
 * into proper blockquote syntax so `marked` can parse them correctly.
 */
const normalizeInlineBlockquotes = (markdown: string): string => {
  if (!markdown) return markdown;
  // Match lines like "Label: > [!TYPE]" or "Label: > text" where label appears before blockquote
  return markdown.replace(
    /^([^\n>]*?):\s*>\s*(\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\].*)/gim,
    '> $2',
  );
};

/**
 * Normalize inline GFM alert markers that aren't at line-start into proper blockquote syntax.
 * Handles patterns like "Caveat: > [!WARNING]" or "Next step: > [!NOTE]"
 * by splitting them so the alert marker starts on its own line as a blockquote.
 */
export const normalizeInlineAlerts = (md: string): string => {
  return md.replace(
    /^(.+?)\s*>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$/gim,
    (_, prefix, type) => {
      const trimmedPrefix = prefix.replace(/:$/, '').trim();
      return trimmedPrefix ? `${trimmedPrefix}\n\n> [!${type.toUpperCase()}]` : `> [!${type.toUpperCase()}]`;
    },
  );
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

  let normalized = stripLegacyPreviouslyCalledMarkers(markdown);
  normalized = normalizeMarkdownLayout(normalized);
  normalized = normalizeInlineBlockquotes(normalized);
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
  const normalized = stripLegacyPreviouslyCalledMarkers(
    normalizeLineEndings(text).replace(/\t/g, '    ').trimEnd(),
  );
  const escapedFenceContent = normalized.replace(/```/g, '``\\`');
  return `\`\`\`text\n${escapedFenceContent}\n\`\`\``;
};
