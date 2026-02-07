<template>
  <div class="settings-container flex flex-col md:flex-row h-[580px] md:h-[700px] max-h-[90vh]">
    <!-- Tab Sidebar -->
    <div
      class="settings-sidebar md:w-[240px] overflow-x-auto md:overflow-x-visible pb-2 md:pb-0 relative">
      <!-- Logo Section -->
      <div class="sidebar-header items-center hidden px-5 pt-6 pb-4 md:flex">
        <div class="flex items-center gap-1">
          <div class="logo-glow">
            <Bot :size="28" class="text-[var(--text-brand)]" />
          </div>
          <PythinkerLogoTextIcon width="90" height="28" />
        </div>
      </div>

      <!-- Mobile Header -->
      <h3
        class="block md:hidden self-stretch pt-4 md:pt-5 px-4 md:px-5 pb-2 text-[18px] font-semibold leading-7 text-[var(--text-primary)] sticky left-0">
        {{ t('Settings') }}
      </h3>

      <!-- Tab Navigation -->
      <div class="relative flex w-full max-md:pe-3">
        <div
          class="flex-1 flex-shrink-0 flex items-start self-stretch px-3 overflow-auto w-max md:w-full border-b border-[var(--border-main)] md:border-b-0 md:flex-col md:gap-1 md:px-3 max-md:gap-[10px]">
          <nav class="flex md:gap-1 gap-[10px] md:flex-col items-start self-stretch w-full">
            <button
              v-for="(tab, index) in tabs"
              :key="tab.id"
              @click="setActiveTab(tab.id)"
              :style="{ animationDelay: `${index * 50}ms` }"
              :class="[
                'settings-tab-btn group flex px-2 py-2.5 items-center text-[13px] leading-5 max-md:whitespace-nowrap md:h-10 md:gap-3 md:self-stretch md:px-4 md:rounded-xl transition-all duration-200',
                activeTab === tab.id
                  ? 'settings-tab-active'
                  : 'settings-tab-inactive'
              ]">
              <span
                class="tab-icon-wrapper hidden md:flex items-center justify-center w-8 h-8 rounded-lg transition-all duration-200"
                :class="activeTab === tab.id ? 'tab-icon-active' : 'tab-icon-inactive'">
                <component :is="tab.icon" class="w-[18px] h-[18px]" />
              </span>
              <span class="truncate font-medium">{{ t(tab.label) }}</span>
              <ChevronRight
                v-if="activeTab === tab.id"
                class="hidden md:block ml-auto w-4 h-4 opacity-50 transition-transform duration-200 group-hover:translate-x-0.5"
              />
            </button>
          </nav>

          <!-- Decorative Divider -->
          <div class="hidden md:block self-stretch px-3 py-3">
            <div class="settings-divider h-[1px]"></div>
          </div>
        </div>
      </div>

      <!-- Sidebar Footer Decoration -->
      <div class="hidden md:block absolute bottom-0 left-0 right-0 h-24 pointer-events-none sidebar-fade"></div>
    </div>

    <!-- Tab Content -->
    <div class="settings-content flex flex-col items-start self-stretch flex-1 overflow-hidden">
      <!-- Content Header -->
      <div
        class="settings-content-header gap-2 items-center px-6 py-5 hidden md:flex self-stretch">
        <!-- Show back button for sub-pages -->
        <button
          v-if="currentSubPage"
          @click="handleBack"
          class="back-btn flex items-center justify-center w-8 h-8 rounded-lg mr-1 transition-all duration-200">
          <ChevronLeft :size="20" />
        </button>
        <div class="flex flex-col">
          <h3 class="text-[20px] font-semibold leading-7 text-[var(--text-primary)] tracking-tight">
            {{ activeTabTitle }}
          </h3>
          <p class="text-xs text-[var(--text-tertiary)] mt-0.5">
            {{ getTabDescription(activeTab) }}
          </p>
        </div>
      </div>

      <!-- Content Body -->
      <div
        class="settings-content-body flex-1 self-stretch items-start overflow-y-auto flex flex-col gap-6 px-4 pt-4 pb-6 md:px-6 md:pt-2">
        <slot :name="currentSlotName" :active-tab="activeTab" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { Bot, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import PythinkerLogoTextIcon from '@/components/icons/PythinkerLogoTextIcon.vue'

export interface TabItem {
  id: string
  label: string
  icon: Component
}

export interface SubPageConfig {
  id: string
  title: string
  parentTabId?: string
}

interface Props {
  tabs: TabItem[]
  defaultTab?: string
  currentSubPage?: string | null
  subPageConfigs?: SubPageConfig[]
}

const props = withDefaults(defineProps<Props>(), {
  defaultTab: undefined,
  currentSubPage: null,
  subPageConfigs: () => []
})

const emit = defineEmits<{
  tabChange: [tabId: string]
  navigateToProfile: []
  back: []
}>()

const { t } = useI18n()

// Active tab state
const activeTab = ref<string>(props.defaultTab || props.tabs[0]?.id || '')

// Tab descriptions for context
const tabDescriptions: Record<string, string> = {
  account: 'Manage your profile and security',
  settings: 'Customize your experience',
  model: 'Configure AI behavior',
  search: 'Set up search preferences',
  agent: 'Fine-tune automation settings',
  skills: 'Enable agent capabilities',
  usage: 'Monitor your activity and costs'
}

// Get tab description
const getTabDescription = (tabId: string) => {
  if (props.currentSubPage === 'profile') {
    return 'Edit your personal information'
  }
  return tabDescriptions[tabId] || ''
}

// Computed active tab title
const activeTabTitle = computed(() => {
  // Show sub-page title if in sub-page
  if (props.currentSubPage) {
    const subPageConfig = props.subPageConfigs.find(config => config.id === props.currentSubPage)
    if (subPageConfig) {
      return t(subPageConfig.title)
    }
  }

  const currentTab = props.tabs.find(tab => tab.id === activeTab.value)
  return currentTab ? t(currentTab.label) : ''
})

// Computed slot name based on current view
const currentSlotName = computed(() => {
  if (props.currentSubPage) {
    const subPageConfig = props.subPageConfigs.find(config => config.id === props.currentSubPage)
    if (subPageConfig && subPageConfig.parentTabId) {
      return `${subPageConfig.parentTabId}-${props.currentSubPage}`
    }
    return props.currentSubPage
  }
  return activeTab.value
})

// Set active tab
const setActiveTab = (tabId: string) => {
  activeTab.value = tabId
  emit('tabChange', tabId)
}

// Handle back button click
const handleBack = () => {
  emit('back')
}

// Expose active tab for parent component
defineExpose({
  activeTab
})
</script>

<style scoped>
.settings-container {
  background: var(--background-gray-main);
  position: relative;
  overflow: hidden;
}

.settings-container::before {
  content: '';
  position: absolute;
  top: -50%;
  right: -20%;
  width: 60%;
  height: 100%;
  background: radial-gradient(
    ellipse at center,
    var(--fill-blue) 0%,
    transparent 70%
  );
  opacity: 0.4;
  pointer-events: none;
}

.settings-sidebar {
  background: linear-gradient(
    180deg,
    var(--fill-tsp-white-light) 0%,
    transparent 100%
  );
  border-right: 1px solid var(--border-main);
  position: relative;
}

.sidebar-header {
  position: relative;
}

.logo-glow {
  position: relative;
}

.logo-glow::after {
  content: '';
  position: absolute;
  inset: -4px;
  background: var(--text-brand);
  opacity: 0.15;
  filter: blur(8px);
  border-radius: 50%;
}

.settings-tab-btn {
  animation: slideInLeft 0.3s ease-out forwards;
  opacity: 0;
  transform: translateX(-8px);
}

@keyframes slideInLeft {
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.settings-tab-active {
  background: var(--fill-tsp-white-main);
  color: var(--text-primary);
  box-shadow:
    0 1px 3px var(--shadow-XS),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

.settings-tab-inactive {
  color: var(--text-secondary);
}

.settings-tab-inactive:hover {
  background: var(--fill-tsp-white-light);
  color: var(--text-primary);
}

.tab-icon-wrapper {
  flex-shrink: 0;
}

.tab-icon-active {
  background: var(--fill-blue);
  color: var(--text-brand);
}

.tab-icon-inactive {
  background: transparent;
  color: var(--icon-tertiary);
}

.settings-tab-inactive:hover .tab-icon-inactive {
  background: var(--fill-tsp-white-main);
  color: var(--icon-secondary);
}

.settings-divider {
  background: linear-gradient(
    90deg,
    transparent 0%,
    var(--border-main) 20%,
    var(--border-main) 80%,
    transparent 100%
  );
}

.sidebar-fade {
  background: linear-gradient(
    to top,
    var(--background-gray-main) 0%,
    transparent 100%
  );
}

.settings-content {
  position: relative;
  background: var(--background-white-main);
  border-radius: 16px 0 0 16px;
  margin: 8px 0 8px 0;
}

@media (max-width: 768px) {
  .settings-content {
    border-radius: 0;
    margin: 0;
  }
}

.settings-content-header {
  border-bottom: 1px solid var(--border-light);
  background: linear-gradient(
    180deg,
    var(--background-white-main) 0%,
    var(--fill-tsp-white-light) 100%
  );
  position: relative;
}

.settings-content-header::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 24px;
  right: 24px;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    var(--border-main) 10%,
    var(--border-main) 90%,
    transparent 100%
  );
}

.back-btn {
  background: var(--fill-tsp-white-main);
  color: var(--icon-secondary);
}

.back-btn:hover {
  background: var(--fill-tsp-white-dark);
  color: var(--icon-primary);
}

.settings-content-body {
  scrollbar-width: thin;
  scrollbar-color: var(--border-main) transparent;
}

.settings-content-body::-webkit-scrollbar {
  width: 6px;
}

.settings-content-body::-webkit-scrollbar-track {
  background: transparent;
}

.settings-content-body::-webkit-scrollbar-thumb {
  background: var(--border-main);
  border-radius: 3px;
}

.settings-content-body::-webkit-scrollbar-thumb:hover {
  background: var(--border-dark);
}
</style>
