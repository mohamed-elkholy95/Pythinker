<template>
  <div class="session-history-page">
    <!-- Header -->
    <header class="page-header">
      <div class="header-left">
        <button class="btn-back" @click="goBack">
          <ArrowLeft :size="20" />
        </button>
        <h1>Session History</h1>
      </div>
      <div class="header-right">
        <div class="search-box">
          <Search :size="16" />
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search sessions..."
            class="search-input"
          />
        </div>
        <select v-model="statusFilter" class="filter-select">
          <option value="">All Status</option>
          <option value="completed">Completed</option>
          <option value="running">Running</option>
          <option value="failed">Failed</option>
        </select>
      </div>
    </header>

    <!-- Session list -->
    <div class="session-list">
      <div v-if="isLoading" class="loading-state">
        <div class="loading-spinner"></div>
        <span>Loading sessions...</span>
      </div>

      <div v-else-if="filteredSessions.length === 0" class="empty-state">
        <History :size="48" class="icon-muted" />
        <h3>No sessions found</h3>
        <p v-if="searchQuery || statusFilter">Try adjusting your filters</p>
        <p v-else>Start a new session to see it here</p>
      </div>

      <div
        v-for="session in filteredSessions"
        :key="session.session_id"
        class="session-card"
        @click="viewSession(session)"
      >
        <div class="session-icon">
          <MessageSquare :size="20" />
        </div>
        <div class="session-content">
          <div class="session-header">
            <h3 class="session-title">{{ session.title || 'Untitled Session' }}</h3>
            <span class="session-status" :class="session.status">
              {{ session.status }}
            </span>
          </div>
          <p v-if="session.latest_message" class="session-preview">
            {{ truncateMessage(session.latest_message) }}
          </p>
          <div class="session-meta">
            <span class="session-date">
              <Clock :size="12" />
              {{ formatDate(session.latest_message_at) }}
            </span>
            <span v-if="session.openreplay_session_id" class="session-replay-badge">
              <Play :size="12" />
              Replay Available
            </span>
          </div>
        </div>
        <div class="session-actions">
          <button
            v-if="session.openreplay_session_id"
            class="btn-action"
            @click.stop="openReplay(session)"
            title="View Replay"
          >
            <Play :size="16" />
          </button>
          <button
            v-if="session.is_shared"
            class="btn-action shared"
            @click.stop="copyShareLink(session)"
            title="Copy Share Link"
          >
            <Share2 :size="16" />
          </button>
        </div>
      </div>
    </div>

    <!-- Replay modal -->
    <Teleport to="body">
      <div v-if="selectedSession" class="replay-modal-overlay" @click="closeReplay">
        <div class="replay-modal" @click.stop>
          <SessionReplayPlayer
            :session-id="selectedSession.session_id"
            :session-title="selectedSession.title"
            :open-replay-session-id="selectedSession.openreplay_session_id"
            :events="replayEvents"
            @close="closeReplay"
          />
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowLeft,
  Search,
  History,
  MessageSquare,
  Clock,
  Play,
  Share2
} from 'lucide-vue-next'
import { getSessions } from '../api/agent'
import SessionReplayPlayer from '../components/SessionReplayPlayer.vue'

interface SessionItem {
  session_id: string
  title: string | null
  status: string
  latest_message: string | null
  latest_message_at: number | null
  is_shared: boolean
  openreplay_session_id?: string | null
}

interface ReplayEvent {
  id: string
  type: string
  name: string
  timestamp: number
  payload?: Record<string, unknown>
}

const router = useRouter()

// State
const sessions = ref<SessionItem[]>([])
const isLoading = ref(true)
const searchQuery = ref('')
const statusFilter = ref('')
const selectedSession = ref<SessionItem | null>(null)
const replayEvents = ref<ReplayEvent[]>([])

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

// Load sessions
async function loadSessions(): Promise<void> {
  isLoading.value = true
  try {
    const response = await getSessions()
     
    sessions.value = response.sessions as any[]
  } catch (error) {
    console.error('Failed to load sessions:', error)
  } finally {
    isLoading.value = false
  }
}

function goBack(): void {
  router.back()
}

function viewSession(session: SessionItem): void {
  router.push(`/chat/${session.session_id}`)
}

function openReplay(session: SessionItem): void {
  selectedSession.value = session
  // In a real implementation, we'd fetch replay events here
  replayEvents.value = []
}

function closeReplay(): void {
  selectedSession.value = null
  replayEvents.value = []
}

function copyShareLink(session: SessionItem): void {
  const url = `${window.location.origin}/share/${session.session_id}`
  navigator.clipboard.writeText(url)
  // Could show a toast notification here
}

function truncateMessage(message: string): string {
  if (message.length > 100) {
    return message.substring(0, 100) + '...'
  }
  return message
}

function formatDate(timestamp: number | null): string {
  if (!timestamp) return 'Unknown'
  const date = new Date(timestamp * 1000)
  const now = new Date()
  const diff = now.getTime() - date.getTime()

  // Less than 24 hours ago
  if (diff < 86400000) {
    const hours = Math.floor(diff / 3600000)
    if (hours < 1) {
      const minutes = Math.floor(diff / 60000)
      return `${minutes}m ago`
    }
    return `${hours}h ago`
  }

  // Less than 7 days ago
  if (diff < 604800000) {
    const days = Math.floor(diff / 86400000)
    return `${days}d ago`
  }

  // Format as date
  return date.toLocaleDateString()
}

onMounted(() => {
  loadSessions()
})
</script>

<style scoped>
.session-history-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--background-main, #0a0a0a);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  background: var(--background-secondary, #111);
  border-bottom: 1px solid var(--border-color, #222);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.btn-back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  color: var(--text-secondary, #888);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-back:hover {
  background: var(--background-hover, #222);
  color: var(--text-primary, #fff);
}

.page-header h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary, #fff);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--background-tertiary, #1a1a1a);
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  color: var(--text-muted, #666);
}

.search-input {
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary, #fff);
  font-size: 14px;
  width: 200px;
}

.search-input::placeholder {
  color: var(--text-muted, #666);
}

.filter-select {
  padding: 8px 12px;
  background: var(--background-tertiary, #1a1a1a);
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  color: var(--text-primary, #fff);
  font-size: 14px;
  cursor: pointer;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px;
  color: var(--text-muted, #666);
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #333;
  border-top-color: #10b981;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.empty-state h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text-secondary, #888);
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}

.icon-muted {
  color: var(--text-muted, #444);
}

.session-card {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 16px;
  background: var(--background-secondary, #111);
  border: 1px solid var(--border-color, #222);
  border-radius: 12px;
  margin-bottom: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.session-card:hover {
  background: var(--background-hover, #1a1a1a);
  border-color: var(--border-hover, #333);
}

.session-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: var(--background-tertiary, #1a1a1a);
  border-radius: 8px;
  color: var(--text-muted, #666);
}

.session-content {
  flex: 1;
  min-width: 0;
}

.session-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 4px;
}

.session-title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary, #fff);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-status {
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 4px;
  text-transform: capitalize;
}

.session-status.completed {
  background: rgba(16, 185, 129, 0.2);
  color: #10b981;
}

.session-status.running {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
}

.session-status.failed {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.session-status.pending {
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.session-preview {
  margin: 4px 0 8px;
  font-size: 13px;
  color: var(--text-muted, #888);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-meta {
  display: flex;
  align-items: center;
  gap: 16px;
}

.session-date,
.session-replay-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-muted, #666);
}

.session-replay-badge {
  color: #10b981;
}

.session-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-action {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--border-color, #333);
  border-radius: 6px;
  color: var(--text-muted, #666);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-action:hover {
  background: var(--background-hover, #222);
  color: var(--text-primary, #fff);
}

.btn-action.shared {
  color: #10b981;
}

.replay-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.replay-modal {
  width: 90%;
  max-width: 1200px;
  height: 80vh;
  background: var(--background-main, #0a0a0a);
  border-radius: 12px;
  overflow: hidden;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
