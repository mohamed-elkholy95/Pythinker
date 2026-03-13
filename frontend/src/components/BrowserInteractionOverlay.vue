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

const navToast = ref<{ url: string; visible: boolean }>({ url: '', visible: false })
const clickRipple = ref<{ x: number; y: number; visible: boolean }>({
  x: 0,
  y: 0,
  visible: false,
})
const scrollIndicator = ref<{ direction: 'up' | 'down'; visible: boolean }>({
  direction: 'down',
  visible: false,
})

let navTimeout: ReturnType<typeof setTimeout> | null = null
let rippleTimeout: ReturnType<typeof setTimeout> | null = null
let scrollTimeout: ReturnType<typeof setTimeout> | null = null

function clearAllTimeouts() {
  if (navTimeout) clearTimeout(navTimeout)
  if (rippleTimeout) clearTimeout(rippleTimeout)
  if (scrollTimeout) clearTimeout(scrollTimeout)
}

watch(
  () => props.lastAction,
  (action) => {
    if (!action) return

    if (action.type === 'navigate' && action.url) {
      navToast.value = { url: action.url, visible: true }
      if (navTimeout) clearTimeout(navTimeout)
      navTimeout = setTimeout(() => {
        navToast.value.visible = false
      }, 2500)
    }

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
    <!-- Navigation Toast -->
    <Transition name="nav-toast">
      <div v-if="navToast.visible" class="nav-toast">
        <span class="nav-icon">&#x1F310;</span>
        <span class="nav-url">{{ navToast.url }}</span>
      </div>
    </Transition>

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

.nav-toast {
  position: absolute;
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 14px;
  background: rgba(26, 27, 38, 0.85);
  backdrop-filter: blur(8px);
  border-radius: 16px;
  border: 1px solid rgba(122, 162, 247, 0.3);
  color: #c0caf5;
  font-size: 11px;
  max-width: 80%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.nav-icon {
  font-size: 12px;
}

.nav-url {
  opacity: 0.9;
}

.nav-toast-enter-active {
  transition: all 0.3s ease-out;
}

.nav-toast-leave-active {
  transition: all 0.4s ease-in;
}

.nav-toast-enter-from {
  opacity: 0;
  transform: translateX(-50%) translateY(-10px);
}

.nav-toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-5px);
}

.click-ripple {
  position: absolute;
  width: 30px;
  height: 30px;
  margin-left: -15px;
  margin-top: -15px;
  border-radius: 50%;
  background: rgba(122, 162, 247, 0.3);
  animation: ripple-expand 0.5s ease-out forwards;
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
  background: rgba(26, 27, 38, 0.7);
  backdrop-filter: blur(4px);
  color: #7aa2f7;
  font-size: 14px;
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
