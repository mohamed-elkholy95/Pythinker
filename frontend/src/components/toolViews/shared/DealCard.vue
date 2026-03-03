<template>
  <div
    class="deal-card"
    :class="{ 'deal-card--best': isBest }"
    @click="$emit('click')"
  >
    <!-- Best Deal ribbon -->
    <div v-if="isBest" class="best-ribbon">
      <Trophy :size="9" />
      <span>Best Deal</span>
    </div>

    <!-- Scanning shimmer overlay (appears briefly on enter) -->
    <div class="card-shimmer"></div>

    <div class="deal-card-body">
      <!-- Left: Store + Product info -->
      <div class="deal-info">
        <div class="deal-store-row">
          <div class="store-avatar">
            <img
              v-if="!faviconError && faviconUrl"
              :src="faviconUrl"
              alt=""
              class="store-favicon"
              @error="faviconError = true"
            />
            <span v-else class="store-letter">{{ storeLetter }}</span>
          </div>
          <span class="deal-store-name">{{ deal.store || 'Unknown Store' }}</span>
          <span v-if="deal.in_stock === true" class="stock-pill stock-in">
            <span class="stock-dot"></span>In Stock
          </span>
          <span v-else-if="deal.in_stock === false" class="stock-pill stock-out">Out of Stock</span>
          <span v-if="categoryLabel" class="item-category-pill">{{ categoryLabel }}</span>
        </div>
        <div class="deal-product-name">{{ deal.product_name || 'Unnamed product' }}</div>
        <div v-if="deal.coupon_code" class="deal-coupon-tag">
          <Ticket :size="9" />
          <code>{{ deal.coupon_code }}</code>
        </div>
      </div>

      <!-- Right: Price block -->
      <div class="deal-price-block">
        <div v-if="deal.discount_percent != null && deal.discount_percent > 0" class="discount-badge">
          -{{ Math.round(deal.discount_percent) }}%
        </div>
        <div v-if="deal.price != null" class="deal-price">
          <span class="price-currency">$</span>{{ formatWhole(deal.price) }}<span class="price-cents">.{{ formatCents(deal.price) }}</span>
        </div>
        <div v-if="deal.original_price != null && deal.original_price !== deal.price" class="deal-was-price">
          was ${{ formatPrice(deal.original_price) }}
        </div>
      </div>
    </div>

    <!-- Score meter -->
    <div v-if="deal.score != null" class="deal-score-row">
      <div class="score-track">
        <div
          class="score-fill"
          :style="{ width: `${Math.min(deal.score, 100)}%` }"
          :class="scoreColorClass"
        ></div>
      </div>
      <span class="score-value" :class="scoreColorClass">{{ deal.score }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { Trophy, Ticket } from 'lucide-vue-next';
import { getFaviconUrl } from '@/utils/toolDisplay';
import type { DealItem } from '@/types/toolContent';

const props = defineProps<{
  deal: DealItem;
  isBest: boolean;
  index: number;
}>();

defineEmits<{
  (e: 'click'): void;
}>();

const faviconError = ref(false);

const faviconUrl = computed(() => {
  if (!props.deal.url) return null;
  return getFaviconUrl(props.deal.url);
});

const storeLetter = computed(() => {
  const name = props.deal.store || props.deal.product_name || '';
  return name.charAt(0).toUpperCase() || '?';
});

const scoreColorClass = computed(() => {
  const s = props.deal.score ?? 0;
  if (s >= 80) return 'score-excellent';
  if (s >= 60) return 'score-good';
  if (s >= 40) return 'score-fair';
  return 'score-low';
});

const categoryLabel = computed(() => {
  if (props.deal.item_category === 'digital') return 'Digital';
  if (props.deal.item_category === 'physical') return 'Physical';
  return '';
});

function formatPrice(price: number): string {
  return price.toFixed(2);
}

function formatWhole(price: number): string {
  return Math.floor(price).toString();
}

function formatCents(price: number): string {
  return (price % 1).toFixed(2).slice(2);
}
</script>

<style scoped>
.deal-card {
  position: relative;
  border-radius: 10px;
  border: 1px solid var(--border-light);
  padding: 10px 12px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  background: var(--background-white-main);
  overflow: hidden;
}

.deal-card:hover {
  border-color: var(--border-hover);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
  transform: translateY(-1px);
}

.deal-card:active {
  transform: translateY(0);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

/* ── Shimmer scan effect on hover ── */
.card-shimmer {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    105deg,
    transparent 40%,
    rgba(234, 88, 12, 0.03) 48%,
    rgba(234, 88, 12, 0.06) 50%,
    rgba(234, 88, 12, 0.03) 52%,
    transparent 60%
  );
  transform: translateX(-120%);
  pointer-events: none;
  border-radius: inherit;
  transition: none;
}

.deal-card:hover .card-shimmer {
  animation: card-scan 0.7s ease-out;
}

@keyframes card-scan {
  0% { transform: translateX(-120%); }
  100% { transform: translateX(120%); }
}

/* ── Best Deal ── */
.deal-card--best {
  border-color: rgba(234, 88, 12, 0.3);
  background: linear-gradient(160deg, #fffcfa, #fff8f3 40%, var(--background-white-main));
  padding-top: 22px; /* clearance for the absolutely-positioned ribbon */
}

:global(.dark) .deal-card--best {
  border-color: rgba(251, 146, 60, 0.25);
  background: linear-gradient(160deg, rgba(234, 88, 12, 0.07), rgba(234, 88, 12, 0.02) 40%, var(--background-white-main));
}

.best-ribbon {
  position: absolute;
  top: 0;
  right: 0;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px 3px 6px;
  border-radius: 0 9px 0 8px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #ffffff;
  background: linear-gradient(135deg, #ea580c, #dc2626);
  box-shadow: 0 2px 6px rgba(220, 38, 38, 0.25);
}

/* ── Card Body ── */
.deal-card-body {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}

.deal-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

/* ── Store Row ── */
.deal-store-row {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  overflow: hidden;
}

.store-avatar {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  background: var(--fill-tsp-gray-main);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
  border: 1px solid var(--border-light);
}

.store-favicon {
  width: 12px;
  height: 12px;
  object-fit: contain;
}

.store-letter {
  font-size: 8px;
  font-weight: 700;
  color: var(--text-tertiary);
  line-height: 1;
}

.deal-store-name {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
  letter-spacing: -0.005em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.stock-pill {
  font-size: 9px;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 999px;
  letter-spacing: 0.01em;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
  white-space: nowrap;
}

.stock-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #22c55e;
}

.stock-in {
  color: #15803d;
  background: #f0fdf4;
  border: 1px solid rgba(21, 128, 61, 0.15);
}

:global(.dark) .stock-in {
  color: #4ade80;
  background: rgba(21, 128, 61, 0.12);
  border-color: rgba(74, 222, 128, 0.15);
}

.stock-out {
  color: #991b1b;
  background: #fef2f2;
  border: 1px solid rgba(153, 27, 27, 0.15);
}

.item-category-pill {
  font-size: 9px;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 999px;
  color: #7c2d12;
  background: #ffedd5;
  border: 1px solid rgba(234, 88, 12, 0.2);
  flex-shrink: 0;
}

:global(.dark) .item-category-pill {
  color: #fdba74;
  background: rgba(234, 88, 12, 0.12);
  border-color: rgba(251, 146, 60, 0.22);
}

:global(.dark) .stock-out {
  color: #fca5a5;
  background: rgba(153, 27, 27, 0.12);
  border-color: rgba(252, 165, 165, 0.15);
}

/* ── Product Name ── */
.deal-product-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
  letter-spacing: -0.01em;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── Inline coupon tag ── */
.deal-coupon-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  color: #9a3412;
  background: repeating-linear-gradient(
    90deg,
    transparent 0px,
    transparent 3px,
    rgba(234, 88, 12, 0.08) 3px,
    rgba(234, 88, 12, 0.08) 6px
  ),
  #fff7ed;
  border: 1px dashed rgba(234, 88, 12, 0.35);
  border-radius: 4px;
  padding: 2px 6px;
  width: fit-content;
}

:global(.dark) .deal-coupon-tag {
  color: #fb923c;
  background: repeating-linear-gradient(
    90deg,
    transparent 0px,
    transparent 3px,
    rgba(234, 88, 12, 0.06) 3px,
    rgba(234, 88, 12, 0.06) 6px
  ),
  rgba(234, 88, 12, 0.08);
  border-color: rgba(234, 88, 12, 0.3);
}

.deal-coupon-tag code {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-weight: 700;
  font-size: 10px;
  letter-spacing: 0.04em;
}

/* ── Price Block ── */
.deal-price-block {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
  flex-shrink: 0;
}

.discount-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 800;
  color: #15803d;
  background: #dcfce7;
  letter-spacing: -0.01em;
  margin-bottom: 1px;
}

:global(.dark) .discount-badge {
  color: #4ade80;
  background: rgba(21, 128, 61, 0.18);
}

.deal-price {
  font-size: 20px;
  font-weight: 800;
  color: var(--text-primary);
  line-height: 1;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
}

.price-currency {
  font-size: 13px;
  font-weight: 600;
  vertical-align: super;
  margin-right: 1px;
  opacity: 0.7;
}

.price-cents {
  font-size: 12px;
  font-weight: 600;
  vertical-align: super;
  opacity: 0.6;
}

.deal-was-price {
  font-size: 10px;
  font-weight: 400;
  color: var(--text-tertiary);
  text-decoration: line-through;
  line-height: 1;
}

/* ── Score Bar ── */
.deal-score-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 7px;
}

.score-track {
  flex: 1;
  height: 3px;
  border-radius: 2px;
  background: var(--fill-tsp-gray-main);
  overflow: hidden;
}

.score-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.8s cubic-bezier(0.16, 1, 0.3, 1);
}

.score-excellent { background: linear-gradient(90deg, #22c55e, #16a34a); }
.score-good { background: linear-gradient(90deg, #84cc16, #65a30d); }
.score-fair { background: linear-gradient(90deg, #eab308, #ca8a04); }
.score-low { background: linear-gradient(90deg, #ef4444, #dc2626); }

.score-value {
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  min-width: 18px;
  text-align: right;
}

.score-value.score-excellent { color: #16a34a; }
.score-value.score-good { color: #65a30d; }
.score-value.score-fair { color: #ca8a04; }
.score-value.score-low { color: #dc2626; }

:global(.dark) .score-value.score-excellent { color: #4ade80; }
:global(.dark) .score-value.score-good { color: #a3e635; }
:global(.dark) .score-value.score-fair { color: #facc15; }
:global(.dark) .score-value.score-low { color: #f87171; }
</style>
