<template>
  <div role="region" aria-label="Notifications (F8)" tabindex="-1" style="">
    <span
      aria-hidden="true"
      tabindex="-1"
      style="position: fixed; border: 0px; width: 1px; height: 1px; padding: 0px; margin: -1px; overflow: hidden; clip: rect(0px, 0px, 0px, 0px); white-space: nowrap; overflow-wrap: normal;"
    ></span>
    <ol
      tabindex="-1"
      class="fixed top-[28px] left-1/2 -translate-x-1/2 z-[1050] flex max-h-screen flex-col-reverse p-4 max-w-[90%] gap-2.5"
    >
      <li
        v-for="toast in toasts"
        :key="toast.id"
        role="status"
        aria-live="off"
        aria-atomic="true"
        tabindex="0"
        data-state="open"
        data-swipe-direction="right"
        class="w-max max-w-full flex-shrink-0 bg-[var(--background-white-main)] rounded-xl shadow-[0px_4px_11px_0px_var(--shadow-M)] border border-[var(--border-white)] backdrop-blur-3xl data-[swipe=cancel]:translate-y-0 data-[swipe=end]:translate-y-[var(--radix-toast-swipe-end-x)] data-[swipe=move]:translate-y-[var(--radix-toast-swipe-move-x)] data-[swipe=move]:transition-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[swipe=end]:animate-out data-[state=closed]:fade-out-80 data-[state=closed]:slide-out-to-top-full data-[state=open]:slide-in-from-top-full"
        :class="toast.title ? 'px-5 py-3.5' : 'px-4 py-2'"
        data-radix-collection-item=""
        style="user-select: none; touch-action: none;"
      >
        <!-- Rich layout (title + subtitle) for progress toasts -->
        <div v-if="toast.title" class="flex items-start gap-3">
          <div class="flex-shrink-0 mt-0.5">
            <div v-if="toast.type === 'progress'" class="text-[var(--status-running)]">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
            </div>
            <div v-else-if="toast.type === 'error'"><ErrorIcon /></div>
            <div v-else-if="toast.type === 'success'"><SuccessIcon /></div>
            <div v-else><InfoIcon /></div>
          </div>
          <div class="flex flex-col gap-0.5 min-w-0">
            <span class="text-[13px] font-semibold text-[var(--text-primary)] leading-tight">{{ toast.title }}</span>
            <span class="text-[12px] text-[var(--text-secondary)] leading-snug">{{ toast.message }}</span>
          </div>
        </div>

        <!-- Simple layout (single line) for standard toasts -->
        <div v-else class="flex items-center gap-2.5">
          <div>
            <div v-if="toast.type === 'error'" class="me-2.5 inline-flex relative top-1">
              <ErrorIcon />
            </div>
            <div v-else-if="toast.type === 'info'" class="me-2.5 inline-flex relative top-1">
              <InfoIcon />
            </div>
            <div v-else-if="toast.type === 'success'" class="me-2.5 inline-flex relative top-1">
              <SuccessIcon />
            </div>
            {{ toast.message }}
          </div>
        </div>
      </li>
    </ol>
    <span
      aria-hidden="true"
      tabindex="-1"
      style="position: fixed; border: 0px; width: 1px; height: 1px; padding: 0px; margin: -1px; overflow: hidden; clip: rect(0px, 0px, 0px, 0px); white-space: nowrap; overflow-wrap: normal;"
    ></span>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import ErrorIcon from '@/components/icons/ErrorIcon.vue';
import InfoIcon from '@/components/icons/InfoIcon.vue';
import SuccessIcon from '@/components/icons/SuccessIcon.vue';

interface Toast {
  id: number;
  message: string;
  title?: string;
  type: 'error' | 'info' | 'success' | 'progress';
  duration?: number;
}

const toasts = ref<Toast[]>([]);
let toastCounter = 0;

// Add toast
const addToast = (message: string, type: 'error' | 'info' | 'success' | 'progress' = 'info', duration: number = 3000, title?: string) => {
  const id = toastCounter++;
  const toast: Toast = { id, message, title, type, duration };
  toasts.value.push(toast);

  // Set automatic removal
  if (duration > 0) {
    setTimeout(() => {
      removeToast(id);
    }, duration);
  }

  return id;
};

// Remove toast
const removeToast = (id: number) => {
  const index = toasts.value.findIndex(toast => toast.id === id);
  if (index !== -1) {
    toasts.value.splice(index, 1);
  }
};

// Create custom event bus
const handleToastEvent = (event: CustomEvent) => {
  const { message, type, duration, title } = event.detail;
  addToast(message, type, duration, title);
};

// Listen for custom events
onMounted(() => {
  window.addEventListener('toast', handleToastEvent as EventListener);
});

onUnmounted(() => {
  window.removeEventListener('toast', handleToastEvent as EventListener);
});

// Expose methods for external use
defineExpose({
  addToast,
  removeToast
});
</script>
