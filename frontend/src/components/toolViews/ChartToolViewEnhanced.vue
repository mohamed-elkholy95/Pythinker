<template>
  <div
    class="h-[36px] flex items-center px-3 w-full bg-[var(--background-gray-main)] border-b border-[var(--border-main)] rounded-t-[12px] shadow-[inset_0px_1px_0px_0px_#FFFFFF] dark:shadow-[inset_0px_1px_0px_0px_#FFFFFF30]">
    <div class="flex-1 flex items-center justify-center">
      <div class="max-w-[250px] truncate text-[var(--text-tertiary)] text-sm font-medium text-center">
        {{ isCreating ? 'Creating Chart' : chartContent.content?.title || 'Chart' }}
      </div>
    </div>
  </div>
  <div class="flex-1 min-h-0 w-full overflow-y-auto">
    <!-- Creating Animation -->
    <div v-if="isCreating"
      class="flex-1 h-full flex flex-col items-center justify-center bg-gradient-to-b from-[var(--background-gray-main)] to-[var(--fill-white)] dark:from-[#1a1a2e] dark:to-[#16213e] py-12">
      <div class="chart-animation">
        <!-- Animated chart bars -->
        <div class="chart-bars">
          <div class="bar bar-1"></div>
          <div class="bar bar-2"></div>
          <div class="bar bar-3"></div>
        </div>
      </div>
      <div class="mt-6 flex flex-col items-center gap-2">
        <div class="flex items-center gap-2 text-[var(--text-secondary)]">
          <span class="text-base font-medium">Generating chart</span>
          <span class="flex gap-1">
            <span v-for="(_, i) in 3" :key="i" class="dot" :style="{ animationDelay: `${i * 200}ms` }"></span>
          </span>
        </div>
      </div>
    </div>

    <!-- Chart Results -->
    <div v-else class="flex-1 min-h-0 max-w-[900px] mx-auto px-4 py-4">
      <!-- Chart header -->
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
          <BarChart3 :size="16" class="text-[var(--text-brand)]" />
          <span class="text-sm font-medium text-[var(--text-primary)]">
            {{ chartContent.content?.title }}
          </span>
        </div>
        <div class="flex items-center gap-2">
          <!-- View mode toggle -->
          <div class="flex items-center gap-1 p-0.5 rounded-md bg-[var(--background-gray-light)]">
            <button
              @click="viewMode = 'interactive'"
              :class="[
                'px-2 py-1 text-xs rounded-md transition-colors',
                viewMode === 'interactive'
                  ? 'bg-white dark:bg-[#2a2a3e] text-[var(--text-primary)] shadow-sm'
                  : 'text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'
              ]"
              :disabled="!canShowInteractive"
            >
              Interactive
            </button>
            <button
              @click="viewMode = 'static'"
              :class="[
                'px-2 py-1 text-xs rounded-md transition-colors',
                viewMode === 'static'
                  ? 'bg-white dark:bg-[#2a2a3e] text-[var(--text-primary)] shadow-sm'
                  : 'text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'
              ]"
            >
              Static
            </button>
          </div>
          <span class="text-xs px-2 py-0.5 rounded bg-[var(--background-gray-light)] text-[var(--text-tertiary)]">
            {{ formatChartType(chartContent.content?.chart_type) }}
          </span>
        </div>
      </div>

      <!-- Interactive Plotly Chart (embedded) -->
      <div v-if="viewMode === 'interactive' && canShowInteractive"
        class="chart-container rounded-lg overflow-hidden border border-[var(--border-main)] bg-white dark:bg-[#1a1a2e] mb-4">
        <div ref="plotlyDiv" class="plotly-chart" v-show="plotlyReady"></div>
        <div v-if="!plotlyReady" class="p-8 flex items-center justify-center">
          <div class="text-[var(--text-tertiary)] text-sm">Loading interactive chart...</div>
        </div>
      </div>

      <!-- Static PNG preview -->
      <div v-else class="chart-preview-container rounded-lg overflow-hidden border border-[var(--border-main)] bg-white dark:bg-[#1a1a2e] mb-4">
        <img v-if="pngUrl" :src="pngUrl" :alt="chartContent.content?.title || 'Chart'" class="w-full h-auto object-contain" />
        <div v-else class="p-8 flex items-center justify-center bg-[var(--background-gray-light)]">
          <div class="text-[var(--text-tertiary)] text-sm">Chart preview loading...</div>
        </div>
      </div>

      <!-- Chart metadata -->
      <div v-if="chartContent.content?.data_points || chartContent.content?.series_count"
        class="flex gap-4 text-xs text-[var(--text-tertiary)] mb-4">
        <div v-if="chartContent.content?.data_points">
          <span class="font-medium">Data points:</span> {{ chartContent.content.data_points }}
        </div>
        <div v-if="chartContent.content?.series_count">
          <span class="font-medium">Series:</span> {{ chartContent.content.series_count }}
        </div>
        <div v-if="htmlFileSize">
          <span class="font-medium">HTML size:</span> {{ htmlFileSize }}
        </div>
      </div>

      <!-- Actions -->
      <div class="flex gap-2">
        <button v-if="chartContent.content?.html_file_id" @click="openInteractive"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-[var(--background-brand)] text-white text-sm font-medium hover:bg-[var(--background-brand-hover)] transition-colors">
          <ExternalLink :size="14" />
          <span>Open in New Tab</span>
        </button>
        <button v-if="chartContent.content?.png_file_id" @click="downloadPng"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-[var(--border-main)] text-[var(--text-primary)] text-sm font-medium hover:bg-[var(--background-gray-light)] transition-colors">
          <Download :size="14" />
          <span>Download PNG</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ToolContent } from '@/types/message';
import { computed, ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue';
import { BarChart3, ExternalLink, Download } from 'lucide-vue-next';
import { fileApi } from '@/api/file';
import Plotly from 'plotly.js-dist-min';

const props = defineProps<{
  sessionId: string;
  chartContent: ToolContent;
  live: boolean;
}>();

// View mode state (interactive or static)
const viewMode = ref<'interactive' | 'static'>('interactive');

// Plotly element ref
const plotlyDiv = ref<HTMLElement | null>(null);
const plotlyReady = ref(false);

// Plotly data and layout
const plotlyData = ref<any[] | null>(null);
const plotlyLayout = ref<any | null>(null);

// Detect if chart is being created
const isCreating = computed(() => {
  return props.chartContent?.status === 'calling';
});

// Can show interactive chart (HTML file available)
const canShowInteractive = computed(() => {
  return !!props.chartContent?.content?.html_file_id;
});

// Get PNG preview URL
const pngUrl = computed(() => {
  const pngFileId = props.chartContent?.content?.png_file_id;
  if (!pngFileId) return null;
  return fileApi.getFileUrl(pngFileId);
});

// Format HTML file size
const htmlFileSize = computed(() => {
  const size = props.chartContent?.content?.html_size;
  if (!size) return null;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
});

// Format chart type for display
const formatChartType = (type: string | undefined) => {
  if (!type) return 'Chart';
  return type
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};

// Check if dark mode is active
const isDarkMode = () => {
  return document.documentElement.classList.contains('dark');
};

// Load Plotly data from HTML file
const loadPlotlyData = async () => {
  const htmlFileId = props.chartContent?.content?.html_file_id;
  if (!htmlFileId) return;

  try {
    const response = await fetch(fileApi.getFileUrl(htmlFileId));
    const html = await response.text();

    // Extract Plotly data from HTML - try multiple patterns
    const dataMatch = html.match(/Plotly\.newPlot\([^,]+,\s*(\[[\s\S]*?\])\s*,\s*({[\s\S]*?})\s*,/);
    if (dataMatch) {
      plotlyData.value = JSON.parse(dataMatch[1]);
      plotlyLayout.value = JSON.parse(dataMatch[2]);
    } else {
      // Fallback: try JSON script tag
      const scriptMatch = html.match(/<script id="plotly-data" type="application\/json">([\s\S]*?)<\/script>/);
      if (scriptMatch) {
        const jsonData = JSON.parse(scriptMatch[1]);
        plotlyData.value = jsonData.data;
        plotlyLayout.value = jsonData.layout;
      }
    }

    // Apply dark mode theming if needed
    if (isDarkMode()) {
      applyDarkModeTheme();
    }

    // Render chart
    if (plotlyData.value && plotlyLayout.value) {
      await nextTick();
      await renderPlotlyChart();
    }
  } catch (error) {
    console.error('Failed to load Plotly data:', error);
    viewMode.value = 'static';
  }
};

// Apply dark mode theme to Plotly layout
const applyDarkModeTheme = () => {
  if (!plotlyLayout.value) return;

  plotlyLayout.value = {
    ...plotlyLayout.value,
    paper_bgcolor: '#1a1a2e',
    plot_bgcolor: '#1a1a2e',
    font: {
      ...plotlyLayout.value.font,
      color: '#e0e0e0',
    },
    xaxis: {
      ...plotlyLayout.value.xaxis,
      gridcolor: '#2a2a3e',
      color: '#e0e0e0',
    },
    yaxis: {
      ...plotlyLayout.value.yaxis,
      gridcolor: '#2a2a3e',
      color: '#e0e0e0',
    },
  };
};

// Render Plotly chart using native Plotly.js
// Uses Plotly.react for efficient updates (Context7 MCP validated best practice)
const renderPlotlyChart = async () => {
  if (!plotlyDiv.value || !plotlyData.value || !plotlyLayout.value) return;

  try {
    const config = {
      responsive: true,
      displayModeBar: true,
      displaylogo: false,
      modeBarButtonsToRemove: ['sendDataToCloud', 'lasso2d', 'select2d'],
      toImageButtonOptions: {
        format: 'png' as const,
        filename: 'chart',
        height: 600,
        width: 1200,
        scale: 2,
      },
    };

    // Use Plotly.react for declarative updates (intelligently diffs state)
    // Falls back to newPlot if chart doesn't exist yet
    await Plotly.react(plotlyDiv.value, plotlyData.value, plotlyLayout.value, config);
    plotlyReady.value = true;
  } catch (error) {
    console.error('Failed to render Plotly chart:', error);
    viewMode.value = 'static';
  }
};

// Open interactive HTML chart in new tab
const openInteractive = () => {
  const htmlFileId = props.chartContent?.content?.html_file_id;
  if (htmlFileId) {
    const url = fileApi.getFileUrl(htmlFileId);
    window.open(url, '_blank');
  }
};

// Download PNG file
const downloadPng = () => {
  const pngFileId = props.chartContent?.content?.png_file_id;
  const filename = props.chartContent?.content?.png_filename || 'chart.png';
  if (pngFileId) {
    fileApi.downloadFile(pngFileId, filename);
  }
};

// Load Plotly data when component mounts or chart content changes
onMounted(() => {
  if (canShowInteractive.value && viewMode.value === 'interactive') {
    loadPlotlyData();
  }
});

watch(() => props.chartContent?.content?.html_file_id, () => {
  if (canShowInteractive.value && viewMode.value === 'interactive') {
    plotlyReady.value = false;
    loadPlotlyData();
  }
});

// Re-render when switching to interactive mode
watch(viewMode, async (newMode) => {
  if (newMode === 'interactive' && canShowInteractive.value && plotlyData.value) {
    plotlyReady.value = false;
    await nextTick();
    await renderPlotlyChart();
  }
});

// Cleanup Plotly instance
onBeforeUnmount(() => {
  if (plotlyDiv.value) {
    Plotly.purge(plotlyDiv.value);
  }
});
</script>

<style scoped>
/* Chart Animation Styles */
.chart-animation {
  position: relative;
  width: 100px;
  height: 80px;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 8px;
}

.chart-bars {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 8px;
  height: 100%;
}

.bar {
  width: 16px;
  background: linear-gradient(to top, var(--background-brand), var(--background-brand-hover));
  border-radius: 4px 4px 0 0;
  animation: bar-grow 1.5s ease-in-out infinite;
}

.bar-1 {
  animation-delay: 0s;
}

.bar-2 {
  animation-delay: 0.2s;
}

.bar-3 {
  animation-delay: 0.4s;
}

/* Bouncing dots */
.dot {
  display: inline-block;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background-color: var(--text-tertiary);
  animation: bounce-dot 1.4s ease-in-out infinite;
}

.chart-preview-container,
.chart-container {
  max-height: 600px;
  min-height: 400px;
}

.chart-container {
  padding: 1rem;
}

.plotly-chart {
  width: 100%;
  min-height: 400px;
}

@keyframes bar-grow {
  0%,
  100% {
    height: 30%;
    opacity: 0.6;
  }

  50% {
    height: 80%;
    opacity: 1;
  }
}

@keyframes bounce-dot {
  0%,
  80%,
  100% {
    transform: translateY(0);
  }

  40% {
    transform: translateY(-6px);
  }
}

/* Responsive chart sizing */
@media (max-width: 768px) {
  .chart-preview-container,
  .chart-container {
    max-height: 400px;
    min-height: 300px;
  }
}
</style>
