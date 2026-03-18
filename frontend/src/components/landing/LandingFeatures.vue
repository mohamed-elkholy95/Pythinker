<template>
  <section id="features" class="features-section">
    <div class="features-inner">
      <h2 :ref="revealRef" class="section-heading scroll-reveal">Everything an AI Agent Needs</h2>
      <p :ref="revealRef" class="section-sub scroll-reveal">
        A complete toolkit for autonomous task execution — all running in isolated Docker sandboxes.
      </p>
      <div class="features-grid">
        <div v-for="(f, i) in features" :key="f.title" :ref="revealRef"
          class="feature-card scroll-reveal" :style="{ transitionDelay: `${i * 0.08}s` }">
          <div :class="['feature-icon-wrap', `fi--${f.color}`]">
            <component :is="f.icon" :size="22" />
          </div>
          <h3 class="feature-title">{{ f.title }}</h3>
          <p class="feature-desc">{{ f.description }}</p>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Globe, Terminal as TerminalIcon, FileText, Search, Palette, Server } from 'lucide-vue-next'
import { useScrollReveal } from '../../composables/useScrollReveal'
const { revealRef } = useScrollReveal()

const features = [
  { title: 'Browser Agent', icon: Globe, color: 'blue',
    description: 'Navigate websites, fill forms, extract data — see everything in real-time via live screencast.' },
  { title: 'Terminal & Code', icon: TerminalIcon, color: 'green',
    description: 'Execute shell commands and run code in isolated containers with full output streaming.' },
  { title: 'File Management', icon: FileText, color: 'amber',
    description: 'Read, write, and organize files within the sandbox filesystem with full access control.' },
  { title: 'Deep Research', icon: Search, color: 'purple',
    description: 'Multi-query parallel research with citation-aware summaries and structured reports.' },
  { title: 'Visual Design', icon: Palette, color: 'pink',
    description: 'Create and iterate on visual designs with canvas capabilities and real-time preview.' },
  { title: 'Self-Hosted', icon: Server, color: 'teal',
    description: 'Deploy on your own infrastructure. Your data never leaves your control. Zero vendor lock-in.' },
]
</script>

<style scoped>
.features-section { position: relative; padding: 72px 24px; }
.features-inner { max-width: 1100px; margin: 0 auto; }
.section-heading {
  font-family: var(--font-display); font-size: 42px; font-weight: 400;
  letter-spacing: -0.03em; color: var(--text-primary); text-align: center; margin-bottom: 16px;
}
.section-sub {
  font-size: 17px; color: var(--text-secondary); text-align: center;
  max-width: 560px; margin: 0 auto 56px; line-height: 1.6;
}
.features-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
.feature-card {
  padding: 28px 24px; border-radius: var(--radius-xl);
  background: color-mix(in srgb, var(--background-card) 80%, transparent);
  border: 1px solid var(--border-light); backdrop-filter: blur(8px);
  transition: transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease, opacity 0.6s ease;
}
.feature-card:hover { transform: translateY(-4px); border-color: var(--border-main); box-shadow: 0 8px 32px var(--shadow-S); }
.feature-icon-wrap {
  width: 48px; height: 48px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center; margin-bottom: 16px;
}
.fi--blue { background: color-mix(in srgb, #3b82f6 12%, transparent); color: #3b82f6; }
.fi--green { background: color-mix(in srgb, #22c55e 12%, transparent); color: #22c55e; }
.fi--amber { background: color-mix(in srgb, #f59e0b 12%, transparent); color: #f59e0b; }
.fi--purple { background: color-mix(in srgb, #a855f7 12%, transparent); color: #a855f7; }
.fi--pink { background: color-mix(in srgb, #ec4899 12%, transparent); color: #ec4899; }
.fi--teal { background: color-mix(in srgb, #14b8a6 12%, transparent); color: #14b8a6; }
.feature-title { font-size: 17px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
.feature-desc { font-size: 14px; line-height: 1.6; color: var(--text-secondary); }
.scroll-reveal { opacity: 0; transform: translateY(24px); transition: opacity 0.6s ease, transform 0.6s ease; }
.scroll-reveal.revealed { opacity: 1; transform: translateY(0); }
@media (max-width: 768px) {
  .features-section { padding: 80px 16px; }
  .section-heading { font-size: 30px; }
  .features-grid { grid-template-columns: 1fr; gap: 14px; }
}
@media (min-width: 769px) and (max-width: 1024px) {
  .features-grid { grid-template-columns: repeat(2, 1fr); }
  .section-heading { font-size: 36px; }
}
@media (prefers-reduced-motion: reduce) { .scroll-reveal { opacity: 1; transform: none; transition: none; } }
</style>
