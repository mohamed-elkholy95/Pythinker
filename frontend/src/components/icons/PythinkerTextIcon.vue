<template>
    <svg xmlns="http://www.w3.org/2000/svg" :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" fill="none">
        <text
            x="0"
            y="55%"
            dominant-baseline="middle"
            text-anchor="start"
            fill="var(--text-primary)"
            font-family="var(--font-display)"
            font-weight="600"
            :font-size="fontSize"
            letter-spacing="-0.01em"
        >Pythinker</text>
    </svg>
</template>
<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps({
  width: {
    type: [String, Number],
    default: 110
  },
  height: {
    type: [String, Number],
    default: 20
  }
})

const fontSize = computed(() => {
  const h = typeof props.height === 'string' ? parseFloat(props.height) : props.height
  return Math.round(h * 0.85)
})
</script>
