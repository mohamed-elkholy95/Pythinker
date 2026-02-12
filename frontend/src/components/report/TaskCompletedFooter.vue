<template>
  <div class="task-completed-footer">
    <div class="footer-row">
      <div class="status-wrap">
        <Check class="status-icon" />
        <span class="status-text">{{ $t('Task completed') }}</span>
      </div>

      <div v-if="props.showRating" class="rating-panel">
        <span class="rating-title">{{ $t('How was this result?') }}</span>
        <div class="rating-stars">
          <button
            v-for="i in 5"
            :key="i"
            class="star-btn"
            @click="handleStarClick(i)"
            @mouseenter="hoverRating = i"
            @mouseleave="hoverRating = 0"
            :aria-label="`Rate ${i}`"
            type="button"
          >
            <Star
              class="star-icon"
              :class="i <= (hoverRating || rating) ? 'star-active' : 'star-inactive'"
            />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { Check, Star } from 'lucide-vue-next';

const props = withDefaults(
  defineProps<{
    showRating?: boolean;
  }>(),
  {
    showRating: true,
  },
);

const emit = defineEmits<{
  (e: 'rate', rating: number, feedback?: string): void;
}>();

const rating = ref(0);
const hoverRating = ref(0);

const handleStarClick = (value: number) => {
  rating.value = value;
  emit('rate', value);
};
</script>

<style scoped>
.task-completed-footer {
  width: 100%;
  max-width: 100%;
  margin-top: 4px;
  overflow-x: visible;
}

.footer-row {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: nowrap;
  min-width: 0;
}

.status-wrap {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  border-radius: 9999px;
  color: var(--function-success);
}

.status-icon {
  width: 18px;
  height: 18px;
  stroke-width: 2.5;
  flex-shrink: 0;
}

.status-text {
  color: var(--function-success);
  font-size: 14px;
  line-height: 20px;
  font-weight: 500;
}

.rating-panel {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  padding: 6px 12px 6px 16px;
  border-radius: 8px;
  background: var(--fill-tsp-gray-main);
  min-height: 36px;
  margin-left: auto;
  flex-shrink: 0;
}

.rating-title {
  font-size: 14px;
  line-height: 20px;
  font-weight: 400;
  color: var(--text-secondary);
  white-space: nowrap;
}

.rating-stars {
  display: inline-flex;
  align-items: center;
  gap: 0;
}

.star-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  border-radius: 0;
  cursor: pointer;
  padding: 2px;
  line-height: 0;
  transition: opacity 0.16s ease;
}

.star-btn:hover {
  opacity: 0.85;
}

.star-btn:focus-visible {
  outline: 2px solid var(--border-input-active);
  outline-offset: 1px;
}

.star-icon {
  width: 16px;
  height: 16px;
  stroke: none;
  fill: currentColor;
  transition: color 0.16s ease;
}

.star-inactive {
  color: var(--border-dark);
}

.star-active {
  color: #f5c36b;
}

.star-btn:hover .star-inactive {
  color: #a8adb6;
}

@media (max-width: 900px) {
  .footer-row {
    flex-wrap: wrap;
    align-items: flex-start;
  }

  .rating-panel {
    margin-left: auto;
  }
}
</style>
