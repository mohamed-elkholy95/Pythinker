<template>
  <div class="interrupted-footer">
    <div class="interrupted-status">
      <AlertTriangle class="interrupted-icon" />
      <span class="status-text">{{ $t('Task was interrupted') }}</span>
    </div>
    <button class="retry-button" type="button" @click="$emit('retry')">
      <RefreshCw class="retry-icon" />
      {{ $t('Retry') }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { AlertTriangle, RefreshCw } from 'lucide-vue-next'

defineEmits<{
  (e: 'retry'): void
}>()
</script>

<style scoped>
.interrupted-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--color-warning-bg, #fffbeb);
  border: 1px solid var(--color-warning-border, #fcd34d);
  border-radius: 8px;
  margin-top: 12px;
}

.interrupted-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.interrupted-icon {
  width: 18px;
  height: 18px;
  color: var(--color-warning, #d97706);
  flex-shrink: 0;
}

.status-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-warning-text, #92400e);
}

.retry-button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-warning-text, #92400e);
  background: transparent;
  border: 1px solid var(--color-warning-border, #fcd34d);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}

.retry-button:hover {
  background: var(--color-warning-hover, #fef3c7);
}

.retry-icon {
  width: 14px;
  height: 14px;
}
</style>
