# Thinking Indicator Warm/Loading Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the thinking indicator feel like a warm, active loader with light warm bulb tones, solid black angled rays, and a slightly slower cadence. Increase the indicator size slightly across all instances.

**Architecture:** Keep the existing component API. Apply visual changes within `ThinkingIndicator.vue` by adjusting SVG/CSS for rays and colors. Update any local size override so the indicator grows everywhere.

**Tech Stack:** Vue 3 SFC, scoped CSS, SVG.

---

### Task 1: Update SVG gradient and core colors

**Files:**
- Modify: `frontend/src/components/ui/ThinkingIndicator.vue`

**Step 1: Update the bulb gradient stops**

Replace the `bulb-fuel` stops with the following:

```vue
<linearGradient id="bulb-fuel" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0%" stop-color="#f8e5c4" stop-opacity="0.35" />
  <stop offset="40%" stop-color="#f2c88a" stop-opacity="0.65" />
  <stop offset="100%" stop-color="#e3a45a" stop-opacity="0.9" />
</linearGradient>
```

**Step 2: Lighten lamp outline/filament/circuit tones**

Update these CSS rules:

```css
.lamp-outline {
  stroke: #3b2a1a;
}

.circuit-lines line {
  stroke: #3b2a1a;
}

.lamp-filament {
  stroke: #4a3017;
}

.lamp-filament.core {
  animation: filament-pulse 1.8s ease-in-out infinite;
}

.filament-node {
  fill: #f2b66b;
}
```

**Step 3: Adjust filament pulse colors**

Update the keyframe to a warmer, lighter pulse:

```css
@keyframes filament-pulse {
  0%, 100% {
    stroke: #4a3017;
    opacity: 0.6;
  }
  50% {
    stroke: #6d4220;
    opacity: 0.9;
  }
}
```

### Task 2: Remove horizontal loading rays

**Files:**
- Modify: `frontend/src/components/ui/ThinkingIndicator.vue`

**Step 1: Remove the loading-ray SVG lines**

Delete the `<!-- Loading rays — left-to-right progression -->` block of `loading-ray` lines.

**Step 2: Remove loading-ray styles and keyframes**

Delete the `.loading-ray` styles, their staggered delay rules, the `@keyframes loading-ray`, and any dark-mode overrides specific to `.loading-ray`.

### Task 3: Keep angled rays black and slow cadence slightly

**Files:**
- Modify: `frontend/src/components/ui/ThinkingIndicator.vue`

**Step 1: Set rays to solid black and slow cadence**

Update ray styles:

```css
.lamp-ray {
  stroke: #000000;
  animation: ray-appear 2.4s ease-in-out infinite;
}

.lamp-ray-s {
  stroke: #000000;
  animation: ray-appear-s 2.4s ease-in-out infinite;
}
```

**Step 2: Keep rays black in dark mode**

```css
:deep(.dark) .lamp-ray,
.dark .lamp-ray,
:deep(.dark) .lamp-ray-s,
.dark .lamp-ray-s {
  stroke: #000000;
}
```

### Task 4: Increase indicator size across all instances

**Files:**
- Modify: `frontend/src/components/ui/ThinkingIndicator.vue`
- Modify: `frontend/src/pages/ChatPage.vue`

**Step 1: Increase base lamp size**

```css
.thinking-lamp {
  width: 22px;
  height: 26px;
}

.thinking-lamp.lamp-with-text {
  width: 20px;
  height: 24px;
}
```

**Step 2: Update planning override size**

In `frontend/src/pages/ChatPage.vue`, update:

```css
.planning-thinking :deep(.thinking-lamp) {
  width: 20px;
  height: 24px;
}
```

### Task 5: Manual verification

**Files:**
- Verify: `frontend/src/components/ui/ThinkingIndicator.vue`
- Verify: `frontend/src/pages/ChatPage.vue`, `frontend/src/components/ChatMessage.vue`, `frontend/src/components/ui/StreamingThinkingIndicator.vue`

**Step 1: Run the dev server**

Run: `cd frontend && bun run dev`

Expected: Vite server starts on `http://localhost:5174`.

**Step 2: Visual check (no automated tests per approval)**

Confirm in light and dark themes:
- Bulb reads warm and lit.
- Angled rays are black and pulse more slowly.
- Indicator is slightly larger in all instances.

**Step 3: Commit**

```bash
git add frontend/src/components/ui/ThinkingIndicator.vue frontend/src/pages/ChatPage.vue
git commit -m "style: warm thinking indicator with slower black rays"
```
