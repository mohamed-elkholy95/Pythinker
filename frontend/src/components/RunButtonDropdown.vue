<template>
  <div class="run-button-group" @click.stop>
    <!-- Primary Run Button -->
    <button @click="$emit('run')" class="run-btn-primary">
      <Play :size="14" />
      <span>Run</span>
    </button>

    <!-- Chevron Dropdown -->
    <Popover v-model:open="dropdownOpen">
      <PopoverTrigger as-child>
        <button class="run-btn-chevron">
          <ChevronDown :size="12" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" :side-offset="8" class="run-dropdown">
        <div class="dropdown-item" @click="handleToggleAutoRun">
          <div class="check-icon-wrapper">
            <Check v-if="autoRun" class="check-icon" :size="14" />
          </div>
          <span>Always run</span>
        </div>
      </PopoverContent>
    </Popover>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Play, ChevronDown, Check } from 'lucide-vue-next'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'

interface Props {
  autoRun: boolean
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'run'): void
  (e: 'toggle-auto-run'): void
}>()

const dropdownOpen = ref(false)

const handleToggleAutoRun = () => {
  emit('toggle-auto-run')
  dropdownOpen.value = false
}
</script>

<style scoped>
.run-button-group {
  display: flex;
  align-items: stretch;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.run-btn-primary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: white;
  font-size: 13px;
  font-weight: 500;
  border: none;
  cursor: pointer;
  transition: all 0.15s ease;
}

.run-btn-primary:hover {
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
}

.run-btn-primary:active {
  transform: scale(0.98);
}

.run-btn-chevron {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px 8px;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  color: white;
  border: none;
  border-left: 1px solid rgba(255, 255, 255, 0.2);
  cursor: pointer;
  transition: all 0.15s ease;
}

.run-btn-chevron:hover {
  background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%);
}

.run-dropdown {
  width: auto !important;
  min-width: 140px;
  padding: 4px;
  border-radius: 10px !important;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--bolt-elements-textPrimary);
  cursor: pointer;
  transition: background 0.15s ease;
}

.dropdown-item:hover {
  background: var(--bolt-elements-bg-depth-2);
}

.check-icon-wrapper {
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.check-icon {
  color: #3b82f6;
}
</style>
