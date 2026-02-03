import { ref, computed, readonly } from 'vue';
import {
  getAvailableSkills,
  getUserSkills,
  updateUserSkill,
  enableSkills,
  getMyCustomSkills,
  createCustomSkill,
  updateCustomSkill as apiUpdateCustomSkill,
  deleteCustomSkill as apiDeleteCustomSkill,
  publishCustomSkill as apiPublishCustomSkill,
  MAX_ENABLED_SKILLS,
  type Skill,
  type UserSkill,
  type UserSkillsResponse,
  type CreateCustomSkillRequest,
  type UpdateCustomSkillRequest,
} from '@/api/skills';

// Global state for skills
const availableSkills = ref<Skill[]>([]);
const userSkillsData = ref<UserSkillsResponse | null>(null);
const customSkills = ref<Skill[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

// Per-message selected skills (reset after sending)
const selectedSkillIds = ref<string[]>([]);

export function useSkills() {
  // Computed properties
  const userSkills = computed<UserSkill[]>(() => userSkillsData.value?.skills ?? []);

  const enabledSkills = computed<UserSkill[]>(() =>
    userSkills.value.filter((s) => s.enabled)
  );

  const enabledSkillIds = computed<string[]>(() =>
    enabledSkills.value.map((s) => s.skill.id)
  );

  const enabledCount = computed(() => userSkillsData.value?.enabled_count ?? 0);

  const maxSkills = computed(() => userSkillsData.value?.max_skills ?? MAX_ENABLED_SKILLS);

  const canEnableMore = computed(() => enabledCount.value < maxSkills.value);

  // Selected skills for current message
  const selectedSkills = computed<Skill[]>(() => {
    return availableSkills.value.filter((s) => selectedSkillIds.value.includes(s.id));
  });

  const canSelectMore = computed(() => selectedSkillIds.value.length < MAX_ENABLED_SKILLS);

  /**
   * Load available skills from the server
   */
  async function loadAvailableSkills(category?: string): Promise<void> {
    try {
      loading.value = true;
      error.value = null;
      availableSkills.value = await getAvailableSkills(category);
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load skills';
      console.error('Failed to load available skills:', err);
    } finally {
      loading.value = false;
    }
  }

  /**
   * Load user's skill configurations
   */
  async function loadUserSkills(): Promise<void> {
    try {
      loading.value = true;
      error.value = null;
      userSkillsData.value = await getUserSkills();
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load user skills';
      console.error('Failed to load user skills:', err);
    } finally {
      loading.value = false;
    }
  }

  /**
   * Load both available and user skills
   */
  async function loadSkills(): Promise<void> {
    await Promise.all([loadAvailableSkills(), loadUserSkills()]);
  }

  /**
   * Toggle a skill's enabled state in user settings
   */
  async function toggleSkillEnabled(skillId: string): Promise<boolean> {
    const currentSkill = userSkills.value.find((s) => s.skill.id === skillId);
    if (!currentSkill) return false;

    const newEnabled = !currentSkill.enabled;

    // Check if we can enable more
    if (newEnabled && !canEnableMore.value) {
      error.value = `Maximum ${maxSkills.value} skills allowed. Remove a skill to add another.`;
      return false;
    }

    try {
      loading.value = true;
      error.value = null;
      await updateUserSkill(skillId, { enabled: newEnabled });
      await loadUserSkills(); // Refresh state
      return true;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to update skill';
      console.error('Failed to toggle skill:', err);
      return false;
    } finally {
      loading.value = false;
    }
  }

  /**
   * Enable specific skills (replaces current enabled skills)
   */
  async function setEnabledSkills(skillIds: string[]): Promise<boolean> {
    if (skillIds.length > MAX_ENABLED_SKILLS) {
      error.value = `Maximum ${MAX_ENABLED_SKILLS} skills allowed.`;
      return false;
    }

    try {
      loading.value = true;
      error.value = null;
      userSkillsData.value = await enableSkills(skillIds);
      return true;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to enable skills';
      console.error('Failed to enable skills:', err);
      return false;
    } finally {
      loading.value = false;
    }
  }

  /**
   * Select a skill for the current message (per-message selection)
   */
  function selectSkill(skillId: string): boolean {
    if (selectedSkillIds.value.includes(skillId)) {
      // Already selected, do nothing
      return true;
    }

    if (!canSelectMore.value) {
      error.value = `Maximum ${MAX_ENABLED_SKILLS} skills allowed. Remove a skill to add another.`;
      return false;
    }

    selectedSkillIds.value.push(skillId);
    error.value = null;
    return true;
  }

  /**
   * Deselect a skill from the current message
   */
  function deselectSkill(skillId: string): void {
    const index = selectedSkillIds.value.indexOf(skillId);
    if (index !== -1) {
      selectedSkillIds.value.splice(index, 1);
    }
  }

  /**
   * Toggle skill selection for current message
   */
  function toggleSkillSelection(skillId: string): boolean {
    if (selectedSkillIds.value.includes(skillId)) {
      deselectSkill(skillId);
      return true;
    }
    return selectSkill(skillId);
  }

  /**
   * Clear selected skills (called after message is sent)
   */
  function clearSelectedSkills(): void {
    selectedSkillIds.value = [];
  }

  /**
   * Get the current selected skill IDs (for sending with message)
   */
  function getSelectedSkillIds(): string[] {
    return [...selectedSkillIds.value];
  }

  /**
   * Clear any error
   */
  function clearError(): void {
    error.value = null;
  }

  // ========================================
  // Custom Skills Management
  // ========================================

  /**
   * Load user's custom skills
   */
  async function loadCustomSkills(): Promise<void> {
    try {
      loading.value = true;
      error.value = null;
      customSkills.value = await getMyCustomSkills();
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load custom skills';
      console.error('Failed to load custom skills:', err);
    } finally {
      loading.value = false;
    }
  }

  /**
   * Create a new custom skill
   */
  async function createSkill(data: CreateCustomSkillRequest): Promise<Skill | null> {
    try {
      loading.value = true;
      error.value = null;
      const skill = await createCustomSkill(data);
      customSkills.value.unshift(skill); // Add to front of list
      return skill;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to create skill';
      console.error('Failed to create skill:', err);
      return null;
    } finally {
      loading.value = false;
    }
  }

  /**
   * Update a custom skill
   */
  async function updateSkill(skillId: string, data: UpdateCustomSkillRequest): Promise<Skill | null> {
    try {
      loading.value = true;
      error.value = null;
      const skill = await apiUpdateCustomSkill(skillId, data);
      // Update in local state
      const index = customSkills.value.findIndex((s) => s.id === skillId);
      if (index !== -1) {
        customSkills.value[index] = skill;
      }
      return skill;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to update skill';
      console.error('Failed to update skill:', err);
      return null;
    } finally {
      loading.value = false;
    }
  }

  /**
   * Delete a custom skill
   */
  async function deleteSkill(skillId: string): Promise<boolean> {
    try {
      loading.value = true;
      error.value = null;
      await apiDeleteCustomSkill(skillId);
      customSkills.value = customSkills.value.filter((s) => s.id !== skillId);
      return true;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to delete skill';
      console.error('Failed to delete skill:', err);
      return false;
    } finally {
      loading.value = false;
    }
  }

  /**
   * Publish a custom skill to the community
   */
  async function publishSkill(skillId: string): Promise<Skill | null> {
    try {
      loading.value = true;
      error.value = null;
      const skill = await apiPublishCustomSkill(skillId);
      // Update in local state
      const index = customSkills.value.findIndex((s) => s.id === skillId);
      if (index !== -1) {
        customSkills.value[index] = skill;
      }
      return skill;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to publish skill';
      console.error('Failed to publish skill:', err);
      return null;
    } finally {
      loading.value = false;
    }
  }

  return {
    // State (readonly to prevent external mutations)
    availableSkills: readonly(availableSkills),
    userSkills,
    enabledSkills,
    enabledSkillIds,
    enabledCount,
    maxSkills,
    canEnableMore,
    loading: readonly(loading),
    error: readonly(error),

    // Custom skills state
    customSkills: readonly(customSkills),

    // Per-message selection state
    selectedSkillIds: readonly(selectedSkillIds),
    selectedSkills,
    canSelectMore,

    // Actions - settings management
    loadAvailableSkills,
    loadUserSkills,
    loadSkills,
    toggleSkillEnabled,
    setEnabledSkills,

    // Actions - custom skill management
    loadCustomSkills,
    createSkill,
    updateSkill,
    deleteSkill,
    publishSkill,

    // Actions - per-message selection
    selectSkill,
    deselectSkill,
    toggleSkillSelection,
    clearSelectedSkills,
    getSelectedSkillIds,

    // Utilities
    clearError,
  };
}
