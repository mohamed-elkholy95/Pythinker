<template>
  <div class="skills-settings">
    <!-- Header Section -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon">
          <Puzzle class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">Skills</h4>
          <p class="section-desc">
            Prepackaged capabilities for your agents. Enable skills to unlock specific tool sets.
          </p>
        </div>
      </div>

      <!-- Stats -->
      <div class="skills-stats">
        <div class="stat-item">
          <span class="stat-value">{{ enabledCount }}</span>
          <span class="stat-label">Enabled</span>
        </div>
        <div class="stat-divider"></div>
        <div class="stat-item">
          <span class="stat-value">{{ maxSkills }}</span>
          <span class="stat-label">Maximum</span>
        </div>
        <div class="stat-divider"></div>
        <div class="stat-item">
          <span class="stat-value">{{ availableSkills.length }}</span>
          <span class="stat-label">Available</span>
        </div>
        <div class="stat-divider"></div>
        <div class="stat-item">
          <span class="stat-value">{{ customSkills.length }}</span>
          <span class="stat-label">Custom</span>
        </div>
      </div>
    </div>

    <!-- Add Custom Skills Banner  -->
    <div class="add-custom-banner">
      <div class="banner-left">
        <div class="banner-icon">
          <FileStack class="w-5 h-5" />
          <Settings class="w-3 h-3 banner-icon-badge" />
        </div>
        <div class="banner-text">
          <span class="banner-title">Add custom Skills</span>
          <span class="banner-subtitle">Add a skill to unlock new capabilities for yourself or your team.</span>
        </div>
      </div>
      <div class="add-dropdown" ref="addDropdownRef">
        <button class="add-btn" @click="showAddDropdown = !showAddDropdown">
          <Plus class="w-4 h-4" />
          <span>Add</span>
          <ChevronDown class="w-4 h-4 add-chevron" :class="{ 'is-open': showAddDropdown }" />
        </button>
        <div v-if="showAddDropdown" class="add-dropdown-menu">
          <button class="add-dropdown-item" @click="buildWithPythinker">
            <MessageCircle class="w-5 h-5" />
            <div class="item-text">
              <span class="item-title">Build with Pythinker</span>
              <span class="item-desc">Build great skills through conversation</span>
            </div>
          </button>
          <button class="add-dropdown-item add-dropdown-item-disabled" disabled>
            <Upload class="w-5 h-5" />
            <div class="item-text">
              <span class="item-title">Upload a skill <span class="coming-soon">(coming soon)</span></span>
              <span class="item-desc">Upload .zip, .skill, or folder</span>
            </div>
          </button>
          <button class="add-dropdown-item add-dropdown-item-disabled" disabled>
            <ShieldCheck class="w-5 h-5" />
            <div class="item-text">
              <span class="item-title">Add from official <span class="coming-soon">(coming soon)</span></span>
              <span class="item-desc">Pre-built skills maintained by Pythinker</span>
            </div>
          </button>
          <button class="add-dropdown-item add-dropdown-item-disabled" disabled>
            <Github class="w-5 h-5" />
            <div class="item-text">
              <span class="item-title">Import from GitHub <span class="coming-soon">(coming soon)</span></span>
              <span class="item-desc">Paste a repository link to get started</span>
            </div>
          </button>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading && userSkills.length === 0" class="loading-state">
      <div class="loading-spinner"></div>
      <span>Loading skills...</span>
    </div>

    <!-- Error State -->
    <div v-else-if="error && userSkills.length === 0" class="error-state">
      <AlertCircle class="w-5 h-5" />
      <span>{{ error }}</span>
      <button @click="loadSkills" class="retry-btn">Retry</button>
    </div>

    <!-- Skills Grid -->
    <div v-else-if="userSkills.length > 0" class="skills-grid">
      <div
        v-for="userSkill in userSkills"
        :key="userSkill.skill.id"
        class="skill-card"
        :class="{
          'skill-enabled': userSkill.enabled,
          'skill-premium': userSkill.skill.is_premium
        }"
      >
        <div class="skill-header">
          <div class="skill-icon-wrapper" :class="getIconBgClass(userSkill.skill.category)">
            <component :is="getSkillIcon(userSkill.skill.icon, userSkill.skill.id)" class="w-4 h-4" />
          </div>
          <div class="skill-info">
            <div class="skill-name-row">
              <span class="skill-name">{{ userSkill.skill.name }}</span>
              <Sparkles
                v-if="userSkill.skill.is_premium"
                class="w-3.5 h-3.5 text-amber-500"
              />
            </div>
            <span class="skill-source" :class="`source-${userSkill.skill.source}`">
              <CheckCircle2 v-if="userSkill.skill.source === 'official'" class="w-3 h-3" />
              {{ userSkill.skill.source }}
            </span>
          </div>
          <button
            @click="toggleSkill(userSkill.skill.id)"
            class="toggle-switch"
            :class="{ 'toggle-active': userSkill.enabled }"
            :disabled="loading"
            role="switch"
            :aria-checked="userSkill.enabled"
            :aria-label="`Toggle ${userSkill.skill.name} skill`"
          >
            <span class="toggle-thumb"></span>
          </button>
        </div>

        <p class="skill-description">{{ userSkill.skill.description }}</p>

        <div class="skill-footer">
          <div class="skill-tools">
            <Wrench class="w-3 h-3" />
            <span>{{ userSkill.skill.required_tools.length }} tools</span>
          </div>
          <span class="skill-version">v{{ userSkill.skill.version }}</span>
        </div>
      </div>
    </div>

    <!-- Custom Skills Section -->
    <div class="custom-skills-section">
      <!-- Empty State -->
      <div v-if="customSkills.length === 0" class="empty-state">
        <Wand2 class="w-8 h-8 text-[var(--text-quaternary)]" />
        <p>You haven't created any custom skills yet.</p>
        <p class="empty-hint">Use "Build with Pythinker" for AI-assisted skill creation!</p>
      </div>

      <!-- Custom Skills Grid -->
      <div v-else class="skills-grid custom-grid">
        <div
          v-for="skill in customSkills"
          :key="skill.id"
          class="skill-card custom-skill-card"
        >
          <div class="skill-header">
            <div class="skill-icon-wrapper icon-bg-purple">
              <component :is="getSkillIcon(skill.icon, skill.id)" class="w-4 h-4" />
            </div>
            <div class="skill-info">
              <div class="skill-name-row">
                <span class="skill-name">{{ skill.name }}</span>
                <Globe v-if="skill.is_public" class="w-3.5 h-3.5 text-green-500" title="Published" />
              </div>
              <span class="skill-source source-custom">Custom</span>
            </div>
            <div class="skill-actions">
              <button @click="editSkill(skill)" class="action-btn" title="Edit">
                <Pencil class="w-3.5 h-3.5" />
              </button>
              <button @click="confirmDeleteSkill(skill)" class="action-btn delete-btn" title="Delete">
                <Trash2 class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <p class="skill-description">{{ skill.description }}</p>

          <div class="skill-footer">
            <div class="skill-tools">
              <Wrench class="w-3 h-3" />
              <span>{{ skill.required_tools.length }} tools</span>
            </div>
            <button
              v-if="!skill.is_public"
              @click="confirmPublishSkill(skill)"
              class="publish-btn"
              title="Publish to community"
            >
              <Upload class="w-3 h-3" />
              Publish
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Info Section -->
    <div class="info-section">
      <div class="info-card">
        <Info class="w-4 h-4 text-[var(--icon-tertiary)]" />
        <p>
          Skills can also be selected per-message in the chat input.
          Enabled skills here set the default tools available to the agent.
          Use "Build with Pythinker" for AI-assisted skill creation!
        </p>
      </div>
    </div>

    <!-- Skill Creator Dialog -->
    <SkillCreatorDialog
      :isOpen="showCreatorDialog"
      :editingSkill="editingSkill"
      @close="closeCreatorDialog"
      @created="onSkillCreated"
      @updated="onSkillUpdated"
    />

    <!-- Delete Confirmation Dialog -->
    <div v-if="deletingSkill" class="confirm-overlay" @click.self="deletingSkill = null">
      <div class="confirm-dialog">
        <div class="confirm-icon delete-icon">
          <Trash2 class="w-5 h-5" />
        </div>
        <h3 class="confirm-title">Delete "{{ deletingSkill.name }}"?</h3>
        <p class="confirm-text">This action cannot be undone. The skill will be permanently removed.</p>
        <div class="confirm-actions">
          <button @click="deletingSkill = null" class="btn-secondary">Cancel</button>
          <button @click="handleDeleteSkill" class="btn-danger" :disabled="loading">
            Delete Skill
          </button>
        </div>
      </div>
    </div>

    <!-- Publish Confirmation Dialog -->
    <div v-if="publishingSkill" class="confirm-overlay" @click.self="publishingSkill = null">
      <div class="confirm-dialog">
        <div class="confirm-icon publish-icon">
          <Upload class="w-5 h-5" />
        </div>
        <h3 class="confirm-title">Publish "{{ publishingSkill.name }}"?</h3>
        <p class="confirm-text">This will share your skill with the community. Published skills cannot be edited.</p>
        <div class="confirm-actions">
          <button @click="publishingSkill = null" class="btn-secondary">Cancel</button>
          <button @click="handlePublishSkill" class="btn-primary" :disabled="loading">
            Publish Skill
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, onUnmounted } from 'vue';
import {
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Wrench,
  Info,
  Search,
  Code,
  Globe,
  Folder,
  BarChart2,
  FileSpreadsheet,
  TrendingUp,
  Bot,
  Puzzle,
  Wand2,
  Pencil,
  Trash2,
  Upload,
  FileStack,
  Plus,
  ChevronDown,
  Settings,
  MessageCircle,
  ShieldCheck,
  Github,
} from 'lucide-vue-next';
import { useSkills } from '@/composables/useSkills';
import type { Skill } from '@/api/skills';
import SkillCreatorDialog from './SkillCreatorDialog.vue';

const emit = defineEmits<{
  (e: 'buildWithPythinker'): void;
}>();

const {
  availableSkills,
  userSkills,
  customSkills,
  enabledCount,
  maxSkills,
  loading,
  error,
  loadSkills,
  loadCustomSkills,
  toggleSkillEnabled,
  deleteSkill,
  publishSkill,
} = useSkills();

// Dialog state
const showCreatorDialog = ref(false);
const showAddDropdown = ref(false);
const editingSkill = ref<Skill | null>(null);
const deletingSkill = ref<Skill | null>(null);
const publishingSkill = ref<Skill | null>(null);

// Ref for click outside
const addDropdownRef = ref<HTMLElement | null>(null);

// Click outside handler
function handleClickOutside(event: MouseEvent) {
  const target = event.target as Node;
  if (addDropdownRef.value && !addDropdownRef.value.contains(target)) {
    showAddDropdown.value = false;
  }
}

// Load skills on mount
onMounted(async () => {
  await Promise.all([loadSkills(), loadCustomSkills()]);
  document.addEventListener('click', handleClickOutside);
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
});

// Toggle skill enabled state
const toggleSkill = async (skillId: string) => {
  await toggleSkillEnabled(skillId);
};

// Build with Pythinker - emit event to open chat with skill-creator skill
function buildWithPythinker() {
  showAddDropdown.value = false;
  emit('buildWithPythinker');
}

// Get skill icon component based on icon name
const getSkillIcon = (iconName: string, skillId?: string) => {
  if (skillId === 'skill-creator') {
    return Puzzle;
  }
  const iconMap: Record<string, unknown> = {
    search: Search,
    code: Code,
    globe: Globe,
    folder: Folder,
    'bar-chart': BarChart2,
    'file-spreadsheet': FileSpreadsheet,
    'trending-up': TrendingUp,
    bot: Bot,
    sparkles: Sparkles,
    'wand-2': Wand2,
    puzzle: Puzzle,
  };
  return iconMap[iconName] || Puzzle;
};

// Get icon background class based on category
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

// Custom skill actions
function editSkill(skill: Skill) {
  editingSkill.value = skill;
  showCreatorDialog.value = true;
}

function confirmDeleteSkill(skill: Skill) {
  deletingSkill.value = skill;
}

function confirmPublishSkill(skill: Skill) {
  publishingSkill.value = skill;
}

async function handleDeleteSkill() {
  if (!deletingSkill.value) return;
  const success = await deleteSkill(deletingSkill.value.id);
  if (success) {
    deletingSkill.value = null;
  }
}

async function handlePublishSkill() {
  if (!publishingSkill.value) return;
  const skill = await publishSkill(publishingSkill.value.id);
  if (skill) {
    publishingSkill.value = null;
  }
}

function closeCreatorDialog() {
  showCreatorDialog.value = false;
  editingSkill.value = null;
}

function onSkillCreated(_skill: Skill) {
  // Skill is already added to customSkills by the composable
}

function onSkillUpdated(_skill: Skill) {
  // Skill is already updated in customSkills by the composable
}
</script>

<style scoped>
.skills-settings {
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: 100%;
  animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.section-card {
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 20px;
}

.section-header {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 16px;
}

.section-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: var(--fill-blue);
  border-radius: 10px;
  color: var(--text-brand);
  flex-shrink: 0;
}

.section-info {
  flex: 1;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.section-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  line-height: 1.4;
}

/* Skills Stats */
.skills-stats {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  background: var(--background-white-main);
  border-radius: 10px;
  border: 1px solid var(--border-light);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-brand);
}

.stat-label {
  font-size: 11px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-divider {
  width: 1px;
  height: 32px;
  background: var(--border-light);
}

/* Loading State */
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px;
  color: var(--text-tertiary);
  font-size: 14px;
}

.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-main);
  border-top-color: var(--text-brand);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Error State */
.error-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px;
  color: var(--function-error);
  font-size: 14px;
}

.retry-btn {
  padding: 6px 12px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-brand);
  background: var(--fill-blue);
  border-radius: 6px;
  transition: all 0.2s ease;
}

.retry-btn:hover {
  opacity: 0.8;
}

/* Skills Grid */
.skills-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.skill-card {
  background: var(--background-white-main);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  padding: 16px;
  transition: all 0.2s ease;
}

.skill-card:hover {
  border-color: var(--border-main);
  box-shadow: 0 2px 8px var(--shadow-XS);
}

.skill-enabled {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.04) 0%, rgba(59, 130, 246, 0.01) 100%);
  border-color: rgba(59, 130, 246, 0.2);
}

.skill-premium {
  position: relative;
}

.skill-premium::before {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, transparent 50%, rgba(245, 158, 11, 0.1) 50%);
  border-radius: 0 12px 0 0;
}

.skill-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.skill-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  flex-shrink: 0;
  color: white;
}

.icon-bg-blue {
  background: #000000;
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

.skill-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.skill-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.skill-source {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 500;
  text-transform: capitalize;
  margin-top: 4px;
  padding: 2px 6px;
  border-radius: 4px;
}

.skill-source.source-official {
  color: #059669;
  background: rgba(5, 150, 105, 0.1);
  border: 1px solid rgba(5, 150, 105, 0.2);
}

.skill-source.source-official svg {
  color: #059669;
}

.skill-source.source-custom {
  color: #6b7280;
  background: rgba(107, 114, 128, 0.1);
  border: 1px dashed rgba(107, 114, 128, 0.3);
}

.skill-source.source-community {
  color: #7c3aed;
  background: rgba(124, 58, 237, 0.1);
  border: 1px solid rgba(124, 58, 237, 0.2);
}

.skill-description {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-bottom: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.skill-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 12px;
  border-top: 1px solid var(--border-light);
}

.skill-tools {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-tertiary);
}

.skill-version {
  font-size: 10px;
  color: var(--text-quaternary);
}

/* Toggle Switch - Enhanced iOS-style */
.toggle-switch {
  position: relative;
  width: 44px;
  height: 26px;
  background: #e5e5ea;
  border-radius: 13px;
  transition: background-color 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
  cursor: pointer;
  border: none;
  outline: none;
}

.toggle-switch:hover:not(:disabled) {
  background: #d1d1d6;
}

.toggle-switch:focus-visible {
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.3);
}

.toggle-switch:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.toggle-active {
  background: #34c759;
}

.toggle-active:hover:not(:disabled) {
  background: #2db84e;
}

.toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 22px;
  height: 22px;
  background: #ffffff;
  border-radius: 50%;
  box-shadow:
    0 3px 8px rgba(0, 0, 0, 0.15),
    0 1px 1px rgba(0, 0, 0, 0.06);
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.toggle-active .toggle-thumb {
  transform: translateX(18px);
}

/* Pressed state animation */
.toggle-switch:active:not(:disabled) .toggle-thumb {
  width: 26px;
}

.toggle-active:active:not(:disabled) .toggle-thumb {
  transform: translateX(14px);
}

/* Info Section */
.info-section {
  margin-top: 4px;
}

.info-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 10px;
}

.info-card p {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.5;
}

/* Custom Skills Section */
.custom-skills-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Add Custom Skills Banner */
.add-custom-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  background: #f3f3f3;
  border: 1px solid #e6e6e6;
  border-radius: 18px;
}

.banner-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.banner-icon {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  background: #ffffff;
  border-radius: 14px;
  color: #8c8c8c;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.banner-icon-badge {
  position: absolute;
  bottom: -3px;
  right: -3px;
  padding: 3px;
  background: white;
  border-radius: 6px;
  color: var(--text-tertiary);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.banner-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.banner-title {
  font-size: 17px;
  font-weight: 600;
  color: #2c2c2c;
  line-height: 1.25;
}

.banner-subtitle {
  font-size: 14px;
  color: #6b6b6b;
  line-height: 1.35;
}

.add-dropdown {
  position: relative;
}

.add-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 34px;
  padding: 0 12px;
  color: #ffffff;
  background: #1f1f1f;
  border: 1px solid #1f1f1f;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 600;
  transition: all 0.2s ease;
}

.add-btn:hover {
  background: #151515;
  border-color: #151515;
}

.add-chevron {
  transition: transform 0.2s ease;
}

.add-chevron.is-open {
  transform: rotate(180deg);
}

.add-dropdown-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 300px;
  background: #ffffff;
  border: 1px solid #e6e6e6;
  border-radius: 14px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.12);
  z-index: 100;
  overflow: hidden;
  animation: dropdownFadeIn 0.2s ease-out;
}

@keyframes dropdownFadeIn {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.add-dropdown-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  text-align: left;
  transition: background 0.15s;
}

.add-dropdown-item:hover:not(:disabled) {
  background: #f7f7f7;
}

.add-dropdown-item-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.coming-soon {
  font-size: 11px;
  font-weight: 400;
  color: #999;
}

.add-dropdown-item + .add-dropdown-item {
  border-top: 1px solid #f0f0f0;
}

.add-dropdown-item svg {
  flex-shrink: 0;
  color: #2d2d2d;
  margin-top: 2px;
}

.item-text {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.item-title {
  font-size: 14px;
  font-weight: 600;
  color: #2c2c2c;
}

.item-desc {
  font-size: 12px;
  color: #7a7a7a;
  line-height: 1.4;
}

@media (max-width: 900px) {
  .add-custom-banner {
    align-items: flex-start;
    gap: 12px;
  }

  .banner-text {
    flex-direction: column;
    align-items: flex-start;
  }

  .banner-subtitle {
    white-space: normal;
  }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px;
  background: var(--fill-tsp-gray-light);
  border-radius: 12px;
  text-align: center;
}

.empty-state p {
  font-size: 13px;
  color: var(--text-tertiary);
}

.empty-hint {
  font-size: 12px;
  color: #8b5cf6;
  font-weight: 500;
}

.custom-grid {
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
}

.custom-skill-card {
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.04) 0%, rgba(99, 102, 241, 0.02) 100%);
  border-color: rgba(139, 92, 246, 0.15);
}

.skill-actions {
  display: flex;
  gap: 4px;
}

.action-btn {
  padding: 6px;
  color: var(--text-tertiary);
  border-radius: 6px;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: var(--fill-tsp-gray-dark);
  color: var(--text-primary);
}

.delete-btn:hover {
  background: rgba(239, 68, 68, 0.1);
  color: var(--function-error);
}

.publish-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-brand);
  background: var(--fill-blue);
  border-radius: 6px;
  transition: all 0.2s ease;
}

.publish-btn:hover {
  opacity: 0.8;
}

/* Confirmation Dialogs */
.confirm-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1100;
}

.confirm-dialog {
  background: var(--background-white-main);
  border-radius: 16px;
  padding: 24px;
  width: 100%;
  max-width: 380px;
  text-align: center;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
}

.confirm-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  margin: 0 auto 16px;
}

.delete-icon {
  background: rgba(239, 68, 68, 0.1);
  color: var(--function-error);
}

.publish-icon {
  background: rgba(59, 130, 246, 0.1);
  color: var(--text-brand);
}

.confirm-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.confirm-text {
  font-size: 13px;
  color: var(--text-tertiary);
  line-height: 1.5;
  margin-bottom: 20px;
}

.confirm-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.btn-secondary {
  padding: 10px 18px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--fill-tsp-gray-light);
  border-radius: 10px;
  transition: all 0.2s ease;
}

.btn-secondary:hover {
  background: var(--fill-tsp-gray-dark);
}

.btn-danger {
  padding: 10px 18px;
  font-size: 14px;
  font-weight: 500;
  color: white;
  background: var(--function-error);
  border-radius: 10px;
  transition: all 0.2s ease;
}

.btn-danger:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  padding: 10px 18px;
  font-size: 14px;
  font-weight: 500;
  color: white;
  background: var(--text-brand);
  border-radius: 10px;
  transition: all 0.2s ease;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
