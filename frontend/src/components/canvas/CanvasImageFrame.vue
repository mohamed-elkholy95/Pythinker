<template>
  <div class="canvas-image-frame" :style="{ width: displayWidth }">
    <div class="canvas-image-frame__info-bar">
      <span class="canvas-image-frame__filename">{{ filename }}</span>
      <span class="canvas-image-frame__dimensions">{{ width }} &times; {{ height }}</span>
    </div>

    <div
      class="canvas-image-frame__container"
      :class="{ 'is-selected': selected }"
    >
      <img
        v-if="!imageError"
        :src="imageUrl"
        :alt="filename"
        class="canvas-image-frame__image"
        :style="{ width: displayWidth, height: displayHeight, transition: 'width 100ms ease, height 100ms ease' }"
        draggable="false"
        @error="imageError = true"
      />
      <div v-else class="canvas-image-frame__error">
        <span>Failed to load image</span>
      </div>

      <template v-if="selected">
        <span class="canvas-image-frame__handle is-top-left" />
        <span class="canvas-image-frame__handle is-top-right" />
        <span class="canvas-image-frame__handle is-bottom-left" />
        <span class="canvas-image-frame__handle is-bottom-right" />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

interface Props {
  imageUrl: string
  filename: string
  width: number
  height: number
  zoom: number
  selected: boolean
}

const props = defineProps<Props>()

const imageError = ref(false)

const displayWidth = computed(() => `${props.width * props.zoom}px`)
const displayHeight = computed(() => `${props.height * props.zoom}px`)
</script>

<style scoped>
.canvas-image-frame {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}

.canvas-image-frame__info-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 0 var(--space-2);
}

.canvas-image-frame__filename {
  font-size: 13px;
  font-weight: var(--font-medium);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.canvas-image-frame__dimensions {
  font-size: 13px;
  color: var(--text-tertiary);
  flex-shrink: 0;
  margin-left: var(--space-3);
}

.canvas-image-frame__container {
  position: relative;
  display: inline-flex;
  border-radius: var(--radius-lg);
  overflow: visible;
}

.canvas-image-frame__container.is-selected {
  border: 2px solid var(--canvas-selection-color, #3b82f6);
  border-radius: var(--radius-lg);
}

.canvas-image-frame__image {
  display: block;
  border-radius: var(--radius-lg);
  user-select: none;
}

.canvas-image-frame__error {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 200px;
  background: var(--fill-tsp-gray-main);
  border-radius: var(--radius-lg);
  color: var(--text-tertiary);
  font-size: 14px;
}

.canvas-image-frame__handle {
  position: absolute;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--canvas-selection-color, #3b82f6);
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  z-index: 2;
}

.canvas-image-frame__handle.is-top-left {
  top: -5px;
  left: -5px;
  cursor: nwse-resize;
}

.canvas-image-frame__handle.is-top-right {
  top: -5px;
  right: -5px;
  cursor: nesw-resize;
}

.canvas-image-frame__handle.is-bottom-left {
  bottom: -5px;
  left: -5px;
  cursor: nesw-resize;
}

.canvas-image-frame__handle.is-bottom-right {
  bottom: -5px;
  right: -5px;
  cursor: nwse-resize;
}
</style>
