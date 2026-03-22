<template>
  <div class="panel">
    <div class="panel-header">
      <span class="panel-title">Skills</span>
      <ChevronRight :size="16" class="panel-chevron" />
    </div>
    <p class="panel-description">Attach skills to enhance task capabilities.</p>
    <div class="panel-placeholder">
      <Sparkles :size="28" class="placeholder-icon" />
    </div>
    <button class="panel-add-btn" type="button" disabled>
      <Plus :size="14" />
      <span>Add</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight, Sparkles, Plus } from 'lucide-vue-next'
</script>

<style scoped>
.panel {
  border-radius: 12px;
  border: 1px solid var(--border-light);
  padding: 16px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.panel-chevron {
  color: var(--text-tertiary);
}

.panel-description {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0 0 12px;
  line-height: 1.5;
}

.panel-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  margin-bottom: 12px;
}

.placeholder-icon {
  color: var(--border-light);
}

.panel-add-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-tertiary);
  background: transparent;
  border: 1px solid var(--border-light);
  cursor: not-allowed;
  padding: 6px 12px;
  border-radius: 8px;
  opacity: 0.6;
  width: 100%;
  justify-content: center;
}
</style>
