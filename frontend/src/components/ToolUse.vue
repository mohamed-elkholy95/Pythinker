<template>
  <!-- Inline message tools (rendered as plain text) -->
  <p v-if="isInlineMessageTool && tool.args?.text" class="inline-message-text whitespace-pre-wrap break-words">
    {{ tool.args.text }}
  </p>
  <!-- Fast search with inline results -->
  <div v-else-if="isFastSearchWithResults" class="fast-search-tool-wrapper flex w-full flex-col gap-0 max-w-full">
    <div class="flex w-full items-start group gap-1.5">
      <div class="flex-1 min-w-0">
        <div
          @click="handleClick"
          class="tool-chip rounded-full items-center gap-[6px] px-[10px] py-[5px] inline-flex max-w-full clickable"
          :class="shouldShimmer ? 'tool-shimmer' : 'tool-idle'"
        >
          <span class="tool-icon-shell">
            <img
              v-if="toolInfo?.faviconUrl && !faviconError"
              :src="toolInfo.faviconUrl"
              alt=""
              class="tool-favicon"
              @error="faviconError = true"
            />
            <component v-else-if="toolInfo?.icon" :is="toolInfo.icon" :size="13" class="tool-icon-glyph" />
          </span>
          <div class="tool-chip-text max-w-[100%] min-w-0">
            {{ toolInfo?.description ?? t('Search') }}
          </div>
          <Loader2 v-if="isRunning" :size="9" class="tool-spinner" />
        </div>
      </div>
      <div class="hidden sm:block ml-auto pl-2 text-right whitespace-nowrap flex-shrink-0 transition text-[11px] text-[var(--text-tertiary)] sm:invisible sm:group-hover:visible">
        {{ relativeTime(tool.timestamp) }}
      </div>
    </div>
    <FastSearchInline
      :results="searchResults"
      :query="searchQuery"
      :is-searching="isRunning"
      :explicit-empty="searchResults.length === 0 && !isRunning"
      @browse-url="handleBrowseUrl"
    />
  </div>
  <!-- Standard tool display (rendered as interactive chip - Pythinker-style) -->
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
import { useI18n } from "vue-i18n";
import { ToolContent } from "../types/message";
import type { SearchToolContent } from "../types/toolContent";
import type { SearchResultItem } from "../types/search";
import { useToolInfo } from "../composables/useTool";
import { useRelativeTime } from "../composables/useTime";
import FastSearchInline from "./FastSearchInline.vue";

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

/** Fast search tools only – show inline results. Excludes wide_research (deep research). */
const FAST_SEARCH_FUNCTIONS = new Set(['info_search_web', 'web_search']);

function isFastSearchTool(tool: ToolContent): boolean {
  const fn = (tool.function || '').toLowerCase();
  return FAST_SEARCH_FUNCTIONS.has(fn);
}

function getSearchToolContent(tool: ToolContent): SearchToolContent | null {
  const content = tool.content;
  if (!content || typeof content !== 'object' || !('results' in content)) return null;
  const sc = content as SearchToolContent;
  return Array.isArray(sc.results) ? sc : null;
}

const props = defineProps<{
  tool: ToolContent;
  /** Whether this tool is the actively running tool (shows shimmer effect) */
  isActive?: boolean;
  /** Keep shimmer on the last task while parent step is still running */
  isTaskRunning?: boolean;
  /** Show fast search inline UI (header, tabs). False when tool is inside agent research phase. */
  showFastSearchInline?: boolean;
}>();

const emit = defineEmits<{
  (e: "click"): void;
  (e: "browseUrl", url: string): void;
}>();

const { t } = useI18n();
const { relativeTime } = useRelativeTime();
const { toolInfo } = useToolInfo(toRef(() => props.tool));

const faviconError = ref(false);

const isRunning = computed(() => props.tool.status === 'calling');
const shouldShimmer = computed(
  () => !!props.isActive && (isRunning.value || !!props.isTaskRunning)
);

const searchToolContent = computed(() => getSearchToolContent(props.tool));
const isFastSearchWithResults = computed(() => {
  // Only show fast search inline UI (header, tabs) for fast-search answer, not agent research
  if (props.showFastSearchInline === false) return false;
  if (!isFastSearchTool(props.tool)) return false;
  if (isRunning.value) return true; // Show fast-search during search (loading/skeleton)
  const sc = searchToolContent.value;
  if (sc === null) return false;
  // Show inline layout only when we have results; hide for 0 results
  return (sc.results?.length ?? 0) > 0;
});

const searchResults = computed((): SearchResultItem[] => {
  const sc = searchToolContent.value;
  if (!sc?.results) return [];
  return sc.results.map((r) => ({
    title: r.title ?? 'No title',
    link: r.link ?? '',
    snippet: r.snippet ?? '',
  }));
});

const searchQuery = computed(() => {
  const sc = searchToolContent.value;
  if (sc?.query) return String(sc.query);
  return props.tool.args?.query ?? props.tool.args?.q ?? '';
});

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

const handleBrowseUrl = (url: string) => {
  emit("browseUrl", url);
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
  background: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-main);
}

/* Text-only shimmer effect (matches ThinkingIndicator design) */
.tool-shimmer .tool-chip-text {
  background: linear-gradient(
    120deg,
    #3a3a3a 0%,
    #3a3a3a 38%,
    #c6894b 48%,
    #d8a26f 52%,
    #3a3a3a 62%,
    #3a3a3a 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: text-shimmer 2.5s ease-in-out infinite;
}

/* Dark mode text shimmer */
:deep(.dark) .tool-shimmer .tool-chip-text,
.dark .tool-shimmer .tool-chip-text {
  background: linear-gradient(
    120deg,
    #fff6dd 0%,
    #fff2cc 38%,
    #ffd969 48%,
    #ffe9aa 54%,
    #fff3cf 62%,
    #fff6dd 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: text-shimmer 2.2s linear infinite;
}

@keyframes text-shimmer {
  0% {
    background-position: 100% 0%;
  }
  100% {
    background-position: 0% 100%;
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
