<template>
  <div class="general-settings">
    <!-- Section Header -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-icon">
          <Globe class="w-5 h-5" />
        </div>
        <div class="section-info">
          <h4 class="section-title">Language & Region</h4>
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
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Globe, Languages } from 'lucide-vue-next'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useLocale } from '@/composables/useI18n'
import type { Locale } from '@/locales'

// Use i18n for translations
const { t } = useI18n()

// Use the project's i18n composable
const { currentLocale, setLocale } = useLocale()

// Language selection
const selectedLanguage = ref<Locale>(currentLocale.value)

interface LanguageOption {
  value: string
  label: string
  flag: string
}

const languageOptions: LanguageOption[] = [
  { value: 'en', label: t('English'), flag: '🇺🇸' },
  { value: 'zh', label: t('Simplified Chinese'), flag: '🇨🇳' },
]

const onLanguageChange = (value: any) => {
  if (value && typeof value === 'string') {
    const locale = value as Locale
    setLocale(locale)
  }
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
</style>
