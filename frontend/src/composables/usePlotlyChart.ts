/**
 * Vue 3 Composable for Plotly Chart Management
 *
 * Provides reactive Plotly chart state and utilities following Vue 3 best practices:
 * - Lazy loading of chart data
 * - Dark mode support
 * - Responsive sizing
 * - Error handling with fallbacks
 */

import { ref, computed, watch, onMounted } from 'vue';

export interface PlotlyChartOptions {
  htmlFileUrl?: string;
  darkMode?: boolean;
  responsive?: boolean;
}

export interface PlotlyChartData {
  data: any[] | null;
  layout: any | null;
  config: any;
  loading: boolean;
  error: string | null;
}

export function usePlotlyChart(options: PlotlyChartOptions = {}) {
  // Reactive state
  const plotlyData = ref<any[] | null>(null);
  const plotlyLayout = ref<any | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  // Default Plotly config (following Plotly.js best practices)
  const plotlyConfig = computed(() => ({
    responsive: options.responsive !== false,
    displayModeBar: true,
    displaylogo: false,
    modeBarButtonsToRemove: ['sendDataToCloud', 'lasso2d', 'select2d'],
    toImageButtonOptions: {
      format: 'png',
      filename: 'chart',
      height: 600,
      width: 1200,
      scale: 2,
    },
  }));

  /**
   * Extract Plotly data from HTML file
   * Supports two common formats:
   * 1. Plotly.newPlot() call in script
   * 2. JSON data in <script id="plotly-data"> tag
   */
  const loadChartFromHtml = async (htmlFileUrl: string) => {
    if (!htmlFileUrl) {
      error.value = 'No HTML file URL provided';
      return;
    }

    loading.value = true;
    error.value = null;

    try {
      const response = await fetch(htmlFileUrl);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const html = await response.text();

      // Method 1: Extract from Plotly.newPlot() call
      const newPlotMatch = html.match(/Plotly\.newPlot\([^,]+,\s*(\[[\s\S]*?\])\s*,\s*({[\s\S]*?})\s*,/);
      if (newPlotMatch) {
        try {
          plotlyData.value = JSON.parse(newPlotMatch[1]);
          plotlyLayout.value = JSON.parse(newPlotMatch[2]);
        } catch (parseError) {
          console.warn('Failed to parse Plotly.newPlot data:', parseError);
        }
      }

      // Method 2: Extract from JSON script tag (fallback)
      if (!plotlyData.value) {
        const scriptMatch = html.match(/<script id="plotly-data" type="application\/json">([\s\S]*?)<\/script>/);
        if (scriptMatch) {
          const jsonData = JSON.parse(scriptMatch[1]);
          plotlyData.value = jsonData.data || [];
          plotlyLayout.value = jsonData.layout || {};
        }
      }

      // Method 3: Extract from window.PLOTLYENV (Plotly CDN pattern)
      if (!plotlyData.value) {
        const envMatch = html.match(/window\.PLOTLYENV[\s\S]*?data:\s*(\[[\s\S]*?\]),[\s\S]*?layout:\s*({[\s\S]*?})/);
        if (envMatch) {
          plotlyData.value = JSON.parse(envMatch[1]);
          plotlyLayout.value = JSON.parse(envMatch[2]);
        }
      }

      if (!plotlyData.value) {
        throw new Error('Could not extract Plotly data from HTML file');
      }

      // Apply dark mode if needed
      if (options.darkMode) {
        applyDarkModeTheme();
      }

    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      error.value = `Failed to load chart: ${message}`;
      console.error('Plotly chart load error:', err);
    } finally {
      loading.value = false;
    }
  };

  /**
   * Apply dark mode theme to Plotly layout
   */
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

  /**
   * Apply light mode theme to Plotly layout
   */
  const applyLightModeTheme = () => {
    if (!plotlyLayout.value) return;

    plotlyLayout.value = {
      ...plotlyLayout.value,
      paper_bgcolor: '#ffffff',
      plot_bgcolor: '#ffffff',
      font: {
        ...plotlyLayout.value.font,
        color: '#1a1a1a',
      },
      xaxis: {
        ...plotlyLayout.value.xaxis,
        gridcolor: '#e5e7eb',
        color: '#1a1a1a',
      },
      yaxis: {
        ...plotlyLayout.value.yaxis,
        gridcolor: '#e5e7eb',
        color: '#1a1a1a',
      },
    };
  };

  /**
   * Refresh chart (reload from HTML)
   */
  const refresh = async () => {
    if (options.htmlFileUrl) {
      await loadChartFromHtml(options.htmlFileUrl);
    }
  };

  /**
   * Reset chart state
   */
  const reset = () => {
    plotlyData.value = null;
    plotlyLayout.value = null;
    error.value = null;
    loading.value = false;
  };

  // Auto-load on mount if htmlFileUrl provided
  onMounted(() => {
    if (options.htmlFileUrl) {
      loadChartFromHtml(options.htmlFileUrl);
    }
  });

  // Watch for dark mode changes
  watch(() => options.darkMode, (isDark) => {
    if (plotlyLayout.value) {
      isDark ? applyDarkModeTheme() : applyLightModeTheme();
    }
  });

  return {
    // State
    plotlyData: computed(() => plotlyData.value),
    plotlyLayout: computed(() => plotlyLayout.value),
    plotlyConfig,
    loading: computed(() => loading.value),
    error: computed(() => error.value),

    // Methods
    loadChartFromHtml,
    applyDarkModeTheme,
    applyLightModeTheme,
    refresh,
    reset,
  };
}
