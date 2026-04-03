<template>
    <div class="flex flex-col items-center justify-center flex-1 w-full min-h-0">
        <iframe
            v-if="pdfUrl"
            :src="pdfUrl"
            class="w-full h-full border-0 rounded-md"
            :title="file.filename"
        />
    </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { getFileUrl } from '../../api/file';
import type { FileInfo } from '../../api/file';

const props = defineProps<{
    file: FileInfo;
}>();

// Use direct backend URL (serves with Content-Disposition: inline for PDFs)
const pdfUrl = computed(() => {
    if (!props.file?.file_id) return '';
    return getFileUrl(props.file.file_id);
});
</script>
