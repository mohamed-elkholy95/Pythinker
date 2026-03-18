<template>
  <section class="cta-section">
    <div class="cta-glow" aria-hidden="true" />
    <div class="cta-inner">
      <h2 :ref="revealRef" class="cta-heading scroll-reveal">Your Personal AI Agent,<br />Ready&nbsp;in&nbsp;Minutes</h2>
      <p :ref="revealRef" class="cta-sub scroll-reveal">Open source. Self-hosted. Your data never leaves your server.</p>
      <div :ref="revealRef" class="cta-actions scroll-reveal">
        <a href="/login" class="cta-btn cta-btn--primary">Get Started Free <ArrowRight :size="18" /></a>
        <a href="https://github.com/mohamed-elkholy95/Pythinker" target="_blank" rel="noopener noreferrer" class="cta-btn cta-btn--secondary">
          <Github :size="18" /> View on GitHub
        </a>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ArrowRight, Github } from 'lucide-vue-next'
import { useScrollReveal } from '../../composables/useScrollReveal'
const { revealRef } = useScrollReveal()
</script>

<style scoped>
.cta-section { position: relative; padding: 120px 24px; overflow: hidden; }
.cta-glow {
  position: absolute; top: 50%; left: 50%; translate: -50% -50%;
  width: 600px; height: 400px; border-radius: 50%;
  background: radial-gradient(ellipse at center, color-mix(in srgb, var(--text-brand) 8%, transparent) 0%, transparent 70%);
  pointer-events: none; filter: blur(60px); z-index: 0;
}
.cta-inner {
  position: relative; z-index: 1; max-width: 680px; margin: 0 auto; text-align: center;
  display: flex; flex-direction: column; align-items: center; gap: 20px;
}
.cta-heading {
  font-family: var(--font-display); font-size: 42px; font-weight: 400;
  letter-spacing: -0.03em; color: var(--text-primary);
}
.cta-sub { font-size: 18px; color: var(--text-secondary); line-height: 1.5; }
.cta-actions { display: flex; align-items: center; gap: 14px; margin-top: 8px; }
.cta-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 12px 28px; border-radius: 12px; font-size: 15px; font-weight: 600;
  text-decoration: none; transition: all 0.2s ease; cursor: pointer; border: none;
}
.cta-btn--primary {
  background: var(--button-primary); color: var(--text-onblack);
  box-shadow: 0 4px 20px color-mix(in srgb, var(--button-primary) 30%, transparent);
}
.cta-btn--primary:hover {
  background: var(--button-primary-hover); transform: translateY(-2px);
  box-shadow: 0 6px 28px color-mix(in srgb, var(--button-primary) 40%, transparent);
}
.cta-btn--secondary {
  background: color-mix(in srgb, var(--background-card) 80%, transparent);
  color: var(--text-primary); border: 1px solid var(--border-main); backdrop-filter: blur(6px);
}
.cta-btn--secondary:hover { border-color: var(--border-dark); background: var(--fill-tsp-gray-main); transform: translateY(-2px); }
.scroll-reveal { opacity: 0; transform: translateY(24px); transition: opacity 0.6s ease, transform 0.6s ease; }
.scroll-reveal.revealed { opacity: 1; transform: translateY(0); }
@media (max-width: 768px) {
  .cta-section { padding: 80px 16px; }
  .cta-heading { font-size: 30px; }
  .cta-actions { flex-direction: column; width: 100%; }
  .cta-btn { width: 100%; justify-content: center; }
}
@media (prefers-reduced-motion: reduce) { .scroll-reveal { opacity: 1; transform: none; transition: none; } }
</style>
