<template>
  <div class="general-settings">
    <!-- Appearance Section -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon">
          <Palette class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">{{ t('Appearance') }}</h4>
          <p class="section-desc">{{ t('Choose how Pythinker looks on your device') }}</p>
        </div>
      </div>

      <div class="theme-grid">
        <button
          v-for="option in themeOptions"
          :key="option.mode"
          class="theme-card"
          :class="{ 'theme-card-active': themeMode === option.mode }"
          @click="setThemeMode(option.mode)"
        >
          <div class="theme-preview" :class="`theme-preview-${option.mode}`">
            <div class="theme-preview-header">
              <span class="theme-preview-dot" />
              <span class="theme-preview-dot" />
              <span class="theme-preview-dot" />
            </div>
            <div class="theme-preview-body">
              <div class="theme-preview-line theme-preview-line-short" />
              <div class="theme-preview-line theme-preview-line-long" />
              <div class="theme-preview-line theme-preview-line-medium" />
            </div>
          </div>
          <div class="theme-card-label">
            <component :is="option.icon" class="w-3.5 h-3.5" />
            <span>{{ t(option.label) }}</span>
          </div>
          <span class="theme-card-hint">{{ t(option.hint) }}</span>
        </button>
      </div>
    </div>

    <!-- Language & Region Section -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon section-icon-language">
          <Globe class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">{{ t('Language') }} & Region</h4>
          <p class="section-desc">Choose your preferred language for the interface</p>
        </div>
      </div>

      <div class="setting-row">
        <div class="setting-label-group">
          <Languages class="w-4 h-4 text-[var(--icon-tertiary)]" />
          <div class="setting-text">
            <span class="setting-label">Display Language</span>
            <span class="setting-hint">Affects all text and UI elements</span>
          </div>
        </div>
        <Select v-model="selectedLanguage" @update:modelValue="onLanguageChange">
          <SelectTrigger class="settings-select">
            <SelectValue :placeholder="t('Select language')" />
          </SelectTrigger>
          <SelectContent :side-offset="5">
            <SelectItem
              v-for="option in languageOptions"
              :key="option.value"
              :value="option.value"
            >
              <div class="select-option">
                <span class="select-option-flag">{{ option.flag }}</span>
                <span>{{ option.label }}</span>
              </div>
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>

    <!-- Notifications Section -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon section-icon-notifications">
          <Bell class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">{{ t('Notifications') }}</h4>
          <p class="section-desc">{{ t('Control how you get notified about task updates') }}</p>
        </div>
      </div>

      <!-- Desktop Notifications Toggle -->
      <div class="toggle-card" :class="{ 'toggle-card-enabled': desktopNotifications }">
        <div class="toggle-content">
          <div class="toggle-icon-wrapper toggle-icon-notifications">
            <BellRing class="w-5 h-5" />
          </div>
          <div class="toggle-info">
            <h5 class="toggle-title">{{ t('Desktop Notifications') }}</h5>
            <p class="toggle-desc">{{ t('Get browser push notifications when tasks complete') }}</p>
          </div>
        </div>
        <button
          @click="toggleDesktopNotifications"
          class="toggle-switch"
          :class="{ 'toggle-active': desktopNotifications }"
        >
          <span class="toggle-thumb" />
        </button>
      </div>

      <!-- Notification permission warning -->
      <div v-if="notificationDenied" class="notification-warning">
        <TriangleAlert class="w-3.5 h-3.5" />
        <span>{{ t('Notification permission denied. Please enable in browser settings.') }}</span>
      </div>

      <!-- Sound Effects Toggle -->
      <div class="toggle-card" :class="{ 'toggle-card-enabled': soundEffects }">
        <div class="toggle-content">
          <div class="toggle-icon-wrapper toggle-icon-sound">
            <Volume2 class="w-5 h-5" />
          </div>
          <div class="toggle-info">
            <h5 class="toggle-title">{{ t('Sound Effects') }}</h5>
            <p class="toggle-desc">{{ t('Play a sound when tasks finish or need attention') }}</p>
          </div>
        </div>
        <button
          @click="toggleSoundEffects"
          class="toggle-switch"
          :class="{ 'toggle-active': soundEffects }"
        >
          <span class="toggle-thumb" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStorage } from '@vueuse/core'
import {
  Palette,
  Globe,
  Languages,
  Bell,
  BellRing,
  Volume2,
  Sun,
  Moon,
  Monitor,
  TriangleAlert,
} from 'lucide-vue-next'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useLocale } from '@/composables/useI18n'
import { useThemeMode, type ThemeMode } from '@/composables/useThemeMode'
import type { Locale } from '@/locales'

const { t } = useI18n()

// ── Theme ────────────────────────────────────────────────────────────
const { themeMode, setThemeMode } = useThemeMode()

const themeOptions = [
  { mode: 'light' as ThemeMode, label: 'Light', hint: 'Clean and bright', icon: Sun },
  { mode: 'dark' as ThemeMode, label: 'Dark', hint: 'Easy on the eyes', icon: Moon },
  { mode: 'system' as ThemeMode, label: 'System', hint: 'Matches your OS', icon: Monitor },
]

// ── Language ─────────────────────────────────────────────────────────
const { currentLocale, setLocale } = useLocale()
const selectedLanguage = ref<Locale>(currentLocale.value)

interface LanguageOption {
  value: string
  label: string
  flag: string
}

const languageOptions: LanguageOption[] = [
  { value: 'en', label: t('English'), flag: '🇺🇸' },
]

const onLanguageChange = (value: string) => {
  if (value && typeof value === 'string') {
    const locale = value as Locale
    setLocale(locale)
  }
}

// ── Notifications ────────────────────────────────────────────────────
const desktopNotifications = useStorage('pythinker-desktop-notifications', false)
const soundEffects = useStorage('pythinker-sound-effects', true)
const notificationDenied = ref(false)

const toggleDesktopNotifications = async () => {
  if (!desktopNotifications.value) {
    // Turning on — request permission
    if ('Notification' in window) {
      const permission = await Notification.requestPermission()
      if (permission === 'granted') {
        desktopNotifications.value = true
        notificationDenied.value = false
      } else {
        notificationDenied.value = true
      }
    }
  } else {
    desktopNotifications.value = false
    notificationDenied.value = false
  }
}

const toggleSoundEffects = () => {
  soundEffects.value = !soundEffects.value
}
</script>

<style scoped>
.general-settings {
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: 100%;
  animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ── Section Cards ──────────────────────────────────────────────── */
.section-card {
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 20px;
}

.section-header {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-light);
}

.section-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: var(--fill-blue);
  border-radius: 10px;
  color: var(--text-brand);
  flex-shrink: 0;
}

.section-icon-language {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.section-icon-notifications {
  background: rgba(245, 158, 11, 0.1);
  color: #f59e0b;
}

.section-info {
  flex: 1;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.section-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  line-height: 1.4;
}

/* ── Theme Picker Grid ──────────────────────────────────────────── */
.theme-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.theme-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: var(--background-white-main);
  border: 2px solid var(--border-light);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.theme-card:hover {
  border-color: var(--border-dark);
  background: var(--fill-tsp-white-light);
}

.theme-card-active {
  border-color: var(--text-brand);
  background: var(--fill-blue);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.12);
}

.theme-card-active:hover {
  border-color: var(--text-brand);
  background: var(--fill-blue);
}

.theme-card-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.theme-card-hint {
  font-size: 11px;
  color: var(--text-tertiary);
}

/* ── Theme Preview (mini window mockup) ─────────────────────────── */
.theme-preview {
  width: 100%;
  aspect-ratio: 16 / 10;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border-light);
}

.theme-preview-header {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
}

.theme-preview-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
}

.theme-preview-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 4px 8px 8px;
}

.theme-preview-line {
  height: 4px;
  border-radius: 2px;
}

.theme-preview-line-short {
  width: 40%;
}

.theme-preview-line-long {
  width: 80%;
}

.theme-preview-line-medium {
  width: 60%;
}

/* Light theme preview */
.theme-preview-light {
  background: #ffffff;
}

.theme-preview-light .theme-preview-header {
  background: #f3f4f6;
}

.theme-preview-light .theme-preview-dot {
  background: #d1d5db;
}

.theme-preview-light .theme-preview-line {
  background: #e5e7eb;
}

.theme-preview-light .theme-preview-line-short {
  background: #d1d5db;
}

/* Dark theme preview */
.theme-preview-dark {
  background: #1a1a2e;
}

.theme-preview-dark .theme-preview-header {
  background: #16162a;
}

.theme-preview-dark .theme-preview-dot {
  background: #374151;
}

.theme-preview-dark .theme-preview-line {
  background: #2d2d4a;
}

.theme-preview-dark .theme-preview-line-short {
  background: #374160;
}

/* System theme preview (split) */
.theme-preview-system {
  background: linear-gradient(135deg, #ffffff 50%, #1a1a2e 50%);
}

.theme-preview-system .theme-preview-header {
  background: linear-gradient(135deg, #f3f4f6 50%, #16162a 50%);
}

.theme-preview-system .theme-preview-dot {
  background: #9ca3af;
}

.theme-preview-system .theme-preview-line {
  background: linear-gradient(135deg, #e5e7eb 50%, #2d2d4a 50%);
}

.theme-preview-system .theme-preview-line-short {
  background: linear-gradient(135deg, #d1d5db 50%, #374160 50%);
}

/* ── Language Setting Row ───────────────────────────────────────── */
.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.setting-label-group {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex: 1;
}

.setting-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.setting-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.setting-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

.settings-select {
  width: 200px;
  height: 40px;
  border-radius: 10px;
  background: var(--background-white-main);
  border: 1px solid var(--border-main);
  font-size: 14px;
  transition: all 0.2s ease;
}

.settings-select:hover {
  border-color: var(--border-dark);
}

.settings-select:focus {
  border-color: var(--text-brand);
  box-shadow: 0 0 0 3px var(--fill-blue);
}

.select-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.select-option-flag {
  font-size: 16px;
}

/* ── Toggle Cards (Notifications) ───────────────────────────────── */
.toggle-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: var(--background-white-main);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  transition: all 0.3s ease;
  margin-bottom: 10px;
}

.toggle-card:last-child {
  margin-bottom: 0;
}

.toggle-card-enabled {
  border-color: rgba(59, 130, 246, 0.2);
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.04) 0%, transparent 100%);
}

.toggle-content {
  display: flex;
  align-items: center;
  gap: 14px;
}

.toggle-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  flex-shrink: 0;
}

.toggle-icon-notifications {
  background: rgba(245, 158, 11, 0.1);
  color: #f59e0b;
}

.toggle-icon-sound {
  background: rgba(168, 85, 247, 0.1);
  color: #a855f7;
}

.toggle-info {
  flex: 1;
}

.toggle-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 3px;
}

.toggle-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.4;
  max-width: 300px;
}

.toggle-switch {
  position: relative;
  width: 48px;
  height: 28px;
  background: var(--fill-tsp-gray-dark);
  border-radius: 14px;
  transition: all 0.3s ease;
  flex-shrink: 0;
}

.toggle-active {
  background: var(--text-brand);
}

.toggle-thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 22px;
  height: 22px;
  background: #fff;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
  transition: transform 0.3s ease;
}

.toggle-active .toggle-thumb {
  transform: translateX(20px);
}

/* ── Notification Warning ───────────────────────────────────────── */
.notification-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin-bottom: 10px;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: 10px;
  font-size: 12px;
  color: #d97706;
  line-height: 1.4;
}
</style>
