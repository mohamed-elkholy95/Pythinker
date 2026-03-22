<template>
  <DialogRoot v-model:open="isOpen">
    <DialogPortal>
      <DialogOverlay class="modal-overlay" />
      <DialogContent class="modal-content">
        <!-- Header -->
        <div class="modal-header">
          <DialogTitle class="modal-title">Project instructions</DialogTitle>
          <DialogClose class="modal-close" aria-label="Close">
            <X :size="20" />
          </DialogClose>
        </div>

        <!-- Subtitle -->
        <p class="modal-subtitle">
          Applies to all chats in this project. Customize behavior, context, style and more.
        </p>

        <!-- Textarea -->
        <div class="modal-body">
          <textarea
            v-model="localInstructions"
            class="instructions-textarea"
            rows="10"
            placeholder="e.g. &quot;Focus on Python best practices&quot;, &quot;Maintain a professional tone&quot;, or &quot;Always provide sources for important conclusions&quot;."
          />
        </div>

        <!-- Footer -->
        <div class="modal-footer">
          <DialogClose as-child>
            <button class="btn-cancel" type="button">Cancel</button>
          </DialogClose>
          <button
            class="btn-save"
            type="button"
            :disabled="saving"
            @click="handleSave"
          >
            {{ saving ? 'Saving...' : 'Save' }}
          </button>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogClose } from 'reka-ui'
import { X } from 'lucide-vue-next'

const props = defineProps<{
  open: boolean
  instructions: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  save: [instructions: string]
}>()

const isOpen = computed({
  get: () => props.open,
  set: (val: boolean) => emit('update:open', val),
})

const localInstructions = ref(props.instructions)
const saving = ref(false)

watch(() => props.open, (val) => {
  if (val) {
    localInstructions.value = props.instructions
    saving.value = false
  }
})

function handleSave() {
  saving.value = true
  emit('save', localInstructions.value)
}
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
  width: min(560px, calc(100vw - 32px));
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
  justify-content: space-between;
  margin-bottom: 8px;
}

.modal-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.01em;
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
}

.modal-close:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

.modal-subtitle {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0 0 20px;
  line-height: 1.5;
}

.modal-body {
  margin-bottom: 20px;
}

.instructions-textarea {
  width: 100%;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: var(--fill-tsp-gray-main, #f5f5f5);
  font-size: 14px;
  color: var(--text-primary);
  outline: none;
  resize: vertical;
  min-height: 200px;
  font-family: inherit;
  line-height: 1.5;
  transition: all 0.15s ease;
}

.instructions-textarea:focus {
  border-color: var(--border-main);
  background: var(--background-main, #ffffff);
}

.instructions-textarea::placeholder {
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

.btn-save:hover:not(:disabled) {
  opacity: 0.85;
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
