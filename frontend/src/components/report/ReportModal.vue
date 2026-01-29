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
          : 'w-[95vw] max-w-[1180px] h-[90vh] max-h-[900px]'
      )"
    >
      <!-- Header Bar -->
      <div class="modal-header">
        <div class="header-left">
          <div class="header-icon">
            <FileText class="w-5 h-5 text-white" />
          </div>
          <div class="header-info">
            <h2 class="header-title">{{ report?.title }}</h2>
            <p class="header-meta">Last modified: {{ formatRelativeTime(report?.lastModified || Date.now()) }}</p>
          </div>
        </div>
        <div class="header-actions">
          <!-- Share Button -->
          <button
            class="action-btn"
            @click="handleShare"
            title="Share"
          >
            <Share2 class="w-5 h-5" />
          </button>

          <!-- Download Button -->
          <Popover v-model:open="showDownloadOptions">
            <PopoverTrigger as-child>
              <button class="action-btn" title="Download">
                <Download class="w-5 h-5" />
              </button>
            </PopoverTrigger>
            <PopoverContent
              :side-offset="8"
              align="end"
              class="w-44 p-1.5"
            >
              <div class="flex flex-col">
                <button
                  class="dropdown-item"
                  @click="handleDownloadMarkdown"
                >
                  <FileText class="w-4 h-4 text-[var(--icon-secondary)]" />
                  Markdown (.md)
                </button>
                <button
                  class="dropdown-item"
                  @click="handleDownloadPdf"
                >
                  <FileDown class="w-4 h-4 text-[#ea4335]" />
                  PDF Document
                </button>
                <button
                  class="dropdown-item"
                  @click="handleDownloadDocx"
                >
                  <FileType class="w-4 h-4 text-[#4285f4]" />
                  Word (.docx)
                </button>
              </div>
            </PopoverContent>
          </Popover>

          <!-- More Options Button -->
          <Popover v-model:open="showMoreOptions">
            <PopoverTrigger as-child>
              <button class="action-btn" title="More options">
                <MoreHorizontal class="w-5 h-5" />
              </button>
            </PopoverTrigger>
            <PopoverContent
              :side-offset="8"
              align="end"
              class="w-48 p-1.5"
            >
              <div class="flex flex-col">
                <button
                  class="dropdown-item"
                  @click="handleCopyContent"
                >
                  <Copy class="w-4 h-4 text-[var(--icon-secondary)]" />
                  {{ isCopied ? 'Copied!' : 'Copy content' }}
                </button>
                <button
                  class="dropdown-item"
                  @click="handlePrint"
                >
                  <Printer class="w-4 h-4 text-[var(--icon-secondary)]" />
                  Print
                </button>
              </div>
            </PopoverContent>
          </Popover>

          <!-- Fullscreen Toggle -->
          <button
            class="action-btn"
            @click="toggleFullscreen"
            :title="isFullscreen ? 'Exit fullscreen' : 'Fullscreen'"
          >
            <Minimize2 v-if="isFullscreen" class="w-5 h-5" />
            <Maximize2 v-else class="w-5 h-5" />
          </button>

          <!-- Close Button -->
          <button
            class="action-btn"
            @click="isOpen = false"
            title="Close"
          >
            <X class="w-5 h-5" />
          </button>
        </div>
      </div>

      <!-- Content Area -->
      <div class="content-wrapper">
        <!-- Main Document Content -->
        <div class="document-container" ref="documentContainerRef" @scroll="handleScroll" @click="showTocSidebar = false">
          <div class="document-content">
            <!-- Document Title -->
            <h1 class="doc-title">{{ report?.title }}</h1>

            <!-- Document Metadata -->
            <div class="doc-meta">
              <div class="meta-row">
                <span class="meta-label">Author:</span>
                <span class="meta-value">{{ report?.author || 'Pythinker' }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">Date:</span>
                <span class="meta-value">{{ formatDate(report?.lastModified || Date.now()) }}</span>
              </div>
            </div>

            <!-- Rendered Content -->
            <div class="doc-body prose" v-html="renderedContent"></div>
          </div>
        </div>

        <!-- TOC Container - Notion style -->
        <div
          v-if="tableOfContents.length > 0"
          class="toc-container"
          @click.stop
        >
          <!-- Collapsed: Lines only -->
          <div
            v-if="!showTocSidebar"
            class="toc-mini"
            @mouseenter="showTocSidebar = true"
          >
            <div
              v-for="(item, index) in tableOfContents"
              :key="index"
              class="toc-line"
              :class="[
                activeSection === item.id ? 'toc-line-active' : '',
                item.level === 3 ? 'toc-line-sub' : '',
                item.level === 4 ? 'toc-line-sub' : ''
              ]"
            />
          </div>

          <!-- Expanded: Full TOC -->
          <Transition name="slide-toc">
            <div
              v-if="showTocSidebar"
              class="toc-sidebar"
            >
              <nav class="toc-nav">
                <!-- Report Title -->
                <button
                  class="toc-title"
                  @click="scrollToTop"
                >
                  {{ truncateText(report?.title || '', 20) }}
                </button>

                <!-- TOC Items (h2-h4 only, h1 is shown as toc-title) -->
                <button
                  v-for="(item, index) in tableOfContents"
                  :key="index"
                  class="toc-item"
                  :class="[
                    activeSection === item.id ? 'toc-item-active' : '',
                    `toc-level-${item.level}`
                  ]"
                  @click="scrollToSection(item.id)"
                >
                  {{ truncateText(item.title, item.level >= 3 ? 18 : 20) }}
                </button>
              </nav>
            </div>
          </Transition>
        </div>
      </div>

      <!-- Bottom Suggestion Bar -->
      <div
        v-if="showSuggestion && suggestion"
        class="suggestion-bar"
      >
        <div class="suggestion-content">
          <div class="suggestion-icon">
            <Lightbulb class="w-4 h-4" />
          </div>
          <span class="suggestion-text">{{ suggestion.text }}</span>
        </div>
        <button
          class="suggestion-action"
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
import { Document, Packer, Paragraph, TextRun, HeadingLevel } from 'docx';
import { saveAs } from 'file-saver';
import {
  FileText,
  Download,
  Maximize2,
  Minimize2,
  Lightbulb,
  X,
  Copy,
  Share2,
  MoreHorizontal,
  Printer,
  FileDown,
  FileType
} from 'lucide-vue-next';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import type { ReportData } from './types';

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

const documentContainerRef = ref<HTMLElement | null>(null);

const activeSection = ref<string>('');
const tableOfContents = ref<TocItem[]>([]);
const showDownloadOptions = ref(false);
const showMoreOptions = ref(false);
const showTocSidebar = ref(false);
const isDownloading = ref(false);
const isFullscreen = ref(false);
const isCopied = ref(false);

// Configure marked options
marked.use({
  breaks: true,
  gfm: true,
});

// Custom renderer to add IDs to headings
const renderer = new marked.Renderer();
renderer.heading = function({ text, depth }: { text: string; depth: number }) {
  const cleanText = text.replace(/\*\*([^*]+)\*\*/g, '$1').replace(/\*([^*]+)\*/g, '$1');
  const id = cleanText.toLowerCase().replace(/[^\w]+/g, '-');
  const parsedText = marked.parseInline(text);
  return `<h${depth} id="${id}">${parsedText}</h${depth}>`;
};

const renderedContent = computed(() => {
  if (!props.report?.content) return '';
  try {
    // Skip the first h1 since we display it separately
    let content = props.report.content;
    const lines = content.split('\n');
    const filteredLines = lines.filter(line => !line.match(/^#\s+/));
    content = filteredLines.join('\n');

    const html = marked.parse(content, { renderer });
    return DOMPurify.sanitize(html as string);
  } catch (error) {
    console.error('Failed to render markdown:', error);
    return '<p class="text-red-500">Failed to render content</p>';
  }
});

// Extract table of contents
const extractToc = () => {
  if (!props.report?.content) {
    tableOfContents.value = [];
    return;
  }

  // Match headings h2-h4 only (skip h1 since it's the title, shown separately)
  const headingRegex = /^(#{2,4})\s+(.+)$/gm;
  const toc: TocItem[] = [];
  let match;

  while ((match = headingRegex.exec(props.report.content)) !== null) {
    const level = match[1].length;
    const rawTitle = match[2].trim();
    const title = rawTitle.replace(/\*\*([^*]+)\*\*/g, '$1').replace(/\*([^*]+)\*/g, '$1');
    const id = title.toLowerCase().replace(/[^\w]+/g, '-');

    toc.push({ id, title, level });
  }

  tableOfContents.value = toc;

  if (toc.length > 0) {
    activeSection.value = toc[0].id;
  }
};

// Scroll to section
const scrollToSection = (id: string) => {
  const container = documentContainerRef.value;
  if (!container) return;

  const element = container.querySelector(`#${id}`);
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    activeSection.value = id;
  }
};

// Scroll to top
const scrollToTop = () => {
  const container = documentContainerRef.value;
  if (container) {
    container.scrollTo({ top: 0, behavior: 'smooth' });
  }
};

// Truncate text with ellipsis
const truncateText = (text: string, maxLength: number) => {
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + '...';
};

// Handle scroll to update active section
const handleScroll = () => {
  const container = documentContainerRef.value;
  if (!container) return;

  const headings = container.querySelectorAll('h1, h2, h3, h4');
  const containerRect = container.getBoundingClientRect();

  let currentSection = '';
  headings.forEach((heading) => {
    const rect = heading.getBoundingClientRect();
    if (rect.top <= containerRect.top + 100) {
      currentSection = heading.id;
    }
  });

  if (currentSection) {
    activeSection.value = currentSection;
  }
};

// Format relative time (e.g., "19 minutes ago")
const formatRelativeTime = (timestamp: number) => {
  const now = Date.now();
  const diff = now - timestamp;
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`;
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  if (days < 7) return `${days} day${days === 1 ? '' : 's'} ago`;

  return formatDate(timestamp);
};

// Format full date
const formatDate = (timestamp: number) => {
  const date = new Date(timestamp);
  return date.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric'
  });
};

// Actions
const handleShare = async () => {
  showMoreOptions.value = false;

  if (!props.report) return;

  const shareData = {
    title: props.report.title,
    text: props.report.content?.substring(0, 200) + '...',
    url: window.location.href
  };

  // Try native Web Share API first (works on mobile and some desktop browsers)
  if (navigator.share && navigator.canShare?.(shareData)) {
    try {
      await navigator.share(shareData);
      emit('share');
      return;
    } catch (error) {
      // User cancelled or share failed, fall through to clipboard
      if ((error as Error).name === 'AbortError') return;
    }
  }

  // Fallback: Copy report content to clipboard
  try {
    const shareText = `${props.report.title}\n\n${props.report.content}`;
    await navigator.clipboard.writeText(shareText);
    isCopied.value = true;
    setTimeout(() => {
      isCopied.value = false;
    }, 2000);
  } catch (error) {
    console.error('Failed to share:', error);
  }

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
  const container = documentContainerRef.value;
  if (!container || !props.report) return;

  showDownloadOptions.value = false;
  isDownloading.value = true;

  try {
    const element = container.querySelector('.document-content');
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
    const lines = props.report.content.split('\n');
    const children: Paragraph[] = [];

    for (const line of lines) {
      const trimmedLine = line.trim();

      if (!trimmedLine) {
        children.push(new Paragraph({}));
        continue;
      }

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
        children.push(new Paragraph({
          children: [new TextRun({ text: '• ' + trimmedLine.substring(2) })],
          indent: { left: 720 }
        }));
      } else if (/^\d+\.\s/.test(trimmedLine)) {
        children.push(new Paragraph({
          text: trimmedLine,
          indent: { left: 720 }
        }));
      } else {
        const runs: TextRun[] = [];
        const regex = /(\*\*[^*]+\*\*|\*[^*]+\*|[^*]+)/g;
        let match;

        while ((match = regex.exec(trimmedLine)) !== null) {
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
      sections: [{ properties: {}, children }]
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

  showMoreOptions.value = false;

  try {
    await navigator.clipboard.writeText(props.report.content);
    isCopied.value = true;
    setTimeout(() => {
      isCopied.value = false;
    }, 2000);
  } catch (error) {
    console.error('Failed to copy content:', error);
  }
};

// Print document
const handlePrint = () => {
  showMoreOptions.value = false;
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
    showTocSidebar.value = false;
  }
});
</script>

<style scoped>
/* ===== HEADER ===== */
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-light);
  background: var(--background-white-main);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex: 1;
}

.header-icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: linear-gradient(135deg, #4285f4 0%, #1a73e8 100%);
  display: flex;
  align-items: center;
  justify-content: center;
}

.header-info {
  min-width: 0;
}

.header-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 500px;
  margin: 0;
}

.header-meta {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 2px 0 0 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.action-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--icon-tertiary);
  transition: all 0.15s ease;
}

.action-btn:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--icon-secondary);
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  font-size: 13px;
  color: var(--text-primary);
  border-radius: 6px;
  transition: background-color 0.15s ease;
  width: 100%;
  text-align: left;
}

.dropdown-item:hover {
  background: var(--fill-tsp-gray-main);
}

/* ===== CONTENT AREA ===== */
.content-wrapper {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

.document-container {
  flex: 1;
  overflow-y: auto;
  scroll-behavior: smooth;
}

.document-content {
  max-width: 800px;
  margin: 0 auto;
  padding: 48px 64px;
}

.doc-title {
  font-size: 40px;
  font-weight: 400;
  line-height: 1.2;
  color: var(--text-primary);
  margin: 0 0 24px 0;
  font-family: 'Times New Roman', Georgia, serif;
}

.doc-meta {
  margin-bottom: 32px;
}

.meta-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 15px;
}

.meta-label {
  font-weight: 700;
  color: var(--text-primary);
}

.meta-value {
  color: var(--text-primary);
}

.doc-body {
  font-size: 16px;
  line-height: 1.75;
  color: var(--text-primary);
}

/* Prose styling for document body */
.doc-body.prose h1 {
  display: none;
}

.doc-body.prose h2 {
  font-size: 24px;
  font-weight: 700;
  margin-top: 40px;
  margin-bottom: 16px;
  line-height: 1.3;
  color: var(--text-primary);
}

.doc-body.prose h3 {
  font-size: 18px;
  font-weight: 700;
  margin-top: 32px;
  margin-bottom: 12px;
  line-height: 1.35;
  color: var(--text-primary);
}

.doc-body.prose h4 {
  font-size: 16px;
  font-weight: 700;
  margin-top: 24px;
  margin-bottom: 8px;
  line-height: 1.4;
  color: var(--text-primary);
}

.doc-body.prose p {
  margin-top: 16px;
  margin-bottom: 16px;
  line-height: 1.75;
}

.doc-body.prose strong {
  font-weight: 700;
  color: var(--text-primary);
}

.doc-body.prose em {
  font-style: italic;
}

.doc-body.prose a {
  color: #1a73e8;
  text-decoration: none;
}

.doc-body.prose a:hover {
  text-decoration: underline;
}

.doc-body.prose ul,
.doc-body.prose ol {
  margin: 16px 0;
  padding-left: 24px;
}

.doc-body.prose li {
  margin: 8px 0;
  line-height: 1.7;
}

.doc-body.prose ul li {
  list-style-type: disc;
}

.doc-body.prose ol li {
  list-style-type: decimal;
}

.doc-body.prose blockquote {
  margin: 24px 0;
  padding: 16px 20px;
  border-left: 4px solid var(--border-main);
  background: var(--fill-tsp-gray-main);
  border-radius: 0 8px 8px 0;
  font-style: italic;
  color: var(--text-secondary);
}

.doc-body.prose blockquote p {
  margin: 0;
}

.doc-body.prose code {
  background: var(--fill-tsp-gray-main);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 14px;
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', monospace;
}

.doc-body.prose pre {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 20px;
  border-radius: 8px;
  margin: 24px 0;
  overflow-x: auto;
  font-size: 14px;
  line-height: 1.5;
}

.doc-body.prose pre code {
  background: transparent;
  padding: 0;
  font-size: inherit;
  color: inherit;
}

.doc-body.prose table {
  width: 100%;
  border-collapse: collapse;
  margin: 24px 0;
  font-size: 14px;
}

.doc-body.prose th {
  background-color: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-main);
  padding: 12px 16px;
  text-align: left;
  font-weight: 700;
  color: var(--text-primary);
}

.doc-body.prose td {
  border: 1px solid var(--border-light);
  padding: 12px 16px;
  vertical-align: top;
}

.doc-body.prose tr:hover td {
  background-color: var(--fill-tsp-white-main);
}

.doc-body.prose hr {
  border: none;
  border-top: 1px solid var(--border-main);
  margin: 32px 0;
}

.doc-body.prose img {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  margin: 24px 0;
}

/* ===== TOC CONTAINER ===== */
.toc-container {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  z-index: 10;
  pointer-events: none;
}

.toc-container > * {
  pointer-events: auto;
}

/* ===== TOC MINI (Collapsed Lines) ===== */
.toc-mini {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  padding: 20px 14px;
  cursor: pointer;
}

.toc-line {
  width: 28px;
  height: 4px;
  background: rgba(0, 0, 0, 0.08);
  border-radius: 2px;
  transition: all 0.15s ease;
}

.toc-line-active {
  background: rgba(0, 0, 0, 0.5);
}

.toc-line-sub {
  width: 20px;
}

.toc-mini:hover .toc-line {
  background: rgba(0, 0, 0, 0.12);
}

.toc-mini:hover .toc-line-active {
  background: rgba(0, 0, 0, 0.6);
}

/* ===== TOC SIDEBAR (Expanded) ===== */
.toc-sidebar {
  position: absolute;
  top: 24px;
  right: 16px;
  width: 220px;
  max-height: calc(100% - 48px);
  flex-shrink: 0;
  background: var(--background-white-main);
  border: 1px solid var(--border-light);
  overflow-y: auto;
  padding: 24px 20px;
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.1);
}

.toc-nav {
  display: flex;
  flex-direction: column;
}

.toc-title {
  display: block;
  width: 100%;
  text-align: left;
  padding: 0;
  margin-bottom: 20px;
  font-size: 17px;
  font-weight: 500;
  color: #1a73e8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: opacity 0.15s ease;
}

.toc-title:hover {
  opacity: 0.8;
}

.toc-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 10px 0;
  font-size: 15px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.15s ease;
  border-radius: 0;
}

.toc-item:hover {
  color: #1a73e8;
}

.toc-item-active {
  color: #1a73e8;
}

.toc-level-2 {
  font-weight: 500;
  color: var(--text-primary);
}

.toc-level-3 {
  padding-left: 14px;
  font-size: 14px;
  font-weight: 400;
  color: var(--text-tertiary);
}

.toc-level-4 {
  padding-left: 24px;
  font-size: 13px;
  font-weight: 400;
  color: var(--text-tertiary);
}

/* TOC Slide Transition */
.slide-toc-enter-active,
.slide-toc-leave-active {
  transition: all 0.15s ease;
}

.slide-toc-enter-from,
.slide-toc-leave-to {
  opacity: 0;
  transform: translateX(10px);
}

/* ===== SUGGESTION BAR ===== */
.suggestion-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 20px;
  border-top: 1px solid var(--border-light);
  background: var(--fill-tsp-white-main);
  flex-shrink: 0;
}

.suggestion-content {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.suggestion-icon {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: var(--fill-tsp-gray-main);
  color: var(--icon-secondary);
}

.suggestion-text {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.suggestion-action {
  flex-shrink: 0;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  color: white;
  background: #1a1a1a;
  border-radius: 6px;
  transition: background-color 0.15s ease;
}

.suggestion-action:hover {
  background: #333;
}

/* ===== SCROLLBAR ===== */
.document-container::-webkit-scrollbar,
.toc-sidebar::-webkit-scrollbar {
  width: 8px;
}

.document-container::-webkit-scrollbar-track,
.toc-sidebar::-webkit-scrollbar-track {
  background: transparent;
}

.document-container::-webkit-scrollbar-thumb,
.toc-sidebar::-webkit-scrollbar-thumb {
  background: var(--border-main);
  border-radius: 4px;
}

.document-container::-webkit-scrollbar-thumb:hover,
.toc-sidebar::-webkit-scrollbar-thumb:hover {
  background: var(--border-dark);
}

/* ===== PRINT STYLES ===== */
@media print {
  .modal-header,
  .toc-sidebar,
  .toc-toggle,
  .suggestion-bar {
    display: none !important;
  }

  .document-content {
    padding: 0;
    max-width: none;
  }
}
</style>
