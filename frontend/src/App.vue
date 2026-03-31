<template>
  <router-view />
  <Toast />
  <!-- Global mount: takeover events + overlay must work even if layout remounts -->
  <TakeOverView />
</template>

<script setup lang="ts">
import TakeOverView from './components/TakeOverView.vue'
import Toast from './components/ui/Toast.vue'
import { useThemeMode } from './composables/useThemeMode'
import { useResponsiveLeftPanel } from './composables/useLeftPanel'

// Activate reactive theme management app-wide:
//  - listens for OS prefers-color-scheme changes via matchMedia
//  - persists user preference to localStorage (bolt_theme)
//  - keeps .dark class and data-theme attribute in sync
useThemeMode()

// Auto-collapse sidebar on mobile viewports (≤639px).
// Restores user's desktop preference when viewport widens.
useResponsiveLeftPanel()
</script>
