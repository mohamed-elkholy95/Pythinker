<template>
  <div class="library-file-card" :class="{ 'list-mode': listMode }" @click="$emit('preview', file)">
    <!-- Favorite star -->
    <button
      class="favorite-btn"
      :class="{ 'is-favorited': isFavorited }"
      @click.stop="$emit('toggleFavorite', file.file_id)"
      :aria-label="isFavorited ? 'Remove from favorites' : 'Add to favorites'"
    >
      <Star :size="14" :fill="isFavorited ? 'currentColor' : 'none'" />
    </button>

    <!-- Actions menu -->
    <button class="actions-btn" @click.stop="showMenu = !showMenu" aria-label="File actions">
      <MoreHorizontal :size="16" />
    </button>
    <div v-if="showMenu" class="actions-menu" @click.stop>
      <button @click="handleAction('preview')"><Eye :size="14" /> Preview</button>
      <button @click="handleAction('download')"><Download :size="14" /> Download</button>
      <button @click="handleAction('open')"><ExternalLink :size="14" /> Open session</button>
    </div>

    <!-- Grid mode: icon + preview -->
    <template v-if="!listMode">
      <div class="card-header">
        <FileTypeIcon :filename="file.filename" :size="18" />
        <span class="card-filename">{{ displayName }}</span>
      </div>
      <div class="card-preview">
        <!-- Image preview -->
        <img v-if="isImage" :src="fileUrl" :alt="file.filename" class="preview-image" loading="lazy" />
        <!-- Text preview -->
        <div v-else-if="previewText" class="preview-text">{{ previewText }}</div>
        <!-- Fallback icon -->
        <div v-else class="preview-fallback">
          <FileTypeIcon :filename="file.filename" :size="32" />
        </div>
      </div>
    </template>

    <!-- List mode: compact row -->
    <template v-else>
      <FileTypeIcon :filename="file.filename" :size="20" />
      <span class="list-filename">{{ displayName }}</span>
    </template>
  </div>
  <!-- Close menu on outside click -->
  <Teleport to="body">
    <div v-if="showMenu" class="menu-backdrop" @click="showMenu = false" />
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Star, MoreHorizontal, Eye, Download, ExternalLink } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import FileTypeIcon from '@/components/FileTypeIcon.vue'
import { getFileUrl, downloadFile as downloadFileApi } from '@/api/file'
import type { LibraryFileItem } from '@/api/file'

const props = defineProps<{
  file: LibraryFileItem
  isFavorited: boolean
  listMode?: boolean
}>()

const emit = defineEmits<{
  preview: [file: LibraryFileItem]
  toggleFavorite: [fileId: string]
}>()

const router = useRouter()
const showMenu = ref(false)

const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp'])
const TEXT_EXTS = new Set(['md', 'txt', 'py', 'js', 'ts', 'json', 'yaml', 'yml', 'css', 'html', 'csv', 'sh'])

const ext = computed(() => {
  const dot = props.file.filename.lastIndexOf('.')
  return dot > 0 ? props.file.filename.slice(dot + 1).toLowerCase() : ''
})

const isImage = computed(() => IMAGE_EXTS.has(ext.value))

const fileUrl = computed(() => props.file.file_url || getFileUrl(props.file.file_id))

const displayName = computed(() => {
  if (props.file.metadata?.title) return props.file.metadata.title
  return props.file.filename
})

const previewText = computed(() => {
  if (!TEXT_EXTS.has(ext.value)) return null
  // For reports, show metadata title as preview hint
  if (props.file.metadata?.is_report && props.file.metadata?.title) {
    return props.file.metadata.title
  }
  return null
})

async function handleAction(action: string) {
  showMenu.value = false
  if (action === 'preview') {
    emit('preview', props.file)
  } else if (action === 'download') {
    try {
      const blob = await downloadFileApi(props.file.file_id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = props.file.filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('Download failed:', e)
    }
  } else if (action === 'open') {
    router.push(`/chat/${props.file.session_id}`)
  }
}
</script>

<style scoped>
.library-file-card {
  position: relative;
  background: var(--background-menu-white, #fff);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

:global(.dark) .library-file-card {
  border-color: var(--border-main);
  background: var(--bolt-elements-bg-depth-1);
}

.library-file-card:hover {
  border-color: rgba(0, 0, 0, 0.15);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

:global(.dark) .library-file-card:hover {
  border-color: var(--border-light);
}

/* ── Grid mode ── */
.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px 6px;
}

.card-filename {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.card-preview {
  height: 140px;
  margin: 0 8px 8px;
  border-radius: 6px;
  overflow: hidden;
  background: var(--fill-tsp-gray-main, #f5f5f5);
}

:global(.dark) .card-preview {
  background: var(--bolt-elements-bg-depth-2);
}

.preview-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-text {
  padding: 8px 10px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--text-secondary);
  overflow: hidden;
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.preview-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  opacity: 0.3;
}

/* ── List mode ── */
.library-file-card.list-mode {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-radius: 8px;
}

.list-filename {
  font-size: 14px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

/* ── Favorite button ── */
.favorite-btn {
  position: absolute;
  top: 8px;
  right: 36px;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease, color 0.15s ease;
}

.library-file-card:hover .favorite-btn,
.favorite-btn.is-favorited {
  opacity: 1;
}

.favorite-btn.is-favorited {
  color: #eab308;
}

.favorite-btn:hover {
  background: rgba(0, 0, 0, 0.05);
}

/* ── Actions button ── */
.actions-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.library-file-card:hover .actions-btn {
  opacity: 1;
}

.actions-btn:hover {
  background: rgba(0, 0, 0, 0.05);
}

.library-file-card.list-mode .favorite-btn {
  position: static;
  opacity: 0;
  margin-left: auto;
  flex-shrink: 0;
}

.library-file-card.list-mode .actions-btn {
  position: static;
  opacity: 0;
  flex-shrink: 0;
}

.library-file-card.list-mode:hover .favorite-btn,
.library-file-card.list-mode .favorite-btn.is-favorited,
.library-file-card.list-mode:hover .actions-btn {
  opacity: 1;
}

/* ── Actions menu ── */
.actions-menu {
  position: absolute;
  top: 38px;
  right: 8px;
  z-index: 20;
  background: var(--background-menu-white, #fff);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  padding: 4px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  min-width: 140px;
}

:global(.dark) .actions-menu {
  background: var(--bolt-elements-bg-depth-1);
  border-color: var(--border-main);
}

.actions-menu button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  text-align: left;
}

.actions-menu button:hover {
  background: var(--fill-tsp-gray-main);
}

.menu-backdrop {
  position: fixed;
  inset: 0;
  z-index: 15;
}
</style>
