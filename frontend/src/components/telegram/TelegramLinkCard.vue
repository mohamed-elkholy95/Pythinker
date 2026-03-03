<template>
  <div class="telegram-link-card">
    <button
      v-if="showPrimaryButton"
      class="telegram-link-btn"
      type="button"
      :disabled="isGenerating"
      @click="emit('generate')"
    >
      <Loader2 v-if="isGenerating" class="w-4 h-4 animate-spin" />
      <Send v-else class="w-4 h-4" />
      {{ primaryLabel }}
    </button>

    <div v-if="hasDraft" class="telegram-bind-panel">
      <p class="telegram-bind-title">{{ codeTitle }}</p>

      <div class="telegram-bind-row">
        <code>{{ activeCommand }}</code>
        <button type="button" class="telegram-icon-btn" @click="emit('copy')">
          <Check v-if="isCopied" class="w-4 h-4" />
          <Copy v-else class="w-4 h-4" />
        </button>
      </div>

      <div class="telegram-bind-meta">
        <span>
          <Clock3 class="w-3.5 h-3.5" />
          Expires in {{ formatCountdown(countdown) }}
        </span>
        <div class="telegram-bind-actions">
          <button type="button" class="telegram-inline-link" @click="emit('open')">
            {{ openLabel }}
          </button>
          <button v-if="showCancel" type="button" class="telegram-inline-link" @click="emit('cancel')">
            Cancel
          </button>
        </div>
      </div>

      <p class="telegram-pending">{{ pendingLabel }}</p>
    </div>

    <p v-if="feedback" class="telegram-feedback">{{ feedback }}</p>
    <p v-if="error" class="telegram-error">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { Check, Clock3, Copy, Loader2, Send } from 'lucide-vue-next'

interface Props {
  isGenerating: boolean
  hasDraft: boolean
  activeCommand: string
  isCopied: boolean
  countdown: number
  feedback?: string | null
  error?: string | null
  showPrimaryButton?: boolean
  showCancel?: boolean
  primaryLabel?: string
  codeTitle?: string
  pendingLabel?: string
  openLabel?: string
}

withDefaults(defineProps<Props>(), {
  feedback: null,
  error: null,
  showPrimaryButton: true,
  showCancel: false,
  primaryLabel: 'Link Account',
  codeTitle: 'Send this command in Telegram',
  pendingLabel: 'Activation pending. Send the bind command in Telegram to finish linking.',
  openLabel: 'Open Telegram',
})

const emit = defineEmits<{
  generate: []
  copy: []
  open: []
  cancel: []
}>()

const formatCountdown = (seconds: number): string => {
  const safe = Math.max(seconds, 0)
  const minutes = Math.floor(safe / 60)
  const remainder = safe % 60
  return `${minutes}:${remainder.toString().padStart(2, '0')}`
}
</script>

<style scoped>
.telegram-link-card {
  width: min(560px, 100%);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.telegram-link-btn {
  height: 42px;
  border-radius: 12px;
  border: none;
  background: #101114;
  color: #fff;
  padding: 0 18px;
  font-size: 15px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  transition: opacity 0.2s ease;
}

.telegram-link-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.telegram-link-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.telegram-bind-panel {
  border: 1px solid #e3e3e3;
  border-radius: 14px;
  background: #fff;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.telegram-bind-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}

.telegram-bind-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.telegram-bind-row code {
  flex: 1;
  min-width: 0;
  border: 1px solid #dddddd;
  border-radius: 10px;
  padding: 10px;
  background: #fafafa;
  font-size: 12px;
  color: #111827;
  overflow-x: auto;
  white-space: nowrap;
}

.telegram-icon-btn {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #4b5563;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.telegram-bind-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  color: #6b7280;
}

.telegram-bind-meta span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.telegram-bind-actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.telegram-inline-link {
  border: none;
  background: transparent;
  color: #2563eb;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
}

.telegram-pending {
  margin: 0;
  font-size: 12px;
  color: #6b7280;
}

.telegram-feedback,
.telegram-error {
  margin: 0;
  font-size: 12px;
}

.telegram-feedback {
  color: #059669;
}

.telegram-error {
  color: #dc2626;
}

@media (max-width: 720px) {
  .telegram-bind-meta {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
