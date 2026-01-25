<template>
  <div class="task-completed-footer w-[600px] flex items-center justify-between px-4 py-3 mt-2 rounded-xl bg-[var(--fill-tsp-white-main)] border border-[var(--border-light)]">
    <div class="flex items-center gap-2 flex-shrink-0">
      <Check class="w-4 h-4 text-[var(--function-success)]" />
      <span class="text-sm text-[var(--function-success)] font-medium whitespace-nowrap">{{ $t('Task completed') }}</span>
    </div>
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
