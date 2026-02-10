<template>
  <div class="task-completed-footer">
    <div class="footer-row">
      <div class="status-wrap">
        <Check class="status-icon" />
        <span class="status-text">{{ $t('Task completed') }}</span>
      </div>

      <div class="rating-pill">
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
  margin-top: 8px;
  padding-bottom: 14px;
  border-bottom: 1px solid #d8dbe0;
}

.footer-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  width: 100%;
}

.status-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.status-icon {
  width: 19px;
  height: 19px;
  color: #43a849;
  stroke-width: 2.4;
}

.status-text {
  color: #43a849;
  font-size: 17px;
  font-weight: 500;
  letter-spacing: -0.01em;
}

.rating-pill {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 16px;
  background: #ebedf0;
  min-height: 44px;
}

.rating-title {
  font-size: 15px;
  font-weight: 500;
  color: #575d66;
  white-space: nowrap;
}

.rating-stars {
  display: inline-flex;
  align-items: center;
  gap: 1px;
}

.star-btn {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
}

.star-icon {
  width: 16px;
  height: 16px;
  transition: color 0.16s ease, fill 0.16s ease;
}

.star-inactive {
  color: #c4c8cf;
  fill: #c4c8cf;
}

.star-active {
  color: #f4b73f;
  fill: #f4b73f;
}

.star-btn:hover .star-inactive {
  color: #a9afb9;
  fill: #a9afb9;
}

@media (max-width: 900px) {
  .footer-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .rating-pill {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
