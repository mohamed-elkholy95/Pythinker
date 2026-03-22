<template>
  <div class="task-input-container">
    <textarea
      ref="textareaRef"
      v-model="message"
      class="task-input-textarea"
      placeholder="Tasks are independent for focus. Use project instructions and files for shared context."
      rows="3"
      @keydown.enter.exact.prevent="handleSubmit"
    />
    <div class="task-input-bar">
      <button class="task-input-btn" type="button" aria-label="Attach">
        <Plus :size="18" />
      </button>
      <button
        class="task-input-send"
        type="button"
        :disabled="!message.trim()"
        aria-label="Send"
        @click="handleSubmit"
      >
        <ArrowUp :size="18" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Plus, ArrowUp } from 'lucide-vue-next'

const emit = defineEmits<{
  submit: [message: string]
}>()

const message = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)

function handleSubmit() {
  const text = message.value.trim()
  if (!text) return
  emit('submit', text)
  message.value = ''
}
</script>

<style scoped>
.task-input-container {
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: var(--background-main, #ffffff);
  overflow: hidden;
}

.task-input-textarea {
  width: 100%;
  padding: 14px 16px 8px;
  border: none;
  background: transparent;
  font-size: 14px;
  color: var(--text-primary);
  outline: none;
  resize: none;
  font-family: inherit;
  line-height: 1.5;
}

.task-input-textarea::placeholder {
  color: var(--text-tertiary);
}

.task-input-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
}

.task-input-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid var(--border-light);
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.task-input-btn:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-secondary);
}

.task-input-send {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: var(--text-primary, #1a1a1a);
  color: var(--background-main, #ffffff);
  cursor: pointer;
  transition: all 0.15s ease;
}

.task-input-send:hover:not(:disabled) {
  opacity: 0.85;
}

.task-input-send:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
</style>
