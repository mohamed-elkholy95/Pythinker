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
          :value="content?.query || checkpointData?.query || ''"
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

      <!-- Progress bar -->
      <div v-if="progressPercent != null && progressPercent > 0" class="deal-progress-bar">
        <div class="progress-fill" :style="{ width: `${progressPercent}%` }"></div>
      </div>

      <!-- Store status grid -->
      <div v-if="mergedStoreStatuses.length > 0" class="store-status-grid">
        <span
          v-for="s in mergedStoreStatuses"
          :key="s.store"
          class="store-chip"
          :class="`store-chip--${s.status}`"
        >
          <Loader2 v-if="s.status === 'pending'" :size="10" class="store-chip-icon spinning" />
          <Check v-else-if="s.status === 'found'" :size="10" class="store-chip-icon" />
          <X v-else-if="s.status === 'failed'" :size="10" class="store-chip-icon" />
          <Minus v-else :size="10" class="store-chip-icon" />
          {{ s.store }}
          <span v-if="s.status === 'found' && s.result_count > 0" class="store-chip-count">
            {{ s.result_count }}
          </span>
        </span>
      </div>

      <!-- Step description -->
      <div v-if="currentStep" class="deal-step-text">
        {{ currentStep }}
      </div>

      <!-- Progressive deal cards from checkpoint_data -->
      <div v-if="progressiveDeals.length > 0" class="deal-cards-list">
        <TransitionGroup name="deal-card-slide">
          <DealCard
            v-for="(deal, index) in progressiveDeals"
            :key="deal.url || index"
            :deal="deal"
            :is-best="false"
            :index="index"
            @click="handleDealClick(deal)"
          />
        </TransitionGroup>
      </div>

      <!-- Skeleton loading when no deals yet and no store statuses -->
      <div v-else-if="mergedStoreStatuses.length === 0" class="deal-skeleton">
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
          {{ storeProgressLabel }}
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

      <!-- Enhanced Empty State -->
      <div v-else class="deal-empty-state">
        <div class="empty-icon-wrap">
          <component :is="emptyIcon" :size="22" />
        </div>
        <p class="deal-empty-title">{{ emptyTitle }}</p>
        <p v-if="emptySubtitle" class="deal-empty-subtitle">{{ emptySubtitle }}</p>
        <p v-if="emptyReason === 'no_matches' && content?.query" class="deal-empty-query">for "{{ content.query }}"</p>

        <!-- Final store status grid (shows which stores were checked) -->
        <div v-if="showStoreDiagnostics && finalStoreStatuses.length > 0" class="empty-stores-searched">
          <div class="empty-stores-header">
            <Store :size="11" />
            <span>Searched {{ finalStoreStatuses.length }} store{{ finalStoreStatuses.length !== 1 ? 's' : '' }}</span>
          </div>
          <div class="empty-stores-list">
            <span
              v-for="s in finalStoreStatuses"
              :key="s.store"
              class="empty-store-chip"
              :class="{
                'empty-store-chip--error': s.status === 'failed',
                'empty-store-chip--found': s.status === 'found',
              }"
            >
              <Check v-if="s.status === 'found' || s.status === 'empty'" :size="9" class="store-result-icon" />
              <X v-else-if="s.status === 'failed'" :size="9" class="store-result-icon store-result-icon--error" />
              {{ s.store }}
            </span>
          </div>
        </div>

        <!-- Fallback: show searchedStores if no checkpoint data -->
        <div v-else-if="showStoreDiagnostics && searchedStores.length > 0" class="empty-stores-searched">
          <div class="empty-stores-header">
            <Store :size="11" />
            <span>Searched {{ searchedStores.length }} store{{ searchedStores.length !== 1 ? 's' : '' }}</span>
          </div>
          <div class="empty-stores-list">
            <span
              v-for="store in searchedStores"
              :key="store"
              class="empty-store-chip"
              :class="{ 'empty-store-chip--error': storeErrors[store] }"
            >
              <span v-if="storeErrors[store]" class="store-error-dot"></span>
              {{ store }}
            </span>
          </div>
        </div>

        <!-- Store errors detail -->
        <div v-if="showStoreDiagnostics && errorStoreCount > 0" class="empty-errors-note">
          <AlertTriangle :size="11" />
          <span>{{ errorStoreCount }} store{{ errorStoreCount !== 1 ? 's' : '' }} had issues</span>
        </div>

        <!-- Suggestions -->
        <div v-if="emptyReason === 'no_matches'" class="empty-suggestions">
          <p class="empty-suggestions-label">Suggestions</p>
          <ul class="empty-suggestions-list">
            <li>Try a more specific product name</li>
            <li>Check if the product is sold by major retailers</li>
            <li>Software/digital products may not have deals</li>
          </ul>
        </div>
      </div>
    </div>
  </ContentContainer>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Tag, Ticket, SearchX, Store, AlertTriangle, Check, X, Loader2, Minus, CloudOff } from 'lucide-vue-next';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
import DealCard from '@/components/toolViews/shared/DealCard.vue';
import CouponCard from '@/components/toolViews/shared/CouponCard.vue';
import type { DealEmptyReason, DealToolContent, DealItem, DealProgressData, StoreStatus } from '@/types/toolContent';

const props = defineProps<{
  content: DealToolContent | null;
  isSearching?: boolean;
  progressPercent?: number;
  currentStep?: string;
  checkpointData?: DealProgressData | null;
  activeStores?: string[];
}>();

const emit = defineEmits<{
  (e: 'browseUrl', url: string): void;
}>();

// ── Store status merging ──
// Combines activeStores (all expected) with checkpointData.store_statuses (completed ones)
const mergedStoreStatuses = computed((): StoreStatus[] => {
  const stores = props.activeStores ?? [];
  const reported = props.checkpointData?.store_statuses ?? [];
  const reportedMap = new Map(reported.map(s => [s.store, s]));

  return stores.map(storeName => {
    const match = reportedMap.get(storeName);
    if (match) return match;
    return { store: storeName, status: 'pending' as const, result_count: 0 };
  });
});

// Final store statuses for empty state (from checkpoint data)
const finalStoreStatuses = computed((): StoreStatus[] => {
  return props.checkpointData?.store_statuses ?? [];
});

// Progressive deals from checkpoint_data during search
const progressiveDeals = computed((): DealItem[] => {
  const partials = props.checkpointData?.partial_deals ?? [];
  return partials
    .filter(d => d.store && (d.price != null && d.price > 0))
    .map(d => ({
      store: d.store ?? '',
      price: d.price ?? null,
      original_price: d.original_price ?? null,
      discount_percent: d.discount_percent ?? null,
      product_name: d.product_name ?? '',
      url: d.url ?? '',
      score: d.score ?? null,
      in_stock: d.in_stock ?? null,
      coupon_code: d.coupon_code ?? null,
      image_url: d.image_url ?? null,
    }));
});

// Progress label for activity bar
const storeProgressLabel = computed(() => {
  const statuses = props.checkpointData?.store_statuses ?? [];
  const total = props.activeStores?.length ?? 0;
  const completed = statuses.length;
  const dealCount = progressiveDeals.value.length;

  if (completed > 0 && total > 0) {
    const parts: string[] = [`${completed}/${total} stores`];
    if (dealCount > 0) parts.push(`${dealCount} deal${dealCount !== 1 ? 's' : ''} found`);
    return parts.join(' \u00b7 ');
  }
  return `${dealCount} deal${dealCount !== 1 ? 's' : ''} found`;
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

const emptyReason = computed<DealEmptyReason>(() => props.content?.empty_reason ?? 'no_matches');

const emptyTitle = computed(() => {
  switch (emptyReason.value) {
    case 'all_store_failures':
      return 'All stores failed to respond';
    case 'search_unavailable':
      return 'Deal search unavailable';
    default:
      return 'No deals found';
  }
});

const emptySubtitle = computed(() => {
  switch (emptyReason.value) {
    case 'all_store_failures':
      return 'This is usually temporary. Try again in a moment.';
    case 'search_unavailable':
      return 'Search services are unavailable for this session.';
    default:
      return null;
  }
});

const emptyIcon = computed(() => {
  switch (emptyReason.value) {
    case 'all_store_failures':
      return AlertTriangle;
    case 'search_unavailable':
      return CloudOff;
    default:
      return SearchX;
  }
});

const showStoreDiagnostics = computed(() => emptyReason.value !== 'search_unavailable');

// Empty-state context
const searchedStores = computed(() => props.content?.searched_stores ?? []);
const storeErrors = computed((): Record<string, string> => {
  const errors = props.content?.store_errors ?? [];
  return Object.fromEntries(errors.map(e => [e.store, e.error]));
});
const errorStoreCount = computed(() => Object.keys(storeErrors.value).length);

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

/* ── Progress Bar ── */
.deal-progress-bar {
  height: 2px;
  margin: 0 8px;
  border-radius: 1px;
  background: rgba(234, 88, 12, 0.08);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 1px;
  background: linear-gradient(90deg, #ea580c, #f97316);
  transition: width 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

/* ── Store Status Grid ── */
.store-status-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 6px 8px 2px;
}

.store-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 7px;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 500;
  border: 1px solid var(--border-light);
  transition: all 0.3s ease;
}

.store-chip-icon {
  flex-shrink: 0;
}

.store-chip-icon.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.store-chip-count {
  font-size: 9px;
  font-weight: 700;
  color: #16a34a;
  background: rgba(22, 163, 74, 0.08);
  border-radius: 999px;
  padding: 0 4px;
  min-width: 14px;
  text-align: center;
}

/* Store chip states */
.store-chip--pending {
  color: var(--text-tertiary);
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-light);
}

.store-chip--found {
  color: #15803d;
  background: rgba(22, 163, 74, 0.06);
  border-color: rgba(22, 163, 74, 0.2);
}

.store-chip--failed {
  color: #dc2626;
  background: rgba(239, 68, 68, 0.04);
  border-color: rgba(239, 68, 68, 0.2);
}

.store-chip--empty {
  color: var(--text-tertiary);
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-light);
}

:global(.dark) .store-chip--found {
  color: #4ade80;
  background: rgba(74, 222, 128, 0.08);
  border-color: rgba(74, 222, 128, 0.15);
}

:global(.dark) .store-chip--failed {
  color: #f87171;
  background: rgba(248, 113, 113, 0.06);
  border-color: rgba(248, 113, 113, 0.15);
}

:global(.dark) .store-chip-count {
  color: #4ade80;
  background: rgba(74, 222, 128, 0.1);
}

/* ── Step text ── */
.deal-step-text {
  padding: 2px 10px 4px;
  font-size: 10.5px;
  color: var(--text-tertiary);
  font-weight: 500;
  letter-spacing: -0.005em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  padding: 28px 16px 16px;
  text-align: center;
  gap: 0;
}

.empty-icon-wrap {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, #fef3c7, #fde68a);
  border: 1px solid rgba(217, 119, 6, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #b45309;
  margin-bottom: 10px;
}

:global(.dark) .empty-icon-wrap {
  background: rgba(217, 119, 6, 0.12);
  border-color: rgba(217, 119, 6, 0.2);
  color: #fbbf24;
}

.deal-empty-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0;
}

.deal-empty-subtitle {
  font-size: 11.5px;
  color: var(--text-tertiary);
  margin: 4px 0 0;
}

.deal-empty-query {
  font-size: 11.5px;
  color: var(--text-tertiary);
  margin: 3px 0 0;
  font-style: italic;
}

/* ── Stores searched ── */
.empty-stores-searched {
  margin-top: 14px;
  width: 100%;
  max-width: 280px;
}

.empty-stores-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 6px;
}

.empty-stores-list {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 4px;
}

.empty-store-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 7px;
  border-radius: 6px;
  font-size: 10.5px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-light);
}

.empty-store-chip--error {
  color: var(--text-tertiary);
  border-color: rgba(239, 68, 68, 0.2);
  background: rgba(239, 68, 68, 0.04);
}

.empty-store-chip--found {
  color: var(--text-secondary);
  border-color: rgba(22, 163, 74, 0.15);
  background: rgba(22, 163, 74, 0.04);
}

:global(.dark) .empty-store-chip--error {
  border-color: rgba(239, 68, 68, 0.15);
  background: rgba(239, 68, 68, 0.06);
}

:global(.dark) .empty-store-chip--found {
  border-color: rgba(74, 222, 128, 0.12);
  background: rgba(74, 222, 128, 0.04);
}

.store-result-icon {
  color: #16a34a;
  flex-shrink: 0;
}

.store-result-icon--error {
  color: #ef4444;
}

:global(.dark) .store-result-icon {
  color: #4ade80;
}

:global(.dark) .store-result-icon--error {
  color: #f87171;
}

.store-error-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #ef4444;
  flex-shrink: 0;
}

/* ── Errors note ── */
.empty-errors-note {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  font-size: 10.5px;
  font-weight: 500;
  color: #d97706;
}

:global(.dark) .empty-errors-note {
  color: #fbbf24;
}

/* ── Suggestions ── */
.empty-suggestions {
  margin-top: 16px;
  width: 100%;
  max-width: 260px;
  text-align: left;
}

.empty-suggestions-label {
  font-size: 10.5px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin: 0 0 5px;
}

.empty-suggestions-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.empty-suggestions-list li {
  font-size: 11px;
  color: var(--text-tertiary);
  padding-left: 10px;
  position: relative;
  line-height: 1.4;
}

.empty-suggestions-list li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 6px;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--text-tertiary);
  opacity: 0.5;
}
</style>
