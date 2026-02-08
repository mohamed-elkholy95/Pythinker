<template>
  <div class="skill-delivery-card">
    <div class="skill-header-bar">
      <div class="header-left">
        <div class="skill-icon-small">
          <Puzzle class="w-4 h-4 text-white" />
        </div>
        <div class="header-text">
          <span class="header-title">{{ skill.name }}</span>
          <span class="header-subtitle">Skill</span>
        </div>
      </div>
      <div class="header-actions">
        <button
          class="download-btn"
          :title="$t('Download')"
          @click="handleDownload"
        >
          <Download class="w-4 h-4" />
        </button>
        <button
          class="add-btn"
          :class="{ 'add-btn-added': added }"
          :disabled="installing"
          @click="handleAdd"
        >
          <Loader2 v-if="installing" class="w-4 h-4 animate-spin" />
          <Check v-else-if="added" class="w-4 h-4" />
          <Plus v-else class="w-4 h-4" />
          <span>{{ added ? $t('Added') : $t('Add to my skills') }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { Puzzle, Download, Check, Plus, Loader2 } from 'lucide-vue-next';
import { downloadSkillPackage, installSkillFromPackage } from '@/api/skills';
import { showSuccessToast, showErrorToast } from '@/utils/toast';
import type { SkillDeliveryContent } from '@/types/message';

const props = defineProps<{
  skill: SkillDeliveryContent;
}>();

const installing = ref(false);
const added = ref(false);

const handleDownload = async () => {
  try {
    await downloadSkillPackage(props.skill.package_id);
  } catch {
    showErrorToast('Failed to download skill package');
  }
};

const handleAdd = async () => {
  if (added.value || installing.value) return;
  installing.value = true;
  try {
    await installSkillFromPackage(props.skill.package_id);
    added.value = true;
    showSuccessToast(`Skill "${props.skill.name}" added successfully`);
  } catch {
    showErrorToast('Failed to install skill');
  } finally {
    installing.value = false;
  }
};
</script>

<style scoped>
@reference "tailwindcss";

.skill-delivery-card {
  width: 100%;
  max-width: 520px;
  min-width: 0;
  border-radius: 10px;
  overflow: hidden;
  background: var(--background-white-main);
  border: 1px solid var(--border-main);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.skill-delivery-card:hover {
  border-color: var(--bolt-elements-borderColorActive);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.skill-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  gap: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.skill-icon-small {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  border-radius: 5px;
  background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
  display: flex;
  align-items: center;
  justify-content: center;
}

.header-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.header-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}

.header-subtitle {
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.3;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.download-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  background: var(--background-white-main);
  color: var(--icon-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.download-btn:hover {
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-dark);
  color: var(--icon-primary);
}

.add-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border-radius: 8px;
  border: none;
  background: var(--text-primary);
  color: var(--background-white-main);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.add-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.add-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.add-btn-added {
  background: var(--function-success);
  cursor: default;
}

.add-btn-added:hover {
  opacity: 1;
}
</style>
