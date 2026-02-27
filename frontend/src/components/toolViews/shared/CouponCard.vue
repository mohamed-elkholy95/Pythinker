<template>
  <div class="coupon-card" :class="{ 'coupon-verified': coupon.verified }">
    <!-- Perforation dots on left edge -->
    <div class="coupon-perforation">
      <span v-for="i in 4" :key="i" class="perf-dot"></span>
    </div>

    <div class="coupon-body">
      <div class="coupon-left">
        <div class="coupon-code-row">
          <code class="coupon-code">{{ coupon.code || 'NO CODE' }}</code>
          <button
            v-if="coupon.code"
            class="copy-btn"
            :class="{ 'copy-btn--copied': copied }"
            @click.stop="copyCode"
          >
            <Check v-if="copied" :size="9" />
            <Copy v-else :size="9" />
            {{ copied ? 'Copied!' : 'Copy' }}
          </button>
        </div>
        <div class="coupon-desc">{{ coupon.description || 'Promo code' }}</div>
        <div class="coupon-meta">
          <span v-if="coupon.store" class="meta-store">{{ coupon.store }}</span>
          <span v-if="coupon.store && coupon.expiry" class="meta-sep">&middot;</span>
          <span v-if="coupon.expiry" class="meta-expiry">{{ coupon.expiry }}</span>
        </div>
      </div>

      <div v-if="coupon.verified" class="coupon-verified-badge">
        <ShieldCheck :size="11" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { Copy, Check, ShieldCheck } from 'lucide-vue-next';
import type { CouponItem } from '@/types/toolContent';

const props = defineProps<{
  coupon: CouponItem;
}>();

const copied = ref(false);

async function copyCode() {
  if (!props.coupon.code) return;
  try {
    await navigator.clipboard.writeText(props.coupon.code);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 2000);
  } catch {
    // Clipboard API not available — silent fail
  }
}
</script>

<style scoped>
.coupon-card {
  display: flex;
  align-items: stretch;
  border-radius: 8px;
  border: 1px dashed var(--border-light);
  background: var(--background-white-main);
  overflow: hidden;
  transition: all 0.15s ease;
}

.coupon-card:hover {
  border-color: rgba(234, 88, 12, 0.3);
  box-shadow: 0 1px 4px rgba(234, 88, 12, 0.06);
}

/* ── Perforation dots ── */
.coupon-perforation {
  width: 10px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  background: linear-gradient(135deg, #fff7ed, #ffedd5);
  border-right: 1px dashed rgba(234, 88, 12, 0.2);
}

:global(.dark) .coupon-perforation {
  background: rgba(234, 88, 12, 0.06);
  border-right-color: rgba(234, 88, 12, 0.15);
}

.perf-dot {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: rgba(234, 88, 12, 0.2);
}

:global(.dark) .perf-dot {
  background: rgba(251, 146, 60, 0.2);
}

/* ── Body ── */
.coupon-body {
  flex: 1;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 10px;
  min-width: 0;
}

.coupon-left {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* ── Code row ── */
.coupon-code-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.coupon-code {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 0.06em;
  padding: 2px 7px;
  border-radius: 4px;
  background: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-light);
}

.copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 5px;
  border-radius: 4px;
  border: 1px solid var(--border-light);
  background: var(--background-white-main);
  font-size: 9px;
  font-weight: 600;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.15s ease;
  letter-spacing: 0.01em;
}

.copy-btn:hover {
  border-color: var(--border-hover);
  color: var(--text-secondary);
  background: var(--fill-tsp-gray-main);
}

.copy-btn--copied {
  color: #15803d;
  border-color: rgba(21, 128, 61, 0.25);
  background: #f0fdf4;
}

:global(.dark) .copy-btn--copied {
  color: #4ade80;
  background: rgba(21, 128, 61, 0.12);
  border-color: rgba(74, 222, 128, 0.2);
}

/* ── Description + Meta ── */
.coupon-desc {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-secondary);
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.coupon-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: var(--text-tertiary);
}

.meta-store { font-weight: 500; }
.meta-sep { opacity: 0.4; }
.meta-expiry { font-weight: 400; }

/* ── Verified badge ── */
.coupon-verified-badge {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: #f0fdf4;
  border: 1px solid rgba(21, 128, 61, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #16a34a;
  flex-shrink: 0;
}

:global(.dark) .coupon-verified-badge {
  background: rgba(21, 128, 61, 0.1);
  border-color: rgba(74, 222, 128, 0.15);
  color: #4ade80;
}

/* ── Verified state card accent ── */
.coupon-verified {
  border-color: rgba(21, 128, 61, 0.15);
}

.coupon-verified:hover {
  border-color: rgba(21, 128, 61, 0.3);
}
</style>
