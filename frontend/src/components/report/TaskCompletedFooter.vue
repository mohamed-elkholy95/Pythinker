<template>
  <div class="task-completed-footer">
    <!-- Phase 1: Inline star row (before any star is clicked) -->
    <div v-if="phase === 'initial' && props.showRating" class="footer-row">
      <div class="status-wrap">
        <Check class="status-icon" />
        <span class="status-text">{{ $t('Task completed') }}</span>
      </div>

      <div class="rating-panel">
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

    <!-- Phase 1: No rating variant -->
    <div v-if="phase === 'initial' && !props.showRating" class="footer-row">
      <div class="status-wrap">
        <Check class="status-icon" />
        <span class="status-text">{{ $t('Task completed') }}</span>
      </div>
    </div>

    <!-- Phase 2: Expanded rating card (after clicking a star) -->
    <div v-if="phase === 'expanded'" class="rating-card">
      <div class="rating-card-inner">
        <!-- Header: title + stars -->
        <div class="rating-card-header">
          <span class="rating-card-title">{{ $t('How was this result?') }}</span>
          <div class="rating-stars">
            <button
              v-for="i in 5"
              :key="i"
              class="star-btn"
              @click="rating = i"
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

        <!-- Comment textarea -->
        <div class="comment-section">
          <div class="comment-label-row">
            <span class="comment-label">{{ $t('Comment') }}</span>
            <span class="comment-optional">({{ $t('optional') }})</span>
          </div>
          <div class="comment-input-wrap">
            <textarea
              v-model="feedback"
              class="comment-textarea"
              :placeholder="$t('Additional feedback')"
              rows="3"
            />
          </div>
        </div>

        <!-- Footer: consent checkbox + buttons -->
        <div class="rating-card-footer">
          <label class="consent-label">
            <span class="consent-checkbox-wrap">
              <input
                v-model="consentChecked"
                type="checkbox"
                class="consent-checkbox-input"
              />
              <span v-if="consentChecked" class="consent-checkbox-icon consent-checked">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" width="16" height="16">
                  <rect width="16" height="16" rx="4" fill="currentColor" />
                  <path fill-rule="evenodd" clip-rule="evenodd" d="M12.4021 5.05176C12.722 5.37869 12.7162 5.903 12.3893 6.22283L7.31009 11.1916C6.98822 11.5065 6.47375 11.5065 6.15189 11.1916L3.6123 8.70721C3.28537 8.38738 3.2796 7.86307 3.59943 7.53613C3.91926 7.20919 4.44357 7.20343 4.77051 7.52326L6.73099 9.44112L11.2311 5.03889C11.558 4.71906 12.0823 4.72482 12.4021 5.05176Z" fill="white" />
                </svg>
              </span>
              <span v-else class="consent-checkbox-icon consent-unchecked">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" width="16" height="16">
                  <rect x="0.5" y="0.5" width="15" height="15" rx="3.5" stroke="currentColor" fill="none" />
                </svg>
              </span>
            </span>
            <span class="consent-text">{{ $t('Help Pythinker improve with my feedback') }}</span>
          </label>

          <div class="rating-card-buttons">
            <button
              type="button"
              class="btn-skip"
              @click="handleSkip"
            >
              {{ $t('Skip comment') }}
            </button>
            <button
              type="button"
              class="btn-submit"
              @click="handleSubmit"
            >
              {{ $t('Submit') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Phase 3: Submitted confirmation -->
    <div v-if="phase === 'submitted'" class="footer-row">
      <div class="status-wrap">
        <Check class="status-icon" />
        <span class="status-text">{{ $t('Task completed') }}</span>
      </div>
      <div class="submitted-badge">
        <Check :size="14" />
        <span>{{ $t('Rating submitted') }}</span>
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

const phase = ref<'initial' | 'expanded' | 'submitted'>('initial');
const rating = ref(0);
const hoverRating = ref(0);
const feedback = ref('');
const consentChecked = ref(true);

const handleStarClick = (value: number) => {
  rating.value = value;
  phase.value = 'expanded';
};

const handleSkip = () => {
  if (!consentChecked.value) {
    phase.value = 'submitted';
    return;
  }
  emit('rate', rating.value);
  phase.value = 'submitted';
};

const handleSubmit = () => {
  if (!consentChecked.value) {
    phase.value = 'submitted';
    return;
  }
  const trimmed = feedback.value.trim();
  emit('rate', rating.value, trimmed || undefined);
  phase.value = 'submitted';
};
</script>

<style scoped>
.task-completed-footer {
  width: 100%;
  max-width: 100%;
  margin-top: 4px;
  overflow-x: visible;
}

/* ── Phase 1: Inline row ─────────────────────── */
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

/* ── Shared star styles ──────────────────────── */
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
  color: var(--function-warning);
}

.star-btn:hover .star-inactive {
  color: var(--text-tertiary);
}

/* ── Phase 2: Expanded rating card ───────────── */
.rating-card {
  background: var(--background-menu-white);
  border-radius: 12px;
  width: 100%;
  border: 0.5px solid var(--border-dark);
  margin-top: 8px;
}

.rating-card-inner {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
}

.rating-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.rating-card-title {
  color: var(--text-primary);
  font-size: 16px;
  font-weight: 600;
  line-height: 22px;
}

/* ── Comment section ─────────────────────────── */
.comment-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.comment-label-row {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  line-height: 20px;
}

.comment-label {
  color: var(--text-primary);
  font-weight: 500;
}

.comment-optional {
  color: var(--text-tertiary);
}

.comment-input-wrap {
  background: var(--fill-tsp-white-light);
  border-radius: 8px;
  width: 100%;
}

.comment-textarea {
  width: 100%;
  min-height: 76px;
  background: transparent;
  border: none;
  resize: none;
  font-size: 14px;
  line-height: 20px;
  padding: 8px 12px;
  color: var(--text-primary);
  font-family: inherit;
  outline: none;
}

.comment-textarea::placeholder {
  color: var(--text-disable);
}

.comment-textarea:focus {
  outline: none;
  box-shadow: none;
}

/* ── Footer: consent + buttons ───────────────── */
.rating-card-footer {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.consent-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  flex-shrink: 0;
}

.consent-checkbox-wrap {
  position: relative;
  align-self: center;
  width: 16px;
  height: 16px;
}

.consent-checkbox-input {
  position: absolute;
  inset: 0;
  margin: 0;
  opacity: 0;
  cursor: pointer;
}

.consent-checkbox-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.consent-checked {
  color: var(--icon-blue, #3b82f6);
}

.consent-unchecked {
  color: var(--border-dark);
}

.consent-text {
  color: var(--text-tertiary);
  font-size: 13px;
  line-height: 18px;
}

.rating-card-buttons {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.btn-skip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
  font-weight: 500;
  font-size: 14px;
  line-height: 18px;
  min-height: 32px;
  min-width: 64px;
  padding: 4px 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: opacity 0.16s ease;
  background: var(--Button-primary-white);
  color: var(--text-primary);
  border: 1px solid var(--border-btn-main);
  box-shadow: none;
}

.btn-skip:hover {
  opacity: 0.7;
}

.btn-skip:active {
  opacity: 0.6;
}

.btn-submit {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
  font-weight: 500;
  font-size: 14px;
  line-height: 18px;
  min-height: 32px;
  min-width: 64px;
  padding: 4px 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: opacity 0.16s ease;
  background: var(--Button-primary-black);
  color: var(--text-onblack);
  border: none;
}

.btn-submit:hover {
  opacity: 0.9;
}

.btn-submit:active {
  opacity: 0.8;
}

/* ── Phase 3: Submitted badge ────────────────── */
.submitted-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 8px;
  background: var(--fill-tsp-gray-main);
  color: var(--function-success);
  font-size: 13px;
  font-weight: 500;
  line-height: 18px;
  margin-left: auto;
}

/* ── Responsive ──────────────────────────────── */
@media (max-width: 900px) {
  .footer-row {
    flex-wrap: wrap;
    align-items: flex-start;
  }

  .rating-panel {
    margin-left: auto;
  }

  .rating-card-footer {
    flex-direction: column;
    align-items: flex-start;
  }

  .rating-card-buttons {
    margin-left: 0;
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
