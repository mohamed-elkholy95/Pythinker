<template>
  <SimpleBar>
    <div
      class="flex flex-col h-full flex-1 min-w-0 mx-auto w-full sm:min-w-[390px] px-5 justify-center items-start gap-2 relative max-w-full sm:max-w-full">
      <div class="w-full pt-4 pb-4 px-5 bg-[var(--background-gray-main)] sticky top-0 z-10 mx-[-1.25]">
        <div class="flex justify-between items-center w-full absolute left-0 right-0">
          <div class="h-8 relative z-20 overflow-hidden flex gap-2 items-center flex-shrink-0">
            <div class="relative flex items-center">
              <div @click="toggleLeftPanel" v-if="!isLeftPanelShow"
                class="flex h-7 w-7 items-center justify-center cursor-pointer rounded-md hover:bg-[var(--fill-tsp-gray-main)]">
                <PanelLeft class="size-5 text-[var(--icon-secondary)]" />
              </div>
            </div>
            <div class="flex">
              <Bot :size="30" />
              <PythinkerLogoTextIcon />
            </div>
          </div>
          <div class="flex items-center gap-2">
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
        <div class="h-8"></div>
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
          <ChatBox :rows="2" v-model="message" @submit="handleSubmit" :isRunning="false" :attachments="attachments" />
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
</template>

<script setup lang="ts">
import SimpleBar from '../components/SimpleBar.vue';
import { ref, onMounted, computed, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import ChatBox from '../components/ChatBox.vue';
import { createSession, type AgentMode } from '../api/agent';
import { showErrorToast } from '../utils/toast';
import {
  Bot, PanelLeft, Search, Presentation, Palette,
  Calendar, Table2, BarChart3, Video, AudioLines, MessageSquare, BookOpen
} from 'lucide-vue-next';
import PythinkerLogoTextIcon from '../components/icons/PythinkerLogoTextIcon.vue';
import type { FileInfo } from '../api/file';
import { useLeftPanel } from '../composables/useLeftPanel';
import { useFilePanel } from '../composables/useFilePanel';
import { useAuth } from '../composables/useAuth';
import UserMenu from '../components/UserMenu.vue';

// Feature type definition
interface Feature {
  id: string;
  label: string;
  icon: any;
  mode: AgentMode;
  prompt?: string;
}

const { t } = useI18n();
const router = useRouter();
const message = ref('');
const isSubmitting = ref(false);
const attachments = ref<FileInfo[]>([]);
const { toggleLeftPanel, isLeftPanelShow } = useLeftPanel();
const { hideFilePanel } = useFilePanel();
const { currentUser } = useAuth();

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
    id: 'slides',
    label: 'Create slides',
    icon: Presentation,
    mode: 'agent',
    prompt: 'Create a professional presentation slides about: '
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

onMounted(() => {
  hideFilePanel();
  document.addEventListener('click', handleClickOutside);
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
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

  try {
    const session = await createSession(mode);
    const sessionId = session.session_id;

    router.push({
      path: `/chat/${sessionId}`,
      state: initialMessage ? {
        message: initialMessage,
        files: attachments.value.map((file: FileInfo) => ({
          file_id: file.file_id,
          filename: file.filename,
          content_type: file.content_type,
          size: file.size,
          upload_date: file.upload_date
        }))
      } : undefined
    });
  } catch (error) {
    console.error('Failed to create session:', error);
    showErrorToast(t('Failed to create session, please try again later'));
    isSubmitting.value = false;
  }
};

const handleSubmit = async () => {
  if (message.value.trim() && !isSubmitting.value) {
    isSubmitting.value = true;

    try {
      // Create new Agent with default agent mode
      const session = await createSession('agent');
      const sessionId = session.session_id;

      // Navigate to new route with session_id, passing initial message via state
      router.push({
        path: `/chat/${sessionId}`,
        state: {
          message: message.value, files: attachments.value.map((file: FileInfo) => ({
            file_id: file.file_id,
            filename: file.filename,
            content_type: file.content_type,
            size: file.size,
            upload_date: file.upload_date
          }))
        }
      });
    } catch (error) {
      console.error('Failed to create session:', error);
      showErrorToast(t('Failed to create session, please try again later'));
      isSubmitting.value = false;
    }
  }
};
</script>

<style scoped>
/* ===== CONTENT AREA ===== */
.home-content {
  width: 100%;
  max-width: 768px;
  min-width: 390px;
  margin: 0 auto;
  margin-top: 100px;
  margin-bottom: auto;
}

@media (max-width: 640px) {
  .home-content {
    max-width: 100%;
    min-width: 0;
  }
}

/* ===== GREETING ===== */
.greeting-section {
  padding: 0 16px;
  margin-bottom: 24px;
}

.greeting-primary {
  font-size: 32px;
  font-weight: 600;
  line-height: 1.25;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.greeting-secondary {
  font-size: 32px;
  font-weight: 600;
  line-height: 1.25;
  color: var(--text-tertiary);
}

/* ===== CHAT INPUT WRAPPER ===== */
.chat-input-wrapper {
  width: 100%;
}

/* ===== FEATURE BUTTONS ===== */
.feature-buttons {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 16px;
  padding: 0 16px;
}

.feature-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  border-radius: 24px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--bolt-elements-bg-depth-1);
  border: 1px solid var(--bolt-elements-borderColor);
  color: var(--bolt-elements-textSecondary);
}

.feature-btn:hover {
  background: var(--bolt-elements-item-backgroundActive);
  border-color: var(--bolt-elements-borderColorActive);
  color: var(--bolt-elements-textPrimary);
  transform: translateY(-1px);
}

.feature-btn:active {
  transform: translateY(0);
}

.feature-icon {
  color: var(--bolt-elements-textTertiary);
  transition: color 0.2s ease;
}

.feature-btn:hover .feature-icon {
  color: var(--bolt-elements-item-contentAccent);
}

.feature-btn-more {
  padding-left: 20px;
  padding-right: 20px;
}

.feature-btn-more.active {
  background: var(--bolt-elements-item-backgroundActive);
  border-color: var(--bolt-elements-borderColorActive);
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
