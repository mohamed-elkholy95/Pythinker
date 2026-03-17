<template>
  <node-view-wrapper class="plotly-chart-block">
    <div v-if="chartError" class="plotly-chart-error">
      <span class="plotly-chart-error-icon">⚠</span>
      <code class="plotly-chart-error-msg">{{ chartError }}</code>
    </div>
    <div v-else ref="chartEl" class="plotly-chart-render" />
  </node-view-wrapper>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue';
import { NodeViewWrapper } from '@tiptap/vue-3';
import type { NodeViewProps } from '@tiptap/core';

const props = defineProps<NodeViewProps>();

const chartEl = ref<HTMLDivElement | null>(null);
const chartError = ref<string | null>(null);

const renderChart = async () => {
  const raw = (props.node.attrs.chartData as string | undefined)?.trim();
  if (!raw || !chartEl.value) return;

  try {
    const spec = JSON.parse(raw) as Record<string, unknown>;
    const Plotly = (await import('plotly.js-dist-min')).default;

    const traces = Array.isArray(spec.data)
      ? (spec.data as Plotly.Data[])
      : Array.isArray(spec)
        ? (spec as Plotly.Data[])
        : [spec as Plotly.Data];

    const layout: Partial<Plotly.Layout> = {
      template: 'plotly_white' as unknown as Plotly.Template,
      margin: { t: 40, l: 60, r: 20, b: 60 },
      font: {
        family: '-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
        size: 12,
      },
      ...(spec.layout as Partial<Plotly.Layout>),
    };

    await Plotly.newPlot(chartEl.value, traces, layout, {
      responsive: true,
      displayModeBar: false,
    });
    chartError.value = null;
  } catch (e) {
    chartError.value = (e as Error).message ?? 'Invalid chart JSON';
  }
};

onMounted(renderChart);
watch(() => props.node.attrs.chartData, renderChart);

onBeforeUnmount(() => {
  if (chartEl.value) {
    import('plotly.js-dist-min').then(({ default: Plotly }) => {
      Plotly.purge(chartEl.value!);
    });
  }
});
</script>

<style scoped>
.plotly-chart-block {
  margin: 1.5rem 0;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--border-light);
  background: var(--background-white-main);
}

.plotly-chart-render {
  min-height: 320px;
  width: 100%;
}

.plotly-chart-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 16px;
  background: var(--fill-tsp-gray-main);
  color: var(--text-secondary);
  font-size: 13px;
}

.plotly-chart-error-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.plotly-chart-error-msg {
  font-family: 'SF Mono', Menlo, Monaco, monospace;
  font-size: 12px;
}
</style>
