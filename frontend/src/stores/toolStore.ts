/**
 * Tool store — manages tool execution state globally via Pinia.
 *
 * Tracks the tool call timeline, active tool executions, streaming output
 * buffers, and panel selection state. Composables become thin facades.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ToolContent } from '../types/message'

// ── Interfaces ──────────────────────────────────────────────────────

/** A recorded tool call in the timeline with optional result metadata. */
export interface ToolTimelineEntry {
  toolCallId: string
  name: string
  functionName: string
  args: Record<string, unknown>
  status: 'calling' | 'called'
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

export const useToolStore = defineStore('tool', () => {
  // ── State ────────────────────────────────────────────────────────
  const lastTool = ref<ToolContent | null>(null)
  const toolTimeline = ref<ToolTimelineEntry[]>([])
  const panelToolId = ref<string | null>(null)
  const streamingContentBuffer = ref<string>('')
  const activeToolCalls = ref<Map<string, ActiveToolCall>>(new Map())

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
    if (tool.status === 'calling') {
      activeToolCalls.value.set(tool.tool_call_id, {
        toolCallId: tool.tool_call_id,
        name: tool.name,
        functionName: tool.function,
        startedAt: tool.timestamp ?? Date.now(),
      })
    } else if (tool.status === 'called') {
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

  function clearTimeline() {
    toolTimeline.value = []
    lastTool.value = null
    activeToolCalls.value.clear()
    panelToolId.value = null
    streamingContentBuffer.value = ''
  }

  function appendStreamContent(content: string) {
    streamingContentBuffer.value += content
  }

  function clearStreamBuffer() {
    streamingContentBuffer.value = ''
  }

  return {
    // State
    lastTool,
    toolTimeline,
    panelToolId,
    streamingContentBuffer,
    activeToolCalls,
    // Computed
    timelineCount,
    hasActiveTool,
    selectedTool,
    // Actions
    recordToolCall,
    updateToolResult,
    selectTool,
    clearTimeline,
    appendStreamContent,
    clearStreamBuffer,
  }
})
