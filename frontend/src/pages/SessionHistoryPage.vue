<template>
  <div class="library-page">
    <!-- Header -->
    <header class="library-header">
      <h1 class="library-title">Library</h1>

      <!-- Toolbar -->
      <div class="library-toolbar">
        <div class="toolbar-left">
          <!-- Category dropdown -->
          <div class="category-dropdown" ref="dropdownRef">
            <button class="toolbar-btn" @click="dropdownOpen = !dropdownOpen">
              <SlidersHorizontal :size="14" />
              {{ categoryLabels[category] }}
              <ChevronDown :size="12" class="chevron" />
            </button>
            <Transition name="dropdown">
              <div v-if="dropdownOpen" class="dropdown-menu">
                <button
                  v-for="cat in categories"
                  :key="cat.value"
                  class="dropdown-item"
                  :class="{ active: category === cat.value }"
                  @click="category = cat.value; dropdownOpen = false"
                >
                  <component :is="cat.icon" :size="15" />
                  {{ cat.label }}
                </button>
              </div>
            </Transition>
          </div>

          <!-- Favorites toggle -->
          <button
            class="toolbar-btn"
            :class="{ 'is-active': showFavoritesOnly }"
            @click="showFavoritesOnly = !showFavoritesOnly"
          >
            <Star :size="14" :fill="showFavoritesOnly ? 'currentColor' : 'none'" />
            My favorites
          </button>
        </div>

        <div class="toolbar-right">
          <!-- Search -->
          <div class="search-field" :class="{ focused: searchFocused }">
            <Search :size="14" class="search-icon" />
            <input
              v-model="searchQuery"
              type="text"
              placeholder="Search files"
              @focus="searchFocused = true"
              @blur="searchFocused = false"
            />
            <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''">
              <X :size="12" />
            </button>
          </div>

          <!-- View toggle -->
          <div class="view-toggle">
            <button
              :class="{ active: viewMode === 'grid' }"
              @click="viewMode = 'grid'"
              aria-label="Grid view"
            >
              <LayoutGrid :size="16" />
            </button>
            <button
              :class="{ active: viewMode === 'list' }"
              @click="viewMode = 'list'"
              aria-label="List view"
            >
              <List :size="16" />
            </button>
          </div>
        </div>
      </div>
    </header>

    <!-- Content -->
    <main class="library-content">
      <!-- Loading -->
      <div v-if="isLoading" class="library-loading">
        <div v-for="i in 3" :key="i" class="skeleton-section">
          <div class="skeleton-heading" />
          <div class="skeleton-rows">
            <div v-for="j in (i === 1 ? 1 : 3)" :key="j" class="skeleton-row" />
          </div>
        </div>
      </div>

      <!-- Empty -->
      <div v-else-if="groupedBySession.length === 0" class="library-empty">
        <div class="empty-icon-wrap">
          <FolderOpen :size="36" />
        </div>
        <h3 v-if="searchQuery || category !== 'all' || showFavoritesOnly">No matching files</h3>
        <h3 v-else>No files yet</h3>
        <p v-if="searchQuery || category !== 'all' || showFavoritesOnly">Try adjusting your search or filters</p>
        <p v-else>Files and reports created during tasks will appear here</p>
      </div>

      <!-- File sections grouped by session -->
      <template v-else>
        <section
          v-for="group in groupedBySession"
          :key="group.sessionId"
          class="file-section"
        >
          <!-- Section header: session title + date -->
          <div class="section-header">
            <h2
              class="section-title"
              @click="$router.push(`/chat/${group.sessionId}`)"
            >
              {{ group.sessionTitle }}
            </h2>
            <span class="section-date">{{ formatGroupDate(group.sessionLatestAt) }}</span>
          </div>

          <!-- Grid view -->
          <div v-if="viewMode === 'grid'" class="file-grid">
            <div
              v-for="file in visibleFiles(group)"
              :key="file.file_id"
              class="file-card"
              @click="handlePreview(file)"
            >
              <div class="card-top">
                <FileTypeIcon :filename="file.filename" :size="20" />
                <span class="card-name">{{ file.metadata?.title || file.filename }}</span>
                <button class="card-menu" @click.stop="toggleMenu(file.file_id)">
                  <MoreHorizontal :size="16" />
                </button>
                <!-- Favorite star -->
                <button
                  class="card-star"
                  :class="{ favorited: isFavorite(file.file_id) }"
                  @click.stop="toggleFavorite(file.file_id)"
                >
                  <Star :size="13" :fill="isFavorite(file.file_id) ? 'currentColor' : 'none'" />
                </button>
              </div>
              <div class="card-body">
                <img
                  v-if="isImageFile(file.filename)"
                  :src="file.file_url || getFileUrl(file.file_id)"
                  :alt="file.filename"
                  class="card-image"
                  loading="lazy"
                />
                <div v-else-if="file.metadata?.title && file.metadata?.is_report" class="card-text-preview">
                  {{ file.metadata.title }}
                </div>
                <div v-else class="card-icon-fallback">
                  <FileTypeIcon :filename="file.filename" :size="28" />
                </div>
              </div>
              <!-- File action menu -->
              <Transition name="dropdown">
                <div v-if="activeMenu === file.file_id" class="card-action-menu" @click.stop>
                  <button @click="handlePreview(file); activeMenu = null"><Eye :size="14" /> Preview</button>
                  <button @click="handleDownload(file); activeMenu = null"><Download :size="14" /> Download</button>
                  <button @click="$router.push(`/chat/${file.session_id}`); activeMenu = null"><ExternalLink :size="14" /> Open session</button>
                </div>
              </Transition>
            </div>
          </div>

          <!-- List view -->
          <div v-else class="file-list">
            <div
              v-for="file in visibleFiles(group)"
              :key="file.file_id"
              class="file-row"
              @click="handlePreview(file)"
            >
              <FileTypeIcon :filename="file.filename" :size="20" />
              <span class="row-name">{{ file.metadata?.title || file.filename }}</span>
              <button
                class="row-star"
                :class="{ favorited: isFavorite(file.file_id) }"
                @click.stop="toggleFavorite(file.file_id)"
              >
                <Star :size="13" :fill="isFavorite(file.file_id) ? 'currentColor' : 'none'" />
              </button>
              <button class="row-menu" @click.stop="toggleMenu(file.file_id)">
                <MoreHorizontal :size="16" />
              </button>
              <Transition name="dropdown">
                <div v-if="activeMenu === file.file_id" class="row-action-menu" @click.stop>
                  <button @click="handlePreview(file); activeMenu = null"><Eye :size="14" /> Preview</button>
                  <button @click="handleDownload(file); activeMenu = null"><Download :size="14" /> Download</button>
                  <button @click="$router.push(`/chat/${file.session_id}`); activeMenu = null"><ExternalLink :size="14" /> Open session</button>
                </div>
              </Transition>
            </div>
          </div>

          <!-- "N more files" expander -->
          <button
            v-if="group.files.length > 3 && !expandedGroups.has(group.sessionId)"
            class="more-btn"
            @click="expandedGroups.add(group.sessionId)"
          >
            {{ group.files.length - 3 }} more files
            <ChevronDown :size="14" />
          </button>
        </section>
      </template>
    </main>

    <!-- Close any open menus -->
    <Teleport to="body">
      <div v-if="activeMenu" class="menu-backdrop" @click="activeMenu = null" />
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import {
  Search, X, Star, ChevronDown, SlidersHorizontal,
  LayoutGrid, List, FolderOpen, MoreHorizontal,
  Eye, Download, ExternalLink,
  FileText, Image, Code2, Archive, FileBarChart, Files,
} from 'lucide-vue-next'
import FileTypeIcon from '@/components/FileTypeIcon.vue'
import { useLibraryFiles, type FileCategory, type SessionFileGroup } from '@/composables/useLibraryFiles'
import type { LibraryFileItem } from '@/api/file'
import { getFileUrl, downloadFile as downloadFileApi } from '@/api/file'
import { useFilePanel } from '@/composables/useFilePanel'

const { showFilePanel } = useFilePanel()

const {
  isLoading,
  searchQuery,
  category,
  viewMode,
  showFavoritesOnly,
  groupedBySession,
  fetchFiles,
  toggleFavorite,
  isFavorite,
} = useLibraryFiles()

const searchFocused = ref(false)
const dropdownOpen = ref(false)
const dropdownRef = ref<HTMLElement | null>(null)
const expandedGroups = ref(new Set<string>())
const activeMenu = ref<string | null>(null)

const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp'])

const categoryLabels: Record<FileCategory, string> = {
  all: 'All',
  reports: 'Reports',
  documents: 'Documents',
  images: 'Images',
  code: 'Code',
  archives: 'Archives',
}

const categories: { value: FileCategory; label: string; icon: typeof Files }[] = [
  { value: 'all', label: 'All', icon: Files },
  { value: 'reports', label: 'Reports', icon: FileBarChart },
  { value: 'documents', label: 'Documents', icon: FileText },
  { value: 'images', label: 'Images', icon: Image },
  { value: 'code', label: 'Code', icon: Code2 },
  { value: 'archives', label: 'Archives', icon: Archive },
]

const MS_PER_DAY = 86_400_000
const MS_PER_WEEK = 7 * MS_PER_DAY

function formatGroupDate(timestamp: number | null): string {
  if (!timestamp) return ''
  const date = new Date(timestamp * 1000)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const dateDay = new Date(date.getFullYear(), date.getMonth(), date.getDate())

  if (dateDay.getTime() === today.getTime()) return 'Today'
  if (dateDay.getTime() === today.getTime() - MS_PER_DAY) return 'Yesterday'
  if (now.getTime() - date.getTime() < MS_PER_WEEK) {
    return date.toLocaleDateString(undefined, { weekday: 'long' })
  }
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function visibleFiles(group: SessionFileGroup): LibraryFileItem[] {
  if (expandedGroups.value.has(group.sessionId) || group.files.length <= 3) {
    return group.files
  }
  return group.files.slice(0, 3)
}

function isImageFile(filename: string): boolean {
  const dot = filename.lastIndexOf('.')
  return dot > 0 && IMAGE_EXTS.has(filename.slice(dot + 1).toLowerCase())
}

function handlePreview(file: LibraryFileItem) {
  showFilePanel(file)
}

async function handleDownload(file: LibraryFileItem) {
  try {
    const blob = await downloadFileApi(file.file_id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = file.filename
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('Download failed:', e)
  }
}

function toggleMenu(fileId: string) {
  activeMenu.value = activeMenu.value === fileId ? null : fileId
}

function handleClickOutside(e: MouseEvent) {
  if (dropdownRef.value && !dropdownRef.value.contains(e.target as Node)) {
    dropdownOpen.value = false
  }
}

onMounted(() => {
  fetchFiles()
  document.addEventListener('click', handleClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
.library-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  flex: 1;
  min-width: 0;
  background: var(--background-gray-main, var(--background-main));
}

/* ════════════════════════════════════════════
   HEADER
   ════════════════════════════════════════════ */
.library-header {
  padding: 28px 40px 0;
  flex-shrink: 0;
}

.library-title {
  margin: 0 0 20px;
  font-size: 21px;
  font-weight: 650;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

/* ── Toolbar ── */
.library-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border-color, rgba(0, 0, 0, 0.08));
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.12));
  border-radius: 8px;
  background: var(--background-menu-white, #fff);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

:global(.dark) .toolbar-btn {
  background: var(--bolt-elements-bg-depth-1);
  border-color: var(--border-main);
}

.toolbar-btn:hover {
  border-color: rgba(0, 0, 0, 0.2);
  color: var(--text-primary);
}

.toolbar-btn.is-active {
  border-color: #ca8a04;
  color: #ca8a04;
  background: rgba(234, 179, 8, 0.06);
}

.chevron {
  opacity: 0.5;
}

/* ── Category dropdown ── */
.category-dropdown {
  position: relative;
}

.dropdown-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 50;
  min-width: 170px;
  padding: 4px;
  background: var(--background-menu-white, #fff);
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));
  border-radius: 10px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
}

:global(.dark) .dropdown-menu {
  background: var(--bolt-elements-bg-depth-1);
  border-color: var(--border-main);
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 12px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.1s ease;
}

.dropdown-item:hover {
  background: var(--fill-tsp-gray-main, rgba(0, 0, 0, 0.04));
}

.dropdown-item.active {
  font-weight: 600;
  color: var(--accent-color, #2563eb);
}

/* ── Search ── */
.search-field {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 12px;
  min-width: 180px;
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.12));
  border-radius: 8px;
  background: var(--background-menu-white, #fff);
  transition: border-color 0.15s ease;
}

:global(.dark) .search-field {
  background: var(--bolt-elements-bg-depth-1);
  border-color: var(--border-main);
}

.search-field.focused {
  border-color: var(--accent-color, #2563eb);
}

.search-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.search-field input {
  border: none;
  background: transparent;
  outline: none;
  font-size: 13px;
  color: var(--text-primary);
  width: 100%;
}

.search-field input::placeholder {
  color: var(--text-tertiary);
}

.search-clear {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.06);
  color: var(--text-tertiary);
  cursor: pointer;
  flex-shrink: 0;
}

/* ── View toggle ── */
.view-toggle {
  display: flex;
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.12));
  border-radius: 8px;
  overflow: hidden;
}

:global(.dark) .view-toggle {
  border-color: var(--border-main);
}

.view-toggle button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 32px;
  padding: 0;
  border: none;
  background: var(--background-menu-white, #fff);
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.1s ease;
}

:global(.dark) .view-toggle button {
  background: var(--bolt-elements-bg-depth-1);
}

.view-toggle button:first-child {
  border-right: 1px solid var(--border-color, rgba(0, 0, 0, 0.08));
}

.view-toggle button.active {
  color: var(--text-primary);
  background: var(--fill-tsp-gray-main, rgba(0, 0, 0, 0.04));
}

/* ════════════════════════════════════════════
   CONTENT
   ════════════════════════════════════════════ */
.library-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px 40px 48px;
}

/* ── File sections ── */
.file-section {
  padding: 24px 0;
  border-bottom: 1px solid var(--border-color, rgba(0, 0, 0, 0.06));
}

.file-section:last-child {
  border-bottom: none;
}

.section-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 14px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  cursor: pointer;
  transition: color 0.1s ease;
}

.section-title:hover {
  color: var(--accent-color, #2563eb);
}

.section-date {
  font-size: 13px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

/* ── Grid ── */
.file-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}

.file-card {
  position: relative;
  background: var(--background-menu-white, #fff);
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.08));
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

:global(.dark) .file-card {
  background: var(--bolt-elements-bg-depth-1);
  border-color: var(--border-main);
}

.file-card:hover {
  border-color: rgba(0, 0, 0, 0.16);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.card-top {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px 8px;
}

.card-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-menu,
.card-star {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s ease, color 0.12s ease;
  flex-shrink: 0;
}

.file-card:hover .card-menu,
.file-card:hover .card-star,
.card-star.favorited {
  opacity: 1;
}

.card-star.favorited {
  color: #eab308;
}

.card-menu:hover,
.card-star:hover {
  background: rgba(0, 0, 0, 0.04);
}

.card-body {
  height: 150px;
  margin: 0 8px 8px;
  border-radius: 8px;
  overflow: hidden;
  background: var(--fill-tsp-gray-main, #f7f7f7);
}

:global(.dark) .card-body {
  background: var(--bolt-elements-bg-depth-2);
}

.card-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.card-text-preview {
  padding: 12px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-secondary);
  overflow: hidden;
  height: 100%;
}

.card-icon-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  opacity: 0.25;
}

.card-action-menu {
  position: absolute;
  top: 42px;
  right: 10px;
  z-index: 30;
  min-width: 150px;
  padding: 4px;
  background: var(--background-menu-white, #fff);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
}

:global(.dark) .card-action-menu {
  background: var(--bolt-elements-bg-depth-1);
  border-color: var(--border-main);
}

.card-action-menu button {
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
}

.card-action-menu button:hover {
  background: var(--fill-tsp-gray-main, rgba(0, 0, 0, 0.04));
}

/* ── List ── */
.file-list {
  display: flex;
  flex-direction: column;
}

.file-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 11px 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.1s ease;
  position: relative;
}

.file-row:hover {
  background: var(--fill-tsp-gray-main, rgba(0, 0, 0, 0.03));
}

.row-name {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.row-star,
.row-menu {
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
  transition: opacity 0.1s ease;
  flex-shrink: 0;
}

.file-row:hover .row-star,
.file-row:hover .row-menu,
.row-star.favorited {
  opacity: 1;
}

.row-star.favorited {
  color: #eab308;
}

.row-star:hover,
.row-menu:hover {
  background: rgba(0, 0, 0, 0.05);
}

.row-action-menu {
  position: absolute;
  top: 100%;
  right: 8px;
  z-index: 30;
  min-width: 150px;
  padding: 4px;
  background: var(--background-menu-white, #fff);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
}

:global(.dark) .row-action-menu {
  background: var(--bolt-elements-bg-depth-1);
  border-color: var(--border-main);
}

.row-action-menu button {
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
}

.row-action-menu button:hover {
  background: var(--fill-tsp-gray-main, rgba(0, 0, 0, 0.04));
}

/* ── More button ── */
.more-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 0;
  margin-top: 4px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 13px;
  cursor: pointer;
}

.more-btn:hover {
  color: var(--text-primary);
}

/* ── Loading ── */
.library-loading {
  display: flex;
  flex-direction: column;
  gap: 32px;
  padding-top: 24px;
}

.skeleton-heading {
  width: 220px;
  height: 15px;
  border-radius: 4px;
  background: var(--fill-tsp-gray-main, rgba(0, 0, 0, 0.06));
  margin-bottom: 14px;
  animation: pulse 1.4s ease-in-out infinite;
}

.skeleton-rows {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.skeleton-row {
  height: 44px;
  border-radius: 8px;
  background: var(--fill-tsp-gray-main, rgba(0, 0, 0, 0.04));
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 0.8; }
}

/* ── Empty ── */
.library-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 24px;
  text-align: center;
  gap: 8px;
}

.empty-icon-wrap {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--fill-tsp-gray-main, rgba(0, 0, 0, 0.04));
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  margin-bottom: 8px;
}

.library-empty h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.library-empty p {
  margin: 0;
  font-size: 14px;
  color: var(--text-tertiary);
}

/* ── Backdrop ── */
.menu-backdrop {
  position: fixed;
  inset: 0;
  z-index: 25;
}

/* ── Transitions ── */
.dropdown-enter-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.dropdown-leave-active {
  transition: opacity 0.08s ease, transform 0.08s ease;
}
.dropdown-enter-from {
  opacity: 0;
  transform: translateY(-4px);
}
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-2px);
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .library-header {
    padding: 20px 16px 0;
  }

  .library-toolbar {
    flex-wrap: wrap;
  }

  .library-content {
    padding: 8px 16px 32px;
  }

  .search-field {
    min-width: 0;
    flex: 1;
  }

  .file-grid {
    grid-template-columns: 1fr;
  }

  .row-star,
  .row-menu {
    opacity: 1;
  }
}
</style>
