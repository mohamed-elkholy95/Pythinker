<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'

export type ReasoningStage = 'parsing' | 'intent' | 'retrieval' | 'planning' | 'generation' | 'quality_checking' | 'completed' | 'idle'

export interface LiveActivity {
  toolName?: string
  toolStatus?: 'calling' | 'called'
  toolArgs?: Record<string, unknown>
  stepDescription?: string
  progressMessage?: string
}

interface Props {
  currentStage: ReasoningStage
  thinkingText?: string
  liveActivity?: LiveActivity
}

const props = defineProps<Props>()

interface StageNode {
  key: ReasoningStage
  label: string
  /** Short friendly label shown on inactive compact nodes */
  shortDesc: string
  /** One-line plain-English description shown in expanded non-active nodes */
  friendlyDesc: string
  /** Active state description shown under active node */
  activeDesc: string
  detail: string
  glyph: string
  color: string
  glowColor: string
  layer: number
  row: number
}

const NODES: StageNode[] = [
  {
    key: 'parsing', label: 'Read',
    shortDesc: 'Reading input',
    friendlyDesc: 'Breaking down your message into meaningful parts',
    activeDesc: 'Reading & breaking down your request…',
    detail: 'Tokenization, Linguistic Analysis, Named Entity Recognition',
    glyph: '⌥', color: '#6366f1', glowColor: 'rgba(99,102,241,0.4)', layer: 0, row: 0,
  },
  {
    key: 'intent', label: 'Understand',
    shortDesc: 'Understanding goal',
    friendlyDesc: 'Figuring out what you actually need',
    activeDesc: 'Understanding your intent & context…',
    detail: 'Intent Recognition, Context Modeling, Ambiguity Resolution',
    glyph: '⊛', color: '#8b5cf6', glowColor: 'rgba(139,92,246,0.4)', layer: 1, row: 0,
  },
  {
    key: 'retrieval', label: 'Search',
    shortDesc: 'Looking things up',
    friendlyDesc: 'Searching the web & knowledge base',
    activeDesc: 'Searching for relevant information…',
    detail: 'Knowledge Graph Traversal, Document Retrieval, Fact Extraction',
    glyph: '⊕', color: '#3b82f6', glowColor: 'rgba(59,130,246,0.4)', layer: 1, row: 1,
  },
  {
    key: 'planning', label: 'Plan',
    shortDesc: 'Building a plan',
    friendlyDesc: 'Creating a step-by-step approach',
    activeDesc: 'Designing an action plan…',
    detail: 'Content Selection, Argumentation, Structure Determination',
    glyph: '⋈', color: '#0ea5e9', glowColor: 'rgba(14,165,233,0.4)', layer: 2, row: 0,
  },
  {
    key: 'generation', label: 'Write',
    shortDesc: 'Writing answer',
    friendlyDesc: 'Composing a clear, structured response',
    activeDesc: 'Writing the response…',
    detail: 'Sentence Construction, Cohesion, Coherence, Formatting Application',
    glyph: '∞', color: '#06b6d4', glowColor: 'rgba(6,182,212,0.4)', layer: 2, row: 1,
  },
  {
    key: 'quality_checking', label: 'Check',
    shortDesc: 'Checking quality',
    friendlyDesc: 'Reviewing for accuracy & completeness',
    activeDesc: 'Verifying accuracy & quality…',
    detail: 'Accuracy Verification, Safety Compliance, Completeness Check',
    glyph: '✦', color: '#10b981', glowColor: 'rgba(16,185,129,0.4)', layer: 3, row: 0,
  },
]

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

// ─── COMPACT MODE ────────────────────────────────────────────────────────────
const compactSvgWidth = ref(0)
const compactSvgHeight = 88
const compactContainerRef = ref<HTMLElement | null>(null)

const compactPositions = computed<{ x: number; y: number }[]>(() => {
  if (!compactSvgWidth.value) return []
  const n = NODES.length
  const pad = 36
  const usable = compactSvgWidth.value - pad * 2
  // Center nodes at 38% height so labels+desc below fit within canvas
  const cy = Math.round(compactSvgHeight * 0.38)
  return NODES.map((_, i) => ({
    x: pad + (usable / (n - 1)) * i,
    y: cy,
  }))
})

// ─── EXPANDED MODE ────────────────────────────────────────────────────────────
const expandedSvgWidth = ref(0)
const expandedSvgHeight = ref(240)
const expandedContainerRef = ref<HTMLElement | null>(null)

const NUM_LAYERS = 4
const expandedPositions = computed<{ x: number; y: number }[]>(() => {
  const w = expandedSvgWidth.value || 600
  const h = expandedSvgHeight.value
  const layerPad = 70
  const usableW = w - layerPad * 2
  const rowsPerLayer: Record<number, number> = {}
  for (const n of NODES) rowsPerLayer[n.layer] = Math.max(rowsPerLayer[n.layer] ?? 0, n.row + 1)
  return NODES.map(node => {
    const x = layerPad + (usableW / (NUM_LAYERS - 1)) * node.layer
    const rows = rowsPerLayer[node.layer] ?? 1
    const rowSpacing = rows > 1 ? (h * 0.5) / (rows - 1) : 0
    const startY = h / 2 - (rows - 1) * rowSpacing / 2
    const y = rows > 1 ? startY + node.row * rowSpacing : h / 2
    return { x, y }
  })
})

const expandedEdges = computed(() => {
  const edges: { from: number; to: number }[] = []
  for (let i = 0; i < NODES.length; i++)
    for (let j = 0; j < NODES.length; j++)
      if (NODES[j].layer === NODES[i].layer + 1) edges.push({ from: i, to: j })
  return edges
})

function isEdgeActive(edge: { from: number; to: number }): boolean {
  const fs = getNodeState(edge.from)
  const ts = getNodeState(edge.to)
  return fs === 'completed' || fs === 'active' || ts === 'active'
}

function edgeColor(edge: { from: number; to: number }): string {
  return isEdgeActive(edge) ? NODES[edge.from].color : 'var(--border-main)'
}

function wavePath(x1: number, y1: number, x2: number, y2: number): string {
  const dx = (x2 - x1) * 0.45
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`
}

// ─── PARTICLE SYSTEM ─────────────────────────────────────────────────────────
interface Particle { id: number; fromIdx: number; toIdx: number; progress: number; speed: number; size: number; opacity: number }
const particles = ref<Particle[]>([])
let pidCounter = 0
let raf: number | null = null
let spawnTimer: ReturnType<typeof setInterval> | null = null

const compactSequentialEdges = computed(() =>
  NODES.slice(0, -1).map((_, i) => ({ from: i, to: i + 1 }))
)

const activeEdgeList = computed(() => {
  const src = isExpanded.value ? expandedEdges.value : compactSequentialEdges.value
  return src.filter(e => isEdgeActive(e))
})

function getPositions() {
  return isExpanded.value ? expandedPositions.value : compactPositions.value
}

function cubicBezier(t: number, p0: number, p1: number, p2: number, p3: number): number {
  const u = 1 - t
  return u*u*u*p0 + 3*u*u*t*p1 + 3*u*t*t*p2 + t*t*t*p3
}

function particlePos(p: Particle | undefined | null): { x: number; y: number } | null {
  if (!p) return null
  const pos = getPositions()
  const from = pos[p.fromIdx]; const to = pos[p.toIdx]
  if (!from || !to) return null
  const t = Math.min(p.progress, 1)
  const dx = (to.x - from.x) * 0.45
  return {
    x: cubicBezier(t, from.x, from.x + dx, to.x - dx, to.x),
    y: cubicBezier(t, from.y, from.y, to.y, to.y),
  }
}

function spawnParticle() {
  const edges = activeEdgeList.value
  if (!edges.length) return
  const edge = edges[Math.floor(Math.random() * edges.length)]
  particles.value.push({ id: pidCounter++, fromIdx: edge.from, toIdx: edge.to, progress: 0, speed: 0.008 + Math.random() * 0.009, size: 2 + Math.random() * 1.5, opacity: 0.7 + Math.random() * 0.3 })
}

function tick() {
  particles.value = particles.value
    .filter((p): p is Particle => !!p && typeof p.fromIdx === 'number')
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

watch(isExpanded, () => { particles.value = []; nextTick(restartSpawner) })

// ─── RESIZE OBSERVERS ────────────────────────────────────────────────────────
const roCompact  = ref<ResizeObserver | null>(null)
const roExpanded = ref<ResizeObserver | null>(null)

onMounted(() => {
  roCompact.value = new ResizeObserver(e => { compactSvgWidth.value = e[0]?.contentRect.width ?? 0 })
  roExpanded.value = new ResizeObserver(e => { expandedSvgWidth.value = e[0]?.contentRect.width ?? 0 })
  if (compactContainerRef.value) { roCompact.value.observe(compactContainerRef.value); compactSvgWidth.value = compactContainerRef.value.offsetWidth }
  if (expandedContainerRef.value) { roExpanded.value.observe(expandedContainerRef.value); expandedSvgWidth.value = expandedContainerRef.value.offsetWidth }
})

onBeforeUnmount(() => { stopAnimation(); roCompact.value?.disconnect(); roExpanded.value?.disconnect() })

const progressPct = computed(() => Math.round((currentIndex.value / NODES.length) * 100))

// ─── TOOL LABEL HELPER ────────────────────────────────────────────────────────
function toolLabel(toolName: string, toolArgs: Record<string, unknown>): { detail: string } {
  const name = toolName.toLowerCase()
  const firstArg = Object.values(toolArgs)[0]
  const argStr = typeof firstArg === 'string' ? firstArg.slice(0, 40) : ''

  if (name.includes('search') || name.includes('web')) return { detail: argStr ? `Searching: ${argStr}` : 'Web search' }
  if (name.includes('browser') || name.includes('navigate')) return { detail: argStr ? `Navigate: ${argStr}` : 'Browser' }
  if (name.includes('read') || name.includes('file')) return { detail: argStr ? `File: ${argStr}` : 'Reading file' }
  if (name.includes('write') || name.includes('edit')) return { detail: argStr ? `Writing: ${argStr}` : 'Editing file' }
  if (name.includes('terminal') || name.includes('bash') || name.includes('exec')) return { detail: argStr ? `Run: ${argStr}` : 'Terminal' }
  return { detail: argStr || toolName }
}

// ─── COMPACT INLINE LABEL ─────────────────────────────────────────────────────
const compactLabel = computed(() => {
  const a = props.liveActivity
  if (!a) return activeNode.value?.sublabel ?? ''
  if (a.toolName) {
    const { detail } = toolLabel(a.toolName, a.toolArgs ?? {})
    return detail.slice(0, 60)
  }
  if (a.stepDescription) return a.stepDescription.slice(0, 60)
  if (a.progressMessage) return a.progressMessage.slice(0, 60)
  return activeNode.value?.sublabel ?? ''
})


</script>

<template>
  <Transition name="nn-fade">
    <div
      v-if="currentStage !== 'idle' && currentStage !== 'completed'"
      class="nn-root"
      :class="{ 'nn-expanded': isExpanded }"
    >

      <!-- ── HEADER ── -->
      <div class="nn-header">
        <span class="nn-pulse-dot"></span>
        <span class="nn-title">NeuralFlow</span>

        <!-- live activity inline label -->
        <span class="nn-activity-inline" v-if="compactLabel">{{ compactLabel }}</span>

        <!-- progress bar -->
        <div class="nn-progress-track">
          <div class="nn-progress-fill" :style="{ width: progressPct + '%', background: activeNode?.color ?? '#6366f1' }"></div>
        </div>

        <!-- active stage pill -->
        <span class="nn-badge" :style="{ color: activeNode?.color, borderColor: (activeNode?.color ?? '#6366f1') + '44', background: (activeNode?.color ?? '#6366f1') + '11' }">
          {{ activeNode?.label ?? '' }}
        </span>
      </div>

      <!-- ── COMPACT VIEW (always shown) ── -->
      <div ref="compactContainerRef" class="nn-compact-canvas">
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
            <path v-for="(edge, ei) in compactSequentialEdges" :key="`ce-${ei}`"
              :d="wavePath(compactPositions[edge.from].x, compactPositions[edge.from].y, compactPositions[edge.to].x, compactPositions[edge.to].y)"
              fill="none" :stroke="edgeColor(edge)"
              :stroke-width="isEdgeActive(edge) ? 1.5 : 1"
              :stroke-opacity="isEdgeActive(edge) ? 0.5 : 0.18"
              :filter="isEdgeActive(edge) ? 'url(#c-glow)' : undefined"
              stroke-linecap="round"
            />
          </g>

          <!-- Particles -->
          <g v-if="compactPositions.length">
            <template v-for="p in particles" :key="p.id">
              <circle v-if="particlePos(p)"
                :cx="particlePos(p)!.x" :cy="particlePos(p)!.y"
                :r="p.size" :fill="NODES[p.fromIdx]?.color ?? '#6366f1'"
                :opacity="p.opacity * (1 - p.progress * 0.6)"
                filter="url(#c-glow)"
              />
            </template>
          </g>

          <!-- Nodes -->
          <g v-if="compactPositions.length">
            <g v-for="(node, i) in NODES" :key="node.key"
              :transform="`translate(${compactPositions[i].x},${compactPositions[i].y})`"
            >
              <circle v-if="getNodeState(i)==='active'" r="18" :fill="node.glowColor" class="nn-ring" />
              <circle r="12"
                :fill="getNodeState(i)==='completed' ? node.color : getNodeState(i)==='active' ? 'var(--background-main)' : 'var(--fill-tsp-gray-main,#f3f4f6)'"
                :stroke="getNodeState(i)==='pending' ? 'var(--border-main)' : node.color"
                :stroke-width="getNodeState(i)==='active' ? 2 : 1.5"
                :fill-opacity="getNodeState(i)==='pending' ? 0.35 : 1"
                :filter="getNodeState(i)!=='pending' ? 'url(#c-glow)' : undefined"
                :class="{'nn-active-node': getNodeState(i)==='active'}"
              />
              <text text-anchor="middle" dominant-baseline="central"
                :font-size="getNodeState(i)==='active' ? 11 : 9.5"
                :fill="getNodeState(i)==='completed' ? '#fff' : getNodeState(i)==='active' ? node.color : 'var(--text-tertiary)'"
                :font-weight="getNodeState(i)==='active' ? '700' : '400'"
                style="pointer-events:none;user-select:none;font-family:monospace"
              >{{ node.glyph }}</text>
              <!-- friendly label below each node -->
              <text y="20" text-anchor="middle" dominant-baseline="hanging"
                font-size="9"
                :fill="getNodeState(i)==='active' ? node.color : getNodeState(i)==='completed' ? 'var(--text-secondary)' : 'var(--text-tertiary)'"
                :font-weight="getNodeState(i)==='active' ? '600' : '400'"
                :opacity="getNodeState(i)==='pending' ? 0.4 : 1"
                style="pointer-events:none;user-select:none"
              >{{ node.label }}</text>
              <!-- active: show friendly description below the label -->
              <text v-if="getNodeState(i)==='active'"
                y="31" text-anchor="middle" dominant-baseline="hanging"
                font-size="7.5"
                :fill="node.color"
                opacity="0.75"
                style="pointer-events:none;user-select:none"
              >{{ node.shortDesc }}</text>
            </g>
          </g>
        </svg>
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
  padding: 0;
  margin-top: -4px;
  margin-bottom: 6px;
  overflow: clip;
  transition: box-shadow 0.25s ease;
}
.nn-root.nn-expanded {
  box-shadow: 0 4px 32px rgba(99,102,241,0.10), 0 1px 6px rgba(0,0,0,0.06);
}
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

/* ── Header ──────────────────────────── */
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
.nn-expanded .nn-header { border-bottom-color: var(--border-light, rgba(0,0,0,0.07)); }

.nn-pulse-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #6366f1; flex-shrink: 0;
  animation: nn-pulse 1.8s ease-in-out infinite;
}
@keyframes nn-pulse {
  0%   { box-shadow: 0 0 0 0   rgba(99,102,241,0.7); }
  60%  { box-shadow: 0 0 0 5px rgba(99,102,241,0); }
  100% { box-shadow: 0 0 0 0   rgba(99,102,241,0); }
}

.nn-title {
  font-size: 10.5px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.08em; color: var(--text-tertiary); white-space: nowrap;
}

.nn-activity-inline {
  font-size: 10.5px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
  font-family: ui-monospace, 'Cascadia Code', monospace;
}

.nn-progress-track {
  flex: 0 0 60px;
  height: 3px;
  background: var(--border-light, rgba(0,0,0,0.08));
  border-radius: 99px;
  overflow: hidden;
}
.nn-progress-fill {
  height: 100%; border-radius: 99px;
  transition: width 0.6s cubic-bezier(0.4,0,0.2,1);
}

.nn-badge {
  font-size: 10px; font-weight: 600; border: 1px solid;
  border-radius: 99px; padding: 1px 8px; white-space: nowrap;
}

.nn-toggle {
  display: flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 6px;
  background: var(--fill-tsp-gray-main, rgba(0,0,0,0.04));
  border: none; cursor: pointer; color: var(--text-tertiary);
  transition: background 0.15s, color 0.15s; flex-shrink: 0;
}
.nn-toggle:hover { background: var(--fill-tsp-gray-hover, rgba(0,0,0,0.08)); color: var(--text-secondary); }

/* ── Compact canvas ─────────────────── */
.nn-compact-canvas { padding: 4px 10px 10px; width: 100%; height: 88px; }

/* ── Expanded ────────────────────────── */
.nn-expanded-wrap { padding: 8px 12px 12px; display: flex; flex-direction: column; gap: 10px; }
.nn-expanded-canvas { width: 100%; height: 240px; }
.nn-svg { display: block; overflow: visible; }

.nn-active-node { animation: nn-active-glow 2s ease-in-out infinite; }
@keyframes nn-active-glow {
  0%, 100% { filter: drop-shadow(0 0 4px currentColor); }
  50%       { filter: drop-shadow(0 0 10px currentColor); }
}
.nn-ring { animation: nn-ring 1.6s ease-in-out infinite; }
@keyframes nn-ring { 0%, 100% { r: 16; opacity: 0.55; } 50% { r: 20; opacity: 0.22; } }

/* ── Activity Feed ───────────────────── */
.nn-activity-feed {
  border: 1px solid var(--border-light, rgba(0,0,0,0.07));
  border-radius: 10px;
  overflow: hidden;
  background: var(--fill-tsp-gray-main, rgba(0,0,0,0.02));
}

.nn-feed-header {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 10px;
  border-bottom: 1px solid var(--border-light, rgba(0,0,0,0.06));
}
.nn-feed-dot {
  width: 5px; height: 5px; border-radius: 50%;
  background: #3b82f6;
  animation: nn-pulse 1.8s ease-in-out infinite;
}
.nn-feed-title {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.07em; color: var(--text-tertiary);
}
.nn-feed-count {
  margin-left: auto;
  font-size: 9.5px; font-weight: 600;
  color: var(--text-tertiary);
  background: var(--fill-tsp-gray-main, rgba(0,0,0,0.05));
  border: 1px solid var(--border-light, rgba(0,0,0,0.08));
  border-radius: 99px; padding: 0 6px;
}

.nn-feed-empty {
  padding: 12px 10px;
  font-size: 11px;
  color: var(--text-tertiary);
  font-style: italic;
}

.nn-feed-scroll {
  max-height: 180px;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.nn-feed-scroll::-webkit-scrollbar { width: 3px; }
.nn-feed-scroll::-webkit-scrollbar-track { background: transparent; }
.nn-feed-scroll::-webkit-scrollbar-thumb { background: var(--border-main, rgba(0,0,0,0.15)); border-radius: 99px; }

.nn-feed-list { display: flex; flex-direction: column; }

.nn-feed-entry {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border-light, rgba(0,0,0,0.04));
  transition: background 0.15s;
}
.nn-feed-entry:last-child { border-bottom: none; }
.nn-feed-entry:hover { background: var(--fill-tsp-gray-main, rgba(0,0,0,0.03)); }

.nn-entry-icon {
  display: flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 6px; flex-shrink: 0;
  background: var(--fill-tsp-gray-main, rgba(0,0,0,0.04));
  border: 1px solid var(--border-light, rgba(0,0,0,0.06));
  margin-top: 1px;
}
.nn-entry-body {
  display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1;
}
.nn-entry-label {
  font-size: 10.5px; font-weight: 700; letter-spacing: 0.02em;
}
.nn-entry-detail {
  font-size: 11px;
  color: var(--text-secondary);
  font-family: ui-monospace, 'Cascadia Code', 'Fira Code', monospace;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.4;
}
.nn-entry-url {
  font-size: 11px;
  color: #3b82f6;
  font-family: ui-monospace, 'Cascadia Code', 'Fira Code', monospace;
  word-break: break-all;
  line-height: 1.4;
  text-decoration: none;
}
.nn-entry-url:hover { text-decoration: underline; color: #2563eb; }

/* Entry slide-in */
.nn-entry-enter-active { transition: opacity 0.25s ease, transform 0.25s ease; }
.nn-entry-enter-from   { opacity: 0; transform: translateY(-6px); }
.nn-entry-leave-active { transition: opacity 0.15s ease; }
.nn-entry-leave-to     { opacity: 0; }

/* ── Thoughts panel ──────────────────── */
.nn-thoughts-panel {
  border-top: 1px solid var(--border-light, rgba(0,0,0,0.06));
  overflow: hidden;
}
.nn-thoughts-header {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border-light, rgba(0,0,0,0.06));
}
.nn-thoughts-dot {
  width: 5px; height: 5px; border-radius: 50%;
  background: #8b5cf6;
  animation: nn-pulse 1.8s ease-in-out infinite;
}
.nn-thoughts-title {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.07em; color: var(--text-tertiary);
}
.nn-thoughts-body {
  padding: 8px 10px;
  font-size: 11.5px; line-height: 1.65;
  color: var(--text-secondary);
  font-family: ui-monospace, 'Cascadia Code', 'Fira Code', monospace;
  white-space: pre-wrap; word-break: break-word;
  max-height: 120px; overflow-y: auto;
}
.nn-cursor {
  display: inline-block; color: #8b5cf6;
  animation: nn-blink 1s step-end infinite; margin-left: 1px;
}
@keyframes nn-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }

/* ── Transitions ─────────────────────── */
.nn-fade-enter-active, .nn-fade-leave-active { transition: opacity 0.3s ease, transform 0.3s ease; }
.nn-fade-enter-from, .nn-fade-leave-to { opacity: 0; transform: translateY(-6px); }
.nn-section-enter-active { transition: opacity 0.25s ease, max-height 0.35s cubic-bezier(0.4,0,0.2,1); overflow: hidden; max-height: 800px; }
.nn-section-leave-active { transition: opacity 0.2s ease, max-height 0.25s cubic-bezier(0.4,0,0.2,1); overflow: hidden; max-height: 800px; }
.nn-section-enter-from, .nn-section-leave-to { opacity: 0; max-height: 0; }
.icon-swap-enter-active, .icon-swap-leave-active { transition: opacity 0.15s; }
.icon-swap-enter-from, .icon-swap-leave-to { opacity: 0; }
</style>
