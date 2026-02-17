# Unified Streaming Architecture

**Status:** 🚧 In Development
**Created:** 2026-02-16
**Owner:** Core Team

## Executive Summary

This document defines a comprehensive streaming architecture that provides real-time progressive output display for **all** agent operations in Pythinker. The system extends the proven `StreamingReportView` pattern to support terminal output, file operations, search results, and generic content streaming.

---

## 1. Goals & Requirements

### Primary Goals

1. **Unified Experience**: All tool operations show progressive output with consistent UX
2. **Real-Time Feedback**: <100ms latency from backend event to frontend update
3. **Type Safety**: Full TypeScript types for all streaming content
4. **Backward Compatible**: Fallback to static display for legacy tools
5. **Performance**: Handle high-throughput streams (>10MB terminal output)

### Success Metrics

- ✅ Zero polling API calls (replace terminal polling with streaming)
- ✅ <100ms perceived latency for streaming updates
- ✅ 100% of tool operations support streaming preview
- ✅ Zero XSS vulnerabilities (all content sanitized)

---

## 2. Architecture Overview

### 2.1 Three-Layer Streaming Model

```
┌──────────────────────────────────────────────────────────────────┐
│ Layer 1: Backend Event Generation                                │
├──────────────────────────────────────────────────────────────────┤
│ • Tool execution emits ToolStreamEvent during operation          │
│ • Chunked output (1KB buffers or line-based)                     │
│ • Content-type classification (terminal, code, json, markdown)   │
└──────────────────────────────────────────────────────────────────┘
                            ↓ SSE Stream
┌──────────────────────────────────────────────────────────────────┐
│ Layer 2: Frontend State Management                               │
├──────────────────────────────────────────────────────────────────┤
│ • useAgentEvents composable receives events                      │
│ • ChatPage updates ToolContent.streaming_content reactively      │
│ • Content accumulation with frame batching (60ms)                │
└──────────────────────────────────────────────────────────────────┘
                            ↓ Props Flow
┌──────────────────────────────────────────────────────────────────┐
│ Layer 3: Content Rendering                                       │
├──────────────────────────────────────────────────────────────────┤
│ • UnifiedStreamingView component (new)                           │
│ • Type-specific formatters (terminal, code, markdown, json)      │
│ • Auto-scroll, syntax highlighting, typing cursor                │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Streaming Priority Hierarchy

When multiple content sources exist for a tool, display in this order:

1. **streaming_content** (highest priority - live streaming)
2. **args.content** (medium priority - LLM-generated preview)
3. **tool_content** (lowest priority - final executed result)

Example:
```typescript
const displayContent = computed(() => {
  return props.toolContent?.streaming_content      // ⭐ Live stream
      || props.toolContent?.args?.content          // Fallback 1
      || props.toolContent?.content?.output        // Fallback 2
      || '';
});
```

---

## 3. Content Type System

### 3.1 Supported Content Types

```typescript
export type StreamingContentType =
  | 'terminal'   // ANSI-colored terminal output
  | 'code'       // Syntax-highlighted code
  | 'markdown'   // Rendered markdown with sanitization
  | 'json'       // Formatted JSON with syntax highlighting
  | 'search'     // Progressive search results
  | 'text';      // Plain text with line breaks

export interface StreamingContentConfig {
  type: StreamingContentType;
  language?: string;           // For code: 'python', 'javascript', 'bash', etc.
  theme?: 'light' | 'dark';    // Syntax highlighting theme
  lineNumbers?: boolean;       // Show line numbers
  autoScroll?: boolean;        // Auto-scroll to bottom
  showCursor?: boolean;        // Show typing cursor while streaming
}
```

### 3.2 Content Type Detection

**Automatic Detection** (from function name):

```typescript
const detectContentType = (functionName: string): StreamingContentType => {
  const mapping: Record<string, StreamingContentType> = {
    // Terminal operations
    'shell_exec': 'terminal',
    'code_execute': 'terminal',
    'code_execute_python': 'terminal',
    'code_execute_javascript': 'terminal',

    // File operations
    'file_write': 'code',
    'file_str_replace': 'code',
    'file_read': 'code',

    // Search operations
    'info_search_web': 'search',
    'web_search': 'search',
    'wide_research': 'search',

    // Browser operations
    'browser_view': 'text',
    'browser_console_view': 'terminal',

    // Code artifacts
    'code_save_artifact': 'code',
    'code_read_artifact': 'code',
  };

  return mapping[functionName] || 'text';
};
```

---

## 4. Backend Implementation

### 4.1 Enhanced ToolStreamEvent

**File:** `backend/app/domain/models/event.py`

```python
class ToolStreamEvent(BaseEvent):
    """Streams partial tool content during operation."""
    type: Literal["tool_stream"] = "tool_stream"
    tool_call_id: str
    tool_name: str
    function_name: str

    # Streaming content
    partial_content: str          # Incremental chunk
    accumulated_content: str      # Full content so far (for late joiners)
    content_type: Literal[
        "terminal", "code", "markdown", "json", "search", "text"
    ]

    # Metadata
    is_final: bool = False
    chunk_index: int = 0          # Sequential chunk number
    total_bytes: int = 0          # Accumulated byte count
    language: str | None = None   # For code: 'python', 'javascript', etc.

    # Progress tracking
    progress_percent: int | None = None     # 0-100 for known-length operations
    elapsed_ms: float | None = None         # Execution time so far
```

### 4.2 Streaming Implementations by Tool Type

#### 4.2.1 Terminal/Shell Streaming

**File:** `backend/app/infrastructure/tools/shell_tool.py`

```python
async def _stream_command_output(
    self,
    process: asyncio.subprocess.Process,
    tool_call_id: str,
) -> AsyncGenerator[ToolStreamEvent, None]:
    """Stream stdout/stderr in real-time."""
    accumulated = ""
    chunk_index = 0
    start_time = time.time()

    async for line in process.stdout:
        chunk = line.decode('utf-8', errors='replace')
        accumulated += chunk

        yield ToolStreamEvent(
            tool_call_id=tool_call_id,
            tool_name="shell",
            function_name="shell_exec",
            partial_content=chunk,              # Just this line
            accumulated_content=accumulated,    # Full output so far
            content_type="terminal",
            is_final=False,
            chunk_index=chunk_index,
            total_bytes=len(accumulated.encode('utf-8')),
            elapsed_ms=(time.time() - start_time) * 1000,
        )
        chunk_index += 1

    # Final event when process completes
    yield ToolStreamEvent(
        tool_call_id=tool_call_id,
        tool_name="shell",
        function_name="shell_exec",
        partial_content="",
        accumulated_content=accumulated,
        content_type="terminal",
        is_final=True,
        chunk_index=chunk_index,
        total_bytes=len(accumulated.encode('utf-8')),
        elapsed_ms=(time.time() - start_time) * 1000,
    )
```

#### 4.2.2 Search Result Streaming

**File:** `backend/app/infrastructure/tools/search_tool.py`

```python
async def _stream_search_results(
    self,
    tool_call_id: str,
    query: str,
) -> AsyncGenerator[ToolStreamEvent, None]:
    """Stream search results progressively as they arrive."""
    results = []

    async for result in self._fetch_results_async(query):
        results.append(result)

        # Serialize partial results as JSON array
        partial_json = json.dumps(results, indent=2)

        yield ToolStreamEvent(
            tool_call_id=tool_call_id,
            tool_name="search",
            function_name="info_search_web",
            partial_content=partial_json,
            accumulated_content=partial_json,
            content_type="search",
            is_final=False,
            chunk_index=len(results),
            progress_percent=min(len(results) * 10, 100),  # Estimate
        )

    # Final event with complete results
    final_json = json.dumps(results, indent=2)
    yield ToolStreamEvent(
        tool_call_id=tool_call_id,
        tool_name="search",
        function_name="info_search_web",
        partial_content=final_json,
        accumulated_content=final_json,
        content_type="search",
        is_final=True,
        chunk_index=len(results),
        progress_percent=100,
    )
```

#### 4.2.3 File Write Streaming (Already Implemented)

**File:** `backend/app/domain/services/agents/tool_stream_parser.py`

```python
STREAMABLE_CONTENT_KEYS = {
    "file_write": "content",              # ✅ Already working
    "file_str_replace": "new_str",        # ✅ Already working
    "code_save_artifact": "content",      # ✅ Already working
    "code_execute_python": "code",        # ✅ Already working
    "code_execute_javascript": "code",    # ✅ Already working
    "code_execute": "code",               # ✅ Already working

    # New streaming functions
    "shell_exec": "command",              # ⭐ Add streaming
    "info_search_web": "query",           # ⭐ Add streaming
    "browser_view": "url",                # ⭐ Add streaming
}
```

---

## 5. Frontend Implementation

### 5.1 UnifiedStreamingView Component

**File:** `frontend/src/components/toolViews/UnifiedStreamingView.vue`

```vue
<template>
  <div class="unified-streaming-view">
    <!-- Status Header -->
    <div class="streaming-header">
      <div class="streaming-indicator">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
      <span class="streaming-label">
        {{ isFinal ? statusComplete : statusStreaming }}
      </span>
      <span v-if="progressPercent !== null" class="progress-badge">
        {{ progressPercent }}%
      </span>
    </div>

    <!-- Content Area (type-specific rendering) -->
    <div ref="contentRef" class="streaming-content">
      <!-- Terminal: xterm.js with ANSI colors -->
      <TerminalRenderer
        v-if="contentType === 'terminal'"
        :content="text"
        :auto-scroll="autoScroll"
      />

      <!-- Code: Monaco editor or syntax-highlighted -->
      <CodeRenderer
        v-else-if="contentType === 'code'"
        :content="text"
        :language="language"
        :line-numbers="lineNumbers"
        :auto-scroll="autoScroll"
      />

      <!-- Markdown: Rendered with marked + sanitized -->
      <div
        v-else-if="contentType === 'markdown'"
        class="markdown-body"
        v-html="renderedMarkdown"
      />

      <!-- JSON: Syntax-highlighted with Shiki -->
      <JsonRenderer
        v-else-if="contentType === 'json'"
        :content="text"
        :collapsed="false"
      />

      <!-- Search: Progressive result cards -->
      <SearchResultStream
        v-else-if="contentType === 'search'"
        :results="parsedSearchResults"
        :is-final="isFinal"
      />

      <!-- Plain Text: Formatted with line breaks -->
      <pre v-else class="text-content">{{ text }}</pre>

      <!-- Typing Cursor (while streaming) -->
      <span v-if="!isFinal && showCursor" class="typing-cursor">|</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import type { StreamingContentType } from '@/types/streaming';

interface Props {
  text: string;
  contentType: StreamingContentType;
  isFinal: boolean;
  language?: string;
  lineNumbers?: boolean;
  autoScroll?: boolean;
  showCursor?: boolean;
  progressPercent?: number | null;
}

const props = withDefaults(defineProps<Props>(), {
  contentType: 'text',
  isFinal: false,
  language: 'text',
  lineNumbers: true,
  autoScroll: true,
  showCursor: true,
  progressPercent: null,
});

const contentRef = ref<HTMLElement | null>(null);

// Status labels
const statusStreaming = computed(() => {
  const labels: Record<StreamingContentType, string> = {
    terminal: 'Executing command...',
    code: 'Writing code...',
    markdown: 'Composing document...',
    json: 'Generating data...',
    search: 'Searching...',
    text: 'Processing...',
  };
  return labels[props.contentType];
});

const statusComplete = computed(() => {
  const labels: Record<StreamingContentType, string> = {
    terminal: 'Command complete',
    code: 'Code complete',
    markdown: 'Document complete',
    json: 'Data complete',
    search: 'Search complete',
    text: 'Complete',
  };
  return labels[props.contentType];
});

// Markdown rendering with sanitization
const renderedMarkdown = computed(() => {
  if (props.contentType !== 'markdown') return '';
  if (!props.text) return '';
  const raw = marked.parse(props.text, { async: false }) as string;
  return DOMPurify.sanitize(raw);
});

// Parse search results from JSON
const parsedSearchResults = computed(() => {
  if (props.contentType !== 'search') return [];
  try {
    return JSON.parse(props.text);
  } catch {
    return [];
  }
});

// Auto-scroll to bottom as content streams in
watch(() => props.text, async () => {
  if (!props.autoScroll) return;

  await nextTick();
  if (contentRef.value) {
    contentRef.value.scrollTop = contentRef.value.scrollHeight;
  }
}, { flush: 'post' });
</script>

<style scoped>
/* Reuse styles from StreamingReportView.vue */
.unified-streaming-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--background-white-main);
  overflow: hidden;
}

.streaming-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-light);
  background: var(--bolt-elements-bg-depth-2);
  flex-shrink: 0;
}

.streaming-indicator {
  display: flex;
  gap: 3px;
  align-items: center;
}

.typing-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--bolt-elements-item-contentAccent);
  animation: typing-bounce 1.4s infinite ease-in-out both;
}

.typing-dot:nth-child(1) { animation-delay: -0.32s; }
.typing-dot:nth-child(2) { animation-delay: -0.16s; }
.typing-dot:nth-child(3) { animation-delay: 0s; }

@keyframes typing-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

.streaming-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.progress-badge {
  margin-left: auto;
  padding: 2px 8px;
  border-radius: 12px;
  background: var(--bolt-elements-item-contentAccent);
  color: white;
  font-size: 11px;
  font-weight: 600;
}

.streaming-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  scroll-behavior: smooth;
}

.typing-cursor {
  display: inline;
  font-weight: 200;
  color: var(--bolt-elements-item-contentAccent);
  animation: blink 0.8s step-end infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
```

### 5.2 Integration into ToolPanelContent

**File:** `frontend/src/components/ToolPanelContent.vue`

```typescript
// Add streaming view with highest priority (before replay, before live preview)
const shouldShowStreamingView = computed(() => {
  return !!props.toolContent?.streaming_content && props.live;
});

const streamingContentType = computed((): StreamingContentType => {
  if (!props.toolContent) return 'text';
  return detectContentType(props.toolContent.function);
});
```

**Template Update:**

```vue
<!-- Content Area: Dynamic content rendering -->
<div class="flex-1 min-h-0 min-w-0 w-full overflow-hidden relative">
  <!-- Unified Streaming View (NEW - highest priority) -->
  <UnifiedStreamingView
    v-if="shouldShowStreamingView"
    :text="toolContent.streaming_content || ''"
    :content-type="streamingContentType"
    :is-final="toolContent.status === 'called'"
    :language="getLanguageFromContent()"
    :progress-percent="toolContent.progress_percent"
  />

  <!-- Streaming Report (summary phase) -->
  <StreamingReportView
    v-else-if="isSummaryPhase || summaryStreamText"
    :text="summaryStreamText || ''"
    :is-final="!isSummaryStreaming"
  />

  <!-- Replay mode: static screenshots -->
  <div v-else-if="isReplayMode && !!replayScreenshotUrl">
    <ScreenshotReplayViewer ... />
  </div>

  <!-- Existing views (fallback when no streaming) -->
  <div v-else-if="currentViewType === 'live_preview'">
    <LiveViewer ... />
  </div>
  <!-- ... other views ... -->
</div>
```

---

## 6. Type System Updates

### 6.1 Frontend Types

**File:** `frontend/src/types/streaming.ts` (NEW)

```typescript
/**
 * Streaming content types for unified streaming system
 */
export type StreamingContentType =
  | 'terminal'   // ANSI-colored terminal output
  | 'code'       // Syntax-highlighted code
  | 'markdown'   // Rendered markdown
  | 'json'       // Formatted JSON
  | 'search'     // Progressive search results
  | 'text';      // Plain text

/**
 * Configuration for streaming content rendering
 */
export interface StreamingContentConfig {
  type: StreamingContentType;
  language?: string;
  theme?: 'light' | 'dark';
  lineNumbers?: boolean;
  autoScroll?: boolean;
  showCursor?: boolean;
}

/**
 * Streaming event metadata from backend
 */
export interface StreamingMetadata {
  chunkIndex: number;
  totalBytes: number;
  progressPercent?: number;
  elapsedMs?: number;
  isComplete: boolean;
}
```

**File:** `frontend/src/types/event.ts` (UPDATE)

```typescript
export interface ToolStreamEventData extends BaseEventData {
  tool_call_id: string;
  tool_name: string;
  function_name: string;

  // Enhanced streaming content
  partial_content: string;           // Incremental chunk
  accumulated_content: string;       // Full content (NEW)
  content_type: StreamingContentType;

  // Metadata
  is_final: boolean;
  chunk_index?: number;              // NEW
  total_bytes?: number;              // NEW
  language?: string;                 // NEW
  progress_percent?: number;         // NEW
  elapsed_ms?: number;               // NEW
}
```

---

## 7. Migration Path

### 7.1 Phase 1: Create UnifiedStreamingView (Week 1)

**Tasks:**
- [ ] Create `UnifiedStreamingView.vue` component
- [ ] Create sub-renderers: `TerminalRenderer`, `CodeRenderer`, `JsonRenderer`, `SearchResultStream`
- [ ] Add comprehensive unit tests
- [ ] Verify backward compatibility with existing `StreamingReportView`

**Success Criteria:**
- Component renders all 6 content types correctly
- Auto-scroll works for all types
- XSS tests pass (sanitization working)
- No visual regressions on existing streaming (report summary)

### 7.2 Phase 2: Backend Streaming for Terminal (Week 2)

**Tasks:**
- [ ] Update `ShellTool` to emit `ToolStreamEvent` during command execution
- [ ] Add line-buffered streaming (emit every line)
- [ ] Handle ANSI escape codes properly
- [ ] Add integration tests for shell streaming
- [ ] Update `tool_stream_parser.py` to include `shell_exec`

**Success Criteria:**
- Terminal output streams in real-time (<100ms latency)
- ANSI colors render correctly
- Large outputs (>10MB) don't cause memory issues
- Polling API removed from frontend

### 7.3 Phase 3: Integrate into ToolPanelContent (Week 2)

**Tasks:**
- [ ] Add `shouldShowStreamingView` computed property
- [ ] Add content type detection logic
- [ ] Update template to show `UnifiedStreamingView` with highest priority
- [ ] Remove terminal polling logic
- [ ] Add fallback logic for non-streaming tools

**Success Criteria:**
- All tools show streaming when available
- Graceful fallback to static views
- No breaking changes to existing tools
- Performance: 60fps rendering during streaming

### 7.4 Phase 4: Search Result Streaming (Week 3)

**Tasks:**
- [ ] Update `SearchTool` to emit progressive results
- [ ] Create `SearchResultStream` sub-component
- [ ] Add result animations (staggered entrance)
- [ ] Update search view integration tests

**Success Criteria:**
- Search results appear progressively (each result animates in)
- Count indicator shows "3 of 10 results" while streaming
- Final result count matches expected
- No duplicate results

### 7.5 Phase 5: Polish & Documentation (Week 3)

**Tasks:**
- [ ] Add loading skeletons for slow streams
- [ ] Add error recovery (connection drop, invalid content)
- [ ] Write comprehensive docs: `STREAMING_ARCHITECTURE.md`
- [ ] Update CLAUDE.md with streaming best practices
- [ ] Create demo video showing streaming UX

**Success Criteria:**
- Documentation complete and reviewed
- All tests passing (>90% coverage)
- Zero known bugs
- Ready for production deployment

---

## 8. Performance Considerations

### 8.1 Frame Batching

**Problem**: High-frequency events (>60fps) cause excessive re-renders

**Solution**: Batch updates with requestAnimationFrame

```typescript
// In ChatPage.vue
let pendingStreamUpdate: string | null = null;
let rafId: number | null = null;

const flushStreamUpdate = () => {
  if (pendingStreamUpdate) {
    toolContent.streaming_content = pendingStreamUpdate;
    pendingStreamUpdate = null;
  }
  rafId = null;
};

const handleToolStream = (event: ToolStreamEventData) => {
  pendingStreamUpdate = event.accumulated_content;

  if (rafId === null) {
    rafId = requestAnimationFrame(flushStreamUpdate);
  }
};
```

### 8.2 Memory Management

**Problem**: Large streaming outputs (>100MB) cause memory pressure

**Solution**: Implement circular buffer with configurable max size

```typescript
const MAX_STREAMING_SIZE = 10 * 1024 * 1024; // 10MB

const updateStreamingContent = (newContent: string) => {
  if (newContent.length > MAX_STREAMING_SIZE) {
    // Keep last 10MB only (rolling window)
    toolContent.streaming_content = newContent.slice(-MAX_STREAMING_SIZE);
    console.warn('Streaming content truncated to prevent memory issues');
  } else {
    toolContent.streaming_content = newContent;
  }
};
```

### 8.3 Virtual Scrolling

**Problem**: Rendering 100k+ lines causes lag

**Solution**: Use virtual scrolling for terminal content

```vue
<template>
  <!-- Use vue-virtual-scroller for large terminal output -->
  <DynamicScroller
    v-if="lines.length > 1000"
    :items="lines"
    :min-item-size="20"
    class="terminal-scroller"
  >
    <template #default="{ item, index, active }">
      <DynamicScrollerItem
        :item="item"
        :active="active"
        :data-index="index"
      >
        <div class="terminal-line" v-html="renderAnsi(item)"></div>
      </DynamicScrollerItem>
    </template>
  </DynamicScroller>

  <!-- Regular rendering for smaller outputs -->
  <div v-else class="terminal-output">
    <div
      v-for="(line, idx) in lines"
      :key="idx"
      class="terminal-line"
      v-html="renderAnsi(line)"
    />
  </div>
</template>
```

---

## 9. Security Considerations

### 9.1 XSS Prevention

All streamed content must be sanitized before rendering:

```typescript
// For markdown content
const renderedHtml = computed(() => {
  const raw = marked.parse(props.text, { async: false }) as string;
  return DOMPurify.sanitize(raw, {
    ALLOWED_TAGS: [
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'p', 'br', 'ul', 'ol', 'li',
      'strong', 'em', 'code', 'pre',
      'a', 'blockquote', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
    ],
    ALLOWED_ATTR: ['href', 'title', 'target', 'rel']
  });
});

// For terminal content (ANSI codes only)
const renderAnsi = (text: string) => {
  return ansiToHtml(text, {
    escapeXML: true,  // ✅ Escape HTML entities
    colors: ANSI_COLOR_PALETTE
  });
};
```

### 9.2 Content Size Limits

Prevent DoS via unbounded streaming:

```typescript
// In SSE handler
const MAX_STREAM_SIZE = 100 * 1024 * 1024; // 100MB per tool call

if (accumulatedSize > MAX_STREAM_SIZE) {
  console.error(`Stream exceeded ${MAX_STREAM_SIZE} bytes, terminating`);
  eventSource.close();
  showError('Output too large to display');
}
```

---

## 10. Testing Strategy

### 10.1 Unit Tests

**File:** `frontend/src/components/toolViews/__tests__/UnifiedStreamingView.spec.ts`

```typescript
import { mount } from '@vue/test-utils';
import { describe, it, expect, vi } from 'vitest';
import UnifiedStreamingView from '../UnifiedStreamingView.vue';

describe('UnifiedStreamingView', () => {
  it('renders terminal content with ANSI colors', async () => {
    const wrapper = mount(UnifiedStreamingView, {
      props: {
        text: '\x1b[31mError\x1b[0m',
        contentType: 'terminal',
        isFinal: false,
      },
    });

    expect(wrapper.find('.terminal-output').exists()).toBe(true);
    expect(wrapper.html()).toContain('Error');
  });

  it('auto-scrolls to bottom when new content arrives', async () => {
    const wrapper = mount(UnifiedStreamingView, {
      props: {
        text: 'Line 1',
        contentType: 'text',
        isFinal: false,
        autoScroll: true,
      },
    });

    const contentEl = wrapper.find('.streaming-content').element as HTMLElement;
    const scrollSpy = vi.spyOn(contentEl, 'scrollTop', 'set');

    await wrapper.setProps({ text: 'Line 1\nLine 2\nLine 3' });
    await wrapper.vm.$nextTick();

    expect(scrollSpy).toHaveBeenCalled();
  });

  it('shows typing cursor while streaming', () => {
    const wrapper = mount(UnifiedStreamingView, {
      props: {
        text: 'Streaming...',
        contentType: 'text',
        isFinal: false,
        showCursor: true,
      },
    });

    expect(wrapper.find('.typing-cursor').exists()).toBe(true);
  });

  it('hides typing cursor when streaming complete', () => {
    const wrapper = mount(UnifiedStreamingView, {
      props: {
        text: 'Complete',
        contentType: 'text',
        isFinal: true,
        showCursor: true,
      },
    });

    expect(wrapper.find('.typing-cursor').exists()).toBe(false);
  });
});
```

### 10.2 Integration Tests

**File:** `backend/tests/integration/test_streaming_shell.py`

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_shell_streaming_realtime(client: AsyncClient, session_id: str):
    """Test that shell output streams in real-time during command execution."""

    # Start SSE connection
    async with client.stream(
        "GET",
        f"/api/v1/chat/{session_id}/events",
        headers={"Accept": "text/event-stream"},
    ) as response:
        # Send shell command that takes 5 seconds
        await client.post(
            f"/api/v1/chat/{session_id}/send",
            json={
                "message": "run this command: for i in {1..5}; do echo $i; sleep 1; done"
            },
        )

        # Collect streaming events
        events = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                event = json.loads(line[6:])
                if event["type"] == "tool_stream":
                    events.append(event)
                if event.get("is_final"):
                    break

        # Assertions
        assert len(events) >= 5, "Should receive at least 5 stream events"
        assert events[-1]["is_final"] is True
        assert "5" in events[-1]["accumulated_content"]

        # Check that events arrived progressively (not all at once)
        timestamps = [e["timestamp"] for e in events]
        assert timestamps[-1] - timestamps[0] >= 5000, "Should take ~5 seconds"
```

---

## 11. Monitoring & Observability

### 11.1 Metrics

Add Prometheus metrics for streaming health:

```python
# backend/app/infrastructure/metrics/streaming_metrics.py

from prometheus_client import Counter, Histogram

streaming_events_total = Counter(
    "pythinker_streaming_events_total",
    "Total streaming events emitted",
    labelnames=["tool_name", "content_type"]
)

streaming_bytes_total = Counter(
    "pythinker_streaming_bytes_total",
    "Total bytes streamed",
    labelnames=["tool_name", "content_type"]
)

streaming_latency_seconds = Histogram(
    "pythinker_streaming_latency_seconds",
    "Latency from backend event to frontend receipt",
    labelnames=["tool_name"]
)
```

### 11.2 Logging

Structured logging for streaming diagnostics:

```typescript
// frontend/src/utils/streamingLogger.ts

export const logStreamEvent = (event: ToolStreamEventData) => {
  console.debug('[STREAM]', {
    toolCallId: event.tool_call_id,
    contentType: event.content_type,
    chunkIndex: event.chunk_index,
    totalBytes: event.total_bytes,
    isFinal: event.is_final,
    latency: Date.now() - event.timestamp,
  });
};
```

---

## 12. Future Enhancements

### 12.1 Binary Content Streaming

Support for image/video/audio streaming:

```typescript
export type StreamingContentType =
  | 'terminal'
  | 'code'
  | 'markdown'
  | 'json'
  | 'search'
  | 'text'
  | 'image'      // ⭐ Future
  | 'video'      // ⭐ Future
  | 'audio';     // ⭐ Future
```

### 12.2 Collaborative Streaming

Multiple users see same streaming output in real-time:

```typescript
// Share streaming session ID via WebRTC
const shareStreamingSession = (sessionId: string) => {
  const shareUrl = `${window.location.origin}/stream/${sessionId}`;
  navigator.clipboard.writeText(shareUrl);
};
```

### 12.3 Stream Recording & Replay

Save streaming sessions for later playback:

```typescript
// Record all streaming events
const streamRecorder = useStreamRecorder();
streamRecorder.start(sessionId);

// Replay at 2x speed
streamRecorder.replay(sessionId, { speed: 2.0 });
```

---

## 13. References

- [StreamingReportView Implementation](../../frontend/src/components/toolViews/StreamingReportView.vue)
- [SSE Connection Management](../../frontend/src/composables/useSSEConnection.ts)
- [Tool Stream Parser](../../backend/app/domain/services/agents/tool_stream_parser.py)
- [Event Types](../../frontend/src/types/event.ts)
- [MDN: Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [Vue Best Practices: Watchers](https://vuejs.org/guide/essentials/watchers.html)

---

## Appendix A: Complete File Checklist

### New Files (6)

- [ ] `docs/architecture/UNIFIED_STREAMING_ARCHITECTURE.md` (this document)
- [ ] `frontend/src/components/toolViews/UnifiedStreamingView.vue`
- [ ] `frontend/src/components/toolViews/renderers/TerminalRenderer.vue`
- [ ] `frontend/src/components/toolViews/renderers/CodeRenderer.vue`
- [ ] `frontend/src/components/toolViews/renderers/JsonRenderer.vue`
- [ ] `frontend/src/components/toolViews/renderers/SearchResultStream.vue`
- [ ] `frontend/src/types/streaming.ts`
- [ ] `frontend/src/components/toolViews/__tests__/UnifiedStreamingView.spec.ts`
- [ ] `backend/tests/integration/test_streaming_shell.py`
- [ ] `backend/tests/integration/test_streaming_search.py`

### Modified Files (8)

- [ ] `backend/app/domain/models/event.py` (enhance ToolStreamEvent)
- [ ] `backend/app/infrastructure/tools/shell_tool.py` (add streaming)
- [ ] `backend/app/infrastructure/tools/search_tool.py` (add streaming)
- [ ] `backend/app/domain/services/agents/tool_stream_parser.py` (extend streamable functions)
- [ ] `frontend/src/components/ToolPanelContent.vue` (integrate UnifiedStreamingView)
- [ ] `frontend/src/types/event.ts` (enhance ToolStreamEventData)
- [ ] `frontend/src/pages/ChatPage.vue` (update event handlers)
- [ ] `CLAUDE.md` (add streaming best practices)

---

**Document Version:** 1.0.0
**Last Updated:** 2026-02-16
**Status:** 🚧 Design Phase Complete, Implementation Pending
