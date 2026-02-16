<template>
  <div class="thinking-lamp-wrapper" @mouseenter="hovered = true" @mouseleave="hovered = false">
    <div class="thinking-lamp" :class="{ 'lamp-with-text': props.showText, 'lamp-hovered': hovered }">
      <!-- Scan line sweeping across -->
      <div class="scan-line"></div>

      <!-- Core energy ring -->
      <div class="energy-ring"></div>

      <!-- The lamp SVG -->
      <svg
        class="lamp-svg"
        viewBox="0 0 32 36"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <!-- Animated gradient for bulb -->
          <linearGradient id="bulb-fuel" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#f8e5c4" stop-opacity="0.35" />
            <stop offset="40%" stop-color="#f2c88a" stop-opacity="0.65" />
            <stop offset="100%" stop-color="#e3a45a" stop-opacity="0.9" />
          </linearGradient>
          <!-- Circuit pattern clip -->
          <clipPath id="bulb-clip">
            <path d="M16 3C10.48 3 6 7.48 6 13c0 3.68 2 6.9 5 8.65V24c0 .55.45 1 1 1h8c.55 0 1-.45 1-1v-2.35c3-1.75 5-4.97 5-8.65 0-5.52-4.48-10-10-10z" />
          </clipPath>
        </defs>

        <!-- Outer hex frame -->
        <path
          class="hex-frame"
          d="M16 1 L27 7 L27 19 L16 25 L5 19 L5 7 Z"
          stroke-width="0.5"
          fill="none"
        />

        <!-- Bulb body — futuristic capsule -->
        <path
          class="lamp-bulb"
          d="M16 3C10.48 3 6 7.48 6 13c0 3.68 2 6.9 5 8.65V24c0 .55.45 1 1 1h8c.55 0 1-.45 1-1v-2.35c3-1.75 5-4.97 5-8.65 0-5.52-4.48-10-10-10z"
        />

        <!-- Internal circuit lines -->
        <g class="circuit-lines" clip-path="url(#bulb-clip)">
          <line x1="10" y1="8" x2="10" y2="22" stroke-width="0.3" />
          <line x1="14" y1="5" x2="14" y2="22" stroke-width="0.3" />
          <line x1="18" y1="5" x2="18" y2="22" stroke-width="0.3" />
          <line x1="22" y1="8" x2="22" y2="22" stroke-width="0.3" />
          <line x1="6" y1="10" x2="26" y2="10" stroke-width="0.3" />
          <line x1="6" y1="16" x2="26" y2="16" stroke-width="0.3" />
        </g>

        <!-- Bulb outline -->
        <path
          class="lamp-outline"
          d="M16 3C10.48 3 6 7.48 6 13c0 3.68 2 6.9 5 8.65V24c0 .55.45 1 1 1h8c.55 0 1-.45 1-1v-2.35c3-1.75 5-4.97 5-8.65 0-5.52-4.48-10-10-10z"
          stroke-width="0.6"
          fill="none"
        />

        <!-- Core filament — energy arc -->
        <path
          class="lamp-filament core"
          d="M13 14c0-1.65 1.35-3 3-3s3 1.35 3 3"
          stroke-width="0.8"
          stroke-linecap="round"
          fill="none"
        />
        <line class="lamp-filament stem" x1="13.5" y1="16" x2="13.5" y2="20" stroke-width="0.5" stroke-linecap="round" />
        <line class="lamp-filament stem" x1="18.5" y1="16" x2="18.5" y2="20" stroke-width="0.5" stroke-linecap="round" />
        <!-- Energy node at filament peak -->
        <circle class="filament-node" cx="16" cy="11" r="1" />

        <!-- Base — segmented tech connector -->
        <rect class="lamp-base seg-1" x="11" y="25.5" width="10" height="1.5" rx="0.3" />
        <rect class="lamp-base seg-2" x="12" y="27.5" width="8" height="1.5" rx="0.3" />
        <rect class="lamp-base seg-3" x="13" y="29.5" width="6" height="1.2" rx="0.3" />
        <!-- Base accent lines -->
        <line class="base-accent" x1="11" y1="26.3" x2="21" y2="26.3" stroke-width="0.3" />
        <line class="base-accent" x1="12" y1="28.3" x2="20" y2="28.3" stroke-width="0.3" />

        <!-- Light rays — angular/geometric (extended) -->
        <line class="lamp-ray ray-1" x1="3" y1="13" x2="-1" y2="13" stroke-width="0.7" stroke-linecap="round" />
        <line class="lamp-ray ray-2" x1="5.5" y1="5.5" x2="2" y2="2" stroke-width="0.7" stroke-linecap="round" />
        <line class="lamp-ray ray-3" x1="16" y1="0.5" x2="16" y2="-3" stroke-width="0.7" stroke-linecap="round" />
        <line class="lamp-ray ray-4" x1="26.5" y1="5.5" x2="30" y2="2" stroke-width="0.7" stroke-linecap="round" />
        <line class="lamp-ray ray-5" x1="29" y1="13" x2="33" y2="13" stroke-width="0.7" stroke-linecap="round" />
        <!-- Secondary short rays (extended) -->
        <line class="lamp-ray-s ray-s1" x1="4" y1="9" x2="1.5" y2="7" stroke-width="0.4" stroke-linecap="round" />
        <line class="lamp-ray-s ray-s2" x1="10" y1="2.5" x2="8" y2="-0.5" stroke-width="0.4" stroke-linecap="round" />
        <line class="lamp-ray-s ray-s3" x1="22" y1="2.5" x2="24" y2="-0.5" stroke-width="0.4" stroke-linecap="round" />
        <line class="lamp-ray-s ray-s4" x1="28" y1="9" x2="30.5" y2="7" stroke-width="0.4" stroke-linecap="round" />
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

/* Hover: slight scale + faster animations */
.thinking-lamp.lamp-hovered {
  transform: scale(1.15);
}

.thinking-lamp.lamp-hovered .lamp-bulb {
  animation-duration: 1.2s !important;
}

.thinking-lamp.lamp-hovered .lamp-ray {
  animation-duration: 1.5s !important;
}

.thinking-lamp.lamp-hovered .scan-line {
  animation-duration: 0.8s !important;
}

.thinking-lamp.lamp-hovered .energy-ring {
  opacity: 0.5;
  transform: scale(1.3);
}

.thinking-lamp.lamp-hovered .filament-node {
  animation-duration: 0.4s !important;
}

/* === Scan line — sweeps top to bottom === */
.scan-line {
  position: absolute;
  top: 0;
  left: 10%;
  right: 10%;
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, #c48a50 50%, transparent 100%);
  opacity: 0.4;
  animation: scan-sweep 2s linear infinite;
  pointer-events: none;
  z-index: 2;
}

/* === Energy ring — subtle rotating border === */
.energy-ring {
  position: absolute;
  top: -2px;
  left: -2px;
  right: -2px;
  bottom: 6px;
  border-radius: 50%;
  border: 0.5px solid transparent;
  border-top-color: rgba(196, 138, 80, 0.3);
  border-right-color: rgba(196, 138, 80, 0.1);
  animation: ring-spin 4s linear infinite;
  pointer-events: none;
  opacity: 0.3;
  transition: opacity 0.3s ease, transform 0.3s ease;
}

/* === SVG lamp === */
.lamp-svg {
  width: 100%;
  height: 100%;
  position: relative;
  z-index: 1;
  overflow: hidden;
}

/* Hex frame — faint geometric border */
.hex-frame {
  stroke: #3d3020;
  stroke-dasharray: 3 2;
  stroke-dashoffset: 0;
  animation: hex-rotate 8s linear infinite;
  opacity: 0.25;
}

/* Bulb fill — muted orange with fuel gradient */
.lamp-bulb {
  fill: url(#bulb-fuel);
  animation: bulb-glow 2.5s ease-in-out infinite;
}

/* Bulb outline — dark stroke */
.lamp-outline {
  stroke: #3b2a1a;
  animation: outline-pulse 2.5s ease-in-out infinite;
}

/* Circuit lines inside bulb */
.circuit-lines line {
  stroke: #3b2a1a;
  opacity: 0.12;
  animation: circuit-flicker 3s ease-in-out infinite;
}

.circuit-lines line:nth-child(odd) {
  animation-delay: 0.5s;
}

/* Filament — dark energy arc */
.lamp-filament {
  stroke: #4a3017;
  opacity: 0.7;
  animation: filament-flicker 1.8s ease-in-out infinite;
}

.lamp-filament.core {
  stroke-width: 0.8;
  animation: filament-pulse 1.8s ease-in-out infinite;
}

.lamp-filament.stem {
  opacity: 0.5;
}

/* Energy node — pulsing dot at filament peak */
.filament-node {
  fill: #f2b66b;
  opacity: 0.8;
  animation: node-pulse 0.8s ease-in-out infinite;
}

/* Base segments — tech connector look */
.lamp-base {
  fill: #6b5a48;
}

.lamp-base.seg-1 {
  fill: #7a6852;
}

.lamp-base.seg-2 {
  fill: #6b5a48;
}

.lamp-base.seg-3 {
  fill: #5a4a3a;
}

.base-accent {
  stroke: #2a2018;
  opacity: 0.4;
}

/* Light rays — dark warm tone, sequential left-to-right sweep */
.lamp-ray {
  stroke: #5a3d1e;
  opacity: 0;
  animation: ray-appear 3.6s ease-in-out infinite;
}

.ray-1 { animation-delay: 0s; }
.ray-2 { animation-delay: 0.4s; }
.ray-3 { animation-delay: 0.8s; }
.ray-4 { animation-delay: 1.2s; }
.ray-5 { animation-delay: 1.6s; }

/* Secondary short rays — staggered between primaries */
.lamp-ray-s {
  stroke: #6b4c2a;
  opacity: 0;
  animation: ray-appear-s 3.6s ease-in-out infinite;
}

.ray-s1 { animation-delay: 0.2s; }
.ray-s2 { animation-delay: 0.6s; }
.ray-s3 { animation-delay: 1.0s; }
.ray-s4 { animation-delay: 1.4s; }

/* === Thinking text === */
.thinking-text {
  font-size: 0.875rem;
  font-weight: 500;
  letter-spacing: 0.03em;
  background: linear-gradient(
    110deg,
    #6b7280 0%,
    #6b7280 35%,
    #9ca3af 45%,
    #d1d5db 50%,
    #f3f4f6 52%,
    #d1d5db 55%,
    #9ca3af 60%,
    #6b7280 70%,
    #6b7280 100%
  );
  background-size: 350% 350%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: text-shimmer 2.8s ease-in-out infinite;
}

/* === Dark mode === */
:deep(.dark) .thinking-text,
.dark .thinking-text {
  background: linear-gradient(
    110deg,
    #9ca3af 0%,
    #9ca3af 35%,
    #d1d5db 45%,
    #e5e7eb 50%,
    #ffffff 52%,
    #e5e7eb 55%,
    #d1d5db 60%,
    #9ca3af 70%,
    #9ca3af 100%
  );
  background-size: 350% 350%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  filter: none;
  animation: text-shimmer 2.8s ease-in-out infinite;
}

:deep(.dark) .thinking-lamp,
.dark .thinking-lamp {
  filter: none;
  animation: none;
}

:deep(.dark) .lamp-bulb,
.dark .lamp-bulb {
  opacity: 0.98;
  filter: saturate(1.3) brightness(1.18) contrast(1.04);
}

:deep(.dark) .lamp-outline,
.dark .lamp-outline {
  stroke: #c58e3f;
  opacity: 0.9;
}

:deep(.dark) .hex-frame,
.dark .hex-frame {
  stroke: #f2c274;
  opacity: 0.28;
}

:deep(.dark) .lamp-filament,
.dark .lamp-filament {
  stroke: #ffd989;
  opacity: 0.92;
}

:deep(.dark) .circuit-lines line,
.dark .circuit-lines line {
  stroke: #f1c173;
  opacity: 0.14;
}

:deep(.dark) .lamp-base.seg-1,
.dark .lamp-base.seg-1 {
  fill: #4a4038;
}

:deep(.dark) .lamp-base.seg-2,
.dark .lamp-base.seg-2 {
  fill: #3e3530;
}

:deep(.dark) .lamp-base.seg-3,
.dark .lamp-base.seg-3 {
  fill: #332a25;
}

:deep(.dark) .base-accent,
.dark .base-accent {
  stroke: #f4cb86;
  opacity: 0.28;
}

:deep(.dark) .lamp-ray,
.dark .lamp-ray {
  stroke: #ffcc44;
  filter: drop-shadow(0 0 1.5px rgba(255, 204, 68, 0.4));
}

:deep(.dark) .lamp-ray-s,
.dark .lamp-ray-s {
  stroke: #ffd966;
  filter: drop-shadow(0 0 1px rgba(255, 217, 102, 0.3));
}

:deep(.dark) .scan-line,
.dark .scan-line {
  background: linear-gradient(90deg, transparent 0%, #ffd57a 50%, transparent 100%);
  opacity: 0.45;
}

:deep(.dark) .energy-ring,
.dark .energy-ring {
  border-top-color: rgba(255, 216, 120, 0.28);
  border-right-color: rgba(255, 216, 120, 0.12);
  opacity: 0.22;
}

:deep(.dark) .filament-node,
.dark .filament-node {
  fill: #ffe9ae;
  filter: none;
}

/* ============ KEYFRAMES ============ */

@keyframes bulb-glow {
  0%, 100% {
    opacity: 0.85;
  }
  50% {
    opacity: 1;
  }
}

@keyframes outline-pulse {
  0%, 100% {
    stroke-opacity: 0.5;
  }
  50% {
    stroke-opacity: 0.9;
  }
}

@keyframes circuit-flicker {
  0%, 100% {
    opacity: 0.08;
  }
  50% {
    opacity: 0.2;
  }
}

@keyframes filament-flicker {
  0%, 100% {
    opacity: 0.5;
  }
  30% {
    opacity: 0.85;
  }
  60% {
    opacity: 0.6;
  }
}

@keyframes filament-pulse {
  0%, 100% {
    stroke: #4a3017;
    opacity: 0.6;
  }
  50% {
    stroke: #6d4220;
    opacity: 0.9;
  }
}

@keyframes node-pulse {
  0%, 100% {
    opacity: 0.5;
    r: 0.8;
  }
  50% {
    opacity: 1;
    r: 1.2;
  }
}

@keyframes ray-appear {
  0%, 5% {
    opacity: 0;
    transform: scaleX(0);
  }
  15% {
    opacity: 0;
    transform: scaleX(0.2);
  }
  25%, 40% {
    opacity: 0.6;
    transform: scaleX(1);
  }
  55%, 100% {
    opacity: 0;
    transform: scaleX(0.2);
  }
}

@keyframes ray-appear-s {
  0%, 8% {
    opacity: 0;
    transform: scale(0);
  }
  20% {
    opacity: 0;
    transform: scale(0.2);
  }
  30%, 42% {
    opacity: 0.4;
    transform: scale(1);
  }
  58%, 100% {
    opacity: 0;
    transform: scale(0.2);
  }
}

@keyframes scan-sweep {
  0% {
    top: 0%;
    opacity: 0;
  }
  10% {
    opacity: 0.4;
  }
  90% {
    opacity: 0.4;
  }
  100% {
    top: 85%;
    opacity: 0;
  }
}

@keyframes ring-spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

@keyframes hex-rotate {
  0% {
    stroke-dashoffset: 0;
  }
  100% {
    stroke-dashoffset: 30;
  }
}

@keyframes text-shimmer {
  0% {
    background-position: 100% 0%;
  }
  100% {
    background-position: 0% 100%;
  }
}
</style>
