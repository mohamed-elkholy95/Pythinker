<template>
    <!-- Backdrop + VNC only (no overlapping chrome - noVNC canvas steals hits in same subtree). -->
    <div
        v-if="shouldShow"
        class="takeover-root fixed inset-0 z-[900] box-border overflow-hidden bg-[var(--background-gray-main)] m-0 p-0"
    >
        <div class="absolute inset-0">
            <VncViewer
                :session-id="sessionId"
                :enabled="shouldShow"
                @connected="onVncConnected"
                @disconnected="onVncDisconnected"
            />
        </div>
    </div>

    <!-- Small fixed controls only — do NOT use a full-viewport Teleport layer (it can composite above VNC and show black). -->
    <Teleport to="body">
        <Transition name="fade">
            <div
                v-if="shouldShow && showOnboarding"
                class="takeover-chrome-onboarding fixed top-4 left-1/2 z-[990] max-w-sm -translate-x-1/2 rounded-xl border border-[var(--border-main)] bg-[var(--background-white-main)] px-4 py-3 shadow-lg"
            >
                <div class="flex items-start gap-3">
                    <div class="flex-shrink-0 w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
                        <MousePointer class="w-4 h-4 text-blue-600" />
                    </div>
                    <div class="flex-1 min-w-0">
                        <h4 class="text-sm font-semibold text-[var(--text-primary)]">{{ t('You\'re in control!') }}</h4>
                        <p class="text-xs text-[var(--text-secondary)] mt-0.5">
                            {{ t('You have full browser control with tabs! The agent is paused while you\'re in control.') }}
                        </p>
                    </div>
                    <button
                        type="button"
                        @click="dismissOnboarding"
                        class="flex-shrink-0 text-[var(--icon-tertiary)] hover:text-[var(--icon-secondary)] transition-colors"
                    >
                        <X class="w-4 h-4" />
                    </button>
                </div>
            </div>
        </Transition>
    </Teleport>
    <Teleport to="body">
        <div v-if="shouldShow" class="fixed bottom-6 left-1/2 z-[990] -translate-x-1/2">
            <button
                type="button"
                @click="handleExitClick"
                class="exit-takeover-btn inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-full border-2 border-[var(--border-dark)] bg-[var(--Button-primary-black)] px-5 text-sm font-medium whitespace-nowrap text-[var(--text-onblack)] shadow-[0px_8px_32px_0px_rgba(0,0,0,0.32)] transition-colors hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)] active:opacity-80"
            >
                {{ t('Exit Takeover') }}
            </button>
        </div>
    </Teleport>

    <!-- Exit dialog: sibling of takeover layers; portals to body at z-[1000]. -->
    <Dialog v-model:open="showExitDialog">
            <DialogContent
                :hide-close-button="false"
                title="Exit Browser Takeover"
                description="Provide context about your browser changes"
                class="w-[440px] max-w-[95vw]"
            >
                <DialogHeader>
                    <DialogTitle>{{ t('Let Pythinker know what you changed') }}</DialogTitle>
                    <p class="text-sm text-[var(--text-tertiary)] mt-1">
                        {{ t('Optionally describe your browser actions so the agent can adapt.') }}
                    </p>
                </DialogHeader>

                <div class="px-6 py-4 space-y-4">
                    <!-- Context textarea -->
                    <textarea
                        v-model="userContext"
                        :placeholder="t('This message will be sent to Pythinker...')"
                        class="w-full h-24 p-3 text-sm border border-[var(--border-main)] rounded-lg resize-none bg-[var(--background-white-main)] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none focus:ring-2 focus:ring-[var(--border-focus)] focus:border-transparent"
                    ></textarea>

                    <!-- Persist login state toggle -->
                    <div class="flex items-center justify-between p-3 bg-[var(--fill-tsp-gray-light)] rounded-lg">
                        <div class="flex items-center gap-3">
                            <div class="flex-shrink-0 w-9 h-9 rounded-lg bg-[var(--fill-tsp-gray-main)] flex items-center justify-center">
                                <Monitor class="w-5 h-5 text-[var(--icon-secondary)]" />
                            </div>
                            <div>
                                <p class="text-sm font-medium text-[var(--text-primary)]">{{ t('Persist login state') }}</p>
                                <p class="text-xs text-[var(--text-tertiary)]">{{ t('Keep browser sessions across tasks') }}</p>
                            </div>
                        </div>
                        <button
                            @click="persistLoginState = !persistLoginState"
                            :class="[
                                'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-white/75',
                                persistLoginState ? 'bg-[var(--function-success)]' : 'bg-[var(--fill-tsp-gray-dark)]'
                            ]"
                        >
                            <span
                                :class="[
                                    'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out',
                                    persistLoginState ? 'translate-x-5' : 'translate-x-0'
                                ]"
                            />
                        </button>
                    </div>
                </div>

                <DialogFooter class="px-6 pb-5 flex-col gap-2">
                    <p v-if="resumeFailed" class="text-xs text-[var(--function-error)] w-full text-center">
                        {{ t('Could not resume the agent. The session may have already ended.') }}
                    </p>
                    <div class="flex gap-2 justify-end w-full">
                        <button
                            v-if="!resumeFailed"
                            @click="showExitDialog = false"
                            :disabled="exitLoading"
                            class="rounded-[10px] px-4 py-2 text-sm border border-[var(--border-btn-main)] bg-[var(--button-secondary)] text-[var(--text-primary)] hover:bg-[var(--fill-tsp-white-dark)] cursor-pointer transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {{ t('Cancel') }}
                        </button>
                        <button
                            v-if="resumeFailed"
                            @click="forceCloseTakeover"
                            class="rounded-[10px] px-4 py-2 text-sm border border-[var(--border-btn-main)] bg-[var(--button-secondary)] text-[var(--text-primary)] hover:bg-[var(--fill-tsp-white-dark)] cursor-pointer transition-colors"
                        >
                            {{ t('Close anyway') }}
                        </button>
                        <button
                            @click="handleExitWithContext"
                            :disabled="exitLoading"
                            class="rounded-[10px] px-4 py-2 text-sm border border-[var(--border-btn-primary)] bg-[var(--button-primary)] text-[var(--text-onblack)] hover:bg-[var(--button-primary-hover)] cursor-pointer transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                            <Loader2 v-if="exitLoading" :size="14" class="animate-spin" />
                            {{ resumeFailed ? t('Retry') : t('Send and continue') }}
                        </button>
                    </div>
                </DialogFooter>
            </DialogContent>
    </Dialog>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { MousePointer, X, Monitor, Loader2 } from 'lucide-vue-next';
import VncViewer from './VncViewer.vue';
import { endTakeover, startTakeover } from '@/api/agent';
import { isTakeoverOverlayActive } from '@/composables/takeoverOverlayState';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter
} from '@/components/ui/dialog';

const route = useRoute();
const { t } = useI18n();

function sessionIdFromRoute(): string {
    const p = route.params.sessionId;
    if (Array.isArray(p)) return p[0] ?? '';
    return typeof p === 'string' ? p : '';
}

// Takeover state
const takeOverActive = ref(false);
const currentSessionId = ref('');

// Exit dialog state
const showExitDialog = ref(false);
const userContext = ref('');
const persistLoginState = ref(false);

// Onboarding tooltip state
const ONBOARDING_DISMISSED_KEY = 'pythinker_takeover_onboarding_dismissed';
const showOnboarding = ref(false);

const checkOnboardingStatus = () => {
    const dismissed = localStorage.getItem(ONBOARDING_DISMISSED_KEY);
    showOnboarding.value = !dismissed;
};

const dismissOnboarding = () => {
    showOnboarding.value = false;
    localStorage.setItem(ONBOARDING_DISMISSED_KEY, 'true');
};

// Listen to takeover events (register in setup, not onMounted — avoids missing early dispatches)
const handleTakeOverEvent = (event: Event) => {
    const customEvent = event as CustomEvent<{ active?: boolean; sessionId?: string }>;
    const active = Boolean(customEvent.detail?.active);
    const fromDetail = typeof customEvent.detail?.sessionId === 'string' ? customEvent.detail.sessionId : '';
    const fromRoute = sessionIdFromRoute();
    takeOverActive.value = active;
    if (active) {
        currentSessionId.value = fromDetail || fromRoute;
    } else {
        currentSessionId.value = '';
    }
    isTakeoverOverlayActive.value = active;
};

if (typeof window !== 'undefined') {
    window.addEventListener('takeover', handleTakeOverEvent as EventListener);
}

// VNC event handlers
const onVncConnected = () => {
    // VNC desktop connection established — full browser chrome is visible
};

const onVncDisconnected = (_reason?: string) => {
    // VNC desktop connection lost
};

// Show overlay when takeover is active and we can resolve a session id (detail or route)
const shouldShow = computed(() => {
    if (!takeOverActive.value) return false;
    const sid = currentSessionId.value || sessionIdFromRoute();
    return sid.length > 0;
});

onMounted(() => {
    checkOnboardingStatus();
});

// Watch for ?preview=1 on every navigation (handles both initial load and SPA client-side navigation).
// TakeOverView is mounted globally in MainLayout and never unmounts, so onMounted only fires once;
// a watch is required to react to subsequent Vue Router navigations.
watch(
    () => ({ sessionId: route.params.sessionId, preview: route.query.preview }),
    async ({ sessionId: routeSessionId, preview }) => {
        if (routeSessionId && preview === '1' && !takeOverActive.value) {
            const sid = routeSessionId as string;
            const status = await startTakeover(sid, 'manual').catch(() => null);
            if (status?.takeover_state === 'takeover_active') {
                takeOverActive.value = true;
                currentSessionId.value = sid;
                isTakeoverOverlayActive.value = true;
            }
        }
    },
    { immediate: true },
);

onBeforeUnmount(() => {
    if (typeof window !== 'undefined') {
        window.removeEventListener('takeover', handleTakeOverEvent as EventListener);
    }
});

// Get session ID
const sessionId = computed(() => {
    return currentSessionId.value || sessionIdFromRoute();
});

// Handle exit button click - show dialog (nextTick avoids rare reka-ui open races)
const handleExitClick = async () => {
    await nextTick();
    showExitDialog.value = true;
};

watch(shouldShow, (visible) => {
    if (!visible) {
        showExitDialog.value = false;
    }
});

// Track exit-in-progress to show loading state on the submit button
const exitLoading = ref(false);
// Track resume failure so UI can offer a retry
const resumeFailed = ref(false);

// Handle dialog submission - exit and optionally resume agent
const handleExitWithContext = async () => {
    const currentSession = sessionId.value;
    if (!currentSession || exitLoading.value) return;

    const contextText = userContext.value || '';
    const persistLogin = persistLoginState.value;

    exitLoading.value = true;
    resumeFailed.value = false;

    try {
        // End takeover via API — must succeed before closing UI
        const status = await endTakeover(currentSession, {
            context: contextText.trim() || undefined,
            persist_login_state: persistLogin || undefined,
            resume_agent: true,
        });

        if (status.takeover_state !== 'idle') {
            // Resume failed — backend stayed in takeover_active; surface retry
            resumeFailed.value = true;
            return;
        }
    } catch {
        // Network/server error — surface retry rather than silently closing
        resumeFailed.value = true;
        return;
    } finally {
        exitLoading.value = false;
    }

    // Resume confirmed — close UI
    closeTakeoverUI(currentSession);
};

// Shared cleanup: close takeover UI, notify parent, reset dialog state
const closeTakeoverUI = (sid?: string) => {
    const currentSession = sid || sessionId.value;
    showExitDialog.value = false;
    takeOverActive.value = false;
    currentSessionId.value = '';
    isTakeoverOverlayActive.value = false;
    window.dispatchEvent(new CustomEvent('takeover', {
        detail: { sessionId: currentSession, active: false }
    }));
    userContext.value = '';
    persistLoginState.value = false;
    resumeFailed.value = false;
};

// Force-close takeover UI without resuming agent (session already ended)
const forceCloseTakeover = () => closeTakeoverUI();

// Expose sessionId for parent component to use
defineExpose({
    sessionId
});
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
    transition: opacity 0.3s ease, transform 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
    opacity: 0;
    transform: translate(-50%, -10px);
}
</style>
