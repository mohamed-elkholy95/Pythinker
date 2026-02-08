<template>
  <div class="streaming-report">
    <div class="streaming-header">
      <div class="streaming-indicator">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
      <span class="streaming-label">{{ isFinal ? 'Report complete' : 'Composing report...' }}</span>
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
