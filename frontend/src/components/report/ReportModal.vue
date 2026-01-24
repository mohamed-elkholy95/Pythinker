<template>
  <Dialog v-model:open="isOpen">
    <DialogContent
      :class="cn(
        'w-[95vw] max-w-[1100px] h-[90vh] max-h-[900px] p-0 flex flex-col overflow-hidden',
        'bg-[var(--background-white-main)]'
      )"
    >
      <!-- Header -->
      <div class="flex items-center justify-between px-6 py-4 border-b border-[var(--border-main)] flex-shrink-0">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-lg bg-[#4285f4] flex items-center justify-center flex-shrink-0">
            <FileText class="w-5 h-5 text-white" />
          </div>
          <div class="min-w-0">
            <h2 class="text-[15px] font-semibold text-[var(--text-primary)] truncate max-w-[600px]">
              {{ report?.title }}
            </h2>
            <p class="text-xs text-[var(--text-tertiary)]">
              Last modified: {{ formatDate(report?.lastModified || Date.now()) }}
            </p>
          </div>
        </div>
        <div class="flex items-center gap-1">
          <button
            class="w-8 h-8 flex items-center justify-center rounded-md hover:bg-[var(--fill-tsp-gray-main)]"
            @click="handleShare"
            title="Share"
          >
            <Share2 class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </button>
          <button
            class="w-8 h-8 flex items-center justify-center rounded-md hover:bg-[var(--fill-tsp-gray-main)]"
            @click="handleDownload"
            title="Download"
          >
            <Download class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </button>
          <button
            class="w-8 h-8 flex items-center justify-center rounded-md hover:bg-[var(--fill-tsp-gray-main)]"
            @click="toggleFullscreen"
            title="Expand"
          >
            <Maximize2 class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </button>
          <button
            class="w-8 h-8 flex items-center justify-center rounded-md hover:bg-[var(--fill-tsp-gray-main)]"
            title="More options"
          >
            <MoreHorizontal class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </button>
        </div>
      </div>

      <!-- Content Area -->
      <div class="flex flex-1 min-h-0 overflow-hidden">
        <!-- Main Content -->
        <div
          ref="contentRef"
          class="flex-1 overflow-y-auto p-8"
          @scroll="handleScroll"
        >
          <div class="max-w-[768px] mx-auto">
            <!-- Document Title -->
            <h1 class="text-[32px] font-bold text-[var(--text-primary)] leading-tight mb-8">
              {{ report?.title }}
            </h1>

            <!-- Markdown Content -->
            <div
              class="prose prose-gray max-w-none dark:prose-invert
                prose-headings:text-[var(--text-primary)]
                prose-h2:text-[24px] prose-h2:font-bold prose-h2:mt-10 prose-h2:mb-4 prose-h2:pb-2 prose-h2:border-b prose-h2:border-[var(--border-main)]
                prose-h3:text-[20px] prose-h3:font-semibold prose-h3:mt-8 prose-h3:mb-3 prose-h3:text-[#1a73e8]
                prose-h4:text-[16px] prose-h4:font-medium prose-h4:mt-6 prose-h4:mb-2
                prose-p:text-[var(--text-secondary)] prose-p:leading-relaxed prose-p:my-4
                prose-strong:text-[var(--text-primary)] prose-strong:font-semibold
                prose-ul:my-4 prose-li:my-1
                prose-table:border-collapse prose-table:w-full prose-table:my-6
                prose-th:bg-[var(--fill-tsp-white-main)] prose-th:text-left prose-th:px-4 prose-th:py-3 prose-th:text-sm prose-th:font-semibold prose-th:text-[var(--text-primary)] prose-th:border prose-th:border-[var(--border-main)]
                prose-td:px-4 prose-td:py-3 prose-td:text-sm prose-td:text-[var(--text-secondary)] prose-td:border prose-td:border-[var(--border-main)]
                prose-code:bg-[var(--fill-tsp-white-main)] prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none
                prose-pre:bg-[var(--fill-tsp-white-main)] prose-pre:p-4 prose-pre:rounded-lg prose-pre:my-4
                prose-a:text-[#1a73e8] prose-a:no-underline hover:prose-a:underline
              "
              v-html="renderedContent"
            />
          </div>
        </div>

        <!-- Table of Contents Sidebar -->
        <div
          v-if="showToc && tableOfContents.length > 0"
          class="w-[240px] flex-shrink-0 border-l border-[var(--border-main)] overflow-y-auto py-4 px-3 bg-[var(--background-gray-main)]"
        >
          <div class="sticky top-0">
            <nav class="space-y-1">
              <button
                v-for="(item, index) in tableOfContents"
                :key="index"
                class="w-full text-left px-2 py-1.5 rounded text-[13px] transition-colors truncate"
                :class="[
                  activeSection === item.id
                    ? 'text-[#1a73e8] bg-[var(--fill-tsp-white-dark)] font-medium'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--fill-tsp-white-main)]',
                  item.level === 2 ? 'font-medium' : '',
                  item.level === 3 ? 'pl-4' : '',
                  item.level === 4 ? 'pl-6 text-[12px]' : ''
                ]"
                @click="scrollToSection(item.id)"
              >
                {{ item.title }}
              </button>
            </nav>
          </div>
        </div>
      </div>

      <!-- Bottom Suggestion Bar (optional) -->
      <div
        v-if="showSuggestion && suggestion"
        class="flex items-center justify-between px-4 py-3 border-t border-[var(--border-main)] bg-[var(--fill-tsp-white-main)] flex-shrink-0"
      >
        <div class="flex items-center gap-2">
          <Lightbulb class="w-4 h-4 text-[var(--icon-secondary)]" />
          <span class="text-sm text-[var(--text-secondary)]">{{ suggestion.text }}</span>
        </div>
        <button
          class="px-4 py-1.5 rounded-lg bg-[var(--Button-primary-brand)] text-white text-sm font-medium hover:opacity-90 transition-opacity"
          @click="handleSuggestionAction"
        >
          {{ suggestion.action }}
        </button>
      </div>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import {
  FileText,
  Share2,
  Download,
  Maximize2,
  MoreHorizontal,
  Lightbulb
} from 'lucide-vue-next';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import type { ReportData } from './ReportCard.vue';

interface TocItem {
  id: string;
  title: string;
  level: number;
}

interface Suggestion {
  text: string;
  action: string;
}

const props = defineProps<{
  report: ReportData | null;
  showToc?: boolean;
  showSuggestion?: boolean;
  suggestion?: Suggestion;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'share'): void;
  (e: 'download'): void;
  (e: 'suggestionAction'): void;
}>();

const isOpen = defineModel<boolean>('open', { default: false });

const contentRef = ref<HTMLElement | null>(null);
const activeSection = ref<string>('');
const tableOfContents = ref<TocItem[]>([]);

// Configure marked options using modern API
marked.use({
  breaks: true,
  gfm: true,
});

// Custom renderer to add IDs to headings
const renderer = new marked.Renderer();
renderer.heading = function({ text, depth }: { text: string; depth: number }) {
  const id = text.toLowerCase().replace(/[^\w]+/g, '-');
  return `<h${depth} id="${id}">${text}</h${depth}>`;
};

const renderedContent = computed(() => {
  if (!props.report?.content) return '';
  try {
    const html = marked.parse(props.report.content, { renderer });
    return DOMPurify.sanitize(html as string);
  } catch (error) {
    console.error('Failed to render markdown:', error);
    return '<p class="text-red-500">Failed to render content</p>';
  }
});

// Extract table of contents from content
const extractToc = () => {
  if (!props.report?.content) {
    tableOfContents.value = [];
    return;
  }

  const headingRegex = /^(#{1,4})\s+(.+)$/gm;
  const toc: TocItem[] = [];
  let match;

  while ((match = headingRegex.exec(props.report.content)) !== null) {
    const level = match[1].length;
    const title = match[2].trim();
    const id = title.toLowerCase().replace(/[^\w]+/g, '-');

    // Only include h2, h3, h4
    if (level >= 2 && level <= 4) {
      toc.push({ id, title, level });
    }
  }

  tableOfContents.value = toc;

  // Set first section as active
  if (toc.length > 0) {
    activeSection.value = toc[0].id;
  }
};

// Scroll to section
const scrollToSection = (id: string) => {
  const element = contentRef.value?.querySelector(`#${id}`);
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    activeSection.value = id;
  }
};

// Handle scroll to update active section
const handleScroll = () => {
  if (!contentRef.value) return;

  const headings = contentRef.value.querySelectorAll('h2, h3, h4');

  let currentSection = '';
  headings.forEach((heading) => {
    const rect = heading.getBoundingClientRect();
    const containerRect = contentRef.value!.getBoundingClientRect();

    if (rect.top <= containerRect.top + 100) {
      currentSection = heading.id;
    }
  });

  if (currentSection) {
    activeSection.value = currentSection;
  }
};

// Format date
const formatDate = (timestamp: number) => {
  const date = new Date(timestamp);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  });
};

// Actions
const handleShare = () => {
  emit('share');
};

const handleDownload = () => {
  emit('download');
};

const toggleFullscreen = () => {
  // Fullscreen toggle logic
};

const handleSuggestionAction = () => {
  emit('suggestionAction');
};

// Watch for content changes
watch(() => props.report?.content, () => {
  nextTick(() => {
    extractToc();
  });
}, { immediate: true });

// Watch for open state
watch(isOpen, (newVal) => {
  if (!newVal) {
    emit('close');
  }
});
</script>

<style scoped>
/* Table styling for Notion-like appearance */
:deep(table) {
  border-radius: 8px;
  overflow: hidden;
}

:deep(table tr:nth-child(even) td) {
  background-color: var(--fill-tsp-white-main);
}

:deep(table tr:hover td) {
  background-color: var(--fill-tsp-white-dark);
}

/* Smooth scrolling */
.overflow-y-auto {
  scroll-behavior: smooth;
}

/* Highlight effect for section navigation */
:deep(h2:target),
:deep(h3:target),
:deep(h4:target) {
  animation: highlight 1.5s ease;
}

@keyframes highlight {
  0%, 50% {
    background-color: rgba(26, 115, 232, 0.1);
  }
  100% {
    background-color: transparent;
  }
}
</style>
