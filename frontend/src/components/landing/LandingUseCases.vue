<template>
  <section id="use-cases" class="uc-section">
    <div class="uc-inner">
      <h2 :ref="revealRef" class="section-heading scroll-reveal">Built for Real Work</h2>
      <p :ref="revealRef" class="section-sub scroll-reveal">
        From market analysis to web automation — let the agent handle the heavy lifting.
      </p>
      <div class="uc-grid">
        <div v-for="(uc, i) in useCases" :key="uc.title" :ref="revealRef"
          class="uc-card scroll-reveal" :style="{ transitionDelay: `${i * 0.1}s` }">
          <div :class="['uc-icon-wrap', `ui--${uc.color}`]">
            <component :is="uc.icon" :size="20" />
          </div>
          <div class="uc-content">
            <h3 class="uc-title">{{ uc.title }}</h3>
            <p class="uc-desc">{{ uc.description }}</p>
            <div class="uc-tags">
              <span v-for="tag in uc.tools" :key="tag" class="uc-tag">{{ tag }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { BarChart3, Tag, Code, MousePointerClick } from 'lucide-vue-next'
import { useScrollReveal } from '../../composables/useScrollReveal'
const { revealRef } = useScrollReveal()

const useCases = [
  { title: 'Market Research', icon: BarChart3, color: 'blue',
    description: 'Analyze competitors, scrape pricing data, and compile comprehensive reports with citations.',
    tools: ['Browser', 'Search', 'Files'] },
  { title: 'Deal Finding', icon: Tag, color: 'amber',
    description: 'Compare prices across stores, find active coupons and promo codes automatically.',
    tools: ['Browser', 'Search'] },
  { title: 'Code Generation', icon: Code, color: 'green',
    description: 'Generate, test, and iterate on code with full terminal access inside isolated sandboxes.',
    tools: ['Terminal', 'Files', 'Code'] },
  { title: 'Web Automation', icon: MousePointerClick, color: 'purple',
    description: 'Fill forms, navigate multi-step workflows, and extract structured data from any website.',
    tools: ['Browser', 'Terminal'] },
]
</script>

<style scoped>
.uc-section { position: relative; padding: 120px 24px; }
.uc-inner { max-width: 1100px; margin: 0 auto; }
.section-heading {
  font-family: var(--font-display); font-size: 42px; font-weight: 400;
  letter-spacing: -0.03em; color: var(--text-primary); text-align: center; margin-bottom: 16px;
}
.section-sub {
  font-size: 17px; color: var(--text-secondary); text-align: center;
  max-width: 520px; margin: 0 auto 56px; line-height: 1.6;
}
.uc-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; }
.uc-card {
  display: flex; gap: 20px; padding: 28px 24px; border-radius: var(--radius-xl);
  background: color-mix(in srgb, var(--background-card) 80%, transparent);
  border: 1px solid var(--border-light); backdrop-filter: blur(8px);
  transition: transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease, opacity 0.6s ease;
}
.uc-card:hover { transform: translateY(-3px); border-color: var(--border-main); box-shadow: 0 6px 24px var(--shadow-S); }
.uc-icon-wrap {
  width: 44px; height: 44px; min-width: 44px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
}
.ui--blue { background: color-mix(in srgb, #3b82f6 12%, transparent); color: #3b82f6; }
.ui--amber { background: color-mix(in srgb, #f59e0b 12%, transparent); color: #f59e0b; }
.ui--green { background: color-mix(in srgb, #22c55e 12%, transparent); color: #22c55e; }
.ui--purple { background: color-mix(in srgb, #a855f7 12%, transparent); color: #a855f7; }
.uc-content { display: flex; flex-direction: column; gap: 6px; }
.uc-title { font-size: 17px; font-weight: 600; color: var(--text-primary); }
.uc-desc { font-size: 14px; line-height: 1.6; color: var(--text-secondary); }
.uc-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.uc-tag {
  display: inline-flex; padding: 3px 10px; border-radius: 999px;
  font-size: 12px; font-weight: 500; color: var(--text-tertiary);
  background: var(--fill-tsp-gray-main); border: 1px solid var(--border-light);
}
.scroll-reveal { opacity: 0; transform: translateY(24px); transition: opacity 0.6s ease, transform 0.6s ease; }
.scroll-reveal.revealed { opacity: 1; transform: translateY(0); }
@media (max-width: 768px) {
  .uc-section { padding: 80px 16px; }
  .section-heading { font-size: 30px; }
  .uc-grid { grid-template-columns: 1fr; }
  .uc-card { flex-direction: column; gap: 14px; }
}
@media (min-width: 769px) and (max-width: 1024px) { .section-heading { font-size: 36px; } }
@media (prefers-reduced-motion: reduce) { .scroll-reveal { opacity: 1; transform: none; transition: none; } }
</style>
