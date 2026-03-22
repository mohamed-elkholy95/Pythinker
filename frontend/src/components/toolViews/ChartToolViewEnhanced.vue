<template>
  <div class="flex-1 min-h-0 w-full flex flex-col">
    <!-- Creating Animation -->
    <div v-if="isCreating"
      class="flex-1 overflow-y-auto flex flex-col items-center justify-center bg-gradient-to-b from-[var(--background-gray-main)] to-[var(--fill-white)] dark:from-[#141414] dark:to-[#1a1a1a] py-12">
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
            {{ formatChartType(chartPayload?.chart_type) }}
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
          </div>
        </div>
        <div v-else-if="!plotlyReady" class="p-8 flex items-center justify-center">
          <div class="text-[var(--text-tertiary)] text-sm">Loading interactive chart...</div>
        </div>
      </div>

      <!-- Static PNG preview -->
      <div v-else class="chart-preview-container rounded-lg overflow-hidden border border-[var(--border-main)] bg-white dark:bg-[var(--code-block-bg)] mb-4">
        <img v-if="pngUrl && !pngLoadError" :src="pngUrl" :alt="chartPayload?.title || 'Chart'" class="w-full h-auto object-contain cursor-pointer hover:opacity-90 transition-opacity" @click="emit('open-canvas')" @error="onPngError" />
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
            <template v-else-if="chartContent.status === 'called' && !chartPayload?.png_file_id">
              Chart output missing — please regenerate the chart
            </template>
            <template v-else>
              Chart preview loading...
            </template>
          </div>
        </div>
      </div>

      <!-- Chart metadata -->
      <div v-if="chartPayload?.data_points || chartPayload?.series_count"
        class="flex gap-4 text-xs text-[var(--text-tertiary)] mb-4">
        <div v-if="chartPayload?.data_points">
          <span class="font-medium">Data points:</span> {{ chartPayload?.data_points }}
        </div>
        <div v-if="chartPayload?.series_count">
          <span class="font-medium">Series:</span> {{ chartPayload?.series_count }}
        </div>
        <div v-if="htmlFileSize">
          <span class="font-medium">HTML size:</span> {{ htmlFileSize }}
        </div>
      </div>

      <!-- Actions -->
      <div class="flex gap-2">
        <button v-if="chartPayload?.html_file_id" @click="openInteractive"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 transition-colors">
          <ExternalLink :size="14" />
          <span>Open in New Tab</span>
        </button>
        <button v-if="chartPayload?.png_file_id" @click="downloadPng"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
          <Download :size="14" />
          <span>Download PNG</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ToolContent } from '@/types/message';
import type { ChartToolContent } from '@/types/toolContent';
import { computed, ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue';
import { ExternalLink, Download } from 'lucide-vue-next';
import { fileApi } from '@/api/file';
import { extractPlotlyFigureFromHtml, type PlotlyFigureContract } from '@/utils/plotlyFigureContract';
import { useThemeColors } from '@/utils/themeColors';

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
    const resolvedModule = module as unknown as { default?: PlotlyApi } & PlotlyApi;
    const resolved = resolvedModule.default ?? resolvedModule;
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
  (e: 'open-canvas'): void;
}>();

const showHeaderControls = computed(() => props.showHeaderControls === true);

/** Typed accessor for the chart payload inside ToolContent. */
const chartPayload = computed(() => props.chartContent?.content as ChartToolContent | undefined);

const displayTitle = computed(() => {
  const rawTitle = chartPayload.value?.title;
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
const plotlyData = ref<Array<Record<string, unknown>> | null>(null);
const plotlyLayout = ref<Record<string, unknown> | null>(null);
const plotlyConfig = ref<Record<string, unknown> | null>(null);
// Base layout as parsed from HTML — never mutated directly; theme is applied on top
const originalPlotlyLayout = ref<Record<string, unknown> | null>(null);

// Reactive theme mode — drives Plotly re-render on dark/light switch
const { themeMode } = useThemeColors();

// AbortController for cancelling in-flight fetch requests
let fetchAbortController: AbortController | null = null;

// Fetch timeout (15 seconds — HTML files can be large with embedded data)
const FETCH_TIMEOUT_MS = 15_000;

// Detect if chart is being created
const isCreating = computed(() => {
  return props.chartContent?.status === 'calling';
});

// Can show interactive chart (HTML available)
const canShowInteractive = computed(() => {
  return !!chartPayload.value?.html_file_id;
});

// Get PNG preview URL
const pngUrl = computed(() => {
  const pngFileId = chartPayload.value?.png_file_id;
  if (!pngFileId) return null;
  return fileApi.getFileUrl(pngFileId);
});

// Backend sync error (propagated from ChartToolContent.error)
const chartError = computed(() => {
  return chartPayload.value?.error || null;
});

// PNG load error handler
const onPngError = () => {
  pngLoadError.value = true;
};

// Format HTML file size
const htmlFileSize = computed(() => {
  const size = chartPayload.value?.html_size;
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

// Pure function: derives a dark-mode Plotly layout from a base layout.
// Does not mutate its argument — safe to call repeatedly on theme switches.
const buildDarkLayout = (base: Record<string, unknown>): Record<string, unknown> => ({
  ...base,
  paper_bgcolor: '#141414',
  plot_bgcolor: '#141414',
  font: { ...(base.font as Record<string, unknown> | undefined), color: '#e8e0d8' },
  xaxis: { ...(base.xaxis as Record<string, unknown> | undefined), gridcolor: '#242424', color: '#e8e0d8' },
  yaxis: { ...(base.yaxis as Record<string, unknown> | undefined), gridcolor: '#242424', color: '#e8e0d8' },
});

const applyParsedFigure = (figure: PlotlyFigureContract): void => {
  plotlyData.value = figure.data;
  originalPlotlyLayout.value = figure.layout;
  plotlyConfig.value = figure.config ?? null;
};

const loadPlotlyDataFromHtml = async (htmlFileId: string, signal: AbortSignal): Promise<boolean> => {
  const response = await fetch(fileApi.getFileUrl(htmlFileId), { signal });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  const html = await response.text();
  if (signal.aborted) return false;

  const parsed = extractPlotlyFigureFromHtml(html);
  if (!parsed) {
    return false;
  }

  applyParsedFigure(parsed);
  return true;
};

// Load Plotly data from JSON contract first, then HTML fallback
const loadPlotlyData = async () => {
  const htmlFileId = chartPayload.value?.html_file_id;
  if (!htmlFileId) return;

  // Cancel any in-flight fetch to prevent race conditions
  if (fetchAbortController) {
    fetchAbortController.abort();
  }
  const localAbortController = new AbortController();
  fetchAbortController = localAbortController;
  const { signal } = localAbortController;
  const timeoutId = window.setTimeout(() => localAbortController.abort(), FETCH_TIMEOUT_MS);

  plotlyLoadError.value = false;
  plotlyReady.value = false;
  // Reset derived state so a stale layout cannot be re-used if this load fails mid-way
  originalPlotlyLayout.value = null;
  plotlyLayout.value = null;
  plotlyData.value = null;
  plotlyConfig.value = null;

  try {
    const loaded = await loadPlotlyDataFromHtml(htmlFileId, signal);

    if (!loaded || !plotlyData.value || !originalPlotlyLayout.value) {
      console.warn('Could not load interactive Plotly payload — falling back to static view');
      plotlyLoadError.value = true;
      return;
    }

    // Derive effective layout from base + current theme (never mutates originalPlotlyLayout)
    plotlyLayout.value = themeMode.value === 'dark'
      ? buildDarkLayout(originalPlotlyLayout.value)
      : originalPlotlyLayout.value;

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
  } finally {
    window.clearTimeout(timeoutId);
    if (fetchAbortController === localAbortController) {
      fetchAbortController = null;
    }
  }
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
      ...(plotlyConfig.value || {}),
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
  const htmlFileId = chartPayload.value?.html_file_id;
  if (htmlFileId) {
    const url = fileApi.getFileUrl(htmlFileId);
    window.open(url, '_blank');
  }
};

// Download PNG file
const downloadPng = async () => {
  const pngFileId = chartPayload.value?.png_file_id;
  const filename = chartPayload.value?.png_filename || 'chart.png';
  if (pngFileId) {
    const blob = await fileApi.downloadFile(pngFileId);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }
};

// Load Plotly data when component mounts or chart content changes
onMounted(() => {
  if (canShowInteractive.value && activeViewMode.value === 'interactive') {
    void loadPlotlyData();
  }
});

watch(
  () => chartPayload.value?.html_file_id,
  () => {
    if (canShowInteractive.value && activeViewMode.value === 'interactive') {
      plotlyReady.value = false;
      plotlyLoadError.value = false;
      void loadPlotlyData();
    }
  }
);

// Reset PNG error when png_file_id changes (e.g., chart regenerated)
watch(() => chartPayload.value?.png_file_id, () => {
  pngLoadError.value = false;
});

watch(
  canShowInteractive,
  (canShow) => {
    if (canShow && activeViewMode.value === 'static') {
      // Promote to interactive when data becomes available
      // (e.g., tool result arrived after initial render demoted to static)
      activeViewMode.value = 'interactive';
    } else if (!canShow && activeViewMode.value === 'interactive') {
      activeViewMode.value = 'static';
    }
  },
  { immediate: true }
);

// Re-render when switching to interactive mode
watch(activeViewMode, async (newMode) => {
  if (newMode === 'interactive' && canShowInteractive.value) {
    plotlyLoadError.value = false;
    if (plotlyData.value && originalPlotlyLayout.value) {
      plotlyReady.value = false;
      await nextTick();
      await renderPlotlyChart();
    } else {
      // Data not loaded yet — trigger full load
      plotlyReady.value = false;
      void loadPlotlyData();
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

// Re-theme Plotly chart when user switches dark/light mode.
// Uses Plotly.react() for efficient diffing — only changed layout props are repainted.
watch(themeMode, async (newMode) => {
  if (!originalPlotlyLayout.value || !plotlyData.value) return;
  plotlyLayout.value = newMode === 'dark'
    ? buildDarkLayout(originalPlotlyLayout.value)
    : originalPlotlyLayout.value;
  if (plotlyReady.value) {
    await renderPlotlyChart();
  }
});

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
