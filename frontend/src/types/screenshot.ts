export interface ScreenshotMetadata {
  id: string
  session_id: string
  sequence_number: number
  timestamp: number
  trigger: 'tool_before' | 'tool_after' | 'periodic' | 'session_start' | 'session_end'
  tool_call_id?: string
  tool_name?: string
  function_name?: string
  action_type?: string
  size_bytes: number
  has_thumbnail: boolean
}

export interface ScreenshotListResponse {
  screenshots: ScreenshotMetadata[]
  total: number
}
