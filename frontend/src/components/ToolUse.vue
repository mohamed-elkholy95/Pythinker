<template>
  <!-- Inline message tools (rendered as plain text) -->
  <p v-if="isInlineMessageTool && tool.args?.text" class="inline-message-text whitespace-pre-wrap break-words">
    {{ tool.args.text }}
  </p>
  <!-- Standard tool display (rendered as interactive chip - Manus-style) -->
  <div v-else-if="toolInfo" class="flex w-full items-start group gap-1.5 max-w-full">
    <div class="flex-1 min-w-0">
      <div
        @click="handleClick"
        class="tool-chip rounded-full items-center gap-[6px] px-[10px] py-[5px] inline-flex max-w-full clickable"
        :class="shouldShimmer ? 'tool-shimmer' : 'tool-idle'"
      >
        <span class="tool-icon-shell">
          <img
            v-if="toolInfo.faviconUrl && !faviconError"
            :src="toolInfo.faviconUrl"
            alt=""
            class="tool-favicon"
            @error="faviconError = true"
          />
          <component v-else :is="toolInfo.icon" :size="13" class="tool-icon-glyph" />
        </span>
        <div class="tool-chip-text max-w-[100%] min-w-0">
          {{ toolInfo.description }}
        </div>
        <Loader2 v-if="isRunning" :size="9" class="tool-spinner" />
      </div>
    </div>
    <div class="hidden sm:block ml-auto pl-2 text-right whitespace-nowrap flex-shrink-0 transition text-[11px] text-[var(--text-tertiary)] sm:invisible sm:group-hover:visible">
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
.inline-message-text {
  color: var(--text-secondary);
  font-size: 14.5px;
  line-height: 1.55;
  font-weight: 400;
}

.tool-shimmer {
  position: relative;
  overflow: hidden;
  background: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-main);
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
    rgba(255, 255, 255, 0.45) 50%,
    transparent 100%
  );
  animation: shimmer-sweep 1.4s ease-in-out infinite;
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
  color: var(--icon-tertiary);
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
  background: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-main);
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
  border: 1px solid var(--border-main);
  background: var(--fill-tsp-gray-main);
  padding: 6px 12px;
  gap: 7px;
  transition: all 0.15s ease;
}

.tool-chip:hover {
  border-color: var(--border-dark);
  background: var(--fill-tsp-white-dark);
}

.tool-idle {
  background: var(--fill-tsp-gray-main);
}

.tool-favicon {
  width: 12px;
  height: 12px;
  object-fit: contain;
  flex-shrink: 0;
  display: block;
}

.tool-icon-shell {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  border: 1px solid var(--border-main);
  background: var(--background-white-main);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.tool-icon-glyph {
  color: var(--icon-secondary);
  flex-shrink: 0;
  display: block;
}

.tool-chip-text {
  font-size: 13.5px;
  line-height: 1.38;
  color: var(--text-secondary);
  font-weight: 450;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

</style>
