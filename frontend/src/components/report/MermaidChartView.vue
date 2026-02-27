<template>
  <node-view-wrapper class="mermaid-chart-block">
    <div v-if="chartError" class="mermaid-chart-error">
      <span class="mermaid-chart-error-icon">⚠</span>
      <code class="mermaid-chart-error-msg">{{ chartError }}</code>
    </div>
    <div v-else ref="chartEl" class="mermaid-chart-render" v-html="svgContent" />
  </node-view-wrapper>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { NodeViewWrapper } from '@tiptap/vue-3';
import type { NodeViewProps } from '@tiptap/core';

const props = defineProps<NodeViewProps>();

const chartError = ref<string | null>(null);
const svgContent = ref<string>('');

let _idCounter = 0;

const renderChart = async () => {
  const raw = (props.node.attrs.chartCode as string | undefined)?.trim();
  if (!raw) return;

  try {
    // @ts-ignore — mermaid types may not be available on host, but installed in Docker
    const mermaid = (await import('mermaid')).default;
    mermaid.initialize({
      startOnLoad: false,
      theme: document.documentElement.classList.contains('dark') ? 'dark' : 'default',
      securityLevel: 'loose',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
      fontSize: 14,
      flowchart: { curve: 'basis', padding: 16 },
      themeVariables: {
        primaryColor: '#e8edf3',
        primaryTextColor: '#1a1a1a',
        primaryBorderColor: '#c4cdd5',
        lineColor: '#8b95a1',
        secondaryColor: '#f0f4f8',
        tertiaryColor: '#fafbfc',
      },
    });

    const id = `mermaid-${Date.now()}-${++_idCounter}`;
    const { svg } = await mermaid.render(id, raw);
    svgContent.value = svg;
    chartError.value = null;
  } catch (e) {
    chartError.value = (e as Error).message ?? 'Invalid Mermaid syntax';
  }
};

onMounted(renderChart);
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

.mermaid-chart-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 16px;
  background: var(--fill-tsp-gray-main);
  color: var(--text-secondary);
  font-size: 13px;
}

.mermaid-chart-error-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.mermaid-chart-error-msg {
  font-family: 'SF Mono', Menlo, Monaco, monospace;
  font-size: 12px;
}

/* Dark mode */
:global(.dark) .mermaid-chart-block {
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
}

:global(.dark) .mermaid-chart-block:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}
</style>
