<template>
  <div class="h-full flex flex-col bg-[var(--background-nav)] border-l border-[var(--border-main)]">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-[var(--border-light)]">
      <div class="flex items-center gap-2">
        <FolderTree class="h-4 w-4 text-[var(--icon-secondary)]" />
        <h3 class="text-sm font-medium text-[var(--text-primary)]">{{ t('Workspace') }}</h3>
      </div>
      <button
        v-if="workspace?.workspace_structure"
        @click="refreshWorkspace"
        class="p-1 rounded hover:bg-[var(--fill-tsp-gray-main)]"
        :disabled="loading"
        aria-label="Refresh workspace"
      >
        <RotateCw
          :class="[
            'h-4 w-4 text-[var(--icon-secondary)]',
            loading && 'animate-spin'
          ]"
        />
      </button>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-auto">
      <!-- Loading state -->
      <div v-if="loading && !workspace" class="flex items-center justify-center h-32">
        <Loader2 class="h-6 w-6 text-[var(--icon-secondary)] animate-spin" />
      </div>

      <!-- Error state -->
      <div v-else-if="error" class="p-4">
        <div class="flex items-start gap-2 p-3 rounded-lg bg-[var(--background-error-subtle)] border border-[var(--border-error)]">
          <AlertCircle class="h-4 w-4 text-[var(--text-error)] flex-shrink-0 mt-0.5" />
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium text-[var(--text-error)]">{{ t('Failed to load workspace') }}</p>
            <p class="text-xs text-[var(--text-secondary)] mt-1">{{ error }}</p>
          </div>
        </div>
      </div>

      <!-- No workspace state -->
      <div v-else-if="!workspace?.workspace_structure" class="flex flex-col items-center justify-center p-6 text-center h-full">
        <FolderOpen class="h-12 w-12 text-[var(--icon-tertiary)] mb-3" />
        <p class="text-sm font-medium text-[var(--text-secondary)] mb-1">{{ t('No workspace initialized') }}</p>
        <p class="text-xs text-[var(--text-tertiary)]">{{ t('Send a message to start') }}</p>
      </div>

      <!-- Workspace structure -->
      <div v-else class="p-3">
        <!-- Workspace root -->
        <div v-if="workspace.workspace_root" class="mb-3 p-2 rounded-lg bg-[var(--bolt-elements-bg-depth-2)] border border-[var(--border-light)]">
          <div class="flex items-center gap-2">
            <Folder class="h-3.5 w-3.5 text-[var(--icon-accent)]" />
            <p class="text-xs font-mono text-[var(--text-tertiary)] truncate">{{ workspace.workspace_root }}</p>
          </div>
        </div>

        <!-- Folder list -->
        <div class="space-y-1">
          <div
            v-for="[folderName, description] in Object.entries(workspace.workspace_structure)"
            :key="folderName"
            class="group p-2 rounded-lg hover:bg-[var(--fill-tsp-gray-main)] cursor-pointer transition-colors"
            @click="handleFolderClick(folderName)"
          >
            <div class="flex items-start gap-2">
              <Folder class="h-4 w-4 text-[var(--icon-accent)] flex-shrink-0 mt-0.5" />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1">
                  <p class="text-sm font-medium text-[var(--text-primary)]">{{ folderName }}/</p>
                  <ChevronRight class="h-3 w-3 text-[var(--icon-tertiary)] opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
                <p class="text-xs text-[var(--text-secondary)] mt-0.5">{{ description }}</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Stats -->
        <div class="mt-4 pt-3 border-t border-[var(--border-light)]">
          <div class="flex items-center justify-between text-xs text-[var(--text-tertiary)]">
            <span>{{ Object.keys(workspace.workspace_structure).length }} {{ t('folders') }}</span>
            <button
              @click="showTemplateInfo"
              class="flex items-center gap-1 hover:text-[var(--text-secondary)] transition-colors"
            >
              <Info class="h-3 w-3" />
              <span>{{ t('Template info') }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import {
  FolderTree,
  Folder,
  FolderOpen,
  RotateCw,
  Loader2,
  AlertCircle,
  ChevronRight,
  Info
} from 'lucide-vue-next';
import { getSessionWorkspace, SessionWorkspaceResponse } from '../api/agent';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

const props = defineProps<{
  sessionId: string;
}>();

const emit = defineEmits<{
  folderClick: [folderName: string];
  templateInfo: [];
}>();

const workspace = ref<SessionWorkspaceResponse | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

const loadWorkspace = async () => {
  if (!props.sessionId) return;

  loading.value = true;
  error.value = null;

  try {
    workspace.value = await getSessionWorkspace(props.sessionId);
  } catch (err: any) {
    console.error('Failed to load workspace:', err);
    error.value = err.message || 'Unknown error';
    workspace.value = null;
  } finally {
    loading.value = false;
  }
};

const refreshWorkspace = () => {
  loadWorkspace();
};

const handleFolderClick = (folderName: string) => {
  emit('folderClick', folderName);
};

const showTemplateInfo = () => {
  emit('templateInfo');
};

// Load workspace when session changes
watch(() => props.sessionId, () => {
  loadWorkspace();
}, { immediate: true });

onMounted(() => {
  loadWorkspace();
});
</script>
