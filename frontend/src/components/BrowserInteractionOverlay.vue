<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'

const props = defineProps<{
  lastAction?: {
    type: 'navigate' | 'click' | 'scroll_up' | 'scroll_down' | 'type'
    url?: string
    x?: number
    y?: number
    text?: string
  }
  containerWidth: number
  containerHeight: number
  scaleX: number
  scaleY: number
}>()

const clickRipple = ref<{ x: number; y: number; visible: boolean }>({
  x: 0,
  y: 0,
  visible: false,
})
const scrollIndicator = ref<{ direction: 'up' | 'down'; visible: boolean }>({
  direction: 'down',
  visible: false,
})

let rippleTimeout: ReturnType<typeof setTimeout> | null = null
let scrollTimeout: ReturnType<typeof setTimeout> | null = null

function clearAllTimeouts() {
  if (rippleTimeout) clearTimeout(rippleTimeout)
  if (scrollTimeout) clearTimeout(scrollTimeout)
}

watch(
  () => props.lastAction,
  (action) => {
    if (!action) return

    if (action.type === 'click' && action.x != null && action.y != null) {
      clickRipple.value = {
        x: action.x * props.scaleX,
        y: action.y * props.scaleY,
        visible: true,
      }
      if (rippleTimeout) clearTimeout(rippleTimeout)
      rippleTimeout = setTimeout(() => {
        clickRipple.value.visible = false
      }, 600)
    }

    if (action.type === 'scroll_up' || action.type === 'scroll_down') {
      scrollIndicator.value = {
        direction: action.type === 'scroll_up' ? 'up' : 'down',
        visible: true,
      }
      if (scrollTimeout) clearTimeout(scrollTimeout)
      scrollTimeout = setTimeout(() => {
        scrollIndicator.value.visible = false
      }, 800)
    }
  },
  { deep: true },
)

onUnmounted(() => {
  clearAllTimeouts()
})
</script>

<template>
  <div class="interaction-overlay">
    <!-- Click Ripple -->
    <Transition name="ripple">
      <div
        v-if="clickRipple.visible"
        class="click-ripple"
        :style="{ left: clickRipple.x + 'px', top: clickRipple.y + 'px' }"
      />
    </Transition>

    <!-- Scroll Indicator -->
    <Transition name="scroll-ind">
      <div
        v-if="scrollIndicator.visible"
        class="scroll-indicator"
        :class="scrollIndicator.direction"
      >
        <span v-if="scrollIndicator.direction === 'up'">&#x25B2;</span>
        <span v-else>&#x25BC;</span>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.interaction-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 10;
  overflow: hidden;
}

.click-ripple {
  position: absolute;
  width: 30px;
  height: 30px;
  margin-left: -15px;
  margin-top: -15px;
  border-radius: 50%;
  background: rgba(37, 99, 235, 0.25);
  animation: ripple-expand 0.5s ease-out forwards;
}

:global(.dark) .click-ripple {
  background: rgba(122, 162, 247, 0.3);
}

@keyframes ripple-expand {
  0% {
    transform: scale(0.3);
    opacity: 1;
  }

  100% {
    transform: scale(2.5);
    opacity: 0;
  }
}

.ripple-enter-active {
  animation: ripple-expand 0.5s ease-out;
}

.ripple-leave-active {
  transition: opacity 0.1s;
}

.ripple-leave-to {
  opacity: 0;
}

.scroll-indicator {
  position: absolute;
  right: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(4px);
  color: #2563eb;
  font-size: 14px;
}

:global(.dark) .scroll-indicator {
  background: rgba(26, 27, 38, 0.7);
  color: #7aa2f7;
}

.scroll-indicator.up {
  top: 40px;
}

.scroll-indicator.down {
  bottom: 40px;
}

.scroll-ind-enter-active {
  transition: all 0.2s ease-out;
}

.scroll-ind-leave-active {
  transition: all 0.3s ease-in;
}

.scroll-ind-enter-from {
  opacity: 0;
  transform: scale(0.5);
}

.scroll-ind-leave-to {
  opacity: 0;
}
</style>
