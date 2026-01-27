<template>
  <div
    class="h-[36px] flex items-center px-3 w-full bg-[var(--background-gray-main)] border-b border-[var(--border-main)] rounded-t-[12px] shadow-[inset_0px_1px_0px_0px_#FFFFFF] dark:shadow-[inset_0px_1px_0px_0px_#FFFFFF30]"
  >
    <div class="flex-1 min-w-0 flex items-center gap-2">
      <div class="text-[var(--text-tertiary)] text-xs font-medium whitespace-nowrap">
        Editor
      </div>
      <div class="text-[var(--text-tertiary)] text-xs">|</div>
      <div class="min-w-0 truncate text-[var(--text-tertiary)] text-xs font-medium">
        Editing file {{ fileDisplayPath }}
      </div>
      <!-- Writing indicator when file is being generated -->
      <div v-if="isWriting" class="flex items-center gap-1.5 ml-2">
        <div class="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></div>
        <span class="text-xs text-blue-500 font-medium">Writing</span>
      </div>
    </div>
    <div class="flex items-center gap-1 bg-[var(--fill-tsp-gray-main)] rounded-lg p-0.5">
      <button
        @click="viewMode = 'diff'"
        class="px-2 py-1 text-xs rounded-md transition-colors"
        :class="viewMode === 'diff' ? 'bg-[var(--background-white-main)] text-[var(--text-primary)] shadow-sm' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'"
      >
        Diff
      </button>
      <button
        @click="viewMode = 'original'"
        class="px-2 py-1 text-xs rounded-md transition-colors"
        :class="viewMode === 'original' ? 'bg-[var(--background-white-main)] text-[var(--text-primary)] shadow-sm' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'"
      >
        Original
      </button>
      <button
        @click="viewMode = 'modified'"
        class="px-2 py-1 text-xs rounded-md transition-colors"
        :class="viewMode === 'modified' ? 'bg-[var(--background-white-main)] text-[var(--text-primary)] shadow-sm' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'"
      >
        Modified
      </button>
    </div>
  </div>
  <div class="flex-1 min-h-0 w-full overflow-y-auto" :class="isWriting ? 'writing-active' : ''">
    <div
      dir="ltr"
      data-orientation="horizontal"
      class="flex flex-col min-h-0 h-full relative"
    >
      <div
        data-state="active"
        data-orientation="horizontal"
        role="tabpanel"
        id="radix-:r2ke:-content-/home/ubuntu/llm_papers/todo.md"
        tabindex="0"
        class="focus-visible:outline-none data-[state=inactive]:hidden flex-1 min-h-0 h-full text-sm flex flex-col py-0 outline-none overflow-auto"
      >
        <section
          style="
            display: flex;
            position: relative;
            text-align: initial;
            width: 100%;
            height: 100%;
          "
        >
          <MonacoEditor
            :value="displayContent"
            :filename="fileName"
            :read-only="true"
            theme="vs"
            :line-numbers="'off'"
            :word-wrap="'on'"
            :minimap="false"
            :scroll-beyond-last-line="false"
            :automatic-layout="true"
          />
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed, watch, onUnmounted } from "vue";
import { ToolContent } from "@/types/message";
import { viewFile } from "@/api/agent";
import MonacoEditor from "@/components/ui/MonacoEditor.vue";
//import { showErrorToast } from "../utils/toast";
//import { useI18n } from "vue-i18n";

//const { t } = useI18n();

const props = defineProps<{
  sessionId: string;
  toolContent: ToolContent;
  live: boolean;
}>();

defineExpose({
  loadContent: () => {
    loadFileContent();
  },
});

const fileContent = ref("");
const originalContent = ref("");
const viewMode = ref<'modified' | 'original' | 'diff'>('modified');
const refreshTimer = ref<number | null>(null);

const filePath = computed(() => {
  if (props.toolContent && props.toolContent.args.file) {
    return props.toolContent.args.file;
  }
  return "";
});

const fileName = computed(() => {
  if (filePath.value) {
    return filePath.value.split("/").pop() || "";
  }
  return "";
});

const fileDisplayPath = computed(() => {
  if (!filePath.value) return fileName.value || '';
  return filePath.value.replace(/^\/home\/ubuntu\//, '');
});

// Check if file is currently being written (streaming preview)
const isWriting = computed(() => {
  return props.toolContent?.status === "calling" &&
         props.toolContent?.function === "file_write";
});

const getToolContentText = () => {
  const content = props.toolContent?.content;
  if (!content) return "";
  if (typeof content === "string") return content;
  if (typeof (content as { content?: unknown }).content === "string") {
    return (content as { content: string }).content;
  }
  return "";
};

const displayContent = computed(() => {
  if (viewMode.value === 'original') {
    return originalContent.value || fileContent.value;
  }
  if (viewMode.value === 'diff') {
    return buildSimpleDiff(originalContent.value, fileContent.value);
  }
  return fileContent.value;
});

// Load file content
const loadFileContent = async () => {
  console.log("loadFileContent", props.live, filePath.value, props.toolContent.content);

  // During file_write (status: calling), show the content being written (streaming preview)
  if (isWriting.value) {
    // Priority: tool_content.content (from backend) > args.content (fallback)
    const argContent = typeof props.toolContent.args?.content === "string"
      ? props.toolContent.args?.content
      : "";
    const streamingContent = getToolContentText() || argContent;
    if (fileContent.value && fileContent.value !== streamingContent) {
      originalContent.value = fileContent.value;
    }
    fileContent.value = streamingContent;
    return;
  }

  if (!props.live) {
    const nextContent = getToolContentText();
    if (fileContent.value && fileContent.value !== nextContent) {
      originalContent.value = fileContent.value;
    }
    fileContent.value = nextContent;
    return;
  }

  if (!filePath.value) return;

  try {
    const response = await viewFile(props.sessionId, filePath.value);
    const nextContent = response.content;
    if (fileContent.value && fileContent.value !== nextContent) {
      originalContent.value = fileContent.value;
    }
    fileContent.value = nextContent;
  } catch (error) {
    console.error("Failed to load file content:", error);
  }
};

const buildSimpleDiff = (original: string, modified: string): string => {
  if (!original && !modified) return "";
  if (!original) return `+ ${modified}`;
  if (!modified) return `- ${original}`;

  const originalLines = original.split('\n');
  const modifiedLines = modified.split('\n');
  const maxLines = Math.max(originalLines.length, modifiedLines.length);
  const out: string[] = [];

  for (let i = 0; i < maxLines; i += 1) {
    const a = originalLines[i];
    const b = modifiedLines[i];
    if (a === b) {
      out.push(`  ${a ?? ''}`);
    } else {
      if (a !== undefined) out.push(`- ${a}`);
      if (b !== undefined) out.push(`+ ${b}`);
    }
  }

  return out.join('\n');
};

// Start auto-refresh timer
const startAutoRefresh = () => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value);
  }
  
  if (props.live && filePath.value) {
    refreshTimer.value = setInterval(() => {
      loadFileContent();
    }, 5000);
  }
};

// Stop auto-refresh timer
const stopAutoRefresh = () => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value);
    refreshTimer.value = null;
  }
};

// Watch for filename changes to reload content
watch(filePath, (newVal: string) => {
  if (newVal) {
    loadFileContent();
    startAutoRefresh();
  } else {
    stopAutoRefresh();
  }
});

watch(() => props.toolContent, () => {
  loadFileContent();
});

watch(() => props.toolContent.timestamp, () => {
  loadFileContent();
});

// Watch for status changes (calling → called transition)
watch(() => props.toolContent.status, () => {
  loadFileContent();
});

// Watch for live prop changes
watch(() => props.live, (live: boolean) => {
  if (live) {
    loadFileContent();
    startAutoRefresh();
  } else {
    stopAutoRefresh();
  }
});

// Load content when component is mounted
onMounted(() => {
  loadFileContent();
  startAutoRefresh();
});

onUnmounted(() => {
  stopAutoRefresh();
});
</script>

<style scoped>
/* Subtle pulsing effect when file is being written */
.writing-active {
  position: relative;
}

.writing-active::after {
  content: '';
  position: absolute;
  inset: 0;
  border: 2px solid transparent;
  border-radius: 0 0 12px 12px;
  pointer-events: none;
  animation: writing-pulse 2s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

@keyframes writing-pulse {
  0%, 100% {
    border-color: rgba(156, 125, 255, 0.12);
  }
  50% {
    border-color: rgba(156, 125, 255, 0.35);
  }
}
</style>
