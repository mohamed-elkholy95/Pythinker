<template>
  <DialogRoot v-model:open="isOpen">
    <DialogPortal>
      <DialogOverlay class="modal-overlay" />
      <DialogContent class="modal-content">
        <!-- Header -->
        <div class="modal-header">
          <button class="modal-back" type="button" @click="isOpen = false" aria-label="Back">
            <ArrowLeft :size="20" />
          </button>
          <DialogTitle class="modal-title">Power your project with connectors</DialogTitle>
          <DialogClose class="modal-close" aria-label="Close">
            <X :size="20" />
          </DialogClose>
        </div>

        <!-- Description -->
        <p class="modal-description">
          Connectors give your project access to external services and data sources. Connect APIs, databases, and more.
        </p>

        <!-- Coming soon -->
        <div class="modal-body">
          <div class="coming-soon">
            <Plug :size="28" class="coming-soon-icon" />
            <span class="coming-soon-text">Coming soon</span>
          </div>
        </div>

        <!-- Footer -->
        <div class="modal-footer">
          <DialogClose as-child>
            <button class="btn-cancel" type="button">Cancel</button>
          </DialogClose>
          <button class="btn-save" type="button" disabled>
            Save
          </button>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogClose } from 'reka-ui'
import { X, ArrowLeft, Plug } from 'lucide-vue-next'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const isOpen = computed({
  get: () => props.open,
  set: (val: boolean) => emit('update:open', val),
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 100;
  animation: fadeIn 0.15s ease;
}

.modal-content {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 101;
  width: min(520px, calc(100vw - 32px));
  max-height: calc(100dvh - 64px);
  overflow-y: auto;
  background: var(--background-main, #ffffff);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15), 0 0 0 1px rgba(0, 0, 0, 0.05);
  padding: 24px;
  animation: modalSlideIn 0.2s ease;
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.modal-back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.modal-back:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

.modal-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  flex: 1;
}

.modal-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.modal-close:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

.modal-description {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0 0 20px;
  line-height: 1.5;
}

.modal-body {
  margin-bottom: 20px;
}

.coming-soon {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 16px;
  border-radius: 12px;
  border: 2px dashed var(--border-light);
}

.coming-soon-icon {
  color: var(--border-light);
}

.coming-soon-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-tertiary);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.btn-cancel {
  height: 40px;
  padding: 0 20px;
  border-radius: 10px;
  border: 1px solid var(--border-main);
  background: var(--background-main, #ffffff);
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-cancel:hover {
  background: var(--fill-tsp-gray-main);
}

.btn-save {
  height: 40px;
  padding: 0 24px;
  border-radius: 10px;
  border: none;
  background: var(--text-primary, #1a1a1a);
  color: var(--background-main, #ffffff);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-save:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes modalSlideIn {
  from {
    opacity: 0;
    transform: translate(-50%, -48%);
  }
  to {
    opacity: 1;
    transform: translate(-50%, -50%);
  }
}
</style>
