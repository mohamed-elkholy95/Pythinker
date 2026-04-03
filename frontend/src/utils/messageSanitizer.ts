const LEAKED_TOOL_CALL_BLOCK_RE =
  /\s*<(?:tool_call|function_call)\b[^>]*>.*?(?:<\/(?:tool_call|function_call)>|$)/gis
const ORPHANED_TOOL_CALL_END_RE =
  /(?:<\/(?:tool_call|function_call)>|\b[\w-]+\/(?:tool_)?function_call>)/gi
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

const RAW_TOOL_PAYLOAD_ALLOWED_CHARS_RE = /^[\s":,A-Za-z0-9_\-./?=&%+!@#$%^*<>\\]+$/

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

function stripTrailingToolWrapper(text: string): string {
  return text.replace(/\s+(?:adaptor|adapter)\s*$/i, '').trimEnd()
}

function hasBalancedBrackets(text: string): boolean {
  let balance = 0
  for (const char of text) {
    if (char === '{' || char === '[') {
      balance += 1
    } else if (char === '}' || char === ']') {
      balance -= 1
      if (balance < 0) return false
    }
  }
  return balance === 0
}

function findTrailingPayloadBoundary(text: string): number | null {
  const lastClosing = Math.max(text.lastIndexOf('}'), text.lastIndexOf(']'))
  if (lastClosing === -1) return null

  const core = text.slice(0, lastClosing + 1).trimEnd()
  const suffix = text.slice(lastClosing + 1).trim()

  if (!hasBalancedBrackets(core)) return null
  if (suffix && !/^(?:[A-Za-z][\w/-]*|>+)$/.test(suffix)) return null

  return lastClosing + 1
}

function isLikelyRawToolPayload(payload: string): boolean {
  const keyCount = countWordBoundaryKeyMatches(payload)
  if (keyCount === 0) return false

  if (keyCount >= 2) {
    const payloadWithoutBrackets = payload.split('{').join('').split('}').join('').split('[').join('').split(']').join('')
    if (RAW_TOOL_PAYLOAD_ALLOWED_CHARS_RE.test(payloadWithoutBrackets)) {
      return true
    }
  }

  return RAW_TOOL_KEY_COLON_RE.test(payload)
}

function stripTrailingRawToolPayload(text: string): string {
  const openerPositions: number[] = []
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (char === '{' || char === '[') {
      openerPositions.push(index)
    }
  }

  for (const start of openerPositions) {
    const tail = text.slice(start).trim()
    if (tail.length < 8) continue

    const boundary = findTrailingPayloadBoundary(tail)
    if (boundary === null) continue

    const payload = tail.slice(0, boundary).trimEnd()
    if (isLikelyRawToolPayload(payload)) {
      return stripTrailingToolWrapper(text.slice(0, start))
    }
  }

  return text
}
