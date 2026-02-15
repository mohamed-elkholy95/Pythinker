<template>
  <div class="shiki-code-block" :class="{ 'has-filename': !!filename }">
    <!-- Header bar with filename and copy button -->
    <div v-if="showHeader" class="code-header">
      <div class="header-left">
        <span v-if="filename" class="filename">{{ filename }}</span>
        <span v-else-if="displayLanguage" class="language-badge">{{ displayLanguage }}</span>
      </div>
      <div class="header-right">
        <button
          v-if="showCopyButton"
          class="copy-button"
          :class="{ copied }"
          @click="handleCopy"
          :aria-label="copied ? 'Copied!' : 'Copy code'"
        >
          <CheckIcon v-if="copied" :size="14" />
          <CopyIcon v-else :size="14" />
          <span class="copy-text">{{ copied ? 'Copied!' : 'Copy' }}</span>
        </button>
      </div>
    </div>

    <!-- Code content -->
    <div
      class="code-content"
      :class="{
        'with-line-numbers': showLineNumbers,
        'has-max-height': !!maxHeight,
      }"
      :style="maxHeight ? { maxHeight: `${maxHeight}px` } : undefined"
    >
      <!-- Loading skeleton -->
      <div v-if="isHighlighting" class="code-skeleton">
        <div v-for="i in skeletonLines" :key="i" class="skeleton-line" :style="{ width: `${getSkeletonWidth(i)}%` }"></div>
      </div>

      <!-- Highlighted code -->
      <div
        v-else
        class="highlighted-code"
        v-html="highlightedHtml"
      ></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { CopyIcon, CheckIcon } from 'lucide-vue-next'
import { useShiki } from '@/composables/useShiki'
import { copyToClipboard } from '@/utils/dom'

interface Props {
  /** The code to highlight */
  code: string
  /** Programming language */
  language?: string
  /** Optional filename (for display and language detection) */
  filename?: string
  /** Show line numbers */
  showLineNumbers?: boolean
  /** Show copy button */
  showCopyButton?: boolean
  /** Maximum height in pixels (enables scrolling) */
  maxHeight?: number
  /** Lines to highlight (1-indexed) */
  highlightLines?: number[]
}

const props = withDefaults(defineProps<Props>(), {
  language: 'text',
  showLineNumbers: false,
  showCopyButton: true,
  highlightLines: () => [],
})

const { highlightDualTheme, detectLanguage } = useShiki()

const highlightedHtml = ref('')
const copied = ref(false)
const isHighlighting = ref(true)

// Detect language from filename or use provided
const effectiveLanguage = computed(() => {
  if (props.filename) {
    return detectLanguage(props.filename)
  }
  return props.language
})

// Display language for badge
const displayLanguage = computed(() => {
  const lang = effectiveLanguage.value
  if (!lang || lang === 'text') return null

  // Capitalize first letter for display
  return lang.charAt(0).toUpperCase() + lang.slice(1)
})

// Show header if there's something to show
const showHeader = computed(() => {
  return props.filename || displayLanguage.value || props.showCopyButton
})

// Calculate skeleton lines based on code length
const skeletonLines = computed(() => {
  const lineCount = props.code.split('\n').length
  return Math.min(lineCount, 10)
})

// Get varied skeleton line widths for visual interest
function getSkeletonWidth(index: number): number {
  const widths = [80, 65, 90, 45, 75, 55, 85, 40, 70, 60]
  return widths[(index - 1) % widths.length]
}

// Highlight the code
async function highlightCodeContent() {
  if (!props.code) {
    highlightedHtml.value = ''
    isHighlighting.value = false
    return
  }

  isHighlighting.value = true

  try {
    highlightedHtml.value = await highlightDualTheme(props.code, effectiveLanguage.value, {
      lineNumbers: props.showLineNumbers,
      highlightLines: props.highlightLines,
    })
  } catch {
    // Fallback to escaped plain text
    highlightedHtml.value = `<pre class="shiki"><code>${escapeHtml(props.code)}</code></pre>`
  } finally {
    isHighlighting.value = false
  }
}

function escapeHtml(text: string): string {
  const htmlEntities: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }
  return text.replace(/[&<>"']/g, (char) => htmlEntities[char])
}

// Handle copy button click
async function handleCopy() {
  const success = await copyToClipboard(props.code)
  if (success) {
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  }
}

// Watch for code or language changes
watch(
  () => [props.code, effectiveLanguage.value, props.showLineNumbers, props.highlightLines],
  () => {
    highlightCodeContent()
  },
  { immediate: false }
)

onMounted(() => {
  highlightCodeContent()
})

// Expose highlight method for external use
defineExpose({
  refresh: highlightCodeContent,
})
</script>

<style scoped>
.shiki-code-block {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  background: var(--bolt-elements-messages-code-background, #f6f8fa);
  border: 1px solid var(--border-dark, #e1e4e8);
  font-family: 'SF Mono', Menlo, Monaco, 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
}

:global(.dark) .shiki-code-block {
  background: var(--code-block-bg);
  border-color: var(--code-block-border);
}

/* Header */
.code-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: rgba(0, 0, 0, 0.03);
  border-bottom: 1px solid var(--border-dark, #e1e4e8);
}

:global(.dark) .code-header {
  background: rgba(255, 255, 255, 0.03);
  border-color: var(--code-block-border);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filename {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary, #586069);
}

:global(.dark) .filename {
  color: #8b949e;
}

.language-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.06);
  color: var(--text-tertiary, #6a737d);
}

:global(.dark) .language-badge {
  background: rgba(255, 255, 255, 0.06);
  color: #8b949e;
}

/* Copy button */
.copy-button {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-tertiary, #6a737d);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.copy-button:hover {
  background: rgba(0, 0, 0, 0.06);
  color: var(--text-primary, #24292e);
}

:global(.dark) .copy-button:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #e6edf3;
}

.copy-button.copied {
  color: #22c55e;
}

.copy-text {
  font-weight: 500;
}

/* Code content */
.code-content {
  overflow-x: auto;
}

.code-content.has-max-height {
  overflow-y: auto;
}

.highlighted-code {
  padding: 12px 16px;
}

/* Style Shiki output */
.highlighted-code :deep(pre) {
  margin: 0;
  padding: 0;
  background: transparent !important;
  overflow: visible;
}

.highlighted-code :deep(code) {
  display: block;
  background: transparent;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
}

/* Dark theme uses CSS variables from Shiki dual-theme output */
:global(.dark) .highlighted-code :deep(span) {
  color: var(--shiki-dark) !important;
}

/* Line numbers styling */
.code-content.with-line-numbers .highlighted-code :deep(.line) {
  display: block;
  padding-left: 3.5em;
  position: relative;
}

.code-content.with-line-numbers .highlighted-code :deep(.line)::before {
  content: attr(data-line);
  position: absolute;
  left: 0;
  width: 2.5em;
  padding-right: 0.5em;
  text-align: right;
  color: var(--text-tertiary, #6a737d);
  opacity: 0.5;
  user-select: none;
}

/* Highlighted lines */
.highlighted-code :deep(.line.highlighted) {
  background: rgba(255, 220, 0, 0.15);
  margin: 0 -16px;
  padding-left: calc(16px + 3.5em);
  padding-right: 16px;
}

:global(.dark) .highlighted-code :deep(.line.highlighted) {
  background: rgba(255, 220, 0, 0.1);
}

/* Loading skeleton */
.code-skeleton {
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skeleton-line {
  height: 14px;
  background: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0.06) 0%,
    rgba(0, 0, 0, 0.1) 50%,
    rgba(0, 0, 0, 0.06) 100%
  );
  border-radius: 4px;
  animation: skeleton-shimmer 1.5s infinite;
}

:global(.dark) .skeleton-line {
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.04) 0%,
    rgba(255, 255, 255, 0.08) 50%,
    rgba(255, 255, 255, 0.04) 100%
  );
}

@keyframes skeleton-shimmer {
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
}

/* Scrollbar styling */
.code-content {
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.15) transparent;
}

.code-content::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.code-content::-webkit-scrollbar-track {
  background: transparent;
}

.code-content::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.12);
  border-radius: 9999px;
}

:global(.dark) .code-content {
  scrollbar-color: rgba(255, 255, 255, 0.12) transparent;
}

:global(.dark) .code-content::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.12);
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .skeleton-line {
    animation: none;
  }
}
</style>
