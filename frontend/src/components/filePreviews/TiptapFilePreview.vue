<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import type { FileInfo } from '@/api/file';
import { downloadFile } from '@/api/file';
import TiptapReportEditor from '@/components/report/TiptapReportEditor.vue';
import { prepareMarkdownForViewer, preparePlainTextForViewer } from '@/components/report/reportContentNormalizer';

const props = defineProps<{
  file: FileInfo;
}>();

const fileContent = ref('');
const isLoading = ref(true);

const isMarkdown = computed(() => {
  const ext = props.file.filename.split('.').pop()?.toLowerCase();
  return ext === 'md' || ext === 'markdown';
});

const viewerContent = computed(() => {
  if (!fileContent.value) return '';
  if (isMarkdown.value) {
    return prepareMarkdownForViewer(fileContent.value, {
      stripMainTitle: false,
      collapseDuplicateBlocks: true,
    });
  }
  return preparePlainTextForViewer(fileContent.value);
});

const loadFileContent = async (fileId: string) => {
  if (!fileId) return;

  isLoading.value = true;
  try {
    const blob = await downloadFile(fileId);
    fileContent.value = await blob.text();
  } catch (error) {
    fileContent.value = '(Failed to load file content)';
    console.error('Failed to load file:', error);
  } finally {
    isLoading.value = false;
  }
};

watch(() => props.file.file_id, loadFileContent, { immediate: true });
</script>

<template>
  <div class="tiptap-file-preview h-full bg-[var(--background-white-main)]">
    <div v-if="isLoading" class="flex items-center justify-center h-full">
      <div class="text-[var(--text-tertiary)]">Loading...</div>
    </div>
    <TiptapReportEditor
      v-else
      :content="viewerContent"
      :compact="false"
      :editable="false"
      class="h-full"
    />
  </div>
</template>
