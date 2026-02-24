<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue'

export type ReasoningStage = 'parsing' | 'intent' | 'retrieval' | 'planning' | 'generation' | 'quality_checking' | 'completed' | 'idle'

interface Props {
  currentStage: ReasoningStage
}

const props = defineProps<Props>()

interface StageNode {
  key: ReasoningStage
  label: string
  sublabel: string
  glyph: string
  color: string
  glowColor: string
}

const NODES: StageNode[] = [
  { key: 'parsing',         label: 'Parse',    sublabel: 'Tokenization · NER',         glyph: '⌥', color: '#6366f1', glowColor: 'rgba(99,102,241,0.35)' },
  { key: 'intent',          label: 'Intent',   sublabel: 'Context · Disambiguation',   glyph: '⊛', color: '#8b5cf6', glowColor: 'rgba(139,92,246,0.35)' },
  { key: 'retrieval',       label: 'Retrieve', sublabel: 'Knowledge · RAG',            glyph: '⊕', color: '#3b82f6', glowColor: 'rgba(59,130,246,0.35)' },
  { key: 'planning',        label: 'Plan',     sublabel: 'Structure · Reasoning',      glyph: '⋈', color: '#0ea5e9', glowColor: 'rgba(14,165,233,0.35)' },
  { key: 'generation',      label: 'Generate', sublabel: 'Synthesis · Coherence',      glyph: '∞', color: '#06b6d4', glowColor: 'rgba(6,182,212,0.35)' },
  { key: 'quality_checking',label: 'Verify',   sublabel: 'Safety · Accuracy',          glyph: '✦', color: '#10b981', glowColor: 'rgba(16,185,129,0.35)' },
]

const currentIndex = computed(() => {
  if (props.currentStage === 'completed') return NODES.length
  const idx = NODES.findIndex(s => s.key === props.currentStage)
  return idx === -1 ? 0 : idx
})

const getNodeState = (index: number): 'completed' | 'active' | 'pending' => {
  if (index < currentIndex.value) return 'completed'
  if (index === currentIndex.value) return 'active'
  return 'pending'
}

// SVG canvas dimensions
const svgWidth = ref(0)
const svgHeight = 72
const containerRef = ref<HTMLElement | null>(null)

// Particle system
interface Particle {
  id: number
  fromIdx: number
  toIdx: number
  progress: number  // 0..1
  speed: number
}

const particles = ref<Particle[]>([])
let particleIdCounter = 0
let animFrame: number | null = null
let particleSpawnTimer: number | null = null

const nodePositions = computed<{ x: number; y: number }[]>(() => {
  if (!svgWidth.value) return []
  const n = NODES.length
  const padding = 40
  const usable = svgWidth.value - padding * 2
  return NODES.map((_, i) => ({
    x: padding + (usable / (n - 1)) * i,
    y: svgHeight / 2,
  }))
})

// Active connection spans (between completed/active nodes)
const activeEdges = computed(() => {
  const edges: { from: number; to: number; active: boolean }[] = []
  for (let i = 0; i < NODES.length - 1; i++) {
    const fromState = getNodeState(i)
    const toState   = getNodeState(i + 1)
    const active = fromState === 'completed' || fromState === 'active'
      || toState === 'active'
    edges.push({ from: i, to: i + 1, active })
  }
  return edges
})

// Wavy SVG path between two x-positions at the same y
function wavePath(x1: number, x2: number, y: number): string {
  const mid = (x1 + x2) / 2
  const amp = 6
  return `M ${x1} ${y} C ${mid - 10} ${y - amp}, ${mid + 10} ${y + amp}, ${x2} ${y}`
}

function spawnParticle() {
  const activeEdgeList = activeEdges.value.filter(e => e.active)
  if (!activeEdgeList.length) return
  const edge = activeEdgeList[Math.floor(Math.random() * activeEdgeList.length)]
  particles.value.push({
    id: particleIdCounter++,
    fromIdx: edge.from,
    toIdx: edge.to,
    progress: 0,
    speed: 0.012 + Math.random() * 0.010,
  })
}

function tick() {
  particles.value = particles.value
    .map(p => ({ ...p, progress: p.progress + p.speed }))
    .filter(p => p.progress < 1.05)
  animFrame = requestAnimationFrame(tick)
}

function particlePosition(p: Particle): { x: number; y: number } | null {
  const positions = nodePositions.value
  if (!positions.length) return null
  const from = positions[p.fromIdx]
  const to   = positions[p.toIdx]
  if (!from || !to) return null
  const t  = Math.min(p.progress, 1)
  const mid = (from.x + to.x) / 2
  const amp = 6
  // Cubic bezier interpolation matching wavePath
  const cx1x = mid - 10, cx1y = from.y - amp
  const cx2x = mid + 10, cx2y = to.y + amp
  const x = Math.pow(1-t,3)*from.x + 3*Math.pow(1-t,2)*t*cx1x + 3*(1-t)*t*t*cx2x + t*t*t*to.x
  const y = Math.pow(1-t,3)*from.y + 3*Math.pow(1-t,2)*t*cx1y + 3*(1-t)*t*t*cx2y + t*t*t*to.y
  return { x, y }
}

function particleColor(p: Particle): string {
  return NODES[p.fromIdx]?.color ?? '#6366f1'
}

function startAnimation() {
  if (animFrame) return
  tick()
  particleSpawnTimer = window.setInterval(spawnParticle, 220)
}

function stopAnimation() {
  if (animFrame) { cancelAnimationFrame(animFrame); animFrame = null }
  if (particleSpawnTimer) { clearInterval(particleSpawnTimer); particleSpawnTimer = null }
  particles.value = []
}

watch(() => props.currentStage, (stage) => {
  if (stage !== 'idle' && stage !== 'completed') {
    startAnimation()
  } else {
    stopAnimation()
  }
}, { immediate: true })

const resizeObserver = ref<ResizeObserver | null>(null)

onMounted(() => {
  resizeObserver.value = new ResizeObserver(entries => {
    for (const entry of entries) {
      svgWidth.value = entry.contentRect.width
    }
  })
  if (containerRef.value) {
    resizeObserver.value.observe(containerRef.value)
    svgWidth.value = containerRef.value.offsetWidth
  }
})

onBeforeUnmount(() => {
  stopAnimation()
  resizeObserver.value?.disconnect()
})
</script>

<template>
  <Transition name="nn-fade">
    <div
      v-if="currentStage !== 'idle' && currentStage !== 'completed'"
      ref="containerRef"
      class="nn-root"
    >
      <!-- Header -->
      <div class="nn-header">
        <span class="nn-dot"></span>
        <span class="nn-title">Chain of Thought</span>
        <span class="nn-stage-badge">{{ NODES[currentIndex]?.label ?? '' }}</span>
      </div>

      <!-- SVG neural network canvas -->
      <div class="nn-canvas-wrap">
        <svg
          v-if="svgWidth > 0"
          :width="svgWidth"
          :height="svgHeight"
          class="nn-svg"
          :viewBox="`0 0 ${svgWidth} ${svgHeight}`"
          overflow="visible"
        >
          <defs>
            <!-- Glow filter for active edges -->
            <filter id="edge-glow" x="-20%" y="-80%" width="140%" height="260%">
              <feGaussianBlur stdDeviation="2.5" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
            <!-- Node glow -->
            <filter id="node-glow" x="-60%" y="-60%" width="220%" height="220%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>

          <!-- Edges -->
          <g v-if="nodePositions.length">
            <path
              v-for="edge in activeEdges"
              :key="`edge-${edge.from}`"
              :d="wavePath(nodePositions[edge.from].x, nodePositions[edge.to].x, svgHeight / 2)"
              fill="none"
              :stroke="edge.active ? NODES[edge.from].color : 'var(--border-main)'"
              :stroke-width="edge.active ? 1.5 : 1"
              :stroke-opacity="edge.active ? 0.55 : 0.22"
              :filter="edge.active ? 'url(#edge-glow)' : undefined"
              stroke-linecap="round"
            />
          </g>

          <!-- Particles -->
          <g v-if="nodePositions.length">
            <template v-for="p in particles" :key="p.id">
              <circle
                v-if="particlePosition(p)"
                :cx="particlePosition(p)!.x"
                :cy="particlePosition(p)!.y"
                r="2.8"
                :fill="particleColor(p)"
                :opacity="0.9 - p.progress * 0.5"
                filter="url(#node-glow)"
              />
            </template>
          </g>

          <!-- Nodes -->
          <g v-if="nodePositions.length">
            <g
              v-for="(node, i) in NODES"
              :key="node.key"
              :transform="`translate(${nodePositions[i].x}, ${nodePositions[i].y})`"
            >
              <!-- Outer glow ring for active node -->
              <circle
                v-if="getNodeState(i) === 'active'"
                r="18"
                :fill="node.glowColor"
                class="nn-active-ring"
              />

              <!-- Node circle -->
              <circle
                r="13"
                :fill="
                  getNodeState(i) === 'completed' ? node.color :
                  getNodeState(i) === 'active'    ? 'var(--background-main)' :
                  'var(--fill-tsp-gray-main)'
                "
                :stroke="getNodeState(i) === 'pending' ? 'var(--border-main)' : node.color"
                :stroke-width="getNodeState(i) === 'active' ? 2 : 1.5"
                :fill-opacity="getNodeState(i) === 'pending' ? 0.4 : 1"
                :filter="getNodeState(i) !== 'pending' ? 'url(#node-glow)' : undefined"
                class="nn-node-circle"
                :class="{ 'nn-node-active': getNodeState(i) === 'active' }"
              />

              <!-- Glyph inside node -->
              <text
                text-anchor="middle"
                dominant-baseline="central"
                :font-size="getNodeState(i) === 'active' ? 11 : 10"
                :fill="
                  getNodeState(i) === 'completed' ? '#fff' :
                  getNodeState(i) === 'active'    ? node.color :
                  'var(--text-tertiary)'
                "
                :font-weight="getNodeState(i) === 'active' ? '700' : '400'"
                style="pointer-events:none;user-select:none;font-family:monospace"
              >{{ node.glyph }}</text>

              <!-- Label below node -->
              <text
                y="22"
                text-anchor="middle"
                dominant-baseline="hanging"
                font-size="9.5"
                :fill="
                  getNodeState(i) === 'active'    ? node.color :
                  getNodeState(i) === 'completed' ? 'var(--text-secondary)' :
                  'var(--text-tertiary)'
                "
                :font-weight="getNodeState(i) === 'active' ? '600' : '400'"
                style="pointer-events:none;user-select:none"
                :opacity="getNodeState(i) === 'pending' ? 0.45 : 1"
              >{{ node.label }}</text>
            </g>
          </g>
        </svg>
      </div>

      <!-- Active stage detail strip -->
      <div class="nn-detail" v-if="currentIndex < NODES.length">
        <span
          class="nn-detail-dot"
          :style="{ background: NODES[currentIndex].color }"
        ></span>
        <span class="nn-detail-text">{{ NODES[currentIndex].sublabel }}</span>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.nn-root {
  position: relative;
  background: var(--background-main, #fff);
  border: 1px solid var(--border-light, rgba(0,0,0,0.07));
  border-radius: 14px;
  padding: 10px 14px 12px;
  margin-bottom: 10px;
  overflow: hidden;
}

/* Subtle grid backdrop */
.nn-root::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(99,102,241,0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(99,102,241,0.04) 1px, transparent 1px);
  background-size: 20px 20px;
  border-radius: inherit;
  pointer-events: none;
}

.nn-header {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 4px;
}

.nn-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #6366f1;
  box-shadow: 0 0 0 0 rgba(99,102,241,0.7);
  animation: nn-pulse 1.8s ease-in-out infinite;
  flex-shrink: 0;
}

@keyframes nn-pulse {
  0%   { box-shadow: 0 0 0 0   rgba(99,102,241,0.7); }
  60%  { box-shadow: 0 0 0 5px rgba(99,102,241,0); }
  100% { box-shadow: 0 0 0 0   rgba(99,102,241,0); }
}

.nn-title {
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-tertiary);
}

.nn-stage-badge {
  margin-left: auto;
  font-size: 10px;
  font-weight: 600;
  color: #6366f1;
  background: rgba(99,102,241,0.08);
  border: 1px solid rgba(99,102,241,0.2);
  border-radius: 99px;
  padding: 1px 8px;
}

.nn-canvas-wrap {
  width: 100%;
  height: 72px;
}

.nn-svg {
  display: block;
  overflow: visible;
}

/* Active node breathing ring */
.nn-active-ring {
  animation: nn-ring-breathe 1.6s ease-in-out infinite;
}

@keyframes nn-ring-breathe {
  0%, 100% { r: 16; opacity: 0.6; }
  50%       { r: 20; opacity: 0.25; }
}

/* Active node border spin */
.nn-node-active {
  animation: nn-node-spin-shadow 2s linear infinite;
}

@keyframes nn-node-spin-shadow {
  0%   { filter: drop-shadow(0 0 4px currentColor); }
  50%  { filter: drop-shadow(0 0 8px currentColor); }
  100% { filter: drop-shadow(0 0 4px currentColor); }
}

.nn-detail {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
  padding-top: 6px;
  border-top: 1px solid var(--border-light, rgba(0,0,0,0.06));
}

.nn-detail-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}

.nn-detail-text {
  font-size: 10px;
  color: var(--text-tertiary);
  letter-spacing: 0.03em;
}

/* Entry/exit transition */
.nn-fade-enter-active,
.nn-fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.nn-fade-enter-from,
.nn-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
