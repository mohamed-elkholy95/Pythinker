<template>
  <div class="panel">
    <div class="panel-header">
      <div class="panel-header-left">
        <span class="panel-title">Skills</span>
        <ChevronRight :size="16" class="panel-chevron" />
      </div>
    </div>
    <p class="panel-description">Add skills to enhance Pythinker's know-how.</p>
    <div v-if="enabledSkills.length > 0" class="panel-items">
      <div v-for="skill in enabledSkills.slice(0, 3)" :key="skill.id" class="panel-item">
        <Sparkles :size="12" class="panel-item-icon" />
        <span class="panel-item-name">{{ skill.name }}</span>
      </div>
      <span v-if="enabledSkills.length > 3" class="panel-more">+{{ enabledSkills.length - 3 }} more</span>
    </div>
    <button class="panel-add-btn" type="button" @click="openSettingsDialog('skills')">
      <Plus :size="14" />
      <span>Add</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight, Sparkles, Plus } from 'lucide-vue-next'
import { useSkills } from '@/composables/useSkills'
import { useSettingsDialog } from '@/composables/useSettingsDialog'

const { enabledSkills } = useSkills()
const { openSettingsDialog } = useSettingsDialog()
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

.panel-header-left {
  display: flex;
  align-items: center;
  gap: 4px;
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

.panel-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.panel-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.panel-item-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.panel-item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-more {
  font-size: 12px;
  color: var(--text-tertiary);
}

.panel-add-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  background: transparent;
  border: 1px solid var(--border-light);
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 8px;
  transition: all 0.15s ease;
}

.panel-add-btn:hover {
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-main);
}
</style>
