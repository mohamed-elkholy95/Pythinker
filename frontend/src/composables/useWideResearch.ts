/**
 * Composable for managing wide research state and events
 *
 * Tracks parallel search progress from wide_research tool events
 * and provides reactive state for overlay visualizations.
 */

import { ref, computed, readonly } from 'vue'
import type { WideResearchState, WideResearchMiniState } from '@/types/message'

// Default search types if not specified
const DEFAULT_SEARCH_TYPES = ['info', 'news', 'academic']

// Internal state
const _state = ref<WideResearchState | null>(null)
const _isActive = ref(false)
const _lastUpdateTime = ref(0)

// Auto-clear timeout (clear state 5 seconds after completion)
let autoClearTimeout: ReturnType<typeof setTimeout> | null = null

/**
 * Parse wide_research progress from tool output
 * Format: "Progress: X/Y queries, Z sources found"
 */
function parseProgressOutput(output: string): { completed: number; total: number; sources: number } | null {
  const match = output.match(/Progress:\s*(\d+)\/(\d+)\s*queries,\s*(\d+)\s*sources/)
  if (match) {
    return {
      completed: parseInt(match[1], 10),
      total: parseInt(match[2], 10),
      sources: parseInt(match[3], 10)
    }
  }
  return null
}

/**
 * Determine status from progress data
 */
function determineStatus(completed: number, total: number): WideResearchState['status'] {
  if (completed === 0) return 'pending'
  if (completed >= total) return 'aggregating'
  return 'searching'
}

export function useWideResearch() {
  /**
   * Start tracking a new wide research session
   */
  function startResearch(data: {
    research_id: string
    topic: string
    search_types?: string[]
    aggregation_strategy?: string
  }) {
    // Clear any pending timeout
    if (autoClearTimeout) {
      clearTimeout(autoClearTimeout)
      autoClearTimeout = null
    }

    _state.value = {
      research_id: data.research_id,
      topic: data.topic,
      status: 'pending',
      total_queries: 0,
      completed_queries: 0,
      sources_found: 0,
      search_types: data.search_types || DEFAULT_SEARCH_TYPES,
      aggregation_strategy: data.aggregation_strategy
    }
    _isActive.value = true
    _lastUpdateTime.value = Date.now()
  }

  /**
   * Update progress from tool event
   */
  function updateProgress(data: {
    research_id: string
    tool_output?: string
    total_queries?: number
    completed_queries?: number
    sources_found?: number
    current_query?: string
  }) {
    if (!_state.value || _state.value.research_id !== data.research_id) {
      // Create new state if we missed the start event
      _state.value = {
        research_id: data.research_id,
        topic: 'Research in progress',
        status: 'searching',
        total_queries: data.total_queries || 0,
        completed_queries: data.completed_queries || 0,
        sources_found: data.sources_found || 0,
        search_types: DEFAULT_SEARCH_TYPES
      }
      _isActive.value = true
    }

    // Parse progress from tool_output if provided
    if (data.tool_output) {
      const parsed = parseProgressOutput(data.tool_output)
      if (parsed) {
        _state.value.completed_queries = parsed.completed
        _state.value.total_queries = parsed.total
        _state.value.sources_found = parsed.sources
        _state.value.status = determineStatus(parsed.completed, parsed.total)
      }
    }

    // Direct updates
    if (data.total_queries !== undefined) {
      _state.value.total_queries = data.total_queries
    }
    if (data.completed_queries !== undefined) {
      _state.value.completed_queries = data.completed_queries
    }
    if (data.sources_found !== undefined) {
      _state.value.sources_found = data.sources_found
    }
    if (data.current_query) {
      _state.value.current_query = data.current_query
    }

    // Update status based on progress
    if (_state.value.total_queries > 0) {
      _state.value.status = determineStatus(
        _state.value.completed_queries,
        _state.value.total_queries
      )
    }

    _lastUpdateTime.value = Date.now()
  }

  /**
   * Mark research as completed
   */
  function completeResearch(data: {
    research_id: string
    sources_count?: number
    synthesis?: string
    errors?: string[]
  }) {
    if (!_state.value || _state.value.research_id !== data.research_id) {
      return
    }

    _state.value.status = 'completed'
    if (data.sources_count !== undefined) {
      _state.value.sources_found = data.sources_count
    }
    if (data.errors && data.errors.length > 0) {
      _state.value.errors = data.errors
    }

    _lastUpdateTime.value = Date.now()

    // Auto-clear after delay
    autoClearTimeout = setTimeout(() => {
      clearResearch()
    }, 5000)
  }

  /**
   * Handle research failure
   */
  function failResearch(research_id: string, error: string) {
    if (!_state.value || _state.value.research_id !== research_id) {
      return
    }

    _state.value.status = 'failed'
    _state.value.errors = [error]
    _lastUpdateTime.value = Date.now()

    // Auto-clear after delay
    autoClearTimeout = setTimeout(() => {
      clearResearch()
    }, 5000)
  }

  /**
   * Clear research state
   */
  function clearResearch() {
    _state.value = null
    _isActive.value = false
    if (autoClearTimeout) {
      clearTimeout(autoClearTimeout)
      autoClearTimeout = null
    }
  }

  /**
   * Process a tool event to update wide research state
   * Call this from the SSE event handler when handling tool events
   */
  function handleToolEvent(event: {
    name: string
    function?: string
    args?: Record<string, unknown>
    content?: unknown
    status: 'calling' | 'called'
    tool_output?: string
  }) {
    // Only handle wide_research tool events
    if (event.name !== 'wide_research' && event.function !== 'wide_research') {
      return
    }

    const args = event.args || {}

    if (event.status === 'calling') {
      // Starting new research
      startResearch({
        research_id: (args.research_id as string) || `wr_${Date.now()}`,
        topic: (args.topic as string) || 'Research',
        search_types: args.search_types as string[] | undefined,
        aggregation_strategy: args.aggregation_strategy as string | undefined
      })
    } else if (event.status === 'called') {
      // Progress update or completion
      const research_id = (args.research_id as string) || _state.value?.research_id || ''

      // Check if this is a final result (has synthesis or aggregated_content)
      const content = event.content as Record<string, unknown> | undefined
      if (content && (content.synthesis || content.aggregated_content)) {
        completeResearch({
          research_id,
          sources_count: content.sources_count as number | undefined,
          synthesis: content.synthesis as string | undefined,
          errors: content.errors as string[] | undefined
        })
      } else if (event.tool_output) {
        // Progress update
        updateProgress({
          research_id,
          tool_output: event.tool_output
        })
      }
    }
  }

  // Computed getters for overlay components
  const overlayState = computed((): WideResearchState | null => _state.value)

  const miniState = computed((): WideResearchMiniState | null => {
    if (!_state.value) return null
    return {
      research_id: _state.value.research_id,
      status: _state.value.status,
      total_queries: _state.value.total_queries,
      completed_queries: _state.value.completed_queries,
      sources_found: _state.value.sources_found,
      search_types: _state.value.search_types
    }
  })

  const isActive = computed(() => _isActive.value)
  const isSearching = computed(() => _state.value?.status === 'searching')
  const isCompleted = computed(() => _state.value?.status === 'completed')

  return {
    // State (readonly)
    state: readonly(_state),
    overlayState,
    miniState,
    isActive,
    isSearching,
    isCompleted,

    // Actions
    startResearch,
    updateProgress,
    completeResearch,
    failResearch,
    clearResearch,
    handleToolEvent
  }
}

// Export singleton instance for global state sharing
let _instance: ReturnType<typeof useWideResearch> | null = null

export function useWideResearchGlobal() {
  if (!_instance) {
    _instance = useWideResearch()
  }
  return _instance
}
