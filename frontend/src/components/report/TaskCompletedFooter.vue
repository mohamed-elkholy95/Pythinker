<template>
  <div class="task-completed-footer">
    <!-- Task completed row (always visible when feedback panel is closed) -->
    <div v-if="!showFeedback" class="footer-row">
      <div class="flex items-center gap-2">
        <Check class="w-4 h-4 text-[var(--function-success)]" />
        <span class="text-sm text-[var(--function-success)] font-medium whitespace-nowrap">{{ $t('Task completed') }}</span>
      </div>
      <!-- Rating stars only before submission -->
      <div v-if="!submitted" class="flex items-center gap-1 flex-shrink-0">
        <span class="text-xs text-[var(--text-tertiary)] mr-2 whitespace-nowrap">{{ $t('How was this result?') }}</span>
        <div class="flex items-center">
          <button
            v-for="i in 5"
            :key="i"
            class="star-btn"
            @click="handleStarClick(i)"
            @mouseenter="hoverRating = i"
            @mouseleave="hoverRating = 0"
          >
            <Star
              class="w-4 h-4 transition-colors"
              :class="i <= (hoverRating || rating) ? 'text-amber-400 fill-amber-400' : 'text-[var(--icon-tertiary)] group-hover:text-amber-300'"
            />
          </button>
        </div>
      </div>
    </div>

    <!-- Feedback panel - appears after clicking a star -->
    <div v-if="showFeedback && !submitted" class="feedback-panel">
      <div class="feedback-header">
        <span class="feedback-title">{{ $t('How was this result?') }}</span>
        <div class="flex items-center">
          <button
            v-for="i in 5"
            :key="i"
            class="star-btn"
            @click="rating = i"
            @mouseenter="hoverRating = i"
            @mouseleave="hoverRating = 0"
          >
            <Star
              class="w-5 h-5 transition-colors"
              :class="i <= (hoverRating || rating) ? 'text-amber-400 fill-amber-400' : 'text-[var(--icon-tertiary)]'"
            />
          </button>
        </div>
      </div>

      <div class="feedback-body">
        <label class="feedback-label">
          {{ $t('Comment') }}
          <span class="feedback-optional">({{ $t('optional') }})</span>
        </label>
        <textarea
          v-model="feedback"
          class="feedback-textarea"
          :placeholder="$t('Additional feedback')"
          rows="3"
        ></textarea>
      </div>

      <div class="feedback-footer">
        <label class="feedback-consent">
          <input type="checkbox" v-model="consentShare" class="feedback-checkbox" />
          <span>{{ $t('Help Pythinker improve with my feedback') }}</span>
        </label>
        <div class="feedback-actions">
          <button class="feedback-btn-skip" @click="submitRating(false)">{{ $t('Skip comment') }}</button>
          <button class="feedback-btn-submit" @click="submitRating(true)">{{ $t('Submit') }}</button>
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
const showFeedback = ref(false);
const feedback = ref('');
const consentShare = ref(true);
const submitted = ref(false);

const handleStarClick = (value: number) => {
  rating.value = value;
  showFeedback.value = true;
};

const submitRating = (includeFeedback: boolean) => {
  const feedbackText = includeFeedback && feedback.value.trim() ? feedback.value.trim() : undefined;
  emit('rate', rating.value, feedbackText);
  submitted.value = true;
  showFeedback.value = false;
};
</script>

<style scoped>
.task-completed-footer {
  width: 100%;
  margin-top: 8px;
}

.footer-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.star-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
}

.feedback-panel {
  margin-top: 12px;
  border: 1px solid var(--border-main);
  border-radius: 12px;
  background: var(--background-white-main);
  padding: 20px;
}

.feedback-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.feedback-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.feedback-body {
  margin-bottom: 16px;
}

.feedback-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.feedback-optional {
  color: var(--text-tertiary);
  font-weight: 400;
}

.feedback-textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-main);
  border-radius: 8px;
  background: var(--fill-tsp-white-main);
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.5;
  resize: none;
  outline: none;
  font-family: inherit;
}

.feedback-textarea::placeholder {
  color: var(--text-tertiary);
}

.feedback-textarea:focus {
  border-color: var(--border-dark);
}

.feedback-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.feedback-consent {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
}

.feedback-checkbox {
  width: 16px;
  height: 16px;
  accent-color: var(--bolt-elements-item-contentAccent);
  cursor: pointer;
}

.feedback-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.feedback-btn-skip {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  background: var(--background-white-main);
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.feedback-btn-skip:hover {
  background: var(--fill-tsp-white-main);
  border-color: var(--border-dark);
}

.feedback-btn-submit {
  padding: 6px 14px;
  border-radius: 8px;
  border: none;
  background: var(--text-primary);
  color: var(--background-white-main);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.feedback-btn-submit:hover {
  opacity: 0.85;
}
</style>
