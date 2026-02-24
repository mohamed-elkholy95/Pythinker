<template>
  <!-- Backdrop -->
  <Transition name="fade">
    <div
      v-if="isOpen"
      class="context-panel-backdrop z-40"
      @click="$emit('close')"
    ></div>
  </Transition>

  <!-- Panel -->
  <Transition name="slide-right">
    <div
      v-if="isOpen"
      class="context-panel z-50 fixed top-0 right-0 h-full w-[380px] bg-[var(--background-menu-white)] border-l border-[var(--border-main)] shadow-2xl flex flex-col"
    >
      <!-- Header -->
      <div class="px-5 py-4 border-b border-[var(--border-main)] flex items-center justify-between sticky top-0 bg-[var(--background-menu-white)]">
        <h2 class="text-base font-semibold text-[var(--text-primary)] flex items-center gap-2">
          <Database :size="16" class="text-[var(--icon-secondary)]" />
          {{ $t('Active Context') }}
        </h2>
        <button
          @click="$emit('close')"
          class="p-1.5 rounded-lg hover:bg-[var(--fill-tsp-gray-main)] transition-colors text-[var(--icon-secondary)] hover:text-[var(--text-primary)]"
          :aria-label="$t('Close Context Panel')"
        >
          <X :size="18" />
        </button>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto px-5 py-6 flex flex-col gap-6">
        
        <!-- Files Section -->
        <section class="context-section">
          <div class="flex items-center gap-2 mb-3">
            <Files :size="14" class="text-[var(--icon-tertiary)]" />
            <h3 class="text-sm font-medium text-[var(--text-secondary)]">{{ $t('Uploaded Files') }}</h3>
            <span class="ml-auto text-xs bg-[var(--fill-tsp-gray-main)] text-[var(--text-tertiary)] px-2 py-0.5 rounded-full">
              {{ files.length }}
            </span>
          </div>
          <div v-if="files.length > 0" class="flex flex-col gap-2">
            <div
              v-for="file in files"
              :key="file.file_id"
              class="flex items-center gap-3 p-2.5 rounded-xl border border-[var(--border-light)] bg-[var(--fill-tsp-white-main)] hover:border-[var(--border-main)] transition-colors"
            >
              <div class="flex items-center justify-center w-8 h-8 rounded-lg bg-[var(--fill-tsp-gray-main)] text-[var(--icon-secondary)] shrink-0">
                <FileText :size="16" />
              </div>
              <div class="flex flex-col min-w-0 flex-1">
                <span class="text-sm font-medium text-[var(--text-primary)] truncate">{{ file.filename }}</span>
                <span class="text-xs text-[var(--text-tertiary)]">{{ formatFileSize(file.size) }}</span>
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-[var(--text-tertiary)] italic px-1">{{ $t('No files active in this session.') }}</p>
        </section>

        <!-- Skills Section -->
        <section class="context-section">
          <div class="flex items-center gap-2 mb-3">
            <Puzzle :size="14" class="text-[var(--icon-tertiary)]" />
            <h3 class="text-sm font-medium text-[var(--text-secondary)]">{{ $t('Active Skills') }}</h3>
            <span class="ml-auto text-xs bg-[var(--fill-tsp-gray-main)] text-[var(--text-tertiary)] px-2 py-0.5 rounded-full">
              {{ skillIds.length }}
            </span>
          </div>
          <div v-if="skillIds.length > 0" class="flex flex-wrap gap-2">
            <div
              v-for="skillId in skillIds"
              :key="skillId"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-[var(--border-dark)] bg-[var(--fill-tsp-white-dark)] text-xs font-medium text-[var(--text-primary)]"
            >
              <Puzzle :size="12" class="text-[var(--icon-secondary)]" />
              {{ getSkillName(skillId) }}
            </div>
          </div>
        </section>

        <!-- Retained Context Section -->
        <section class="context-section">
          <div class="flex items-center gap-2 mb-3">
            <Brain :size="14" class="text-[var(--icon-tertiary)]" />
            <h3 class="text-sm font-medium text-[var(--text-secondary)]">{{ $t('Retained Context') }}</h3>
          </div>
          <p class="text-[13px] text-[var(--text-tertiary)] px-1 mb-2 leading-snug">
            Current active entities and implicit constraints being prioritized by the agent.
          </p>
          <div class="flex flex-wrap gap-2 px-1">
            <div class="inline-flex items-center px-2 py-1 rounded-md bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 text-[11px] font-medium border border-blue-200 dark:border-blue-800/40">
              Goal: Code Enhancement
            </div>
            <div class="inline-flex items-center px-2 py-1 rounded-md bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 text-[11px] font-medium border border-purple-200 dark:border-purple-800/40">
              Topic: UI/UX Transparency
            </div>
            <div class="inline-flex items-center px-2 py-1 rounded-md bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300 text-[11px] font-medium border border-emerald-200 dark:border-emerald-800/40">
              Constraint: High Detail
            </div>
          </div>
        </section>

        <!-- Environment / Workspace Section -->
        <section class="context-section">
          <div class="flex items-center gap-2 mb-3">
            <Terminal :size="14" class="text-[var(--icon-tertiary)]" />
            <h3 class="text-sm font-medium text-[var(--text-secondary)]">{{ $t('Environment Details') }}</h3>
          </div>
          
          <div class="flex flex-col gap-3">
            <div v-if="envKeys.length > 0" class="rounded-xl border border-[var(--border-light)] bg-transparent p-3">
              <h4 class="text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wider mb-2">{{ $t('Environment Variables') }}</h4>
              <div class="flex flex-wrap gap-1.5">
                <span v-for="key in envKeys" :key="key" class="font-mono text-[11px] px-2 py-1 bg-[var(--fill-tsp-gray-main)] text-[var(--text-secondary)] rounded-md border border-[var(--border-light)]">
                  {{ key }}
                </span>
              </div>
            </div>
          </div>
        </section>

      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { Database, X, Files, FileText, Puzzle, Terminal, Brain } from 'lucide-vue-next';
import type { FileInfo } from '../api/file';
import { formatFileSize } from '../utils/fileType';
import { useSkills } from '../composables/useSkills';

defineProps<{
  isOpen: boolean;
  files: FileInfo[];
  skillIds: string[];
  envKeys: string[];
}>();

defineEmits<{
  (e: 'close'): void;
}>();

const { availableSkills } = useSkills();

const getSkillName = (id: string) => {
  const matching = availableSkills.value.find((s: any) => s.id === id);
  return matching ? matching.name : id;
};
</script>

<style scoped>
.context-panel-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(2px);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s ease;
}

.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

.context-section {
  display: flex;
  flex-direction: column;
}
</style>
