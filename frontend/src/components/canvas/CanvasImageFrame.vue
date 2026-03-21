<template>
  <div class="canvas-image-frame">
    <div class="canvas-image-frame__info-bar">
      <span class="canvas-image-frame__filename">{{ filename }}</span>
      <span class="canvas-image-frame__dimensions">{{ width }} &times; {{ height }}</span>
    </div>

    <div
      class="canvas-image-frame__container"
      :class="{ 'is-selected': selected }"
    >
      <img
        :src="imageUrl"
        :alt="filename"
        class="canvas-image-frame__image"
        :style="imageStyle"
        draggable="false"
      />

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
import { computed } from 'vue'

interface Props {
  imageUrl: string
  filename: string
  width: number
  height: number
  zoom: number
  selected: boolean
}

const props = defineProps<Props>()

const imageStyle = computed(() => ({
  transform: `scale(${props.zoom})`,
  transformOrigin: 'center center',
}))
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
  border: 2px solid #3b82f6;
  border-radius: var(--radius-lg);
}

.canvas-image-frame__image {
  display: block;
  max-width: 100%;
  height: auto;
  border-radius: var(--radius-lg);
  user-select: none;
}

.canvas-image-frame__handle {
  position: absolute;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #3b82f6;
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
