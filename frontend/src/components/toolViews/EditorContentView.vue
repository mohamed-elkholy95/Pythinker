<template>
  <ContentContainer :scrollable="false" padding="none" class="editor-view" :class="{ 'writing-active': isWritingActive }">
    <LoadingState
      v-if="isLoading"
      :label="loadingLabel"
      :detail="loadingDetail"
      animation="file"
    />
    <ErrorState v-else-if="error" :error="error" />

    <!-- HTML Preview mode -->
    <HtmlPreviewView
      v-else-if="viewMode === 'preview' && isHtmlFile"
      :content="content"
      :is-live="isWriting"
    />

    <!-- Markdown Preview mode -->
    <section v-else-if="viewMode === 'preview' && isMarkdownFile" class="markdown-preview">
      <div class="markdown-body" v-html="renderedMarkdown"></div>
    </section>

    <!-- Markdown Code view — shiki syntax highlighting -->
    <section v-else-if="isMarkdownFile" class="markdown-code-view">
      <div class="shiki-markdown" v-html="shikiHighlightedHtml"></div>
    </section>

    <!-- Code editor mode (default for non-markdown) -->
    <section v-else class="editor-body">
      <MonacoEditor
        :value="content"
        :filename="filename"
        :read-only="true"
        theme="vs"
        :line-numbers="'off'"
        :word-wrap="'on'"
        :minimap="false"
        :scroll-beyond-last-line="false"
        :automatic-layout="true"
      />
    </section>
  </ContentContainer>
</template>

<script setup lang="ts">
import MonacoEditor from '@/components/ui/MonacoEditor.vue';
import HtmlPreviewView from '@/components/toolViews/HtmlPreviewView.vue';
import { computed, ref, watch, onMounted } from 'vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { useShiki } from '@/composables/useShiki';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
import ErrorState from '@/components/toolViews/shared/ErrorState.vue';
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';

const props = withDefaults(defineProps<{
  content: string;
  filename?: string;
  isWriting?: boolean;
  isLoading?: boolean;
  error?: string;
  /** 'code' shows Monaco editor, 'preview' shows rendered content */
  viewMode?: 'code' | 'preview';
  /** Whether the current file is an HTML file that supports preview */
  isHtmlFile?: boolean;
  /** Whether the current file is a Markdown file that supports preview */
  isMarkdownFile?: boolean;
}>(), {
  isLoading: false,
  error: '',
  viewMode: 'code',
  isHtmlFile: false,
  isMarkdownFile: false,
});

const loadingLabel = computed(() => (props.filename ? 'Loading file' : 'Loading content'));
const loadingDetail = computed(() => props.filename || '');
const isWritingActive = computed(() => !!props.isWriting && !props.isLoading && !props.error);

const renderedMarkdown = computed(() => {
  if (!props.content) return '';
  const raw = marked.parse(props.content, { async: false, breaks: true, gfm: true }) as string;
  return DOMPurify.sanitize(raw);
});

// Shiki highlighting for markdown code view
// Use single-theme `highlight` (not dual) to preserve inline font-weight:bold on headings
const { highlight } = useShiki();
const shikiHighlightedHtml = ref('');

async function highlightMarkdown() {
  if (!props.content || !props.isMarkdownFile) {
    shikiHighlightedHtml.value = '';
    return;
  }
  try {
    shikiHighlightedHtml.value = await highlight(props.content, 'markdown');
  } catch {
    // Fallback: escaped plain text
    shikiHighlightedHtml.value = `<pre><code>${props.content.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] || c))}</code></pre>`;
  }
}

watch(() => [props.content, props.isMarkdownFile, props.viewMode], () => {
  if (props.isMarkdownFile && props.viewMode !== 'preview') {
    highlightMarkdown();
  }
}, { immediate: false });

onMounted(() => {
  if (props.isMarkdownFile) {
    highlightMarkdown();
  }
});
</script>

<style scoped>
.editor-view {
  position: relative;
}

.editor-body {
  width: 100%;
  height: 100%;
}

/* ── Markdown Code view (shiki) ── */
.markdown-code-view {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.18) transparent;
}

.markdown-code-view::-webkit-scrollbar { width: 8px; }
.markdown-code-view::-webkit-scrollbar-track { background: transparent; }
.markdown-code-view::-webkit-scrollbar-thumb { background: rgba(0, 0, 0, 0.18); border-radius: 4px; }
.markdown-code-view::-webkit-scrollbar-thumb:hover { background: rgba(0, 0, 0, 0.28); }

.shiki-markdown {
  font-family: Menlo, 'SF Mono', 'Fira Mono', Consolas, monospace;
  overflow: auto;
  width: 100%;
  padding: 15px 16px;
  white-space: pre-wrap;
  overflow-wrap: break-word;
  word-break: normal;
  font-size: 15px;
  line-height: 22px;
  box-sizing: border-box;
}

.shiki-markdown :deep(pre) {
  margin: 0;
  padding: 0;
  background: transparent !important;
  white-space: pre-wrap !important;
  max-width: 100%;
}

.shiki-markdown :deep(pre code) {
  display: block;
  background: transparent;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  white-space: inherit;
}

/* Dark mode: use shiki CSS variables */
:global(.dark) .shiki-markdown :deep(span) {
  color: var(--shiki-dark) !important;
}

/* ── Markdown preview ── */
.markdown-preview {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  padding: 18px 24px;
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.15) transparent;
}

.markdown-preview::-webkit-scrollbar { width: 6px; }
.markdown-preview::-webkit-scrollbar-track { background: transparent; }
.markdown-preview::-webkit-scrollbar-thumb { background: rgba(0, 0, 0, 0.15); border-radius: 3px; }
.markdown-preview::-webkit-scrollbar-thumb:hover { background: rgba(0, 0, 0, 0.25); }

.markdown-body {
  max-width: 720px;
  margin: 0 auto;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  font-size: 14.5px;
  line-height: 1.6;
  color: #24292e;
  word-wrap: break-word;
}

/* Headings */
.markdown-body :deep(h1) {
  font-size: 1.8em;
  font-weight: 800;
  color: #1e3a5f;
  margin: 0 0 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--border-light);
  line-height: 1.25;
  letter-spacing: -0.02em;
}

.markdown-body :deep(h2) {
  font-size: 1.4em;
  font-weight: 700;
  color: #1e3a5f;
  margin: 24px 0 10px;
  padding-bottom: 5px;
  border-bottom: 1px solid var(--border-light);
  line-height: 1.3;
}

.markdown-body :deep(h3) {
  font-size: 1.15em;
  font-weight: 700;
  color: #1e3a5f;
  margin: 20px 0 8px;
  line-height: 1.35;
}

.markdown-body :deep(h4) {
  font-size: 1.05em;
  font-weight: 700;
  color: #1e3a5f;
  margin: 16px 0 6px;
  line-height: 1.35;
}

.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  font-size: 1em;
  font-weight: 700;
  color: #1e3a5f;
  margin: 14px 0 4px;
  line-height: 1.35;
}

/* Paragraphs */
.markdown-body :deep(p) {
  margin: 0 0 12px;
}

/* Lists */
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0 0 12px;
  padding-left: 24px;
}

.markdown-body :deep(li) {
  margin-bottom: 3px;
}

.markdown-body :deep(li > p) {
  margin-bottom: 4px;
}

.markdown-body :deep(li > ul),
.markdown-body :deep(li > ol) {
  margin-top: 4px;
  margin-bottom: 0;
}

/* Horizontal rule */
.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--border-light);
  margin: 20px 0;
}

/* Bold & italic */
.markdown-body :deep(strong) {
  font-weight: 700;
  color: #1a1a1a;
}

/* Links */
.markdown-body :deep(a) {
  color: #1e3a5f;
  text-decoration: none;
  font-weight: 500;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

/* Tables */
.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 0.92em;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 6px 10px;
  border: 1px solid var(--border-light);
  text-align: left;
}

.markdown-body :deep(th) {
  background: var(--bolt-elements-bg-depth-2, #f8f9fa);
  font-weight: 600;
}

.markdown-body :deep(tr:nth-child(even)) {
  background: var(--bolt-elements-bg-depth-1, #fafbfc);
}

/* Inline code */
.markdown-body :deep(code) {
  font-family: 'SF Mono', 'Fira Code', 'Fira Mono', Menlo, Consolas, monospace;
  background: var(--bolt-elements-bg-depth-2, #f0f1f3);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.88em;
}

/* Code blocks */
.markdown-body :deep(pre) {
  background: var(--bolt-elements-bg-depth-2, #f6f7f9);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  padding: 10px 14px;
  overflow-x: auto;
  margin: 10px 0;
  line-height: 1.45;
}

.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
  border-radius: 0;
  font-size: 0.88em;
}

/* Blockquotes */
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--bolt-elements-item-contentAccent, #6366f1);
  padding: 2px 0 2px 16px;
  color: var(--text-secondary);
  margin: 10px 0;
}

.markdown-body :deep(blockquote p:last-child) {
  margin-bottom: 0;
}

/* Images */
.markdown-body :deep(img) {
  max-width: 100%;
  border-radius: 6px;
  margin: 10px 0;
}

/* Subtle pulsing effect when file is being written */
.writing-active {
  position: relative;
}

.writing-active::after {
  content: '';
  position: absolute;
  inset: 0;
  border: 2px solid transparent;
  border-radius: 0 0 12px 12px;
  pointer-events: none;
  animation: writing-pulse 2s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

@keyframes writing-pulse {
  0%, 100% {
    border-color: rgba(156, 125, 255, 0.12);
  }
  50% {
    border-color: rgba(156, 125, 255, 0.35);
  }
}
</style>

