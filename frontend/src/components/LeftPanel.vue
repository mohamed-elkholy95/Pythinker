<template>
  <div
    class="left-panel-container h-full flex flex-col"
    :class="{
      'left-panel-expanded': isLeftPanelShow,
      'left-panel-collapsed': !isLeftPanelShow
    }"
  >
    <!-- Collapsed icon sidebar (always visible when collapsed) -->
    <div v-if="!isLeftPanelShow" class="collapsed-sidebar">
      <div class="collapsed-sidebar-top">
        <button @click="toggleLeftPanel" class="collapsed-icon-btn" aria-label="Expand sidebar">
          <PanelLeft class="h-5 w-5" />
        </button>
        <button @click="handleNewTaskClick" class="collapsed-icon-btn" aria-label="New task">
          <SquarePen class="h-5 w-5" />
        </button>
        <button @click="handleLibraryClick" class="collapsed-icon-btn" aria-label="Library">
          <Library class="h-5 w-5" />
        </button>
      </div>
      <div class="collapsed-sidebar-bottom">
        <button @click="openSettingsDialog('settings')" class="collapsed-icon-btn" aria-label="Settings">
          <Settings2 class="h-5 w-5" />
        </button>
      </div>
    </div>
    <div
      class="left-panel-content flex flex-col overflow-hidden bg-[var(--background-nav)]"
      :class="{
        'h-full opacity-100 translate-x-0 border-r border-[var(--border-main)]': isLeftPanelShow,
        'hidden': !isLeftPanelShow
      }"
    >
      <div class="left-panel-header px-4 py-3 h-[56px]">
        <div class="flex items-center gap-2">
          <Bot :size="20" class="logo-robot" :stroke-width="2.2" />
          <PythinkerLogoTextIcon />
        </div>
        <button
          class="collapse-btn"
          @click="toggleLeftPanel"
          aria-label="Collapse sidebar"
        >
          <PanelLeft class="h-5 w-5 text-[var(--icon-secondary)]" />
        </button>
      </div>
      <div class="px-3 mb-2 flex justify-center flex-shrink-0">
        <button @click="handleNewTaskClick" class="new-task-btn">
          <Plus class="h-4 w-4" />
          <span class="new-task-label">
            {{ t('New Task') }}
          </span>
          <div class="new-task-shortcut">
            <span class="shortcut-key">
              <Command :size="12" />
            </span>
            <span class="shortcut-key">K</span>
          </div>
        </button>
      </div>
      <div class="px-3">
        <div class="nav-section">
          <button class="nav-item" type="button" @click="openSearch">
            <Search class="nav-icon" />
            <span>{{ t('Search') }}</span>
          </button>
          <button class="nav-item" type="button" @click="handleLibraryClick">
            <Library class="nav-icon" />
            <span>{{ t('Library') }}</span>
          </button>
        </div>
        <div class="nav-section">
          <div class="nav-section-title">{{ t('Projects') }}</div>
          <button class="nav-item nav-item-muted" type="button" aria-disabled="true" title="Coming soon">
            <FolderPlus class="nav-icon" />
            <span>{{ t('New project') }}</span>
          </button>
        </div>
      </div>
      <!-- Search bar -->
      <div v-if="isSearching" class="search-bar-container">
        <div class="search-bar">
          <Search :size="14" class="search-bar-icon" />
          <input
            ref="searchInputRef"
            v-model="searchQuery"
            type="text"
            :placeholder="t('Search tasks...')"
            class="search-input"
            @keydown.escape="closeSearch"
          />
          <button v-if="searchQuery" class="search-clear-btn" @click="searchQuery = ''">
            <X :size="12" />
          </button>
          <button class="search-close-btn" @click="closeSearch">
            <X :size="14" />
          </button>
        </div>
        <div v-if="searchQuery && filteredSessions.length === 0" class="search-no-results">
          {{ t('No matching tasks') }}
        </div>
      </div>
      <div class="left-panel-section-title">
        <template v-if="isSearching && searchQuery">{{ filteredSessions.length }} {{ t('results') }}</template>
        <template v-else>{{ t('All tasks') }}</template>
      </div>
      <div class="flex flex-col flex-1 min-h-0">
        <div v-if="filteredSessions.length > 0" class="flex flex-col flex-1 min-h-0 overflow-auto pt-1 pb-4 px-2 overflow-x-hidden minimal-scrollbar">
          <SessionItem v-for="session in filteredSessions" :key="session.session_id" :session="session"
            @deleted="handleSessionDeleted"
            @stopped="handleSessionStopped" />
        </div>
        <div v-else-if="!isSearching" class="flex flex-1 flex-col items-center justify-center gap-4">
          <div class="flex flex-col items-center gap-2 text-[var(--text-tertiary)]">
            <MessageSquareDashed :size="38" />
            <span class="text-sm font-medium">{{ t('Create a task to get started') }}</span></div>
        </div>
      </div>
      <div class="mt-auto border-t border-[var(--border-light)] p-3 bg-[var(--background-nav)]">
        <div class="flex items-center gap-1 w-full">
          <Popover>
            <PopoverTrigger as-child>
              <button
                class="group flex flex-1 items-center gap-3 rounded-lg p-2 text-start hover:bg-[var(--fill-tsp-gray-main)] transition-colors min-w-0 outline-none"
                aria-label="Open user menu"
              >
                <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--bolt-elements-item-contentAccent)] text-white text-sm font-semibold shadow-sm">
                  {{ avatarLetter }}
                </span>
                <div class="flex flex-col min-w-0 overflow-hidden">
                  <span class="truncate text-sm font-medium text-[var(--text-primary)]">
                    {{ currentUser?.fullname || t('Account') }}
                  </span>
                  <span v-if="currentUser?.email" class="truncate text-xs text-[var(--text-tertiary)]">
                    {{ currentUser?.email }}
                  </span>
                </div>
              </button>
            </PopoverTrigger>
            <PopoverContent side="top" align="start" :side-offset="12" class="p-0 border-0 bg-transparent shadow-none">
              <UserMenu />
            </PopoverContent>
          </Popover>

          <button
            class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[var(--icon-tertiary)] hover:bg-[var(--fill-tsp-gray-main)] hover:text-[var(--text-primary)] transition-colors"
            @click="openSettingsDialog('settings')"
            aria-label="Open settings"
          >
            <Settings2 class="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { PanelLeft, Plus, Command, MessageSquareDashed, Settings2, Search, Library, FolderPlus, SquarePen, Bot, X } from 'lucide-vue-next';
import PythinkerLogoTextIcon from './icons/PythinkerLogoTextIcon.vue';
import SessionItem from './SessionItem.vue';
import { useLeftPanel } from '../composables/useLeftPanel';
import { ref, nextTick, onMounted, watch, onUnmounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getSessionsSSE, getSessions, stopSession } from '../api/agent';
import { ListSessionItem, SessionStatus } from '../types/response';
import { useI18n } from 'vue-i18n';
import { useSettingsDialog } from '@/composables/useSettingsDialog';
import { useAuth } from '@/composables/useAuth';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import UserMenu from './UserMenu.vue';
import { useSessionStatus } from '@/composables/useSessionStatus';

const { t } = useI18n()
const { isLeftPanelShow, toggleLeftPanel } = useLeftPanel()
const { openSettingsDialog } = useSettingsDialog()
const { currentUser } = useAuth()
const { onStatusChange } = useSessionStatus()
const route = useRoute()
const router = useRouter()

const sessions = ref<ListSessionItem[]>([])
const optimisticTitleHints = ref<Record<string, string>>({})

// Search state
const searchQuery = ref('')
const isSearching = ref(false)
const searchInputRef = ref<HTMLInputElement | null>(null)

interface SessionTitleHintDetail {
  sessionId: string
  title: string
  status?: SessionStatus
}

const isPlaceholderTitle = (title: string): boolean => {
  const placeholderTitles = new Set([
    t('New Chat').toLowerCase(),
    'new chat',
  ])
  return placeholderTitles.has(title.toLowerCase())
}

const getSessionDisplayTitle = (session: ListSessionItem): string | null => {
  const normalizedTitle = session.title?.trim()
  if (normalizedTitle && !isPlaceholderTitle(normalizedTitle)) {
    return normalizedTitle
  }

  const normalizedLatestMessage = session.latest_message?.trim()
  if (normalizedLatestMessage) {
    return normalizedLatestMessage
  }

  const optimisticTitle = optimisticTitleHints.value[session.session_id]?.trim()
  if (optimisticTitle) {
    return optimisticTitle
  }

  return null
}

const hasResolvedTaskTitle = (session: ListSessionItem): boolean => {
  return !!getSessionDisplayTitle(session)
}

const visibleSessions = computed(() =>
  sessions.value.filter((session) => hasResolvedTaskTitle(session))
)

const filteredSessions = computed(() => {
  if (!searchQuery.value.trim()) return visibleSessions.value
  const q = searchQuery.value.toLowerCase().trim()
  return visibleSessions.value.filter(s =>
    getSessionDisplayTitle(s)?.toLowerCase().includes(q) ||
    s.latest_message?.toLowerCase().includes(q)
  )
})

const openSearch = async () => {
  isSearching.value = true
  await nextTick()
  searchInputRef.value?.focus()
}

const closeSearch = () => {
  searchQuery.value = ''
  isSearching.value = false
}

// Handle session status changes from other components (e.g., ChatPage)
const handleSessionStatusChange = (sessionId: string, status: SessionStatus) => {
  const session = sessions.value.find(s => s.session_id === sessionId);
  if (session) {
    session.status = status;
  }
};
const cancelGetSessionsSSE = ref<(() => void) | null>(null)
const avatarLetter = computed(() => {
  return currentUser.value?.fullname?.charAt(0)?.toUpperCase() || 'M';
})

const mergeWithOptimisticSession = (serverSessions: ListSessionItem[]): ListSessionItem[] => {
  const activeSessionId = route.params.sessionId as string | undefined
  if (!activeSessionId || activeSessionId === 'new') {
    return serverSessions
  }

  const optimisticTitle = optimisticTitleHints.value[activeSessionId]?.trim()
  if (!optimisticTitle) {
    return serverSessions
  }

  const alreadyExists = serverSessions.some((session) => session.session_id === activeSessionId)
  if (alreadyExists) {
    return serverSessions
  }

  return [{
    session_id: activeSessionId,
    title: optimisticTitle,
    latest_message: optimisticTitle,
    latest_message_at: Date.now(),
    status: SessionStatus.PENDING,
    unread_message_count: 0,
    is_shared: false,
  }, ...serverSessions]
}

const handleSessionTitleHint = (event: Event) => {
  const detail = (event as CustomEvent<SessionTitleHintDetail>).detail
  if (!detail?.sessionId) return

  const optimisticTitle = detail.title?.trim()
  if (!optimisticTitle) return

  optimisticTitleHints.value = {
    ...optimisticTitleHints.value,
    [detail.sessionId]: optimisticTitle,
  }

  const existing = sessions.value.find((session) => session.session_id === detail.sessionId)
  if (existing) {
    if (!existing.title || isPlaceholderTitle(existing.title)) {
      existing.title = optimisticTitle
    }
    if (!existing.latest_message) {
      existing.latest_message = optimisticTitle
      existing.latest_message_at = Date.now()
    }
    return
  }

  sessions.value = mergeWithOptimisticSession(sessions.value)
}

// Function to fetch sessions data
const updateSessions = async () => {
  try {
    const response = await getSessions()
    sessions.value = mergeWithOptimisticSession(response.sessions)
  } catch {
    // Session fetch failed - will retry on next navigation
  }
}

// Function to fetch sessions data
const fetchSessions = async () => {
  try {
    if (cancelGetSessionsSSE.value) {
      cancelGetSessionsSSE.value()
      cancelGetSessionsSSE.value = null
    }
    cancelGetSessionsSSE.value = await getSessionsSSE({
      onOpen: () => {
        // SSE connection opened
      },
      onMessage: (event) => {
        sessions.value = mergeWithOptimisticSession(event.data.sessions)
      },
      onError: () => {
        // SSE error - will reconnect automatically
      },
      onClose: () => {
        // SSE connection closed
      }
    })
  } catch {
    // SSE connection failed - will use cached sessions
  }
}

const handleNewTaskClick = async () => {
  // Stop current running session to release sandbox/browser resources
  const currentSessionId = route.params.sessionId as string | undefined;
  if (currentSessionId) {
    const currentSession = sessions.value.find(s => s.session_id === currentSessionId);
    if (currentSession && [SessionStatus.RUNNING, SessionStatus.PENDING, SessionStatus.INITIALIZING].includes(currentSession.status)) {
      try {
        await stopSession(currentSessionId);
        handleSessionStatusChange(currentSessionId, SessionStatus.COMPLETED);
      } catch {
        // Non-critical — backend safety net will clean up on next create_session
      }
    }
  }
  router.push('/')
}

const handleLibraryClick = () => {
  router.push('/chat/history')
}

const handleSessionDeleted = (sessionId: string) => {
  sessions.value = sessions.value.filter(session => session.session_id !== sessionId);
}

const handleSessionStopped = (sessionId: string) => {
  handleSessionStatusChange(sessionId, SessionStatus.COMPLETED);
}

// Handle keyboard shortcuts
const handleKeydown = (event: KeyboardEvent) => {
  // Check for Command + K (Mac) or Ctrl + K (Windows/Linux)
  if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
    event.preventDefault()
    handleNewTaskClick()
  }
}

// Unsubscribe function for session status listener
let unsubscribeStatusChange: (() => void) | null = null;

onMounted(async () => {
  // Initial fetch of sessions
  fetchSessions()

  // Add keyboard event listener
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('pythinker:session-title-hint', handleSessionTitleHint as EventListener)

  // Listen for session status changes from other components
  unsubscribeStatusChange = onStatusChange(handleSessionStatusChange)
})

onUnmounted(() => {
  if (cancelGetSessionsSSE.value) {
    cancelGetSessionsSSE.value()
    cancelGetSessionsSSE.value = null
  }

  // Remove keyboard event listener
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('pythinker:session-title-hint', handleSessionTitleHint as EventListener)

  // Unsubscribe from session status changes
  if (unsubscribeStatusChange) {
    unsubscribeStatusChange()
    unsubscribeStatusChange = null
  }
})

// Only update sessions when navigating to/from chat pages (not on every route change)
// The SSE connection will handle real-time updates
watch(() => route.path, async (newPath, oldPath) => {
  // Only update if moving between different session pages or to/from home
  const isSessionChange =
    newPath.startsWith('/chat/') !== oldPath?.startsWith('/chat/') ||
    (newPath === '/' && oldPath !== '/');

  if (isSessionChange) {
    await updateSessions();
  }
})
</script>

<style scoped>
/* ===== LEFT PANEL LAYOUT ===== */
.left-panel-container {
  --left-panel-width-expanded: 264px;
  --left-panel-width-collapsed: 64px;
}

.left-panel-expanded {
  width: var(--left-panel-width-expanded);
  transition: width 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}

.left-panel-collapsed {
  width: var(--left-panel-width-collapsed);
  transition: width 0.36s cubic-bezier(0.4, 0, 0.2, 1);
}

.left-panel-content {
  transition: opacity 0.2s, transform 0.2s, width 0.2s;
}

.left-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.left-panel-header .logo-robot {
  color: var(--text-primary);
}

.collapse-btn {
  display: inline-flex;
  width: 36px;
  height: 36px;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s ease;
  color: var(--icon-secondary);
  background: transparent;
  border: 1px solid transparent;
  margin-left: auto;
}

.collapse-btn:hover {
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-main);
  color: var(--icon-primary);
}

.left-panel-expanded .left-panel-content {
  width: var(--left-panel-width-expanded);
}

.left-panel-collapsed .left-panel-content {
  width: 0px;
}

/* ===== COLLAPSED ICON SIDEBAR ===== */
.collapsed-sidebar {
  width: var(--left-panel-width-collapsed);
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  background: var(--background-nav);
  border-right: 1px solid var(--border-main);
}

.collapsed-sidebar-top,
.collapsed-sidebar-bottom {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.collapsed-icon-btn {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s ease;
  color: var(--icon-secondary);
  background: transparent;
  border: none;
}

.collapsed-icon-btn:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--icon-primary);
}

/* ===== NAV SECTIONS ===== */
.nav-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-light);
  margin-bottom: 10px;
}

.nav-section-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-tertiary);
  padding: 4px 6px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 36px;
  padding: 0 10px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  transition: all 0.15s ease;
  background: transparent;
  border: 1px solid transparent;
  cursor: pointer;
}

.nav-item:hover {
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-light);
}

.nav-item-muted {
  color: var(--text-secondary);
}

.nav-icon {
  width: 16px;
  height: 16px;
  color: var(--icon-secondary);
}

.left-panel-section-title {
  padding: 6px 14px 2px 14px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-tertiary);
}

/* ===== NEW TASK BUTTON ===== */
.new-task-btn {
  display: flex;
  width: 100%;
  min-width: 36px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 14px;
  height: 38px;
  border-radius: 12px;
  background: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-light);
  cursor: pointer;
  transition: all 0.2s ease;
  color: var(--text-primary);
  font-weight: 600;
}

.new-task-btn:hover {
  background: var(--fill-tsp-gray-dark);
  border-color: var(--border-main);
  box-shadow: none;
}

.new-task-btn:active {
  transform: scale(0.98);
}

.new-task-label {
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
}

.new-task-shortcut {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
  opacity: 0.7;
}

.shortcut-key {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  border-radius: 4px;
  background: var(--bolt-elements-bg-depth-2);
  border: 1px solid var(--bolt-elements-borderColor);
  font-size: 10px;
  font-weight: 600;
  color: var(--bolt-elements-textTertiary);
}

:global(.dark) .new-task-btn {
  background: #2a2d34;
  border-color: #3a3f49;
  color: #ebf0f6;
}

:global(.dark) .new-task-btn:hover {
  background: #333843;
  border-color: #4b5260;
}

:global(.dark) .new-task-shortcut {
  opacity: 0.92;
}

:global(.dark) .shortcut-key {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  color: #d7deea;
}

/* ===== SEARCH BAR ===== */
.search-bar-container {
  padding: 0 12px 4px;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 8px;
  border-radius: 8px;
  background: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-light);
  transition: border-color 0.15s ease;
}

.search-bar:focus-within {
  border-color: var(--bolt-elements-borderColorActive);
}

.search-bar-icon {
  flex-shrink: 0;
  color: var(--icon-tertiary);
}

.search-input {
  flex: 1;
  min-width: 0;
  height: 100%;
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  color: var(--text-primary);
}

.search-input::placeholder {
  color: var(--text-tertiary);
}

.search-clear-btn,
.search-close-btn {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  color: var(--icon-tertiary);
  cursor: pointer;
  transition: all 0.15s ease;
  background: transparent;
  border: none;
}

.search-clear-btn:hover,
.search-close-btn:hover {
  background: var(--bolt-elements-bg-depth-2);
  color: var(--text-secondary);
}

.search-no-results {
  padding: 8px 4px 0;
  font-size: 12px;
  color: var(--text-tertiary);
  text-align: center;
}
</style>
