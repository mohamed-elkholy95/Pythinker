<template>
  <!-- Inline message tools (rendered as plain text) -->
  <p v-if="isInlineMessageTool && tool.args?.text" class="text-[var(--text-secondary)] text-[14px] overflow-hidden text-ellipsis whitespace-pre-line">
    {{ tool.args.text }}
  </p>
  <!-- Standard tool display (rendered as interactive chip - Manus-style) -->
  <div v-else-if="toolInfo" class="flex items-center group gap-2">
    <div class="flex-1 min-w-0">
      <div @click="handleClick"
        class="tool-chip rounded-[20px] items-center gap-[8px] px-[12px] py-[6px] inline-flex max-w-full clickable"
        :class="props.isActive && tool.status === 'calling' ? 'tool-shimmer' : 'tool-idle'">
        <!-- Icon: favicon for URL-based tools, or tool icon -->
        <div class="tool-icon-container">
          <img
            v-if="toolInfo.faviconUrl && !faviconError"
            :src="toolInfo.faviconUrl"
            alt=""
            class="tool-favicon"
            @error="faviconError = true"
          />
          <component v-else :is="toolInfo.icon" :size="13" class="text-[var(--text-secondary)]" />
        </div>
        <!-- Human-readable description -->
        <div class="flex-1 h-full min-w-0">
          <div class="text-[13px] text-[var(--text-primary)] max-w-[100%] text-ellipsis overflow-hidden whitespace-nowrap"
            :title="toolInfo.description">
            {{ toolInfo.description }}
          </div>
        </div>
        <!-- Status indicator: spinner when running, check when done -->
        <Loader2 v-if="isRunning" :size="13" class="tool-spinner" />
        <Check v-else :size="13" class="tool-check" />
      </div>
    </div>
    <div class="transition text-[12px] text-[var(--text-tertiary)] invisible group-hover:visible">
      {{ relativeTime(tool.timestamp) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, ref, watch } from "vue";
import { Loader2, Check } from "lucide-vue-next";
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
}>();

const emit = defineEmits<{
  (e: "click"): void;
}>();

const { relativeTime } = useRelativeTime();
const { toolInfo } = useToolInfo(toRef(() => props.tool));

const faviconError = ref(false);

const isRunning = computed(() => props.tool.status === 'calling');

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
  background: rgba(59, 130, 246, 0.12);
  border: 1px solid rgba(59, 130, 246, 0.3);
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
  color: var(--text-brand);
  flex-shrink: 0;
  animation: spin 1s linear infinite;
}

.tool-check {
  color: var(--text-tertiary);
  flex-shrink: 0;
  opacity: 0.5;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>

<style>
/* Dark mode support - needs to be unscoped to work with :root selector */
:root.dark .tool-shimmer {
  background: rgba(59, 130, 246, 0.18);
  border: 1px solid rgba(59, 130, 246, 0.45);
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
  border: 1px solid var(--border-light);
  background: var(--background-white-main);
  transition: all 0.15s ease;
}

.tool-chip:hover {
  border-color: var(--border-main);
  background: var(--fill-tsp-gray-main);
}

.tool-idle {
  background: var(--background-white-main);
}

.tool-icon-container {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--fill-tsp-gray-main);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1px solid var(--border-light);
  overflow: hidden;
}

.tool-favicon {
  width: 14px;
  height: 14px;
  object-fit: contain;
}
</style>
