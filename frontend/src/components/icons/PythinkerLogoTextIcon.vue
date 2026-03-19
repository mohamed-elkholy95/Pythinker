<template>
  <svg
    data-testid="pythinker-wordmark"
    xmlns="http://www.w3.org/2000/svg"
    :width="width"
    :height="height"
    viewBox="0 0 164 32"
    preserveAspectRatio="xMinYMid meet"
    fill="none"
    aria-hidden="true"
  >
    <text
      x="0"
      y="24"
      text-anchor="start"
      fill="var(--logo-color)"
      font-family="'Instrument Sans', var(--font-sans)"
      font-size="28"
      letter-spacing="-0.045em"
      text-rendering="geometricPrecision"
    >
      <tspan font-weight="700">Py</tspan>
      <tspan fill="var(--text-primary)" fill-opacity="0.94" font-weight="600">thinker</tspan>
    </text>
  </svg>
</template>
<script setup lang="ts">
defineProps({
  width: {
    type: [String, Number],
    default: 120
  },
  height: {
    type: [String, Number],
    default: 24
  }
})
</script>
