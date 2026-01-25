<template>
  <div v-if="isVisible" class="task-progress-bar flex flex-col gap-4">
    <!-- View Computer Button - shown when collapsed and agent is using computer tools -->
    <button
      v-if="!isExpanded && showThumbnail && !isAllCompleted"
      @click.stop="emit('openPanel')"
      class="px-5 py-2.5 bg-[var(--Button-primary-black)] text-[var(--text-onblack)] rounded-full text-sm font-medium hover:opacity-90 transition-opacity flex items-center gap-2 self-start"
    >
      {{ $t("View Pythinker's computer") }}
    </button>

    <!-- Collapsed View -->
    <div
      v-if="!isExpanded"
      class="flex items-center cursor-pointer"
      @click="toggleExpand"
    >
      <!-- Thumbnail -->
      <div v-if="showThumbnail" class="flex-shrink-0 mr-3">
        <div class="w-[120px] h-[75px] rounded-lg overflow-hidden border border-black/8 bg-[#f0f0ef]">
          <img
            v-if="thumbnailUrl"
            :src="thumbnailUrl"
            alt="Computer view"
            class="w-full h-full object-cover"
          />
          <div v-else class="w-full h-full flex items-center justify-center">
            <div class="terminal-preview">
              <div class="terminal-line"></div>
              <div class="terminal-line short"></div>
              <div class="terminal-line"></div>
              <div class="terminal-cursor"></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Main Card (white wrapper + grey inner) -->
      <div class="p-2 bg-white dark:bg-[var(--background-menu-white)] rounded-2xl flex-1 shadow-sm border border-black/5">
        <div class="flex items-center gap-3 py-3 px-4 bg-[#f5f5f4] dark:bg-[var(--fill-tsp-white-main)] rounded-xl hover:bg-[#eeeeec] transition-colors">
          <!-- Status indicator + Task description -->
          <div class="flex items-center gap-2.5 flex-1 min-w-0">
            <div v-if="isAllCompleted" class="flex-shrink-0">
              <Check class="w-[16px] h-[16px] text-[#22c55e]" :stroke-width="2.5" />
            </div>
            <div v-else class="thinking-shape small" :class="currentShape"></div>
            <span class="text-[15px] font-medium text-[var(--text-primary)]">{{ currentTaskDescription }}</span>
          </div>

          <!-- Progress and Chevron -->
          <div class="flex items-center gap-2 flex-shrink-0">
            <span class="text-sm text-[var(--text-tertiary)]">{{ progressText }}</span>
            <ChevronUp class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </div>
        </div>
      </div>
    </div>

    <!-- Expanded View -->
    <template v-else>
      <!-- Computer Preview Section (no card background, just flex layout) -->
      <div
        v-if="showThumbnail"
        class="flex items-start gap-4 mb-2"
      >
        <!-- Thumbnail -->
        <div class="flex-shrink-0">
          <div class="w-[120px] h-[75px] rounded-lg overflow-hidden border border-black/8 bg-[#f0f0ef]">
            <img
              v-if="thumbnailUrl"
              :src="thumbnailUrl"
              alt="Computer view"
              class="w-full h-full object-cover"
            />
            <div v-else class="w-full h-full flex items-center justify-center">
              <div class="terminal-preview">
                <div class="terminal-line"></div>
                <div class="terminal-line short"></div>
                <div class="terminal-line"></div>
                <div class="terminal-cursor"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- Computer Info -->
        <div class="flex-1 min-w-0 flex flex-col gap-1.5 pt-0.5">
          <h3 class="text-lg font-semibold text-[var(--text-primary)] leading-tight">{{ $t("Pythinker's computer") }}</h3>
          <div v-if="currentTool && !isAllCompleted" class="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <div class="w-6 h-6 rounded-md bg-[#eaeaea] flex items-center justify-center">
              <component :is="getToolIcon(currentTool.name)" class="w-3.5 h-3.5 text-[var(--text-secondary)]" />
            </div>
            <span>{{ $t('Pythinker is using') }} {{ currentTool.function }}</span>
          </div>
        </div>

        <!-- Monitor Icon + Chevron -->
        <div class="flex items-center gap-1 flex-shrink-0">
          <Monitor class="w-5 h-5 text-[var(--icon-tertiary)]" />
          <button
            @click.stop="toggleExpand"
            class="p-0.5 rounded hover:bg-black/5 cursor-pointer"
          >
            <ChevronDown class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </button>
        </div>
      </div>

      <!-- Task Progress Card (white wrapper + grey inner card) -->
      <div class="p-2 bg-white dark:bg-[var(--background-menu-white)] rounded-2xl shadow-sm border border-black/5">
        <div class="px-5 py-4 bg-[#f5f5f4] dark:bg-[var(--fill-tsp-white-main)] rounded-xl">
          <!-- Header -->
          <div
            class="flex items-center justify-between mb-2 cursor-pointer"
            @click="toggleExpand"
          >
            <h3 class="text-[15px] font-bold text-[var(--text-primary)]">{{ $t('Task progress') }}</h3>
            <div class="flex items-center gap-2">
              <span class="text-sm text-[var(--text-tertiary)]">{{ progressText }}</span>
              <ChevronDown class="w-4 h-4 text-[var(--icon-tertiary)]" />
            </div>
          </div>

          <!-- Task List -->
          <div class="flex flex-col">
            <div v-for="(step, index) in steps" :key="step.id" class="flex items-start gap-3 py-2.5">
              <!-- Step Indicator -->
              <div class="flex-shrink-0 mt-0.5">
                <Check v-if="step.status === 'completed'" class="w-[16px] h-[16px] text-[#22c55e]" :stroke-width="2.5" />
                <div v-else-if="step.status === 'running'" class="thinking-shape small" :class="currentShape"></div>
                <div v-else class="w-[16px] h-[16px] rounded-full border-2 border-[var(--border-dark)]"></div>
              </div>

              <!-- Step Content -->
              <div class="flex-1 min-w-0">
                <span
                  class="text-[15px] leading-snug"
                  :class="step.status === 'running' ? 'text-[var(--text-primary)] font-medium' : 'text-[var(--text-primary)]'"
                >
                  {{ step.description }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { ChevronUp, ChevronDown, Check, Monitor, Terminal, Globe, FolderOpen } from 'lucide-vue-next'
import type { PlanEventData } from '@/types/event'

interface Props {
  plan?: PlanEventData
  isLoading: boolean
  isThinking: boolean
  showThumbnail?: boolean
  thumbnailUrl?: string
  currentTool?: { name: string; function: string; functionArg?: string } | null
}

const props = withDefaults(defineProps<Props>(), {
  showThumbnail: false,
  thumbnailUrl: '',
  currentTool: null
})

const emit = defineEmits<{
  (e: 'openPanel'): void
}>()

const isExpanded = ref(false)

// Morphing shape animation
const shapes = ['circle', 'diamond', 'cube'] as const
type Shape = typeof shapes[number]
const currentShapeIndex = ref(0)
const currentShape = ref<Shape>('circle')
let shapeIntervalId: ReturnType<typeof setInterval> | null = null

// Check if all steps are completed
const isAllCompleted = computed(() => {
  return steps.value.length > 0 && steps.value.every(s => s.status === 'completed')
})

const isVisible = computed(() => {
  return props.plan && props.plan.steps.length > 0 && (props.isLoading || isAllCompleted.value)
})

const steps = computed(() => props.plan?.steps ?? [])

const progressText = computed(() => {
  const completed = steps.value.filter(s => s.status === 'completed').length
  const total = steps.value.length
  return `${completed} / ${total}`
})

const currentTaskDescription = computed(() => {
  const runningStep = steps.value.find(s => s.status === 'running')
  if (runningStep) return runningStep.description

  const pendingStep = steps.value.find(s => s.status === 'pending')
  if (pendingStep) return pendingStep.description

  if (isAllCompleted.value && steps.value.length > 0) {
    return steps.value[steps.value.length - 1].description
  }

  return 'Processing...'
})

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

// Get icon for tool type
const getToolIcon = (toolName: string) => {
  if (toolName.includes('browser') || toolName.includes('web')) return Globe
  if (toolName.includes('file') || toolName.includes('folder')) return FolderOpen
  return Terminal
}

const startShapeAnimation = () => {
  if (shapeIntervalId) return
  shapeIntervalId = setInterval(() => {
    currentShapeIndex.value = (currentShapeIndex.value + 1) % shapes.length
    currentShape.value = shapes[currentShapeIndex.value]
  }, 800)
}

const stopShapeAnimation = () => {
  if (shapeIntervalId) {
    clearInterval(shapeIntervalId)
    shapeIntervalId = null
  }
}

// Start/stop shape animation based on thinking state
watch(() => props.isThinking, (thinking) => {
  if (thinking) {
    startShapeAnimation()
  } else {
    stopShapeAnimation()
  }
}, { immediate: true })

onMounted(() => {
  if (props.isThinking) {
    startShapeAnimation()
  }
})

onUnmounted(() => {
  stopShapeAnimation()
})
</script>

<style scoped>
.thinking-shape {
  width: 14px;
  height: 14px;
  background: linear-gradient(135deg, #22c55e 0%, #4ade80 50%, #22c55e 100%);
  background-size: 200% 200%;
  animation: shimmer 1.5s ease-in-out infinite;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
}

.thinking-shape.small {
  width: 12px;
  height: 12px;
}

/* Circle */
.thinking-shape.circle {
  border-radius: 50%;
}

/* Diamond */
.thinking-shape.diamond {
  border-radius: 2px;
  transform: rotate(45deg) scale(0.85);
}

/* Cube */
.thinking-shape.cube {
  border-radius: 2px;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

/* Terminal preview animation */
.terminal-preview {
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  height: 100%;
  justify-content: center;
}

.terminal-line {
  height: 8px;
  background: var(--fill-tsp-gray-dark);
  border-radius: 2px;
  width: 80%;
  animation: terminal-type 2s ease-in-out infinite;
}

.terminal-line.short {
  width: 50%;
  animation-delay: 0.3s;
}

.terminal-cursor {
  width: 10px;
  height: 12px;
  background: var(--text-brand);
  border-radius: 1px;
  animation: cursor-blink 1s step-end infinite;
}

@keyframes terminal-type {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.7; }
}

@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
