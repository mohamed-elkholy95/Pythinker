<template>
  <Teleport to="body">
    <Transition name="search-modal">
      <div v-if="open" class="search-modal-backdrop" @click.self="close">
        <div class="search-modal" @click.stop>
          <!-- Search header -->
          <div class="search-modal-header">
            <Search :size="22" class="search-modal-icon" />
            <input
              ref="searchInputRef"
              v-model="searchQuery"
              type="text"
              :placeholder="t('Search tasks...')"
              class="search-modal-input"
              @keydown.escape="close"
              @keydown.down.prevent="focusNext"
              @keydown.up.prevent="focusPrev"
              @keydown.enter.prevent="selectFocused"
            />
            <button
              class="search-modal-close"
              @click="close"
              aria-label="Close search"
            >
              <X :size="18" />
            </button>
          </div>

          <!-- Results list -->
          <div class="search-modal-body minimal-scrollbar">
            <!-- New task action -->
            <button
              class="search-modal-item search-modal-action"
              :class="{ 'search-modal-item-focused': focusedIndex === 0 }"
              @click="handleNewChat"
              @mouseenter="focusedIndex = 0"
            >
              <div class="search-modal-icon-circle search-modal-icon-circle--new">
                <Plus :size="20" :stroke-width="2.5" />
              </div>
              <span class="search-modal-action-label">{{ t('New task') }}</span>
            </button>

            <!-- Grouped sessions -->
            <template v-if="groupedSessions.length > 0">
              <template v-for="group in groupedSessions" :key="group.label">
                <div class="search-modal-group-label">{{ group.label }}</div>
                <button
                  v-for="(session, sIdx) in group.sessions"
                  :key="session.session_id"
                  class="search-modal-item"
                  :class="{ 'search-modal-item-focused': focusedIndex === getGlobalIndex(group, sIdx) }"
                  @click="handleSelectSession(session)"
                  @mouseenter="focusedIndex = getGlobalIndex(group, sIdx)"
                >
                  <!-- Icon -->
                  <div class="search-modal-icon-circle">
                    <template v-if="isRunning(session)">
                      <svg class="search-modal-spinner" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" opacity="0.2" />
                        <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
                      </svg>
                    </template>
                    <template v-else>
                      <TaskIcon :title="getDisplayTitle(session)" :session-id="session.session_id" />
                    </template>
                  </div>

                  <!-- Title + description -->
                  <div class="search-modal-item-content">
                    <span class="search-modal-item-title">{{ getDisplayTitle(session) }}</span>
                    <span v-if="getDescription(session)" class="search-modal-item-desc">{{ getDescription(session) }}</span>
                  </div>

                  <!-- Relative date -->
                  <span class="search-modal-item-date">{{ formatRelativeDay(session.latest_message_at) }}</span>
                </button>
              </template>
            </template>

            <!-- No results -->
            <div v-else-if="searchQuery.trim()" class="search-modal-empty">
              {{ t('No matching tasks') }}
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Search, X, Plus } from 'lucide-vue-next'
import { useSessionListFeed } from '@/composables/useSessionListFeed'
import type { ListSessionItem } from '@/types/response'
import { SessionStatus } from '@/types/response'
import TaskIcon from '@/components/icons/TaskIcon.vue'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
}>()

const { t } = useI18n()
const router = useRouter()
const { sessions } = useSessionListFeed()

const searchQuery = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)
const focusedIndex = ref(0)

function close() {
  emit('update:open', false)
}

// Auto-focus input when modal opens
watch(() => props.open, async (isOpen) => {
  if (isOpen) {
    searchQuery.value = ''
    focusedIndex.value = 0
    await nextTick()
    searchInputRef.value?.focus()
  }
})

function getDisplayTitle(session: ListSessionItem): string {
  if (session.title?.trim()) return session.title.trim()
  if (session.latest_message?.trim()) {
    const msg = session.latest_message.trim()
    return msg.length > 60 ? msg.substring(0, 60) + '...' : msg
  }
  return t('New Chat')
}

function getDescription(session: ListSessionItem): string {
  if (!session.latest_message?.trim()) return ''
  const msg = session.latest_message.trim()
  return msg.length > 90 ? msg.substring(0, 90) + '...' : msg
}

function formatRelativeDay(ts: number | null): string {
  if (!ts) return ''
  const date = new Date(ts * 1000)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const sessionDay = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const diffDays = Math.floor((today.getTime() - sessionDay.getTime()) / 86400000)

  if (diffDays === 0) {
    // Today — show time
    return date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  }
  if (diffDays < 7) {
    // Within the last week — show day name
    return date.toLocaleDateString(undefined, { weekday: 'long' })
  }
  // Older — show short date
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function isRunning(session: ListSessionItem): boolean {
  return session.status === SessionStatus.RUNNING || session.status === SessionStatus.PENDING
}

// Filter sessions by search query
const filteredSessions = computed(() => {
  const all = sessions.value.filter(s => {
    const title = getDisplayTitle(s)
    return title && title !== t('New Chat')
  })

  if (!searchQuery.value.trim()) return all

  const q = searchQuery.value.toLowerCase().trim()
  return all.filter(s =>
    getDisplayTitle(s).toLowerCase().includes(q) ||
    s.latest_message?.toLowerCase().includes(q)
  )
})

// Group sessions by date
const groupedSessions = computed(() => {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 86400000)
  const weekAgo = new Date(today.getTime() - 7 * 86400000)
  const monthAgo = new Date(today.getTime() - 30 * 86400000)

  const groups: { label: string; sessions: ListSessionItem[] }[] = [
    { label: 'Today', sessions: [] },
    { label: 'Yesterday', sessions: [] },
    { label: 'Last 7 days', sessions: [] },
    { label: 'Last 30 days', sessions: [] },
    { label: 'Older', sessions: [] },
  ]

  for (const session of filteredSessions.value) {
    const ts = session.latest_message_at
    if (!ts) {
      groups[4].sessions.push(session)
      continue
    }
    const date = new Date(ts * 1000)
    if (date >= today) {
      groups[0].sessions.push(session)
    } else if (date >= yesterday) {
      groups[1].sessions.push(session)
    } else if (date >= weekAgo) {
      groups[2].sessions.push(session)
    } else if (date >= monthAgo) {
      groups[3].sessions.push(session)
    } else {
      groups[4].sessions.push(session)
    }
  }

  return groups.filter(g => g.sessions.length > 0)
})

// Total number of navigable items (1 for "New chat" + all session items)
const totalItems = computed(() => {
  return 1 + filteredSessions.value.length
})

// Get global index for a session within a group
function getGlobalIndex(group: { label: string; sessions: ListSessionItem[] }, sessionIndex: number): number {
  let idx = 1 // Start after "New chat"
  for (const g of groupedSessions.value) {
    if (g.label === group.label) {
      return idx + sessionIndex
    }
    idx += g.sessions.length
  }
  return idx + sessionIndex
}

// Get the session at a given global index
function getSessionAtIndex(globalIndex: number): ListSessionItem | null {
  if (globalIndex === 0) return null // "New chat"
  let idx = 1
  for (const g of groupedSessions.value) {
    for (const session of g.sessions) {
      if (idx === globalIndex) return session
      idx++
    }
  }
  return null
}

function focusNext() {
  focusedIndex.value = Math.min(focusedIndex.value + 1, totalItems.value - 1)
}

function focusPrev() {
  focusedIndex.value = Math.max(focusedIndex.value - 1, 0)
}

function selectFocused() {
  if (focusedIndex.value === 0) {
    handleNewChat()
  } else {
    const session = getSessionAtIndex(focusedIndex.value)
    if (session) handleSelectSession(session)
  }
}

function handleNewChat() {
  close()
  router.push('/')
}

function handleSelectSession(session: ListSessionItem) {
  close()
  router.push(`/chat/${session.session_id}`)
}
</script>

<style scoped>
.search-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: min(20vh, 160px);
}

.search-modal {
  width: 100%;
  max-width: 640px;
  max-height: min(70vh, 580px);
  display: flex;
  flex-direction: column;
  background: var(--background-white-main);
  border: 1px solid var(--border-main);
  border-radius: 16px;
  box-shadow:
    0 24px 48px -12px rgba(0, 0, 0, 0.18),
    0 0 0 1px rgba(0, 0, 0, 0.05);
  animation: slideUp 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  overflow: hidden;
}

/* ─── Header ─────────────────────────────── */
.search-modal-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 24px;
  border-bottom: 1px solid var(--border-light);
  flex-shrink: 0;
}

.search-modal-icon {
  flex-shrink: 0;
  color: var(--text-tertiary);
}

.search-modal-input {
  flex: 1;
  min-width: 0;
  height: 32px;
  border: none;
  outline: none;
  background: transparent;
  font-size: 18px;
  color: var(--text-primary);
  font-weight: 400;
}

.search-modal-input::placeholder {
  color: var(--text-tertiary);
}

.search-modal-close {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.15s ease;
  background: transparent;
  border: none;
}

.search-modal-close:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-secondary);
}

/* ─── Body ───────────────────────────────── */
.search-modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 14px 14px;
}

/* ─── Group label ────────────────────────── */
.search-modal-group-label {
  padding: 16px 10px 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-tertiary);
  user-select: none;
}

/* ─── Circular icon ──────────────────────── */
.search-modal-icon-circle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  min-width: 44px;
  border-radius: 50%;
  background: var(--fill-tsp-gray-main, #f0ede8);
  color: var(--icon-secondary);
  flex-shrink: 0;
}

.search-modal-icon-circle--new {
  background: var(--fill-tsp-gray-main, #f0ede8);
  color: var(--text-primary);
}

/* ─── Items ──────────────────────────────── */
.search-modal-item {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
  padding: 10px 10px;
  border-radius: 12px;
  color: var(--text-primary);
  cursor: pointer;
  transition: background 0.1s ease;
  background: transparent;
  border: none;
  text-align: left;
}

.search-modal-item:hover,
.search-modal-item-focused {
  background: var(--fill-tsp-gray-main);
}

.search-modal-action {
  margin-bottom: 2px;
}

.search-modal-action-label {
  font-size: 16px;
  font-weight: 600;
}

/* ─── Item content (title + desc) ────────── */
.search-modal-item-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.search-modal-item-title {
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary);
  line-height: 1.35;
}

.search-modal-item-desc {
  font-size: 13px;
  font-weight: 400;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.35;
}

/* ─── Date label ─────────────────────────── */
.search-modal-item-date {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 400;
  color: var(--text-tertiary);
  white-space: nowrap;
  padding-left: 12px;
}

.search-modal-spinner {
  width: 22px;
  height: 22px;
  color: var(--bolt-elements-item-contentAccent, #3b82f6);
  animation: spin 1.2s linear infinite;
}

/* ─── Empty state ────────────────────────── */
.search-modal-empty {
  padding: 32px 16px;
  text-align: center;
  font-size: 14px;
  color: var(--text-tertiary);
}

/* ─── Transition ─────────────────────────── */
.search-modal-enter-active {
  transition: opacity 0.15s ease;
}
.search-modal-enter-active .search-modal {
  transition: opacity 0.2s cubic-bezier(0.16, 1, 0.3, 1), transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.search-modal-leave-active {
  transition: opacity 0.12s ease;
}
.search-modal-leave-active .search-modal {
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.search-modal-enter-from {
  opacity: 0;
}
.search-modal-enter-from .search-modal {
  opacity: 0;
  transform: translateY(8px) scale(0.98);
}
.search-modal-leave-to {
  opacity: 0;
}
.search-modal-leave-to .search-modal {
  opacity: 0;
  transform: translateY(8px) scale(0.98);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ─── Dark mode ──────────────────────────── */
:global(.dark) .search-modal {
  background: var(--background-gray-main, #1a1a1a);
  border-color: var(--border-main);
  box-shadow:
    0 24px 48px -12px rgba(0, 0, 0, 0.5),
    0 0 0 1px rgba(255, 255, 255, 0.06);
}

:global(.dark) .search-modal-icon-circle {
  background: rgba(255, 255, 255, 0.08);
}

/* ─── Responsive ─────────────────────────── */
@media (max-width: 639px) {
  .search-modal-backdrop {
    padding: 12px;
    padding-top: 60px;
  }

  .search-modal {
    max-height: 80vh;
    border-radius: 14px;
  }

  .search-modal-item-date {
    display: none;
  }
}
</style>
