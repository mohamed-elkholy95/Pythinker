<template>
  <div class="pdf-preview">
    <div class="pdf-preview__toolbar">
      <div class="pdf-preview__meta">
        <p class="pdf-preview__title">{{ props.file.filename }}</p>
        <p class="pdf-preview__status">{{ statusText }}</p>
      </div>

      <div class="pdf-preview__actions">
        <a
          v-if="directPdfUrl"
          class="pdf-preview__action"
          :href="directPdfUrl"
          target="_blank"
          rel="noreferrer"
        >
          Open in new tab
        </a>
        <a
          v-if="directPdfUrl"
          class="pdf-preview__action pdf-preview__action--secondary"
          :href="directPdfUrl"
          :download="props.file.filename"
        >
          Download
        </a>
      </div>
    </div>

    <div
      ref="viewerRef"
      class="pdf-preview__viewer"
      :class="{ 'pdf-preview__viewer--loading': isLoading }"
    >
      <div v-if="isLoading" class="pdf-preview__placeholder">
        Loading PDF preview...
      </div>
      <div v-else-if="errorMessage" class="pdf-preview__placeholder pdf-preview__placeholder--error">
        <p>{{ errorMessage }}</p>
        <a v-if="directPdfUrl" :href="directPdfUrl" target="_blank" rel="noreferrer">
          Open original PDF
        </a>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { downloadFile, getFileUrl } from '../../api/file'
import type { FileInfo } from '../../api/file'
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist/build/pdf.mjs'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

const props = defineProps<{
  file: FileInfo
}>()

const viewerRef = ref<HTMLDivElement | null>(null)
const isLoading = ref(false)
const errorMessage = ref('')

const directPdfUrl = computed(() => {
  if (!props.file?.file_id) return ''
  return props.file.file_url || getFileUrl(props.file.file_id)
})

const statusText = computed(() => {
  if (isLoading.value) return 'Rendering preview...'
  if (errorMessage.value) return 'Preview failed'
  return 'Rendered with PDF.js'
})

let renderToken = 0
let workerConfigured = false

function clearViewer(): void {
  const viewer = viewerRef.value
  if (!viewer) return
  viewer.replaceChildren()
}

function configureWorker(): void {
  if (workerConfigured) return
  GlobalWorkerOptions.workerSrc = pdfWorkerUrl
  workerConfigured = true
}

async function renderPdfPreview(file: FileInfo): Promise<void> {
  const token = ++renderToken
  isLoading.value = true
  errorMessage.value = ''
  clearViewer()

  if (!file?.file_id) {
    isLoading.value = false
    errorMessage.value = 'Missing PDF file identifier.'
    return
  }

  try {
    configureWorker()
    const pdfBlob = await downloadFile(file.file_id)
    const pdfData = await pdfBlob.arrayBuffer()

    const loadingTask = getDocument({ data: pdfData })
    const pdfDocument = await loadingTask.promise
    if (token !== renderToken) return

    await nextTick()
    const viewer = viewerRef.value
    if (!viewer) {
      return
    }

    const availableWidth = Math.max(viewer.clientWidth - 32, 320)
    for (let pageNumber = 1; pageNumber <= pdfDocument.numPages; pageNumber += 1) {
      if (token !== renderToken) return

      const page = await pdfDocument.getPage(pageNumber)
      const baseViewport = page.getViewport({ scale: 1 })
      const fitScale = availableWidth / baseViewport.width
      const scale = Math.min(2, Math.max(0.6, fitScale))
      const viewport = page.getViewport({ scale })

      const pageWrap = document.createElement('div')
      pageWrap.className = 'pdf-preview__page'

      const pageLabel = document.createElement('div')
      pageLabel.className = 'pdf-preview__page-label'
      pageLabel.textContent = `Page ${pageNumber} of ${pdfDocument.numPages}`
      pageWrap.appendChild(pageLabel)

      const canvas = document.createElement('canvas')
      const context = canvas.getContext('2d')
      if (!context) {
        throw new Error('Canvas rendering is not available in this browser.')
      }

      const devicePixelRatio = window.devicePixelRatio || 1
      canvas.width = Math.floor(viewport.width * devicePixelRatio)
      canvas.height = Math.floor(viewport.height * devicePixelRatio)
      canvas.style.width = `${Math.floor(viewport.width)}px`
      canvas.style.height = `${Math.floor(viewport.height)}px`

      const canvasContext = canvas.getContext('2d')
      if (!canvasContext) {
        throw new Error('Canvas rendering is not available in this browser.')
      }
      canvasContext.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0)

      pageWrap.appendChild(canvas)
      viewer.appendChild(pageWrap)

      await page.render({ canvasContext, viewport }).promise
      page.cleanup()
    }
  } catch (error) {
    if (token !== renderToken) return
    const message = error instanceof Error ? error.message : 'Unknown PDF rendering error.'
    errorMessage.value = `Unable to render PDF preview: ${message}`
  } finally {
    if (token === renderToken) {
      isLoading.value = false
    }
  }
}

watch(
  () => props.file.file_id,
  (fileId) => {
    if (!fileId) {
      renderToken += 1
      clearViewer()
      errorMessage.value = 'Missing PDF file identifier.'
      isLoading.value = false
      return
    }

    void renderPdfPreview(props.file)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  renderToken += 1
  clearViewer()
})
</script>

<style scoped>
.pdf-preview {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  width: 100%;
  gap: 12px;
}

.pdf-preview__toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-main);
  background: var(--background-menu-white);
}

:global(.dark) .pdf-preview__toolbar {
  background: var(--bolt-elements-bg-depth-1);
}

.pdf-preview__meta {
  min-width: 0;
}

.pdf-preview__title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-word;
}

.pdf-preview__status {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.pdf-preview__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.pdf-preview__action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
  color: var(--text-onblack);
  background: var(--Button-primary-black);
}

.pdf-preview__action--secondary {
  color: var(--text-primary);
  background: var(--background-white-main);
  border: 1px solid var(--border-main);
}

.pdf-preview__viewer {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 16px;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(245, 246, 248, 0.92) 0%, rgba(233, 236, 241, 0.92) 100%);
}

:global(.dark) .pdf-preview__viewer {
  background: linear-gradient(180deg, rgba(24, 24, 24, 0.92) 0%, rgba(15, 15, 15, 0.92) 100%);
}

.pdf-preview__viewer--loading {
  display: grid;
  place-items: center;
}

.pdf-preview__placeholder {
  display: grid;
  gap: 8px;
  place-items: center;
  min-height: 240px;
  color: var(--text-secondary);
  font-size: 13px;
  text-align: center;
}

.pdf-preview__placeholder--error {
  color: var(--text-primary);
}

.pdf-preview__placeholder a {
  color: var(--Button-primary-black);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.pdf-preview__page {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0 auto 16px;
  padding: 14px;
  width: fit-content;
  border-radius: 14px;
  background: #ffffff;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
}

:global(.dark) .pdf-preview__page {
  background: #111111;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
}

.pdf-preview__page-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-secondary);
}

.pdf-preview__page canvas {
  display: block;
  max-width: 100%;
  height: auto;
}
</style>
