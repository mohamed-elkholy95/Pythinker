/**
 * Agent Events Bridge Composable
 *
 * Bridges SSE events from the Pythinker agent to OpenReplay custom events.
 * This allows agent activities to appear in the OpenReplay timeline with
 * searchable metadata for debugging and analysis.
 */
import { ref, onUnmounted } from 'vue'
import { trackEvent, trackIssue, setMetadata } from './useOpenReplay'
import type {
  AgentSSEEvent,
  ToolEventData,
  StepEventData,
  MessageEventData,
  ErrorEventData,
  PlanEventData,
  ProgressEventData,
  StreamEventData,
  DeepResearchEventData,
  WideResearchEventData,
  WaitEventData,
  ReportEventData
} from '../types/event'
import { useWideResearchGlobal } from './useWideResearch'

// Event statistics for debugging
interface EventStats {
  totalEvents: number
  toolEvents: number
  stepEvents: number
  messageEvents: number
  errorEvents: number
  planEvents: number
}

const stats = ref<EventStats>({
  totalEvents: 0,
  toolEvents: 0,
  stepEvents: 0,
  messageEvents: 0,
  errorEvents: 0,
  planEvents: 0
})

// Tool timing tracking
const toolStartTimes = new Map<string, number>()

/**
 * Track a tool event (tool execution start/complete)
 */
function handleToolEvent(data: ToolEventData): void {
  stats.value.toolEvents++
  stats.value.totalEvents++

  // Handle wide_research tool events to update overlay state
  if (data.name === 'wide_research' || data.function === 'wide_research') {
    const wideResearch = useWideResearchGlobal()
    wideResearch.handleToolEvent({
      name: data.name,
      function: data.function,
      args: data.args,
      content: data.content,
      status: data.status
    })
  }

  if (data.status === 'calling') {
    // Tool execution starting
    toolStartTimes.set(data.tool_call_id, Date.now())

    trackEvent('agent_tool_start', {
      tool_call_id: data.tool_call_id,
      tool_name: data.name,
      function: data.function,
      action_type: data.action_type,
      // Include command for shell tools
      command: data.command,
      cwd: data.cwd,
      // Include file path for file operations
      file_path: data.file_path,
      // Security context if present
      security_risk: data.security_risk,
      confirmation_state: data.confirmation_state
    })
  } else if (data.status === 'called') {
    // Tool execution completed
    const startTime = toolStartTimes.get(data.tool_call_id)
    const duration = startTime ? Date.now() - startTime : undefined
    toolStartTimes.delete(data.tool_call_id)

    trackEvent('agent_tool_complete', {
      tool_call_id: data.tool_call_id,
      tool_name: data.name,
      function: data.function,
      duration_ms: duration,
      // Shell tool results
      exit_code: data.exit_code,
      // File tool results
      diff: data.diff ? 'present' : undefined,
      // Runtime status
      runtime_status: data.runtime_status,
      // Flag if there was an error
      has_error: data.exit_code !== undefined && data.exit_code !== 0
    })

    // Track issues for failed commands
    if (data.exit_code !== undefined && data.exit_code !== 0) {
      trackIssue('tool_execution_failed', {
        tool_call_id: data.tool_call_id,
        tool_name: data.name,
        exit_code: data.exit_code,
        stderr: data.stderr?.substring(0, 500) // Truncate for storage
      })
    }
  }
}

/**
 * Track a step event (plan step status change)
 */
function handleStepEvent(data: StepEventData): void {
  stats.value.stepEvents++
  stats.value.totalEvents++

  trackEvent('agent_step', {
    step_id: data.id,
    status: data.status,
    description: data.description.substring(0, 200) // Truncate for storage
  })

  // Track step failures as issues
  if (data.status === 'failed') {
    trackIssue('step_failed', {
      step_id: data.id,
      description: data.description.substring(0, 200)
    })
  }
}

/**
 * Track a message event (user/assistant message)
 */
function handleMessageEvent(data: MessageEventData): void {
  stats.value.messageEvents++
  stats.value.totalEvents++

  trackEvent('agent_message', {
    role: data.role,
    content_length: data.content?.length ?? 0,
    has_attachments: (data.attachments?.length ?? 0) > 0,
    attachment_count: data.attachments?.length ?? 0
  })
}

/**
 * Track an error event
 */
function handleErrorEvent(data: ErrorEventData): void {
  stats.value.errorEvents++
  stats.value.totalEvents++

  trackIssue('agent_error', {
    error: data.error.substring(0, 500) // Truncate for storage
  })
}

/**
 * Track a plan event (new plan created)
 */
function handlePlanEvent(data: PlanEventData): void {
  stats.value.planEvents++
  stats.value.totalEvents++

  trackEvent('agent_plan_created', {
    step_count: data.steps?.length ?? 0,
    steps: data.steps?.map((s) => ({
      id: s.id,
      status: s.status,
      description: s.description.substring(0, 100)
    }))
  })
}

/**
 * Track a progress event (planning phase changes)
 */
function handleProgressEvent(data: ProgressEventData): void {
  stats.value.totalEvents++

  trackEvent('agent_progress', {
    phase: data.phase,
    message: data.message.substring(0, 200),
    estimated_steps: data.estimated_steps,
    progress_percent: data.progress_percent
  })

  // Also update metadata for current phase
  setMetadata('agent_phase', data.phase)
}

/**
 * Track a wait event (waiting for user input)
 */
function handleWaitEvent(_data: WaitEventData): void {
  stats.value.totalEvents++

  trackEvent('agent_waiting', {
    reason: 'user_input'
  })
}

/**
 * Track a stream event (streaming response)
 */
function handleStreamEvent(data: StreamEventData): void {
  // Only track final stream events to avoid noise
  if (data.is_final) {
    stats.value.totalEvents++
    trackEvent('agent_stream_complete', {
      content_length: data.content?.length ?? 0
    })
  }
}

/**
 * Track a deep research event
 */
function handleDeepResearchEvent(data: DeepResearchEventData): void {
  stats.value.totalEvents++

  trackEvent('agent_deep_research', {
    research_id: data.research_id,
    status: data.status,
    total_queries: data.total_queries,
    completed_queries: data.completed_queries,
    progress_percent: data.total_queries > 0 ? Math.round((data.completed_queries / data.total_queries) * 100) : 0
  })
}

/**
 * Track a wide research event (parallel multi-source search)
 */
function handleWideResearchEvent(data: WideResearchEventData): void {
  stats.value.totalEvents++

  // Update the global wide research state
  const wideResearch = useWideResearchGlobal()

  if (data.status === 'pending') {
    wideResearch.startResearch({
      research_id: data.research_id,
      topic: data.topic,
      search_types: data.search_types,
      aggregation_strategy: data.aggregation_strategy
    })
  } else if (data.status === 'searching' || data.status === 'aggregating') {
    wideResearch.updateProgress({
      research_id: data.research_id,
      total_queries: data.total_queries,
      completed_queries: data.completed_queries,
      sources_found: data.sources_found,
      current_query: data.current_query
    })
  } else if (data.status === 'completed') {
    wideResearch.completeResearch({
      research_id: data.research_id,
      sources_count: data.sources_found
    })
  } else if (data.status === 'failed') {
    wideResearch.failResearch(data.research_id, data.errors?.join(', ') || 'Unknown error')
  }

  // Track to OpenReplay timeline
  trackEvent('agent_wide_research', {
    research_id: data.research_id,
    topic: data.topic,
    status: data.status,
    total_queries: data.total_queries,
    completed_queries: data.completed_queries,
    sources_found: data.sources_found,
    search_types: data.search_types,
    progress_percent: data.total_queries > 0 ? Math.round((data.completed_queries / data.total_queries) * 100) : 0
  })
}

/**
 * Track a report event (report generated)
 */
function handleReportEvent(data: ReportEventData): void {
  stats.value.totalEvents++

  trackEvent('agent_report_generated', {
    report_id: data.id,
    title: data.title.substring(0, 100),
    content_length: data.content?.length ?? 0,
    has_attachments: (data.attachments?.length ?? 0) > 0,
    source_count: data.sources?.length ?? 0
  })
}

/**
 * Track session start
 */
function trackSessionStart(sessionId: string, mode: string): void {
  trackEvent('session_start', {
    session_id: sessionId,
    mode
  })
  setMetadata('session_id', sessionId)
  setMetadata('session_mode', mode)
}

/**
 * Track session end
 */
function trackSessionEnd(sessionId: string, status: string): void {
  trackEvent('session_end', {
    session_id: sessionId,
    status,
    total_events: stats.value.totalEvents,
    tool_events: stats.value.toolEvents,
    step_events: stats.value.stepEvents,
    error_events: stats.value.errorEvents
  })
}

/**
 * Track user takeover
 */
function trackUserTakeover(sessionId: string): void {
  trackEvent('user_takeover', {
    session_id: sessionId
  })
}

/**
 * Track user resume
 */
function trackUserResume(sessionId: string): void {
  trackEvent('user_resume', {
    session_id: sessionId
  })
}

/**
 * Main event handler - routes SSE events to appropriate handlers
 */
function handleAgentEvent(event: AgentSSEEvent): void {
  switch (event.event) {
    case 'tool':
      handleToolEvent(event.data as ToolEventData)
      break
    case 'step':
      handleStepEvent(event.data as StepEventData)
      break
    case 'message':
      handleMessageEvent(event.data as MessageEventData)
      break
    case 'error':
      handleErrorEvent(event.data as ErrorEventData)
      break
    case 'plan':
      handlePlanEvent(event.data as PlanEventData)
      break
    case 'progress':
      handleProgressEvent(event.data as ProgressEventData)
      break
    case 'wait':
      handleWaitEvent(event.data as WaitEventData)
      break
    case 'stream':
      handleStreamEvent(event.data as StreamEventData)
      break
    case 'deep_research':
      handleDeepResearchEvent(event.data as DeepResearchEventData)
      break
    case 'wide_research':
      handleWideResearchEvent(event.data as WideResearchEventData)
      break
    case 'report':
      handleReportEvent(event.data as ReportEventData)
      break
    case 'done':
      trackEvent('agent_done', {})
      break
    case 'title':
      // Title events are UI-only, skip tracking
      break
    case 'attachments':
      // Attachment events are UI-only, skip tracking
      break
    case 'mode_change':
      trackEvent('agent_mode_change', event.data as unknown as Record<string, unknown>)
      break
    case 'suggestion':
      // Suggestion events are UI-only, skip tracking
      break
    default:
      // Unknown event type
      console.debug('[AgentEvents] Unknown event type:', event.event)
  }
}

/**
 * Reset statistics (call when starting a new session)
 */
function resetStats(): void {
  stats.value = {
    totalEvents: 0,
    toolEvents: 0,
    stepEvents: 0,
    messageEvents: 0,
    errorEvents: 0,
    planEvents: 0
  }
  toolStartTimes.clear()
}

/**
 * Main composable export
 */
export function useAgentEvents() {
  // Cleanup on unmount
  onUnmounted(() => {
    toolStartTimes.clear()
  })

  return {
    // State
    stats,

    // Event handlers
    handleAgentEvent,
    handleToolEvent,
    handleStepEvent,
    handleMessageEvent,
    handleErrorEvent,
    handlePlanEvent,

    // Session lifecycle
    trackSessionStart,
    trackSessionEnd,
    trackUserTakeover,
    trackUserResume,

    // Utilities
    resetStats
  }
}

// Export individual handlers for direct usage
export {
  handleAgentEvent,
  trackSessionStart,
  trackSessionEnd,
  trackUserTakeover,
  trackUserResume
}
