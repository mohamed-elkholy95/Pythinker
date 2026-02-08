<template>
  <Popover v-model:open="isOpen">
    <PopoverTrigger as-child>
      <button class="skill-picker-btn" :class="{ 'has-selected': selectedCount > 0 }">
        <Puzzle :size="16" />
        <span v-if="selectedCount > 0" class="skill-picker-badge">{{ selectedCount }}</span>
      </button>
    </PopoverTrigger>
    <PopoverContent side="bottom" :side-offset="8" align="start" class="skill-picker-popover">
      <div class="skill-picker-content">
        <!-- Search -->
        <div class="skill-picker-search">
          <Search :size="14" class="skill-picker-search-icon" />
          <input
            ref="searchInputRef"
            v-model="searchQuery"
            type="text"
            :placeholder="t('Search skills...')"
            class="skill-picker-search-input"
          />
        </div>

        <!-- Skill list -->
        <div class="skill-picker-list">
          <div v-if="loading" class="skill-picker-empty">
            {{ t('Loading skills...') }}
          </div>
          <div v-else-if="filteredSkills.length === 0" class="skill-picker-empty">
            {{ searchQuery ? t('No skills match your search') : t('No skills available') }}
          </div>
          <button
            v-for="skill in filteredSkills"
            :key="skill.id"
            class="skill-picker-item"
            @click="handleToggle(skill.id)"
          >
            <Puzzle :size="14" class="skill-picker-item-icon" />
            <div class="skill-picker-item-info">
              <div class="skill-picker-item-header">
                <span class="skill-picker-item-name">{{ skill.name }}</span>
                <span class="skill-picker-item-source" :class="`source-${skill.source}`">
                  {{ sourceLabel(skill.source) }}
                </span>
              </div>
              <span class="skill-picker-item-desc">{{ skill.description }}</span>
            </div>
            <Check v-if="isSelected(skill.id)" :size="16" class="skill-picker-item-check" />
          </button>
        </div>

        <!-- Footer -->
        <div class="skill-picker-footer">
          <button class="skill-picker-manage" @click="handleManageSkills">
            <ExternalLink :size="12" />
            {{ t('Manage Skills') }}
          </button>
        </div>
      </div>
    </PopoverContent>
  </Popover>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { Puzzle, Search, Check, ExternalLink } from 'lucide-vue-next';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useSkills } from '@/composables/useSkills';
import { useSettingsDialog } from '@/composables/useSettingsDialog';
import { showInfoToast } from '@/utils/toast';
import { MAX_ENABLED_SKILLS } from '@/api/skills';

const { t } = useI18n();
const {
  availableSkills,
  selectedSkillIds,
  canSelectMore,
  toggleSkillSelection,
  loadAvailableSkills,
  loading,
} = useSkills();
const { openSettingsDialog } = useSettingsDialog();

const isOpen = ref(false);
const searchQuery = ref('');
const searchInputRef = ref<HTMLInputElement>();

const selectedCount = computed(() => selectedSkillIds.value.length);

const filteredSkills = computed(() => {
  const query = searchQuery.value.toLowerCase().trim();
  if (!query) return availableSkills.value;
  return availableSkills.value.filter(
    (s) =>
      s.name.toLowerCase().includes(query) ||
      s.description.toLowerCase().includes(query)
  );
});

function isSelected(skillId: string): boolean {
  return selectedSkillIds.value.includes(skillId);
}

function sourceLabel(source: string): string {
  if (source === 'official') return t('Official');
  if (source === 'community') return t('Community');
  return t('Personal');
}

function handleToggle(skillId: string) {
  if (!isSelected(skillId) && !canSelectMore.value) {
    showInfoToast(t('Maximum {max} skills per message', { max: MAX_ENABLED_SKILLS }));
    return;
  }
  toggleSkillSelection(skillId);
}

function handleManageSkills() {
  isOpen.value = false;
  openSettingsDialog('skills');
}

// Lazy load skills on first open
watch(isOpen, (open) => {
  if (open && availableSkills.value.length === 0 && !loading.value) {
    loadAvailableSkills();
  }
  if (open) {
    searchQuery.value = '';
    // Focus search input after popover opens
    setTimeout(() => searchInputRef.value?.focus(), 100);
  }
});
</script>

<style scoped>
.skill-picker-btn {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s ease;
  background: var(--background-white-main);
  border: 1px solid var(--border-main);
  color: var(--text-secondary);
  position: relative;
}

.skill-picker-btn:hover {
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-dark);
  color: var(--text-primary);
}

.skill-picker-btn.has-selected {
  border-color: #3b82f6;
  color: #3b82f6;
}

.skill-picker-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #3b82f6;
  color: white;
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.skill-picker-popover {
  width: 320px !important;
}

.skill-picker-content {
  display: flex;
  flex-direction: column;
  padding: 8px 0;
}

.skill-picker-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px 8px;
  border-bottom: 1px solid var(--border-light);
}

.skill-picker-search-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.skill-picker-search-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  color: var(--text-primary);
  padding: 4px 0;
}

.skill-picker-search-input::placeholder {
  color: var(--text-disable);
}

.skill-picker-list {
  max-height: 300px;
  overflow-y: auto;
  padding: 4px 0;
}

.skill-picker-empty {
  padding: 20px 16px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

.skill-picker-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.1s ease;
  width: 100%;
  text-align: left;
  border: none;
  background: transparent;
}

.skill-picker-item:hover {
  background: var(--fill-tsp-gray-main);
}

.skill-picker-item-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
  margin-top: 2px;
}

.skill-picker-item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.skill-picker-item-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.skill-picker-item-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.skill-picker-item-source {
  font-size: 10px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 4px;
  flex-shrink: 0;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.skill-picker-item-source.source-official {
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}

.skill-picker-item-source.source-community {
  background: rgba(168, 85, 247, 0.1);
  color: #a855f7;
}

.skill-picker-item-source.source-custom {
  background: rgba(34, 197, 94, 0.1);
  color: #22c55e;
}

.skill-picker-item-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.skill-picker-item-check {
  color: #3b82f6;
  flex-shrink: 0;
  margin-top: 2px;
}

.skill-picker-footer {
  padding: 6px 12px 4px;
  border-top: 1px solid var(--border-light);
}

.skill-picker-manage {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px 0;
  border: none;
  background: transparent;
  transition: color 0.1s ease;
}

.skill-picker-manage:hover {
  color: var(--text-primary);
}
</style>
