<template>
  <div class="session-history-page">
    <!-- Header -->
    <header class="page-header">
      <div class="header-top">
        <div class="header-left">
          <button class="btn-back" aria-label="Go back" @click="goBack">
            <ArrowLeft :size="18" />
          </button>
          <div class="header-title-group">
            <h1>Library</h1>
          </div>
          <!-- Tab switcher -->
          <div class="tab-switcher">
            <button
              class="tab-btn"
              :class="{ active: activeTab === 'sessions' }"
              @click="activeTab = 'sessions'"
            >
              Sessions
            </button>
            <button
              class="tab-btn"
              :class="{ active: activeTab === 'files' }"
              @click="activeTab = 'files'"
            >
              Files
            </button>
          </div>
        </div>
        <div v-if="activeTab === 'sessions'" class="header-right">
          <div class="search-box" :class="{ focused: isSearchFocused }">
            <Search :size="15" class="search-icon" />
            <input
              v-model="searchQuery"
              id="session-search"
              name="session-search"
              type="text"
              placeholder="Search sessions..."
              class="search-input"
              @focus="isSearchFocused = true"
              @blur="isSearchFocused = false"
            />
            <button
              v-if="searchQuery"
              class="search-clear"
              @click="searchQuery = ''"
              aria-label="Clear search"
            >
              <X :size="14" />
            </button>
          </div>
          <div class="filter-group">
            <button
              v-for="filter in statusFilters"
              :key="filter.value"
              class="filter-chip"
              :class="{ active: statusFilter === filter.value }"
              @click="statusFilter = statusFilter === filter.value ? '' : filter.value"
            >
              <component :is="filter.icon" :size="13" v-if="filter.icon" />
              {{ filter.label }}
              <span v-if="filter.value && getStatusCount(filter.value)" class="filter-count">
                {{ getStatusCount(filter.value) }}
              </span>
            </button>
          </div>
        </div>
      </div>
    </header>

    <!-- Files tab -->
    <div v-if="activeTab === 'files'" class="tab-content">
      <LibraryFilesView />
    </div>

    <!-- Sessions tab -->
    <div v-else class="session-list">
      <!-- Loading state -->
      <div v-if="isLoading" class="loading-state">
        <div class="loading-skeleton" v-for="i in 5" :key="i">
          <div class="skeleton-icon"></div>
          <div class="skeleton-content">
            <div class="skeleton-title"></div>
            <div class="skeleton-meta"></div>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div v-else-if="filteredSessions.length === 0" class="empty-state">
        <div class="empty-illustration">
          <div class="empty-circle">
            <Inbox :size="32" />
          </div>
        </div>
        <h3 v-if="searchQuery || statusFilter">No matching sessions</h3>
        <h3 v-else>No sessions yet</h3>
        <p v-if="searchQuery || statusFilter">
          Try adjusting your search or filters
        </p>
        <p v-else>Start a new task to begin your first session</p>
        <button v-if="searchQuery || statusFilter" class="btn-clear-filters" @click="clearFilters">
          Clear filters
        </button>
      </div>

      <!-- Grouped sessions -->
      <template v-else>
        <div
          v-for="group in groupedSessions"
          :key="group.label"
          class="session-group"
        >
          <div class="group-header">
            <span class="group-label">{{ group.label }}</span>
            <span class="group-count">{{ group.sessions.length }}</span>
          </div>

          <div class="group-list">
            <div
              v-for="session in group.sessions"
              :key="session.session_id"
              class="session-card"
              :class="{ 'is-running': isRunning(session) }"
              @click="viewSession(session)"
            >
              <!-- Icon -->
              <div class="session-icon-wrapper" :class="statusClass(session)">
                <template v-if="isRunning(session)">
                  <svg class="running-spinner" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" opacity="0.2" />
                    <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
                  </svg>
                </template>
                <template v-else>
                  <TaskIcon :title="session.title || ''" :session-id="session.session_id" />
                </template>
              </div>

              <!-- Content -->
              <div class="session-content">
                <div class="session-top-row">
                  <h3 class="session-title">{{ session.title || deriveTitle(session) }}</h3>
                  <span class="session-time">{{ formatDate(session.latest_message_at) }}</span>
                </div>
                <p v-if="session.latest_message && session.title" class="session-preview">
                  {{ truncateMessage(session.latest_message) }}
                </p>
                <div class="session-bottom-row">
                  <span class="session-status-badge" :class="session.status">
                    <span class="status-dot"></span>
                    {{ session.status }}
                  </span>
                  <span v-if="session.source === 'telegram'" class="source-badge telegram">
                    <Send :size="10" />
                    Telegram
                  </span>
                  <span v-if="session.is_shared" class="source-badge shared">
                    <Share2 :size="10" />
                    Shared
                  </span>
                </div>
              </div>

              <!-- Actions (visible on hover) -->
              <div class="session-actions" @click.stop>
                <button
                  class="btn-session-action"
                  title="Open session"
                  @click="viewSession(session)"
                >
                  <ExternalLink :size="14" />
                </button>
                <button
                  v-if="session.is_shared"
                  class="btn-session-action"
                  title="Copy share link"
                  @click="copyShareLink(session)"
                >
                  <Link :size="14" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowLeft,
  Search,
  Inbox,
  CheckCircle2,
  AlertCircle,
  Share2,
  Send,
  ExternalLink,
  Link,
  X,
  Loader2,
} from 'lucide-vue-next'
import { useSessionListFeed } from '@/composables/useSessionListFeed'
import type { ListSessionItem } from '@/types/response'
import { SessionStatus } from '@/types/response'
import TaskIcon from '@/components/icons/TaskIcon.vue'
import LibraryFilesView from '@/components/LibraryFilesView.vue'
import { copyToClipboard } from '@/utils/dom'

type SessionItem = ListSessionItem

const MS_PER_MINUTE = 60_000
const MS_PER_HOUR = 3_600_000
const MS_PER_DAY = 86_400_000
const MS_PER_WEEK = 7 * MS_PER_DAY

const router = useRouter()

// State
const activeTab = ref<'sessions' | 'files'>('sessions')
const { sessions, isLoading } = useSessionListFeed({ initialFetch: true })
const searchQuery = ref('')
const statusFilter = ref('')
const isSearchFocused = ref(false)

const statusFilters = [
  { label: 'All', value: '', icon: null },
  { label: 'Running', value: 'running', icon: Loader2 },
  { label: 'Completed', value: 'completed', icon: CheckCircle2 },
  { label: 'Failed', value: 'failed', icon: AlertCircle },
]

// Filtered sessions
const filteredSessions = computed(() => {
  let result = sessions.value

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(
      (s) =>
        s.title?.toLowerCase().includes(query) ||
        s.latest_message?.toLowerCase().includes(query) ||
        s.session_id.toLowerCase().includes(query)
    )
  }

  if (statusFilter.value) {
    result = result.filter((s) => s.status === statusFilter.value)
  }

  return result
})

function getStatusCount(status: string): number {
  return sessions.value.filter((s) => s.status === status).length
}

// Group sessions by date
const groupedSessions = computed(() => {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - MS_PER_DAY)
  const weekAgo = new Date(today.getTime() - MS_PER_WEEK)

  const groups: { label: string; sessions: SessionItem[] }[] = [
    { label: 'Today', sessions: [] },
    { label: 'Yesterday', sessions: [] },
    { label: 'This Week', sessions: [] },
    { label: 'Earlier', sessions: [] },
  ]

  for (const session of filteredSessions.value) {
    const ts = session.latest_message_at
    if (!ts) {
      groups[3].sessions.push(session)
      continue
    }
    const date = new Date(ts * 1000)
    if (date >= today) {
      groups[0].sessions.push(session)
    } else if (date >= yesterday) {
      groups[1].sessions.push(session)
    } else if (date >= weekAgo) {
      groups[2].sessions.push(session)
    } else {
      groups[3].sessions.push(session)
    }
  }

  return groups.filter((g) => g.sessions.length > 0)
})

function isRunning(session: SessionItem): boolean {
  return session.status === SessionStatus.RUNNING || session.status === SessionStatus.PENDING
}

function statusClass(session: SessionItem): string {
  if (isRunning(session)) return 'status-running'
  if (session.status === SessionStatus.COMPLETED) return 'status-completed'
  if (session.status === SessionStatus.FAILED) return 'status-failed'
  return ''
}

function goBack(): void {
  router.back()
}

function viewSession(session: SessionItem): void {
  router.push(`/chat/${session.session_id}`)
}

async function copyShareLink(session: SessionItem): Promise<void> {
  const url = `${window.location.origin}/share/${session.session_id}`
  await copyToClipboard(url)
}

function clearFilters(): void {
  searchQuery.value = ''
  statusFilter.value = ''
}

function deriveTitle(session: SessionItem): string {
  if (session.latest_message) {
    const trimmed = session.latest_message.trim()
    return trimmed.length > 60 ? trimmed.substring(0, 60) + '...' : trimmed
  }
  return 'New Session'
}

function truncateMessage(message: string): string {
  if (message.length > 120) {
    return message.substring(0, 120) + '...'
  }
  return message
}

function formatDate(timestamp: number | null): string {
  if (!timestamp) return ''
  const date = new Date(timestamp * 1000)
  const now = new Date()
  const diff = now.getTime() - date.getTime()

  if (diff < MS_PER_MINUTE) return 'Just now'
  if (diff < MS_PER_HOUR) {
    const minutes = Math.floor(diff / MS_PER_MINUTE)
    return `${minutes}m ago`
  }
  if (diff < MS_PER_DAY) {
    const hours = Math.floor(diff / MS_PER_HOUR)
    return `${hours}h ago`
  }
  if (diff < MS_PER_WEEK) {
    const days = Math.floor(diff / MS_PER_DAY)
    return `${days}d ago`
  }
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
</script>

<style scoped>
.session-history-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--background-main);
}

/* ─── Header ─────────────────────────────── */
.page-header {
  padding: 20px 28px 16px;
  background: var(--background-secondary);
  border-bottom: 1px solid var(--border-color);
}

.header-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-shrink: 0;
}

/* ─── Tab switcher ─────────────────────── */
.tab-switcher {
  display: flex;
  gap: 2px;
  background: var(--fill-tsp-gray-main, #f0f0f0);
  border-radius: 8px;
  padding: 2px;
  margin-left: 8px;
}

:global(.dark) .tab-switcher {
  background: var(--bolt-elements-bg-depth-2);
}

.tab-btn {
  padding: 5px 14px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.tab-btn.active {
  background: var(--background-menu-white, #fff);
  color: var(--text-primary);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

:global(.dark) .tab-btn.active {
  background: var(--bolt-elements-bg-depth-1);
}

.tab-btn:hover:not(.active) {
  color: var(--text-primary);
}

/* ─── Tab content ─────────────────────── */
.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 0 28px 28px;
}

.btn-back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-back:hover {
  background: var(--background-hover);
  color: var(--text-primary);
  border-color: var(--border-hover, var(--border-color));
}

.header-title-group {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.page-header h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.session-count {
  font-size: 13px;
  color: var(--text-muted);
  font-weight: 400;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

/* ─── Search ─────────────────────────────── */
.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  background: var(--background-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  transition: all 0.2s ease;
  min-width: 220px;
}

.search-box.focused {
  border-color: var(--text-brand, var(--function-success));
  box-shadow: 0 0 0 3px var(--function-success-tsp, var(--focus-ring-color));
}

.search-icon {
  color: var(--text-muted);
  flex-shrink: 0;
}

.search-input {
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: 13px;
  width: 100%;
}

.search-input::placeholder {
  color: var(--text-muted);
}

.search-clear {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  background: var(--background-hover);
  border: none;
  border-radius: 50%;
  color: var(--text-muted);
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s;
}

.search-clear:hover {
  background: var(--border-color);
  color: var(--text-primary);
}

/* ─── Filter Chips ───────────────────────── */
.filter-group {
  display: flex;
  gap: 6px;
}

.filter-chip {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.filter-chip:hover {
  background: var(--background-hover);
  color: var(--text-primary);
}

.filter-chip.active {
  background: var(--text-primary);
  color: var(--background-main);
  border-color: var(--text-primary);
}

.filter-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  font-size: 10px;
  font-weight: 600;
  border-radius: 9px;
  background: var(--fill-tsp-white-dark);
}

.filter-chip:not(.active) .filter-count {
  background: var(--background-tertiary);
  color: var(--text-muted);
}

/* ─── Session List ───────────────────────── */
.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px 28px 32px;
}

/* ─── Loading Skeleton ───────────────────── */
.loading-state {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.loading-skeleton {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 18px;
  background: var(--background-secondary);
  border-radius: 12px;
  border: 1px solid var(--border-color);
}

.skeleton-icon {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: linear-gradient(110deg, var(--background-tertiary) 30%, var(--background-hover) 50%, var(--background-tertiary) 70%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  flex-shrink: 0;
}

.skeleton-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skeleton-title {
  width: 60%;
  height: 14px;
  border-radius: 6px;
  background: linear-gradient(110deg, var(--background-tertiary) 30%, var(--background-hover) 50%, var(--background-tertiary) 70%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}

.skeleton-meta {
  width: 35%;
  height: 10px;
  border-radius: 5px;
  background: linear-gradient(110deg, var(--background-tertiary) 30%, var(--background-hover) 50%, var(--background-tertiary) 70%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  animation-delay: 0.1s;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ─── Empty State ────────────────────────── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 80px 24px;
  text-align: center;
}

.empty-illustration {
  margin-bottom: 8px;
}

.empty-circle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: var(--background-tertiary);
  color: var(--text-muted);
  border: 2px dashed var(--border-color);
}

.empty-state h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-secondary);
}

.empty-state p {
  margin: 0;
  font-size: 14px;
  color: var(--text-muted);
  max-width: 280px;
}

.btn-clear-filters {
  margin-top: 8px;
  padding: 8px 18px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-brand, var(--function-success));
  background: transparent;
  border: 1px solid var(--text-brand, var(--function-success));
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-clear-filters:hover {
  background: var(--function-success-tsp);
}

/* ─── Session Group ──────────────────────── */
.session-group {
  margin-bottom: 28px;
}

.session-group:last-child {
  margin-bottom: 0;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  padding: 0 4px;
}

.group-label {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

.group-count {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  background: var(--background-tertiary);
  padding: 1px 7px;
  border-radius: 10px;
}

.group-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* ─── Session Card ───────────────────────── */
.session-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  background: var(--background-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;
}

.session-card:hover {
  background: var(--background-hover);
  border-color: var(--border-hover, var(--border-color));
  box-shadow: 0 2px 8px var(--shadow-color, var(--border-color));
}

.session-card.is-running {
  border-color: var(--status-running, var(--text-brand));
  border-left-width: 3px;
}

/* ─── Session Icon ───────────────────────── */
.session-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: var(--background-tertiary);
  color: var(--text-muted);
  flex-shrink: 0;
  transition: all 0.15s;
}

.session-icon-wrapper.status-running {
  background: var(--status-running-tsp, var(--function-info-tsp));
  color: var(--status-running, var(--text-brand));
}

.session-icon-wrapper.status-completed {
  background: var(--function-success-tsp);
  color: var(--function-success);
}

.session-icon-wrapper.status-failed {
  background: var(--function-error-tsp);
  color: var(--function-error);
}

.running-spinner {
  width: 22px;
  height: 22px;
  animation: spin 1.2s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ─── Session Content ────────────────────── */
.session-content {
  flex: 1;
  min-width: 0;
}

.session-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 3px;
}

.session-title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}

.session-time {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

.session-preview {
  margin: 2px 0 6px;
  font-size: 13px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}

.session-bottom-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── Status Badge ───────────────────────── */
.session-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 6px;
  text-transform: capitalize;
  line-height: 1.5;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.session-status-badge.completed {
  background: var(--function-success-tsp);
  color: var(--function-success);
}

.session-status-badge.completed .status-dot {
  background: var(--function-success);
}

.session-status-badge.running {
  background: var(--status-running-tsp, var(--function-info-tsp));
  color: var(--status-running, var(--text-brand));
}

.session-status-badge.running .status-dot {
  background: var(--status-running, var(--text-brand));
  animation: pulse-dot 1.5s ease-in-out infinite;
}

.session-status-badge.pending {
  background: var(--function-warning-tsp);
  color: var(--function-warning);
}

.session-status-badge.pending .status-dot {
  background: var(--function-warning);
  animation: pulse-dot 1.5s ease-in-out infinite;
}

.session-status-badge.failed {
  background: var(--function-error-tsp);
  color: var(--function-error);
}

.session-status-badge.failed .status-dot {
  background: var(--function-error);
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ─── Source Badges ──────────────────────── */
.source-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 7px;
  font-size: 10px;
  font-weight: 500;
  border-radius: 5px;
  text-transform: capitalize;
}

.source-badge.telegram {
  background: var(--function-info-tsp);
  color: var(--function-info, var(--text-brand));
}

.source-badge.shared {
  background: var(--function-success-tsp);
  color: var(--function-success);
}

/* ─── Session Actions ────────────────────── */
.session-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s ease;
  flex-shrink: 0;
}

.session-card:hover .session-actions {
  opacity: 1;
}

.btn-session-action {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  background: var(--background-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-session-action:hover {
  background: var(--background-hover);
  color: var(--text-primary);
  border-color: var(--border-hover, var(--border-color));
}

/* ─── Responsive ─────────────────────────── */
@media (max-width: 768px) {
  .page-header {
    padding: 16px 16px 12px;
  }

  .header-top {
    flex-direction: column;
    gap: 12px;
  }

  .header-right {
    width: 100%;
  }

  .search-box {
    flex: 1;
    min-width: 0;
  }

  .session-list {
    padding: 16px;
  }

  .filter-group {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .session-actions {
    opacity: 1;
  }
}
</style>
