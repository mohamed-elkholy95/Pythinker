<template>
  <div class="html-file-preview flex flex-1 min-h-0 w-full">
    <div
      v-if="isLoading"
      class="flex flex-1 items-center justify-center text-sm text-[var(--text-tertiary)]"
    >
      Loading chart preview...
    </div>
    <div
      v-else-if="loadError"
      class="flex flex-1 items-center justify-center px-6 text-center text-sm text-[var(--text-tertiary)]"
    >
      {{ loadError }}
    </div>
    <HtmlPreviewView v-else :content="htmlContent" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import type { FileInfo } from '../../api/file';
import { getFileDownloadUrl } from '../../api/file';
import HtmlPreviewView from '@/components/toolViews/HtmlPreviewView.vue';

const props = defineProps<{
  file: FileInfo;
}>();

const htmlContent = ref('');
const isLoading = ref(false);
const loadError = ref<string | null>(null);

const addBaseHref = (html: string, baseHref: string): string => {
  const baseTag = `<base href="${baseHref}">`;

  if (/<base\s/i.test(html)) return html;
  if (/<head(\s[^>]*)?>/i.test(html)) {
    return html.replace(/<head(\s[^>]*)?>/i, (match) => `${match}${baseTag}`);
  }

  return `${baseTag}${html}`;
};

watch(
  () => props.file,
  async (file, _previousFile, onCleanup) => {
    const controller = new AbortController();
    let isActive = true;

    onCleanup(() => {
      isActive = false;
      controller.abort();
    });

    isLoading.value = true;
    loadError.value = null;
    htmlContent.value = '';

    try {
      const url = await getFileDownloadUrl(file);
      if (!isActive) return;

      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const html = await response.text();
      if (!isActive) return;

      htmlContent.value = addBaseHref(html, url);
    } catch (error) {
      const isAbortError = error instanceof Error && error.name === 'AbortError';
      if (!isActive || isAbortError) return;
      loadError.value = 'Failed to load chart preview.';
    } finally {
      if (isActive) {
        isLoading.value = false;
      }
    }
  },
  { immediate: true }
);
</script>
