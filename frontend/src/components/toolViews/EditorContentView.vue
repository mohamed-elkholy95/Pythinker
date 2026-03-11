<template>
  <ContentContainer :scrollable="false" padding="none" class="editor-view" :class="{ 'writing-active': isWritingActive, 'editor-view--live': isWritingActive }">
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

    <!-- Code editor mode (default) -->
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
import { computed } from 'vue';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
import ErrorState from '@/components/toolViews/shared/ErrorState.vue';
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';

const props = withDefaults(defineProps<{
  content: string;
  filename?: string;
  isWriting?: boolean;
  isLoading?: boolean;
  error?: string;
  /** 'code' shows Monaco editor, 'preview' shows rendered HTML (only for HTML files) */
  viewMode?: 'code' | 'preview';
  /** Whether the current file is an HTML file that supports preview */
  isHtmlFile?: boolean;
}>(), {
  isLoading: false,
  error: '',
  viewMode: 'code',
  isHtmlFile: false,
});

const loadingLabel = computed(() => (props.filename ? 'Loading file' : 'Loading content'));
const loadingDetail = computed(() => props.filename || '');
const isWritingActive = computed(() => !!props.isWriting && !props.isLoading && !props.error);
</script>

<style scoped>
.editor-view {
  position: relative;
}

.editor-body {
  width: 100%;
  height: 100%;
}

/* Live surface decoration — subtle top highlight matching the terminal treatment */
.editor-view--live .editor-body {
  box-shadow: inset 0 2px 0 color-mix(in srgb, var(--status-running, #22c55e) 18%, transparent);
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

