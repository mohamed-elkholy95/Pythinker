<template>
  <div class="planner-activity">
    <svg
      class="planner-svg"
      viewBox="0 0 28 28"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <!-- Slow-rotating outer glow ring -->
      <circle class="ambient-ring" cx="14" cy="14" r="13" />

      <!-- Outer hexagonal orbit ring -->
      <polygon
        class="orbit-ring"
        points="14,3 23.5,8.5 23.5,19.5 14,25 4.5,19.5 4.5,8.5"
        stroke-width="0.4"
        fill="none"
      />

      <!-- Inner hexagonal orbit ring -->
      <polygon
        class="orbit-ring inner"
        points="14,8.5 18.8,11.2 18.8,16.8 14,19.5 9.2,16.8 9.2,11.2"
        stroke-width="0.3"
        fill="none"
      />

      <!-- Spoke connections from outer vertices to center -->
      <line class="conn-line c1" x1="14" y1="3" x2="14" y2="14" stroke-width="0.25" />
      <line class="conn-line c2" x1="23.5" y1="8.5" x2="14" y2="14" stroke-width="0.25" />
      <line class="conn-line c3" x1="23.5" y1="19.5" x2="14" y2="14" stroke-width="0.25" />
      <line class="conn-line c4" x1="14" y1="25" x2="14" y2="14" stroke-width="0.25" />
      <line class="conn-line c5" x1="4.5" y1="19.5" x2="14" y2="14" stroke-width="0.25" />
      <line class="conn-line c6" x1="4.5" y1="8.5" x2="14" y2="14" stroke-width="0.25" />

      <!-- Energy sparks traveling inward along spokes -->
      <circle class="spark s1" r="0.6">
        <animate attributeName="cx" values="14;14" dur="2s" repeatCount="indefinite" />
        <animate attributeName="cy" values="3;14" dur="2s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0;0.9;0.9;0" dur="2s" repeatCount="indefinite" />
      </circle>
      <circle class="spark s2" r="0.6">
        <animate attributeName="cx" values="23.5;14" dur="2s" repeatCount="indefinite" begin="0.33s" />
        <animate attributeName="cy" values="8.5;14" dur="2s" repeatCount="indefinite" begin="0.33s" />
        <animate attributeName="opacity" values="0;0.9;0.9;0" dur="2s" repeatCount="indefinite" begin="0.33s" />
      </circle>
      <circle class="spark s3" r="0.6">
        <animate attributeName="cx" values="23.5;14" dur="2s" repeatCount="indefinite" begin="0.66s" />
        <animate attributeName="cy" values="19.5;14" dur="2s" repeatCount="indefinite" begin="0.66s" />
        <animate attributeName="opacity" values="0;0.9;0.9;0" dur="2s" repeatCount="indefinite" begin="0.66s" />
      </circle>
      <circle class="spark s4" r="0.6">
        <animate attributeName="cx" values="14;14" dur="2s" repeatCount="indefinite" begin="1s" />
        <animate attributeName="cy" values="25;14" dur="2s" repeatCount="indefinite" begin="1s" />
        <animate attributeName="opacity" values="0;0.9;0.9;0" dur="2s" repeatCount="indefinite" begin="1s" />
      </circle>
      <circle class="spark s5" r="0.6">
        <animate attributeName="cx" values="4.5;14" dur="2s" repeatCount="indefinite" begin="1.33s" />
        <animate attributeName="cy" values="19.5;14" dur="2s" repeatCount="indefinite" begin="1.33s" />
        <animate attributeName="opacity" values="0;0.9;0.9;0" dur="2s" repeatCount="indefinite" begin="1.33s" />
      </circle>
      <circle class="spark s6" r="0.6">
        <animate attributeName="cx" values="4.5;14" dur="2s" repeatCount="indefinite" begin="1.66s" />
        <animate attributeName="cy" values="8.5;14" dur="2s" repeatCount="indefinite" begin="1.66s" />
        <animate attributeName="opacity" values="0;0.9;0.9;0" dur="2s" repeatCount="indefinite" begin="1.66s" />
      </circle>

      <!-- Orbiting dot on outer hex path -->
      <circle class="orbit-dot" r="1.1">
        <animateMotion
          path="M14,3 L23.5,8.5 L23.5,19.5 L14,25 L4.5,19.5 L4.5,8.5 Z"
          dur="3s"
          repeatCount="indefinite"
        />
      </circle>

      <!-- Counter-orbiting dot on inner hex path (reversed direction) -->
      <circle class="orbit-dot secondary" r="0.8">
        <animateMotion
          path="M14,8.5 L9.2,11.2 L9.2,16.8 L14,19.5 L18.8,16.8 L18.8,11.2 Z"
          dur="2.2s"
          repeatCount="indefinite"
        />
      </circle>

      <!-- Third orbiting dot — outer ring, opposite phase -->
      <circle class="orbit-dot tertiary" r="0.7">
        <animateMotion
          path="M14,25 L4.5,19.5 L4.5,8.5 L14,3 L23.5,8.5 L23.5,19.5 Z"
          dur="3.5s"
          repeatCount="indefinite"
        />
      </circle>

      <!-- Center node — pulsing hub -->
      <circle class="center-node" cx="14" cy="14" r="2" />
      <circle class="center-pulse" cx="14" cy="14" r="2" />
      <circle class="center-pulse delayed" cx="14" cy="14" r="2" />

      <!-- Vertex nodes (hexagon — 6 outer neurons) -->
      <circle class="vertex-node n1" cx="14" cy="3" r="1.3" />
      <circle class="vertex-node n2" cx="23.5" cy="8.5" r="1.3" />
      <circle class="vertex-node n3" cx="23.5" cy="19.5" r="1.3" />
      <circle class="vertex-node n4" cx="14" cy="25" r="1.3" />
      <circle class="vertex-node n5" cx="4.5" cy="19.5" r="1.3" />
      <circle class="vertex-node n6" cx="4.5" cy="8.5" r="1.3" />

      <!-- Vertex glow bursts — each vertex flashes brighter when spark arrives -->
      <circle class="vertex-burst" cx="14" cy="3" r="2.5">
        <animate attributeName="opacity" values="0;0.6;0" dur="2s" repeatCount="indefinite" />
        <animate attributeName="r" values="1.3;3;1.3" dur="2s" repeatCount="indefinite" />
      </circle>
      <circle class="vertex-burst" cx="23.5" cy="8.5" r="2.5">
        <animate attributeName="opacity" values="0;0.6;0" dur="2s" repeatCount="indefinite" begin="0.33s" />
        <animate attributeName="r" values="1.3;3;1.3" dur="2s" repeatCount="indefinite" begin="0.33s" />
      </circle>
      <circle class="vertex-burst" cx="23.5" cy="19.5" r="2.5">
        <animate attributeName="opacity" values="0;0.6;0" dur="2s" repeatCount="indefinite" begin="0.66s" />
        <animate attributeName="r" values="1.3;3;1.3" dur="2s" repeatCount="indefinite" begin="0.66s" />
      </circle>
      <circle class="vertex-burst" cx="14" cy="25" r="2.5">
        <animate attributeName="opacity" values="0;0.6;0" dur="2s" repeatCount="indefinite" begin="1s" />
        <animate attributeName="r" values="1.3;3;1.3" dur="2s" repeatCount="indefinite" begin="1s" />
      </circle>
      <circle class="vertex-burst" cx="4.5" cy="19.5" r="2.5">
        <animate attributeName="opacity" values="0;0.6;0" dur="2s" repeatCount="indefinite" begin="1.33s" />
        <animate attributeName="r" values="1.3;3;1.3" dur="2s" repeatCount="indefinite" begin="1.33s" />
      </circle>
      <circle class="vertex-burst" cx="4.5" cy="8.5" r="2.5">
        <animate attributeName="opacity" values="0;0.6;0" dur="2s" repeatCount="indefinite" begin="1.66s" />
        <animate attributeName="r" values="1.3;3;1.3" dur="2s" repeatCount="indefinite" begin="1.66s" />
      </circle>

      <!-- Data pulse traveling along outer hex perimeter -->
      <circle class="data-pulse" r="0.5">
        <animate
          attributeName="cx"
          values="14;23.5;23.5;14;4.5;4.5;14"
          dur="4.5s"
          repeatCount="indefinite"
        />
        <animate
          attributeName="cy"
          values="3;8.5;19.5;25;19.5;8.5;3"
          dur="4.5s"
          repeatCount="indefinite"
        />
      </circle>
    </svg>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.planner-activity {
  width: 18px;
  height: 18px;
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

/* Ambient glow ring — slow rotation */
.ambient-ring {
  fill: none;
  stroke: #c48a50;
  stroke-width: 0.3;
  opacity: 0.12;
  stroke-dasharray: 6 4 2 4;
  animation: ambient-rotate 12s linear infinite;
  transform-origin: 14px 14px;
}

/* Orbit rings */
.orbit-ring {
  stroke: #c48a50;
  opacity: 0.2;
  stroke-dasharray: 4 3;
  animation: hex-dash 4s linear infinite;
}

.orbit-ring.inner {
  stroke-dasharray: 2 2;
  animation-direction: reverse;
  animation-duration: 3s;
}

/* Connection lines — sequential firing */
.conn-line {
  stroke: #c48a50;
  opacity: 0;
  animation: conn-fire 2s ease-in-out infinite;
}

.c1 { animation-delay: 0s; }
.c2 { animation-delay: 0.33s; }
.c3 { animation-delay: 0.66s; }
.c4 { animation-delay: 1s; }
.c5 { animation-delay: 1.33s; }
.c6 { animation-delay: 1.66s; }

/* Energy sparks */
.spark {
  fill: #f2c88a;
  opacity: 0;
  filter: drop-shadow(0 0 2px rgba(242, 200, 138, 0.8));
}

/* Orbiting dots */
.orbit-dot {
  fill: #e3a45a;
  opacity: 0.85;
  filter: drop-shadow(0 0 3px rgba(227, 164, 90, 0.6));
  animation: orbit-glow 1.5s ease-in-out infinite;
}

.orbit-dot.secondary {
  fill: #d4a060;
  opacity: 0.65;
  animation-delay: 0.75s;
}

.orbit-dot.tertiary {
  fill: #f2c88a;
  opacity: 0.5;
  filter: drop-shadow(0 0 2px rgba(242, 200, 138, 0.5));
  animation-delay: 0.4s;
}

/* Center node */
.center-node {
  fill: #c48a50;
  opacity: 0.7;
  animation: center-breathe 1.6s ease-in-out infinite;
}

.center-pulse {
  fill: none;
  stroke: #c48a50;
  stroke-width: 0.5;
  opacity: 0;
  animation: center-ring-pulse 2s ease-out infinite;
}

.center-pulse.delayed {
  animation-delay: 1s;
}

/* Vertex nodes */
.vertex-node {
  fill: #d4a060;
  opacity: 0.5;
  animation: vertex-blink 2s ease-in-out infinite;
}

.n1 { animation-delay: 0s; }
.n2 { animation-delay: 0.33s; }
.n3 { animation-delay: 0.66s; }
.n4 { animation-delay: 1s; }
.n5 { animation-delay: 1.33s; }
.n6 { animation-delay: 1.66s; }

/* Vertex glow bursts */
.vertex-burst {
  fill: #e3a45a;
  opacity: 0;
  filter: blur(1px);
}

/* Data pulse */
.data-pulse {
  fill: #f2c88a;
  opacity: 0.7;
  filter: drop-shadow(0 0 1.5px rgba(242, 200, 138, 0.6));
  animation: pulse-throb 1s ease-in-out infinite;
}

/* === Dark mode === */
:deep(.dark) .ambient-ring,
.dark .ambient-ring {
  stroke: #ffd67a;
  opacity: 0.08;
}

:deep(.dark) .orbit-ring,
.dark .orbit-ring {
  stroke: #ffd67a;
  opacity: 0.18;
}

:deep(.dark) .conn-line,
.dark .conn-line {
  stroke: #ffd67a;
}

:deep(.dark) .spark,
.dark .spark {
  fill: #ffe9ae;
  filter: drop-shadow(0 0 2px rgba(255, 233, 174, 0.7));
}

:deep(.dark) .orbit-dot,
.dark .orbit-dot {
  fill: #ffe9ae;
  filter: drop-shadow(0 0 3px rgba(255, 216, 122, 0.5));
}

:deep(.dark) .orbit-dot.secondary,
.dark .orbit-dot.secondary {
  fill: #ffd67a;
}

:deep(.dark) .orbit-dot.tertiary,
.dark .orbit-dot.tertiary {
  fill: #ffe9ae;
  filter: drop-shadow(0 0 2px rgba(255, 233, 174, 0.4));
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

:deep(.dark) .vertex-burst,
.dark .vertex-burst {
  fill: #ffd67a;
}

:deep(.dark) .data-pulse,
.dark .data-pulse {
  fill: #ffe9ae;
  filter: drop-shadow(0 0 1.5px rgba(255, 233, 174, 0.5));
}

/* ============ KEYFRAMES ============ */

@keyframes ambient-rotate {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@keyframes hex-dash {
  0% { stroke-dashoffset: 0; }
  100% { stroke-dashoffset: 66; }
}

@keyframes conn-fire {
  0%, 5% { opacity: 0.05; stroke-width: 0.25; }
  20%, 35% { opacity: 0.55; stroke-width: 0.5; }
  50%, 100% { opacity: 0.05; stroke-width: 0.25; }
}

@keyframes orbit-glow {
  0%, 100% { opacity: 0.6; filter: drop-shadow(0 0 2px rgba(227, 164, 90, 0.3)); }
  50% { opacity: 1; filter: drop-shadow(0 0 4px rgba(227, 164, 90, 0.7)); }
}

@keyframes center-breathe {
  0%, 100% { opacity: 0.5; r: 1.6; }
  50% { opacity: 0.95; r: 2.4; }
}

@keyframes center-ring-pulse {
  0% { r: 2; opacity: 0.6; stroke-width: 0.5; }
  100% { r: 6; opacity: 0; stroke-width: 0.1; }
}

@keyframes vertex-blink {
  0%, 100% { opacity: 0.25; r: 1.0; }
  40% { opacity: 0.85; r: 1.6; }
}

@keyframes pulse-throb {
  0%, 100% { r: 0.4; opacity: 0.5; }
  50% { r: 0.7; opacity: 0.9; }
}

@media (prefers-reduced-motion: reduce) {
  .planner-svg * {
    animation: none !important;
  }
}
</style>
