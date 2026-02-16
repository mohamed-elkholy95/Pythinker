<script setup lang="ts">
import { ref, watch, computed, onBeforeUnmount } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import Highlight from '@tiptap/extension-highlight'
import TaskList from '@tiptap/extension-task-list'
import TaskItem from '@tiptap/extension-task-item'
import TextAlign from '@tiptap/extension-text-align'
import Typography from '@tiptap/extension-typography'
import Underline from '@tiptap/extension-underline'
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight'
import { common, createLowlight } from 'lowlight'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { FileInfo } from '@/api/file'
import { downloadFile } from '@/api/file'

const props = defineProps<{
  file: FileInfo
}>()

const fileContent = ref('')
const isLoading = ref(true)

// Create lowlight instance for syntax highlighting
const lowlight = createLowlight(common)

// Determine if file is markdown
const isMarkdown = computed(() => {
  const ext = props.file.filename.split('.').pop()?.toLowerCase()
  return ext === 'md' || ext === 'markdown'
})

// Convert content to HTML (markdown → HTML, plain text → pre-wrapped)
const htmlContent = computed(() => {
  if (!fileContent.value) return ''

  if (isMarkdown.value) {
    // Render markdown
    const rawHtml = marked.parse(fileContent.value, { async: false }) as string
    return DOMPurify.sanitize(rawHtml)
  } else {
    // Render plain text with preserved formatting
    const escaped = fileContent.value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
    return `<pre style="white-space: pre-wrap; word-wrap: break-word; font-family: monospace;">${escaped}</pre>`
  }
})

// Initialize TipTap editor
const editor = useEditor({
  content: htmlContent.value,
  editable: false,
  extensions: [
    StarterKit.configure({
      codeBlock: false,
    }),
    Link.configure({
      openOnClick: true,
      HTMLAttributes: {
        class: 'text-blue-600 hover:underline cursor-pointer dark:text-blue-400',
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
})

// Load file content
const loadFileContent = async (fileId: string) => {
  if (!fileId) return

  isLoading.value = true
  try {
    const blob = await downloadFile(fileId)
    const text = await blob.text()
    fileContent.value = text
  } catch (error) {
    fileContent.value = '(Failed to load file content)'
    console.error('Failed to load file:', error)
  } finally {
    isLoading.value = false
  }
}

// Watch for file changes
watch(() => props.file.file_id, loadFileContent, { immediate: true })

// Update editor content when HTML changes
watch(htmlContent, (newContent) => {
  if (editor.value && newContent !== editor.value.getHTML()) {
    editor.value.commands.setContent(newContent)
  }
})

// Cleanup
onBeforeUnmount(() => {
  editor.value?.destroy()
})
</script>

<template>
  <div class="tiptap-file-preview h-full overflow-y-auto bg-[var(--background-white-main)]">
    <div v-if="isLoading" class="flex items-center justify-center h-full">
      <div class="text-[var(--text-tertiary)]">Loading...</div>
    </div>
    <div v-else class="px-8 py-6">
      <EditorContent
        :editor="editor"
        class="prose prose-gray max-w-4xl mx-auto dark:prose-invert"
      />
    </div>
  </div>
</template>

<style scoped>
.tiptap-file-preview::-webkit-scrollbar {
  width: 6px;
}

.tiptap-file-preview::-webkit-scrollbar-track {
  background: transparent;
}

.tiptap-file-preview::-webkit-scrollbar-thumb {
  background: var(--fill-tsp-gray-dark);
  border-radius: 3px;
}

.tiptap-file-preview::-webkit-scrollbar-thumb:hover {
  background: var(--border-dark);
}

/* Firefox */
.tiptap-file-preview {
  scrollbar-width: thin;
  scrollbar-color: var(--fill-tsp-gray-dark) transparent;
}

/* TipTap prose styling */
:deep(.ProseMirror) {
  outline: none;
  padding: 0;
}

:deep(.ProseMirror pre) {
  background: var(--fill-tsp-gray-main);
  border-radius: 8px;
  padding: 1rem;
  overflow-x: auto;
}

:deep(.ProseMirror code) {
  background: var(--fill-tsp-gray-main);
  border-radius: 4px;
  padding: 0.2em 0.4em;
  font-size: 0.9em;
}

:deep(.ProseMirror pre code) {
  background: none;
  padding: 0;
}
</style>
