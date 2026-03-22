<template>
  <DialogRoot v-model:open="isOpen">
    <DialogPortal>
      <DialogOverlay class="modal-overlay" />
      <DialogContent class="modal-content">
        <!-- Header -->
        <div class="modal-header">
          <DialogTitle class="modal-title">Add skills to project</DialogTitle>
          <DialogClose class="modal-close" aria-label="Close">
            <X :size="20" />
          </DialogClose>
        </div>

        <p class="modal-desc">
          Select skills to enhance Pythinker's capabilities for tasks in this project.
        </p>

        <!-- Search -->
        <div class="modal-search">
          <Search :size="16" class="search-icon" />
          <input
            v-model="searchQuery"
            type="text"
            class="search-input"
            placeholder="Search skills..."
          />
        </div>

        <!-- Skill list -->
        <div class="skill-list">
          <label
            v-for="skill in filteredSkills"
            :key="skill.id"
            class="skill-item"
          >
            <div class="skill-info">
              <span class="skill-name">{{ skill.name }}</span>
              <span class="skill-desc">{{ skill.description }}</span>
            </div>
            <input
              type="checkbox"
              :checked="selectedIds.has(skill.id)"
              class="skill-checkbox"
              @change="toggleSkill(skill.id)"
            />
          </label>
        </div>

        <!-- Footer -->
        <div class="modal-footer">
          <DialogClose as-child>
            <button class="btn-cancel" type="button">Cancel</button>
          </DialogClose>
          <button class="btn-save" type="button" @click="handleSave">
            Save ({{ selectedIds.size }})
          </button>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  DialogRoot,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogTitle,
  DialogClose,
} from 'reka-ui'
import { X, Search } from 'lucide-vue-next'
import { useSkills } from '@/composables/useSkills'

const props = defineProps<{
  open: boolean
  currentSkillIds: string[]
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  save: [skillIds: string[]]
}>()

const isOpen = computed({
  get: () => props.open,
  set: (val: boolean) => emit('update:open', val),
})

const { availableSkills } = useSkills()
const searchQuery = ref('')
const selectedIds = ref(new Set<string>())

// Sync selected IDs when modal opens
watch(
  () => props.open,
  (opened) => {
    if (opened) {
      selectedIds.value = new Set(props.currentSkillIds)
      searchQuery.value = ''
    }
  },
)

const filteredSkills = computed(() => {
  const q = searchQuery.value.toLowerCase().trim()
  if (!q) return availableSkills.value
  return availableSkills.value.filter(
    (s) => s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q),
  )
})

function toggleSkill(id: string) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function handleSave() {
  emit('save', Array.from(selectedIds.value))
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
  width: min(480px, calc(100vw - 32px));
  max-height: calc(100dvh - 64px);
  background: var(--background-main, #ffffff);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15), 0 0 0 1px rgba(0, 0, 0, 0.05);
  padding: 24px;
  display: flex;
  flex-direction: column;
  animation: modalSlideIn 0.2s ease;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.modal-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
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

.modal-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 16px;
  line-height: 1.5;
}

.modal-search {
  position: relative;
  margin-bottom: 12px;
}

.search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-tertiary);
}

.search-input {
  width: 100%;
  height: 40px;
  padding: 0 12px 0 36px;
  border-radius: 10px;
  border: 1px solid var(--border-light, var(--border-main));
  background: var(--fill-tsp-gray-main, #f5f5f5);
  font-size: 14px;
  color: var(--text-primary);
  outline: none;
  font-family: inherit;
}

.search-input:focus {
  border-color: var(--border-main);
}

.skill-list {
  flex: 1;
  overflow-y: auto;
  max-height: 320px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 16px;
}

.skill-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.12s;
}

.skill-item:hover {
  background: var(--fill-tsp-gray-main);
}

.skill-info {
  flex: 1;
  min-width: 0;
}

.skill-name {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.skill-desc {
  display: block;
  font-size: 12px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-checkbox {
  width: 18px;
  height: 18px;
  accent-color: var(--text-primary);
  cursor: pointer;
  flex-shrink: 0;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.btn-cancel {
  height: 38px;
  padding: 0 18px;
  border-radius: 10px;
  border: 1px solid var(--border-main);
  background: transparent;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-cancel:hover {
  background: var(--fill-tsp-gray-main);
}

.btn-save {
  height: 38px;
  padding: 0 20px;
  border-radius: 10px;
  border: none;
  background: var(--text-primary, #1a1a1a);
  color: var(--background-main, #ffffff);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-save:hover {
  opacity: 0.85;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
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
