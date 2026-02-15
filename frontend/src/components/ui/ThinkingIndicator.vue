<template>
  <div class="thinking-lamp-wrapper" @mouseenter="hovered = true" @mouseleave="hovered = false">
    <div class="thinking-lamp" :class="{ 'lamp-with-text': props.showText, 'lamp-hovered': hovered }">
      <!-- The lamp SVG — Futuristic AI Core Design -->
      <svg
        class="lamp-svg"
        viewBox="0 0 200 200"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <!-- Clip interior to hex core -->
          <clipPath id="core-clip">
            <polygon points="100,18 162,52 162,118 100,152 38,118 38,52" />
          </clipPath>
          <!-- Pulsing core gradient -->
          <radialGradient id="core-energy" cx="50%" cy="45%" r="45%">
            <stop offset="0%" stop-color="#ffe4a0" stop-opacity="0.9">
              <animate attributeName="stop-opacity" values="0.9;0.3;0.9" dur="2s" repeatCount="indefinite" />
            </stop>
            <stop offset="55%" stop-color="#c48a50" stop-opacity="0.2">
              <animate attributeName="stop-opacity" values="0.2;0.05;0.2" dur="2s" repeatCount="indefinite" />
            </stop>
            <stop offset="100%" stop-color="transparent" />
          </radialGradient>
          <!-- Plasma blob gradient -->
          <radialGradient id="plasma-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#ffd080" stop-opacity="0.65" />
            <stop offset="80%" stop-color="#c48a50" stop-opacity="0.1" />
            <stop offset="100%" stop-color="transparent" />
          </radialGradient>
        </defs>

        <!-- Sequential thinking rays — left to right -->
        <g class="rays-group">
          <line class="thinking-ray ray-1" x1="22" y1="85" x2="6" y2="85" stroke-width="3" stroke-linecap="round" />
          <line class="thinking-ray ray-2" x1="32" y1="40" x2="18" y2="22" stroke-width="3" stroke-linecap="round" />
          <line class="thinking-ray ray-3" x1="72" y1="14" x2="66" y2="-2" stroke-width="3" stroke-linecap="round" />
          <line class="thinking-ray ray-4" x1="100" y1="8" x2="100" y2="-8" stroke-width="3" stroke-linecap="round" />
          <line class="thinking-ray ray-5" x1="128" y1="14" x2="134" y2="-2" stroke-width="3" stroke-linecap="round" />
          <line class="thinking-ray ray-6" x1="168" y1="40" x2="182" y2="22" stroke-width="3" stroke-linecap="round" />
          <line class="thinking-ray ray-7" x1="178" y1="85" x2="194" y2="85" stroke-width="3" stroke-linecap="round" />
        </g>

        <!-- Outer rotating hex ring -->
        <polygon
          class="hex-ring outer"
          points="100,10 168,48 168,122 100,160 32,122 32,48"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-dasharray="8 6"
        />

        <!-- Inner hex frame (main shape) -->
        <polygon
          class="hex-frame"
          points="100,18 162,52 162,118 100,152 38,118 38,52"
          fill="currentColor"
          stroke="currentColor"
          stroke-width="1"
        />

        <!-- Base connector — futuristic stem -->
        <rect class="base-seg s1" x="82" y="152" width="36" height="8" rx="2" fill="currentColor" />
        <rect class="base-seg s2" x="86" y="162" width="28" height="7" rx="2" fill="currentColor" />
        <rect class="base-seg s3" x="90" y="171" width="20" height="6" rx="2" fill="currentColor" />
        <!-- Base accent lines -->
        <line class="base-accent" x1="82" y1="156" x2="118" y2="156" stroke="currentColor" stroke-width="0.5" opacity="0.3" />
        <line class="base-accent" x1="86" y1="165" x2="114" y2="165" stroke="currentColor" stroke-width="0.5" opacity="0.3" />

        <!-- Interior animations (clipped to hex) -->
        <g clip-path="url(#core-clip)">
          <!-- Energy core -->
          <circle class="energy-core" cx="100" cy="82" r="28" fill="url(#core-energy)">
            <animate attributeName="r" values="24;32;24" dur="2.2s" repeatCount="indefinite" />
          </circle>

          <!-- Orbiting plasma blob 1 -->
          <ellipse class="plasma-blob" cx="100" cy="65" rx="18" ry="12" fill="url(#plasma-glow)" opacity="0.55">
            <animateTransform attributeName="transform" type="rotate" values="0 100 85;360 100 85" dur="5s" repeatCount="indefinite" />
            <animate attributeName="rx" values="18;10;18" dur="2.5s" repeatCount="indefinite" />
            <animate attributeName="ry" values="12;20;12" dur="2.5s" repeatCount="indefinite" />
          </ellipse>

          <!-- Orbiting plasma blob 2 (counter) -->
          <ellipse class="plasma-blob" cx="100" cy="105" rx="14" ry="10" fill="url(#plasma-glow)" opacity="0.4">
            <animateTransform attributeName="transform" type="rotate" values="360 100 85;0 100 85" dur="4s" repeatCount="indefinite" />
            <animate attributeName="rx" values="14;22;14" dur="2s" repeatCount="indefinite" />
            <animate attributeName="ry" values="10;6;10" dur="2s" repeatCount="indefinite" />
          </ellipse>

          <!-- Figure-8 wandering spark -->
          <ellipse class="plasma-blob" rx="10" ry="8" fill="url(#plasma-glow)" opacity="0.5">
            <animate attributeName="cx" values="75;125;75" dur="3.5s" repeatCount="indefinite" />
            <animate attributeName="cy" values="70;100;70" dur="1.75s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.3;0.6;0.3" dur="3.5s" repeatCount="indefinite" />
          </ellipse>

          <!-- Rising sparks -->
          <circle class="spark" r="2.5" fill="currentColor" opacity="0">
            <animate attributeName="cx" values="90;95;90" dur="2.4s" repeatCount="indefinite" />
            <animate attributeName="cy" values="130;45;130" dur="2.4s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0;0.8;0" dur="2.4s" repeatCount="indefinite" />
          </circle>
          <circle class="spark" r="2" fill="currentColor" opacity="0">
            <animate attributeName="cx" values="112;108;112" dur="2.9s" repeatCount="indefinite" />
            <animate attributeName="cy" values="125;40;125" dur="2.9s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0;0.7;0" dur="2.9s" repeatCount="indefinite" />
          </circle>
          <circle class="spark" r="1.8" fill="currentColor" opacity="0">
            <animate attributeName="cx" values="100;103;100" dur="2s" repeatCount="indefinite" />
            <animate attributeName="cy" values="135;35;135" dur="2s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0;0.9;0" dur="2s" repeatCount="indefinite" />
          </circle>

          <!-- Swirling dashed orbit -->
          <ellipse class="swirl-ring" cx="100" cy="85" rx="42" ry="16" fill="none" stroke="currentColor" stroke-width="1" stroke-dasharray="5 8" opacity="0.12">
            <animateTransform attributeName="transform" type="rotate" values="0 100 85;360 100 85" dur="7s" repeatCount="indefinite" />
            <animate attributeName="ry" values="16;28;16" dur="3.5s" repeatCount="indefinite" />
          </ellipse>

          <!-- Electric arc flashes -->
          <polyline class="electric-arc" points="65,110 80,80 70,65 95,50" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0">
            <animate attributeName="opacity" values="0;0.7;0;0;0" dur="3.2s" repeatCount="indefinite" />
          </polyline>
          <polyline class="electric-arc" points="135,105 120,78 130,60 105,48" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" opacity="0">
            <animate attributeName="opacity" values="0;0;0.6;0;0" dur="3.6s" repeatCount="indefinite" />
          </polyline>

          <!-- Scanning horizontal line -->
          <line class="scan-beam" x1="42" y1="85" x2="158" y2="85" stroke="currentColor" stroke-width="0.8" opacity="0">
            <animate attributeName="y1" values="55;145;55" dur="3s" repeatCount="indefinite" />
            <animate attributeName="y2" values="55;145;55" dur="3s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.3;0.1;0.3" dur="3s" repeatCount="indefinite" />
          </line>
        </g>

        <!-- Corner node accents (tech detail) -->
        <circle class="corner-node" cx="100" cy="18" r="3" fill="currentColor" opacity="0.4">
          <animate attributeName="opacity" values="0.4;0.8;0.4" dur="1.5s" repeatCount="indefinite" />
        </circle>
        <circle class="corner-node" cx="162" cy="52" r="2.5" fill="currentColor" opacity="0.3">
          <animate attributeName="opacity" values="0.3;0.7;0.3" dur="1.5s" begin="0.25s" repeatCount="indefinite" />
        </circle>
        <circle class="corner-node" cx="38" cy="52" r="2.5" fill="currentColor" opacity="0.3">
          <animate attributeName="opacity" values="0.3;0.7;0.3" dur="1.5s" begin="0.5s" repeatCount="indefinite" />
        </circle>
        <circle class="corner-node" cx="162" cy="118" r="2.5" fill="currentColor" opacity="0.3">
          <animate attributeName="opacity" values="0.3;0.7;0.3" dur="1.5s" begin="0.75s" repeatCount="indefinite" />
        </circle>
        <circle class="corner-node" cx="38" cy="118" r="2.5" fill="currentColor" opacity="0.3">
          <animate attributeName="opacity" values="0.3;0.7;0.3" dur="1.5s" begin="1s" repeatCount="indefinite" />
        </circle>
        <circle class="corner-node" cx="100" cy="152" r="3" fill="currentColor" opacity="0.4">
          <animate attributeName="opacity" values="0.4;0.8;0.4" dur="1.5s" begin="1.25s" repeatCount="indefinite" />
        </circle>
      </svg>
    </div>
    <span v-if="props.showText" class="thinking-text">Thinking</span>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(defineProps<{
  showText?: boolean
}>(), {
  showText: true
})

const hovered = ref(false)
</script>

<style scoped>
.thinking-lamp-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: default;
  position: relative;
  z-index: 0;
  isolation: isolate;
}

.thinking-lamp {
  position: relative;
  width: 24px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  transform-origin: center center;
  overflow: visible;
  contain: none;
}

.thinking-lamp.lamp-with-text {
  width: 22px;
  height: 27px;
}

.thinking-lamp.lamp-hovered {
  transform: scale(1.2);
}

/* === SVG === */
.lamp-svg {
  width: 100%;
  height: 100%;
  position: relative;
  z-index: 1;
  overflow: visible;
}

/* Hex frame — main body */
.hex-frame {
  color: #8b6914;
  animation: bulb-breathe 2.5s ease-in-out infinite;
  filter: drop-shadow(0 0 2px rgba(196, 138, 80, 0.3));
  transition: color 0.3s ease, filter 0.3s ease;
}

.thinking-lamp.lamp-hovered .hex-frame {
  color: #b8860b;
  filter: drop-shadow(0 0 6px rgba(196, 138, 80, 0.5));
}

/* Outer rotating hex ring */
.hex-ring.outer {
  color: #8b6914;
  opacity: 0.2;
  animation: hex-spin 12s linear infinite;
  transform-origin: 100px 85px;
}

.thinking-lamp.lamp-hovered .hex-ring.outer {
  opacity: 0.4;
  animation-duration: 6s;
}

/* Base connector */
.base-seg {
  color: #6b5a48;
  opacity: 0.8;
}

.base-seg.s1 { opacity: 0.9; }
.base-seg.s2 { opacity: 0.7; }
.base-seg.s3 { opacity: 0.55; }

/* === Sequential thinking rays === */
.thinking-ray {
  stroke: #1a1a1a;
  opacity: 0;
  animation: ray-sequential 3.5s ease-in-out infinite;
  transform-origin: center;
}

.ray-1 { animation-delay: 0s; }
.ray-2 { animation-delay: 0.2s; }
.ray-3 { animation-delay: 0.4s; }
.ray-4 { animation-delay: 0.6s; }
.ray-5 { animation-delay: 0.8s; }
.ray-6 { animation-delay: 1.0s; }
.ray-7 { animation-delay: 1.2s; }

.thinking-lamp.lamp-hovered .thinking-ray {
  animation-duration: 2s;
  stroke: #000;
}

/* Interior elements */
.energy-core {
  mix-blend-mode: screen;
}

.plasma-blob {
  mix-blend-mode: screen;
}

.spark {
  color: #c48a50;
}

.swirl-ring {
  color: #c48a50;
}

.electric-arc {
  color: #daa520;
  filter: drop-shadow(0 0 2px currentColor);
}

.scan-beam {
  color: #c48a50;
}

.corner-node {
  color: #c48a50;
}

.thinking-lamp.lamp-hovered .spark {
  color: #e0a030;
}

.thinking-lamp.lamp-hovered .electric-arc {
  filter: drop-shadow(0 0 5px currentColor);
}

/* === Thinking text === */
.thinking-text {
  font-size: 0.875rem;
  font-weight: 500;
  letter-spacing: 0.03em;
  background: linear-gradient(
    120deg,
    #3a3a3a 0%,
    #3a3a3a 38%,
    #c6894b 48%,
    #d8a26f 52%,
    #3a3a3a 62%,
    #3a3a3a 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: text-shimmer 2.5s ease-in-out infinite;
}

/* === Dark mode === */
:deep(.dark) .thinking-text,
.dark .thinking-text {
  background: linear-gradient(
    120deg,
    #fff6dd 0%,
    #fff2cc 38%,
    #ffd969 48%,
    #ffe9aa 54%,
    #fff3cf 62%,
    #fff6dd 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: text-shimmer 2.2s linear infinite;
}

:deep(.dark) .hex-frame,
.dark .hex-frame {
  color: #ffd67a;
  filter: drop-shadow(0 0 4px rgba(255, 214, 122, 0.4));
}

:deep(.dark) .thinking-lamp.lamp-hovered .hex-frame,
.dark .thinking-lamp.lamp-hovered .hex-frame {
  color: #ffe4a0;
  filter: drop-shadow(0 0 8px rgba(255, 214, 122, 0.6));
}

:deep(.dark) .hex-ring.outer,
.dark .hex-ring.outer {
  color: #ffd67a;
  opacity: 0.18;
}

:deep(.dark) .base-seg,
.dark .base-seg {
  color: #4a4038;
}

:deep(.dark) .thinking-ray,
.dark .thinking-ray {
  stroke: #ffd67a;
}

:deep(.dark) .thinking-lamp.lamp-hovered .thinking-ray,
.dark .thinking-lamp.lamp-hovered .thinking-ray {
  stroke: #ffe4a0;
}

:deep(.dark) .spark,
.dark .spark,
:deep(.dark) .corner-node,
.dark .corner-node,
:deep(.dark) .swirl-ring,
.dark .swirl-ring,
:deep(.dark) .scan-beam,
.dark .scan-beam {
  color: #ffe4a0;
}

:deep(.dark) .electric-arc,
.dark .electric-arc {
  color: #ffd67a;
  filter: drop-shadow(0 0 4px rgba(255, 214, 122, 0.6));
}

/* ============ KEYFRAMES ============ */

@keyframes bulb-breathe {
  0%, 100% {
    opacity: 0.75;
    filter: drop-shadow(0 0 2px rgba(196, 138, 80, 0.2));
  }
  50% {
    opacity: 1;
    filter: drop-shadow(0 0 5px rgba(196, 138, 80, 0.45));
  }
}

@keyframes hex-spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@keyframes ray-sequential {
  0% {
    opacity: 0;
    transform: scaleY(0.3);
  }
  8% {
    opacity: 0.7;
    transform: scaleY(1);
  }
  25% {
    opacity: 0.7;
    transform: scaleY(1);
  }
  40% {
    opacity: 0;
    transform: scaleY(0.3);
  }
  100% {
    opacity: 0;
    transform: scaleY(0.3);
  }
}

@keyframes text-shimmer {
  0% { background-position: 100% 0%; }
  100% { background-position: 0% 100%; }
}
</style>
