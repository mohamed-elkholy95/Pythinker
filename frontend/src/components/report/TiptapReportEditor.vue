<template>
  <div
    ref="contentRef"
    :class="[
      'bg-[var(--background-white-main)]',
      embedded ? 'overflow-visible' : compact ? 'overflow-hidden' : 'h-full overflow-y-auto px-8 py-6'
    ]"
    @scroll="$emit('scroll', $event)"
  >
    <EditorContent
      :editor="editor"
      :class="[
        'prose prose-gray',
        compact
          ? ['prose-compact', hideMainTitleInCompact ?? true ? 'hide-main-title' : '']
          : 'max-w-4xl mx-auto'
      ]"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount, computed, nextTick } from 'vue';
import { useEditor, EditorContent } from '@tiptap/vue-3';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { normalizeVerificationMarkers, linkifyInlineCitations } from './reportContentNormalizer';
import { createTiptapDocumentExtensions } from './tiptapDocumentExtensions';

const props = defineProps<{
  content: string;
  editable?: boolean;
  compact?: boolean;
  hideMainTitleInCompact?: boolean;
  embedded?: boolean;
}>();

const _emit = defineEmits<{
  (e: 'scroll', event: Event): void;
}>();

const contentRef = ref<HTMLElement | null>(null);

// Convert markdown to HTML, applying citation linkification before marked.parse()
const htmlContent = computed(() => {
  if (!props.content) return '';
  const normalizedMarkdown = normalizeVerificationMarkers(props.content);
  const linkedMarkdown = linkifyInlineCitations(normalizedMarkdown);
  const rawHtml = marked.parse(linkedMarkdown, { async: false, breaks: true, gfm: true }) as string;
  return DOMPurify.sanitize(rawHtml);
});

// After TipTap renders, stamp id="ref-N" onto ordered list items inside the
// References / Sources / Bibliography section. TipTap strips unknown id attrs
// from its schema nodes, so we must do this via direct DOM mutation.
const addReferenceAnchors = () => {
  const proseMirror = contentRef.value?.querySelector('.ProseMirror');
  if (!proseMirror) return;

  const refHeadingRe = /^(references?|sources?|bibliography|citations?)$/i;
  const headings = Array.from(proseMirror.querySelectorAll('h1, h2, h3, h4'));

  for (const heading of headings) {
    if (!refHeadingRe.test(heading.textContent?.trim() ?? '')) continue;

    let sibling = heading.nextElementSibling;
    while (sibling) {
      if (sibling.tagName === 'OL') {
        sibling.querySelectorAll('li').forEach((item, index) => {
          item.setAttribute('id', `ref-${index + 1}`);
        });
        break;
      }
      if (/^H[1-4]$/.test(sibling.tagName)) break;
      sibling = sibling.nextElementSibling;
    }
  }
};

const editor = useEditor({
  content: htmlContent.value,
  editable: props.editable ?? false,
  extensions: createTiptapDocumentExtensions(),
  editorProps: {
    attributes: {
      class: 'focus:outline-none min-h-full',
    },
  },
  onCreate: () => { nextTick(addReferenceAnchors); },
  onUpdate: () => { nextTick(addReferenceAnchors); },
});

// Watch for content changes - convert markdown to HTML
watch(() => props.content, () => {
  if (editor.value && htmlContent.value !== editor.value.getHTML()) {
    editor.value.commands.setContent(htmlContent.value, false);
  }
});

// Watch for editable changes
watch(() => props.editable, (newEditable) => {
  if (editor.value) {
    editor.value.setEditable(newEditable ?? false);
  }
});

onBeforeUnmount(() => {
  editor.value?.destroy();
});

// Expose content ref for parent component
defineExpose({
  contentRef,
});
</script>

<style scoped>
/* Prose styling for report content */
:deep(.prose) {
  --tw-prose-body: var(--text-primary);
  --tw-prose-headings: var(--text-primary);
  --tw-prose-links: #1a73e8;
  --tw-prose-bold: var(--text-primary);
  --tw-prose-counters: var(--text-secondary);
  --tw-prose-bullets: var(--text-tertiary);
  --tw-prose-hr: var(--border-main);
  --tw-prose-quotes: var(--text-secondary);
  --tw-prose-quote-borders: var(--border-main);
  --tw-prose-captions: var(--text-tertiary);
  --tw-prose-code: var(--text-primary);
  --tw-prose-pre-code: var(--text-primary);
  --tw-prose-pre-bg: var(--fill-tsp-gray-main);
  --tw-prose-th-borders: var(--border-main);
  --tw-prose-td-borders: var(--border-light);
}

:global(.dark) :deep(.prose),
:global([data-theme='dark']) :deep(.prose) {
  --tw-prose-links: #58a6ff;
}

/* Link styling — theme-aware for dark mode */
:deep(.report-link) {
  color: #1a73e8;
  transition: color 0.15s ease;
}

:global(.dark) :deep(.report-link),
:global([data-theme='dark']) :deep(.report-link) {
  color: #58a6ff;
}

:deep(.prose h1) {
  font-size: 1.875rem;
  font-weight: 700;
  margin-top: 2rem;
  margin-bottom: 1rem;
  line-height: 1.3;
}

:deep(.prose h2) {
  font-size: 1.5rem;
  font-weight: 600;
  margin-top: 1.75rem;
  margin-bottom: 0.75rem;
  line-height: 1.35;
  border-bottom: 1px solid var(--border-light);
  padding-bottom: 0.5rem;
}

:deep(.prose h3) {
  font-size: 1.25rem;
  font-weight: 600;
  margin-top: 1.5rem;
  margin-bottom: 0.5rem;
  line-height: 1.4;
}

:deep(.prose h4) {
  font-size: 1.1rem;
  font-weight: 600;
  margin-top: 1.25rem;
  margin-bottom: 0.5rem;
  line-height: 1.4;
}

:deep(.prose p) {
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
  line-height: 1.7;
}

:deep(.prose ul),
:deep(.prose ol) {
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
  padding-left: 1.5rem;
}

:deep(.prose li) {
  margin-top: 0.25rem;
  margin-bottom: 0.25rem;
}

:deep(.prose blockquote) {
  border-left: 4px solid var(--border-main);
  padding-left: 1rem;
  margin-top: 1rem;
  margin-bottom: 1rem;
  font-style: italic;
  color: var(--text-secondary);
}

:deep(.prose table) {
  width: 100%;
  border-collapse: collapse;
  margin-top: 1rem;
  margin-bottom: 1rem;
  font-size: 0.875rem;
  table-layout: fixed;
}

:deep(.prose th) {
  background-color: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-main);
  padding: 0.75rem;
  text-align: left;
  font-weight: 600;
}

:deep(.prose td) {
  border: 1px solid var(--border-light);
  padding: 0.75rem;
  vertical-align: top;
}

:deep(.prose th p),
:deep(.prose td p) {
  margin: 0;
}

:deep(.prose code) {
  background-color: var(--fill-tsp-gray-main);
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  font-size: 0.875em;
}

:deep(.prose pre) {
  margin-top: 1rem;
  margin-bottom: 1rem;
}

:deep(.prose pre code) {
  background-color: transparent;
  padding: 0;
}

:deep(.verification-marker) {
  color: var(--function-warning);
  font-size: 0.72em;
  line-height: 1;
  margin-left: 0.24rem;
  opacity: 0.8;
  cursor: help;
  user-select: none;
}

:deep(.verification-marker:hover) {
  opacity: 1;
}

/* ===== INLINE CITATION LINKS ===== */
/* Target by href attr so the style is robust even if TipTap rewrites the class */
:deep(a[href^="#ref-"]) {
  color: #1a73e8;
  font-size: 0.78em;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  padding: 0 0.05em;
  border-radius: 3px;
  transition: background-color 0.15s ease, opacity 0.15s ease;
  line-height: 1;
}

:deep(a[href^="#ref-"]:hover) {
  background-color: rgba(26, 115, 232, 0.12);
  opacity: 0.85;
  text-decoration: none;
}

:global(.dark) :deep(a[href^="#ref-"]),
:global([data-theme='dark']) :deep(a[href^="#ref-"]) {
  color: #58a6ff;
}

:global(.dark) :deep(a[href^="#ref-"]:hover),
:global([data-theme='dark']) :deep(a[href^="#ref-"]:hover) {
  background-color: rgba(88, 166, 255, 0.12);
}

:deep(.prose hr) {
  border-color: var(--border-main);
  margin-top: 2rem;
  margin-bottom: 2rem;
}

:deep(.prose img) {
  max-width: 100%;
  height: auto;
  border-radius: 0.5rem;
  margin-top: 1rem;
  margin-bottom: 1rem;
}

/* Task list styling */
:deep(.prose ul[data-type="taskList"]) {
  list-style: none;
  padding-left: 0;
}

:deep(.prose ul[data-type="taskList"] li) {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
}

:deep(.prose ul[data-type="taskList"] li input[type="checkbox"]) {
  margin-top: 0.25rem;
}

/* Compact mode styling for card preview */
:deep(.prose-compact) {
  --tw-prose-body: var(--text-secondary);
  --tw-prose-headings: var(--text-primary);
  --tw-prose-links: var(--tw-prose-links, #1a73e8);
  --tw-prose-bold: var(--text-primary);
  --tw-prose-counters: var(--text-secondary);
  --tw-prose-bullets: var(--text-tertiary);
  --tw-prose-hr: var(--border-main);
  --tw-prose-quotes: var(--text-secondary);
  --tw-prose-quote-borders: var(--border-main);
  --tw-prose-captions: var(--text-tertiary);
  --tw-prose-code: var(--text-primary);
  --tw-prose-pre-code: var(--text-primary);
  --tw-prose-pre-bg: var(--fill-tsp-gray-main);
  --tw-prose-th-borders: var(--border-main);
  --tw-prose-td-borders: var(--border-light);
}

:deep(.prose-compact.hide-main-title h1) {
  display: none; /* Hide h1 in compact mode - shown separately */
}

:deep(.prose-compact h2) {
  font-size: 1rem;
  font-weight: 600;
  margin-top: 1rem;
  margin-bottom: 0.5rem;
  line-height: 1.35;
  border-bottom: none;
  padding-bottom: 0;
  color: var(--text-primary);
}

:deep(.prose-compact h3) {
  font-size: 0.875rem;
  font-weight: 600;
  margin-top: 0.75rem;
  margin-bottom: 0.375rem;
  line-height: 1.4;
  color: var(--text-primary);
}

:deep(.prose-compact h4) {
  font-size: 0.8125rem;
  font-weight: 600;
  margin-top: 0.625rem;
  margin-bottom: 0.25rem;
  line-height: 1.4;
  color: var(--text-primary);
}

:deep(.prose-compact p) {
  margin-top: 0.5rem;
  margin-bottom: 0.5rem;
  line-height: 1.6;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

:deep(.prose-compact ul),
:deep(.prose-compact ol) {
  margin-top: 0.5rem;
  margin-bottom: 0.5rem;
  padding-left: 1.25rem;
  font-size: 0.875rem;
}

:deep(.prose-compact li) {
  margin-top: 0.125rem;
  margin-bottom: 0.125rem;
}

:deep(.prose-compact blockquote) {
  border-left: 3px solid var(--border-main);
  padding-left: 0.75rem;
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
  font-style: italic;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

:deep(.prose-compact table) {
  width: 100%;
  border-collapse: collapse;
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
  font-size: 0.75rem;
}

:deep(.prose-compact th) {
  background-color: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-main);
  padding: 0.5rem;
  text-align: left;
  font-weight: 600;
}

:deep(.prose-compact td) {
  border: 1px solid var(--border-light);
  padding: 0.5rem;
}

:deep(.prose-compact code) {
  background-color: var(--fill-tsp-gray-main);
  padding: 0.0625rem 0.25rem;
  border-radius: 0.1875rem;
  font-size: 0.8125em;
}

:deep(.prose-compact pre) {
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
  padding: 0.75rem;
  font-size: 0.75rem;
}

:deep(.prose-compact hr) {
  border-color: var(--border-main);
  margin-top: 1rem;
  margin-bottom: 1rem;
}

:deep(.prose-compact img) {
  max-width: 100%;
  height: auto;
  border-radius: 0.375rem;
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
}

:deep(.prose-compact strong) {
  color: var(--text-primary);
  font-weight: 600;
}
</style>
