<template>
  <div class="flex-1 min-h-0 w-full flex flex-col">
    <!-- Creating Animation -->
    <div v-if="isCreating"
      class="flex-1 overflow-y-auto flex flex-col items-center justify-center bg-gradient-to-b from-[var(--background-gray-main)] to-[var(--fill-white)] dark:from-[#0d1117] dark:to-[#161b22] py-12">
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
    <div v-else :class="resultContainerClass">
      <!-- Chart header -->
      <div
        v-if="!showHeaderControls"
        class="flex items-center mb-3"
        :class="displayTitle ? 'justify-between' : 'justify-end'"
      >
        <span v-if="displayTitle" class="text-sm font-medium text-[var(--text-primary)]">
          {{ displayTitle }}
        </span>
        <div class="flex items-center gap-2">
          <!-- View mode toggle -->
          <div class="flex items-center gap-1 p-0.5 rounded-md bg-[var(--background-gray-light)]">
            <button
              @click="activeViewMode = 'interactive'"
              :class="[
                'px-2 py-1 text-xs rounded-md transition-colors',
                activeViewMode === 'interactive'
                  ? 'bg-white dark:bg-[var(--code-block-bg)] text-[var(--text-primary)] shadow-sm'
                  : 'text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'
              ]"
              :disabled="!canShowInteractive"
            >
              Interactive
            </button>
            <button
              @click="activeViewMode = 'static'"
              :class="[
                'px-2 py-1 text-xs rounded-md transition-colors',
                activeViewMode === 'static'
                  ? 'bg-white dark:bg-[var(--code-block-bg)] text-[var(--text-primary)] shadow-sm'
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
      <div v-if="activeViewMode === 'interactive' && canShowInteractive"
        class="chart-container rounded-lg overflow-hidden border border-[var(--border-main)] bg-white dark:bg-[var(--code-block-bg)] mb-4">
        <div ref="plotlyDiv" class="plotly-chart" v-show="plotlyReady"></div>
        <div v-if="plotlyLoadError" class="p-8 flex flex-col items-center justify-center gap-2">
          <div class="text-[var(--text-tertiary)] text-sm text-center">
            Failed to load interactive chart —
            <button @click="activeViewMode = 'static'" class="text-blue-500 hover:text-blue-600 underline">view static image</button>
            or
            <button @click="openInteractive" class="text-blue-500 hover:text-blue-600 underline">open in new tab</button>
          </div>
        </div>
        <div v-else-if="!plotlyReady" class="p-8 flex items-center justify-center">
          <div class="text-[var(--text-tertiary)] text-sm">Loading interactive chart...</div>
        </div>
      </div>

      <!-- Static PNG preview -->
      <div v-else class="chart-preview-container rounded-lg overflow-hidden border border-[var(--border-main)] bg-white dark:bg-[var(--code-block-bg)] mb-4">
        <img v-if="pngUrl && !pngLoadError" :src="pngUrl" :alt="chartContent.content?.title || 'Chart'" class="w-full h-auto object-contain" @error="onPngError" />
        <div v-else class="p-8 flex flex-col items-center justify-center gap-2 bg-[var(--background-gray-light)]">
          <div class="text-[var(--text-tertiary)] text-sm text-center">
            <template v-if="chartError">
              {{ chartError }}
            </template>
            <template v-else-if="pngLoadError">
              Chart image failed to load — try
              <button v-if="canShowInteractive" @click="activeViewMode = 'interactive'" class="text-blue-500 hover:text-blue-600 underline">interactive view</button>
              <span v-else>regenerating the chart</span>
            </template>
            <template v-else-if="chartContent.status === 'called' && !chartContent.content?.png_file_id">
              Chart output missing — please regenerate the chart
            </template>
            <template v-else>
              Chart preview loading...
            </template>
          </div>
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
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 transition-colors">
          <ExternalLink :size="14" />
          <span>Open in New Tab</span>
        </button>
        <button v-if="chartContent.content?.png_file_id" @click="downloadPng"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
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
import { ExternalLink, Download } from 'lucide-vue-next';
import { fileApi } from '@/api/file';

type PlotlyApi = {
  react: (...args: unknown[]) => Promise<unknown> | unknown;
  purge: (target: HTMLElement) => void;
};
let plotlyModule: PlotlyApi | null = null;
let plotlyLoadPromise: Promise<PlotlyApi> | null = null;

const loadPlotly = async (): Promise<PlotlyApi> => {
  if (plotlyModule) {
    return plotlyModule;
  }

  if (plotlyLoadPromise) {
    return plotlyLoadPromise;
  }

  plotlyLoadPromise = import('plotly.js-dist-min').then((module) => {
    const resolved = (module as { default?: PlotlyApi } & PlotlyApi).default ?? (module as PlotlyApi);
    plotlyModule = resolved;
    return resolved;
  });

  return plotlyLoadPromise;
};

const props = defineProps<{
  sessionId: string;
  chartContent: ToolContent;
  live: boolean;
  viewMode?: 'interactive' | 'static';
  showHeaderControls?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:viewMode', value: 'interactive' | 'static'): void;
}>();

const showHeaderControls = computed(() => props.showHeaderControls === true);

const displayTitle = computed(() => {
  const rawTitle = props.chartContent?.content?.title;
  if (typeof rawTitle !== 'string') return '';
  const trimmed = rawTitle.trim();
  if (!trimmed || trimmed.toLowerCase() === 'chart') return '';
  return trimmed;
});

// View mode state (controlled or uncontrolled)
const internalViewMode = ref<'interactive' | 'static'>(props.viewMode ?? 'interactive');
const activeViewMode = computed<'interactive' | 'static'>({
  get: () => props.viewMode ?? internalViewMode.value,
  set: (value) => {
    internalViewMode.value = value;
    emit('update:viewMode', value);
  },
});

// Plotly element ref
const plotlyDiv = ref<HTMLElement | null>(null);
const plotlyReady = ref(false);
const plotlyLoadError = ref(false);

// PNG error state
const pngLoadError = ref(false);

// Plotly data and layout
const plotlyData = ref<any[] | null>(null);
const plotlyLayout = ref<any | null>(null);

// AbortController for cancelling in-flight fetch requests
let fetchAbortController: AbortController | null = null;

// Fetch timeout (15 seconds — HTML files can be large with embedded data)
const FETCH_TIMEOUT_MS = 15_000;

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

// Backend sync error (propagated from ChartToolContent.error)
const chartError = computed(() => {
  return props.chartContent?.content?.error || null;
});

// PNG load error handler
const onPngError = () => {
  pngLoadError.value = true;
};

// Format HTML file size
const htmlFileSize = computed(() => {
  const size = props.chartContent?.content?.html_size;
  if (!size) return null;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
});

const resultContainerClass = computed(() => {
  if (showHeaderControls.value) {
    return 'flex-1 min-h-0 overflow-y-auto w-full px-2 py-2 sm:px-3 sm:py-3';
  }
  return 'flex-1 min-h-0 overflow-y-auto max-w-[980px] mx-auto px-4 py-4';
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

  // Cancel any in-flight fetch to prevent race conditions
  if (fetchAbortController) {
    fetchAbortController.abort();
  }
  fetchAbortController = new AbortController();
  const { signal } = fetchAbortController;

  plotlyLoadError.value = false;

  try {
    // Timeout wrapper: abort if fetch takes too long
    const timeoutId = setTimeout(() => fetchAbortController?.abort(), FETCH_TIMEOUT_MS);

    const response = await fetch(fileApi.getFileUrl(htmlFileId), { signal });
    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const html = await response.text();

    // Guard: if this request was aborted while reading body, bail out
    if (signal.aborted) return;

    // Extract Plotly data from HTML - try multiple patterns
    // Pattern 1: Plotly.newPlot(..., data, layout, config)
    const dataMatch = html.match(/Plotly\.newPlot\([^,]+,\s*(\[[\s\S]*?\])\s*,\s*({[\s\S]*?})\s*,/);
    if (dataMatch) {
      plotlyData.value = JSON.parse(dataMatch[1]);
      plotlyLayout.value = JSON.parse(dataMatch[2]);
    } else {
      // Pattern 2: Plotly.newPlot(..., data, layout) without config
      const altMatch = html.match(/Plotly\.newPlot\([^,]+,\s*(\[[\s\S]*?\])\s*,\s*({[\s\S]*?})\s*\)/);
      if (altMatch) {
        plotlyData.value = JSON.parse(altMatch[1]);
        plotlyLayout.value = JSON.parse(altMatch[2]);
      } else {
        // Pattern 3: JSON script tag (some Plotly HTML exports use this)
        const scriptMatch = html.match(/<script id="plotly-data" type="application\/json">([\s\S]*?)<\/script>/);
        if (scriptMatch) {
          const jsonData = JSON.parse(scriptMatch[1]);
          plotlyData.value = jsonData.data;
          plotlyLayout.value = jsonData.layout;
        }
      }
    }

    // If no pattern matched, fall back to static view
    if (!plotlyData.value || !plotlyLayout.value) {
      console.warn('Could not extract Plotly data from HTML — falling back to static view');
      plotlyLoadError.value = true;
      return;
    }

    // Apply dark mode theming if needed
    if (isDarkMode()) {
      applyDarkModeTheme();
    }

    // Render chart (only if not aborted during extraction)
    if (!signal.aborted) {
      await nextTick();
      await renderPlotlyChart();
    }
  } catch (error: unknown) {
    // Don't treat intentional aborts as errors
    if (error instanceof DOMException && error.name === 'AbortError') return;
    console.error('Failed to load Plotly data:', error);
    plotlyLoadError.value = true;
  }
};

// Apply dark mode theme to Plotly layout
const applyDarkModeTheme = () => {
  if (!plotlyLayout.value) return;

  plotlyLayout.value = {
    ...plotlyLayout.value,
    paper_bgcolor: '#0d1117',
    plot_bgcolor: '#0d1117',
    font: {
      ...plotlyLayout.value.font,
      color: '#e6edf3',
    },
    xaxis: {
      ...plotlyLayout.value.xaxis,
      gridcolor: '#21262d',
      color: '#e6edf3',
    },
    yaxis: {
      ...plotlyLayout.value.yaxis,
      gridcolor: '#21262d',
      color: '#e6edf3',
    },
  };
};

// Render Plotly chart using native Plotly.js
// Uses Plotly.react for efficient updates (Context7 MCP validated best practice)
const renderPlotlyChart = async () => {
  if (!plotlyDiv.value || !plotlyData.value || !plotlyLayout.value) return;

  try {
    const plotly = await loadPlotly();
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
    await plotly.react(plotlyDiv.value, plotlyData.value, plotlyLayout.value, config);
    plotlyReady.value = true;
  } catch (error) {
    console.error('Failed to render Plotly chart:', error);
    plotlyLoadError.value = true;
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
  if (canShowInteractive.value && activeViewMode.value === 'interactive') {
    loadPlotlyData();
  }
});

watch(() => props.chartContent?.content?.html_file_id, () => {
  if (canShowInteractive.value && activeViewMode.value === 'interactive') {
    plotlyReady.value = false;
    plotlyLoadError.value = false;
    loadPlotlyData();
  }
});

// Reset PNG error when png_file_id changes (e.g., chart regenerated)
watch(() => props.chartContent?.content?.png_file_id, () => {
  pngLoadError.value = false;
});

watch(
  canShowInteractive,
  (canShow) => {
    if (!canShow && activeViewMode.value === 'interactive') {
      activeViewMode.value = 'static';
    }
  },
  { immediate: true }
);

// Re-render when switching to interactive mode
watch(activeViewMode, async (newMode) => {
  if (newMode === 'interactive' && canShowInteractive.value) {
    plotlyLoadError.value = false;
    if (plotlyData.value) {
      plotlyReady.value = false;
      await nextTick();
      await renderPlotlyChart();
    } else {
      // Data not loaded yet — trigger full load
      plotlyReady.value = false;
      loadPlotlyData();
    }
  }
});

watch(
  () => props.viewMode,
  (newMode) => {
    if (newMode) {
      internalViewMode.value = newMode;
    }
  }
);

// Cleanup Plotly instance and abort in-flight fetches
onBeforeUnmount(() => {
  if (fetchAbortController) {
    fetchAbortController.abort();
    fetchAbortController = null;
  }
  if (plotlyDiv.value && plotlyModule) {
    plotlyModule.purge(plotlyDiv.value);
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
  background: linear-gradient(to top, #2563eb, #3b82f6);
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
