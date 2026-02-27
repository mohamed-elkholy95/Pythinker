<template>
      <div class="bg-[var(--background-gray-main)] overflow-hidden shadow-[0px_0px_8px_0px_rgba(0,0,0,0.02)] ltr:border-l rtl:border-r border-black/8 dark:border-[var(--border-light)] flex flex-col h-full w-full">
        <div
          class="px-4 pt-2 pb-4 gap-4 flex items-center justify-between flex-shrink-0 border-b border-[var(--border-main)] flex-col-reverse md:flex-row md:py-4">
          <div class="flex justify-between self-stretch flex-1 truncate">
            <div
              class="flex flex-row gap-1 items-center text-[var(--text-secondary)] font-medium truncate [&amp;_svg]:flex-shrink-0">
              <a href="" class="p-1 flex-shrink-0 cursor-default" target="_blank">
                <div class="relative flex items-center justify-center">
                  <component :is="fileType.icon" />
                </div>
              </a>
              <div class="truncate flex flex-col"><span class="truncate" :title="file.filename">{{ file.filename }}</span></div>
            </div>
          </div>
          <div class="flex items-center justify-between gap-2 w-full py-3 md:w-auto md:py-0 select-none">
            <div class="flex items-center gap-2">
              <!-- Phase 5: Open interactive chart button -->
              <div
                v-if="fileType.isInteractiveChart"
                @click="openInteractiveChart"
                class="flex h-7 px-3 items-center justify-center cursor-pointer hover:bg-[var(--fill-tsp-gray-main)] rounded-md gap-1"
                :title="'Open Interactive Chart'"
              >
                <svg class="size-[16px] text-[var(--icon-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
                <span class="text-xs font-medium text-[var(--text-secondary)]">Open Chart</span>
              </div>
              <button type="button" @click="download"
                class="flex h-7 w-7 items-center justify-center cursor-pointer hover:bg-[var(--fill-tsp-gray-main)] rounded-md"
                aria-label="Download file">
                <Download class="text-[var(--icon-secondary)] size-[18px]" />
              </button>
            </div>
            <div class="flex items-center gap-2">
              <div @click="hide"
                class="flex h-7 w-7 items-center justify-center cursor-pointer hover:bg-[var(--fill-tsp-gray-main)] rounded-md">
                <X class="size-5 text-[var(--icon-secondary)]" />
              </div>
            </div>
          </div>
        </div>
        <component :is="fileType.preview" :file="file" />
      </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Download, X } from 'lucide-vue-next';
import type { FileInfo } from '../api/file';
import { getFileDownloadUrl } from '../api/file';
import { getFileType } from '../utils/fileType';

const props = defineProps<{
  file: FileInfo;
}>();

const emit = defineEmits<{
  (e: 'hide'): void
}>();

const hide = () => {
  emit('hide');
};

const fileType = computed(() => {
  // Phase 5: Pass metadata to detect interactive charts
  return getFileType(props.file.filename, props.file.metadata);
});

const download = async () => {
  const url = await getFileDownloadUrl(props.file);
  window.open(url, '_blank');
};

// Phase 5: Open interactive chart in new tab
const openInteractiveChart = async () => {
  const url = await getFileDownloadUrl(props.file);
  window.open(url, '_blank');
};
</script>
