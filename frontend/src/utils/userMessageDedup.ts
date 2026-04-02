/**
 * Normalize user message text for duplicate detection between optimistic UI and SSE.
 * Collapses line endings and horizontal whitespace so minor formatting differences
 * do not produce duplicate bubbles.
 */
export function normalizeUserMessageForDedup(raw: string): string {
  return raw
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .split('\n')
    .map((line) => line.replace(/[\t ]+/g, ' ').trimEnd())
    .join('\n')
    .trim();
}
