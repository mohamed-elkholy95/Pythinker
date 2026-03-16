<template>
  <div class="final-summary-card" data-testid="final-summary-card">
    <div class="final-summary-content markdown-content" v-html="htmlContent" />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  htmlContent: string;
}>();
</script>

<style scoped>
.final-summary-card {
  width: 100%;
  max-width: 704px;
  margin: 4px 0 14px;
  padding: 0;
}

.final-summary-content {
  color: var(--text-primary);
  font-size: 15.25px;
  line-height: 1.34;
  font-weight: 400;
  letter-spacing: -0.003em;
  text-wrap: pretty;
  text-align: left;
  white-space: normal;
}

.final-summary-content :deep(p) {
  margin: 0;
}

.final-summary-content :deep(p + p) {
  margin-top: 10px;
}

.final-summary-content :deep(strong) {
  font-weight: 700;
  color: var(--text-primary);
}

.final-summary-content :deep(ul),
.final-summary-content :deep(ol) {
  margin: 8px 0 10px;
  padding-left: 0;
  list-style: none;
}

.final-summary-content :deep(li) {
  margin: 8px 0;
  line-height: 1.34;
}

:global(.dark) .final-summary-content {
  color: #d5dbe4;
}
</style>
