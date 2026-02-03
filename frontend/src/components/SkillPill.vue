<template>
  <div class="skill-pill" :class="{ 'skill-premium': skill.is_premium, 'skill-custom': skill.source === 'custom' }">
    <div class="skill-icon-wrapper" :class="getIconBgClass(skill.category)">
      <component :is="getSkillIcon(skill.icon, skill.id)" class="w-3 h-3" />
    </div>
    <span class="skill-name">{{ skill.name }}</span>
    <span v-if="skill.source === 'custom'" class="skill-source-badge">Custom</span>
    <button @click="$emit('remove', skill.id)" class="remove-btn">
      <X :size="12" />
    </button>
  </div>
</template>

<script setup lang="ts">
import {
  X,
  Sparkles,
  Search,
  Code,
  Globe,
  Folder,
  BarChart2,
  FileSpreadsheet,
  TrendingUp,
  Bot,
  Puzzle,
} from 'lucide-vue-next';
import type { Skill } from '@/api/skills';

defineProps<{
  skill: Skill;
}>();

defineEmits<{
  (e: 'remove', skillId: string): void;
}>();

// Get skill icon component
const getSkillIcon = (iconName: string, skillId?: string) => {
  if (skillId === 'skill-creator') {
    return Puzzle;
  }
  const iconMap: Record<string, any> = {
    search: Search,
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
.skill-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px 4px 4px;
  background: var(--fill-blue);
  border-radius: 6px;
  animation: slideIn 0.2s ease-out;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: scale(0.9);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.skill-premium {
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(59, 130, 246, 0.08) 100%);
  border: 1px solid rgba(245, 158, 11, 0.2);
}

.skill-custom {
  background: rgba(107, 114, 128, 0.08);
  border: 1px dashed rgba(107, 114, 128, 0.25);
}

.skill-source-badge {
  font-size: 9px;
  font-weight: 500;
  color: #6b7280;
  background: rgba(107, 114, 128, 0.15);
  padding: 1px 4px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.skill-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
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

.skill-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-brand);
  white-space: nowrap;
}

.remove-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 4px;
  color: var(--text-brand);
  opacity: 0.6;
  cursor: pointer;
  transition: all 0.15s ease;
}

.remove-btn:hover {
  opacity: 1;
  background: rgba(59, 130, 246, 0.2);
}
</style>
