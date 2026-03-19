<template>
  <Teleport to="body">
    <div v-if="isOpen" class="dialog-overlay" @click.self.stop="handleClose" @keydown.escape.stop="handleClose" @mousedown.stop @pointerdown.stop>
      <div
        ref="dialogContainerRef"
        class="dialog-container"
        role="dialog"
        aria-modal="true"
        aria-labelledby="skill-dialog-title"
        aria-describedby="skill-dialog-subtitle"
      >
        <!-- Header -->
        <div class="dialog-header">
          <div class="header-content">
            <div class="header-icon">
              <Wand2 class="w-5 h-5" />
            </div>
            <div>
              <h2 id="skill-dialog-title" class="dialog-title">{{ isEditing ? 'Edit Skill' : 'Create Custom Skill' }}</h2>
              <p id="skill-dialog-subtitle" class="dialog-subtitle">
                {{ isEditing ? 'Modify your custom skill' : 'Define a new skill with custom tools and prompts' }}
              </p>
            </div>
          </div>
          <button @click="handleClose" class="close-btn" aria-label="Close dialog">
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Form -->
        <form ref="dialogBodyRef" @submit.prevent="handleSubmit" class="dialog-body">
          <!-- Name -->
          <div class="form-group">
            <label for="skill-name" class="form-label">
              Name <span class="required">*</span>
            </label>
            <input
              id="skill-name"
              v-model="form.name"
              type="text"
              class="form-input"
              placeholder="e.g., Code Reviewer"
              minlength="2"
              maxlength="100"
              required
              aria-describedby="skill-name-hint"
            />
            <p id="skill-name-hint" class="form-hint">A short, descriptive name (2-100 characters)</p>
          </div>

          <!-- Description -->
          <div class="form-group">
            <label for="skill-description" class="form-label">
              Description <span class="required">*</span>
            </label>
            <textarea
              id="skill-description"
              v-model="form.description"
              class="form-textarea"
              placeholder="e.g., Reviews code for bugs, security issues, and best practices"
              minlength="10"
              maxlength="500"
              rows="2"
              required
              aria-describedby="skill-description-hint"
            ></textarea>
            <p id="skill-description-hint" class="form-hint">Brief explanation of what this skill does (10-500 characters)</p>
          </div>

          <!-- Icon -->
          <div class="form-group">
            <label class="form-label">Icon</label>
            <div class="icon-selector">
              <button
                v-for="iconName in availableIcons"
                :key="iconName"
                type="button"
                class="icon-option"
                :class="{ 'icon-selected': form.icon === iconName }"
                :aria-label="`Select ${iconName} icon`"
                :aria-pressed="form.icon === iconName"
                @click="form.icon = iconName"
              >
                <component :is="getIconComponent(iconName)" class="w-4 h-4" />
              </button>
            </div>
          </div>

          <!-- Required Tools -->
          <div class="form-group" role="group" aria-labelledby="skill-tools-label">
            <label id="skill-tools-label" class="form-label">
              Required Tools <span class="required">*</span>
            </label>
            <div class="tools-grid">
              <label
                v-for="tool in AVAILABLE_TOOLS"
                :key="tool.name"
                class="tool-checkbox"
                :class="{ 'tool-selected': form.required_tools.includes(tool.name) }"
              >
                <input
                  type="checkbox"
                  :value="tool.name"
                  v-model="form.required_tools"
                  class="sr-only"
                />
                <span class="tool-name">{{ tool.label }}</span>
                <span class="tool-desc">{{ tool.description }}</span>
              </label>
            </div>
            <p class="form-hint">Select tools this skill needs to function. Scroll down for more options.</p>
          </div>

          <!-- System Prompt Addition -->
          <div class="form-group">
            <div class="flex items-center justify-between mb-1">
              <label for="skill-prompt" class="form-label" style="margin-bottom: 0">
                System Prompt Instructions <span class="required">*</span>
              </label>
              <button
                type="button"
                :disabled="!form.name || !form.description || isGenerating"
                class="generate-draft-btn"
                @click="handleGenerateDraft"
              >
                <Loader2 v-if="isGenerating" :size="12" class="animate-spin" />
                <Sparkles v-else :size="12" />
                {{ isGenerating ? 'Generating...' : 'Generate draft' }}
              </button>
            </div>
            <p v-if="generateError" class="generate-error">{{ generateError }}</p>
            <textarea
              id="skill-prompt"
              v-model="form.system_prompt_addition"
              class="form-textarea code-textarea"
              aria-describedby="skill-prompt-hint"
              placeholder="<skill_instructions>
When [trigger condition]:
1. First, [action 1]
2. Then, [action 2]

Guidelines:
- [Specific guideline]
</skill_instructions>"
              minlength="10"
              maxlength="4000"
              rows="10"
              required
            ></textarea>
            <div class="prompt-counter">
              {{ form.system_prompt_addition.length }} / 4000 characters
            </div>
            <p id="skill-prompt-hint" class="form-hint">
              Instructions that guide the agent when this skill is enabled. Use XML-style tags for organization.
            </p>
          </div>

          <!-- Error message -->
          <div v-if="formError" class="form-error">
            <AlertCircle class="w-4 h-4" />
            {{ formError }}
          </div>
        </form>

        <!-- Footer -->
        <div class="dialog-footer">
          <button type="button" @click="handleClose" class="btn-secondary">
            Cancel
          </button>
          <button
            type="submit"
            @click="handleSubmit"
            class="btn-primary"
            :disabled="isSubmitting || !isFormValid"
          >
            <Loader2 v-if="isSubmitting" class="w-4 h-4 animate-spin" />
            {{ isEditing ? 'Save Changes' : 'Create Skill' }}
          </button>
        </div>
      </div>
    </div>
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
      // Scroll to top when opening for edit
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
}

// Handle close
function handleClose() {
  resetForm();
  emit('close');
}

// Focus trap: keep Tab/Shift+Tab within the dialog
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

// Focus the first input when dialog opens
watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      nextTick(() => {
        const nameInput = document.getElementById('skill-name');
        nameInput?.focus();
        document.addEventListener('keydown', handleFocusTrap);
      });
    } else {
      document.removeEventListener('keydown', handleFocusTrap);
    }
  }
);

onUnmounted(() => {
  document.removeEventListener('keydown', handleFocusTrap);
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
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  padding: 20px;
  pointer-events: auto;
}

.dialog-container {
  background: var(--background-white-main);
  border-radius: 16px;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
  width: 100%;
  max-width: 640px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.dialog-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-light);
}

.header-content {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

.header-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  background: linear-gradient(135deg, #1a1a1a 0%, #262626 100%);
  border-radius: 12px;
  color: white;
}

.dialog-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.dialog-subtitle {
  font-size: 13px;
  color: var(--text-tertiary);
}

.close-btn {
  padding: 8px;
  color: var(--text-tertiary);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.close-btn:hover {
  background: var(--fill-tsp-gray-light);
  color: var(--text-primary);
}

.dialog-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  /* Performance optimizations */
  will-change: scroll-position;
  -webkit-overflow-scrolling: touch;
  /* Visual scroll indicator */
  scroll-behavior: smooth;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.required {
  color: var(--function-error);
}

.form-input,
.form-textarea {
  width: 100%;
  padding: 10px 14px;
  font-size: 14px;
  color: var(--text-primary);
  background: var(--background-white-main);
  border: 1px solid var(--border-light);
  border-radius: 10px;
  transition: all 0.2s ease;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--text-brand);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.form-textarea {
  resize: vertical;
  min-height: 80px;
}

.code-textarea {
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', monospace;
  font-size: 13px;
  line-height: 1.5;
}

.prompt-counter {
  font-size: 11px;
  color: var(--text-quaternary);
  text-align: right;
}

.flex {
  display: flex;
}

.items-center {
  align-items: center;
}

.justify-between {
  justify-content: space-between;
}

.mb-1 {
  margin-bottom: 4px;
}

.generate-draft-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 9999px;
  background: rgba(59, 130, 246, 0.1);
  color: var(--text-brand);
  transition: all 0.2s ease;
}

.generate-draft-btn:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.2);
}

.generate-draft-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.generate-error {
  font-size: 12px;
  color: var(--function-error);
  margin-top: 4px;
}

.form-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.4;
}

.form-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 10px;
  color: var(--function-error);
  font-size: 13px;
}

/* Icon Selector */
.icon-selector {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.icon-option {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--fill-tsp-gray-light);
  color: var(--text-secondary);
  transition: all 0.2s ease;
}

.icon-option:hover {
  background: var(--fill-tsp-gray-dark);
  color: var(--text-primary);
}

.icon-selected {
  background: var(--text-brand);
  color: white;
}

.icon-selected:hover {
  background: var(--text-brand);
  color: white;
}

/* Tools Grid */
.tools-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
}

.tool-checkbox {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  background: var(--fill-tsp-gray-light);
  border: 1px solid transparent;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tool-checkbox:hover {
  background: var(--fill-tsp-gray-dark);
}

.tool-selected {
  background: rgba(59, 130, 246, 0.1);
  border-color: rgba(59, 130, 246, 0.3);
}

.tool-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.tool-desc {
  font-size: 11px;
  color: var(--text-tertiary);
}

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

/* Footer */
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-light);
  background: var(--fill-tsp-white-main);
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
  color: var(--text-primary);
}

.btn-primary {
  display: flex;
  align-items: center;
  gap: 8px;
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

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
