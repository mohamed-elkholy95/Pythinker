<script setup lang="ts">
import { computed } from 'vue'
import type { SkillEventData } from '@/composables/useSkillEvents'

const props = defineProps<{
  phase: string
  activeSkills: SkillEventData[]
  currentTool?: string
  currentToolDetail?: string
  stepProgress?: string
  elapsedTime?: string
}>()

const phaseIcon = computed(() => {
  const icons: Record<string, string> = {
    planning: '\u{1F9E0}',
    executing: '\u{26A1}',
    reflecting: '\u{1F914}',
    verifying: '\u{2705}',
  }
  return icons[props.phase?.toLowerCase()] ?? '\u{2699}'
})

const skillColors: Record<string, string> = {
  research: '#7aa2f7',
  coding: '#9ece6a',
  browser: '#e0af68',
  data_analysis: '#bb9af7',
  file_management: '#7dcfff',
  communication: '#f7768e',
  custom: '#a9b1d6',
}

function getSkillColor(skill: SkillEventData): string {
  const name = skill.skill_name.toLowerCase()
  for (const [key, color] of Object.entries(skillColors)) {
    if (name.includes(key.replace('_', ' ')) || name.includes(key.replace('_', ''))) {
      return color
    }
  }
  return skillColors.custom
}
</script>

<template>
  <div class="activity-bar">
    <div class="activity-segment phase-segment">
      <span class="phase-icon">{{ phaseIcon }}</span>
      <span class="phase-label">{{ phase }}</span>
    </div>

    <div v-if="activeSkills.length" class="activity-segment skills-segment">
      <span
        v-for="skill in activeSkills"
        :key="skill.skill_id"
        class="skill-badge"
        :style="{
          backgroundColor: getSkillColor(skill) + '22',
          color: getSkillColor(skill),
          borderColor: getSkillColor(skill) + '44',
        }"
        :title="skill.reason"
      >
        {{ skill.skill_name }}
      </span>
    </div>

    <div v-if="currentTool" class="activity-segment tool-segment">
      <span class="tool-spinner" />
      <span class="tool-name">{{ currentTool }}</span>
      <span v-if="currentToolDetail" class="tool-detail">{{ currentToolDetail }}</span>
    </div>

    <div v-if="stepProgress" class="activity-segment progress-segment">
      <span class="step-progress">{{ stepProgress }}</span>
      <span v-if="elapsedTime" class="elapsed-time">{{ elapsedTime }}</span>
    </div>
  </div>
</template>

<style scoped>
.activity-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 12px;
  background: var(--bg-secondary, #1e1f2e);
  border-bottom: 1px solid var(--border-color, #2a2b3d);
  font-size: 12px;
  min-height: 32px;
  overflow-x: auto;
}

.activity-segment {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.phase-segment {
  font-weight: 600;
  color: var(--text-primary, #c0caf5);
}

.phase-icon {
  font-size: 14px;
}

.phase-label {
  text-transform: capitalize;
}

.skill-badge {
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid;
  font-size: 11px;
  font-weight: 500;
  transition: all 0.2s ease;
}

.tool-spinner {
  width: 10px;
  height: 10px;
  border: 2px solid var(--text-secondary, #565f89);
  border-top-color: var(--accent, #7aa2f7);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.tool-name {
  color: var(--accent, #7aa2f7);
  font-weight: 500;
}

.tool-detail {
  color: var(--text-secondary, #565f89);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.progress-segment {
  margin-left: auto;
  color: var(--text-secondary, #565f89);
}

.step-progress {
  font-weight: 500;
}

.elapsed-time {
  opacity: 0.7;
}
</style>
