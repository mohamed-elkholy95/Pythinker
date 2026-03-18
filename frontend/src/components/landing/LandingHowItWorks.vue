<template>
  <section id="how-it-works" class="how-section">
    <div class="how-inner">
      <h2 :ref="revealRef" class="section-heading scroll-reveal">How It Works</h2>
      <p :ref="revealRef" class="section-sub scroll-reveal">
        From natural language to results — in three simple steps.
      </p>
      <div class="steps">
        <div class="step-connector" aria-hidden="true">
          <div class="connector-line" />
        </div>
        <div
          v-for="(step, i) in steps"
          :key="step.title"
          :ref="revealRef"
          class="step scroll-reveal"
          :style="{ transitionDelay: `${i * 0.12}s` }"
        >
          <div class="step-badge-area">
            <span class="step-badge">{{ i + 1 }}</span>
            <div :class="['step-icon-wrap', `si--${step.color}`]">
              <component :is="step.icon" :size="22" :stroke-width="1.8" />
            </div>
          </div>
          <h3 class="step-title">{{ step.title }}</h3>
          <p class="step-desc">{{ step.description }}</p>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { CheckCircle, Cpu, MessageSquare } from 'lucide-vue-next'
import { useScrollReveal } from '../../composables/useScrollReveal'

const { revealRef } = useScrollReveal()

const steps = [
  {
    title: 'Tell It What You Need',
    icon: MessageSquare,
    color: 'blue',
    description:
      'Type your task in plain language — from the web, Telegram, or any connected app. No setup required.',
  },
  {
    title: 'It Works Autonomously',
    icon: Cpu,
    color: 'purple',
    description:
      'Pythinker plans the steps, picks the right tools, and executes — you can watch live or walk away.',
  },
  {
    title: 'You Get the Results',
    icon: CheckCircle,
    color: 'green',
    description:
      'Reports, files, code, screenshots — delivered and ready. Everything runs on your own server.',
  },
]
</script>

<style scoped>
.how-section {
  position: relative;
  padding: 120px 24px;
  background: var(--fill-tsp-white-light);
}

.how-inner {
  max-width: 1100px;
  margin: 0 auto;
}

.section-heading {
  font-family: var(--font-display);
  font-size: 42px;
  font-weight: 400;
  letter-spacing: -0.03em;
  color: var(--text-primary);
  text-align: center;
  margin-bottom: 16px;
}

.section-sub {
  font-size: 17px;
  color: var(--text-secondary);
  text-align: center;
  max-width: 480px;
  margin: 0 auto 72px;
  line-height: 1.6;
}

/* ── Steps grid ─────────────────────────────────── */
.steps {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 40px;
  position: relative;
}

.step {
  position: relative;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* ── Badge + Icon combo ─────────────────────────── */
.step-badge-area {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 20px;
}

.step-badge {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-tertiary);
  background: var(--fill-tsp-white-dark, rgba(17, 24, 39, 0.04));
  border: 1px solid var(--border-light);
  margin-bottom: 12px;
  position: relative;
  z-index: 2;
}

.step-icon-wrap {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  z-index: 2;
}

.si--blue {
  background: color-mix(in srgb, #3b82f6 10%, transparent);
  color: #3b82f6;
}

.si--purple {
  background: color-mix(in srgb, #a855f7 10%, transparent);
  color: #a855f7;
}

.si--green {
  background: color-mix(in srgb, #22c55e 10%, transparent);
  color: #22c55e;
}

/* ── Connector line ─────────────────────────────── */
.step-connector {
  position: absolute;
  top: 12px;
  left: 0;
  right: 0;
  height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
  pointer-events: none;
}

.connector-line {
  width: 60%;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    var(--border-main) 20%,
    var(--border-main) 80%,
    transparent 100%
  );
}

/* ── Text ───────────────────────────────────────── */
.step-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.step-desc {
  font-size: 14px;
  line-height: 1.65;
  color: var(--text-secondary);
  max-width: 280px;
}

/* ── Scroll reveal ──────────────────────────────── */
.scroll-reveal {
  opacity: 0;
  transform: translateY(24px);
  transition:
    opacity 0.6s ease,
    transform 0.6s ease;
}

.scroll-reveal.revealed {
  opacity: 1;
  transform: translateY(0);
}

/* ── Responsive ─────────────────────────────────── */
@media (max-width: 768px) {
  .how-section {
    padding: 80px 16px;
  }

  .section-heading {
    font-size: 30px;
  }

  .steps {
    grid-template-columns: 1fr;
    gap: 48px;
  }

  .step-connector {
    display: none;
  }
}

@media (min-width: 769px) and (max-width: 1024px) {
  .section-heading {
    font-size: 36px;
  }

  .steps {
    gap: 28px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .scroll-reveal {
    opacity: 1;
    transform: none;
    transition: none;
  }
}
</style>
