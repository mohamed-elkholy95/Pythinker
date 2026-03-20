<template>
  <section class="hero">
    <div class="hero-glow" aria-hidden="true" />
    <div class="hero-grid" aria-hidden="true" />

    <div class="hero-content">
      <div class="hero-split">
        <div class="hero-text">
          <Transition appear name="fade-up">
            <span class="hero-badge">
              <Server :size="14" class="hero-badge-icon" />
              Personal AI Agent &middot; Works Autonomously
            </span>
          </Transition>

          <Transition appear name="fade-up-d1">
            <h1 class="hero-headline">
              Build. Deploy. Automate.<br />
              <span class="hero-headline-accent">Scale Without Limits.</span>
            </h1>
          </Transition>

          <Transition appear name="fade-up-d2">
            <p class="hero-sub">
              An autonomous AI agent that researches, writes code, browses the web,
              and delivers results &mdash; end to end. Give it a task and watch it work.
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
        </div>

        <Transition appear name="fade-up-d2">
          <div class="hero-mascot">
            <div class="mascot-glow" aria-hidden="true" />
            <img src="/pythinker_animated.svg" alt="Pythinker AI Robot" class="mascot-img" width="280" height="350" />
          </div>
        </Transition>
      </div>

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
              <!-- Left: Chat panel -->
              <div class="preview-sidebar">
                <div class="sidebar-header">
                  <div class="sidebar-action-line" />
                </div>
                <div class="sidebar-nav">
                  <div class="sidebar-nav-item" />
                  <div class="sidebar-nav-item" />
                  <div class="sidebar-nav-item" />
                </div>
                <div class="sidebar-section-label" />
                <div class="sidebar-tasks">
                  <div class="sidebar-task-item active">
                    <span class="task-icon" />
                    <span class="task-line" />
                  </div>
                  <div class="sidebar-task-item">
                    <span class="task-icon" />
                    <span class="task-line" />
                  </div>
                </div>
              </div>
              <div class="preview-main">
                <!-- Agent name header -->
                <div class="main-agent-header">
                  <span class="agent-logo" />
                  <span class="agent-name-line" />
                </div>
                <!-- Agent intro message -->
                <div class="preview-bubble preview-bubble--agent">
                  <div class="bubble-line" style="width:90%" />
                  <div class="bubble-line" style="width:70%" />
                </div>
                <!-- Plan steps -->
                <div class="plan-steps">
                  <div class="plan-step completed">
                    <CheckCircle :size="13" class="step-icon step-icon--done" />
                    <span class="step-line" style="width:75%" />
                  </div>
                  <div class="plan-step completed">
                    <CheckCircle :size="13" class="step-icon step-icon--done" />
                    <span class="step-line" style="width:85%" />
                  </div>
                  <div class="plan-step active">
                    <span class="step-spinner" />
                    <span class="step-line" style="width:65%" />
                  </div>
                  <div class="plan-step">
                    <span class="step-dot" />
                    <span class="step-line" style="width:80%" />
                  </div>
                </div>
                <!-- Report card -->
                <div class="report-card">
                  <div class="report-card-header">
                    <FileText :size="14" class="report-icon" />
                    <span class="report-title-line" />
                    <span class="report-menu-dots">···</span>
                  </div>
                  <div class="report-card-body">
                    <div class="report-meta">
                      <span class="report-meta-line" style="width:40%" />
                      <span class="report-meta-line" style="width:35%" />
                    </div>
                    <div class="report-heading-line" />
                    <div class="report-body-line" style="width:100%" />
                    <div class="report-body-line" style="width:85%" />
                    <div class="report-body-line" style="width:60%" />
                  </div>
                </div>
                <!-- Tool cards row -->
                <div class="bubble-tools">
                  <div class="tool-card"><Globe :size="12" class="tool-icon" /><span class="tool-line" /></div>
                  <div class="tool-card"><Terminal :size="12" class="tool-icon" /><span class="tool-line" /></div>
                </div>
              </div>
              <!-- Right: Pythinker's Computer panel -->
              <div class="preview-pc-panel">
                <div class="pc-panel-header">
                  <div class="pc-panel-title">
                    <Monitor :size="12" class="pc-title-icon" />
                    <span class="pc-title-text">Pythinker's Computer</span>
                  </div>
                  <div class="pc-panel-status">
                    <span class="pc-status-dot" />
                    <span class="pc-status-text" />
                  </div>
                  <div class="pc-panel-controls">
                    <Minimize2 :size="11" class="pc-control-icon" />
                    <X :size="11" class="pc-control-icon" />
                  </div>
                </div>
                <div class="pc-panel-tabs">
                  <span class="pc-tab active">Report</span>
                  <span class="pc-tab">Browser</span>
                </div>
                <div class="pc-panel-content">
                  <!-- Document skeleton -->
                  <div class="pc-doc">
                    <div class="pc-doc-title" />
                    <div class="pc-doc-divider" />
                    <div class="pc-doc-section-title" />
                    <div class="pc-doc-lines">
                      <div class="pc-doc-line" style="width:100%" />
                      <div class="pc-doc-line" style="width:95%" />
                      <div class="pc-doc-line" style="width:80%" />
                      <div class="pc-doc-line" style="width:100%" />
                      <div class="pc-doc-line" style="width:70%" />
                    </div>
                    <div class="pc-doc-divider" />
                    <div class="pc-doc-section-title" />
                    <div class="pc-doc-lines">
                      <div class="pc-doc-line" style="width:90%" />
                      <div class="pc-doc-line" style="width:100%" />
                      <div class="pc-doc-line" style="width:85%" />
                      <div class="pc-doc-line" style="width:65%" />
                    </div>
                    <div class="pc-doc-divider" />
                    <div class="pc-doc-section-title" />
                    <div class="pc-doc-lines">
                      <div class="pc-doc-line" style="width:100%" />
                      <div class="pc-doc-line" style="width:75%" />
                      <div class="pc-doc-line" style="width:90%" />
                    </div>
                  </div>
                </div>
                <!-- Replay bar at bottom -->
                <div class="pc-replay-bar">
                  <span class="pc-replay-track" />
                  <span class="pc-replay-label">replay</span>
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
import { Server, ArrowRight, Play, Globe, Terminal, Monitor, Minimize2, X, FileText, CheckCircle } from 'lucide-vue-next'

const scrollTo = (id: string) => {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
}
</script>

<style scoped>
/* ── Hero section ─────────────────────────────── */
.hero {
  position: relative; min-height: 100vh; display: flex;
  align-items: center; justify-content: center; padding: 100px 24px 32px; overflow: hidden;
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

/* ── Hero content layout ──────────────────────── */
.hero-content {
  position: relative; z-index: 1; max-width: 1100px; width: 100%;
  display: flex; flex-direction: column; align-items: center; text-align: center; gap: 24px;
}
.hero-split { display: flex; align-items: center; gap: 48px; width: 100%; }
.hero-text { flex: 1; display: flex; flex-direction: column; align-items: flex-start; text-align: left; gap: 24px; }
.hero-mascot { position: relative; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
.mascot-glow {
  position: absolute; inset: -20%; border-radius: 50%;
  background: radial-gradient(ellipse at center, color-mix(in srgb, var(--text-brand) 12%, transparent) 0%, color-mix(in srgb, #EE9983 6%, transparent) 40%, transparent 70%);
  filter: blur(40px); pointer-events: none;
}
.mascot-img {
  width: 280px; height: auto;
  filter: drop-shadow(0 8px 32px color-mix(in srgb, #213853 20%, transparent));
  animation: mascotFloat 6s ease-in-out infinite;
}
@keyframes mascotFloat { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-12px); } }

/* ── Badge, headline, CTA ─────────────────────── */
.hero-badge {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 16px; border-radius: 999px; font-size: 13px; font-weight: 500;
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--background-card) 80%, transparent);
  border: 1px solid var(--border-main); backdrop-filter: blur(6px);
}
.hero-badge-icon { color: var(--text-brand); }
.hero-headline {
  font-family: var(--font-display); font-size: 52px; font-weight: 400;
  line-height: 1.12; letter-spacing: -0.03em; color: var(--text-primary);
}
.hero-headline-accent {
  background: linear-gradient(135deg, var(--text-primary), var(--text-secondary));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.hero-sub { max-width: 520px; font-size: 16px; line-height: 1.65; color: var(--text-secondary); }
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
.hero-btn--secondary:hover { border-color: var(--border-dark); background: var(--fill-tsp-gray-main); transform: translateY(-2px); }

/* ── Preview window (wider) ───────────────────── */
.hero-preview { width: 100%; max-width: 1100px; margin-top: 32px; }
.preview-window {
  border-radius: 16px; overflow: hidden; border: 1px solid var(--border-main);
  background: color-mix(in srgb, var(--background-card) 90%, transparent);
  backdrop-filter: blur(12px);
  box-shadow: 0 12px 48px color-mix(in srgb, var(--shadow-L) 35%, transparent),
              0 0 0 1px var(--border-light),
              0 0 80px -20px color-mix(in srgb, var(--text-brand) 6%, transparent);
}
.preview-titlebar {
  display: flex; align-items: center; gap: 12px; padding: 10px 16px;
  background: var(--fill-tsp-gray-main); border-bottom: 1px solid var(--border-light);
}
.preview-dots { display: flex; gap: 6px; }
.dot { width: 10px; height: 10px; border-radius: 50%; }
.dot--red { background: #ff5f57; } .dot--yellow { background: #febc2e; } .dot--green { background: #28c840; }
.preview-title { font-size: 12px; font-weight: 500; color: var(--text-tertiary); }
.preview-body { display: flex; min-height: 480px; }

/* ── Left sidebar ─────────────────────────────── */
.preview-sidebar {
  width: 160px; flex-shrink: 0; padding: 10px;
  display: flex; flex-direction: column; gap: 6px;
  border-right: 1px solid var(--border-light);
  background: color-mix(in srgb, var(--fill-tsp-gray-main) 50%, transparent);
}
.sidebar-header { padding: 4px 0 8px; }
.sidebar-action-line {
  height: 28px; border-radius: 6px;
  background: var(--fill-tsp-gray-main); border: 1px solid var(--border-light);
}
.sidebar-nav { display: flex; flex-direction: column; gap: 2px; padding-bottom: 8px; }
.sidebar-nav-item {
  height: 24px; border-radius: 5px;
  background: var(--fill-tsp-gray-main);
  width: 100%;
}
.sidebar-nav-item:first-child { width: 70%; }
.sidebar-nav-item:nth-child(2) { width: 60%; }
.sidebar-nav-item:nth-child(3) { width: 55%; }
.sidebar-section-label {
  height: 8px; width: 50%; border-radius: 3px;
  background: var(--fill-tsp-gray-dark); margin: 4px 0 6px;
}
.sidebar-tasks { display: flex; flex-direction: column; gap: 4px; }
.sidebar-task-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; border-radius: 6px;
}
.sidebar-task-item.active { background: var(--fill-tsp-gray-main); }
.task-icon {
  width: 16px; height: 16px; border-radius: 4px; flex-shrink: 0;
  background: var(--fill-tsp-gray-dark);
}
.task-line {
  height: 7px; flex: 1; border-radius: 3px;
  background: var(--fill-tsp-gray-main);
}
.sidebar-task-item.active .task-line { background: var(--fill-tsp-gray-dark); }

/* ── Chat main area ───────────────────────────── */
.preview-main {
  flex: 1; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px;
  overflow: hidden; min-width: 0;
}
.main-agent-header {
  display: flex; align-items: center; gap: 8px; padding-bottom: 6px;
}
.agent-logo {
  width: 22px; height: 22px; border-radius: 6px;
  background: var(--fill-tsp-gray-dark);
}
.agent-name-line {
  height: 10px; width: 64px; border-radius: 4px;
  background: var(--fill-tsp-gray-dark);
}
.preview-bubble { padding: 10px 14px; border-radius: 10px; display: flex; flex-direction: column; gap: 5px; }
.preview-bubble--agent {
  background: transparent; max-width: 100%;
}
.bubble-line { height: 7px; border-radius: 3px; background: var(--fill-tsp-gray-main); }

/* ── Plan steps ───────────────────────────────── */
.plan-steps { display: flex; flex-direction: column; gap: 6px; padding: 4px 0; }
.plan-step { display: flex; align-items: center; gap: 8px; padding: 3px 0; }
.step-icon--done { color: var(--function-success); flex-shrink: 0; }
.step-spinner {
  width: 13px; height: 13px; border-radius: 50%; flex-shrink: 0;
  border: 2px solid var(--fill-tsp-gray-dark);
  border-top-color: var(--text-brand);
  animation: spin 1s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.step-dot {
  width: 13px; height: 13px; border-radius: 50%; flex-shrink: 0;
  background: var(--fill-tsp-gray-main); border: 1.5px solid var(--border-main);
}
.step-line {
  height: 7px; border-radius: 3px;
  background: var(--fill-tsp-gray-main);
}
.plan-step.completed .step-line { background: var(--fill-tsp-gray-dark); }
.plan-step.active .step-line {
  background: linear-gradient(90deg, var(--fill-tsp-gray-dark) 60%, var(--fill-tsp-gray-main) 100%);
  animation: shimmerLine 2s ease-in-out infinite;
}

/* ── Report card ──────────────────────────────── */
.report-card {
  border-radius: 10px; border: 1px solid var(--border-light);
  overflow: hidden; background: var(--background-card);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--shadow-XS) 60%, transparent);
}
.report-card-header {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  border-bottom: 1px solid var(--border-light);
  background: var(--fill-tsp-gray-main);
}
.report-icon { color: var(--text-tertiary); flex-shrink: 0; }
.report-title-line {
  height: 8px; flex: 1; max-width: 180px; border-radius: 3px;
  background: var(--fill-tsp-gray-dark);
}
.report-menu-dots {
  color: var(--text-tertiary); font-size: 14px; letter-spacing: 1px;
  margin-left: auto; line-height: 1;
}
.report-card-body { padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; }
.report-meta { display: flex; gap: 12px; padding-bottom: 4px; }
.report-meta-line { height: 6px; border-radius: 3px; background: var(--fill-tsp-gray-main); }
.report-heading-line {
  height: 10px; width: 70%; border-radius: 4px;
  background: var(--fill-tsp-gray-dark); margin: 2px 0;
}
.report-body-line { height: 6px; border-radius: 3px; background: var(--fill-tsp-gray-main); }

/* ── Tool cards ───────────────────────────────── */
.bubble-tools { display: flex; gap: 8px; margin-top: 4px; }
.tool-card {
  display: flex; align-items: center; gap: 6px; padding: 5px 10px; border-radius: 6px;
  background: color-mix(in srgb, var(--text-brand) 6%, transparent); border: 1px solid var(--border-light);
}
.tool-icon { color: var(--text-brand); flex-shrink: 0; }
.tool-line { height: 6px; width: 48px; border-radius: 3px; background: var(--fill-tsp-gray-main); }

/* ── Right: Pythinker's Computer panel ────────── */
.preview-pc-panel {
  width: 380px; flex-shrink: 0;
  border-left: 1px solid var(--border-light);
  display: flex; flex-direction: column;
  background: color-mix(in srgb, var(--background-card) 95%, transparent);
}
.pc-panel-header {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-light);
  background: var(--fill-tsp-gray-main);
}
.pc-panel-title { display: flex; align-items: center; gap: 5px; }
.pc-title-icon { color: var(--text-tertiary); }
.pc-title-text {
  font-size: 11px; font-weight: 600; color: var(--text-primary);
  white-space: nowrap;
}
.pc-panel-status {
  display: flex; align-items: center; gap: 4px; margin-left: 4px;
}
.pc-status-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--function-success);
  animation: statusPulse 2s ease-in-out infinite;
}
@keyframes statusPulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
.pc-status-text {
  height: 6px; width: 55px; border-radius: 3px;
  background: var(--fill-tsp-gray-dark);
}
.pc-panel-controls {
  display: flex; align-items: center; gap: 6px; margin-left: auto;
}
.pc-control-icon { color: var(--text-tertiary); cursor: pointer; }

/* ── PC panel tabs ────────────────────────────── */
.pc-panel-tabs {
  display: flex; gap: 0; padding: 0 12px;
  border-bottom: 1px solid var(--border-light);
}
.pc-tab {
  font-size: 11px; font-weight: 500; color: var(--text-tertiary);
  padding: 7px 12px; cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: color 0.15s, border-color 0.15s;
}
.pc-tab.active {
  color: var(--text-primary);
  border-bottom-color: var(--text-brand);
}

/* ── PC panel document content ────────────────── */
.pc-panel-content { flex: 1; padding: 14px; overflow: hidden; }
.pc-doc { display: flex; flex-direction: column; gap: 8px; }
.pc-doc-title {
  height: 12px; width: 75%; border-radius: 4px;
  background: var(--fill-tsp-gray-dark);
}
.pc-doc-divider {
  height: 1px; width: 100%;
  background: var(--border-light); margin: 4px 0;
}
.pc-doc-section-title {
  height: 9px; width: 40%; border-radius: 3px;
  background: color-mix(in srgb, var(--function-error) 18%, transparent);
}
.pc-doc-lines { display: flex; flex-direction: column; gap: 5px; }
.pc-doc-line {
  height: 6px; border-radius: 3px;
  background: var(--fill-tsp-gray-main);
  animation: docShimmer 3s ease-in-out infinite;
}
.pc-doc-line:nth-child(odd) { animation-delay: 0.3s; }
.pc-doc-line:nth-child(even) { animation-delay: 0.7s; }
@keyframes docShimmer {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

/* ── PC panel replay bar ──────────────────────── */
.pc-replay-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 12px;
  border-top: 1px solid var(--border-light);
  background: var(--fill-tsp-gray-main);
}
.pc-replay-track {
  flex: 1; height: 3px; border-radius: 2px;
  background: var(--fill-tsp-gray-dark);
  position: relative; overflow: hidden;
}
.pc-replay-track::after {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0;
  width: 60%; border-radius: 2px;
  background: var(--text-brand);
}
.pc-replay-label {
  font-size: 10px; font-weight: 500; color: var(--text-tertiary);
  white-space: nowrap;
}

/* ── Shimmer animation for active step ────────── */
@keyframes shimmerLine {
  0%, 100% { opacity: 0.7; }
  50% { opacity: 1; }
}

/* ── Transitions ──────────────────────────────── */
.fade-up-enter-active, .fade-up-d1-enter-active, .fade-up-d2-enter-active,
.fade-up-d3-enter-active, .fade-up-d4-enter-active { transition: opacity 0.7s ease, transform 0.7s ease; }
.fade-up-enter-from, .fade-up-d1-enter-from, .fade-up-d2-enter-from,
.fade-up-d3-enter-from, .fade-up-d4-enter-from { opacity: 0; transform: translateY(24px); }
.fade-up-d1-enter-active { transition-delay: 0.1s; }
.fade-up-d2-enter-active { transition-delay: 0.2s; }
.fade-up-d3-enter-active { transition-delay: 0.35s; }
.fade-up-d4-enter-active { transition-delay: 0.55s; }

/* ── Responsive ───────────────────────────────── */
@media (max-width: 768px) {
  .hero { padding: 90px 16px 40px; min-height: auto; }
  .hero-split { flex-direction: column-reverse; gap: 32px; }
  .hero-text { align-items: center; text-align: center; }
  .hero-headline { font-size: 32px; }
  .hero-sub { font-size: 15px; }
  .hero-ctas { flex-direction: column; width: 100%; }
  .hero-btn { width: 100%; justify-content: center; }
  .mascot-img { width: 180px; }
  .preview-body { min-height: 280px; flex-direction: column; }
  .preview-sidebar { display: none; }
  .preview-pc-panel { width: 100%; border-left: none; border-top: 1px solid var(--border-light); max-height: 200px; }
  .pc-doc-lines:last-child { display: none; }
}
@media (min-width: 769px) and (max-width: 1024px) {
  .hero-headline { font-size: 42px; }
  .mascot-img { width: 220px; }
  .preview-sidebar { width: 120px; }
  .preview-pc-panel { width: 280px; }
}
@media (prefers-reduced-motion: reduce) {
  .fade-up-enter-active, .fade-up-d1-enter-active, .fade-up-d2-enter-active,
  .fade-up-d3-enter-active, .fade-up-d4-enter-active { transition: none; }
  .hero-grid { animation: none; }
  .mascot-img { animation: none; }
  .step-spinner { animation: none; }
  .pc-doc-line { animation: none; }
  .pc-status-dot { animation: none; }
}
</style>
