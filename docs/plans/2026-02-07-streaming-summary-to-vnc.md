# Streaming Summary to VNC Panel — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When the agent writes a summary/report (SUMMARIZING phase), stream LLM tokens live into the tool panel (VNC area) so users watch the report being composed in real-time.

**Architecture:** Backend `summarize()` switches from non-streaming `ask_structured()`/`ask()` to streaming `ask_stream()`, yielding `StreamEvent(phase="summarizing")` chunks. Frontend adds a `StreamingReportView` component to ToolPanelContent that renders accumulating markdown with auto-scroll and typing cursor. After streaming completes, CoVe/Critic still run on the complete text, and the final `ReportEvent` appears in chat.

**Tech Stack:** Python async generators, SSE events, Vue 3 Composition API, marked (markdown)

---

## Task 1: Add `phase` field to StreamEvent (backend model)

**Files:**
- Modify: `backend/app/domain/models/event.py:538-543`

**Step 1: Add phase field to StreamEvent**

```python
class StreamEvent(BaseEvent):
    """Stream event for real-time LLM response streaming"""

    type: Literal["stream"] = "stream"
    content: str  # Streamed content chunk
    is_final: bool = False  # Whether this is the final chunk
    phase: str = "thinking"  # "thinking" for planning, "summarizing" for report generation
```

**Step 2: Verify**

Run: `cd backend && ruff check app/domain/models/event.py`
Expected: All checks passed

**Step 3: Commit**

```bash
git add backend/app/domain/models/event.py
git commit -m "feat: add phase field to StreamEvent for thinking vs summarizing"
```

---

## Task 2: Add `phase` to frontend StreamEventData

**Files:**
- Modify: `frontend/src/types/event.ts:87-90`

**Step 1: Add phase field**

```typescript
export interface StreamEventData extends BaseEventData {
  content: string;
  is_final: boolean;
  phase?: 'thinking' | 'summarizing';  // defaults to 'thinking' for backward compat
}
```

**Step 2: Verify**

Run: `cd frontend && bun run type-check`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/types/event.ts
git commit -m "feat: add phase to StreamEventData type"
```

---

## Task 3: Create streaming summarize prompt

**Files:**
- Modify: `backend/app/domain/services/prompts/execution.py` (add after line 1179)

**Step 1: Add STREAMING_SUMMARIZE_PROMPT**

Add a new prompt constant after the existing `SUMMARIZE_PROMPT = ENHANCED_SUMMARIZE_PROMPT` line:

```python
STREAMING_SUMMARIZE_PROMPT = """Deliver the completed result as a professional research report in Markdown.

REPORT STRUCTURE (follow this format exactly):

# [Clear, Descriptive Title]

## Introduction
Brief context and scope of the research (2-3 sentences).

## [Main Section 1]
### [Subsection if needed]
Content with **bold** for key terms. Use tables for comparisons:

| Category | Details | Notes |
|----------|---------|-------|
| Item 1   | Value   | Info  |

## [Main Section 2]
Continue with clear, factual content.

## Conclusion
Key takeaways and recommendations.

## References
[1] Source Name - URL

WRITING GUIDELINES:
- Be CONCISE - no filler text, disclaimers, or meta-commentary
- NO revision notes, change logs, or "this report has been updated" sections
- NO "Important Disclaimer" or similar notices
- Focus on FACTS and FINDINGS only
- Use **bold** for key terms, not for entire headings
- Use tables for structured comparisons
- Use bullet points for lists of items
- Include numbered references at the end
- Write in professional, direct tone

FORBIDDEN:
- "This report has been revised..."
- "Changes Made:" sections
- "IMPORTANT DISCLAIMER:"
- Meta-commentary about the report itself
- Work-in-progress language
- Excessive caveats or hedging

IMPORTANT: Write ONLY the Markdown report. No JSON wrapping, no prose before or after. Start directly with the # title heading.
"""
```

**Step 2: Export it**

Ensure the import in execution.py can access it (same file, just a new constant).

**Step 3: Verify**

Run: `cd backend && ruff check app/domain/services/prompts/execution.py`

**Step 4: Commit**

```bash
git add backend/app/domain/services/prompts/execution.py
git commit -m "feat: add STREAMING_SUMMARIZE_PROMPT for plain markdown output"
```

---

## Task 4: Modify `summarize()` to stream LLM tokens

**Files:**
- Modify: `backend/app/domain/services/agents/execution.py:395-539`

This is the core backend change. Replace the non-streaming LLM calls with `ask_stream()`, yielding `StreamEvent` chunks during generation.

**Step 1: Add import for STREAMING_SUMMARIZE_PROMPT**

At the top imports, add:
```python
from app.domain.services.prompts.execution import EXECUTION_SYSTEM_PROMPT, SUMMARIZE_PROMPT, STREAMING_SUMMARIZE_PROMPT, build_execution_prompt
```

**Step 2: Rewrite the `summarize()` method**

Replace the method body with this flow:

```python
async def summarize(self) -> AsyncGenerator[BaseEvent, None]:
    """Summarize the completed task, streaming tokens for live display."""
    yield StepEvent(
        status=StepStatus.RUNNING,
        step=Step(id="summarize", description="Composing final report...", status=ExecutionStatus.RUNNING),
    )

    # Use streaming prompt (plain markdown, no JSON wrapper)
    await self._add_to_memory([{"role": "user", "content": STREAMING_SUMMARIZE_PROMPT}])
    await self._ensure_within_token_limit()

    try:
        accumulated_text = ""

        # Phase 1: Stream tokens live via StreamEvent
        async for chunk in self.llm.ask_stream(
            self.memory.get_messages(), tools=None, tool_choice=None
        ):
            accumulated_text += chunk
            yield StreamEvent(content=chunk, is_final=False, phase="summarizing")

        # Signal streaming complete
        yield StreamEvent(content="", is_final=True, phase="summarizing")

        message_content = accumulated_text.strip()

        # Extract title from first # heading
        message_title = self._extract_title(message_content)

        # Phase 2: Post-processing (CoVe + Critic on complete text)
        if len(message_content) > 300 and self._user_request:
            message_content, cove_result = await self._apply_cove_verification(
                message_content, self._user_request
            )
            if cove_result and cove_result.has_contradictions:
                logger.info(
                    f"CoVe refined output: {cove_result.claims_contradicted} claims corrected, "
                    f"new confidence: {cove_result.confidence_score:.2f}"
                )

        if len(message_content) > 200 and self._user_request:
            message_content = await self._apply_critic_revision(message_content, [])

        # Reward hacking detection (log-only, unchanged)
        flags = get_feature_flags()
        if flags.get("reward_hacking_detection"):
            try:
                task_state_manager = get_task_state_manager()
                recent_actions = task_state_manager.get_recent_actions() if task_state_manager else []
                traces = get_tool_tracer().get_recent_traces(limit=20)
                score = RewardScorer().score_output(
                    output=message_content,
                    user_request=self._user_request or "",
                    recent_actions=recent_actions,
                    tool_traces=traces,
                )
                if score.signals:
                    for signal in score.signals:
                        _metrics.record_reward_hacking_signal(signal.signal_type, signal.severity)
                    logger.warning(
                        "Reward hacking signals detected (log-only)",
                        extra={
                            "signals": [s.signal_type for s in score.signals],
                            "overall_score": score.overall,
                        },
                    )
            except Exception as e:
                logger.debug(f"Reward hacking detection failed: {e}")

        yield StepEvent(
            status=StepStatus.COMPLETED,
            step=Step(id="summarize", description="Summary complete", status=ExecutionStatus.COMPLETED),
        )

        # Emit final report/message event
        is_substantial = len(message_content) > 500
        has_title = bool(message_title)
        is_report_structure = self._is_report_structure(message_content)

        if is_substantial or has_title or is_report_structure:
            title = message_title or "Summary"
            sources = self.get_collected_sources() if self._collected_sources else None
            yield ReportEvent(
                id=str(uuid.uuid4()),
                title=title,
                content=message_content,
                attachments=None,
                sources=sources,
            )
        else:
            yield MessageEvent(message=message_content)

        # Generate suggestions via a lightweight structured call
        try:
            suggestion_response = await self.llm.ask(
                [{"role": "user", "content": f"Given this report title: \"{message_title or 'Summary'}\", suggest exactly 3 short follow-up questions (5-15 words each). Return ONLY a JSON array of 3 strings."}],
                tools=None,
                response_format={"type": "json_object"},
                tool_choice=None,
            )
            import json
            raw = suggestion_response.get("content", "[]")
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            suggestions = parsed if isinstance(parsed, list) else parsed.get("suggestions", [])
            suggestions = [str(s) for s in suggestions[:3]]
            if suggestions:
                yield SuggestionEvent(suggestions=suggestions)
        except Exception as e:
            logger.debug(f"Suggestion generation failed (non-critical): {e}")

    except Exception as e:
        logger.error(f"Error during summarization: {e}")
        yield ErrorEvent(error=f"Failed to generate summary: {e!s}")
```

**Step 3: Verify**

Run: `cd backend && ruff check app/domain/services/agents/execution.py`

**Step 4: Commit**

```bash
git add backend/app/domain/services/agents/execution.py
git commit -m "feat: stream summarize tokens via ask_stream + StreamEvent"
```

---

## Task 5: Create StreamingReportView component

**Files:**
- Create: `frontend/src/components/toolViews/StreamingReportView.vue`

**Step 1: Create the component**

```vue
<template>
  <div class="streaming-report">
    <div class="streaming-header">
      <div class="streaming-indicator">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
      <span class="streaming-label">Composing report...</span>
    </div>
    <div ref="contentRef" class="streaming-content">
      <div class="markdown-body" v-html="renderedHtml"></div>
      <span v-if="!isFinal" class="typing-cursor">|</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

const props = defineProps<{
  text: string;
  isFinal: boolean;
}>();

const contentRef = ref<HTMLElement | null>(null);

const renderedHtml = computed(() => {
  if (!props.text) return '';
  const raw = marked.parse(props.text, { async: false }) as string;
  return DOMPurify.sanitize(raw);
});

// Auto-scroll to bottom as text streams in
watch(() => props.text, async () => {
  await nextTick();
  if (contentRef.value) {
    contentRef.value.scrollTop = contentRef.value.scrollHeight;
  }
});
</script>

<style scoped>
.streaming-report {
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

.streaming-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  scroll-behavior: smooth;
}

.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
  word-wrap: break-word;
}

.markdown-body :deep(h1) {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-light);
}

.markdown-body :deep(h2) {
  font-size: 17px;
  font-weight: 600;
  margin: 20px 0 8px;
}

.markdown-body :deep(h3) {
  font-size: 15px;
  font-weight: 600;
  margin: 16px 0 6px;
}

.markdown-body :deep(p) {
  margin: 0 0 10px;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0 0 10px;
  padding-left: 20px;
}

.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 13px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 6px 10px;
  border: 1px solid var(--border-light);
  text-align: left;
}

.markdown-body :deep(th) {
  background: var(--bolt-elements-bg-depth-2);
  font-weight: 600;
}

.markdown-body :deep(code) {
  background: var(--bolt-elements-bg-depth-2);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 13px;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--border-main);
  padding-left: 12px;
  color: var(--text-secondary);
  margin: 10px 0;
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

**Step 2: Verify**

Run: `cd frontend && bun run type-check`

**Step 3: Commit**

```bash
git add frontend/src/components/toolViews/StreamingReportView.vue
git commit -m "feat: add StreamingReportView component for live report display"
```

---

## Task 6: Update ChatPage to handle summarizing stream events

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue`

**Step 1: Add summaryStreamText ref** (near existing `thinkingText` ref)

Find the line `const thinkingText = ref('')` and add after it:

```typescript
const summaryStreamText = ref('')
const isSummaryStreaming = ref(false)
```

**Step 2: Update handleStreamEvent** (lines 870-878)

Replace with:

```typescript
const handleStreamEvent = (streamData: StreamEventData) => {
  const phase = streamData.phase || 'thinking';

  if (phase === 'summarizing') {
    if (streamData.is_final) {
      isSummaryStreaming.value = false;
      // Keep text visible briefly — cleared when ReportEvent arrives
    } else {
      isSummaryStreaming.value = true;
      summaryStreamText.value += streamData.content;
    }
    return;
  }

  // Default: thinking phase (existing behavior)
  if (streamData.is_final) {
    isThinkingStreaming.value = false;
    thinkingText.value = '';
  } else {
    isThinkingStreaming.value = true;
    thinkingText.value += streamData.content;
  }
}
```

**Step 3: Clear summary stream when ReportEvent or MessageEvent arrives**

In `handleReportEvent` (around line 957), add at the top:
```typescript
// Clear summary streaming overlay — report card takes over
summaryStreamText.value = '';
isSummaryStreaming.value = false;
```

In `handleMessageEvent` (around line 706), add near the top (after `isThinking.value = false`):
```typescript
summaryStreamText.value = '';
isSummaryStreaming.value = false;
```

**Step 4: Pass summaryStreamText to ToolPanel**

Find where `<ToolPanel` is used in the template and add these props:
```vue
:summaryStreamText="summaryStreamText"
:isSummaryStreaming="isSummaryStreaming"
```

**Step 5: Verify**

Run: `cd frontend && bun run type-check`

**Step 6: Commit**

```bash
git add frontend/src/pages/ChatPage.vue
git commit -m "feat: route summarizing stream events to tool panel"
```

---

## Task 7: Pass streaming props through ToolPanel

**Files:**
- Modify: `frontend/src/components/ToolPanel.vue`

**Step 1: Add props to ToolPanel**

In the `defineProps` interface, add:
```typescript
summaryStreamText?: string
isSummaryStreaming?: boolean
```

**Step 2: Pass to ToolPanelContent**

In the `<ToolPanelContent>` template, add:
```vue
:summaryStreamText="panelProps.summaryStreamText"
:isSummaryStreaming="panelProps.isSummaryStreaming"
```

**Step 3: Verify**

Run: `cd frontend && bun run type-check`

**Step 4: Commit**

```bash
git add frontend/src/components/ToolPanel.vue
git commit -m "feat: pass streaming summary props through ToolPanel"
```

---

## Task 8: Show StreamingReportView in ToolPanelContent

**Files:**
- Modify: `frontend/src/components/ToolPanelContent.vue`

**Step 1: Import StreamingReportView**

```typescript
import StreamingReportView from '@/components/toolViews/StreamingReportView.vue';
```

**Step 2: Add props**

In the `defineProps` interface, add:
```typescript
summaryStreamText?: string;
isSummaryStreaming?: boolean;
```

**Step 3: Add template section**

Add BEFORE the VNC view `v-else-if="currentViewType === 'vnc'"` block (around line 93):

```vue
<!-- Streaming Report (live summary composition) -->
<StreamingReportView
  v-if="isSummaryStreaming || summaryStreamText"
  :text="summaryStreamText || ''"
  :is-final="!isSummaryStreaming"
/>
```

This takes priority over all other views when summary is streaming.

**Step 4: Update activity bar for streaming**

In the `toolDisplay` activity bar section (line 33-38), add a streaming state:

```vue
<div v-if="isSummaryStreaming" class="flex items-center gap-2 mt-2 text-[13px] text-[var(--text-tertiary)] overflow-hidden">
  <Loader2 :size="18" class="flex-shrink-0 text-[var(--icon-secondary)] animate-spin" style="min-width: 18px; min-height: 18px;" />
  <span class="flex-shrink-0 whitespace-nowrap">{{ $t('Pythinker is') }} <span class="text-[var(--text-secondary)] font-medium">{{ $t('composing a report') }}</span></span>
</div>
<div v-else-if="toolDisplay" ... >
  <!-- existing tool display -->
</div>
```

**Step 5: Verify**

Run: `cd frontend && bun run type-check && bun run lint`

**Step 6: Commit**

```bash
git add frontend/src/components/ToolPanelContent.vue
git commit -m "feat: show StreamingReportView in tool panel during summarization"
```

---

## Task 9: Update VncMiniPreview for streaming indicator

**Files:**
- Modify: `frontend/src/components/VncMiniPreview.vue`
- Modify: `frontend/src/components/TaskProgressBar.vue`

**Step 1: Add props to VncMiniPreview**

```typescript
/** Whether summary is currently streaming */
isSummaryStreaming?: boolean;
```

Default: `isSummaryStreaming: false`

**Step 2: Add streaming template section**

Add after the editor view and before the VNC catch-all:

```vue
<!-- Summary streaming preview -->
<div v-else-if="isSummaryStreaming" class="content-preview streaming-preview">
  <div class="streaming-mini-window">
    <div class="streaming-mini-header">
      <span class="streaming-mini-title">Composing report</span>
    </div>
    <div class="streaming-mini-body">
      <div class="streaming-mini-lines">
        <div class="streaming-line" v-for="n in 5" :key="n" :style="{ animationDelay: `${n * 0.15}s`, width: `${60 + Math.random() * 35}%` }"></div>
      </div>
    </div>
  </div>
  <div class="activity-indicator"></div>
</div>
```

**Step 3: Add CSS**

```css
/* Streaming mini preview */
.streaming-preview {
  background: var(--bolt-elements-bg-depth-1);
}

.streaming-mini-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  border-radius: 6px;
  overflow: hidden;
}

.streaming-mini-header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 8px;
  background: var(--bolt-elements-bg-depth-2);
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  flex-shrink: 0;
}

.streaming-mini-title {
  font-size: 7px;
  font-weight: 500;
  color: var(--bolt-elements-textPrimary);
}

.streaming-mini-body {
  flex: 1;
  padding: 6px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
}

.streaming-line {
  height: 3px;
  border-radius: 2px;
  background: var(--bolt-elements-borderColor);
  animation: line-appear 0.6s ease-out both;
}

@keyframes line-appear {
  from { width: 0; opacity: 0; }
  to { opacity: 0.6; }
}
```

**Step 4: Pass prop from TaskProgressBar**

In TaskProgressBar.vue, add `:is-summary-streaming="isSummaryStreaming"` to both VncMiniPreview usages. Add the prop to TaskProgressBar's own props interface and pass it from ChatPage.

**Step 5: Verify**

Run: `cd frontend && bun run type-check && bun run lint`

**Step 6: Commit**

```bash
git add frontend/src/components/VncMiniPreview.vue frontend/src/components/TaskProgressBar.vue
git commit -m "feat: add streaming indicator to VNC mini preview"
```

---

## Task 10: Verification

**Step 1: Backend lint + tests**

```bash
cd backend && conda activate pythinker
ruff check . && ruff format --check .
pytest tests/ -q --timeout=30
```

**Step 2: Frontend lint + type-check**

```bash
cd frontend && bun run type-check && bun run lint
```

**Step 3: Manual testing**

1. Start the dev stack: `./dev.sh up -d`
2. Create a research task: "Create a comprehensive research report on: React vs Vue comparison"
3. Verify:
   - After planning/execution, when SUMMARIZING starts, the tool panel shows StreamingReportView
   - Text appears progressively with auto-scroll and typing cursor
   - Activity bar shows "Pythinker is composing a report"
   - VNC mini preview shows streaming line animation
   - When streaming completes, the report card appears in chat
   - Summary stream overlay clears from tool panel

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: streaming summary to VNC panel — complete"
```

---

## Summary of Changes

| Layer | File | Change |
|-------|------|--------|
| Backend model | `event.py` | Add `phase` field to StreamEvent |
| Backend prompt | `prompts/execution.py` | Add STREAMING_SUMMARIZE_PROMPT (plain markdown) |
| Backend agent | `agents/execution.py` | Rewrite `summarize()` to use `ask_stream()` + yield StreamEvents |
| Frontend types | `types/event.ts` | Add `phase` to StreamEventData |
| Frontend view | `toolViews/StreamingReportView.vue` | New: auto-scrolling markdown renderer with cursor |
| Frontend page | `pages/ChatPage.vue` | Route `phase=summarizing` streams to tool panel |
| Frontend panel | `ToolPanel.vue` | Pass streaming props through |
| Frontend panel | `ToolPanelContent.vue` | Show StreamingReportView when streaming |
| Frontend mini | `VncMiniPreview.vue` | Streaming indicator animation |
| Frontend bar | `TaskProgressBar.vue` | Pass streaming prop to mini preview |
