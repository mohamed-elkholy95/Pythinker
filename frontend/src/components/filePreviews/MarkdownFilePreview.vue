<template>
    <div class="markdown-preview-scroll relative overflow-y-scroll h-full p-5">
        <div class="relative w-full max-w-[768px] mx-auto">
            <div class="prose prose-gray max-w-none dark:prose-invert"
                 v-html="renderedContent">
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import type { FileInfo } from '../../api/file';
import { downloadFile } from '../../api/file';

const content = ref('');

const props = defineProps<{
    file: FileInfo;
}>();

// Configure marked options using modern API
marked.use({
    breaks: true,
    gfm: true,
});

// Compute rendered HTML content
const renderedContent = computed(() => {
    if (!content.value) return '';
    try {
        const html = marked.parse(content.value);
        return DOMPurify.sanitize(html as string);
    } catch {
        return `<pre class="text-sm text-red-500">Failed to render markdown content</pre>`;
    }
});

watch(() => props.file.file_id, async (fileId) => {
    if (!fileId) return;
    try {
        const blob = await downloadFile(fileId);
        const text = await blob.text();
        content.value = text;
    } catch {
        content.value = '(Failed to load file content)';
    }
}, { immediate: true });
</script>

<style scoped>
.markdown-preview-scroll::-webkit-scrollbar {
    width: 6px;
}

.markdown-preview-scroll::-webkit-scrollbar-track {
    background: transparent;
}

.markdown-preview-scroll::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.2);
    border-radius: 3px;
}

.markdown-preview-scroll::-webkit-scrollbar-thumb:hover {
    background: rgba(0, 0, 0, 0.3);
}

/* Firefox */
.markdown-preview-scroll {
    scrollbar-width: thin;
    scrollbar-color: rgba(0, 0, 0, 0.2) transparent;
}
</style>