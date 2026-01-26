<template>
  <div class="w-full h-full flex flex-col bg-[#1e1e1e] text-gray-100 font-mono text-sm overflow-hidden">
    <!-- Output type indicator -->
    <div class="flex items-center gap-2 px-3 py-2 bg-[#2d2d2d] border-b border-[#404040]">
      <component :is="outputIcon" class="w-4 h-4 text-gray-400" />
      <span class="text-xs text-gray-400">{{ outputTypeLabel }}</span>
      <div v-if="isLive" class="ml-auto flex items-center gap-1.5">
        <div class="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></div>
        <span class="text-xs text-green-400">Live</span>
      </div>
    </div>

    <!-- Content area -->
    <div ref="outputRef" class="flex-1 overflow-y-auto p-3 whitespace-pre-wrap break-all">
      <!-- Shell/Code output -->
      <template v-if="contentType === 'shell' || contentType === 'code'">
        <div v-if="content" v-html="formatShellOutput(content)"></div>
        <div v-else class="text-gray-500 italic">Waiting for output...</div>
      </template>

      <!-- File content -->
      <template v-else-if="contentType === 'file'">
        <div v-if="content" class="text-gray-200">{{ content }}</div>
        <div v-else class="text-gray-500 italic">
          {{ isWriting ? 'Generating content...' : 'Reading file...' }}
        </div>
      </template>

      <!-- Browser content -->
      <template v-else-if="contentType === 'browser'">
        <div v-if="content" class="text-gray-200">{{ content }}</div>
        <div v-else class="text-gray-500 italic">Browser activity...</div>
      </template>

      <!-- Generic output -->
      <template v-else>
        <div v-if="content" class="text-gray-200">{{ content }}</div>
        <div v-else class="text-gray-500 italic">No output yet...</div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue';
import { Terminal, FileText, Globe, Code } from 'lucide-vue-next';

const props = defineProps<{
  content: string;
  contentType?: 'shell' | 'file' | 'browser' | 'code' | 'generic';
  isLive?: boolean;
  isWriting?: boolean;
  autoScroll?: boolean;
}>();

const emit = defineEmits<{
  newContent: [];
}>();

const outputRef = ref<HTMLElement>();

// Icon based on content type
const outputIcon = computed(() => {
  switch (props.contentType) {
    case 'shell':
    case 'code':
      return Terminal;
    case 'file':
      return FileText;
    case 'browser':
      return Globe;
    default:
      return Code;
  }
});

// Label based on content type
const outputTypeLabel = computed(() => {
  switch (props.contentType) {
    case 'shell':
      return 'Terminal Output';
    case 'code':
      return 'Execution Output';
    case 'file':
      return props.isWriting ? 'File Content (Writing)' : 'File Content';
    case 'browser':
      return 'Browser Content';
    default:
      return 'Output';
  }
});

// Format shell output with ANSI colors
const formatShellOutput = (output: string) => {
  return output
    .replace(/(\$|\>)\s/g, '<span class="text-green-400">$1</span> ')
    .replace(/(error|Error|ERROR)/gi, '<span class="text-red-400">$1</span>')
    .replace(/(warning|Warning|WARNING)/gi, '<span class="text-yellow-400">$1</span>')
    .replace(/(success|Success|SUCCESS|done|Done|DONE)/gi, '<span class="text-green-400">$1</span>');
};

// Auto-scroll when content changes
watch(() => props.content, async () => {
  emit('newContent');
  if (props.autoScroll !== false) {
    await nextTick();
    if (outputRef.value) {
      outputRef.value.scrollTop = outputRef.value.scrollHeight;
    }
  }
});
</script>
