<template>
  <DialogRoot v-model:open="isOpen">
    <DialogPortal>
      <DialogOverlay class="modal-overlay" />
      <DialogContent class="modal-content">
        <!-- Header -->
        <div class="modal-header">
          <DialogTitle class="modal-title">Create project</DialogTitle>
          <DialogClose class="modal-close" aria-label="Close">
            <X :size="20" />
          </DialogClose>
        </div>

        <!-- Folder icon -->
        <div class="modal-icon-wrapper">
          <div class="modal-icon-circle">
            <Folder :size="28" class="text-[var(--text-secondary)]" />
          </div>
        </div>

        <!-- Form -->
        <div class="modal-body">
          <!-- Project name -->
          <div class="form-group">
            <label class="form-label">Project name</label>
            <div class="input-wrapper">
              <input
                v-model="form.name"
                type="text"
                class="form-input"
                placeholder="new_project"
                @keydown.enter.prevent="handleCreate"
              />
              <button
                v-if="form.name"
                class="input-clear"
                type="button"
                @click="form.name = ''"
                aria-label="Clear"
              >
                <XCircle :size="16" />
              </button>
            </div>
          </div>

          <!-- Instructions -->
          <div class="form-group">
            <label class="form-label">Instructions <span class="form-label-optional">(optional)</span></label>
            <textarea
              v-model="form.instructions"
              class="form-textarea"
              rows="5"
              placeholder='e.g. "Focus on Python best practices", "Maintain a professional tone", or "Always provide sources for important conclusions".'
            />
          </div>

          <!-- Connectors -->
          <div class="connectors-row">
            <span class="connectors-label">Connectors <span class="form-label-optional">(optional)</span></span>
            <button class="connectors-add-btn" type="button" disabled>
              <Plus :size="14" />
              <span>Add connectors</span>
            </button>
          </div>
        </div>

        <!-- Footer -->
        <div class="modal-footer">
          <DialogClose as-child>
            <button class="btn-cancel" type="button">Cancel</button>
          </DialogClose>
          <button
            class="btn-create"
            type="button"
            :disabled="!form.name.trim() || creating"
            @click="handleCreate"
          >
            {{ creating ? 'Creating...' : 'Create' }}
          </button>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<script setup lang="ts">
import { reactive, ref, computed } from 'vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogClose } from 'reka-ui'
import { X, XCircle, Folder, Plus } from 'lucide-vue-next'
import * as projectsApi from '@/api/projects'
import type { ProjectListItem } from '@/types/project'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  created: [project: ProjectListItem]
}>()

const isOpen = computed({
  get: () => props.open,
  set: (val: boolean) => emit('update:open', val),
})

const form = reactive({
  name: '',
  instructions: '',
})

const creating = ref(false)

async function handleCreate() {
  const name = form.name.trim()
  if (!name || creating.value) return

  creating.value = true
  try {
    const project = await projectsApi.createProject({
      name,
      instructions: form.instructions,
    })
    emit('created', {
      id: project.id,
      name: project.name,
      status: project.status,
      session_count: project.session_count,
      updated_at: project.updated_at,
    })
    // Reset form
    form.name = ''
    form.instructions = ''
    isOpen.value = false
  } catch {
    // Error handling — could add toast notification later
  } finally {
    creating.value = false
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 100;
  animation: fadeIn 0.15s ease;
}

.modal-content {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 101;
  width: min(520px, calc(100vw - 32px));
  max-height: calc(100dvh - 64px);
  overflow-y: auto;
  background: var(--background-main, #ffffff);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15), 0 0 0 1px rgba(0, 0, 0, 0.05);
  padding: 24px;
  animation: modalSlideIn 0.2s ease;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.modal-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.modal-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.15s ease;
}
.modal-close:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

.modal-icon-wrapper {
  display: flex;
  justify-content: center;
  margin-bottom: 24px;
}

.modal-icon-circle {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--fill-tsp-gray-main, #f0f0f0);
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.form-label-optional {
  font-weight: 400;
  color: var(--text-tertiary);
}

.input-wrapper {
  position: relative;
}

.form-input {
  width: 100%;
  height: 44px;
  padding: 0 36px 0 14px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: var(--fill-tsp-gray-main, #f5f5f5);
  font-size: 14px;
  color: var(--text-primary);
  outline: none;
  transition: all 0.15s ease;
}
.form-input:focus {
  border-color: var(--border-main);
  background: var(--background-main, #ffffff);
}
.form-input::placeholder {
  color: var(--text-tertiary);
}

.input-clear {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 2px;
  border-radius: 50%;
}
.input-clear:hover {
  color: var(--text-secondary);
}

.form-textarea {
  width: 100%;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: var(--fill-tsp-gray-main, #f5f5f5);
  font-size: 14px;
  color: var(--text-primary);
  outline: none;
  resize: vertical;
  min-height: 120px;
  font-family: inherit;
  line-height: 1.5;
  transition: all 0.15s ease;
}
.form-textarea:focus {
  border-color: var(--border-main);
  background: var(--background-main, #ffffff);
}
.form-textarea::placeholder {
  color: var(--text-tertiary);
}

.connectors-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid var(--border-light);
}

.connectors-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
}

.connectors-add-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: all 0.15s ease;
}
.connectors-add-btn:hover:not(:disabled) {
  background: var(--fill-tsp-gray-main);
}
.connectors-add-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.btn-cancel {
  height: 40px;
  padding: 0 20px;
  border-radius: 10px;
  border: 1px solid var(--border-main);
  background: var(--background-main, #ffffff);
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.btn-cancel:hover {
  background: var(--fill-tsp-gray-main);
}

.btn-create {
  height: 40px;
  padding: 0 24px;
  border-radius: 10px;
  border: none;
  background: var(--text-primary, #1a1a1a);
  color: var(--background-main, #ffffff);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.btn-create:hover:not(:disabled) {
  opacity: 0.85;
}
.btn-create:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes modalSlideIn {
  from {
    opacity: 0;
    transform: translate(-50%, -48%);
  }
  to {
    opacity: 1;
    transform: translate(-50%, -50%);
  }
}
</style>
