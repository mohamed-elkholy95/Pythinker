<template>
  <Dialog :open="open" @update:open="handleOpenChange">
    <DialogContent class="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2">
          <Sparkles class="h-5 w-5 text-[var(--icon-accent)]" />
          {{ t('Workspace Templates') }}
        </DialogTitle>
        <DialogDescription>
          {{ t('Available workspace templates for organizing your tasks') }}
        </DialogDescription>
      </DialogHeader>

      <!-- Loading state -->
      <div v-if="loading" class="flex items-center justify-center py-12">
        <Loader2 class="h-8 w-8 text-[var(--icon-secondary)] animate-spin" />
      </div>

      <!-- Error state -->
      <div v-else-if="error" class="py-6">
        <div class="flex items-start gap-2 p-4 rounded-lg bg-[var(--background-error-subtle)] border border-[var(--border-error)]">
          <AlertCircle class="h-5 w-5 text-[var(--text-error)] flex-shrink-0 mt-0.5" />
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium text-[var(--text-error)]">{{ t('Failed to load templates') }}</p>
            <p class="text-xs text-[var(--text-secondary)] mt-1">{{ error }}</p>
          </div>
        </div>
      </div>

      <!-- Templates list -->
      <div v-else class="flex-1 overflow-auto space-y-4 py-2">
        <div
          v-for="template in templates"
          :key="template.name"
          class="border border-[var(--border-light)] rounded-lg p-4 hover:border-[var(--border-main)] transition-colors"
        >
          <!-- Template header -->
          <div class="flex items-start justify-between mb-3">
            <div class="flex items-center gap-2">
              <div class="p-2 rounded-lg bg-[var(--bolt-elements-bg-depth-2)]">
                <FolderTree class="h-4 w-4 text-[var(--icon-accent)]" />
              </div>
              <div>
                <h4 class="text-sm font-semibold text-[var(--text-primary)] capitalize">
                  {{ template.name.replace('_', ' ') }}
                </h4>
                <p class="text-xs text-[var(--text-secondary)] mt-0.5">{{ template.description }}</p>
              </div>
            </div>
          </div>

          <!-- Folders -->
          <div class="space-y-2 mb-3">
            <p class="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wide">
              {{ t('Folders') }}
            </p>
            <div class="grid grid-cols-1 gap-2">
              <div
                v-for="[folderName, description] in Object.entries(template.folders)"
                :key="folderName"
                class="flex items-start gap-2 p-2 rounded bg-[var(--bolt-elements-bg-depth-1)]"
              >
                <Folder class="h-3.5 w-3.5 text-[var(--icon-accent)] flex-shrink-0 mt-0.5" />
                <div class="flex-1 min-w-0">
                  <p class="text-xs font-medium text-[var(--text-primary)]">{{ folderName }}/</p>
                  <p class="text-xs text-[var(--text-secondary)]">{{ description }}</p>
                </div>
              </div>
            </div>
          </div>

          <!-- Keywords -->
          <div>
            <p class="text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wide mb-2">
              {{ t('Trigger Keywords') }}
            </p>
            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="keyword in template.trigger_keywords"
                :key="keyword"
                class="px-2 py-1 text-xs font-medium rounded-full bg-[var(--bolt-elements-bg-depth-2)] text-[var(--text-secondary)] border border-[var(--border-light)]"
              >
                {{ keyword }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="pt-4 border-t border-[var(--border-light)]">
        <div class="flex items-start gap-2 p-3 rounded-lg bg-[var(--bolt-elements-bg-depth-1)]">
          <Info class="h-4 w-4 text-[var(--icon-accent)] flex-shrink-0 mt-0.5" />
          <p class="text-xs text-[var(--text-secondary)]">
            {{ t('Workspaces are automatically selected based on your task description. Include keywords to match a specific template.') }}
          </p>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog';
import {
  FolderTree,
  Folder,
  Sparkles,
  Loader2,
  AlertCircle,
  Info
} from 'lucide-vue-next';
import { getWorkspaceTemplates, WorkspaceTemplate } from '../api/agent';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

const props = defineProps<{
  open: boolean;
}>();

const emit = defineEmits<{
  'update:open': [value: boolean];
}>();

const templates = ref<WorkspaceTemplate[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const loadTemplates = async () => {
  loading.value = true;
  error.value = null;

  try {
    const response = await getWorkspaceTemplates();
    templates.value = response.templates;
  } catch (err: any) {
    console.error('Failed to load templates:', err);
    error.value = err.message || 'Unknown error';
  } finally {
    loading.value = false;
  }
};

const handleOpenChange = (value: boolean) => {
  emit('update:open', value);
};

// Load templates when dialog opens
watch(() => props.open, (isOpen) => {
  if (isOpen && templates.value.length === 0) {
    loadTemplates();
  }
});
</script>
