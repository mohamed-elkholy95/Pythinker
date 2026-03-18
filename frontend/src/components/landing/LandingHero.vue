<template>
  <section class="hero">
    <div class="hero-glow" aria-hidden="true" />
    <div class="hero-grid" aria-hidden="true" />

    <div class="hero-content">
      <Transition appear name="fade-up">
        <span class="hero-badge">
          <Server :size="14" class="hero-badge-icon" />
          Self-Hosted AI Agent Platform
        </span>
      </Transition>

      <Transition appear name="fade-up-d1">
        <h1 class="hero-headline">
          Your AI. Your Tools.<br />
          <span class="hero-headline-accent">Your Infrastructure.</span>
        </h1>
      </Transition>

      <Transition appear name="fade-up-d2">
        <p class="hero-sub">
          An AI agent that browses the web, runs code, manages files, and
          researches &mdash; all in isolated Docker sandboxes you control.
        </p>
      </Transition>

      <Transition appear name="fade-up-d3">
        <div class="hero-ctas">
          <a href="/login" class="hero-btn hero-btn--primary">
            Get Started <ArrowRight :size="18" />
          </a>
          <a href="#how-it-works" class="hero-btn hero-btn--secondary"
            @click.prevent="scrollTo('how-it-works')">
            <Play :size="16" /> See How It Works
          </a>
        </div>
      </Transition>

      <Transition appear name="fade-up-d4">
        <div class="hero-preview">
          <div class="preview-window">
            <div class="preview-titlebar">
              <div class="preview-dots">
                <span class="dot dot--red" />
                <span class="dot dot--yellow" />
                <span class="dot dot--green" />
              </div>
              <span class="preview-title">Pythinker</span>
            </div>
            <div class="preview-body">
              <div class="preview-sidebar">
                <div class="preview-sidebar-item active" />
                <div class="preview-sidebar-item" />
                <div class="preview-sidebar-item" />
              </div>
              <div class="preview-main">
                <div class="preview-bubble preview-bubble--user">
                  <div class="bubble-line" style="width:85%" />
                  <div class="bubble-line" style="width:60%" />
                </div>
                <div class="preview-bubble preview-bubble--agent">
                  <div class="bubble-header">
                    <span class="bubble-avatar" /><span class="bubble-name-line" />
                  </div>
                  <div class="bubble-line" style="width:100%" />
                  <div class="bubble-line" style="width:90%" />
                  <div class="bubble-line" style="width:75%" />
                  <div class="bubble-tools">
                    <div class="tool-card"><Globe :size="12" class="tool-icon" /><span class="tool-line" /></div>
                    <div class="tool-card"><Terminal :size="12" class="tool-icon" /><span class="tool-line" /></div>
                  </div>
                </div>
                <div class="preview-browser">
                  <div class="browser-bar"><span class="browser-url-line" /></div>
                  <div class="browser-content">
                    <div class="browser-skeleton-block" />
                    <div class="browser-skeleton-lines">
                      <div class="browser-line" style="width:100%" />
                      <div class="browser-line" style="width:80%" />
                      <div class="browser-line" style="width:60%" />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Server, ArrowRight, Play, Globe, Terminal } from 'lucide-vue-next'

const scrollTo = (id: string) => {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
}
</script>

<style scoped>
.hero {
  position: relative; min-height: 100vh; display: flex;
  align-items: center; justify-content: center;
  padding: 100px 24px 60px; overflow: hidden;
}
.hero-glow {
  position: absolute; top: -15%; left: 50%; translate: -50% 0;
  width: 700px; height: 500px; border-radius: 50%;
  background: radial-gradient(ellipse at center, color-mix(in srgb, var(--text-brand) 10%, transparent) 0%, transparent 70%);
  pointer-events: none; filter: blur(50px); z-index: 0;
}
.hero-grid {
  position: absolute; inset: 0; pointer-events: none; z-index: 0;
  background-image: radial-gradient(circle, var(--grid-dot-color, rgba(128,128,128,0.3)) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse 60% 60% at 50% 40%, black 0%, transparent 100%);
  -webkit-mask-image: radial-gradient(ellipse 60% 60% at 50% 40%, black 0%, transparent 100%);
  animation: gridBreath 5s ease-in-out infinite;
}
@keyframes gridBreath { 0%,100% { opacity: .7 } 50% { opacity: 1 } }
.hero-content {
  position: relative; z-index: 1; max-width: 900px; width: 100%;
  display: flex; flex-direction: column; align-items: center; text-align: center; gap: 24px;
}
.hero-badge {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 16px; border-radius: 999px; font-size: 13px; font-weight: 500;
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--background-card) 80%, transparent);
  border: 1px solid var(--border-main); backdrop-filter: blur(6px);
}
.hero-badge-icon { color: var(--text-brand); }
.hero-headline {
  font-family: var(--font-display); font-size: 68px; font-weight: 400;
  line-height: 1.08; letter-spacing: -0.035em; color: var(--text-primary);
}
.hero-headline-accent {
  background: linear-gradient(135deg, var(--text-primary), var(--text-secondary));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.hero-sub { max-width: 600px; font-size: 18px; line-height: 1.6; color: var(--text-secondary); }
.hero-ctas { display: flex; align-items: center; gap: 16px; margin-top: 8px; }
.hero-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 12px 28px; border-radius: 12px; font-size: 15px; font-weight: 600;
  text-decoration: none; transition: all 0.2s ease; cursor: pointer; border: none;
}
.hero-btn--primary {
  background: var(--button-primary); color: var(--text-onblack);
  box-shadow: 0 4px 20px color-mix(in srgb, var(--button-primary) 30%, transparent);
}
.hero-btn--primary:hover {
  background: var(--button-primary-hover); transform: translateY(-2px);
  box-shadow: 0 6px 28px color-mix(in srgb, var(--button-primary) 40%, transparent);
}
.hero-btn--secondary {
  background: color-mix(in srgb, var(--background-card) 80%, transparent);
  color: var(--text-primary); border: 1px solid var(--border-main); backdrop-filter: blur(6px);
}
.hero-btn--secondary:hover {
  border-color: var(--border-dark); background: var(--fill-tsp-gray-main); transform: translateY(-2px);
}
/* Preview window */
.hero-preview { width: 100%; max-width: 820px; margin-top: 32px; }
.preview-window {
  border-radius: 16px; overflow: hidden; border: 1px solid var(--border-main);
  background: color-mix(in srgb, var(--background-card) 90%, transparent);
  backdrop-filter: blur(12px);
  box-shadow: 0 8px 40px color-mix(in srgb, var(--shadow-L) 40%, transparent), 0 0 0 1px var(--border-light);
}
.preview-titlebar {
  display: flex; align-items: center; gap: 12px; padding: 12px 16px;
  background: var(--fill-tsp-gray-main); border-bottom: 1px solid var(--border-light);
}
.preview-dots { display: flex; gap: 6px; }
.dot { width: 10px; height: 10px; border-radius: 50%; }
.dot--red { background: #ff5f57; } .dot--yellow { background: #febc2e; } .dot--green { background: #28c840; }
.preview-title { font-size: 12px; font-weight: 500; color: var(--text-tertiary); }
.preview-body { display: flex; min-height: 320px; }
.preview-sidebar {
  width: 48px; flex-shrink: 0; padding: 12px 8px;
  display: flex; flex-direction: column; gap: 8px; border-right: 1px solid var(--border-light);
}
.preview-sidebar-item { width: 32px; height: 32px; border-radius: 8px; background: var(--fill-tsp-gray-main); }
.preview-sidebar-item.active { background: color-mix(in srgb, var(--text-brand) 15%, transparent); }
.preview-main { flex: 1; padding: 16px; display: flex; flex-direction: column; gap: 12px; overflow: hidden; }
.preview-bubble { padding: 12px 16px; border-radius: 12px; display: flex; flex-direction: column; gap: 6px; }
.preview-bubble--user { background: var(--fill-tsp-gray-main); align-self: flex-end; max-width: 70%; }
.preview-bubble--agent { background: var(--fill-tsp-white-light); border: 1px solid var(--border-light); max-width: 85%; }
.bubble-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.bubble-avatar { width: 20px; height: 20px; border-radius: 50%; background: color-mix(in srgb, var(--text-brand) 20%, transparent); }
.bubble-name-line { height: 8px; width: 60px; border-radius: 4px; background: var(--fill-tsp-gray-dark); }
.bubble-line { height: 8px; border-radius: 4px; background: var(--fill-tsp-gray-main); }
.bubble-tools { display: flex; gap: 8px; margin-top: 6px; }
.tool-card {
  display: flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 6px;
  background: color-mix(in srgb, var(--text-brand) 8%, transparent); border: 1px solid var(--border-light);
}
.tool-icon { color: var(--text-brand); flex-shrink: 0; }
.tool-line { height: 6px; width: 48px; border-radius: 3px; background: var(--fill-tsp-gray-main); }
.preview-browser { border-radius: 8px; border: 1px solid var(--border-light); overflow: hidden; margin-top: auto; }
.browser-bar { padding: 6px 10px; background: var(--fill-tsp-gray-main); border-bottom: 1px solid var(--border-light); }
.browser-url-line { display: block; height: 6px; width: 140px; border-radius: 3px; background: var(--fill-tsp-gray-dark); }
.browser-content { padding: 10px; display: flex; flex-direction: column; gap: 8px; }
.browser-skeleton-block { border-radius: 6px; background: var(--fill-tsp-gray-main); min-height: 40px; }
.browser-skeleton-lines { display: flex; flex-direction: column; gap: 4px; }
.browser-line { height: 6px; border-radius: 3px; background: var(--fill-tsp-gray-main); }
/* Appear transitions */
.fade-up-enter-active, .fade-up-d1-enter-active, .fade-up-d2-enter-active,
.fade-up-d3-enter-active, .fade-up-d4-enter-active {
  transition: opacity 0.7s ease, transform 0.7s ease;
}
.fade-up-enter-from, .fade-up-d1-enter-from, .fade-up-d2-enter-from,
.fade-up-d3-enter-from, .fade-up-d4-enter-from {
  opacity: 0; transform: translateY(24px);
}
.fade-up-d1-enter-active { transition-delay: 0.1s; }
.fade-up-d2-enter-active { transition-delay: 0.2s; }
.fade-up-d3-enter-active { transition-delay: 0.35s; }
.fade-up-d4-enter-active { transition-delay: 0.55s; }
@media (max-width: 768px) {
  .hero { padding: 90px 16px 40px; min-height: auto; }
  .hero-headline { font-size: 38px; }
  .hero-sub { font-size: 16px; }
  .hero-ctas { flex-direction: column; width: 100%; }
  .hero-btn { width: 100%; justify-content: center; }
  .preview-body { min-height: 220px; }
  .preview-sidebar { display: none; }
}
@media (min-width: 769px) and (max-width: 1024px) { .hero-headline { font-size: 52px; } }
@media (prefers-reduced-motion: reduce) {
  .fade-up-enter-active, .fade-up-d1-enter-active, .fade-up-d2-enter-active,
  .fade-up-d3-enter-active, .fade-up-d4-enter-active { transition: none; }
  .hero-grid { animation: none; }
}
</style>
