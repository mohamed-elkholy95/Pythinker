<script setup lang="ts">
import { Zap, Globe } from 'lucide-vue-next';
import type { ResearchMode } from '../api/agent';

defineProps<{
  mode: ResearchMode | null;
  compact?: boolean;
}>();
</script>

<template>
  <span
    v-if="mode"
    class="research-badge"
    :class="[
      mode === 'fast_search' ? 'badge-fast' : 'badge-deep',
      { 'badge-compact': compact }
    ]"
  >
    <span class="badge-icon-wrap">
      <Zap v-if="mode === 'fast_search'" :size="12" :stroke-width="2.5" />
      <Globe v-else :size="12" :stroke-width="2" />
    </span>
    <span v-if="!compact" class="badge-label">
      {{ mode === 'fast_search' ? 'Fast Search' : 'Research' }}
    </span>
  </span>
</template>

<style scoped>
.research-badge {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px 4px 6px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 500;
  line-height: 1;
  letter-spacing: 0.02em;
  white-space: nowrap;
  flex-shrink: 0;
  color: var(--text-primary);
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-dark);
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.badge-compact {
  padding: 4px 6px;
  gap: 0;
}

.research-badge:hover {
  background: var(--fill-tsp-white-dark);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  border-color: var(--border-hover);
}

:global(.dark) .research-badge {
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

:global(.dark) .research-badge:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
}

/* ── Icon container ── */
.badge-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: var(--radius-full);
  background: var(--bolt-elements-item-backgroundAccent);
  color: var(--text-white);
  flex-shrink: 0;
  transition: all 0.3s ease;
}

/* ── Fast Search — lighter weight ── */
.badge-fast {
  color: var(--text-secondary);
}

.badge-fast .badge-icon-wrap {
  background: var(--fill-tsp-white-dark);
  color: var(--text-primary);
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.05);
}

/* ── Deep Research — full contrast + shimmer ── */
.badge-deep {
  border-color: rgba(0, 0, 0, 0.15);
  background: linear-gradient(145deg, var(--fill-tsp-white-main), rgba(0, 0, 0, 0.03));
}

.badge-deep .badge-icon-wrap {
  background: linear-gradient(135deg, #27272a, #000000);
  color: #ffffff;
  animation: globe-spin 7s cubic-bezier(0.4, 0, 0.2, 1) infinite;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
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
    rgba(0, 0, 0, 0.08) 50%,
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
:global(.dark) .badge-deep {
  border-color: rgba(255, 255, 255, 0.15);
  background: linear-gradient(145deg, var(--fill-tsp-white-main), rgba(255, 255, 255, 0.05));
}

:global(.dark) .badge-deep::after {
  background: linear-gradient(
    105deg,
    transparent 35%,
    rgba(255, 255, 255, 0.08) 45%,
    rgba(255, 255, 255, 0.15) 50%,
    rgba(255, 255, 255, 0.08) 55%,
    transparent 65%
  );
}

:global(.dark) .badge-fast .badge-icon-wrap {
  background: rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.9);
  box-shadow: inset 0 1px 2px rgba(255, 255, 255, 0.05);
}

:global(.dark) .badge-deep .badge-icon-wrap {
  background: linear-gradient(135deg, #f4f4f5, #ffffff);
  color: #000000;
  box-shadow: 0 0 12px rgba(255, 255, 255, 0.3);
}

:global(.dark) .research-badge {
  border-color: var(--border-light);
}

/* ── Label ── */
.badge-label {
  position: relative;
  z-index: 1;
}
</style>
