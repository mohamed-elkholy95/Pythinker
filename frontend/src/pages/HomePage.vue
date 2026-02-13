<template>
  <SimpleBar>
    <div
      class="flex flex-col h-full flex-1 min-w-0 mx-auto w-full sm:min-w-[390px] px-5 justify-start items-start gap-2 relative max-w-full sm:max-w-full">
      <!-- Minimal header - logo and user avatar, blended into background -->
      <div class="w-full pt-4 pb-4 ps-[8px] pe-[8px] sm:ps-5 sm:pe-5 sticky top-0 z-10">
        <div class="flex justify-between items-center w-full">
          <div class="flex items-center gap-1 flex-shrink-0">
            <button
              class="sm:hidden h-8 w-8 inline-flex items-center justify-center rounded-lg hover:bg-[var(--fill-tsp-gray-main)] transition-colors -ml-0.5"
              @click="toggleLeftPanel"
              aria-label="Open sidebar"
            >
              <Menu :size="20" class="text-[var(--icon-secondary)]" />
            </button>
            <div v-if="!isLeftPanelShow" class="h-8 relative z-20 overflow-hidden flex gap-2 items-center">
              <Bot :size="20" class="logo-robot" :stroke-width="2.2" />
              <PythinkerLogoTextIcon />
            </div>
          </div>
          <div class="flex items-center gap-2 ml-auto">
            <div class="relative flex items-center" aria-expanded="false" aria-haspopup="dialog"
              @mouseenter="handleUserMenuEnter" @mouseleave="handleUserMenuLeave">
              <div class="relative flex items-center justify-center font-bold cursor-pointer flex-shrink-0">
                <div
                  class="relative flex items-center justify-center font-bold flex-shrink-0 rounded-full overflow-hidden bg-[var(--bolt-elements-item-contentAccent)] text-white"
                  style="width: 32px; height: 32px; font-size: 16px;">
                  {{ avatarLetter }}</div>
              </div>
              <!-- User Menu -->
              <div v-if="showUserMenu" @mouseenter="handleUserMenuEnter" @mouseleave="handleUserMenuLeave"
                class="absolute top-full right-0 mt-1 mr-[-15px] z-50">
                <UserMenu />
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="home-content">
        <!-- Greeting -->
        <div class="greeting-section">
          <h1 class="greeting-primary">
            {{ $t('Hello') }}, {{ currentUser?.fullname }}
          </h1>
          <p class="greeting-secondary">
            {{ $t('What can I do for you?') }}
          </p>
        </div>

        <!-- Chat Input -->
        <div class="chat-input-wrapper">
          <ChatBox
            :rows="1"
            v-model="message"
            @submit="handleSubmit"
            :isRunning="false"
            :attachments="attachments"
            :showConnectorBanner="true"
            expand-direction="down"
          />
        </div>

        <!-- Feature Buttons -->
        <div class="feature-buttons">
          <button
            v-for="feature in visibleFeatures"
            :key="feature.id"
            @click="handleFeatureClick(feature)"
            class="feature-btn"
          >
            <component :is="feature.icon" :size="17" class="feature-icon" />
            <span>{{ $t(feature.label) }}</span>
          </button>

          <!-- More Dropdown -->
          <div class="relative" ref="moreDropdownRef">
            <button
              @click="toggleMoreDropdown"
              class="feature-btn feature-btn-more"
              :class="{ 'active': showMoreDropdown }"
            >
              <span>{{ $t('More') }}</span>
            </button>

            <!-- Dropdown Menu -->
            <Transition
              enter-active-class="transition duration-150 ease-out"
              enter-from-class="transform scale-95 opacity-0 translate-y-2"
              enter-to-class="transform scale-100 opacity-100 translate-y-0"
              leave-active-class="transition duration-100 ease-in"
              leave-from-class="transform scale-100 opacity-100 translate-y-0"
              leave-to-class="transform scale-95 opacity-0 translate-y-2"
            >
              <div v-if="showMoreDropdown" class="more-dropdown">
                <button
                  v-for="item in moreFeatures"
                  :key="item.id"
                  @click="handleFeatureClick(item)"
                  class="more-dropdown-item"
                >
                  <component :is="item.icon" :size="17" class="more-dropdown-icon" />
                  <span>{{ $t(item.label) }}</span>
                </button>
              </div>
            </Transition>
          </div>
        </div>
      </div>
    </div>
  </SimpleBar>
  <ConnectorsDialog />
</template>

<script setup lang="ts">
import SimpleBar from '../components/SimpleBar.vue';
import { ref, onMounted, computed, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import ChatBox from '../components/ChatBox.vue';
import type { AgentMode } from '../api/agent';
import {
  Search, Palette, Bot, Menu,
  Calendar, Table2, BarChart3, Video, AudioLines, MessageSquare, BookOpen
} from 'lucide-vue-next';
import PythinkerLogoTextIcon from '../components/icons/PythinkerLogoTextIcon.vue';
import type { FileInfo } from '../api/file';
import { useFilePanel } from '../composables/useFilePanel';
import { useAuth } from '../composables/useAuth';
import { useLeftPanel } from '../composables/useLeftPanel';
import UserMenu from '../components/UserMenu.vue';
import ConnectorsDialog from '@/components/connectors/ConnectorsDialog.vue';
import type { Component } from 'vue';

// Feature type definition
interface Feature {
  id: string;
  label: string;
  icon: Component;
  mode: AgentMode;
  prompt?: string;
}

const router = useRouter();
const message = ref('');
const isSubmitting = ref(false);
const attachments = ref<FileInfo[]>([]);
const pendingSkillId = ref<string | null>(null);
const { hideFilePanel } = useFilePanel();
const { currentUser } = useAuth();
const { isLeftPanelShow, toggleLeftPanel } = useLeftPanel();

// Visible feature buttons
const visibleFeatures: Feature[] = [
  {
    id: 'research',
    label: 'Research',
    icon: Search,
    mode: 'agent',
    prompt: 'Create a comprehensive research report on: '
  },
  {
    id: 'deep-research',
    label: 'Deep Research',
    icon: Search,
    mode: 'agent',
    prompt: 'Conduct a deep research with multiple parallel searches on: '
  },
  {
    id: 'design',
    label: 'Design',
    icon: Palette,
    mode: 'agent',
    prompt: 'Create a design for: '
  }
];

// More dropdown features
const moreFeatures: Feature[] = [
  {
    id: 'schedule',
    label: 'Schedule task',
    icon: Calendar,
    mode: 'agent',
    prompt: 'Schedule a task to: '
  },
  {
    id: 'wide-research',
    label: 'Wide Research',
    icon: Search,
    mode: 'agent',
    prompt: 'Conduct a wide and in-depth research on: '
  },
  {
    id: 'spreadsheet',
    label: 'Spreadsheet',
    icon: Table2,
    mode: 'agent',
    prompt: 'Create a spreadsheet for: '
  },
  {
    id: 'visualization',
    label: 'Visualization',
    icon: BarChart3,
    mode: 'agent',
    prompt: 'Create a data visualization for: '
  },
  {
    id: 'video',
    label: 'Video',
    icon: Video,
    mode: 'agent',
    prompt: 'Create a video about: '
  },
  {
    id: 'audio',
    label: 'Audio',
    icon: AudioLines,
    mode: 'agent',
    prompt: 'Create audio content about: '
  },
  {
    id: 'chat',
    label: 'Chat mode',
    icon: MessageSquare,
    mode: 'discuss',
    prompt: ''
  },
  {
    id: 'playbook',
    label: 'Playbook',
    icon: BookOpen,
    mode: 'agent',
    prompt: 'Create a playbook for: '
  }
];

// Get first letter of user's fullname for avatar display
const avatarLetter = computed(() => {
  return currentUser.value?.fullname?.charAt(0)?.toUpperCase() || 'M';
});

// User menu state
const showUserMenu = ref(false);
const userMenuTimeout = ref<number | null>(null);

// More dropdown state
const showMoreDropdown = ref(false);
const moreDropdownRef = ref<HTMLElement | null>(null);

// Show user menu on hover
const handleUserMenuEnter = () => {
  if (userMenuTimeout.value) {
    clearTimeout(userMenuTimeout.value);
    userMenuTimeout.value = null;
  }
  showUserMenu.value = true;
};

// Hide user menu with delay
const handleUserMenuLeave = () => {
  userMenuTimeout.value = setTimeout(() => {
    showUserMenu.value = false;
  }, 200); // 200ms delay to allow moving to menu
};

// Toggle more dropdown
const toggleMoreDropdown = () => {
  showMoreDropdown.value = !showMoreDropdown.value;
};

// Close dropdown when clicking outside
const handleClickOutside = (event: MouseEvent) => {
  if (moreDropdownRef.value && !moreDropdownRef.value.contains(event.target as Node)) {
    showMoreDropdown.value = false;
  }
};

// Handle insert message event from settings (e.g., "Build with Pythinker" button)
const handleInsertMessage = (event: Event) => {
  const detail = (event as CustomEvent<{ message: string; skillId?: string }>).detail;
  message.value = detail.message;
  // Store skillId for session creation (forwarded via history.state)
  if (detail.skillId) {
    pendingSkillId.value = detail.skillId;
  }
};

onMounted(() => {
  hideFilePanel();
  document.addEventListener('click', handleClickOutside);
  // Listen for message insert event from settings dialog
  window.addEventListener('pythinker:insert-chat-message', handleInsertMessage as EventListener);
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
  window.removeEventListener('pythinker:insert-chat-message', handleInsertMessage as EventListener);
});

// Handle feature button click
const handleFeatureClick = async (feature: Feature) => {
  showMoreDropdown.value = false;

  if (feature.id === 'chat') {
    // Chat mode - create session with discuss mode directly
    await createSessionWithMode('discuss');
  } else if (feature.prompt) {
    // Set the prompt in the message input
    message.value = feature.prompt;
  }
};

// Create session with specific mode
const createSessionWithMode = async (mode: AgentMode, initialMessage?: string) => {
  if (isSubmitting.value) return;
  isSubmitting.value = true;

  router.push({
    path: '/chat/new',
    state: {
      pendingSessionCreate: true,
      mode,
      message: initialMessage ?? '',
      skills: [],
      files: attachments.value.map((file: FileInfo) => ({
        file_id: file.file_id,
        filename: file.filename,
        content_type: file.content_type,
        size: file.size,
        upload_date: file.upload_date
      }))
    }
  });
};

const handleSubmit = async (skillIds: string[] = []) => {
  // Merge pending skill from "Build with Pythinker" button if present
  if (pendingSkillId.value && !skillIds.includes(pendingSkillId.value)) {
    skillIds = [...skillIds, pendingSkillId.value];
  }
  pendingSkillId.value = null;

  const trimmedMessage = message.value.trim();
  if ((trimmedMessage || skillIds.includes('skill-creator')) && !isSubmitting.value) {
    isSubmitting.value = true;
    let submitMessage = message.value;
    if (skillIds.includes('skill-creator')) {
      const trimmed = submitMessage.trim();
      const hasCommand = trimmed.toLowerCase().includes('/skill-creator');
      if (!trimmed) {
        submitMessage = 'Help me create a skill together using /skill-creator. First ask me what the skill should do.';
      } else if (!hasCommand) {
        submitMessage = `/skill-creator ${trimmed}`;
      }
    }

    router.push({
      path: '/chat/new',
      state: {
        pendingSessionCreate: true,
        mode: 'agent',
        message: submitMessage,
        skills: skillIds,
        files: attachments.value.map((file: FileInfo) => ({
          file_id: file.file_id,
          filename: file.filename,
          content_type: file.content_type,
          size: file.size,
          upload_date: file.upload_date
        }))
      }
    });
  }
};
</script>

<style scoped>
/* ===== CONTENT AREA ===== */
.home-content {
  width: 100%;
  max-width: 860px;
  min-width: 390px;
  margin: 0 auto;
  /* Position content centered vertically */
  padding-top: 18vh;
  padding-bottom: 100px;
}

@media (max-width: 640px) {
  .home-content {
    max-width: 100%;
    min-width: 0;
    padding-top: 12vh;
  }
}

/* ===== GREETING ===== */
.greeting-section {
  padding: 0 16px;
  margin-bottom: 28px;
  text-align: center;
}

.greeting-primary {
  font-size: 16px;
  font-weight: 500;
  line-height: 1.3;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.greeting-secondary {
  font-size: 32px;
  font-weight: 400;
  line-height: 1.2;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

/* ===== CHAT INPUT WRAPPER ===== */
.chat-input-wrapper {
  width: 100%;
  margin-top: 8px;
  padding: 0 8px;
}

/* Home page chatbox uses ChatBox component visual system directly */
:deep(.chat-input-wrapper .chatbox-shell) {
  background: transparent;
}

:deep(.chat-input-wrapper .chatbox-input-area) {
  padding-left: 20px;
  padding-right: 20px;
}

:deep(.chat-input-wrapper .chatbox-textarea) {
  font-size: 15px;
  font-weight: 400;
  line-height: 1.5;
  min-height: 28px;
  color: var(--text-primary);
}

:deep(.chat-input-wrapper .chatbox-textarea::placeholder) {
  color: var(--text-disable);
}

:deep(.chat-input-wrapper .chatbox-footer) {
  padding: 0 14px;
  margin-top: 4px;
}

/* ===== FEATURE BUTTONS ===== */
.feature-buttons {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-top: 24px;
  padding: 0 16px;
}

.feature-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--background-card);
  border: 1px solid var(--border-main);
  color: var(--text-primary);
  box-shadow: 0 1px 3px var(--shadow-XS);
}

.feature-btn:hover {
  border-color: var(--border-dark);
  color: var(--text-primary);
  box-shadow: 0 2px 8px var(--shadow-S);
}

.feature-btn:active {
  transform: scale(0.98);
}

.feature-icon {
  color: var(--text-secondary);
  flex-shrink: 0;
  transition: color 0.2s ease;
}

.feature-btn:hover .feature-icon {
  color: var(--text-primary);
}

.feature-btn-more {
  padding-left: 22px;
  padding-right: 22px;
}

.feature-btn-more.active {
  border-color: var(--border-dark);
}

.feature-btn:focus-visible {
  outline: 2px solid var(--border-btn-primary);
  outline-offset: 2px;
}

/* ===== MORE DROPDOWN ===== */
.more-dropdown {
  position: absolute;
  right: 0;
  bottom: calc(100% + 8px);
  width: 220px;
  padding: 6px;
  border-radius: 14px;
  z-index: 50;
  background: var(--fill-input-chat);
  border: 1px solid var(--bolt-elements-borderColor);
  box-shadow: var(--shadow-L);
}

.more-dropdown-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  color: var(--bolt-elements-textSecondary);
  text-align: left;
  cursor: pointer;
  transition: all 0.15s ease;
}

.more-dropdown-item:hover {
  background: var(--bolt-elements-item-backgroundAccent);
  color: var(--bolt-elements-textPrimary);
}

.more-dropdown-icon {
  color: var(--bolt-elements-textTertiary);
  transition: color 0.15s ease;
}

.more-dropdown-item:hover .more-dropdown-icon {
  color: var(--bolt-elements-item-contentAccent);
}
</style>
