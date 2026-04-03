<template>
  <div class="flex flex-col items-center justify-center flex-1 w-full min-h-0 gap-3">
    <a
      v-if="downloadUrl"
      :href="downloadUrl"
      class="text-xs text-blue-600 underline underline-offset-2"
      target="_blank"
      rel="noreferrer"
    >
      Open PDF
    </a>

    <p v-if="errorMessage" class="text-sm text-red-600">
      Unable to render PDF preview: {{ errorMessage }}
    </p>

    <template v-else-if="downloadUrl">
      <p v-if="isRendered" class="text-sm text-[var(--text-secondary)]">
        Rendered with PDF.js
      </p>
      <canvas
        ref="canvasRef"
        class="max-w-full rounded-md border border-[var(--border-light)]"
      />
      <p v-if="!isRendered" class="text-sm text-[var(--text-tertiary)]">
        Loading PDF preview...
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch, computed, nextTick } from 'vue';
import { downloadFile, getFileUrl } from '../../api/file';
import type { FileInfo } from '../../api/file';
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist/build/pdf.mjs';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

const props = defineProps<{
  file: FileInfo;
}>();

const canvasRef = ref<HTMLCanvasElement | null>(null);
const isRendered = ref(false);
const errorMessage = ref('');

const downloadUrl = computed(() => {
  if (!props.file?.file_id) return '';
  return getFileUrl(props.file.file_id);
});

const renderPreview = async (): Promise<void> => {
  const fileId = props.file?.file_id;
  if (!fileId) return;

  errorMessage.value = '';
  isRendered.value = false;

  try {
    await nextTick();
    const blob = await downloadFile(fileId);
    const arrayBuffer = await blob.arrayBuffer();
    const pdfDocument = await getDocument({ data: arrayBuffer }).promise;
    const page = await pdfDocument.getPage(1);
    const canvas = canvasRef.value;
    if (!canvas) {
      throw new Error('canvas unavailable');
    }

    const viewport = page.getViewport({ scale: 1 });
    canvas.width = viewport.width;
    canvas.height = viewport.height;

    const context = canvas.getContext('2d');
    if (!context) {
      throw new Error('canvas context unavailable');
    }

    await page.render({ canvasContext: context, viewport }).promise;
    page.cleanup?.();
    isRendered.value = true;
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error';
  }
};

onMounted(() => {
  void renderPreview();
});

watch(
  () => props.file?.file_id,
  () => {
    void renderPreview();
  }
);
</script>
