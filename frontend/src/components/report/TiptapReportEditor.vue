<template>
  <div
    ref="contentRef"
    class="h-full overflow-y-auto px-8 py-6 bg-[var(--background-white-main)]"
    @scroll="$emit('scroll', $event)"
  >
    <EditorContent
      :editor="editor"
      class="prose prose-gray max-w-4xl mx-auto"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue';
import { useEditor, EditorContent } from '@tiptap/vue-3';
import StarterKit from '@tiptap/starter-kit';
import Link from '@tiptap/extension-link';
import Image from '@tiptap/extension-image';
import Highlight from '@tiptap/extension-highlight';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
import TextAlign from '@tiptap/extension-text-align';
import Typography from '@tiptap/extension-typography';
import Underline from '@tiptap/extension-underline';
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight';
import { common, createLowlight } from 'lowlight';

const props = defineProps<{
  content: string;
  editable?: boolean;
}>();

const _emit = defineEmits<{
  (e: 'scroll', event: Event): void;
}>();

const contentRef = ref<HTMLElement | null>(null);

// Create lowlight instance with common languages
const lowlight = createLowlight(common);

const editor = useEditor({
  content: props.content,
  editable: props.editable ?? false,
  extensions: [
    StarterKit.configure({
      codeBlock: false, // We use CodeBlockLowlight instead
    }),
    Link.configure({
      openOnClick: true,
      HTMLAttributes: {
        class: 'text-[#1a73e8] hover:underline cursor-pointer',
        target: '_blank',
        rel: 'noopener noreferrer',
      },
    }),
    Image.configure({
      HTMLAttributes: {
        class: 'max-w-full h-auto rounded-lg my-4',
      },
    }),
    Highlight.configure({
      multicolor: true,
    }),
    TaskList,
    TaskItem.configure({
      nested: true,
    }),
    TextAlign.configure({
      types: ['heading', 'paragraph'],
    }),
    Typography,
    Underline,
    CodeBlockLowlight.configure({
      lowlight,
      HTMLAttributes: {
        class: 'bg-[var(--fill-tsp-gray-main)] rounded-lg p-4 my-4 overflow-x-auto text-sm font-mono',
      },
    }),
  ],
  editorProps: {
    attributes: {
      class: 'focus:outline-none min-h-full',
    },
  },
});

// Watch for content changes
watch(() => props.content, (newContent) => {
  if (editor.value && newContent !== editor.value.getHTML()) {
    editor.value.commands.setContent(newContent, false);
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
</style>
