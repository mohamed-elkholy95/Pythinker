<template>
  <div class="library-files-view">
    <!-- Toolbar -->
    <div class="files-toolbar">
      <div class="toolbar-left">
        <!-- Category dropdown -->
        <div class="category-dropdown" ref="dropdownRef">
          <button class="category-btn" @click="dropdownOpen = !dropdownOpen">
            <SlidersHorizontal :size="14" />
            {{ categoryLabels[category] }}
            <ChevronDown :size="12" />
          </button>
          <div v-if="dropdownOpen" class="category-menu">
            <button
              v-for="cat in categories"
              :key="cat.value"
              class="category-option"
              :class="{ active: category === cat.value }"
              @click="category = cat.value; dropdownOpen = false"
            >
              <component :is="cat.icon" :size="14" />
              {{ cat.label }}
            </button>
          </div>
        </div>

        <!-- Favorites toggle -->
        <button
          class="favorites-btn"
          :class="{ active: showFavoritesOnly }"
          @click="showFavoritesOnly = !showFavoritesOnly"
        >
          <Star :size="14" :fill="showFavoritesOnly ? 'currentColor' : 'none'" />
          My favorites
        </button>
      </div>

      <div class="toolbar-right">
        <!-- Search -->
        <div class="search-box" :class="{ focused: searchFocused }">
          <Search :size="14" class="search-icon" />
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search files"
            class="search-input"
            @focus="searchFocused = true"
            @blur="searchFocused = false"
          />
          <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''">
            <X :size="12" />
          </button>
        </div>

        <!-- View mode toggle -->
        <div class="view-toggle">
          <button
            class="view-btn"
            :class="{ active: viewMode === 'grid' }"
            @click="viewMode = 'grid'"
            aria-label="Grid view"
          >
            <LayoutGrid :size="16" />
          </button>
          <button
            class="view-btn"
            :class="{ active: viewMode === 'list' }"
            @click="viewMode = 'list'"
            aria-label="List view"
          >
            <List :size="16" />
          </button>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="loading-state">
      <div v-for="i in 4" :key="i" class="skeleton-group">
        <div class="skeleton-title" />
        <div class="skeleton-cards">
          <div v-for="j in 3" :key="j" class="skeleton-card" />
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="groupedBySession.length === 0" class="empty-state">
      <FolderOpen :size="40" class="empty-icon" />
      <h3 v-if="searchQuery || category !== 'all' || showFavoritesOnly">No matching files</h3>
      <h3 v-else>No files yet</h3>
      <p v-if="searchQuery || category !== 'all' || showFavoritesOnly">Try adjusting your search or filters</p>
      <p v-else>Files created during tasks will appear here</p>
    </div>

    <!-- File groups by session -->
    <div v-else class="file-groups">
      <div v-for="group in groupedBySession" :key="group.sessionId" class="file-group">
        <div class="group-header">
          <h3 class="group-title" @click="openSession(group.sessionId)">{{ group.sessionTitle }}</h3>
          <span class="group-date">{{ formatGroupDate(group.sessionLatestAt) }}</span>
        </div>

        <!-- Grid view -->
        <div v-if="viewMode === 'grid'" class="files-grid">
          <LibraryFileCard
            v-for="file in visibleFiles(group)"
            :key="file.file_id"
            :file="file"
            :is-favorited="isFavorite(file.file_id)"
            @preview="handlePreview"
            @toggle-favorite="toggleFavorite"
          />
        </div>

        <!-- List view -->
        <div v-else class="files-list">
          <LibraryFileCard
            v-for="file in visibleFiles(group)"
            :key="file.file_id"
            :file="file"
            :is-favorited="isFavorite(file.file_id)"
            :list-mode="true"
            @preview="handlePreview"
            @toggle-favorite="toggleFavorite"
          />
        </div>

        <!-- "N more files" expander -->
        <button
          v-if="group.files.length > 3 && !expandedGroups.has(group.sessionId)"
          class="more-files-btn"
          @click="expandedGroups.add(group.sessionId)"
        >
          {{ group.files.length - 3 }} more files
          <ChevronDown :size="14" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Search, X, Star, ChevronDown, SlidersHorizontal,
  LayoutGrid, List, FolderOpen,
  FileText, Image, Code2, Archive, FileBarChart, Files,
} from 'lucide-vue-next'
import LibraryFileCard from '@/components/LibraryFileCard.vue'
import { useLibraryFiles, type FileCategory, type SessionFileGroup } from '@/composables/useLibraryFiles'
import type { LibraryFileItem } from '@/api/file'
import { useFilePanel } from '@/composables/useFilePanel'

const router = useRouter()
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
  const diff = now.getTime() - date.getTime()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const dateDay = new Date(date.getFullYear(), date.getMonth(), date.getDate())

  if (dateDay.getTime() === today.getTime()) return 'Today'
  if (dateDay.getTime() === today.getTime() - MS_PER_DAY) return 'Yesterday'
  if (diff < MS_PER_WEEK) return date.toLocaleDateString(undefined, { weekday: 'long' })
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function visibleFiles(group: SessionFileGroup): LibraryFileItem[] {
  if (expandedGroups.value.has(group.sessionId) || group.files.length <= 3) {
    return group.files
  }
  return group.files.slice(0, 3)
}

function handlePreview(file: LibraryFileItem) {
  showFilePanel(file)
}

function openSession(sessionId: string) {
  router.push(`/chat/${sessionId}`)
}

onMounted(() => {
  fetchFiles()
})
</script>

<style scoped>
.library-files-view {
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* ── Toolbar ── */
.files-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 0 20px;
  flex-wrap: wrap;
}

.toolbar-left, .toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ── Category dropdown ── */
.category-dropdown {
  position: relative;
}

.category-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 8px;
  background: var(--background-menu-white, #fff);
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

:global(.dark) .category-btn {
  border-color: var(--border-main);
  background: var(--bolt-elements-bg-depth-1);
}

.category-btn:hover {
  border-color: rgba(0, 0, 0, 0.2);
}

.category-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 20;
  background: var(--background-menu-white, #fff);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 10px;
  padding: 4px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  min-width: 160px;
}

:global(.dark) .category-menu {
  background: var(--bolt-elements-bg-depth-1);
  border-color: var(--border-main);
}

.category-option {
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

.category-option:hover {
  background: var(--fill-tsp-gray-main);
}

.category-option.active {
  font-weight: 600;
  color: var(--accent-color, #3b82f6);
}

/* ── Favorites button ── */
.favorites-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 8px;
  background: var(--background-menu-white, #fff);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

:global(.dark) .favorites-btn {
  border-color: var(--border-main);
  background: var(--bolt-elements-bg-depth-1);
}

.favorites-btn:hover {
  border-color: rgba(0, 0, 0, 0.2);
}

.favorites-btn.active {
  border-color: #eab308;
  color: #eab308;
  background: rgba(234, 179, 8, 0.06);
}

/* ── Search ── */
.search-box {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 8px;
  background: var(--background-menu-white, #fff);
  min-width: 160px;
  transition: border-color 0.15s ease;
}

:global(.dark) .search-box {
  border-color: var(--border-main);
  background: var(--bolt-elements-bg-depth-1);
}

.search-box.focused {
  border-color: var(--accent-color, #3b82f6);
}

.search-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.search-input {
  border: none;
  background: transparent;
  outline: none;
  font-size: 13px;
  color: var(--text-primary);
  width: 100%;
}

.search-input::placeholder {
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
  background: rgba(0, 0, 0, 0.08);
  color: var(--text-tertiary);
  cursor: pointer;
  flex-shrink: 0;
}

/* ── View toggle ── */
.view-toggle {
  display: flex;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 8px;
  overflow: hidden;
}

:global(.dark) .view-toggle {
  border-color: var(--border-main);
}

.view-btn {
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
  transition: all 0.15s ease;
}

:global(.dark) .view-btn {
  background: var(--bolt-elements-bg-depth-1);
}

.view-btn:first-child {
  border-right: 1px solid rgba(0, 0, 0, 0.08);
}

:global(.dark) .view-btn:first-child {
  border-right-color: var(--border-main);
}

.view-btn.active {
  color: var(--text-primary);
  background: var(--fill-tsp-gray-main);
}

.view-btn:hover:not(.active) {
  background: var(--fill-tsp-gray-main);
}

/* ── File groups ── */
.file-groups {
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.file-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.group-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
}

.group-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  cursor: pointer;
}

.group-title:hover {
  text-decoration: underline;
}

.group-date {
  font-size: 13px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

/* ── Grid ── */
.files-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

@media (max-width: 900px) {
  .files-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 520px) {
  .files-grid {
    grid-template-columns: 1fr;
  }
}

/* ── List ── */
.files-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* ── More files ── */
.more-files-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 0;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 13px;
  cursor: pointer;
  transition: color 0.15s ease;
}

.more-files-btn:hover {
  color: var(--text-primary);
}

/* ── Loading ── */
.loading-state {
  display: flex;
  flex-direction: column;
  gap: 28px;
  padding: 8px 0;
}

.skeleton-title {
  width: 200px;
  height: 16px;
  border-radius: 4px;
  background: var(--fill-tsp-gray-main);
  margin-bottom: 12px;
  animation: skeleton-pulse 1.5s infinite;
}

.skeleton-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.skeleton-card {
  height: 180px;
  border-radius: 12px;
  background: var(--fill-tsp-gray-main);
  animation: skeleton-pulse 1.5s infinite;
}

@keyframes skeleton-pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.7; }
}

/* ── Empty state ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 60px 20px;
  text-align: center;
}

.empty-icon {
  color: var(--text-tertiary);
  opacity: 0.5;
  margin-bottom: 8px;
}

.empty-state h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.empty-state p {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

/* ── Mobile ── */
@media (max-width: 639px) {
  .files-toolbar {
    padding: 12px 0 16px;
  }

  .toolbar-left, .toolbar-right {
    flex-wrap: wrap;
  }

  .search-box {
    min-width: 120px;
    flex: 1;
  }

  .skeleton-cards {
    grid-template-columns: 1fr;
  }
}
</style>
