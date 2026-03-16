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
const loadingAvailable = ref(false);
const loadingCustom = ref(false);
const loadingUser = ref(false);
const loadingMutation = ref(false);
const loading = computed(() => loadingAvailable.value || loadingCustom.value || loadingUser.value || loadingMutation.value);
const error = ref<string | null>(null);

// Per-message selected skills (reset after sending)
const selectedSkillIds = ref<string[]>([]);

// Session-level persistent skills (persist across messages in same session)
const sessionSkillIds = ref<string[]>([]);

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
      loadingAvailable.value = true;
      error.value = null;
      availableSkills.value = await getAvailableSkills(category);
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load skills';
      console.error('Failed to load available skills:', err);
    } finally {
      loadingAvailable.value = false;
    }
  }

  /**
   * Load user's skill configurations
   */
  async function loadUserSkills(): Promise<void> {
    try {
      loadingUser.value = true;
      error.value = null;
      userSkillsData.value = await getUserSkills();
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load user skills';
      console.error('Failed to load user skills:', err);
    } finally {
      loadingUser.value = false;
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
      loadingMutation.value = true;
      error.value = null;
      await updateUserSkill(skillId, { enabled: newEnabled });
      await loadUserSkills(); // Refresh state
      return true;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to update skill';
      console.error('Failed to toggle skill:', err);
      return false;
    } finally {
      loadingMutation.value = false;
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
      loadingMutation.value = true;
      error.value = null;
      userSkillsData.value = await enableSkills(skillIds);
      return true;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to enable skills';
      console.error('Failed to enable skills:', err);
      return false;
    } finally {
      loadingMutation.value = false;
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
   * Clear per-message selected skills (called after message is sent)
   * Session skills are preserved.
   */
  function clearSelectedSkills(): void {
    selectedSkillIds.value = [];
  }

  /**
   * Lock skills for the current session (persist across messages).
   * Called when skill_activation SSE event arrives.
   */
  function lockSkillsForSession(skillIds: string[]): void {
    const combined = new Set([...sessionSkillIds.value, ...skillIds]);
    sessionSkillIds.value = [...combined];
  }

  /**
   * Remove a single skill from session persistence.
   */
  function removeSessionSkill(skillId: string): void {
    sessionSkillIds.value = sessionSkillIds.value.filter((id) => id !== skillId);
  }

  /**
   * Clear all session-level skills (called on session change).
   */
  function clearSessionSkills(): void {
    sessionSkillIds.value = [];
  }

  /**
   * Get the current selected skill IDs (for sending with message)
   */
  function getSelectedSkillIds(): string[] {
    return [...selectedSkillIds.value];
  }

  /**
   * Get effective skill IDs = session skills + per-message picks (deduplicated).
   * This is what gets sent with each message.
   */
  function getEffectiveSkillIds(): string[] {
    return [...new Set([...sessionSkillIds.value, ...selectedSkillIds.value])];
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
      loadingCustom.value = true;
      error.value = null;
      customSkills.value = await getMyCustomSkills();
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load custom skills';
      console.error('Failed to load custom skills:', err);
    } finally {
      loadingCustom.value = false;
    }
  }

  /**
   * Create a new custom skill
   */
  async function createSkill(data: CreateCustomSkillRequest): Promise<Skill | null> {
    try {
      loadingMutation.value = true;
      error.value = null;
      const skill = await createCustomSkill(data);
      customSkills.value.unshift(skill); // Add to front of list
      return skill;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to create skill';
      console.error('Failed to create skill:', err);
      return null;
    } finally {
      loadingMutation.value = false;
    }
  }

  /**
   * Update a custom skill
   */
  async function updateSkill(skillId: string, data: UpdateCustomSkillRequest): Promise<Skill | null> {
    try {
      loadingMutation.value = true;
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
      loadingMutation.value = false;
    }
  }

  /**
   * Delete a custom skill
   */
  async function deleteSkill(skillId: string): Promise<boolean> {
    try {
      loadingMutation.value = true;
      error.value = null;
      await apiDeleteCustomSkill(skillId);
      customSkills.value = customSkills.value.filter((s) => s.id !== skillId);
      return true;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to delete skill';
      console.error('Failed to delete skill:', err);
      return false;
    } finally {
      loadingMutation.value = false;
    }
  }

  /**
   * Publish a custom skill to the community
   */
  async function publishSkill(skillId: string): Promise<Skill | null> {
    try {
      loadingMutation.value = true;
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
      loadingMutation.value = false;
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
    loading,
    error: readonly(error),

    // Custom skills state
    customSkills: readonly(customSkills),

    // Per-message selection state
    selectedSkillIds: readonly(selectedSkillIds),
    selectedSkills,
    canSelectMore,

    // Session-level persistent skills
    sessionSkillIds: readonly(sessionSkillIds),

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

    // Actions - session-level persistence
    lockSkillsForSession,
    removeSessionSkill,
    clearSessionSkills,
    getEffectiveSkillIds,

    // Utilities
    clearError,
  };
}
