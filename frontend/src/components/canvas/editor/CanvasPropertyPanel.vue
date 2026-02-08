<template>
  <div class="property-panel">
    <div v-if="!element" class="empty-state">
      <span class="empty-label">No selection</span>
    </div>

    <template v-else>
      <!-- Header -->
      <div class="panel-section">
        <div class="section-title">{{ element.type }}</div>
        <input
          class="prop-input name-input"
          :value="element.name"
          @change="emitUpdate('name', ($event.target as HTMLInputElement).value)"
          placeholder="Element name"
        />
      </div>

      <!-- Position -->
      <div class="panel-section">
        <div class="section-title">Position</div>
        <div class="prop-row">
          <label class="prop-label">X</label>
          <input
            class="prop-input"
            type="number"
            :value="Math.round(element.x)"
            @change="emitUpdate('x', Number(($event.target as HTMLInputElement).value))"
          />
          <label class="prop-label">Y</label>
          <input
            class="prop-input"
            type="number"
            :value="Math.round(element.y)"
            @change="emitUpdate('y', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
      </div>

      <!-- Size -->
      <div class="panel-section">
        <div class="section-title">Size</div>
        <div class="prop-row">
          <label class="prop-label">W</label>
          <input
            class="prop-input"
            type="number"
            :value="Math.round(element.width)"
            min="1"
            @change="emitUpdate('width', Math.max(1, Number(($event.target as HTMLInputElement).value)))"
          />
          <label class="prop-label">H</label>
          <input
            class="prop-input"
            type="number"
            :value="Math.round(element.height)"
            min="1"
            @change="emitUpdate('height', Math.max(1, Number(($event.target as HTMLInputElement).value)))"
          />
        </div>
      </div>

      <!-- Rotation -->
      <div class="panel-section">
        <div class="section-title">Rotation</div>
        <div class="prop-row">
          <input
            class="prop-slider"
            type="range"
            min="0"
            max="360"
            step="1"
            :value="Math.round(element.rotation)"
            @input="emitUpdate('rotation', Number(($event.target as HTMLInputElement).value))"
          />
          <span class="prop-value">{{ Math.round(element.rotation) }}&deg;</span>
        </div>
      </div>

      <!-- Opacity -->
      <div class="panel-section">
        <div class="section-title">Opacity</div>
        <div class="prop-row">
          <input
            class="prop-slider"
            type="range"
            min="0"
            max="1"
            step="0.01"
            :value="element.opacity"
            @input="emitUpdate('opacity', Number(($event.target as HTMLInputElement).value))"
          />
          <span class="prop-value">{{ Math.round(element.opacity * 100) }}%</span>
        </div>
      </div>

      <!-- Fill color -->
      <div class="panel-section">
        <div class="section-title">Fill</div>
        <div class="prop-row color-row">
          <div
            class="color-swatch"
            :style="{ background: fillColor }"
          />
          <input
            class="prop-input"
            type="text"
            :value="fillColor"
            @change="handleFillChange(($event.target as HTMLInputElement).value)"
            placeholder="#000000"
          />
        </div>
      </div>

      <!-- Corner radius (rectangle only) -->
      <div v-if="element.type === 'rectangle'" class="panel-section">
        <div class="section-title">Corner Radius</div>
        <div class="prop-row">
          <input
            class="prop-input"
            type="number"
            min="0"
            :value="element.corner_radius"
            @change="emitUpdate('corner_radius', Math.max(0, Number(($event.target as HTMLInputElement).value)))"
          />
        </div>
      </div>

      <!-- Text content (text only) -->
      <template v-if="element.type === 'text'">
        <div class="panel-section">
          <div class="section-title">Text</div>
          <textarea
            class="prop-textarea"
            :value="element.text || ''"
            @input="emitUpdate('text', ($event.target as HTMLTextAreaElement).value)"
            rows="3"
            placeholder="Enter text..."
          />
        </div>
        <div class="panel-section">
          <div class="section-title">Font Size</div>
          <div class="prop-row">
            <input
              class="prop-input"
              type="number"
              min="1"
              :value="fontSize"
              @change="handleFontSizeChange(Number(($event.target as HTMLInputElement).value))"
            />
          </div>
        </div>
      </template>

      <!-- Image source (image only) -->
      <div v-if="element.type === 'image' && element.src" class="panel-section">
        <div class="section-title">Image Source</div>
        <div class="image-src-display">{{ element.src }}</div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CanvasElement } from '@/types/canvas'

const props = defineProps<{
  element: CanvasElement | null
}>()

const emit = defineEmits<{
  (e: 'property-change', elementId: string, updates: Partial<CanvasElement>): void
}>()

const fillColor = computed(() => {
  if (!props.element?.fill) return 'transparent'
  const fill = props.element.fill as Record<string, unknown>
  if (fill.type === 'solid' && typeof fill.color === 'string') return fill.color
  return 'transparent'
})

const fontSize = computed(() => {
  if (!props.element?.text_style) return 16
  const style = props.element.text_style as Record<string, unknown>
  return (style.font_size as number) || 16
})

function emitUpdate(key: string, value: unknown) {
  if (!props.element) return
  emit('property-change', props.element.id, { [key]: value })
}

function handleFillChange(color: string) {
  if (!props.element) return
  emit('property-change', props.element.id, {
    fill: { type: 'solid', color },
  })
}

function handleFontSizeChange(size: number) {
  if (!props.element) return
  const existing = (props.element.text_style ?? {}) as Record<string, unknown>
  emit('property-change', props.element.id, {
    text_style: { ...existing, font_size: Math.max(1, size) },
  })
}
</script>

<style scoped>
.property-panel {
  width: 260px;
  height: 100%;
  overflow-y: auto;
  background: var(--background-white-main, #ffffff);
  border-left: 1px solid var(--border-light, #e5e5e5);
  flex-shrink: 0;
  padding: 12px;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.empty-label {
  color: var(--text-tertiary, #999999);
  font-size: 13px;
}

.panel-section {
  margin-bottom: 16px;
}

.section-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-tertiary, #999999);
  margin-bottom: 6px;
}

.prop-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.prop-label {
  font-size: 12px;
  color: var(--text-secondary, #666666);
  width: 16px;
  flex-shrink: 0;
}

.prop-input {
  flex: 1;
  height: 28px;
  border: 1px solid var(--border-light, #e5e5e5);
  border-radius: 6px;
  padding: 0 8px;
  font-size: 12px;
  color: var(--text-primary, #1a1a1a);
  background: var(--background-white-main, #ffffff);
  outline: none;
  transition: border-color 0.15s;
}

.prop-input:focus {
  border-color: var(--text-secondary, #666666);
}

.name-input {
  width: 100%;
}

.prop-slider {
  flex: 1;
  height: 4px;
  appearance: none;
  background: var(--border-light, #e5e5e5);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}

.prop-slider::-webkit-slider-thumb {
  appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--text-primary, #1a1a1a);
  cursor: pointer;
}

.prop-value {
  font-size: 11px;
  color: var(--text-secondary, #666666);
  min-width: 36px;
  text-align: right;
}

.color-row {
  gap: 8px;
}

.color-swatch {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid var(--border-light, #e5e5e5);
  flex-shrink: 0;
}

.prop-textarea {
  width: 100%;
  border: 1px solid var(--border-light, #e5e5e5);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  color: var(--text-primary, #1a1a1a);
  background: var(--background-white-main, #ffffff);
  outline: none;
  resize: vertical;
  font-family: inherit;
  transition: border-color 0.15s;
}

.prop-textarea:focus {
  border-color: var(--text-secondary, #666666);
}

.image-src-display {
  font-size: 11px;
  color: var(--text-secondary, #666666);
  word-break: break-all;
  padding: 6px 8px;
  background: var(--fill-tsp-gray-main, #f5f5f5);
  border-radius: 6px;
}
</style>
