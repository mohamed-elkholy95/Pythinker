<template>
  <node-view-wrapper class="mermaid-chart-block">
    <!-- Loading state -->
    <div v-if="isLoading" class="mermaid-chart-loading">
      <svg class="mermaid-loading-spinner" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" opacity="0.2" />
        <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
      </svg>
      <span class="mermaid-loading-text">Rendering diagram...</span>
    </div>

    <!-- Error state -->
    <div v-else-if="chartError" class="mermaid-chart-error">
      <svg class="mermaid-error-icon" viewBox="0 0 16 16" fill="none">
        <path d="M8 1.5L14.5 13H1.5L8 1.5Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round" />
        <path d="M8 6v3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
        <circle cx="8" cy="11" r="0.5" fill="currentColor" />
      </svg>
      <div class="mermaid-error-content">
        <span class="mermaid-error-label">Diagram syntax error</span>
        <code class="mermaid-error-msg">{{ chartError }}</code>
      </div>
    </div>

    <!-- Rendered chart -->
    <div v-else ref="chartEl" class="mermaid-chart-render" v-html="svgContent" />
  </node-view-wrapper>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue';
import { NodeViewWrapper } from '@tiptap/vue-3';
import type { NodeViewProps } from '@tiptap/core';
import type { MermaidConfig } from 'mermaid';

const props = defineProps<NodeViewProps>();

const chartError = ref<string | null>(null);
const svgContent = ref('');
const isLoading = ref(false);
const chartEl = ref<HTMLElement | null>(null);
defineExpose({ chartEl })

let _idCounter = 0;

// Detect dark mode from the root element
const isDarkMode = (): boolean =>
  document.documentElement.classList.contains('dark');

// Build Mermaid config based on current theme
const buildConfig = (): MermaidConfig => ({
  startOnLoad: false,
  securityLevel: 'strict',
  theme: isDarkMode() ? 'dark' : 'default',
  fontFamily: '"Arial", "Helvetica Neue", Helvetica, sans-serif',
  fontSize: 14,
  logLevel: 'error',
  flowchart: { curve: 'basis', padding: 16, useMaxWidth: true },
  sequence: { useMaxWidth: true },
  pie: { useMaxWidth: true },
});

const renderChart = async () => {
  const raw = (props.node.attrs.chartCode as string | undefined)?.trim();
  if (!raw) {
    svgContent.value = '';
    chartError.value = null;
    return;
  }

  isLoading.value = true;
  chartError.value = null;

  try {
    const mermaid = (await import('mermaid')).default;
    mermaid.initialize(buildConfig());

    const id = `mermaid-${Date.now()}-${++_idCounter}`;
    const { svg } = await mermaid.render(id, raw);
    svgContent.value = svg;
    chartError.value = null;
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    // Mermaid errors often include verbose stack info — extract just the first line
    chartError.value = msg.split('\n')[0].slice(0, 200);
    svgContent.value = '';
  } finally {
    isLoading.value = false;
  }
};

// Re-render on dark mode toggle
let _themeObserver: MutationObserver | null = null;

const setupThemeObserver = () => {
  _themeObserver = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (
        mutation.type === 'attributes' &&
        mutation.attributeName === 'class'
      ) {
        // Theme changed — re-render with new colors
        renderChart();
        break;
      }
    }
  });
  _themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class'],
  });
};

onMounted(() => {
  renderChart();
  setupThemeObserver();
});

onBeforeUnmount(() => {
  _themeObserver?.disconnect();
  _themeObserver = null;
});

watch(() => props.node.attrs.chartCode, renderChart);
</script>

<style scoped>
.mermaid-chart-block {
  margin: 1.5rem 0;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--border-light);
  background: var(--background-white-main);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.mermaid-chart-block:hover {
  border-color: var(--border-main);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

/* Loading state */
.mermaid-chart-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 32px 16px;
  color: var(--text-tertiary);
}

.mermaid-loading-spinner {
  width: 20px;
  height: 20px;
  animation: mermaid-spin 0.8s linear infinite;
}

.mermaid-loading-text {
  font-size: 13px;
}

@keyframes mermaid-spin {
  to { transform: rotate(360deg); }
}

/* Rendered chart */
.mermaid-chart-render {
  padding: 24px 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  width: 100%;
  overflow-x: auto;
}

.mermaid-chart-render :deep(svg) {
  max-width: 100%;
  height: auto;
}

/* Error state */
.mermaid-chart-error {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px 16px;
  background: color-mix(in srgb, var(--function-error) 6%, transparent);
  border-left: 3px solid var(--function-error);
  color: var(--text-secondary);
}

.mermaid-error-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--function-error);
}

.mermaid-error-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.mermaid-error-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--function-error);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.mermaid-error-msg {
  font-family: 'SF Mono', Menlo, Monaco, monospace;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
  word-break: break-word;
}

/* Dark mode */
:global(.dark) .mermaid-chart-block {
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
}

:global(.dark) .mermaid-chart-block:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}
</style>
