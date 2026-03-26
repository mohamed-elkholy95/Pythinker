<template>
  <ContentContainer :scrollable="false" padding="none" class="html-preview-view">
    <!-- Loading skeleton -->
    <div v-if="!hasContent" class="html-preview-empty">
      <div class="html-preview-empty-icon">
        <Code2 :size="32" />
      </div>
      <p class="html-preview-empty-text">No HTML content to preview</p>
    </div>

    <!-- Sandboxed iframe preview -->
    <iframe
      v-else
      class="html-preview-iframe"
      :srcdoc="debouncedContent"
      sandbox="allow-scripts"
      title="HTML Preview"
      @load="onIframeLoad"
    />

    <!-- Loading overlay during initial render -->
    <Transition name="fade">
      <div v-if="hasContent && !iframeLoaded" class="html-preview-loading">
        <Loader2 :size="20" class="animate-spin text-[var(--text-tertiary)]" />
      </div>
    </Transition>
  </ContentContainer>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { Code2, Loader2 } from 'lucide-vue-next';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';

const props = defineProps<{
  content: string;
  isLive?: boolean;
}>();


const iframeLoaded = ref(false);

// Debounced content to avoid flicker during streaming writes
const debouncedContent = ref('');
let debounceTimer: ReturnType<typeof setTimeout> | null = null;

const hasContent = computed(() => props.content.trim().length > 0);

// Debounce updates: short during live streaming, instant when settled
watch(
  () => props.content,
  (newContent) => {
    if (debounceTimer) clearTimeout(debounceTimer);

    if (!props.isLive) {
      // Not live — apply immediately
      debouncedContent.value = newContent;
      return;
    }

    // During live streaming, debounce to avoid rapid iframe reloads
    debounceTimer = setTimeout(() => {
      debouncedContent.value = newContent;
      debounceTimer = null;
    }, 400);
  },
  { immediate: true }
);

const onIframeLoad = () => {
  iframeLoaded.value = true;
};

// Reset loaded state when content changes substantially
watch(debouncedContent, () => {
  iframeLoaded.value = false;
});
</script>

<style scoped>
.html-preview-view {
  position: relative;
  height: 100%;
  width: 100%;
}

.html-preview-iframe {
  width: 100%;
  height: 100%;
  border: none;
  background: var(--background-white-main, #fff);
  display: block;
}

.html-preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: var(--text-quaternary);
}

.html-preview-empty-icon {
  opacity: 0.4;
}

.html-preview-empty-text {
  font-size: 13px;
  margin: 0;
}

.html-preview-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--background-white-main, #fff);
  z-index: 1;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
