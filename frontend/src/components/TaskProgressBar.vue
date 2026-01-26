<template>
  <div v-if="isVisible" class="task-progress-bar">
    <!-- Collapsed View - Task Summary Bar -->
    <div v-if="!isExpanded" class="relative">
      <!-- Floating Terminal Thumbnail -->
      <div
        v-if="showCollapsedThumbnail"
        class="absolute -top-14 left-3 z-20 flex-shrink-0 group/thumb"
      >
        <!-- View Computer Badge - shows on hover -->
        <div
          @click.stop="emit('openPanel')"
          class="absolute -top-10 left-1/2 -translate-x-1/2 inline-flex items-center gap-1.5 px-4 py-2 bg-[var(--Button-primary-black)] text-[var(--text-onblack)] rounded-full text-sm font-medium cursor-pointer opacity-0 group-hover/thumb:opacity-100 transition-opacity duration-200 whitespace-nowrap shadow-lg z-20"
        >
          {{ $t("View Pythinker's computer") }}
        </div>
        <div
          class="w-[140px] h-[88px] sm:w-[150px] sm:h-[96px] rounded-xl overflow-hidden border border-black/8 dark:border-[var(--border-main)] bg-[var(--background-menu-white)] cursor-pointer group-hover/thumb:border-[var(--text-brand)] transition-colors shadow-md"
          @click.stop="emit('openPanel')"
        >
          <!-- Live VNC View -->
          <div
            v-if="showShellPreview"
            class="w-full h-full bg-[var(--background-white-main)] text-[7px] leading-tight font-mono text-[var(--text-secondary)] p-2"
          >
            <div v-for="(line, index) in shellPreviewLines" :key="index">
              <template v-if="line.type === 'prompt'">
                <span class="text-green-600">{{ line.ps1 }}</span>
                <span class="text-[var(--text-primary)]"> {{ line.command }}</span>
              </template>
              <template v-else>
                <span class="text-gray-500">{{ line.text }}</span>
              </template>
            </div>
          </div>
          <VNCViewer
            v-else-if="showVncPreview"
            :session-id="sessionId"
            :enabled="true"
            :view-only="true"
            class="w-full h-full vnc-thumbnail"
          />
          <!-- Static Screenshot -->
          <img
            v-else-if="thumbnailUrl"
            :src="thumbnailUrl"
            alt="Computer view"
            class="w-full h-full object-cover"
          />
          <!-- Terminal Placeholder -->
          <div v-else class="w-full h-full bg-[#1a1a1a] flex flex-col p-2">
            <div class="text-[8px] text-gray-500 text-center mb-1">main</div>
            <div class="terminal-text">
              <div class="text-[7px] leading-tight">
                <span class="text-green-500">ubuntu@sandbox:~$</span>
                <span class="text-gray-300"> cd /home/ubuntu</span>
              </div>
              <div class="text-[7px] leading-tight text-gray-400">Executing task...</div>
              <div class="text-[7px] leading-tight">
                <span class="text-green-500">ubuntu@sandbox:~$</span>
                <span class="terminal-cursor"></span>
              </div>
            </div>
          </div>
        </div>
        <!-- Expand Button -->
        <button
          @click.stop="emit('openPanel')"
          class="absolute bottom-1.5 right-1.5 w-6 h-6 rounded-md bg-[#4a4a4a]/80 hover:bg-[#5a5a5a] flex items-center justify-center transition-colors opacity-0 group-hover/thumb:opacity-100"
        >
          <ArrowUpRight class="w-3.5 h-3.5 text-white" />
        </button>
      </div>

      <div
        class="bg-[var(--background-menu-white)] rounded-2xl border border-black/8 dark:border-[var(--border-main)] shadow-[0px_0px_1px_0px_rgba(0,_0,_0,_0.05),_0px_8px_32px_0px_rgba(0,_0,_0,_0.04)] p-3 sm:p-4 flex items-center gap-3 clickable"
        :class="showCollapsedThumbnail ? 'pl-[176px] sm:pl-[188px]' : ''"
        @click="toggleExpand"
      >
        <!-- Status Indicator -->
        <div class="flex items-center gap-2.5 flex-1 min-w-0">
          <div v-if="isAllCompleted" class="flex-shrink-0">
            <Check class="w-4 h-4 text-[#22c55e]" :stroke-width="2.5" />
          </div>
          <div v-else class="thinking-shape small" :class="currentShape"></div>
          <span class="text-sm text-[var(--text-primary)] truncate">{{ currentTaskDescription }}</span>
        </div>

        <!-- Progress Indicator -->
        <div class="flex items-center gap-2 flex-shrink-0">
          <span class="text-xs text-[var(--text-tertiary)]">{{ progressText }}</span>
          <button @click.stop="toggleExpand" class="p-0.5 hover:bg-[var(--fill-tsp-gray-main)] rounded cursor-pointer">
            <ChevronUp class="w-4 h-4 text-[var(--icon-tertiary)]" />
          </button>
        </div>
      </div>
    </div>

    <!-- Expanded View -->
    <div
      v-else
      class="flex flex-col gap-4 rounded-3xl border border-black/8 dark:border-[var(--border-main)] bg-[var(--background-menu-white)] shadow-[0px_0px_1px_0px_rgba(0,_0,_0,_0.05),_0px_8px_32px_0px_rgba(0,_0,_0,_0.04)] p-5 sm:p-6"
    >
      <!-- Header Section - always show for collapse control -->
      <div class="flex flex-col sm:flex-row sm:items-start gap-4">
        <!-- Terminal Thumbnail Card - only when available -->
        <div v-if="showThumbnail || thumbnailUrl || sessionId" class="flex-shrink-0 relative group/thumb">
          <!-- View Computer Badge - shows on hover -->
          <div
            @click.stop="emit('openPanel')"
            class="absolute -top-10 left-1/2 -translate-x-1/2 inline-flex items-center gap-1.5 px-4 py-2 bg-[var(--Button-primary-black)] text-[var(--text-onblack)] rounded-full text-sm font-medium cursor-pointer opacity-0 group-hover/thumb:opacity-100 transition-opacity duration-200 whitespace-nowrap shadow-lg z-20"
          >
            {{ $t("View Pythinker's computer") }}
          </div>
          <div
            class="w-[140px] h-[88px] sm:w-[150px] sm:h-[96px] rounded-xl overflow-hidden border border-black/8 dark:border-[var(--border-main)] bg-[var(--background-menu-white)] cursor-pointer group-hover/thumb:border-[var(--text-brand)] transition-colors shadow-md"
            @click.stop="emit('openPanel')"
          >
            <!-- Live VNC View -->
            <div
              v-if="showShellPreview"
              class="w-full h-full bg-[var(--background-white-main)] text-[8px] leading-tight font-mono text-[var(--text-secondary)] p-3"
            >
              <div v-for="(line, index) in shellPreviewLines" :key="index">
                <template v-if="line.type === 'prompt'">
                  <span class="text-green-600">{{ line.ps1 }}</span>
                  <span class="text-[var(--text-primary)]"> {{ line.command }}</span>
                </template>
                <template v-else>
                  <span class="text-gray-500">{{ line.text }}</span>
                </template>
              </div>
            </div>
            <VNCViewer
              v-else-if="showVncPreview"
              :session-id="sessionId"
              :enabled="true"
              :view-only="true"
              class="w-full h-full vnc-thumbnail"
            />
            <!-- Static Screenshot -->
            <img
              v-else-if="thumbnailUrl"
              :src="thumbnailUrl"
              alt="Computer view"
              class="w-full h-full object-cover"
            />
            <!-- Terminal Placeholder -->
            <div v-else class="w-full h-full bg-[#1a1a1a] flex flex-col p-3">
              <div class="text-[9px] text-gray-500 text-center mb-1.5">main</div>
              <div class="terminal-text flex-1">
                <div class="text-[8px] leading-relaxed">
                  <span class="text-green-500">ubuntu@sandbox:~$</span>
                  <span class="text-gray-300"> cd /home/ubuntu && g</span>
                </div>
                <div class="text-[8px] leading-relaxed text-gray-300">h repo clone project.git</div>
                <div class="text-[8px] leading-relaxed text-gray-400">GraphQL: Could not resolve</div>
                <div class="text-[8px] leading-relaxed text-gray-400">ory with the name 'project'</div>
                <div class="text-[8px] leading-relaxed">
                  <span class="text-green-500">ubuntu@sandbox:~$</span>
                  <span class="terminal-cursor"></span>
                </div>
              </div>
            </div>
          </div>
          <!-- Expand Button -->
          <button
            @click.stop="emit('openPanel')"
            class="absolute bottom-2 right-2 w-7 h-7 rounded-lg bg-[#4a4a4a]/80 hover:bg-[#5a5a5a] flex items-center justify-center transition-colors"
          >
            <ArrowUpRight class="w-4 h-4 text-white" />
          </button>
        </div>

        <!-- Computer Info -->
        <div class="flex-1 min-w-0">
          <div class="flex items-start justify-between gap-4">
            <h2 class="text-lg sm:text-xl font-semibold text-[var(--text-primary)]">
              {{ $t("Pythinker's computer") }}
            </h2>
            <div class="flex items-center gap-3 flex-shrink-0 pt-0.5">
              <button
                type="button"
                @click.stop="emit('openPanel')"
                class="w-9 h-9 rounded-lg border border-black/10 dark:border-[var(--border-main)] bg-[var(--background-white-main)] flex items-center justify-center shadow-sm hover:bg-[var(--fill-tsp-gray-main)] cursor-pointer"
                aria-label="Open Pythinker's computer"
              >
                <Monitor class="w-5 h-5 text-[var(--icon-secondary)]" />
              </button>
              <button
                @click="toggleExpand"
                class="p-1 hover:bg-[var(--fill-tsp-gray-main)] rounded cursor-pointer"
              >
                <ChevronDown class="w-5 h-5 text-[var(--icon-tertiary)]" />
              </button>
            </div>
          </div>
          <div class="flex items-center gap-3 text-[var(--text-secondary)] mt-2">
            <div class="w-9 h-9 rounded-lg border border-black/10 dark:border-[var(--border-main)] bg-[var(--background-white-main)] flex items-center justify-center shadow-sm">
              <component :is="currentToolIcon" class="w-[18px] h-[18px] text-[var(--text-secondary)]" />
            </div>
            <span class="text-xs sm:text-sm">
              <span v-if="isAllCompleted" class="font-medium text-[var(--text-primary)]">
                {{ currentToolName }}
              </span>
              <span v-else>
                {{ $t('Pythinker is using') }}
                <span class="font-medium text-[var(--text-primary)]">{{ currentToolName }}</span>
              </span>
            </span>
          </div>
        </div>
      </div>

      <!-- Task Progress Card -->
      <div class="bg-[var(--fill-tsp-gray-main)] rounded-2xl p-5 sm:p-6 border border-black/5 dark:border-[var(--border-main)]">
        <!-- Card Header -->
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm sm:text-base font-semibold text-[var(--text-primary)]">{{ $t('Task progress') }}</h3>
          <span class="text-xs text-[var(--text-tertiary)]">{{ progressText }}</span>
        </div>

        <!-- Task List -->
        <div class="flex flex-col">
          <div
            v-for="(step, index) in steps"
            :key="step.id"
            class="flex items-start gap-2.5 py-2.5"
          >
            <!-- Checkmark -->
            <div class="flex-shrink-0 mt-0.5">
              <Check
                v-if="step.status === 'completed'"
                class="w-3.5 h-3.5 text-[#22c55e]"
                :stroke-width="2.5"
              />
              <div v-else-if="step.status === 'running'" class="thinking-shape small" :class="currentShape"></div>
              <div v-else class="w-3.5 h-3.5 rounded-full border-2 border-gray-300"></div>
            </div>

            <!-- Task Text -->
            <span
              class="text-xs sm:text-sm leading-relaxed"
              :class="step.status === 'running' ? 'text-[var(--text-primary)] font-semibold' : 'text-[var(--text-primary)] font-medium'"
            >
              {{ step.description }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { ChevronUp, ChevronDown, Check, Monitor, Terminal, Globe, FolderOpen, ArrowUpRight } from 'lucide-vue-next'
import type { PlanEventData } from '@/types/event'
import type { ToolContent } from '@/types/message'
import VNCViewer from '@/components/VNCViewer.vue'

interface Props {
  plan?: PlanEventData
  isLoading: boolean
  isThinking: boolean
  showThumbnail?: boolean
  thumbnailUrl?: string
  currentTool?: { name: string; function: string; functionArg?: string } | null
  toolContent?: ToolContent | null
  sessionId?: string
  liveVnc?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showThumbnail: false,
  thumbnailUrl: '',
  currentTool: null,
  sessionId: '',
  liveVnc: false
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

const thumbnailToolName = computed(() => {
  if (props.toolContent?.name) return props.toolContent.name
  if (props.currentTool?.name) return props.currentTool.name
  return ''
})

const shellPreviewLines = computed(() => {
  if (!thumbnailToolName.value.includes('shell')) return []
  const consoleEntries = props.toolContent?.content?.console
  if (!Array.isArray(consoleEntries)) return []
  const lines: Array<{ type: 'prompt'; ps1: string; command: string } | { type: 'output'; text: string }> = []
  for (const entry of consoleEntries) {
    const ps1 = typeof entry?.ps1 === 'string' ? entry.ps1 : ''
    const command = typeof entry?.command === 'string' ? entry.command : ''
    if (ps1 || command) {
      lines.push({ type: 'prompt', ps1, command })
    }
    const output = typeof entry?.output === 'string' ? entry.output : ''
    if (output) {
      output.split('\n').forEach((line: string) => {
        if (line.trim().length > 0) {
          lines.push({ type: 'output', text: line })
        }
      })
    }
  }
  return lines.slice(-4)
})

const showShellPreview = computed(() => shellPreviewLines.value.length > 0)
const showVncPreview = computed(() => !!props.sessionId && !showShellPreview.value)

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

const showCollapsedThumbnail = computed(() => {
  return props.showThumbnail || (isAllCompleted.value && !!props.thumbnailUrl)
})

// Get current tool name for display
const currentToolName = computed(() => {
  if (isAllCompleted.value) return 'Task completed'
  if (props.currentTool?.function) return props.currentTool.function
  return 'Terminal'
})

// Get icon for current tool
const currentToolIcon = computed(() => {
  if (isAllCompleted.value) return Check
  const toolName = props.currentTool?.name || ''
  if (toolName.includes('browser') || toolName.includes('web')) return Globe
  if (toolName.includes('file') || toolName.includes('folder')) return FolderOpen
  return Terminal
})

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
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
/* Thinking shape animation */
.thinking-shape {
  width: 16px;
  height: 16px;
  background: linear-gradient(135deg, #22c55e 0%, #4ade80 50%, #22c55e 100%);
  background-size: 200% 200%;
  animation: shimmer 1.5s ease-in-out infinite;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
}

.thinking-shape.small {
  width: 14px;
  height: 14px;
}

.thinking-shape.circle {
  border-radius: 50%;
}

.thinking-shape.diamond {
  border-radius: 2px;
  transform: rotate(45deg) scale(0.85);
}

.thinking-shape.cube {
  border-radius: 3px;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Terminal cursor blink */
.terminal-cursor {
  display: inline-block;
  width: 6px;
  height: 10px;
  background: #22c55e;
  animation: cursor-blink 1s step-end infinite;
  margin-left: 2px;
  vertical-align: middle;
}

@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* VNC Thumbnail scaling */
.vnc-thumbnail :deep(canvas) {
  width: 100% !important;
  height: 100% !important;
  object-fit: cover;
  cursor: pointer !important;
  pointer-events: none;
  margin: 0 !important;
  display: block;
}

.vnc-thumbnail {
  cursor: pointer;
  pointer-events: none;
  border-radius: 12px;
  overflow: hidden;
}

.vnc-thumbnail :deep(.vnc-container),
.vnc-thumbnail :deep(.vnc-container > div) {
  width: 100% !important;
  height: 100% !important;
  margin: 0 !important;
  display: block;
}
</style>
