const LEAKED_TOOL_CALL_BLOCK_RE =
  /\s*<(?:tool_call|function_call)\b[^>]*>.*?(?:<\/(?:tool_call|function_call)>|$)/gis
const ORPHANED_TOOL_CALL_END_RE = /<\/(?:tool_call|function_call)>/gi
const LEAKED_INTERNAL_STATUS_RE =
  /\s*(?:\*\*)?\[?\s*(Sandbox Browser|SYSTEM NOTE|CONTEXT PRESSURE|FOCUSED(?: CONTENT)?|AUTO-TERMINATED|Audit failure|Step time|INFORMATIONAL|SYSTEM|Tool result|Attempted to call|Previously called):\s*(?:Navigating to|Connecting to|Opening|Loading|Visiting|Reading|Clicking|Typing|Searching|Fetching|Inspecting|Reloading)\b[^\n]*|\s*(?:\*\*)?\[?\s*(Sandbox Browser|SYSTEM NOTE|CONTEXT PRESSURE|FOCUSED(?: CONTENT)?|AUTO-TERMINATED|Audit failure|Step time|INFORMATIONAL|SYSTEM|Tool result|Attempted to call|Previously called):[^\n]*/gi

export function stripLeakedToolCallMarkup(text: string | null | undefined): string {
  if (!text) {
    return ''
  }

  let cleaned = text.replace(LEAKED_TOOL_CALL_BLOCK_RE, '')
  cleaned = cleaned.replace(ORPHANED_TOOL_CALL_END_RE, '')
  cleaned = cleaned.replace(LEAKED_INTERNAL_STATUS_RE, '')
  cleaned = cleaned.replace(/\s+([.,!?;:])/g, '$1')
  cleaned = cleaned.replace(/[ \t]{2,}/g, ' ')
  return cleaned.trim()
}
