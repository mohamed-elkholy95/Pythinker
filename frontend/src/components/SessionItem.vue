<template>
  <div class="px-2">
    <div @click="handleSessionClick"
      role="button"
      tabindex="0"
      @keydown.enter="handleSessionClick"
      @keydown.space.prevent="handleSessionClick"
      class="group flex h-10 cursor-pointer items-center gap-3 rounded-lg px-2 transition-colors border border-transparent"
      :class="isCurrentSession ? 'bg-[var(--background-white-main)] border-[var(--border-main)] shadow-[0_6px_14px_rgba(15,23,42,0.08)]' : 'hover:bg-[var(--fill-tsp-gray-main)]'">

      <!-- Icon area -->
      <div class="relative flex-shrink-0 w-7 h-7 flex items-center justify-center">
        <!-- Blue spinning circle for running sessions -->
        <template v-if="isRunning">
          <svg class="w-6 h-6 animate-spin-slow" viewBox="0 0 24 24" fill="none">
            <circle
              cx="12"
              cy="12"
              r="10"
              stroke="#e5e7eb"
              stroke-width="2.5"
              class="dark:stroke-gray-700"
            />
            <path
              d="M12 2a10 10 0 0 1 10 10"
              stroke="var(--bolt-elements-item-contentAccent)"
              stroke-width="2.5"
              stroke-linecap="round"
            />
          </svg>
        </template>
        <!-- Task icon for non-running sessions -->
        <template v-else>
          <TaskIcon :title="session.title || ''" :session-id="session.session_id" />
        </template>
        <!-- Unread badge -->
        <div v-if="session.unread_message_count > 0 && !isCurrentSession"
          class="flex h-4 min-w-[16px] items-center justify-center rounded-full bg-[var(--function-error)] absolute -end-1 -top-1">
          <span class="px-1 text-xs text-[var(--text-white)]">{{ session.unread_message_count }}</span>
        </div>
      </div>

      <!-- Title -->
      <div class="flex-1 min-w-0">
        <span class="block truncate text-sm text-[var(--text-primary)]"
          :class="isCurrentSession ? 'font-medium' : 'font-normal'"
          :title="displayTitle">
          {{ displayTitle }}
        </span>
      </div>

      <!-- Menu button (appears on hover) -->
      <button type="button" @click="handleSessionMenuClick"
        class="w-6 h-6 flex-shrink-0 rounded-md flex items-center justify-center cursor-pointer opacity-100 sm:opacity-0 sm:group-hover:opacity-100 hover:bg-[var(--fill-tsp-gray-dark)] transition-opacity"
        :class="isContextMenuOpen ? 'opacity-100 bg-[var(--fill-tsp-gray-dark)]' : ''"
        aria-haspopup="menu"
        :aria-expanded="isContextMenuOpen"
        aria-label="Session options">
        <Ellipsis :size="14" class="text-[var(--icon-secondary)]" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Ellipsis } from 'lucide-vue-next';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import { ListSessionItem, SessionStatus } from '../types/response';
import TaskIcon from './icons/TaskIcon.vue';
import { useContextMenu, createMenuItem, createDangerMenuItem } from '../composables/useContextMenu';
import { useDialog } from '../composables/useDialog';
import { deleteSession, stopSession, shareSession, renameSession } from '../api/agent';
import { showSuccessToast, showErrorToast } from '../utils/toast';
import { Trash, Square, Share2, Pencil } from 'lucide-vue-next';
import { copyToClipboard } from '../utils/dom';

interface Props {
  session: ListSessionItem;
}

const props = defineProps<Props>();

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const { showContextMenu } = useContextMenu();
const { showConfirmDialog, showPromptDialog } = useDialog();
const isContextMenuOpen = ref(false);

const emit = defineEmits<{
  (e: 'deleted', sessionId: string): void
  (e: 'stopped', sessionId: string): void
  (e: 'renamed', sessionId: string, newTitle: string): void
}>();

const currentSessionId = computed(() => {
  return route.params.sessionId as string;
});

const isCurrentSession = computed(() => {
  return currentSessionId.value === props.session.session_id;
});

const isAgentsWorkspace = computed(() =>
  route.matched.some((record) => record.meta?.workspace === 'agents')
);

const isRunning = computed(() => {
  return props.session.status === SessionStatus.RUNNING || props.session.status === SessionStatus.PENDING;
});

const displayTitle = computed(() => {
  if (props.session.title) return props.session.title;
  if (props.session.latest_message) {
    const msg = props.session.latest_message.trim();
    return msg.length > 40 ? msg.substring(0, 40) + '...' : msg;
  }
  return t('New Chat');
});

const handleSessionClick = () => {
  if (isAgentsWorkspace.value && props.session.source === 'telegram') {
    router.push({
      name: 'agents-session',
      params: { sessionId: props.session.session_id },
    });
    return;
  }

  router.push(`/chat/${props.session.session_id}`);
};

const handleSessionMenuClick = (event: MouseEvent) => {
  event.stopPropagation();

  const target = event.currentTarget as HTMLElement;
  isContextMenuOpen.value = true;

  const menuItems = [
    // Only show Stop if session is running
    ...(isRunning.value ? [createMenuItem('stop', t('Stop'), { icon: Square })] : []),
    createMenuItem('rename', t('Rename'), { icon: Pencil }),
    createMenuItem('share', t('Share'), { icon: Share2 }),
    createDangerMenuItem('delete', t('Delete'), { icon: Trash }),
  ];

  showContextMenu(props.session.session_id, target, menuItems, (itemKey: string, _: string) => {
    if (itemKey === 'stop') {
      stopSession(props.session.session_id).then(() => {
        showSuccessToast(t('Session stopped'));
        emit('stopped', props.session.session_id);
      }).catch(() => {
        showErrorToast(t('Failed to stop session'));
      });
    } else if (itemKey === 'rename') {
      showPromptDialog({
        title: t('Rename Session'),
        placeholder: t('Enter new name'),
        defaultValue: props.session.title || displayTitle.value,
        confirmText: t('Rename'),
        cancelText: t('Cancel'),
        onConfirm: async (newTitle: string) => {
          if (newTitle.trim()) {
            try {
              await renameSession(props.session.session_id, newTitle.trim());
              showSuccessToast(t('Renamed successfully'));
              emit('renamed', props.session.session_id, newTitle.trim());
            } catch {
              showErrorToast(t('Failed to rename session'));
            }
          }
        }
      });
    } else if (itemKey === 'share') {
      shareSession(props.session.session_id).then(() => {
        const shareUrl = `${window.location.origin}/share/${props.session.session_id}`;
        copyToClipboard(shareUrl);
        showSuccessToast(t('Share link copied to clipboard'));
      }).catch(() => {
        showErrorToast(t('Failed to share session'));
      });
    } else if (itemKey === 'delete') {
      showConfirmDialog({
        title: t('Are you sure you want to delete this session?'),
        content: t('The chat history of this session cannot be recovered after deletion.'),
        confirmText: t('Delete'),
        cancelText: t('Cancel'),
        confirmType: 'danger',
        onConfirm: () => {
          deleteSession(props.session.session_id).then(() => {
            showSuccessToast(t('Deleted successfully'));
            emit('deleted', props.session.session_id);
          }).catch(() => {
            showErrorToast(t('Failed to delete session'));
          });
          if (isCurrentSession.value) {
            router.push('/');
          }
        }
      })
    }
  }, (_: string) => {
    isContextMenuOpen.value = false;
  });
};
</script>

<style scoped>
@keyframes spin-slow {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
.animate-spin-slow {
  animation: spin-slow 1.2s linear infinite;
}
</style>
