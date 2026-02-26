<template>
    <div v-if="shouldShow" class="fixed bg-[var(--background-gray-main)] z-[60] transition-all w-full h-full inset-0 flex flex-col">
        <!-- Browser viewport — full desktop via VNC (Chrome chrome, tabs, address bar visible) -->
        <div class="flex-1 min-h-0 relative">
            <VncViewer
                :session-id="sessionId"
                :enabled="shouldShow"
                @connected="onVncConnected"
                @disconnected="onVncDisconnected"
            />
        </div>

        <!-- First-time onboarding tooltip -->
        <Transition name="fade">
            <div
                v-if="showOnboarding"
                class="absolute top-3 left-1/2 -translate-x-1/2 bg-[var(--background-white-main)] rounded-xl shadow-lg border border-[var(--border-main)] px-4 py-3 max-w-sm z-20"
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
                        @click="dismissOnboarding"
                        class="flex-shrink-0 text-[var(--icon-tertiary)] hover:text-[var(--icon-secondary)] transition-colors"
                    >
                        <X class="w-4 h-4" />
                    </button>
                </div>
            </div>
        </Transition>

        <!-- Exit button -->
        <div class="absolute bottom-4 left-1/2 -translate-x-1/2 z-20">
            <button @click="handleExitClick"
                class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring hover:opacity-90 active:opacity-80 bg-[var(--Button-primary-black)] text-[var(--text-onblack)] h-[36px] px-[12px] gap-[6px] text-sm rounded-full border-2 border-[var(--border-dark)] shadow-[0px_8px_32px_0px_rgba(0,0,0,0.32)] exit-takeover-btn">
                <span class="text-sm font-medium">{{ t('Exit Takeover') }}</span>
            </button>
        </div>

        <!-- Exit Dialog -->
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
                    />

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
                        {{ t('Failed to resume agent. Please try again.') }}
                    </p>
                    <div class="flex gap-2 justify-end w-full">
                        <button
                            @click="showExitDialog = false"
                            :disabled="exitLoading"
                            class="rounded-[10px] px-4 py-2 text-sm border border-[var(--border-btn-main)] bg-[var(--button-secondary)] text-[var(--text-primary)] hover:bg-[var(--fill-tsp-white-dark)] cursor-pointer transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {{ t('Cancel') }}
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
    </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { MousePointer, X, Monitor, Loader2 } from 'lucide-vue-next';
import VncViewer from './VncViewer.vue';
import { endTakeover, startTakeover } from '@/api/agent';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter
} from '@/components/ui/dialog';

const route = useRoute();
const { t } = useI18n();

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

// Listen to takeover events
const handleTakeOverEvent = (event: Event) => {
    const customEvent = event as CustomEvent;
    takeOverActive.value = customEvent.detail.active;
    currentSessionId.value = customEvent.detail.sessionId;
};

// VNC event handlers
const onVncConnected = () => {
    // VNC desktop connection established — full browser chrome is visible
};

const onVncDisconnected = (_reason?: string) => {
    // VNC desktop connection lost
};

// Calculate whether to show takeover view
const shouldShow = computed(() => {
    return takeOverActive.value && !!currentSessionId.value;
});

// Add event listener when component is mounted
onMounted(() => {
    window.addEventListener('takeover', handleTakeOverEvent as EventListener);
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
            }
        }
    },
    { immediate: true },
);

// Remove event listener when component is unmounted
onBeforeUnmount(() => {
    window.removeEventListener('takeover', handleTakeOverEvent as EventListener);
});

// Get session ID
const sessionId = computed(() => {
    return currentSessionId.value || route.params.sessionId as string || '';
});

// Handle exit button click - show dialog
const handleExitClick = () => {
    showExitDialog.value = true;
};

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

    // Resume confirmed — close UI and notify parent
    showExitDialog.value = false;
    takeOverActive.value = false;
    currentSessionId.value = '';
    window.dispatchEvent(new CustomEvent('takeover', {
        detail: { sessionId: currentSession, active: false }
    }));

    // Reset dialog state for next time
    userContext.value = '';
    persistLoginState.value = false;
    resumeFailed.value = false;
};

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
