<template>
  <!-- Inline message tools (rendered as plain text) -->
  <p v-if="isInlineMessageTool && tool.args?.text" class="text-[var(--text-secondary)] text-[14px] overflow-hidden text-ellipsis whitespace-pre-line">
    {{ tool.args.text }}
  </p>
  <!-- Standard tool display (rendered as interactive chip - Manus-style) -->
  <div v-else-if="toolInfo" class="flex items-center group gap-2 max-w-full">
    <div
      @click="handleClick"
      class="tool-chip rounded-full items-center gap-[7px] px-[10px] py-[4px] inline-flex max-w-full clickable"
      :class="shouldShimmer ? 'tool-shimmer' : 'tool-idle'"
    >
      <div class="tool-icon-container">
        <img
          v-if="toolInfo.faviconUrl && !faviconError"
          :src="toolInfo.faviconUrl"
          alt=""
          class="tool-favicon"
          @error="faviconError = true"
        />
        <component v-else :is="toolInfo.icon" :size="11" class="text-[var(--text-secondary)]" />
      </div>
      <div class="text-[12px] font-medium text-[var(--text-secondary)] max-w-[100%] text-ellipsis overflow-hidden whitespace-nowrap"
        :title="toolInfo.description">
        {{ toolInfo.description }}
      </div>
      <Loader2 v-if="isRunning" :size="10" class="tool-spinner" />
    </div>
    <div class="transition text-[11px] text-[var(--text-tertiary)] invisible group-hover:visible">
      {{ relativeTime(tool.timestamp) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, ref, watch } from "vue";
import { Loader2 } from "lucide-vue-next";
import { ToolContent } from "../types/message";
import { useToolInfo } from "../composables/useTool";
import { useRelativeTime } from "../composables/useTime";

/**
 * Configuration: Tools that should be rendered as inline text messages
 * instead of the standard interactive chip display.
 * Add tool names here if they should show their text content directly.
 */
const INLINE_MESSAGE_TOOLS: ReadonlySet<string> = new Set([
  'message',
  'user_message',
  'system_note',
]);

const props = defineProps<{
  tool: ToolContent;
  /** Whether this tool is the actively running tool (shows shimmer effect) */
  isActive?: boolean;
  /** Keep shimmer on the last task while parent step is still running */
  isTaskRunning?: boolean;
}>();

const emit = defineEmits<{
  (e: "click"): void;
}>();

const { relativeTime } = useRelativeTime();
const { toolInfo } = useToolInfo(toRef(() => props.tool));

const faviconError = ref(false);

const isRunning = computed(() => props.tool.status === 'calling');
const shouldShimmer = computed(
  () => !!props.isActive && (isRunning.value || !!props.isTaskRunning)
);

// Reset favicon error when tool changes
watch(() => props.tool.tool_call_id, () => {
  faviconError.value = false;
});

/** Check if this tool should be rendered as an inline message */
const isInlineMessageTool = computed(() => {
  return INLINE_MESSAGE_TOOLS.has(props.tool.name);
});

const handleClick = () => {
  emit("click");
};
</script>

<style scoped>
.tool-shimmer {
  position: relative;
  overflow: hidden;
  background: #e7ebf1;
  border: 1px solid #cfd6e0;
}

.tool-shimmer::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.4) 50%,
    transparent 100%
  );
  animation: shimmer-sweep 1.2s ease-in-out infinite;
}

@keyframes shimmer-sweep {
  0% {
    left: -100%;
  }
  100% {
    left: 100%;
  }
}

.tool-spinner {
  color: #7a8698;
  flex-shrink: 0;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>

<style>
/* Dark mode support - needs to be unscoped to work with :root selector */
:root.dark .tool-shimmer {
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.24);
}

:root.dark .tool-shimmer::before {
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.2) 50%,
    transparent 100%
  );
}

.tool-chip {
  border: 1px solid #d7dde6;
  background: #eceff3;
  transition: all 0.15s ease;
}

.tool-chip:hover {
  border-color: #c8d0db;
  background: #e5e9ef;
}

.tool-idle {
  background: #eceff3;
}

.tool-icon-container {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #e2e6ed;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1px solid #d1d8e2;
  overflow: hidden;
}

.tool-favicon {
  width: 11px;
  height: 11px;
  object-fit: contain;
}
</style>
