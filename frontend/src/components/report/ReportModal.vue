<template>
  <Dialog v-model:open="isOpen">
    <DialogContent
      :hide-close-button="true"
      :title="report?.title || 'Report Preview'"
      description="View and download report content"
      :class="cn(
        'p-0 flex flex-col overflow-hidden transition-all duration-200',
        'bg-[var(--background-white-main)]',
        isFullscreen
          ? 'w-screen max-w-none h-screen max-h-none rounded-none'
          : 'w-[95vw] max-w-[1100px] h-[90vh] max-h-[900px]'
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
          <!-- Download Dropdown -->
          <Popover v-model:open="showDownloadOptions">
            <PopoverTrigger as-child>
              <button
                class="w-9 h-9 flex items-center justify-center rounded-md hover:bg-[var(--fill-tsp-gray-main)] transition-colors"
                title="Download"
              >
                <Download class="w-5 h-5 text-[var(--icon-tertiary)]" />
              </button>
            </PopoverTrigger>
            <PopoverContent
              :side-offset="8"
              align="end"
              class="w-44 p-1.5"
            >
              <div class="flex flex-col">
                <button
                  class="flex items-center gap-3 px-3 py-2.5 text-sm text-[var(--text-primary)] hover:bg-[var(--fill-tsp-gray-main)] rounded-lg transition-colors"
                  @click="handleDownloadMarkdown"
                >
                  <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" fill="#4285f4"/>
                    <path d="M14 2v6h6" fill="#a1c2fa"/>
                    <path d="M8 13h8M8 17h6" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>
                  Markdown
                </button>
                <button
                  class="flex items-center gap-3 px-3 py-2.5 text-sm text-[var(--text-primary)] hover:bg-[var(--fill-tsp-gray-main)] rounded-lg transition-colors"
                  @click="handleDownloadPdf"
                >
                  <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" fill="#ea4335"/>
                    <path d="M14 2v6h6" fill="#f5a9a3"/>
                    <text x="7" y="17" fill="white" font-size="6" font-weight="bold" font-family="Arial">A</text>
                  </svg>
                  PDF
                </button>
                <button
                  class="flex items-center gap-3 px-3 py-2.5 text-sm text-[var(--text-primary)] hover:bg-[var(--fill-tsp-gray-main)] rounded-lg transition-colors"
                  @click="handleDownloadDocx"
                >
                  <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" fill="#4285f4"/>
                    <path d="M14 2v6h6" fill="#a1c2fa"/>
                    <text x="7" y="17" fill="white" font-size="6" font-weight="bold" font-family="Arial">W</text>
                  </svg>
                  Docx
                </button>
              </div>
            </PopoverContent>
          </Popover>

          <!-- Expand/Minimize Button -->
          <button
            class="w-9 h-9 flex items-center justify-center rounded-md hover:bg-[var(--fill-tsp-gray-main)] transition-colors"
            @click="toggleFullscreen"
            :title="isFullscreen ? 'Exit fullscreen' : 'Fullscreen'"
          >
            <Minimize2 v-if="isFullscreen" class="w-5 h-5 text-[var(--icon-tertiary)]" />
            <Maximize2 v-else class="w-5 h-5 text-[var(--icon-tertiary)]" />
          </button>

          <!-- Close Button -->
          <button
            class="w-9 h-9 flex items-center justify-center rounded-md hover:bg-[var(--fill-tsp-gray-main)] transition-colors"
            @click="isOpen = false"
            title="Close"
          >
            <X class="w-5 h-5 text-[var(--icon-tertiary)]" />
          </button>
        </div>
      </div>

      <!-- Content Area -->
      <div class="flex flex-1 min-h-0 overflow-hidden">
        <!-- Main Content with Tiptap Editor -->
        <div class="flex-1 overflow-hidden">
          <TiptapReportEditor
            :content="renderedContent"
            :editable="false"
          />
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
import html2pdf from 'html2pdf.js';
import { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType } from 'docx';
import { saveAs } from 'file-saver';
import {
  FileText,
  Download,
  Maximize2,
  Minimize2,
  Lightbulb,
  X
} from 'lucide-vue-next';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import type { ReportData } from './ReportCard.vue';
import TiptapReportEditor from './TiptapReportEditor.vue';

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
const showDownloadOptions = ref(false);
const isDownloading = ref(false);
const isFullscreen = ref(false);

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

const toggleFullscreen = () => {
  isFullscreen.value = !isFullscreen.value;
};

const handleSuggestionAction = () => {
  emit('suggestionAction');
};

// Generate sanitized filename
const getSafeFilename = (title: string) => {
  return (title || 'document')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
    .substring(0, 50);
};

// Download as Markdown
const handleDownloadMarkdown = () => {
  if (!props.report?.content) return;

  showDownloadOptions.value = false;
  const filename = getSafeFilename(props.report.title) + '.md';
  const blob = new Blob([props.report.content], { type: 'text/markdown;charset=utf-8' });
  saveAs(blob, filename);
  emit('download');
};

// Download as PDF
const handleDownloadPdf = async () => {
  if (!contentRef.value || !props.report) return;

  showDownloadOptions.value = false;
  isDownloading.value = true;

  try {
    const element = contentRef.value.querySelector('.prose');
    if (!element) return;

    const opt = {
      margin: [15, 15, 15, 15],
      filename: getSafeFilename(props.report.title) + '.pdf',
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: {
        scale: 2,
        useCORS: true,
        letterRendering: true
      },
      jsPDF: {
        unit: 'mm',
        format: 'a4',
        orientation: 'portrait'
      },
      pagebreak: { mode: ['avoid-all', 'css', 'legacy'] }
    };

    await html2pdf().set(opt).from(element).save();
    emit('download');
  } catch (error) {
    console.error('Failed to generate PDF:', error);
  } finally {
    isDownloading.value = false;
  }
};

// Download as DOCX
const handleDownloadDocx = async () => {
  if (!props.report?.content) return;

  showDownloadOptions.value = false;
  isDownloading.value = true;

  try {
    // Parse markdown content into document structure
    const lines = props.report.content.split('\n');
    const children: Paragraph[] = [];

    for (const line of lines) {
      const trimmedLine = line.trim();

      // Skip empty lines
      if (!trimmedLine) {
        children.push(new Paragraph({}));
        continue;
      }

      // Handle headings
      if (trimmedLine.startsWith('# ')) {
        children.push(new Paragraph({
          text: trimmedLine.substring(2),
          heading: HeadingLevel.HEADING_1,
          spacing: { before: 400, after: 200 }
        }));
      } else if (trimmedLine.startsWith('## ')) {
        children.push(new Paragraph({
          text: trimmedLine.substring(3),
          heading: HeadingLevel.HEADING_2,
          spacing: { before: 300, after: 150 }
        }));
      } else if (trimmedLine.startsWith('### ')) {
        children.push(new Paragraph({
          text: trimmedLine.substring(4),
          heading: HeadingLevel.HEADING_3,
          spacing: { before: 200, after: 100 }
        }));
      } else if (trimmedLine.startsWith('- ') || trimmedLine.startsWith('* ')) {
        // Handle list items
        children.push(new Paragraph({
          children: [
            new TextRun({ text: '• ' + trimmedLine.substring(2) })
          ],
          indent: { left: 720 }
        }));
      } else if (/^\d+\.\s/.test(trimmedLine)) {
        // Handle numbered lists
        children.push(new Paragraph({
          text: trimmedLine,
          indent: { left: 720 }
        }));
      } else {
        // Regular paragraph - handle bold and italic
        const runs: TextRun[] = [];
        let remaining = trimmedLine;

        // Simple parsing for **bold** and *italic*
        const regex = /(\*\*[^*]+\*\*|\*[^*]+\*|[^*]+)/g;
        let match;

        while ((match = regex.exec(remaining)) !== null) {
          const text = match[0];
          if (text.startsWith('**') && text.endsWith('**')) {
            runs.push(new TextRun({ text: text.slice(2, -2), bold: true }));
          } else if (text.startsWith('*') && text.endsWith('*')) {
            runs.push(new TextRun({ text: text.slice(1, -1), italics: true }));
          } else {
            runs.push(new TextRun({ text }));
          }
        }

        if (runs.length === 0) {
          runs.push(new TextRun({ text: trimmedLine }));
        }

        children.push(new Paragraph({
          children: runs,
          spacing: { after: 120 }
        }));
      }
    }

    const doc = new Document({
      sections: [{
        properties: {},
        children: children
      }]
    });

    const blob = await Packer.toBlob(doc);
    saveAs(blob, getSafeFilename(props.report.title) + '.docx');
    emit('download');
  } catch (error) {
    console.error('Failed to generate DOCX:', error);
  } finally {
    isDownloading.value = false;
  }
};

// Copy content to clipboard
const handleCopyContent = async () => {
  if (!props.report?.content) return;

  showDownloadOptions.value = false;

  try {
    await navigator.clipboard.writeText(props.report.content);
    // Could emit a toast notification here
  } catch (error) {
    console.error('Failed to copy content:', error);
  }
};

// Print document
const handlePrint = () => {
  showDownloadOptions.value = false;
  window.print();
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
