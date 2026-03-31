const LEAKED_TOOL_CALL_BLOCK_RE =
  /\s*<(?:tool_call|function_call)\b[^>]*>.*?(?:<\/(?:tool_call|function_call)>|$)/gis
const ORPHANED_TOOL_CALL_END_RE = /<\/(?:tool_call|function_call)>/gi
const LEAKED_INTERNAL_STATUS_RE =
  /\s*(?:\*\*)?\[?\s*(Sandbox Browser|SYSTEM NOTE|CONTEXT PRESSURE|FOCUSED(?: CONTENT)?|AUTO-TERMINATED|Audit failure|Step time|INFORMATIONAL|SYSTEM|Tool result|Attempted to call|Previously called):\s*(?:Navigating to|Connecting to|Opening|Loading|Visiting|Reading|Clicking|Typing|Searching|Fetching|Inspecting|Reloading)\b[^\n]*|\s*(?:\*\*)?\[?\s*(Sandbox Browser|SYSTEM NOTE|CONTEXT PRESSURE|FOCUSED(?: CONTENT)?|AUTO-TERMINATED|Audit failure|Step time|INFORMATIONAL|SYSTEM|Tool result|Attempted to call|Previously called):[^\n]*/gi
// Word-boundary regex that matches any payload key as a standalone word.
// Prevents false positives where "url" matches inside "furniture" or
// "task" matches inside "multitasking".
const RAW_TOOL_PAYLOAD_KEY_WORD_RE =
  /\b(?:tool_call|function_call|search_depth|date_range|tool|function|query|arguments|params|top_n|url|task)\b/gi

// Structural check: a JSON key followed by a colon, optionally quoted.
const RAW_TOOL_KEY_COLON_RE =
  /["']?(?:tool_call|function_call|search_depth|date_range|tool|function|query|arguments|params|top_n|url|task)["']?\s*:/i

export function stripLeakedToolCallMarkup(text: string | null | undefined): string {
  if (!text) {
    return ''
  }

  let cleaned = text.replace(LEAKED_TOOL_CALL_BLOCK_RE, '')
  cleaned = cleaned.replace(ORPHANED_TOOL_CALL_END_RE, '')
  cleaned = cleaned.replace(LEAKED_INTERNAL_STATUS_RE, '')
  cleaned = stripTrailingRawToolPayload(cleaned)
  cleaned = cleaned.replace(/\s+([.,!?;:])/g, '$1')
  cleaned = cleaned.replace(/[ \t]{2,}/g, ' ')
  return cleaned.trim()
}

function countWordBoundaryKeyMatches(text: string): number {
  const matches = text.match(RAW_TOOL_PAYLOAD_KEY_WORD_RE)
  return matches ? matches.length : 0
}

function stripTrailingRawToolPayload(text: string): string {
  for (const opener of ['{', '[']) {
    const start = text.lastIndexOf(opener)
    if (start === -1) {
      continue
    }

    const tail = text.slice(start).trim()
    if (tail.length < 8) {
      continue
    }

    const keyCount = countWordBoundaryKeyMatches(tail)
    if (keyCount === 0) {
      continue
    }

    // Branch 1: entire tail is JSON-like characters AND multiple keys matched.
    // Multiple word-boundary matches make coincidence extremely unlikely.
    if (keyCount >= 2 && /^[\s{}[\]":,A-Za-z0-9_\-./?=&%+!@#$%^*<>\\]+$/.test(tail)) {
      return text.slice(0, start).trimEnd()
    }

    // Branch 2: tail contains a structural JSON key-colon pattern.
    // A single key match + actual JSON structure is a strong signal.
    if (RAW_TOOL_KEY_COLON_RE.test(tail)) {
      return text.slice(0, start).trimEnd()
    }
  }

  return text
}
