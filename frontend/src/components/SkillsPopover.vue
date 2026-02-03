<template>
  <Popover v-model:open="isOpen">
    <PopoverTrigger as-child>
      <button
        class="skills-trigger"
        :class="{ 'has-selection': selectedCount > 0 }"
        @click="handleClick"
      >
        <Puzzle :size="16" />
      </button>
    </PopoverTrigger>

    <PopoverContent class="skills-popover" align="start" :side-offset="8">
      <!-- Search -->
      <div class="skills-search">
        <Search :size="16" />
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search skills..."
          class="search-input"
        />
      </div>

      <!-- Skills List -->
      <div class="skills-list">
        <div
          v-for="skill in filteredSkills"
          :key="skill.id"
          class="skill-item"
          :class="{
            'skill-selected': isSelected(skill.id),
            'skill-premium': skill.is_premium
          }"
          @click="handleSkillClick(skill.id)"
        >
          <div class="skill-icon-wrapper" :class="getIconBgClass(skill.category)">
            <component :is="getSkillIcon(skill.icon, skill.id)" class="w-3.5 h-3.5" />
          </div>
          <div class="skill-info">
            <div class="skill-header">
              <span class="skill-name">{{ skill.name }}</span>
              <span v-if="skill.source === 'official'" class="skill-badge skill-badge-official">Official</span>
              <span v-else-if="skill.source === 'custom'" class="skill-badge skill-badge-custom">Custom</span>
              <span v-else-if="skill.source === 'community'" class="skill-badge skill-badge-community">Community</span>
            </div>
            <p class="skill-description">{{ skill.description }}</p>
          </div>
          <Check
            v-if="isSelected(skill.id)"
            :size="16"
            class="skill-check"
          />
        </div>

        <!-- Empty State -->
        <div v-if="filteredSkills.length === 0" class="empty-state">
          <Sparkles :size="24" class="empty-icon" />
          <span>No skills found</span>
        </div>
      </div>

      <!-- Footer -->
      <div class="skills-footer">
        <div class="selection-info">
          {{ selectedCount }}/{{ maxSkills }} selected
        </div>
        <button @click="openSettings" class="manage-btn">
          <Settings :size="14" />
          <span>Manage Skills</span>
        </button>
      </div>
    </PopoverContent>
  </Popover>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Sparkles,
  Search,
  Check,
  Settings,
  Code,
  Globe,
  Folder,
  BarChart2,
  FileSpreadsheet,
  TrendingUp,
  Bot,
  Puzzle,
} from 'lucide-vue-next';
import SearchIcon from './icons/SearchIcon.vue';
import { useSkills } from '@/composables/useSkills';
import { useSettingsDialog } from '@/composables/useSettingsDialog';
import { MAX_ENABLED_SKILLS } from '@/api/skills';

const {
  availableSkills,
  selectedSkillIds,
  loadAvailableSkills,
  toggleSkillSelection,
} = useSkills();

const { openSettingsDialog } = useSettingsDialog();

const isOpen = ref(false);
const searchQuery = ref('');

// Load skills on mount
onMounted(async () => {
  if (availableSkills.value.length === 0) {
    await loadAvailableSkills();
  }
});

// Computed
const selectedCount = computed(() => selectedSkillIds.value.length);
const maxSkills = MAX_ENABLED_SKILLS;

const filteredSkills = computed(() => {
  if (!searchQuery.value.trim()) {
    return availableSkills.value;
  }
  const query = searchQuery.value.toLowerCase();
  return availableSkills.value.filter(
    (skill) =>
      skill.name.toLowerCase().includes(query) ||
      skill.description.toLowerCase().includes(query)
  );
});

// Methods
const handleClick = () => {
  if (availableSkills.value.length === 0) {
    loadAvailableSkills();
  }
};

const isSelected = (skillId: string) => {
  return selectedSkillIds.value.includes(skillId);
};

const handleSkillClick = (skillId: string) => {
  toggleSkillSelection(skillId);
  isOpen.value = false;
};

const openSettings = () => {
  isOpen.value = false;
  openSettingsDialog('skills');
};

// Get skill icon component
const getSkillIcon = (iconName: string, skillId?: string) => {
  if (skillId === 'skill-creator') {
    return Puzzle;
  }
  const iconMap: Record<string, any> = {
    search: SearchIcon,
    code: Code,
    globe: Globe,
    folder: Folder,
    'bar-chart': BarChart2,
    'file-spreadsheet': FileSpreadsheet,
    'trending-up': TrendingUp,
    bot: Bot,
    sparkles: Sparkles,
    puzzle: Puzzle,
  };
  return iconMap[iconName] || Sparkles;
};

// Get icon background class
const getIconBgClass = (category: string) => {
  const categoryColors: Record<string, string> = {
    research: 'icon-bg-blue',
    coding: 'icon-bg-purple',
    browser: 'icon-bg-green',
    file_management: 'icon-bg-orange',
    data_analysis: 'icon-bg-pink',
    communication: 'icon-bg-cyan',
    custom: 'icon-bg-gray',
  };
  return categoryColors[category] || 'icon-bg-blue';
};
</script>

<style scoped>
.skills-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--bolt-elements-bg-depth-4);
  border: 1px solid var(--bolt-elements-borderColor);
  color: var(--bolt-elements-textTertiary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.skills-trigger:hover {
  background: var(--bolt-elements-item-backgroundActive);
  color: var(--bolt-elements-textSecondary);
}

.skills-trigger.has-selection {
  background: var(--fill-blue);
  color: var(--text-brand);
  border-color: transparent;
}

.skills-popover {
  width: 320px;
  padding: 0;
  background: var(--background-white-main);
  border: 1px solid var(--border-main);
  border-radius: 12px;
  box-shadow: 0 8px 24px var(--shadow-M);
  overflow: hidden;
}

.skills-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
  color: var(--text-tertiary);
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 13px;
  color: var(--text-primary);
  outline: none;
}

.search-input::placeholder {
  color: var(--text-quaternary);
}

.skills-list {
  max-height: 280px;
  overflow-y: auto;
  padding: 6px;
}

.skill-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.skill-item:hover {
  background: var(--fill-tsp-white-main);
}

.skill-selected {
  background: var(--fill-blue);
}

.skill-selected:hover {
  background: rgba(59, 130, 246, 0.12);
}

.skill-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  flex-shrink: 0;
  color: white;
}

.icon-bg-blue {
  background: #3b82f6;
}

.icon-bg-purple {
  background: #8b5cf6;
}

.icon-bg-green {
  background: #10b981;
}

.icon-bg-orange {
  background: #f59e0b;
}

.icon-bg-pink {
  background: #ec4899;
}

.icon-bg-cyan {
  background: #06b6d4;
}

.icon-bg-gray {
  background: #6b7280;
}

.skill-info {
  flex: 1;
  min-width: 0;
}

.skill-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}

.skill-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.skill-badge {
  font-size: 10px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 4px;
}

.skill-badge-official {
  color: #059669;
  background: rgba(5, 150, 105, 0.1);
  border: 1px solid rgba(5, 150, 105, 0.2);
}

.skill-badge-custom {
  color: #6b7280;
  background: rgba(107, 114, 128, 0.1);
  border: 1px dashed rgba(107, 114, 128, 0.3);
}

.skill-badge-community {
  color: #7c3aed;
  background: rgba(124, 58, 237, 0.1);
  border: 1px solid rgba(124, 58, 237, 0.2);
}

.skill-description {
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.skill-check {
  color: var(--text-brand);
  flex-shrink: 0;
  margin-top: 2px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px;
  color: var(--text-tertiary);
  font-size: 13px;
}

.empty-icon {
  opacity: 0.5;
}

.skills-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-top: 1px solid var(--border-light);
  background: var(--fill-tsp-white-light);
}

.selection-info {
  font-size: 12px;
  color: var(--text-tertiary);
}

.manage-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.manage-btn:hover {
  background: var(--fill-tsp-white-main);
  color: var(--text-primary);
}
</style>
