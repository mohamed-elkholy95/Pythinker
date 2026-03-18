/**
 * Tool store — manages tool execution state globally via Pinia.
 *
 * Tracks the tool call timeline, active tool executions, streaming output
 * buffers, and panel selection state. Composables become thin facades.
 */
import { defineStore } from 'pinia'
import { ref, shallowRef, computed } from 'vue'
import type { ToolContent, SourceCitation } from '../types/message'

// ── Interfaces ──────────────────────────────────────────────────────

/** A recorded tool call in the timeline with optional result metadata. */
export interface ToolTimelineEntry {
  toolCallId: string
  name: string
  functionName: string
  args: Record<string, unknown>
  status: 'calling' | 'running' | 'called' | 'interrupted'
  startedAt: number
  completedAt?: number
  /** Human-readable description (e.g., "Search for OpenRouter models") */
  displayCommand?: string
  /** Tool category (e.g., "search", "browse", "shell") */
  commandCategory?: string
  /** Result payload after tool completes */
  result?: Record<string, unknown>
}

/** Active tool call tracking entry. */
export interface ActiveToolCall {
  toolCallId: string
  name: string
  functionName: string
  startedAt: number
  streamingContent?: string
}

/** Buffered streaming content entry keyed by tool_call_id. */
export interface StreamingBufferEntry {
  content: string
  functionName: string
  contentType: string
}

export const useToolStore = defineStore('tool', () => {
  // ── State ────────────────────────────────────────────────────────
  const lastTool = ref<ToolContent | null>(null)
  const lastNoMessageTool = ref<ToolContent | null>(null)
  const toolTimeline = ref<ToolTimelineEntry[]>([])
  const panelToolId = ref<string | null>(null)
  const realTime = ref(true)
  const activeToolCalls = ref<Map<string, ActiveToolCall>>(new Map())

  /** Per-tool_call_id streaming content buffer (replaces string buffer). */
  const streamingContentBuffer = ref<Map<string, StreamingBufferEntry>>(new Map())

  /** Search sources cache keyed by tool_call_id. */
  const searchSourcesCache = shallowRef<Map<string, SourceCitation[]>>(new Map())

  // ── Computed ─────────────────────────────────────────────────────
  const timelineCount = computed(() => toolTimeline.value.length)
  const hasActiveTool = computed(() => activeToolCalls.value.size > 0)
  const selectedTool = computed(() => {
    if (!panelToolId.value) return null
    return (
      toolTimeline.value.find((t) => t.toolCallId === panelToolId.value) ?? null
    )
  })

  // ── Actions ──────────────────────────────────────────────────────

  function recordToolCall(tool: ToolContent) {
    lastTool.value = tool
    // Track last non-message tool for panel display
    if (tool.name !== 'message') {
      lastNoMessageTool.value = tool
    }

    const entry: ToolTimelineEntry = {
      toolCallId: tool.tool_call_id,
      name: tool.name,
      functionName: tool.function,
      args: tool.args,
      status: tool.status,
      startedAt: tool.timestamp ?? Date.now(),
      displayCommand: tool.display_command,
      commandCategory: tool.command_category,
    }

    // Upsert: update existing entry or append new
    const idx = toolTimeline.value.findIndex(
      (t) => t.toolCallId === tool.tool_call_id,
    )
    if (idx !== -1) {
      toolTimeline.value[idx] = {
        ...toolTimeline.value[idx],
        ...entry,
      }
    } else {
      toolTimeline.value.push(entry)
    }

    // Track active calls
    if (tool.status === 'calling' || tool.status === 'running') {
      activeToolCalls.value.set(tool.tool_call_id, {
        toolCallId: tool.tool_call_id,
        name: tool.name,
        functionName: tool.function,
        startedAt: tool.timestamp ?? Date.now(),
      })
    } else if (tool.status === 'called' || tool.status === 'interrupted') {
      activeToolCalls.value.delete(tool.tool_call_id)
    }
  }

  function updateToolResult(toolId: string, result: Record<string, unknown>) {
    const idx = toolTimeline.value.findIndex((t) => t.toolCallId === toolId)
    if (idx !== -1) {
      toolTimeline.value[idx] = {
        ...toolTimeline.value[idx],
        status: 'called',
        completedAt: Date.now(),
        result,
      }
    }
    // Remove from active calls
    activeToolCalls.value.delete(toolId)
  }

  function selectTool(toolId: string | null) {
    panelToolId.value = toolId
  }

  // ── Streaming content buffer (per-tool_call_id) ─────────────────

  function setStreamingContent(
    toolCallId: string,
    content: string,
    functionName: string,
    contentType: string,
  ) {
    const newMap = new Map(streamingContentBuffer.value)
    newMap.set(toolCallId, { content, functionName, contentType })
    streamingContentBuffer.value = newMap
  }

  function getStreamingContent(toolCallId: string): StreamingBufferEntry | undefined {
    return streamingContentBuffer.value.get(toolCallId)
  }

  function deleteStreamingContent(toolCallId: string) {
    const newMap = new Map(streamingContentBuffer.value)
    newMap.delete(toolCallId)
    streamingContentBuffer.value = newMap
  }

  // ── Search sources cache ────────────────────────────────────────

  function cacheSearchSources(toolCallId: string, sources: SourceCitation[]) {
    const newMap = new Map(searchSourcesCache.value)
    newMap.set(toolCallId, sources)
    searchSourcesCache.value = newMap
  }

  function getSearchSources(toolCallId: string): SourceCitation[] | undefined {
    return searchSourcesCache.value.get(toolCallId)
  }

  // ── Real-time toggle ────────────────────────────────────────────

  function setRealTime(value: boolean) {
    realTime.value = value
  }

  // ── Full reset ──────────────────────────────────────────────────

  function clearAll() {
    toolTimeline.value = []
    lastTool.value = null
    lastNoMessageTool.value = null
    activeToolCalls.value.clear()
    panelToolId.value = null
    streamingContentBuffer.value = new Map()
    searchSourcesCache.value = new Map()
    realTime.value = true
  }

  return {
    // State
    lastTool,
    lastNoMessageTool,
    toolTimeline,
    panelToolId,
    realTime,
    streamingContentBuffer,
    searchSourcesCache,
    activeToolCalls,
    // Computed
    timelineCount,
    hasActiveTool,
    selectedTool,
    // Actions
    recordToolCall,
    updateToolResult,
    selectTool,
    setStreamingContent,
    getStreamingContent,
    deleteStreamingContent,
    cacheSearchSources,
    getSearchSources,
    setRealTime,
    clearAll,
  }
})
