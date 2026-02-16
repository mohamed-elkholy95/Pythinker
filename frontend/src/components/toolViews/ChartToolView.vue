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
      class="flex-1 h-full flex flex-col items-center justify-center bg-gradient-to-b from-[var(--background-gray-main)] to-[var(--fill-white)] dark:from-[#0d1117] dark:to-[#161b22] py-12">
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
    <div v-else class="flex-1 min-h-0 max-w-[280px] mx-auto px-3 py-3">
      <!-- Chart header -->
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-1.5">
          <BarChart3 :size="13" class="text-[var(--text-brand)]" />
          <span class="text-xs font-medium text-[var(--text-primary)] truncate">
            {{ chartContent.content?.title }}
          </span>
        </div>
        <span class="text-[10px] px-1.5 py-0.5 rounded bg-[var(--background-gray-light)] text-[var(--text-tertiary)] whitespace-nowrap">
          {{ formatChartType(chartContent.content?.chart_type) }}
        </span>
      </div>

      <!-- PNG preview image -->
      <div
        v-if="pngUrl"
        class="chart-preview-container rounded-md overflow-hidden border border-[var(--border-main)] bg-white dark:bg-[var(--code-block-bg)] mb-2 hover:border-[var(--border-brand)] transition-colors cursor-pointer"
        :class="{ 'cursor-not-allowed opacity-70': !chartContent.content?.html_file_id }"
        role="button"
        :tabindex="chartContent.content?.html_file_id ? 0 : -1"
        :aria-label="chartContent.content?.html_file_id ? `Open interactive chart: ${chartContent.content?.title}` : 'Chart preview'"
        @click="openInteractive"
        @keydown.enter="openInteractive"
        @keydown.space.prevent="openInteractive"
      >
        <img :src="pngUrl" :alt="chartContent.content?.title || 'Chart'" class="w-full h-auto object-contain" />
      </div>
      <div v-else class="chart-preview-container rounded-md overflow-hidden border border-[var(--border-main)] bg-[var(--background-gray-light)] p-6 flex items-center justify-center mb-2">
        <div class="text-[var(--text-tertiary)] text-xs">Loading...</div>
      </div>

      <!-- Chart metadata -->
      <div v-if="chartContent.content?.data_points || chartContent.content?.series_count"
        class="flex gap-3 text-[10px] text-[var(--text-tertiary)] mb-2">
        <div v-if="chartContent.content?.data_points">
          <span class="font-medium">Data:</span> {{ chartContent.content.data_points }}
        </div>
        <div v-if="chartContent.content?.series_count">
          <span class="font-medium">Series:</span> {{ chartContent.content.series_count }}
        </div>
      </div>

      <!-- Actions -->
      <div class="flex flex-col gap-1.5">
        <button v-if="chartContent.content?.html_file_id" @click="openInteractive"
          class="flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-md bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 transition-colors">
          <ExternalLink :size="12" />
          <span>Open Interactive</span>
        </button>
        <button v-if="chartContent.content?.png_file_id" @click="downloadPng"
          class="flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 text-xs font-medium hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
          <Download :size="12" />
          <span>Download PNG</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ToolContent } from '@/types/message';
import { computed } from 'vue';
import { BarChart3, ExternalLink, Download } from 'lucide-vue-next';
import { fileApi } from '@/api/file';

const props = defineProps<{
  sessionId: string;
  chartContent: ToolContent;
  live: boolean;
}>();

// Detect if chart is being created
const isCreating = computed(() => {
  return props.chartContent?.status === 'calling';
});

// Get PNG preview URL
const pngUrl = computed(() => {
  const pngFileId = props.chartContent?.content?.png_file_id;
  if (!pngFileId) return null;
  return fileApi.getFileUrl(pngFileId);
});

// Format chart type for display
const formatChartType = (type: string | undefined) => {
  if (!type) return 'Chart';
  return type
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};

// Open interactive HTML chart in new tab
const openInteractive = () => {
  const htmlFileId = props.chartContent?.content?.html_file_id;
  if (!htmlFileId) {
    console.warn('No interactive chart available');
    return;
  }
  const url = fileApi.getFileUrl(htmlFileId);
  window.open(url, '_blank');
};

// Download PNG file
const downloadPng = () => {
  const pngFileId = props.chartContent?.content?.png_file_id;
  const filename = props.chartContent?.content?.png_filename || 'chart.png';
  if (pngFileId) {
    fileApi.downloadFile(pngFileId, filename);
  }
};
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

.chart-preview-container {
  max-height: 220px;
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
</style>
