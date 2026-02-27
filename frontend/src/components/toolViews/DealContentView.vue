<template>
  <ContentContainer
    :centered="false"
    :constrained="false"
    padding="none"
    class="deal-view"
  >
    <!-- Active State: Scanning deals -->
    <div v-if="isSearching" class="deal-container">
      <div class="deal-search-bar">
        <div class="deal-search-icon-wrap">
          <Tag :size="12" class="deal-search-icon" />
        </div>
        <input
          class="deal-search-input"
          :value="content?.query || ''"
          placeholder="Scanning deals..."
          readonly
        />
        <span class="scanning-pill">
          <span class="scanning-bars">
            <span class="scanning-bar"></span>
            <span class="scanning-bar"></span>
            <span class="scanning-bar"></span>
          </span>
          Scanning deals
        </span>
      </div>

      <!-- Progressive deal cards as they stream in -->
      <div v-if="displayDeals.length > 0" class="deal-cards-list">
        <TransitionGroup name="deal-card-slide">
          <DealCard
            v-for="(deal, index) in displayDeals"
            :key="deal.url || index"
            :deal="deal"
            :is-best="index === content?.best_deal_index"
            :index="index"
            @click="handleDealClick(deal)"
          />
        </TransitionGroup>
      </div>

      <!-- Skeleton loading when no deals yet -->
      <div v-else class="deal-skeleton">
        <div v-for="i in 3" :key="i" class="skeleton-card" :style="{ animationDelay: `${i * 0.12}s` }">
          <div class="skeleton-card-header">
            <div class="skeleton-store"></div>
            <div class="skeleton-price"></div>
          </div>
          <div class="skeleton-product"></div>
          <div class="skeleton-score"></div>
        </div>
      </div>

      <!-- Activity bar -->
      <div class="deal-activity-bar">
        <div class="activity-scanner">
          <div class="scanner-line"></div>
        </div>
        <span class="activity-text">
          {{ displayDeals.length }} deal{{ displayDeals.length !== 1 ? 's' : '' }} found
        </span>
      </div>
    </div>

    <!-- Completed State: All deals loaded -->
    <div v-else class="deal-container">
      <div class="deal-search-bar deal-search-bar--done">
        <div class="deal-search-icon-wrap">
          <Tag :size="12" class="deal-search-icon" />
        </div>
        <input
          class="deal-search-input"
          :value="content?.query || ''"
          placeholder="Deal search"
          readonly
        />
        <span v-if="sortedDeals.length > 0" class="results-count-pill">
          {{ sortedDeals.length }} deal{{ sortedDeals.length !== 1 ? 's' : '' }}
        </span>
      </div>

      <!-- Deal Cards -->
      <div v-if="sortedDeals.length > 0 || sortedCoupons.length > 0" class="deal-cards-list">
        <DealCard
          v-for="(deal, index) in sortedDeals"
          :key="deal.url || index"
          :deal="deal"
          :is-best="index === 0"
          :index="index"
          @click="handleDealClick(deal)"
        />

        <!-- Coupon Section -->
        <div v-if="sortedCoupons.length > 0" class="coupon-section">
          <div class="coupon-section-header">
            <Ticket :size="13" />
            <span>Coupons &amp; Promo Codes</span>
            <span class="coupon-count">{{ sortedCoupons.length }}</span>
          </div>
          <div class="coupon-grid">
            <CouponCard
              v-for="(coupon, index) in sortedCoupons"
              :key="coupon.code || index"
              :coupon="coupon"
            />
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-else class="deal-empty-state">
        <div class="empty-icon-wrap">
          <Tag :size="24" />
        </div>
        <p class="deal-empty-text">No deals found</p>
        <p v-if="content?.query" class="deal-empty-query">for "{{ content.query }}"</p>
      </div>
    </div>
  </ContentContainer>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Tag, Ticket } from 'lucide-vue-next';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
import DealCard from '@/components/toolViews/shared/DealCard.vue';
import CouponCard from '@/components/toolViews/shared/CouponCard.vue';
import { useStaggeredResults } from '@/composables/useStaggeredResults';
import type { DealToolContent, DealItem } from '@/types/toolContent';

const props = defineProps<{
  content: DealToolContent | null;
  isSearching?: boolean;
}>();

const emit = defineEmits<{
  (e: 'browseUrl', url: string): void;
}>();

// Progressive result reveal during active search
const { visibleResults } = useStaggeredResults(
  computed(() => props.content?.deals ?? []),
  { delayMs: 200, enabled: props.isSearching ?? false }
);

const displayDeals = computed(() => {
  if (props.isSearching) return visibleResults.value;
  return props.content?.deals ?? [];
});

// Sort deals by score (descending) when completed
const sortedDeals = computed(() => {
  const deals = [...(props.content?.deals ?? [])];
  return deals.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
});

// Sort coupons: verified first, then by store
const sortedCoupons = computed(() => {
  const coupons = [...(props.content?.coupons ?? [])];
  return coupons.sort((a, b) => {
    if (a.verified !== b.verified) return a.verified ? -1 : 1;
    return a.store.localeCompare(b.store);
  });
});

function handleDealClick(deal: DealItem) {
  if (deal.url) emit('browseUrl', deal.url);
}
</script>

<style scoped>
.deal-view {
  height: 100%;
  background: var(--background-white-main);
  font-family: var(--font-sans);
}

.deal-container {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* ── Search Bar ── */
.deal-search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  margin: 8px 8px 4px 8px;
  border-radius: 10px;
  border: 1px solid rgba(234, 88, 12, 0.2);
  background: linear-gradient(135deg, #fffbf7, #fff7ed);
  box-shadow: 0 2px 8px rgba(234, 88, 12, 0.06);
  transition: all 0.3s ease;
}

.deal-search-bar--done {
  border-color: var(--border-light);
  background: var(--background-white-main);
  box-shadow: 0 2px 8px var(--shadow-XS);
}

:global(.dark) .deal-search-bar {
  background: linear-gradient(135deg, rgba(234, 88, 12, 0.06), rgba(234, 88, 12, 0.03));
  border-color: rgba(234, 88, 12, 0.15);
}

:global(.dark) .deal-search-bar--done {
  background: var(--background-white-main);
  border-color: var(--border-light);
}

.deal-search-icon-wrap {
  width: 20px;
  height: 20px;
  border-radius: 5px;
  background: linear-gradient(135deg, #ea580c, #dc2626);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.deal-search-icon {
  color: #ffffff;
}

.deal-search-input {
  border: none;
  outline: none;
  background: transparent;
  width: 100%;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.deal-search-input::placeholder {
  color: var(--text-tertiary);
}

/* ── Scanning pill with audio-bar animation ── */
.scanning-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.03em;
  color: #c2410c;
  background: linear-gradient(135deg, #fff7ed, #ffedd5);
  border: 1px solid rgba(234, 88, 12, 0.2);
  white-space: nowrap;
}

:global(.dark) .scanning-pill {
  color: #fb923c;
  background: rgba(234, 88, 12, 0.12);
  border-color: rgba(234, 88, 12, 0.25);
}

.scanning-bars {
  display: flex;
  align-items: center;
  gap: 1.5px;
  height: 10px;
}

.scanning-bar {
  width: 2px;
  background: #ea580c;
  border-radius: 1px;
  animation: scanning-bar-bounce 0.8s ease-in-out infinite;
}

.scanning-bar:nth-child(1) { height: 4px; animation-delay: 0s; }
.scanning-bar:nth-child(2) { height: 7px; animation-delay: 0.15s; }
.scanning-bar:nth-child(3) { height: 5px; animation-delay: 0.3s; }

@keyframes scanning-bar-bounce {
  0%, 100% { transform: scaleY(0.5); }
  50% { transform: scaleY(1.4); }
}

.results-count-pill {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-tertiary);
  background: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-light);
  white-space: nowrap;
}

/* ── Deal Cards List ── */
.deal-cards-list {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow-y: auto;
  padding: 4px 8px 8px;
  gap: 5px;
}

/* ── Card slide-in transition ── */
.deal-card-slide-enter-active {
  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
.deal-card-slide-enter-from {
  opacity: 0;
  transform: translateY(16px) scale(0.96);
}

/* ── Coupon Section ── */
.coupon-section {
  margin-top: 6px;
}

.coupon-section-header {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 4px 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.01em;
}

.coupon-count {
  font-size: 9px;
  font-weight: 700;
  color: var(--text-tertiary);
  background: var(--fill-tsp-gray-main);
  border-radius: 999px;
  padding: 1px 5px;
  margin-left: auto;
}

.coupon-grid {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* ── Skeleton Loading ── */
.deal-skeleton {
  padding: 4px 8px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  flex: 1;
}

.skeleton-card {
  border-radius: 10px;
  border: 1px solid var(--border-light);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  animation: skeleton-card-enter 0.5s ease-out both;
}

@keyframes skeleton-card-enter {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.skeleton-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.skeleton-store {
  width: 80px;
  height: 12px;
  border-radius: 4px;
  background: var(--fill-tsp-gray-main);
  animation: skeleton-shimmer 1.8s ease-in-out infinite;
}

.skeleton-price {
  width: 60px;
  height: 18px;
  border-radius: 6px;
  background: linear-gradient(135deg, var(--fill-tsp-gray-main), rgba(234, 88, 12, 0.06));
  animation: skeleton-shimmer 1.8s ease-in-out infinite;
  animation-delay: 0.1s;
}

.skeleton-product {
  width: 75%;
  height: 10px;
  border-radius: 4px;
  background: var(--fill-tsp-gray-main);
  animation: skeleton-shimmer 1.8s ease-in-out infinite;
  animation-delay: 0.2s;
}

.skeleton-score {
  width: 40%;
  height: 3px;
  border-radius: 2px;
  background: var(--fill-tsp-gray-main);
  animation: skeleton-shimmer 1.8s ease-in-out infinite;
  animation-delay: 0.3s;
}

@keyframes skeleton-shimmer {
  0%, 100% { opacity: 0.35; }
  50% { opacity: 0.75; }
}

/* ── Activity bar with scanner effect ── */
.deal-activity-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  border-top: 1px solid var(--border-light);
  background: var(--background-white-main);
  flex-shrink: 0;
}

.activity-scanner {
  width: 24px;
  height: 4px;
  border-radius: 2px;
  background: rgba(234, 88, 12, 0.1);
  overflow: hidden;
  position: relative;
}

.scanner-line {
  position: absolute;
  top: 0;
  left: 0;
  width: 50%;
  height: 100%;
  border-radius: 2px;
  background: linear-gradient(90deg, #ea580c, #f97316);
  animation: scanner-sweep 1.2s ease-in-out infinite;
}

@keyframes scanner-sweep {
  0% { left: -50%; }
  100% { left: 100%; }
}

.activity-text {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 500;
  letter-spacing: -0.005em;
}

/* ── Empty State ── */
.deal-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.empty-icon-wrap {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: linear-gradient(135deg, #fff7ed, #ffedd5);
  border: 1px solid rgba(234, 88, 12, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ea580c;
  margin-bottom: 12px;
}

:global(.dark) .empty-icon-wrap {
  background: rgba(234, 88, 12, 0.1);
  border-color: rgba(234, 88, 12, 0.2);
  color: #fb923c;
}

.deal-empty-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0;
}

.deal-empty-query {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 4px 0 0;
  font-style: italic;
}
</style>
