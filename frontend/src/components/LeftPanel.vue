<template>
  <div
    class="left-panel-container h-full flex flex-col"
    :class="{
      'left-panel-expanded': isLeftPanelShow,
      'left-panel-collapsed fixed top-0 start-0 bottom-0 z-[1]': !isLeftPanelShow
    }"
  >
    <div
      class="left-panel-content flex flex-col overflow-hidden bg-[var(--background-nav)]"
      :class="{
        'h-full opacity-100 translate-x-0 border-r border-[var(--border-main)]': isLeftPanelShow,
        'fixed top-1 start-1 bottom-1 z-[1] border dark:border border-[var(--border-main)] dark:border-[var(--border-light)] rounded-xl shadow-[0px_8px_32px_0px_rgba(0,0,0,0.16),0px_0px_0px_1px_rgba(0,0,0,0.06)] opacity-0 pointer-events-none -translate-x-10': !isLeftPanelShow
      }"
    >
      <div class="flex">
        <div class="flex items-center px-3 py-3 flex-row h-[52px] gap-1 justify-end w-full">
          <div class="flex justify-between w-full px-1 pt-2">
            <div class="relative flex">
              <div
                class="flex h-7 w-7 items-center justify-center cursor-pointer hover:bg-[var(--fill-tsp-gray-main)] rounded-md"
                @click="toggleLeftPanel">
                <PanelLeft class="h-5 w-5 text-[var(--icon-secondary)]" />
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="px-3 mb-1 flex justify-center flex-shrink-0">
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
        <div v-if="sessions.length > 0" class="flex flex-col flex-1 min-h-0 overflow-auto pt-2 pb-5 overflow-x-hidden">
          <SessionItem v-for="session in sessions" :key="session.session_id" :session="session"
            @deleted="handleSessionDeleted" />
        </div>
        <div v-else class="flex flex-1 flex-col items-center justify-center gap-4">
          <div class="flex flex-col items-center gap-2 text-[var(--text-tertiary)]">
            <MessageSquareDashed :size="38" />
            <span class="text-sm font-medium">{{ t('Create a task to get started') }}</span></div>
        </div>
      </div>
      <div class="mt-auto border-t border-[var(--border-light)] p-3">
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
import { ListSessionItem } from '../types/response';
import { useI18n } from 'vue-i18n';
import { useSettingsDialog } from '@/composables/useSettingsDialog';
import { useAuth } from '@/composables/useAuth';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import UserMenu from './UserMenu.vue';

const { t } = useI18n()
const { isLeftPanelShow, toggleLeftPanel } = useLeftPanel()
const { openSettingsDialog } = useSettingsDialog()
const { currentUser } = useAuth()
const route = useRoute()
const router = useRouter()

const sessions = ref<ListSessionItem[]>([])
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

// Handle keyboard shortcuts
const handleKeydown = (event: KeyboardEvent) => {
  // Check for Command + K (Mac) or Ctrl + K (Windows/Linux)
  if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
    event.preventDefault()
    handleNewTaskClick()
  }
}

onMounted(async () => {
  // Initial fetch of sessions
  fetchSessions()

  // Add keyboard event listener
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  if (cancelGetSessionsSSE.value) {
    cancelGetSessionsSSE.value()
    cancelGetSessionsSSE.value = null
  }

  // Remove keyboard event listener
  window.removeEventListener('keydown', handleKeydown)
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
/* CSS custom properties for configurable widths */
.left-panel-container {
  --left-panel-width-expanded: 300px;
  --left-panel-width-collapsed: 24px;
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
  border-radius: 10px;
  background: var(--bolt-elements-button-primary-background);
  border: 1px solid var(--bolt-elements-borderColor);
  cursor: pointer;
  transition: all 0.2s ease;
  color: var(--bolt-elements-button-primary-text);
}

.new-task-btn:hover {
  background: var(--bolt-elements-button-primary-backgroundHover);
  border-color: var(--bolt-elements-borderColorActive);
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
  gap: 3px;
  margin-left: 4px;
}

.shortcut-key {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 4px;
  border-radius: 5px;
  background: var(--bolt-elements-bg-depth-2);
  border: 1px solid var(--bolt-elements-borderColor);
  font-size: 11px;
  font-weight: 500;
  color: var(--bolt-elements-textTertiary);
}
</style>
