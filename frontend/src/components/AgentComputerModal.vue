<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div v-if="isOpen" class="modal-backdrop" @click.self="closeModal">
        <AgentComputerView
          :session-id="sessionId"
          :agent-name="agentName"
          :current-tool="currentTool"
          :task-title="taskTitle"
          :task-time="taskTime"
          :task-status="taskStatus"
          :task-steps="taskSteps"
          :live="live"
          @close="closeModal"
          @fullscreen="toggleFullscreen"
          @task-details-toggle="handleTaskDetailsToggle"
        />
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import AgentComputerView from './AgentComputerView.vue';
import type { ToolContent } from '@/types/message';

const props = defineProps<{
  modelValue: boolean;
  sessionId: string;
  agentName?: string;
  currentTool?: ToolContent;
  taskTitle?: string;
  taskTime?: string;
  taskStatus?: string;
  taskSteps?: string;
  live?: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  fullscreen: [];
  taskDetailsToggle: [show: boolean];
}>();

const isOpen = ref(props.modelValue);

watch(() => props.modelValue, (value) => {
  isOpen.value = value;
  if (value) {
    document.body.style.overflow = 'hidden';
  } else {
    document.body.style.overflow = '';
  }
});

const closeModal = () => {
  isOpen.value = false;
  emit('update:modelValue', false);
  document.body.style.overflow = '';
};

const toggleFullscreen = () => {
  emit('fullscreen');
};

const handleTaskDetailsToggle = (show: boolean) => {
  emit('taskDetailsToggle', show);
};

// Handle escape key
const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && isOpen.value) {
    closeModal();
  }
};

// Listen for escape key
if (typeof window !== 'undefined') {
  window.addEventListener('keydown', handleKeydown);
}
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-center;
  z-index: 9999;
  padding: 20px;
  overflow-y: auto;
}

.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.3s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-active .agent-computer-container,
.modal-fade-leave-active .agent-computer-container {
  transition: transform 0.3s ease;
}

.modal-fade-enter-from .agent-computer-container,
.modal-fade-leave-to .agent-computer-container {
  transform: scale(0.95);
}
</style>
