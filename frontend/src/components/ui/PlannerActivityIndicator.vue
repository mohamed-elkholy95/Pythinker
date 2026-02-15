<template>
  <div class="planner-activity">
    <svg
      class="planner-svg"
      viewBox="0 0 28 28"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <!-- Outer orbit ring -->
      <circle
        class="orbit-ring"
        cx="14"
        cy="14"
        r="12"
        stroke-width="0.4"
        fill="none"
      />

      <!-- Inner orbit ring -->
      <circle
        class="orbit-ring inner"
        cx="14"
        cy="14"
        r="7"
        stroke-width="0.3"
        fill="none"
      />

      <!-- Connection lines (drawn between nodes) -->
      <line class="conn-line c1" x1="14" y1="2" x2="24.4" y2="20" stroke-width="0.3" />
      <line class="conn-line c2" x1="24.4" y1="20" x2="3.6" y2="20" stroke-width="0.3" />
      <line class="conn-line c3" x1="3.6" y1="20" x2="14" y2="2" stroke-width="0.3" />
      <!-- Cross connections to center -->
      <line class="conn-line c4" x1="14" y1="2" x2="14" y2="14" stroke-width="0.25" />
      <line class="conn-line c5" x1="24.4" y1="20" x2="14" y2="14" stroke-width="0.25" />
      <line class="conn-line c6" x1="3.6" y1="20" x2="14" y2="14" stroke-width="0.25" />

      <!-- Orbiting dot on outer ring -->
      <circle class="orbit-dot" cx="14" cy="2" r="1.2">
        <animateTransform
          attributeName="transform"
          type="rotate"
          from="0 14 14"
          to="360 14 14"
          dur="4s"
          repeatCount="indefinite"
        />
      </circle>

      <!-- Counter-orbiting dot on inner ring -->
      <circle class="orbit-dot secondary" cx="14" cy="7" r="0.9">
        <animateTransform
          attributeName="transform"
          type="rotate"
          from="360 14 14"
          to="0 14 14"
          dur="3s"
          repeatCount="indefinite"
        />
      </circle>

      <!-- Center node — pulsing hub -->
      <circle class="center-node" cx="14" cy="14" r="2" />
      <circle class="center-pulse" cx="14" cy="14" r="2" />

      <!-- Vertex nodes (triangle) -->
      <circle class="vertex-node n1" cx="14" cy="2" r="1.5" />
      <circle class="vertex-node n2" cx="24.4" cy="20" r="1.5" />
      <circle class="vertex-node n3" cx="3.6" cy="20" r="1.5" />

      <!-- Data pulse traveling along connection c1 -->
      <circle class="data-pulse" r="0.6">
        <animate attributeName="cx" values="14;24.4;3.6;14" dur="3s" repeatCount="indefinite" />
        <animate attributeName="cy" values="2;20;20;2" dur="3s" repeatCount="indefinite" />
      </circle>
    </svg>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.planner-activity {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.planner-svg {
  width: 100%;
  height: 100%;
  overflow: visible;
}

/* Orbit rings */
.orbit-ring {
  stroke: #c48a50;
  opacity: 0.2;
  stroke-dasharray: 4 3;
  animation: ring-dash 6s linear infinite;
}

.orbit-ring.inner {
  stroke-dasharray: 2 2;
  animation-direction: reverse;
  animation-duration: 4s;
}

/* Connection lines */
.conn-line {
  stroke: #c48a50;
  opacity: 0;
  animation: conn-fade 3s ease-in-out infinite;
}

.c1 { animation-delay: 0s; }
.c2 { animation-delay: 0.5s; }
.c3 { animation-delay: 1.0s; }
.c4 { animation-delay: 0.25s; }
.c5 { animation-delay: 0.75s; }
.c6 { animation-delay: 1.25s; }

/* Orbiting dots */
.orbit-dot {
  fill: #e3a45a;
  opacity: 0.8;
  filter: drop-shadow(0 0 2px rgba(227, 164, 90, 0.5));
}

.orbit-dot.secondary {
  fill: #d4a060;
  opacity: 0.6;
}

/* Center node */
.center-node {
  fill: #c48a50;
  opacity: 0.7;
  animation: center-breathe 2s ease-in-out infinite;
}

.center-pulse {
  fill: none;
  stroke: #c48a50;
  stroke-width: 0.5;
  opacity: 0;
  animation: center-ring-pulse 2s ease-out infinite;
}

/* Vertex nodes */
.vertex-node {
  fill: #d4a060;
  opacity: 0.5;
  animation: vertex-blink 3s ease-in-out infinite;
}

.n1 { animation-delay: 0s; }
.n2 { animation-delay: 1s; }
.n3 { animation-delay: 2s; }

/* Data pulse */
.data-pulse {
  fill: #f2c88a;
  opacity: 0.7;
  filter: drop-shadow(0 0 1.5px rgba(242, 200, 138, 0.6));
}

/* === Dark mode === */
:deep(.dark) .orbit-ring,
.dark .orbit-ring {
  stroke: #ffd67a;
  opacity: 0.18;
}

:deep(.dark) .conn-line,
.dark .conn-line {
  stroke: #ffd67a;
}

:deep(.dark) .orbit-dot,
.dark .orbit-dot {
  fill: #ffe9ae;
  filter: drop-shadow(0 0 2px rgba(255, 216, 122, 0.4));
}

:deep(.dark) .orbit-dot.secondary,
.dark .orbit-dot.secondary {
  fill: #ffd67a;
}

:deep(.dark) .center-node,
.dark .center-node {
  fill: #ffd67a;
}

:deep(.dark) .center-pulse,
.dark .center-pulse {
  stroke: #ffd67a;
}

:deep(.dark) .vertex-node,
.dark .vertex-node {
  fill: #ffe9ae;
  opacity: 0.45;
}

:deep(.dark) .data-pulse,
.dark .data-pulse {
  fill: #ffe9ae;
  filter: drop-shadow(0 0 1.5px rgba(255, 233, 174, 0.5));
}

/* ============ KEYFRAMES ============ */

@keyframes ring-dash {
  0% { stroke-dashoffset: 0; }
  100% { stroke-dashoffset: 42; }
}

@keyframes conn-fade {
  0%, 10% { opacity: 0.08; }
  30%, 50% { opacity: 0.35; }
  70%, 100% { opacity: 0.08; }
}

@keyframes center-breathe {
  0%, 100% { opacity: 0.5; r: 1.8; }
  50% { opacity: 0.85; r: 2.2; }
}

@keyframes center-ring-pulse {
  0% { r: 2; opacity: 0.5; stroke-width: 0.5; }
  100% { r: 5; opacity: 0; stroke-width: 0.1; }
}

@keyframes vertex-blink {
  0%, 100% { opacity: 0.3; r: 1.3; }
  50% { opacity: 0.7; r: 1.7; }
}
</style>
