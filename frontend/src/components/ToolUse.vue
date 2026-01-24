<template>
  <p v-if="tool.name === 'message' && tool.args?.text" class="text-[var(--text-secondary)] text-[14px] overflow-hidden text-ellipsis whitespace-pre-line">
    {{ tool.args.text }}
  </p>
  <div v-else-if="toolInfo" class="flex items-center group gap-2">
    <div class="flex-1 min-w-0">
      <div @click="handleClick"
        class="rounded-[20px] items-center gap-[6px] px-[10px] py-[4px] inline-flex max-w-full clickable hover:bg-[var(--fill-tsp-gray-dark)] dark:hover:bg-white/[0.02]"
        :class="tool.status === 'calling' ? 'tool-shimmer' : 'bg-[var(--fill-tsp-gray-main)]'">
        <div class="w-[16px] h-[16px] inline-flex items-center justify-center text-[var(--text-secondary)]">
          <component :is="toolInfo.icon" :size="16" />
        </div>
        <div class="flex-1 h-full min-w-0 flex">
          <div
            class="inline-flex items-center h-full text-[13px] text-[var(--text-secondary)] max-w-[100%]">
            <div class="max-w-[100%] text-ellipsis overflow-hidden whitespace-nowrap"
              :title="`${toolInfo.function} ${toolInfo.functionArg}`">
              <span class="font-medium">{{ toolInfo.function }}</span>
              <span v-if="toolInfo.functionArg" class="ml-1 font-mono text-[var(--text-tertiary)]">{{ toolInfo.functionArg }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="float-right transition text-[12px] text-[var(--text-tertiary)] invisible group-hover:visible">
      {{ relativeTime(tool.timestamp) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ToolContent } from "../types/message";
import { useToolInfo } from "../composables/useTool";
import { useRelativeTime } from "../composables/useTime";

const props = defineProps<{
  tool: ToolContent;
}>();

const emit = defineEmits<{
  (e: "click"): void;
}>();

const { relativeTime } = useRelativeTime();
const { toolInfo } = useToolInfo(ref(props.tool));

const handleClick = () => {
  emit("click");
};
</script>

<style scoped>
.tool-shimmer {
  background: linear-gradient(
    90deg,
    var(--fill-tsp-gray-main) 0%,
    var(--fill-tsp-gray-light, rgba(0, 0, 0, 0.04)) 25%,
    var(--fill-tsp-gray-main) 50%,
    var(--fill-tsp-gray-light, rgba(0, 0, 0, 0.04)) 75%,
    var(--fill-tsp-gray-main) 100%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
</style>

<style>
/* Dark mode support - needs to be unscoped to work with :root selector */
:root.dark .tool-shimmer {
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.05) 0%,
    rgba(255, 255, 255, 0.1) 25%,
    rgba(255, 255, 255, 0.05) 50%,
    rgba(255, 255, 255, 0.1) 75%,
    rgba(255, 255, 255, 0.05) 100%
  );
  background-size: 200% 100%;
}
</style>
