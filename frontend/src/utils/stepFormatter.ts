/**
 * Formats step descriptions for optimal display in the UI.
 * Strips redundant prefixes and provides smart word-boundary truncation.
 */

export interface FormattedStepDescription {
  /** Compact version for display */
  short: string
  /** Original full description */
  full: string
  /** Whether the description was truncated */
  shouldTruncate: boolean
}

const REDUNDANT_PREFIXES = [
  /^step\s*\d+[:.]\s*/i,
  /^task[:.]\s*/i,
  /^action[:.]\s*/i,
]

/**
 * Format a step description for UI display.
 * Strips redundant prefixes and truncates at word boundaries.
 */
export function formatStepDescription(
  description: string,
  maxLength: number = 65,
): FormattedStepDescription {
  if (!description) {
    return { short: '', full: '', shouldTruncate: false }
  }

  let cleaned = description.trim()

  // Strip redundant prefixes like "Step 1:", "Task:"
  for (const prefix of REDUNDANT_PREFIXES) {
    cleaned = cleaned.replace(prefix, '')
  }
  cleaned = cleaned.trim()

  // If it fits, return as-is
  if (cleaned.length <= maxLength) {
    return { short: cleaned, full: cleaned, shouldTruncate: false }
  }

  // Truncate at word boundary
  const truncated = cleaned.slice(0, maxLength)
  const lastSpace = truncated.lastIndexOf(' ')
  const short = lastSpace > maxLength * 0.6
    ? truncated.slice(0, lastSpace)
    : truncated

  return {
    short: short.replace(/[,;:.]$/, '').trim(),
    full: cleaned,
    shouldTruncate: true,
  }
}
