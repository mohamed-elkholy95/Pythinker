const LEAKED_TOOL_CALL_BLOCK_RE =
  /\s*<(?:tool_call|function_call)\b[^>]*>.*?(?:<\/(?:tool_call|function_call)>|$)/gis
const ORPHANED_TOOL_CALL_END_RE = /<\/(?:tool_call|function_call)>/gi

export function stripLeakedToolCallMarkup(text: string | null | undefined): string {
  if (!text) {
    return ''
  }

  let cleaned = text.replace(LEAKED_TOOL_CALL_BLOCK_RE, '')
  cleaned = cleaned.replace(ORPHANED_TOOL_CALL_END_RE, '')
  cleaned = cleaned.replace(/\s+([.,!?;:])/g, '$1')
  cleaned = cleaned.replace(/[ \t]{2,}/g, ' ')
  return cleaned.trim()
}
