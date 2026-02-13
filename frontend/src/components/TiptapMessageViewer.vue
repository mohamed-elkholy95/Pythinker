<template>
  <div
    ref="contentRef"
    :class="['tiptap-message-viewer', compact ? 'tiptap-message-viewer--compact' : '']"
  >
    <EditorContent
      :editor="editor"
      :class="[
        'tiptap-message-prose',
        compact ? 'tiptap-message-prose--compact' : '',
      ]"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount, computed } from 'vue';
import { useEditor, EditorContent } from '@tiptap/vue-3';
import StarterKit from '@tiptap/starter-kit';
import Link from '@tiptap/extension-link';
import Image from '@tiptap/extension-image';
import Highlight from '@tiptap/extension-highlight';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
import TextAlign from '@tiptap/extension-text-align';
import Typography from '@tiptap/extension-typography';
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight';
import { common, createLowlight } from 'lowlight';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

const props = withDefaults(
  defineProps<{
    content: string;
    /** Render as compact (summary cards, etc.) */
    compact?: boolean;
  }>(),
  { compact: false }
);

const contentRef = ref<HTMLElement | null>(null);
const lowlight = createLowlight(common);

const htmlContent = computed(() => {
  if (!props.content) return '<p></p>';
  const rawHtml = marked.parse(props.content, { async: false }) as string;
  return DOMPurify.sanitize(rawHtml);
});

const editor = useEditor({
  content: htmlContent.value,
  editable: false,
  extensions: [
    StarterKit.configure({
      codeBlock: false,
      link: false,
    }),
    Link.configure({
      openOnClick: true,
      HTMLAttributes: {
        class: 'message-link',
        target: '_blank',
        rel: 'noopener noreferrer',
      },
    }),
    Image.configure({
      HTMLAttributes: {
        class: 'message-image',
      },
    }),
    Highlight.configure({ multicolor: true }),
    TaskList,
    TaskItem.configure({ nested: true }),
    TextAlign.configure({ types: ['heading', 'paragraph'] }),
    Typography,
    CodeBlockLowlight.configure({
      lowlight,
      HTMLAttributes: {
        class: 'message-code-block',
      },
    }),
  ],
  editorProps: {
    attributes: {
      class: 'focus:outline-none select-text',
    },
  },
});

watch(
  () => props.content,
  () => {
    if (editor.value && htmlContent.value !== editor.value.getHTML()) {
      editor.value.commands.setContent(htmlContent.value, false);
    }
  }
);

onBeforeUnmount(() => {
  editor.value?.destroy();
});

defineExpose({ contentRef });
</script>

<style scoped>
.tiptap-message-viewer {
  width: 100%;
  min-height: 1em;
}

.tiptap-message-viewer--compact {
  font-size: 0.9375rem;
}

.tiptap-message-prose {
  font-family: var(--font-sans);
  color: var(--text-primary);
  font-size: 15.5px;
  line-height: 1.65;
  letter-spacing: -0.003em;
  text-align: left;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  hyphens: auto;
  hyphenate-limit-chars: 6 3 2;
}

.tiptap-message-prose--compact {
  font-size: 14px;
  line-height: 1.55;
}

:deep(.tiptap) {
  outline: none;
  max-width: 72ch;
}

:deep(.tiptap p) {
  margin: 0.25em 0 0.5em;
  text-align: inherit;
}

:deep(.tiptap p:first-child) {
  margin-top: 0;
}

:deep(.tiptap p:last-child) {
  margin-bottom: 0;
}

:deep(.tiptap strong) {
  font-weight: 600;
  color: var(--text-primary);
}

:deep(.tiptap a) {
  color: var(--bolt-elements-item-contentAccent, #3b82f6);
  text-decoration: none;
}

:deep(.tiptap a:hover) {
  text-decoration: underline;
}

:deep(.tiptap ul),
:deep(.tiptap ol) {
  margin: 0.5em 0;
  padding-left: 1.5em;
  text-align: inherit;
}

:deep(.tiptap li) {
  margin: 0.25em 0;
}

:deep(.tiptap blockquote) {
  border-left: 4px solid var(--border-main);
  padding-left: 1em;
  margin: 0.75em 0;
  font-style: italic;
  color: var(--text-secondary);
  text-align: inherit;
}

:deep(.tiptap code) {
  background-color: var(--fill-tsp-white-light, #f5f5f5);
  padding: 0.125em 0.375em;
  border-radius: 4px;
  font-size: 0.9em;
  font-family: ui-monospace, monospace;
}

:deep(.tiptap pre) {
  margin: 0.75em 0;
  border-radius: 8px;
  overflow-x: auto;
}

:deep(.tiptap pre code) {
  background: none;
  padding: 0;
}

:deep(.message-code-block) {
  background-color: var(--fill-tsp-gray-main) !important;
  padding: 0.75rem 1rem !important;
  border-radius: 8px !important;
  font-size: 0.875rem !important;
  line-height: 1.5 !important;
}

:deep(.tiptap h1) {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 1em 0 0.5em;
  text-align: inherit;
}

:deep(.tiptap h2) {
  font-size: 1.25rem;
  font-weight: 600;
  margin: 0.875em 0 0.5em;
  text-align: inherit;
}

:deep(.tiptap h3) {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0.75em 0 0.375em;
  text-align: inherit;
}

:deep(.tiptap img) {
  max-width: 100%;
  height: auto;
  border-radius: 6px;
  margin: 0.5em 0;
}

/* Task list */
:deep(.tiptap ul[data-type="taskList"]) {
  list-style: none;
  padding-left: 0;
}

:deep(.tiptap ul[data-type="taskList"] li) {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
}

:deep(.tiptap ul[data-type="taskList"] li input[type="checkbox"]) {
  pointer-events: none;
  margin-top: 0.35em;
}
</style>
