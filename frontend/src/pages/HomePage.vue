<template>
  <SimpleBar>
    <div
      class="flex flex-col h-full flex-1 min-w-0 mx-auto w-full sm:min-w-[390px] px-5 justify-start items-start gap-2 relative max-w-full sm:max-w-full">

      <!-- Ambient background glow -->
      <div class="ambient-glow" aria-hidden="true" />

      <!-- Center dot-grid decoration -->
      <div class="center-grid" aria-hidden="true" />

      <!-- Header -->
      <div class="home-header w-full sticky top-0 z-10">
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
              <div class="avatar-ring cursor-pointer flex-shrink-0">
                <div class="avatar-inner">
                  {{ avatarLetter }}
                </div>
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
          <p class="greeting-eyebrow">
            {{ $t('Hello') }}, {{ currentUser?.fullname }} 👋
          </p>
          <h1 class="greeting-headline">
            Ask anything. <span class="greeting-headline-accent">I'll figure it out.</span>
          </h1>
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
            :class="['feature-btn', `feature-btn--${feature.id}`]"
          >
            <span class="feature-btn-icon-wrap">
              <component :is="feature.icon" :size="15" class="feature-icon" />
            </span>
            <span>{{ $t(feature.label) }}</span>
          </button>
        </div>
      </div>
    </div>
  </SimpleBar>
  <ConnectorsDialog />
</template>

<script setup lang="ts">
import SimpleBar from '../components/SimpleBar.vue';
import { ref, onMounted, computed, onUnmounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import ChatBox from '../components/ChatBox.vue';
import type { AgentMode, ThinkingMode, ResearchMode } from '../api/agent';
import {
  Palette, Bot, Menu,
  MessageSquare, Search
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
    prompt: 'create a comprehensive research report about: '
  },
  {
    id: 'design',
    label: 'Design',
    icon: Palette,
    mode: 'agent',
    prompt: 'Create a design for: '
  },
  {
    id: 'chat',
    label: 'Chat Mode',
    icon: MessageSquare,
    mode: 'agent',
    prompt: ''
  }
];

// Get first letter of user's fullname for avatar display (fallback to email initial)
const avatarLetter = computed(() => {
  return currentUser.value?.fullname?.charAt(0)?.toUpperCase()
    || currentUser.value?.email?.charAt(0)?.toUpperCase()
    || '?';
});

// User menu state
const showUserMenu = ref(false);
const userMenuTimeout = ref<number | null>(null);
let chatPreloadPromise: Promise<unknown> | null = null;
let chatPreloadIdleHandle: number | null = null;
let chatPreloadTimeoutHandle: number | null = null;

const preloadChatRoute = () => {
  if (chatPreloadPromise) return chatPreloadPromise;
  chatPreloadPromise = import('./ChatPage.vue');
  return chatPreloadPromise;
};

const scheduleChatRoutePreload = () => {
  if (chatPreloadPromise || chatPreloadIdleHandle !== null || chatPreloadTimeoutHandle !== null) {
    return;
  }

  const runPreload = () => {
    chatPreloadIdleHandle = null;
    chatPreloadTimeoutHandle = null;
    void preloadChatRoute();
  };

  if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
    const idleCallback = window.requestIdleCallback as (
      callback: IdleRequestCallback,
      options?: IdleRequestOptions,
    ) => number;
    chatPreloadIdleHandle = idleCallback(() => runPreload(), { timeout: 1200 });
    return;
  }

  chatPreloadTimeoutHandle = window.setTimeout(runPreload, 300);
};



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
  scheduleChatRoutePreload();
  // Listen for message insert event from settings dialog
  window.addEventListener('pythinker:insert-chat-message', handleInsertMessage as EventListener);
});

watch(message, (value) => {
  if (value.trim().length > 0) {
    void preloadChatRoute();
  }
});

onUnmounted(() => {
  window.removeEventListener('pythinker:insert-chat-message', handleInsertMessage as EventListener);
  if (chatPreloadIdleHandle !== null && typeof window !== 'undefined' && 'cancelIdleCallback' in window) {
    const cancelIdleCallback = window.cancelIdleCallback as (handle: number) => void;
    cancelIdleCallback(chatPreloadIdleHandle);
    chatPreloadIdleHandle = null;
  }
  if (chatPreloadTimeoutHandle !== null) {
    clearTimeout(chatPreloadTimeoutHandle);
    chatPreloadTimeoutHandle = null;
  }
  if (userMenuTimeout.value) {
    clearTimeout(userMenuTimeout.value);
    userMenuTimeout.value = null;
  }
});

// Handle feature button click
const handleFeatureClick = async (feature: Feature) => {
  if (feature.id === 'chat') {
    // Chat mode - create agent session with a greeting so fast path sends a welcome bubble
    await createSessionWithMode('agent', 'Hello');
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
    await router.push({
      path: '/chat/new',
      state: {
        pendingSessionCreate: true,
        mode,
        research_mode: 'deep_research' as ResearchMode,
        chat_mode: mode === 'agent' && !!initialMessage,
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
  } finally {
    isSubmitting.value = false;
  }
};

const handleSubmit = async (options: { thinkingMode?: ThinkingMode, detailLevel?: string } = {}, skillIds: string[] = []) => {
  const thinkingMode = options.thinkingMode || 'auto';
  const detailLevel = options.detailLevel || 'detailed';
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

    try {
      await router.push({
        path: '/chat/new',
        state: {
          pendingSessionCreate: true,
          mode: 'agent',
          research_mode: 'deep_research' as ResearchMode,
          message: submitMessage,
          skills: skillIds,
          thinking_mode: thinkingMode,
          detail_level: detailLevel,
          files: attachments.value.map((file: FileInfo) => ({
            file_id: file.file_id,
            filename: file.filename,
            content_type: file.content_type,
            size: file.size,
            upload_date: file.upload_date
          }))
        }
      });
    } finally {
      isSubmitting.value = false;
    }
  }
};
</script>

<style scoped>
/* ===== AMBIENT GLOW ===== */
.ambient-glow {
  position: fixed;
  top: -20%;
  left: 50%;
  translate: -50% 0;
  width: 680px;
  height: 480px;
  border-radius: 50%;
  background: radial-gradient(ellipse at center,
    color-mix(in srgb, var(--text-brand) 8%, transparent) 0%,
    transparent 70%);
  pointer-events: none;
  z-index: 0;
  filter: blur(40px);
}

/* ===== CENTER DOT GRID ===== */

/* CSS variable for dot color — set per theme using :global so scoping doesn't break it */
:global(:root) {
  --grid-dot-color: rgba(0, 0, 0, 0.45);
}
:global(:root[data-theme="dark"]),
:global(.dark) {
  --grid-dot-color: rgba(255, 255, 255, 0.38);
}

.center-grid {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 100vw;
  height: 100vh;
  pointer-events: none;
  z-index: 0;

  /* Dot pattern using the theme-aware variable */
  background-image: radial-gradient(circle, var(--grid-dot-color) 1px, transparent 1px);
  background-size: 52px 52px;

  /* Fade out toward all edges — bright center only */
  mask-image: radial-gradient(ellipse 55% 55% at 50% 50%, black 0%, transparent 100%);
  -webkit-mask-image: radial-gradient(ellipse 55% 55% at 50% 50%, black 0%, transparent 100%);

  animation: gridBreath 5s ease-in-out infinite;
}

@keyframes gridBreath {
  0%, 100% { opacity: 0.75; }
  50%       { opacity: 1; }
}

/* ===== HEADER ===== */
.home-header {
  padding: 16px 8px 14px;
}

@media (min-width: 640px) {
  .home-header {
    padding: 16px 20px 14px;
  }
}

/* ===== AVATAR ===== */
.avatar-ring {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  padding: 1.5px;
  background: linear-gradient(135deg, var(--border-main), var(--border-dark));
  transition: background 0.2s ease;
}

.avatar-ring:hover {
  background: linear-gradient(135deg, var(--text-brand), color-mix(in srgb, var(--text-brand) 50%, var(--border-dark)));
}

.avatar-inner {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: var(--background-card);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
}

/* ===== CONTENT AREA ===== */
.home-content {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 720px;
  min-width: 390px;
  margin: 0 auto;
  padding-top: 16vh;
  padding-bottom: 100px;
}

@media (max-width: 640px) {
  .home-content {
    max-width: 100%;
    min-width: 0;
    padding-top: 10vh;
  }
}

/* ===== GREETING ===== */
.greeting-section {
  padding: 0 16px;
  margin-bottom: 28px;
  text-align: left;
}

.greeting-eyebrow {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 10px;
  letter-spacing: 0.01em;
}

.greeting-headline {
  font-size: 40px;
  font-weight: 500;
  line-height: 1.12;
  letter-spacing: -0.03em;
  color: var(--text-primary);
}

.greeting-headline-accent {
  font-weight: 500;
  color: var(--text-brand, #6366f1);
}

@media (max-width: 640px) {
  .greeting-headline {
    font-size: 28px;
  }
}

/* ===== CHAT INPUT WRAPPER ===== */
.chat-input-wrapper {
  width: 100%;
  margin-top: 4px;
  padding: 0 8px;
}

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
  gap: 8px;
  margin-top: 20px;
  padding: 0 16px;
}

.feature-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 16px 8px 10px;
  border-radius: 999px;
  font-size: 13.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.18s ease;
  background: var(--background-card);
  border: 1px solid var(--border-main);
  color: var(--text-secondary);
  box-shadow: 0 1px 2px var(--shadow-XS);
}

.feature-btn:hover {
  border-color: var(--border-dark);
  color: var(--text-primary);
  box-shadow: 0 2px 10px var(--shadow-S);
  transform: translateY(-1px);
}

.feature-btn:active {
  transform: translateY(0) scale(0.98);
  box-shadow: 0 1px 2px var(--shadow-XS);
}

/* Icon container */
.feature-btn-icon-wrap {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--fill-tsp-gray-main);
  transition: background 0.18s ease;
}

.feature-btn:hover .feature-btn-icon-wrap {
  background: color-mix(in srgb, var(--text-brand) 12%, transparent);
}

.feature-icon {
  color: var(--icon-secondary);
  transition: color 0.18s ease;
}

.feature-btn:hover .feature-icon {
  color: var(--text-brand);
}

/* Per-button accent colors on hover */
.feature-btn--research:hover .feature-btn-icon-wrap {
  background: color-mix(in srgb, #3b82f6 12%, transparent);
}
.feature-btn--research:hover .feature-icon {
  color: #3b82f6;
}

.feature-btn--design:hover .feature-btn-icon-wrap {
  background: color-mix(in srgb, #a855f7 12%, transparent);
}
.feature-btn--design:hover .feature-icon {
  color: #a855f7;
}

.feature-btn--chat:hover .feature-btn-icon-wrap {
  background: color-mix(in srgb, #22c55e 12%, transparent);
}
.feature-btn--chat:hover .feature-icon {
  color: #22c55e;
}

.feature-btn:focus-visible {
  outline: 2px solid var(--border-btn-primary);
  outline-offset: 2px;
}
</style>
