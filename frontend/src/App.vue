<template>
  <router-view />
  <Toast />
</template>

<script setup lang="ts">
import Toast from './components/ui/Toast.vue'
import { useThemeMode } from './composables/useThemeMode'

// Activate reactive theme management app-wide:
//  - listens for OS prefers-color-scheme changes via matchMedia
//  - persists user preference to localStorage (bolt_theme)
//  - keeps .dark class and data-theme attribute in sync
useThemeMode()
</script>
