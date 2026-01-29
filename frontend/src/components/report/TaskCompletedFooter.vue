<template>
  <div class="task-completed-footer-wrapper w-full flex items-center justify-between mt-2 gap-4">
    <!-- Task completed indicator -->
    <div class="flex items-center gap-2">
      <Check class="w-4 h-4 text-[var(--function-success)]" />
      <span class="text-sm text-[var(--function-success)] font-medium whitespace-nowrap">{{ $t('Task completed') }}</span>
    </div>

    <!-- Rating section - positioned at far right -->
    <div class="flex items-center gap-1 flex-shrink-0">
      <span class="text-xs text-[var(--text-tertiary)] mr-2 whitespace-nowrap">{{ $t('How was this result?') }}</span>
      <div class="flex items-center">
        <button
          v-for="i in 5"
          :key="i"
          class="w-6 h-6 flex items-center justify-center group"
          @click="rate(i)"
          @mouseenter="hoverRating = i"
          @mouseleave="hoverRating = 0"
        >
          <Star
            class="w-4 h-4 transition-colors"
            :class="i <= (hoverRating || rating) ? 'text-yellow-400 fill-yellow-400' : 'text-[var(--icon-tertiary)] group-hover:text-yellow-300'"
          />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { Check, Star } from 'lucide-vue-next';

const emit = defineEmits<{
  (e: 'rate', rating: number): void;
}>();

const rating = ref(0);
const hoverRating = ref(0);

const rate = (value: number) => {
  rating.value = value;
  emit('rate', value);
};
</script>
