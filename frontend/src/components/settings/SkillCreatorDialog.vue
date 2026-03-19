<template>
  <Teleport to="body">
    <Transition name="skill-dialog">
      <!-- data-dismissable-layer: helps Reka layer stacking; data-pythinker-skill-creator-overlay: DialogContent always prevents dismiss (DOM order independent). -->
      <div
        v-if="isOpen"
        class="skill-creator-overlay"
        data-dismissable-layer=""
        data-pythinker-skill-creator-overlay
        @mousedown.self.stop="handleClose"
      >
        <div
          ref="dialogContainerRef"
          class="skill-creator-container"
          role="dialog"
          aria-modal="true"
          aria-labelledby="skill-dialog-title"
          aria-describedby="skill-dialog-subtitle"
          @keydown.escape.stop="handleClose"
        >
          <!-- Header -->
          <div class="sc-header">
            <div class="sc-header-left">
              <div class="sc-header-icon">
                <Wand2 :size="18" />
              </div>
              <div>
                <h2 id="skill-dialog-title" class="sc-title">{{ isEditing ? 'Edit Skill' : 'Create Custom Skill' }}</h2>
                <p id="skill-dialog-subtitle" class="sc-subtitle">
                  {{ isEditing ? 'Modify your custom skill' : 'Define a new skill with custom tools and prompts' }}
                </p>
              </div>
            </div>
            <button @click="handleClose" class="sc-close" aria-label="Close dialog">
              <X :size="18" />
            </button>
          </div>

          <!-- Scrollable Form Body -->
          <form ref="dialogBodyRef" @submit.prevent="handleSubmit" class="sc-body">
            <!-- Name -->
            <div class="sc-field">
              <label for="skill-name" class="sc-label">
                Name <span class="sc-required">*</span>
              </label>
              <input
                id="skill-name"
                v-model="form.name"
                type="text"
                class="sc-input"
                placeholder="e.g., Code Reviewer"
                minlength="2"
                maxlength="100"
                required
              />
              <p class="sc-hint">A short, descriptive name (2-100 characters)</p>
            </div>

            <!-- Description -->
            <div class="sc-field">
              <label for="skill-description" class="sc-label">
                Description <span class="sc-required">*</span>
              </label>
              <textarea
                id="skill-description"
                v-model="form.description"
                class="sc-textarea"
                placeholder="e.g., Reviews code for bugs, security issues, and best practices"
                minlength="10"
                maxlength="500"
                rows="2"
                required
              ></textarea>
              <p class="sc-hint">Brief explanation of what this skill does (10-500 characters)</p>
            </div>

            <!-- Icon -->
            <div class="sc-field">
              <label class="sc-label">Icon</label>
              <div class="sc-icons">
                <button
                  v-for="iconName in availableIcons"
                  :key="iconName"
                  type="button"
                  class="sc-icon-btn"
                  :class="{ 'sc-icon-active': form.icon === iconName }"
                  :aria-label="`Select ${iconName} icon`"
                  :aria-pressed="form.icon === iconName"
                  @click="form.icon = iconName"
                >
                  <component :is="getIconComponent(iconName)" :size="15" />
                </button>
              </div>
            </div>

            <!-- Required Tools -->
            <div class="sc-field" role="group" aria-labelledby="skill-tools-label">
              <label id="skill-tools-label" class="sc-label">
                Required Tools <span class="sc-required">*</span>
              </label>
              <div class="sc-tools">
                <label
                  v-for="tool in AVAILABLE_TOOLS"
                  :key="tool.name"
                  class="sc-tool"
                  :class="{ 'sc-tool-active': form.required_tools.includes(tool.name) }"
                >
                  <input
                    type="checkbox"
                    :value="tool.name"
                    v-model="form.required_tools"
                    class="sr-only"
                  />
                  <span class="sc-tool-name">{{ tool.label }}</span>
                  <span class="sc-tool-desc">{{ tool.description }}</span>
                </label>
              </div>
            </div>

            <!-- System Prompt Instructions -->
            <div class="sc-field">
              <div class="sc-label-row">
                <label for="skill-prompt" class="sc-label" style="margin-bottom: 0">
                  Instructions <span class="sc-required">*</span>
                </label>
                <button
                  type="button"
                  :disabled="!form.name || !form.description || isGenerating"
                  class="sc-generate-btn"
                  @click="handleGenerateDraft"
                >
                  <Loader2 v-if="isGenerating" :size="12" class="animate-spin" />
                  <Sparkles v-else :size="12" />
                  {{ isGenerating ? 'Generating...' : 'Generate draft' }}
                </button>
              </div>
              <p v-if="generateError" class="sc-error-inline">{{ generateError }}</p>
              <textarea
                id="skill-prompt"
                v-model="form.system_prompt_addition"
                class="sc-textarea sc-code"
                placeholder="# My Skill&#10;&#10;## Workflow&#10;1. First step&#10;2. Second step&#10;&#10;## Guidelines&#10;- Be specific&#10;- Follow best practices"
                minlength="10"
                maxlength="4000"
                rows="8"
                required
              ></textarea>
              <div class="sc-counter">
                {{ form.system_prompt_addition.length }} / 4000
              </div>
            </div>

            <!-- Error message -->
            <div v-if="formError" class="sc-form-error">
              <AlertCircle :size="14" />
              {{ formError }}
            </div>
          </form>

          <!-- Footer -->
          <div class="sc-footer">
            <button type="button" @click="handleClose" class="sc-btn-cancel">
              Cancel
            </button>
            <button
              type="submit"
              @click="handleSubmit"
              class="sc-btn-submit"
              :disabled="isSubmitting || !isFormValid"
            >
              <Loader2 v-if="isSubmitting" :size="14" class="animate-spin" />
              {{ isEditing ? 'Save Changes' : 'Create Skill' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from 'vue';
import {
  X,
  Wand2,
  AlertCircle,
  Loader2,
  Sparkles,
  Code,
  Search,
  Globe,
  Folder,
  BarChart2,
  FileSpreadsheet,
  TrendingUp,
  Bot,
  FileCode,
  Terminal,
  MessageSquare,
  Database,
  Zap,
} from 'lucide-vue-next';
import type { Skill, CreateCustomSkillRequest } from '@/api/skills';
import { generateSkillDraft } from '@/api/skills';

// Dialog refs
const dialogBodyRef = ref<HTMLElement | null>(null);
const dialogContainerRef = ref<HTMLElement | null>(null);

const props = defineProps<{
  isOpen: boolean;
  editingSkill?: Skill | null;
}>();

const emit = defineEmits<{
  close: [];
  created: [skill: Skill];
  updated: [skill: Skill];
}>();

const isEditing = computed(() => !!props.editingSkill);
const isSubmitting = ref(false);
const formError = ref<string | null>(null);
const isGenerating = ref(false);
const generateError = ref('');

async function handleGenerateDraft() {
  if (!form.value.name || !form.value.description) return;
  if (
    form.value.system_prompt_addition &&
    !confirm('Replace current instructions with generated draft?')
  )
    return;

  isGenerating.value = true;
  generateError.value = '';
  try {
    const draft = await generateSkillDraft(
      form.value.name,
      form.value.description,
      form.value.required_tools || [],
      form.value.optional_tools || [],
    );
    form.value.system_prompt_addition = draft.instructions;
    if (draft.description_suggestion && draft.description_suggestion !== form.value.description) {
      if (form.value.description.length < 80) {
        form.value.description = draft.description_suggestion;
      }
    }
  } catch (err: unknown) {
    generateError.value = 'Failed to generate draft. Please try again.';
    console.error('Draft generation error:', err);
  } finally {
    isGenerating.value = false;
  }
}

// Form state
const form = ref<CreateCustomSkillRequest>({
  name: '',
  description: '',
  category: 'custom',
  icon: 'sparkles',
  required_tools: [],
  optional_tools: [],
  system_prompt_addition: '',
});

// Available icons
const availableIcons = [
  'sparkles', 'code', 'search', 'globe', 'folder',
  'bar-chart', 'file-spreadsheet', 'trending-up', 'bot',
  'file-code', 'terminal', 'message-square', 'database', 'zap', 'wand-2'
];

// Available tools with labels
const AVAILABLE_TOOLS = [
  { name: 'info_search_web', label: 'Web Search', description: 'Search the web' },
  { name: 'browser_navigate', label: 'Browser Navigate', description: 'Go to URLs' },
  { name: 'browser_view', label: 'Browser View', description: 'View current page' },
  { name: 'browser_get_content', label: 'Get Content', description: 'Extract page content' },
  { name: 'browser_click', label: 'Browser Click', description: 'Click elements' },
  { name: 'browser_input', label: 'Browser Input', description: 'Type text' },
  { name: 'file_read', label: 'File Read', description: 'Read files' },
  { name: 'file_write', label: 'File Write', description: 'Create/write files' },
  { name: 'file_str_replace', label: 'File Edit', description: 'Edit file contents' },
  { name: 'file_find_in_content', label: 'Search Files', description: 'Search in files' },
  { name: 'code_execute_python', label: 'Python', description: 'Run Python code' },
  { name: 'shell_exec', label: 'Shell', description: 'Execute commands' },
  { name: 'message_notify_user', label: 'Notify', description: 'Send notifications' },
  { name: 'message_ask_user', label: 'Ask User', description: 'Ask questions' },
];

// Icon component mapping
const getIconComponent = (iconName: string) => {
  const iconMap: Record<string, unknown> = {
    sparkles: Sparkles,
    code: Code,
    search: Search,
    globe: Globe,
    folder: Folder,
    'bar-chart': BarChart2,
    'file-spreadsheet': FileSpreadsheet,
    'trending-up': TrendingUp,
    bot: Bot,
    'file-code': FileCode,
    terminal: Terminal,
    'message-square': MessageSquare,
    database: Database,
    zap: Zap,
    'wand-2': Wand2,
  };
  return iconMap[iconName] || Sparkles;
};

// Form validation
const isFormValid = computed(() => {
  return (
    form.value.name.trim().length >= 2 &&
    form.value.description.trim().length >= 10 &&
    form.value.required_tools.length > 0 &&
    form.value.system_prompt_addition.trim().length >= 10
  );
});

// Watch for editing skill changes
watch(
  () => props.editingSkill,
  (skill) => {
    if (skill) {
      form.value = {
        name: skill.name,
        description: skill.description,
        category: skill.category,
        icon: skill.icon,
        required_tools: [...skill.required_tools],
        optional_tools: [...(skill.optional_tools || [])],
        system_prompt_addition: skill.system_prompt_addition || '',
      };
      nextTick(() => {
        if (dialogBodyRef.value) {
          dialogBodyRef.value.scrollTop = 0;
        }
      });
    } else {
      resetForm();
    }
  },
  { immediate: true }
);

// Reset form
function resetForm() {
  form.value = {
    name: '',
    description: '',
    category: 'custom',
    icon: 'sparkles',
    required_tools: [],
    optional_tools: [],
    system_prompt_addition: '',
  };
  formError.value = null;
  generateError.value = '';
}

// Handle close
function handleClose() {
  resetForm();
  emit('close');
}

// Focus trap
function handleFocusTrap(e: KeyboardEvent) {
  if (e.key !== 'Tab' || !dialogContainerRef.value) return;

  const focusable = dialogContainerRef.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
  );
  if (focusable.length === 0) return;

  const first = focusable[0];
  const last = focusable[focusable.length - 1];

  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

// Suppress the Settings dialog layer while Creator is open (Reka UI, not Radix data attrs).
// Avoid overflow:hidden on the shell — it breaks flex/scroll layout inside Settings (misaligned panes).
const SETTINGS_DIALOG_SELECTOR = '[data-pythinker-settings-dialog]';

function suppressSettingsDialogLayer() {
  document.querySelectorAll('[data-reka-focus-guard]').forEach((el) => {
    (el as HTMLElement).style.display = 'none';
  });
  document.querySelectorAll('[data-slot="dialog-overlay"]').forEach((el) => {
    (el as HTMLElement).style.pointerEvents = 'none';
  });
  const settingsShell = document.querySelector(SETTINGS_DIALOG_SELECTOR) as HTMLElement | null;
  if (settingsShell) {
    settingsShell.setAttribute('inert', '');
    settingsShell.style.pointerEvents = 'none';
  }
}

function restoreSettingsDialogLayer() {
  document.querySelectorAll('[data-reka-focus-guard]').forEach((el) => {
    (el as HTMLElement).style.display = '';
  });
  document.querySelectorAll('[data-slot="dialog-overlay"]').forEach((el) => {
    (el as HTMLElement).style.pointerEvents = '';
  });
  const settingsShell = document.querySelector(SETTINGS_DIALOG_SELECTOR) as HTMLElement | null;
  if (settingsShell) {
    settingsShell.removeAttribute('inert');
    settingsShell.style.pointerEvents = '';
  }
}

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      nextTick(suppressSettingsDialogLayer);
      setTimeout(() => {
        document.getElementById('skill-name')?.focus();
      }, 80);
      document.addEventListener('keydown', handleFocusTrap);
    } else {
      restoreSettingsDialogLayer();
      document.removeEventListener('keydown', handleFocusTrap);
    }
  }
);

onUnmounted(() => {
  document.removeEventListener('keydown', handleFocusTrap);
  restoreSettingsDialogLayer();
});

// Handle submit
async function handleSubmit() {
  if (!isFormValid.value) return;

  isSubmitting.value = true;
  formError.value = null;

  try {
    const { useSkills } = await import('@/composables/useSkills');
    const { createSkill, updateSkill } = useSkills();

    if (isEditing.value && props.editingSkill) {
      const skill = await updateSkill(props.editingSkill.id, form.value);
      if (skill) {
        emit('updated', skill);
        handleClose();
      }
    } else {
      const skill = await createSkill(form.value);
      if (skill) {
        emit('created', skill);
        handleClose();
      }
    }
  } catch (err) {
    formError.value = err instanceof Error ? err.message : 'Failed to save skill';
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<style scoped>
/* ── Overlay ────────────────────────────────── */
.skill-creator-overlay {
  position: fixed;
  inset: 0;
  z-index: 99999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  padding: 24px;
  pointer-events: auto;
  overscroll-behavior: contain;
}

/* ── Container ──────────────────────────────── */
.skill-creator-container {
  background: var(--background-white-main, #fff);
  border-radius: 14px;
  box-shadow:
    0 24px 48px -12px rgba(0, 0, 0, 0.25),
    0 0 0 1px rgba(0, 0, 0, 0.06);
  width: 100%;
  max-width: 580px;
  height: min(88vh, 720px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Header ─────────────────────────────────── */
.sc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-light, #e5e5e5);
  flex-shrink: 0;
}

.sc-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sc-header-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: #1a1a1a;
  border-radius: 10px;
  color: white;
}

.sc-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #111);
  line-height: 1.2;
}

.sc-subtitle {
  font-size: 12px;
  color: var(--text-tertiary, #888);
  margin-top: 2px;
}

.sc-close {
  padding: 6px;
  color: var(--text-tertiary, #888);
  border-radius: 8px;
  transition: all 0.15s;
}
.sc-close:hover {
  background: var(--fill-tsp-gray-light, #f0f0f0);
  color: var(--text-primary, #111);
}

/* ── Body (scrollable) ──────────────────────── */
.sc-body {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
  touch-action: pan-y;
}

/* ── Fields ──────────────────────────────────── */
.sc-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sc-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #111);
  margin-bottom: 2px;
}

.sc-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.sc-required {
  color: #ef4444;
}

.sc-input,
.sc-textarea {
  width: 100%;
  padding: 9px 12px;
  font-size: 14px;
  color: var(--text-primary, #111);
  background: var(--background-white-main, #fff);
  border: 1px solid var(--border-light, #ddd);
  border-radius: 8px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.sc-input:focus,
.sc-textarea:focus {
  outline: none;
  border-color: var(--text-brand, #3b82f6);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.12);
}

.sc-textarea {
  resize: vertical;
  min-height: 64px;
}

.sc-code {
  font-family: 'SF Mono', 'Monaco', 'Menlo', 'Consolas', monospace;
  font-size: 12.5px;
  line-height: 1.55;
}

.sc-counter {
  font-size: 11px;
  color: var(--text-quaternary, #aaa);
  text-align: right;
}

.sc-hint {
  font-size: 11px;
  color: var(--text-tertiary, #888);
  line-height: 1.3;
}

/* ── Generate Button ─────────────────────────── */
.sc-generate-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  font-size: 11.5px;
  font-weight: 500;
  border-radius: 6px;
  background: rgba(59, 130, 246, 0.08);
  color: var(--text-brand, #3b82f6);
  transition: all 0.15s;
}
.sc-generate-btn:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.16);
}
.sc-generate-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.sc-error-inline {
  font-size: 12px;
  color: #ef4444;
}

/* ── Icons ───────────────────────────────────── */
.sc-icons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.sc-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--fill-tsp-gray-light, #f5f5f5);
  color: var(--text-secondary, #555);
  transition: all 0.15s;
}
.sc-icon-btn:hover {
  background: var(--fill-tsp-gray-dark, #e5e5e5);
  color: var(--text-primary, #111);
}
.sc-icon-active {
  background: #1a1a1a !important;
  color: white !important;
}

/* ── Tools Grid ──────────────────────────────── */
.sc-tools {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

.sc-tool {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 8px 10px;
  background: var(--fill-tsp-gray-light, #f5f5f5);
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}
.sc-tool:hover {
  background: var(--fill-tsp-gray-dark, #e8e8e8);
}
.sc-tool-active {
  background: rgba(59, 130, 246, 0.08);
  border-color: rgba(59, 130, 246, 0.25);
}

.sc-tool-name {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-primary, #111);
}
.sc-tool-desc {
  font-size: 11px;
  color: var(--text-tertiary, #888);
}

/* ── Error ───────────────────────────────────── */
.sc-form-error {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.15);
  border-radius: 8px;
  color: #ef4444;
  font-size: 13px;
}

/* ── Footer ──────────────────────────────────── */
.sc-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--border-light, #e5e5e5);
  flex-shrink: 0;
}

.sc-btn-cancel {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary, #555);
  background: var(--fill-tsp-gray-light, #f5f5f5);
  border-radius: 8px;
  transition: all 0.15s;
}
.sc-btn-cancel:hover {
  background: var(--fill-tsp-gray-dark, #e5e5e5);
  color: var(--text-primary, #111);
}

.sc-btn-submit {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  color: white;
  background: #1a1a1a;
  border-radius: 8px;
  transition: all 0.15s;
}
.sc-btn-submit:hover:not(:disabled) {
  background: #333;
}
.sc-btn-submit:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ── Utility ─────────────────────────────────── */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

.animate-spin {
  animation: sc-spin 1s linear infinite;
}

@keyframes sc-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ── Transition ──────────────────────────────── */
.skill-dialog-enter-active {
  transition: opacity 0.15s ease;
}
.skill-dialog-enter-active .skill-creator-container {
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.15s ease;
}
.skill-dialog-leave-active {
  transition: opacity 0.1s ease;
}
.skill-dialog-leave-active .skill-creator-container {
  transition: transform 0.1s ease, opacity 0.1s ease;
}
.skill-dialog-enter-from {
  opacity: 0;
}
.skill-dialog-enter-from .skill-creator-container {
  opacity: 0;
  transform: scale(0.97) translateY(8px);
}
.skill-dialog-leave-to {
  opacity: 0;
}
.skill-dialog-leave-to .skill-creator-container {
  opacity: 0;
  transform: scale(0.97) translateY(4px);
}
</style>
