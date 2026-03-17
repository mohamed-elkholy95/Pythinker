<template>
    <svg xmlns="http://www.w3.org/2000/svg" :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" fill="none">
        <text
            x="50%"
            y="55%"
            dominant-baseline="middle"
            text-anchor="middle"
            fill="var(--logo-color)"
            font-family="var(--font-sans)"
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
    default: 100
  },
  height: {
    type: [String, Number],
    default: 38
  }
})

const fontSize = computed(() => {
  const h = typeof props.height === 'string' ? parseFloat(props.height) : props.height
  return Math.round(h * 0.55)
})
</script>
