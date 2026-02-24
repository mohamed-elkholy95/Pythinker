<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'

export type ReasoningStage = 'parsing' | 'intent' | 'retrieval' | 'planning' | 'generation' | 'quality_checking' | 'completed' | 'idle'

interface Props {
  currentStage: ReasoningStage
  /** Live streaming thinking text from the agent — shown in expanded view */
  thinkingText?: string
}

const props = defineProps<Props>()

interface StageNode {
  key: ReasoningStage
  label: string
  sublabel: string
  detail: string
  glyph: string
  color: string
  glowColor: string
  layer: number   // 0-based column in expanded layout
  row: number     // 0-based row for multi-row layouts
}

// Expanded: nodes are laid out in a multi-layer neural network topology
// Layer 0: Input  | Layer 1: Hidden-A | Layer 2: Hidden-B | Layer 3: Output
const NODES: StageNode[] = [
  { key: 'parsing',         label: 'Parse',    sublabel: 'Tokenization · NER',          detail: 'Tokenization, Linguistic Analysis, Named Entity Recognition',        glyph: '⌥', color: '#6366f1', glowColor: 'rgba(99,102,241,0.4)',  layer: 0, row: 0 },
  { key: 'intent',          label: 'Intent',   sublabel: 'Context · Disambiguation',    detail: 'Intent Recognition, Context Modeling, Ambiguity Resolution',          glyph: '⊛', color: '#8b5cf6', glowColor: 'rgba(139,92,246,0.4)', layer: 1, row: 0 },
  { key: 'retrieval',       label: 'Retrieve', sublabel: 'Knowledge · RAG',             detail: 'Knowledge Graph Traversal, Document Retrieval, Fact Extraction',      glyph: '⊕', color: '#3b82f6', glowColor: 'rgba(59,130,246,0.4)',  layer: 1, row: 1 },
  { key: 'planning',        label: 'Plan',     sublabel: 'Structure · Reasoning',       detail: 'Content Selection, Argumentation, Structure Determination',           glyph: '⋈', color: '#0ea5e9', glowColor: 'rgba(14,165,233,0.4)', layer: 2, row: 0 },
  { key: 'generation',      label: 'Generate', sublabel: 'Synthesis · Coherence',       detail: 'Sentence Construction, Cohesion, Coherence, Formatting Application',  glyph: '∞', color: '#06b6d4', glowColor: 'rgba(6,182,212,0.4)',   layer: 2, row: 1 },
  { key: 'quality_checking',label: 'Verify',   sublabel: 'Safety · Accuracy',           detail: 'Accuracy Verification, Safety Compliance, Completeness Check',        glyph: '✦', color: '#10b981', glowColor: 'rgba(16,185,129,0.4)', layer: 3, row: 0 },
]

// Sequential order for compact mode & progress tracking
const SEQUENCE: ReasoningStage[] = ['parsing','intent','retrieval','planning','generation','quality_checking']

const isExpanded = ref(false)

const currentIndex = computed(() => {
  if (props.currentStage === 'completed') return SEQUENCE.length
  const idx = SEQUENCE.indexOf(props.currentStage)
  return idx === -1 ? 0 : idx
})

const getNodeState = (nodeIdx: number): 'completed' | 'active' | 'pending' => {
  const seqIdx = SEQUENCE.indexOf(NODES[nodeIdx].key)
  if (seqIdx < currentIndex.value) return 'completed'
  if (seqIdx === currentIndex.value) return 'active'
  return 'pending'
}

const activeNode = computed(() => NODES.find(n => n.key === props.currentStage))

// ─── COMPACT MODE LAYOUT ────────────────────────────────────────────────────
const compactSvgWidth = ref(0)
const compactSvgHeight = 64
const compactContainerRef = ref<HTMLElement | null>(null)

const compactPositions = computed<{ x: number; y: number }[]>(() => {
  if (!compactSvgWidth.value) return []
  const n = NODES.length
  const pad = 36
  const usable = compactSvgWidth.value - pad * 2
  return NODES.map((_, i) => ({
    x: pad + (usable / (n - 1)) * i,
    y: compactSvgHeight / 2,
  }))
})

// ─── EXPANDED MODE LAYOUT ───────────────────────────────────────────────────
const expandedSvgWidth = ref(0)
const expandedSvgHeight = ref(280)
const expandedContainerRef = ref<HTMLElement | null>(null)

const NUM_LAYERS = 4
const expandedPositions = computed<{ x: number; y: number }[]>(() => {
  const w = expandedSvgWidth.value || 600
  const h = expandedSvgHeight.value
  const layerPad = 70
  const usableW = w - layerPad * 2
  const positions: { x: number; y: number }[] = []

  // Count rows per layer
  const rowsPerLayer: Record<number, number> = {}
  for (const n of NODES) {
    rowsPerLayer[n.layer] = Math.max(rowsPerLayer[n.layer] ?? 0, n.row + 1)
  }

  for (const node of NODES) {
    const x = layerPad + (usableW / (NUM_LAYERS - 1)) * node.layer
    const rows = rowsPerLayer[node.layer] ?? 1
    const rowSpacing = rows > 1 ? (h * 0.5) / (rows - 1) : 0
    const startY = h / 2 - (rows - 1) * rowSpacing / 2
    const y = rows > 1 ? startY + node.row * rowSpacing : h / 2
    positions.push({ x, y })
  }
  return positions
})

// Edges: full mesh between adjacent layers (like a real NN)
const expandedEdges = computed(() => {
  const edges: { from: number; to: number }[] = []
  for (let i = 0; i < NODES.length; i++) {
    for (let j = 0; j < NODES.length; j++) {
      if (NODES[j].layer === NODES[i].layer + 1) {
        edges.push({ from: i, to: j })
      }
    }
  }
  return edges
})

function isEdgeActive(edge: { from: number; to: number }): boolean {
  const fs = getNodeState(edge.from)
  const ts = getNodeState(edge.to)
  return fs === 'completed' || fs === 'active' || ts === 'active'
}

function edgeColor(edge: { from: number; to: number }): string {
  if (isEdgeActive(edge)) return NODES[edge.from].color
  return 'var(--border-main)'
}

// ─── WAVE PATH helper ────────────────────────────────────────────────────────
function wavePath(x1: number, y1: number, x2: number, y2: number): string {
  const dx = (x2 - x1) * 0.45
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`
}

// ─── PARTICLE SYSTEM ─────────────────────────────────────────────────────────
interface Particle {
  id: number
  fromIdx: number
  toIdx: number
  progress: number
  speed: number
  size: number
  opacity: number
}

const particles = ref<Particle[]>([])
let pidCounter = 0
let raf: number | null = null
let spawnTimer: ReturnType<typeof setInterval> | null = null

const activeEdgeList = computed(() => {
  const src = isExpanded.value ? expandedEdges.value : compactSequentialEdges.value
  return src.filter(e => isEdgeActive(e))
})

const compactSequentialEdges = computed(() =>
  NODES.slice(0, -1).map((_, i) => ({ from: i, to: i + 1 }))
)

function getPositions() {
  return isExpanded.value ? expandedPositions.value : compactPositions.value
}

function cubicBezier(t: number, p0: number, p1: number, p2: number, p3: number): number {
  const u = 1 - t
  return u*u*u*p0 + 3*u*u*t*p1 + 3*u*t*t*p2 + t*t*t*p3
}

function particlePos(p: Particle): { x: number; y: number } | null {
  const pos = getPositions()
  const from = pos[p.fromIdx]
  const to   = pos[p.toIdx]
  if (!from || !to) return null
  const t  = Math.min(p.progress, 1)
  const dx = (to.x - from.x) * 0.45
  const x  = cubicBezier(t, from.x, from.x + dx, to.x - dx, to.x)
  const y  = cubicBezier(t, from.y, from.y,       to.y,      to.y)
  return { x, y }
}

function spawnParticle() {
  const edges = activeEdgeList.value
  if (!edges.length) return
  const edge = edges[Math.floor(Math.random() * edges.length)]
  particles.value.push({
    id: pidCounter++,
    fromIdx: edge.from,
    toIdx: edge.to,
    progress: 0,
    speed: 0.008 + Math.random() * 0.009,
    size: 2 + Math.random() * 1.5,
    opacity: 0.7 + Math.random() * 0.3,
  })
}

function tick() {
  particles.value = particles.value
    .map(p => ({ ...p, progress: p.progress + p.speed }))
    .filter(p => p.progress < 1.08)
  raf = requestAnimationFrame(tick)
}

function startAnimation() {
  if (raf) return
  tick()
  spawnTimer = setInterval(spawnParticle, isExpanded.value ? 160 : 240)
}

function stopAnimation() {
  if (raf) { cancelAnimationFrame(raf); raf = null }
  if (spawnTimer) { clearInterval(spawnTimer); spawnTimer = null }
  particles.value = []
}

function restartSpawner() {
  if (spawnTimer) clearInterval(spawnTimer)
  if (raf) spawnTimer = setInterval(spawnParticle, isExpanded.value ? 160 : 240)
}

watch(() => props.currentStage, (s) => {
  if (s !== 'idle' && s !== 'completed') startAnimation()
  else stopAnimation()
}, { immediate: true })

watch(isExpanded, () => {
  particles.value = []
  nextTick(restartSpawner)
})

// ─── RESIZE OBSERVERS ────────────────────────────────────────────────────────
const roCompact  = ref<ResizeObserver | null>(null)
const roExpanded = ref<ResizeObserver | null>(null)

onMounted(() => {
  roCompact.value = new ResizeObserver(entries => {
    compactSvgWidth.value = entries[0]?.contentRect.width ?? 0
  })
  roExpanded.value = new ResizeObserver(entries => {
    expandedSvgWidth.value = entries[0]?.contentRect.width ?? 0
  })
  if (compactContainerRef.value) {
    roCompact.value.observe(compactContainerRef.value)
    compactSvgWidth.value = compactContainerRef.value.offsetWidth
  }
  if (expandedContainerRef.value) {
    roExpanded.value.observe(expandedContainerRef.value)
    expandedSvgWidth.value = expandedContainerRef.value.offsetWidth
  }
})

onBeforeUnmount(() => {
  stopAnimation()
  roCompact.value?.disconnect()
  roExpanded.value?.disconnect()
})

// Progress percent for the header bar
const progressPct = computed(() =>
  Math.round((currentIndex.value / NODES.length) * 100)
)
</script>

<template>
  <Transition name="nn-fade">
    <div
      v-if="currentStage !== 'idle' && currentStage !== 'completed'"
      class="nn-root"
      :class="{ 'nn-expanded': isExpanded }"
    >

      <!-- ── HEADER ── -->
      <div class="nn-header" @click="isExpanded = !isExpanded">
        <span class="nn-pulse-dot"></span>
        <span class="nn-title">NeuralFlow</span>

        <!-- progress bar -->
        <div class="nn-progress-track">
          <div class="nn-progress-fill" :style="{ width: progressPct + '%', background: activeNode?.color ?? '#6366f1' }"></div>
        </div>

        <!-- active stage pill -->
        <span class="nn-badge" :style="{ color: activeNode?.color, borderColor: activeNode?.color + '44', background: activeNode?.color + '11' }">
          {{ activeNode?.label ?? '' }}
        </span>

        <!-- expand toggle -->
        <button class="nn-toggle" :title="isExpanded ? 'Collapse' : 'Expand'">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <Transition name="icon-swap" mode="out-in">
              <path v-if="!isExpanded" key="expand"
                d="M2 5l5 4 5-4" stroke="currentColor" stroke-width="1.6"
                stroke-linecap="round" stroke-linejoin="round"/>
              <path v-else key="collapse"
                d="M2 9l5-4 5 4" stroke="currentColor" stroke-width="1.6"
                stroke-linecap="round" stroke-linejoin="round"/>
            </Transition>
          </svg>
        </button>
      </div>

      <!-- ── COMPACT VIEW ── -->
      <Transition name="nn-section">
        <div v-if="!isExpanded" ref="compactContainerRef" class="nn-compact-canvas">
          <svg
            v-if="compactSvgWidth > 0"
            :width="compactSvgWidth"
            :height="compactSvgHeight"
            :viewBox="`0 0 ${compactSvgWidth} ${compactSvgHeight}`"
            overflow="visible"
            class="nn-svg"
          >
            <defs>
              <filter id="c-glow" x="-30%" y="-80%" width="160%" height="260%">
                <feGaussianBlur stdDeviation="2.5" result="b"/>
                <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
              </filter>
            </defs>

            <!-- Edges -->
            <g v-if="compactPositions.length">
              <path
                v-for="(edge, ei) in compactSequentialEdges"
                :key="`ce-${ei}`"
                :d="wavePath(compactPositions[edge.from].x, compactPositions[edge.from].y, compactPositions[edge.to].x, compactPositions[edge.to].y)"
                fill="none"
                :stroke="edgeColor(edge)"
                :stroke-width="isEdgeActive(edge) ? 1.5 : 1"
                :stroke-opacity="isEdgeActive(edge) ? 0.5 : 0.18"
                :filter="isEdgeActive(edge) ? 'url(#c-glow)' : undefined"
                stroke-linecap="round"
              />
            </g>

            <!-- Particles -->
            <g v-if="compactPositions.length">
              <template v-for="p in particles" :key="p.id">
                <circle
                  v-if="particlePos(p)"
                  :cx="particlePos(p)!.x"
                  :cy="particlePos(p)!.y"
                  :r="p.size"
                  :fill="NODES[p.fromIdx].color"
                  :opacity="p.opacity * (1 - p.progress * 0.6)"
                  filter="url(#c-glow)"
                />
              </template>
            </g>

            <!-- Nodes -->
            <g v-if="compactPositions.length">
              <g
                v-for="(node, i) in NODES"
                :key="node.key"
                :transform="`translate(${compactPositions[i].x},${compactPositions[i].y})`"
              >
                <circle v-if="getNodeState(i)==='active'" r="18" :fill="node.glowColor" class="nn-ring" />
                <circle
                  r="12"
                  :fill="getNodeState(i)==='completed' ? node.color : getNodeState(i)==='active' ? 'var(--background-main)' : 'var(--fill-tsp-gray-main,#f3f4f6)'"
                  :stroke="getNodeState(i)==='pending' ? 'var(--border-main)' : node.color"
                  :stroke-width="getNodeState(i)==='active' ? 2 : 1.5"
                  :fill-opacity="getNodeState(i)==='pending' ? 0.35 : 1"
                  :filter="getNodeState(i)!=='pending' ? 'url(#c-glow)' : undefined"
                  :class="{'nn-active-node': getNodeState(i)==='active'}"
                />
                <text text-anchor="middle" dominant-baseline="central"
                  :font-size="getNodeState(i)==='active'?11:9.5"
                  :fill="getNodeState(i)==='completed'?'#fff': getNodeState(i)==='active'?node.color:'var(--text-tertiary)'"
                  :font-weight="getNodeState(i)==='active'?'700':'400'"
                  style="pointer-events:none;user-select:none;font-family:monospace"
                >{{ node.glyph }}</text>
                <text y="20" text-anchor="middle" dominant-baseline="hanging"
                  font-size="9"
                  :fill="getNodeState(i)==='active'?node.color: getNodeState(i)==='completed'?'var(--text-secondary)':'var(--text-tertiary)'"
                  :font-weight="getNodeState(i)==='active'?'600':'400'"
                  :opacity="getNodeState(i)==='pending'?0.4:1"
                  style="pointer-events:none;user-select:none"
                >{{ node.label }}</text>
              </g>
            </g>
          </svg>
        </div>
      </Transition>

      <!-- ── EXPANDED CANVAS ── -->
      <Transition name="nn-section">
        <div v-if="isExpanded" class="nn-expanded-wrap">
          <div ref="expandedContainerRef" class="nn-expanded-canvas">
            <svg
              v-if="expandedSvgWidth > 0"
              :width="expandedSvgWidth"
              :height="expandedSvgHeight"
              :viewBox="`0 0 ${expandedSvgWidth} ${expandedSvgHeight}`"
              overflow="visible"
              class="nn-svg"
            >
              <defs>
                <filter id="e-glow" x="-30%" y="-60%" width="160%" height="220%">
                  <feGaussianBlur stdDeviation="3.5" result="b"/>
                  <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
                </filter>
                <filter id="e-node-glow" x="-80%" y="-80%" width="260%" height="260%">
                  <feGaussianBlur stdDeviation="6" result="b"/>
                  <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
                </filter>
                <!-- Gradient for active edges -->
                <linearGradient
                  v-for="edge in expandedEdges"
                  :key="`grad-${edge.from}-${edge.to}`"
                  :id="`eg-${edge.from}-${edge.to}`"
                  gradientUnits="userSpaceOnUse"
                  :x1="expandedPositions[edge.from]?.x"
                  :y1="expandedPositions[edge.from]?.y"
                  :x2="expandedPositions[edge.to]?.x"
                  :y2="expandedPositions[edge.to]?.y"
                >
                  <stop offset="0%" :stop-color="NODES[edge.from].color" stop-opacity="0.7"/>
                  <stop offset="100%" :stop-color="NODES[edge.to].color" stop-opacity="0.5"/>
                </linearGradient>
              </defs>

              <!-- Layer labels -->
              <g v-if="expandedPositions.length">
                <text
                  v-for="(label, li) in ['Input','Hidden A','Hidden B','Output']"
                  :key="`lbl-${li}`"
                  :x="(expandedSvgWidth > 0 ? 70 + ((expandedSvgWidth-140)/(NUM_LAYERS-1))*li : 0)"
                  y="18"
                  text-anchor="middle"
                  font-size="9"
                  font-weight="600"
                  letter-spacing="0.08em"
                  text-transform="uppercase"
                  fill="var(--text-tertiary)"
                  style="text-transform:uppercase;user-select:none"
                  opacity="0.55"
                >{{ label }}</text>
              </g>

              <!-- Edges -->
              <g v-if="expandedPositions.length">
                <path
                  v-for="(edge, ei) in expandedEdges"
                  :key="`ee-${ei}`"
                  :d="wavePath(expandedPositions[edge.from].x, expandedPositions[edge.from].y, expandedPositions[edge.to].x, expandedPositions[edge.to].y)"
                  fill="none"
                  :stroke="isEdgeActive(edge) ? `url(#eg-${edge.from}-${edge.to})` : 'var(--border-main)'"
                  :stroke-width="isEdgeActive(edge) ? 1.8 : 1"
                  :stroke-opacity="isEdgeActive(edge) ? 0.65 : 0.15"
                  :filter="isEdgeActive(edge) ? 'url(#e-glow)' : undefined"
                  stroke-linecap="round"
                />
              </g>

              <!-- Particles -->
              <g v-if="expandedPositions.length">
                <template v-for="p in particles" :key="p.id">
                  <circle
                    v-if="particlePos(p)"
                    :cx="particlePos(p)!.x"
                    :cy="particlePos(p)!.y"
                    :r="p.size + 0.5"
                    :fill="NODES[p.fromIdx].color"
                    :opacity="p.opacity * (1 - p.progress * 0.55)"
                    filter="url(#e-node-glow)"
                  />
                </template>
              </g>

              <!-- Nodes (expanded, larger) -->
              <g v-if="expandedPositions.length">
                <g
                  v-for="(node, i) in NODES"
                  :key="node.key"
                  :transform="`translate(${expandedPositions[i].x},${expandedPositions[i].y})`"
                >
                  <!-- Outer halo -->
                  <circle
                    v-if="getNodeState(i)==='active'"
                    r="30"
                    :fill="node.glowColor"
                    class="nn-ring-large"
                  />

                  <!-- Node body -->
                  <circle
                    r="22"
                    :fill="getNodeState(i)==='completed' ? node.color : getNodeState(i)==='active' ? 'var(--background-main)' : 'var(--fill-tsp-gray-main,#f3f4f6)'"
                    :stroke="getNodeState(i)==='pending' ? 'var(--border-main)' : node.color"
                    :stroke-width="getNodeState(i)==='active' ? 2.5 : 2"
                    :fill-opacity="getNodeState(i)==='pending' ? 0.3 : 1"
                    :filter="getNodeState(i)!=='pending' ? 'url(#e-node-glow)' : undefined"
                    :class="{'nn-active-node': getNodeState(i)==='active'}"
                  />

                  <!-- Glyph -->
                  <text text-anchor="middle" dominant-baseline="central"
                    :font-size="getNodeState(i)==='active'?17:14"
                    :fill="getNodeState(i)==='completed'?'#fff': getNodeState(i)==='active'?node.color:'var(--text-tertiary)'"
                    :font-weight="getNodeState(i)==='active'?'700':'500'"
                    style="pointer-events:none;user-select:none;font-family:monospace"
                    :opacity="getNodeState(i)==='pending'?0.45:1"
                  >{{ node.glyph }}</text>

                  <!-- Label -->
                  <text y="34" text-anchor="middle" dominant-baseline="hanging"
                    font-size="11"
                    :fill="getNodeState(i)==='active'?node.color: getNodeState(i)==='completed'?'var(--text-primary)':'var(--text-tertiary)'"
                    :font-weight="getNodeState(i)==='active'?'700':'500'"
                    :opacity="getNodeState(i)==='pending'?0.4:1"
                    style="pointer-events:none;user-select:none"
                  >{{ node.label }}</text>

                  <!-- Sublabel (only active) -->
                  <text
                    v-if="getNodeState(i)==='active'"
                    y="48" text-anchor="middle" dominant-baseline="hanging"
                    font-size="8.5"
                    :fill="node.color"
                    opacity="0.8"
                    style="pointer-events:none;user-select:none"
                  >{{ node.sublabel }}</text>
                </g>
              </g>
            </svg>
          </div>

          <!-- Detail strip -->
          <div class="nn-detail-strip" v-if="activeNode">
            <span class="nn-detail-color" :style="{ background: activeNode.color }"></span>
            <div class="nn-detail-info">
              <span class="nn-detail-label">{{ activeNode.label }}</span>
              <span class="nn-detail-desc">{{ activeNode.detail }}</span>
            </div>
          </div>

          <!-- Live agent thoughts -->
          <Transition name="nn-section">
            <div v-if="props.thinkingText" class="nn-thoughts-panel">
              <div class="nn-thoughts-header">
                <span class="nn-thoughts-dot"></span>
                <span class="nn-thoughts-title">Agent Thoughts</span>
              </div>
              <div class="nn-thoughts-body">{{ props.thinkingText }}<span class="nn-cursor">▋</span></div>
            </div>
          </Transition>
        </div>
      </Transition>

    </div>
  </Transition>
</template>

<style scoped>
.nn-root {
  position: relative;
  background: var(--background-main, #fff);
  border: 1px solid var(--border-light, rgba(0,0,0,0.07));
  border-radius: 14px;
  padding: 0;
  margin-bottom: 10px;
  overflow: hidden;
  transition: box-shadow 0.25s ease;
}

.nn-root.nn-expanded {
  box-shadow: 0 4px 32px rgba(99,102,241,0.10), 0 1px 6px rgba(0,0,0,0.06);
}

/* Grid backdrop */
.nn-root::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(99,102,241,0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(99,102,241,0.035) 1px, transparent 1px);
  background-size: 22px 22px;
  pointer-events: none;
  border-radius: inherit;
}

/* ── Header ─────────────────────────── */
.nn-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  cursor: pointer;
  user-select: none;
  border-bottom: 1px solid transparent;
  transition: border-color 0.2s;
}
.nn-expanded .nn-header {
  border-bottom-color: var(--border-light, rgba(0,0,0,0.07));
}

.nn-pulse-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #6366f1;
  flex-shrink: 0;
  animation: nn-pulse 1.8s ease-in-out infinite;
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
  white-space: nowrap;
}

.nn-progress-track {
  flex: 1;
  height: 3px;
  background: var(--border-light, rgba(0,0,0,0.08));
  border-radius: 99px;
  overflow: hidden;
}
.nn-progress-fill {
  height: 100%;
  border-radius: 99px;
  transition: width 0.6s cubic-bezier(0.4,0,0.2,1);
}

.nn-badge {
  font-size: 10px;
  font-weight: 600;
  border: 1px solid;
  border-radius: 99px;
  padding: 1px 8px;
  white-space: nowrap;
}

.nn-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: var(--fill-tsp-gray-main, rgba(0,0,0,0.04));
  border: none;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: background 0.15s, color 0.15s;
  flex-shrink: 0;
}
.nn-toggle:hover {
  background: var(--fill-tsp-gray-hover, rgba(0,0,0,0.08));
  color: var(--text-secondary);
}

/* ── Compact canvas ─────────────────── */
.nn-compact-canvas {
  padding: 4px 10px 8px;
  width: 100%;
  height: 64px;
}

/* ── Expanded canvas ─────────────────── */
.nn-expanded-wrap {
  padding: 8px 12px 12px;
}
.nn-expanded-canvas {
  width: 100%;
  height: 280px;
}

/* ── SVG shared ─────────────────────── */
.nn-svg { display: block; overflow: visible; }

/* Active node border pulse */
.nn-active-node {
  animation: nn-active-glow 2s ease-in-out infinite;
}
@keyframes nn-active-glow {
  0%, 100% { filter: drop-shadow(0 0 4px currentColor); }
  50%       { filter: drop-shadow(0 0 10px currentColor); }
}

/* Compact active ring breathe */
.nn-ring {
  animation: nn-ring 1.6s ease-in-out infinite;
}
@keyframes nn-ring {
  0%, 100% { r: 16; opacity: 0.55; }
  50%       { r: 20; opacity: 0.22; }
}

/* Expanded large ring */
.nn-ring-large {
  animation: nn-ring-lg 1.8s ease-in-out infinite;
}
@keyframes nn-ring-lg {
  0%, 100% { r: 28; opacity: 0.5; }
  50%       { r: 36; opacity: 0.18; }
}

/* ── Detail strip ───────────────────── */
.nn-detail-strip {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 8px;
  padding: 8px 10px;
  background: var(--fill-tsp-gray-main, rgba(0,0,0,0.02));
  border: 1px solid var(--border-light, rgba(0,0,0,0.06));
  border-radius: 10px;
}
.nn-detail-color {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 4px;
}
.nn-detail-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.nn-detail-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-primary);
}
.nn-detail-desc {
  font-size: 10px;
  color: var(--text-tertiary);
  line-height: 1.5;
}

/* ── Agent Thoughts Panel ───────────── */
.nn-thoughts-panel {
  margin-top: 8px;
  border: 1px solid var(--border-light, rgba(0,0,0,0.07));
  border-radius: 10px;
  overflow: hidden;
  background: var(--fill-tsp-gray-main, rgba(0,0,0,0.02));
}

.nn-thoughts-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border-light, rgba(0,0,0,0.06));
}

.nn-thoughts-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #8b5cf6;
  animation: nn-pulse 1.8s ease-in-out infinite;
}

.nn-thoughts-title {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--text-tertiary);
}

.nn-thoughts-body {
  padding: 8px 10px;
  font-size: 11.5px;
  line-height: 1.65;
  color: var(--text-secondary);
  font-family: ui-monospace, 'Cascadia Code', 'Fira Code', monospace;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 160px;
  overflow-y: auto;
}

.nn-cursor {
  display: inline-block;
  color: #8b5cf6;
  animation: nn-blink 1s step-end infinite;
  margin-left: 1px;
}

@keyframes nn-blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}

/* ── Transitions ────────────────────── */
.nn-fade-enter-active, .nn-fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.nn-fade-enter-from, .nn-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

.nn-section-enter-active {
  transition: opacity 0.25s ease, max-height 0.35s cubic-bezier(0.4,0,0.2,1);
  overflow: hidden;
  max-height: 400px;
}
.nn-section-leave-active {
  transition: opacity 0.2s ease, max-height 0.25s cubic-bezier(0.4,0,0.2,1);
  overflow: hidden;
  max-height: 400px;
}
.nn-section-enter-from, .nn-section-leave-to {
  opacity: 0;
  max-height: 0;
}

.icon-swap-enter-active, .icon-swap-leave-active { transition: opacity 0.15s; }
.icon-swap-enter-from, .icon-swap-leave-to       { opacity: 0; }
</style>
