<template>
    <div v-if="shouldShow" class="fixed bg-[var(--background-gray-main)] z-50 transition-all w-full h-full inset-0">
        <div class="w-full h-full">
            <VNCViewer
                :session-id="sessionId"
                :enabled="shouldShow"
                :view-only="false"
                @connected="onVNCConnected"
                @disconnected="onVNCDisconnected"
                @credentials-required="onVNCCredentialsRequired"
            />
        </div>

        <!-- First-time onboarding tooltip -->
        <Transition name="fade">
            <div
                v-if="showOnboarding"
                class="absolute top-4 left-1/2 -translate-x-1/2 bg-[var(--background-white-main)] rounded-xl shadow-lg border border-[var(--border-main)] px-4 py-3 max-w-sm"
            >
                <div class="flex items-start gap-3">
                    <div class="flex-shrink-0 w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
                        <MousePointer class="w-4 h-4 text-blue-600" />
                    </div>
                    <div class="flex-1 min-w-0">
                        <h4 class="text-sm font-semibold text-[var(--text-primary)]">{{ t('You\'re in control!') }}</h4>
                        <p class="text-xs text-[var(--text-secondary)] mt-0.5">
                            {{ t('You can interact directly with the browser. The agent is paused while you explore.') }}
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
        <div class="absolute bottom-4 left-1/2 -translate-x-1/2">
            <button @click="handleExitClick"
                class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring hover:opacity-90 active:opacity-80 bg-[var(--Button-primary-black)] text-[var(--text-onblack)] h-[36px] px-[12px] gap-[6px] text-sm rounded-full border-2 border-[var(--border-dark)] shadow-[0px_8px_32px_0px_rgba(0,0,0,0.32)]">
                <span class="text-sm font-medium text-[var(--text-onblack)]">{{ t('Exit Takeover') }}</span>
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
                    <DialogTitle>{{ t('Let Pythinker know what you\'ve changed') }}</DialogTitle>
                    <p class="text-sm text-[var(--text-tertiary)] mt-1">
                        {{ t('Summarize your browser actions to help Pythinker work smoothly.') }}
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

                <DialogFooter class="px-6 pb-5">
                    <button
                        @click="showExitDialog = false"
                        class="rounded-[10px] px-4 py-2 text-sm border border-[var(--border-btn-main)] bg-[var(--button-secondary)] text-[var(--text-secondary)] hover:bg-[var(--fill-tsp-white-dark)] cursor-pointer transition-colors"
                    >
                        {{ t('Cancel') }}
                    </button>
                    <button
                        @click="handleExitWithContext"
                        class="rounded-[10px] px-4 py-2 text-sm border border-[var(--border-btn-primary)] bg-[var(--button-primary)] text-[var(--text-white)] hover:bg-[var(--button-primary-hover)] cursor-pointer transition-colors"
                    >
                        {{ t('Send and continue') }}
                    </button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { MousePointer, X, Monitor } from 'lucide-vue-next';
import VNCViewer from './VNCViewer.vue';
import { resumeSession } from '@/api/agent';
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
const onVNCConnected = () => {
    console.log('TakeOver VNC connection successful');
};

const onVNCDisconnected = (reason?: any) => {
    console.log('TakeOver VNC connection disconnected', reason);
};

const onVNCCredentialsRequired = () => {
    console.log('TakeOver VNC credentials required');
};

// Calculate whether to show takeover view
const shouldShow = computed(() => {
    // Check component state first (from takeover event)
    if (takeOverActive.value && currentSessionId.value) {
        return true;
    }

    // Also check route parameters (for direct URL access or page refresh)
    const { params: { sessionId }, query: { vnc } } = route;
    // Only show if both sessionId exists in route AND vnc=1 in query
    return !!sessionId && vnc === '1';
});

// Add event listener when component is mounted
onMounted(() => {
    window.addEventListener('takeover', handleTakeOverEvent as EventListener);
    checkOnboardingStatus();
});



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

// Handle dialog submission - exit with context
const handleExitWithContext = async () => {
    const currentSession = sessionId.value;

    // Close dialog first
    showExitDialog.value = false;

    // Update local state
    takeOverActive.value = false;
    currentSessionId.value = '';
    window.dispatchEvent(new CustomEvent('takeover', {
        detail: { sessionId: currentSession, active: false }
    }));

    // Resume the agent with context
    if (currentSession) {
        try {
            await resumeSession(currentSession, {
                context: userContext.value || undefined,
                persist_login_state: persistLoginState.value || undefined
            });
        } catch (error) {
            console.error('Failed to resume session:', error);
        }
    }

    // Reset dialog state for next time
    userContext.value = '';
    persistLoginState.value = false;
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
