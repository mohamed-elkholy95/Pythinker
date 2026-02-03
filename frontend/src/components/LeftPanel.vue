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
      <div class="flex items-center px-4 py-3 h-[56px]">
        <div
          class="flex h-8 w-8 items-center justify-center cursor-pointer hover:bg-[var(--fill-tsp-gray-main)] rounded-lg transition-colors"
          @click="toggleLeftPanel">
          <PanelLeft class="h-5 w-5 text-[var(--icon-secondary)]" />
        </div>
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
      <div class="flex flex-col flex-1 min-h-0">
        <div v-if="sessions.length > 0" class="flex flex-col flex-1 min-h-0 overflow-auto pt-1 pb-4 px-2 overflow-x-hidden minimal-scrollbar">
          <SessionItem v-for="session in sessions" :key="session.session_id" :session="session"
            @deleted="handleSessionDeleted"
            @stopped="handleSessionStopped" />
        </div>
        <div v-else class="flex flex-1 flex-col items-center justify-center gap-4">
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
import { PanelLeft, Plus, Command, MessageSquareDashed, Settings2 } from 'lucide-vue-next';
import SessionItem from './SessionItem.vue';
import { useLeftPanel } from '../composables/useLeftPanel';
import { ref, onMounted, watch, onUnmounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getSessionsSSE, getSessions } from '../api/agent';
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

// Function to fetch sessions data
const updateSessions = async () => {
  try {
    const response = await getSessions()
    sessions.value = response.sessions
  } catch (error) {
    console.error('Failed to fetch sessions:', error)
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
        console.log('Sessions SSE opened')
      },
      onMessage: (event) => {
        sessions.value = event.data.sessions
      },
      onError: (error) => {
        console.error('Failed to fetch sessions:', error)
      },
      onClose: () => {
        console.log('Sessions SSE closed')
      }
    })
  } catch (error) {
    console.error('Failed to fetch sessions:', error)
  }
}

const handleNewTaskClick = () => {
  router.push('/')
}

const handleSessionDeleted = (sessionId: string) => {
  console.log('handleSessionDeleted', sessionId)
  sessions.value = sessions.value.filter(session => session.session_id !== sessionId);
}

const handleSessionStopped = (sessionId: string) => {
  console.log('handleSessionStopped', sessionId)
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
  --left-panel-width-expanded: 280px;
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

/* ===== NEW TASK BUTTON ===== */
.new-task-btn {
  display: flex;
  width: 100%;
  min-width: 36px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 14px;
  height: 40px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(59, 130, 246, 0.05) 100%);
  border: 1px solid rgba(59, 130, 246, 0.2);
  cursor: pointer;
  transition: all 0.2s ease;
  color: var(--bolt-elements-button-primary-text);
  font-weight: 500;
}

.new-task-btn:hover {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.15) 0%, rgba(59, 130, 246, 0.08) 100%);
  border-color: rgba(59, 130, 246, 0.35);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.15);
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
</style>
