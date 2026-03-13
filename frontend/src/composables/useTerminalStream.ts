import { ref, onUnmounted } from 'vue'

export interface TerminalStreamOptions {
  sessionId: string
  shellSessionId: string
}

type DataListener = (data: string) => void

/**
 * Composable that consumes ToolStreamEvent SSE events with content_type="terminal"
 * and provides a writable stream of text chunks for xterm.js.
 */
export function useTerminalStream(options: TerminalStreamOptions) {
  const buffer = ref<string[]>([])
  const isComplete = ref(false)
  const exitCode = ref<number | null>(null)

  // Keep options accessible for consumers
  const _sessionId = options.sessionId
  const _shellSessionId = options.shellSessionId

  const listeners: DataListener[] = []

  function onData(listener: DataListener) {
    listeners.push(listener)
  }

  function pushChunk(text: string) {
    buffer.value.push(text)
    for (const listener of listeners) {
      listener(text)
    }
  }

  function markComplete(code: number) {
    isComplete.value = true
    exitCode.value = code
  }

  function reset() {
    buffer.value = []
    isComplete.value = false
    exitCode.value = null
  }

  onUnmounted(() => {
    listeners.length = 0
  })

  return {
    sessionId: _sessionId,
    shellSessionId: _shellSessionId,
    buffer,
    isComplete,
    exitCode,
    onData,
    pushChunk,
    markComplete,
    reset,
  }
}
