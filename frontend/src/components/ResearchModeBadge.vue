<script setup lang="ts">
import { Zap, Globe } from 'lucide-vue-next';
import type { ResearchMode } from '../api/agent';

defineProps<{
  mode: ResearchMode | null;
}>();
</script>

<template>
  <span
    v-if="mode"
    class="research-badge"
    :class="mode === 'fast_search' ? 'badge-fast' : 'badge-deep'"
  >
    <span class="badge-icon-wrap">
      <Zap v-if="mode === 'fast_search'" :size="11" :stroke-width="2.5" />
      <Globe v-else :size="11" :stroke-width="2" />
    </span>
    <span class="badge-label">
      {{ mode === 'fast_search' ? 'Fast Search' : 'Research' }}
    </span>
  </span>
</template>

<style scoped>
.research-badge {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px 3px 7px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: 0.04em;
  white-space: nowrap;
  flex-shrink: 0;
  color: var(--text-primary);
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-dark);
  overflow: hidden;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.research-badge:hover {
  background: var(--fill-tsp-white-dark);
  border-color: var(--border-hover);
}

/* ── Icon container ── */
.badge-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: var(--radius-full);
  background: var(--bolt-elements-item-backgroundAccent);
  color: var(--text-white);
  flex-shrink: 0;
}

/* ── Fast Search — lighter weight ── */
.badge-fast {
  color: var(--text-secondary);
}

.badge-fast .badge-icon-wrap {
  background: var(--fill-tsp-white-dark);
  color: var(--text-primary);
}

/* ── Deep Research — full contrast + shimmer ── */
.badge-deep .badge-icon-wrap {
  background: var(--bolt-elements-item-contentAccent);
  color: var(--Button-primary-white);
  animation: globe-spin 7s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

/* Spin 360deg in first ~2s, then hold still for ~5s */
@keyframes globe-spin {
  0% { transform: rotate(0deg); }
  28% { transform: rotate(360deg); }
  100% { transform: rotate(360deg); }
}

.badge-deep::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    105deg,
    transparent 35%,
    rgba(0, 0, 0, 0.04) 45%,
    rgba(0, 0, 0, 0.06) 50%,
    rgba(0, 0, 0, 0.04) 55%,
    transparent 65%
  );
  animation: badge-shimmer 3.5s ease-in-out infinite;
  pointer-events: none;
  border-radius: inherit;
}

@keyframes badge-shimmer {
  0% { transform: translateX(-120%); }
  60%, 100% { transform: translateX(120%); }
}

/* ── Dark theme ── */
:global([data-theme='dark']) .badge-deep::after {
  background: linear-gradient(
    105deg,
    transparent 35%,
    rgba(255, 255, 255, 0.04) 45%,
    rgba(255, 255, 255, 0.07) 50%,
    rgba(255, 255, 255, 0.04) 55%,
    transparent 65%
  );
}

/* In dark mode --bolt-elements-item-contentAccent resolves to a muted grey
   surface — replace with a vivid brand-aware fill so the globe reads clearly. */
:global([data-theme='dark']) .badge-deep .badge-icon-wrap {
  background: var(--text-brand);
  color: #fff;
}

:global([data-theme='dark']) .badge-fast .badge-icon-wrap {
  background: rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.82);
}

:global([data-theme='dark']) .research-badge {
  border-color: var(--border-light);
}

/* ── Label ── */
.badge-label {
  position: relative;
  z-index: 1;
}
</style>
