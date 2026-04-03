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
              <img src="/logo.png" alt="Pythinker" width="20" height="20" class="w-5 h-5 rounded" style="aspect-ratio: 1 / 1;" />
            </button>
            <!-- Desktop branding (visible when sidebar is collapsed) -->
            <PythinkerLogoTextIcon
              v-if="!isLeftPanelShow"
              :width="120"
              :height="28"
              class="hidden sm:block flex-shrink-0 -ml-2"
            />
          </div>
          <!-- Center: Model name as header title (Pythinker-style) -->
          <button
            v-if="activeModelName"
            type="button"
            class="header-model-title"
            data-testid="home-header-model-title"
            :title="activeModelName"
            @click="openSettingsDialog('model')"
          >
            <span class="header-model-title-label">{{ activeModelName }}</span>
            <ChevronDown class="header-model-title-icon" />
          </button>
          <div class="flex items-center gap-2 ml-auto">
            <div class="relative flex items-center"
              @mouseenter="handleUserMenuEnter" @mouseleave="handleUserMenuLeave">
              <button
                class="avatar-ring cursor-pointer flex-shrink-0"
                type="button"
                :aria-expanded="showUserMenu"
                aria-haspopup="menu"
                aria-label="Account menu"
              >
                <div class="avatar-inner">
                  {{ avatarLetter }}
                </div>
              </button>
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
import { ref, onMounted, computed, onUnmounted, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import ChatBox from '../components/ChatBox.vue';
import type { AgentMode, ThinkingMode, ResearchMode } from '../api/agent';
import { consumeComposerDraft } from '@/utils/composerDraft';
import type { FileInfo } from '@/api/file';
import SearchIcon from '../components/icons/SearchIcon.vue';
import PaletteIcon from '../components/icons/PaletteIcon.vue';
import ChatBubbleIcon from '../components/icons/ChatBubbleIcon.vue';
import { Tag } from 'lucide-vue-next';
import { ChevronDown } from 'lucide-vue-next';
import { useFilePanel } from '../composables/useFilePanel';
import { useAuth } from '../composables/useAuth';
import { useLeftPanel } from '../composables/useLeftPanel';
import { useSettingsDialog } from '../composables/useSettingsDialog';
import UserMenu from '../components/UserMenu.vue';
import PythinkerLogoTextIcon from '../components/icons/PythinkerLogoTextIcon.vue';
import ConnectorsDialog from '@/components/connectors/ConnectorsDialog.vue';
import { getServerConfig, getSettings } from '../api/settings';
import { resolveInitialHeaderModelName } from '@/utils/chatHeaderModel';
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
const { toggleLeftPanel, isLeftPanelShow } = useLeftPanel();
const { openSettingsDialog } = useSettingsDialog();
const activeModelName = ref('');

// Visible feature buttons
const visibleFeatures: Feature[] = [
  {
    id: 'research',
    label: 'Research',
    icon: SearchIcon,
    mode: 'agent',
    prompt: 'create a comprehensive research report about: '
  },
  {
    id: 'deals',
    label: 'Deal Finder',
    icon: Tag,
    mode: 'agent',
    prompt: 'Act as a professional deal finder. Search all major stores, compare prices, and find the best deals, coupons, and promo codes for: '
  },
  {
    id: 'design',
    label: 'Design',
    icon: PaletteIcon,
    mode: 'agent',
    prompt: 'Create a design for: '
  },
  {
    id: 'chat',
    label: 'Chat Mode',
    icon: ChatBubbleIcon,
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
const userMenuTimeout = ref<ReturnType<typeof setTimeout> | null>(null);
let chatPreloadPromise: Promise<unknown> | null = null;
let chatPreloadIdleHandle: number | null = null;
let chatPreloadTimeoutHandle: ReturnType<typeof setTimeout> | null = null;

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

  if (typeof window !== 'undefined') {
    chatPreloadTimeoutHandle = globalThis.setTimeout(runPreload, 300);
  }
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
  userMenuTimeout.value = globalThis.setTimeout(() => {
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

onMounted(async () => {
  hideFilePanel();
  scheduleChatRoutePreload();
  // Listen for message insert event from settings dialog
  window.addEventListener('pythinker:insert-chat-message', handleInsertMessage as EventListener);

  // Fetch model name for header pill
  const [serverConfigResult, userSettingsResult] = await Promise.allSettled([
    getServerConfig(),
    getSettings(),
  ]);
  activeModelName.value = resolveInitialHeaderModelName(
    serverConfigResult.status === 'fulfilled' ? serverConfigResult.value.model_name : '',
    userSettingsResult.status === 'fulfilled' ? userSettingsResult.value.model_name : '',
  );
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
    // Set the prompt in the message input and focus textarea for immediate typing
    message.value = feature.prompt;
    await nextTick();
    const textarea = document.getElementById('chatbox-message') as HTMLTextAreaElement | null;
    if (textarea) {
      textarea.focus();
      // Place cursor at end of prompt so user can type product name immediately
      textarea.setSelectionRange(feature.prompt.length, feature.prompt.length);
    }
  }
};

// Create session with specific mode
const createSessionWithMode = async (mode: AgentMode, seedMessage?: string) => {
  if (isSubmitting.value) return;
  isSubmitting.value = true;
  const draft = consumeComposerDraft({
    message: message.value,
    attachments: attachments.value,
    setMessage: (value: string) => { message.value = value; },
    setAttachments: (value: FileInfo[]) => { attachments.value = value; },
  });

  try {
    await router.push({
      path: '/chat/new',
      state: {
        pendingSessionCreate: true,
        mode,
        research_mode: 'deep_research' as ResearchMode,
        chat_mode: mode === 'agent' && !!seedMessage,
        message: seedMessage ?? '',
        skills: [],
        files: draft.attachments.map((file: FileInfo) => ({
          file_id: file.file_id,
          filename: file.filename,
          content_type: file.content_type,
          size: file.size,
          upload_date: file.upload_date
        }))
      }
    });
  } catch (error) {
    draft.restore();
    throw error;
  } finally {
    isSubmitting.value = false;
  }
};

const handleSubmit = async (options: { thinkingMode?: ThinkingMode } = {}, skillIds: string[] = []) => {
  const thinkingMode = options.thinkingMode || 'auto';
  // Merge pending skill from "Build with Pythinker" button if present
  if (pendingSkillId.value && !skillIds.includes(pendingSkillId.value)) {
    skillIds = [...skillIds, pendingSkillId.value];
  }
  pendingSkillId.value = null;

  const trimmedMessage = message.value.trim();
  if ((trimmedMessage || skillIds.includes('skill-creator')) && !isSubmitting.value) {
    isSubmitting.value = true;
    const draft = consumeComposerDraft({
      message: message.value,
      attachments: attachments.value,
      setMessage: (value: string) => { message.value = value; },
      setAttachments: (value: FileInfo[]) => { attachments.value = value; },
    });
    let submitMessage = draft.message;
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
          files: draft.attachments.map((file: FileInfo) => ({
            file_id: file.file_id,
            filename: file.filename,
            content_type: file.content_type,
            size: file.size,
            upload_date: file.upload_date
          }))
        }
      });
    } catch (error) {
      draft.restore();
      throw error;
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

/* Pythinker-style centered model title */
.header-model-title {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 32px;
  padding: 0 4px;
  border-radius: 6px;
  background: transparent;
  color: var(--text-primary);
  transition: opacity 0.15s ease;
  flex-shrink: 0;
  cursor: pointer;
  border: none;
}

.header-model-title:hover {
  opacity: 0.7;
}

.header-model-title-label {
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
  letter-spacing: -0.01em;
}

@media (max-width: 639px) {
  .header-model-title-label {
    font-size: 14px;
  }
}

.header-model-title-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: var(--text-tertiary);
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
  --icon-secondary: var(--text-brand);
}

/* Per-button accent colors on hover */
.feature-btn--research:hover .feature-btn-icon-wrap {
  background: color-mix(in srgb, #3b82f6 12%, transparent);
}
.feature-btn--research:hover .feature-icon {
  color: #3b82f6;
  --icon-secondary: #3b82f6;
}

.feature-btn--deals:hover .feature-btn-icon-wrap {
  background: color-mix(in srgb, #f59e0b 12%, transparent);
}
.feature-btn--deals:hover .feature-icon {
  color: #f59e0b;
  --icon-secondary: #f59e0b;
}

.feature-btn--design:hover .feature-btn-icon-wrap {
  background: color-mix(in srgb, #a855f7 12%, transparent);
}
.feature-btn--design:hover .feature-icon {
  color: #a855f7;
  --icon-secondary: #a855f7;
}

.feature-btn--chat:hover .feature-btn-icon-wrap {
  background: color-mix(in srgb, #22c55e 12%, transparent);
}
.feature-btn--chat:hover .feature-icon {
  color: #22c55e;
  --icon-secondary: #22c55e;
}

.feature-btn:focus-visible {
  outline: 2px solid var(--border-btn-primary);
  outline-offset: 2px;
}

/* ── Model pill ── */
.home-model-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 220px;
  height: 40px;
  padding: 0 16px;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--border-main) 85%, transparent);
  background: color-mix(in srgb, var(--background-secondary) 92%, var(--background-white-main));
  color: var(--text-primary);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--text-white) 8%, transparent);
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
  cursor: pointer;
}

.home-model-pill:hover {
  background: color-mix(in srgb, var(--background-secondary) 84%, var(--background-white-main));
  border-color: var(--border-hover);
  transform: translateY(-1px);
}

.home-model-pill:focus-visible {
  outline: none;
  border-color: var(--border-hover);
}

.home-model-pill-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.home-model-pill-icon {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
  color: var(--icon-secondary);
}
</style>
