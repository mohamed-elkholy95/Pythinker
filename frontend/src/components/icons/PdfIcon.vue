<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 32
})

const viewBox = computed(() => `0 0 32 32`)
</script>

<template>
  <svg
    :width="props.size"
    :height="props.size"
    :viewBox="viewBox"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path
      d="M3.55566 26.8889C3.55566 28.6071 4.94856 30 6.66678 30H25.3334C27.0517 30 28.4446 28.6071 28.4446 26.8889V9.77778L20.6668 2H6.66678C4.94856 2 3.55566 3.39289 3.55566 5.11111V26.8889Z"
      fill="#EA5355"
    />
    <path
      d="M20.6685 6.66647C20.6685 8.38469 22.0613 9.77759 23.7796 9.77759H28.4462L20.6685 1.99981V6.66647Z"
      fill="#F49B9C"
    />
    <text
      x="50%"
      y="60%"
      text-anchor="middle"
      dominant-baseline="middle"
      fill="white"
      font-size="10"
      font-weight="700"
      font-family="system-ui, -apple-system, sans-serif"
    >
      PDF
    </text>
  </svg>
</template>
