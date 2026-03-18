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
      <TerminalContentView
        v-if="contentType === 'terminal'"
        :content="text"
        :contentType="'shell'"
        :live="true"
      />

      <!-- Code: Monaco editor with syntax highlighting -->
      <EditorContentView
        v-else-if="contentType === 'code'"
        :content="text"
        :language="language"
        :live="true"
      />

      <!-- Markdown: Rendered with marked + sanitized -->
      <div
        v-else-if="contentType === 'markdown'"
        class="markdown-body"
        v-html="renderedMarkdown"
      />

      <!-- JSON: Syntax-highlighted display -->
      <div v-else-if="contentType === 'json'" class="json-content">
        <ShikiCodeBlock
          :code="formattedJson"
          language="json"
          :show-copy="false"
        />
      </div>

      <!-- Search: Use existing SearchContentView -->
      <SearchContentView
        v-else-if="contentType === 'search'"
        :content="text"
        :toolContent="searchToolContent"
        :live="!isFinal"
      />

      <!-- Plain Text: Formatted with line breaks -->
      <pre v-else class="text-content">{{ text }}</pre>

      <!-- Typing Cursor (while streaming) -->
      <span v-if="!isFinal && showCursor && shouldShowCursor" class="typing-cursor">|</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import type { StreamingContentType } from '@/types/streaming';
import type { ToolContent } from '@/types/message';
import TerminalContentView from './TerminalContentView.vue';
import EditorContentView from './EditorContentView.vue';
import SearchContentView from './SearchContentView.vue';
import ShikiCodeBlock from '../ui/ShikiCodeBlock.vue';

// Status label constants for i18n readiness
const STATUS_LABELS = {
  streaming: {
    terminal: 'Executing command...',
    code: 'Writing code...',
    markdown: 'Composing document...',
    json: 'Generating data...',
    search: 'Searching...',
    text: 'Processing...',
  },
  complete: {
    terminal: 'Command complete',
    code: 'Code complete',
    markdown: 'Document complete',
    json: 'Data complete',
    search: 'Search complete',
    text: 'Complete',
  },
} as const;

// Content types that show typing cursor (O(1) lookup)
const CURSOR_CONTENT_TYPES: ReadonlySet<StreamingContentType> = new Set([
  'text',
  'markdown',
  'code',
]);

interface Props {
  text: string;
  contentType: StreamingContentType;
  isFinal: boolean;
  language?: string;
  lineNumbers?: boolean;
  autoScroll?: boolean;
  showCursor?: boolean;
  progressPercent?: number | null;
  toolContent?: ToolContent | null;
}

const props = withDefaults(defineProps<Props>(), {
  contentType: 'text',
  isFinal: false,
  language: 'text',
  lineNumbers: true,
  autoScroll: true,
  showCursor: true,
  progressPercent: null,
  toolContent: null,
});

const contentRef = ref<HTMLElement | null>(null);

// Status labels based on content type
const statusStreaming = computed(() => STATUS_LABELS.streaming[props.contentType]);
const statusComplete = computed(() => STATUS_LABELS.complete[props.contentType]);

// Markdown rendering with XSS protection
const renderedMarkdown = computed(() => {
  if (props.contentType !== 'markdown') return '';
  if (!props.text) return '';

  try {
    const raw = marked.parse(props.text, { async: false }) as string;
    return DOMPurify.sanitize(raw, {
      ALLOWED_TAGS: [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'br', 'ul', 'ol', 'li',
        'strong', 'em', 'code', 'pre',
        'a', 'blockquote', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'img', 'hr', 'span', 'div'
      ],
      ALLOWED_ATTR: ['href', 'title', 'target', 'rel', 'src', 'alt', 'class']
    });
  } catch (error) {
    console.warn('[UnifiedStreamingView] Markdown parsing failed, displaying error fallback', {
      error,
      contentType: props.contentType,
      textLength: props.text?.length,
    });
    return '<p>Error rendering markdown</p>';
  }
});

// Format JSON with proper indentation
const formattedJson = computed(() => {
  if (props.contentType !== 'json') return '';
  if (!props.text) return '';

  try {
    const parsed = JSON.parse(props.text);
    return JSON.stringify(parsed, null, 2);
  } catch (error) {
    console.warn('[UnifiedStreamingView] JSON formatting failed, displaying raw text', {
      error,
      contentType: props.contentType,
      textLength: props.text?.length,
    });
    return props.text;
  }
});

// Create ToolContent for SearchContentView
const searchToolContent = computed((): ToolContent | null => {
  if (props.contentType !== 'search' || !props.toolContent) return null;

  try {
    const results = JSON.parse(props.text);
    return {
      ...props.toolContent,
      content: {
        type: 'search' as const,
        results: Array.isArray(results) ? results : [],
      },
    };
  } catch (error) {
    console.warn('[UnifiedStreamingView] Search results parsing failed, using fallback', {
      error,
      contentType: props.contentType,
      textLength: props.text?.length,
    });
    return props.toolContent;
  }
});

// Show cursor only for text-based content types
const shouldShowCursor = computed(() => CURSOR_CONTENT_TYPES.has(props.contentType));

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
  overflow-x: hidden;
  scroll-behavior: smooth;
  position: relative;
}

/* Markdown body styling */
.markdown-body {
  padding: 16px 20px;
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

/* JSON content styling */
.json-content {
  padding: 16px 20px;
}

/* Text content styling */
.text-content {
  padding: 16px 20px;
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
}

/* Typing cursor animation */
.typing-cursor {
  display: inline;
  font-weight: 200;
  color: var(--bolt-elements-item-contentAccent);
  animation: blink 0.8s step-end infinite;
  margin-left: 2px;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
