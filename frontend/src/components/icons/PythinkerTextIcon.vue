<template>
    <svg xmlns="http://www.w3.org/2000/svg" :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" fill="none">
        <text
            x="50%"
            y="55%"
            dominant-baseline="middle"
            text-anchor="middle"
            fill="var(--logo-color)"
            font-family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            font-weight="600"
            :font-size="fontSize"
            letter-spacing="-0.02em"
        >Pythinker</text>
    </svg>
</template>
<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps({
  width: {
    type: [String, Number],
    default: 70
  },
  height: {
    type: [String, Number],
    default: 12
  }
})

const fontSize = computed(() => {
  const h = typeof props.height === 'string' ? parseFloat(props.height) : props.height
  return Math.round(h * 0.9)
})
</script>
