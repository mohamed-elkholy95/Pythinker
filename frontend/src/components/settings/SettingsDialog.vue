<template>
  <Dialog v-model:open="isSettingsDialogOpen">
    <DialogContent class="w-[380px] md:w-[95vw] md:max-w-[920px]">
      <DialogTitle></DialogTitle>
      <DialogDescription></DialogDescription>

      <SettingsTabs
        :tabs="tabs"
        :default-tab="defaultTab"
        :current-sub-page="currentSubPage"
        :sub-page-configs="subPageConfigs"
        @tab-change="onTabChange"
        @navigate-to-profile="navigateToProfile"
        @back="goBack">

        <template #account>
          <AccountSettings @navigate-to-profile="navigateToProfile" />
        </template>

        <template #account-profile>
          <ProfileSettings @back="goBack" />
        </template>

        <template #settings>
          <GeneralSettings />
        </template>

        <template #model>
          <ModelSettings />
        </template>

        <template #search>
          <SearchSettings />
        </template>

        <template #agent>
          <AgentSettings />
        </template>

        <template #skills>
          <SkillsSettings @buildWithPythinker="handleBuildWithPythinker" />
        </template>

        <template #usage>
          <UsageSettings />
        </template>

      </SettingsTabs>

    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { UserRound, Settings2, Bot, Search, Workflow, BarChart2, Puzzle } from 'lucide-vue-next'
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { useSettingsDialog } from '@/composables/useSettingsDialog'
import SettingsTabs from './SettingsTabs.vue'
import AccountSettings from './AccountSettings.vue'
import GeneralSettings from './GeneralSettings.vue'
import ProfileSettings from './ProfileSettings.vue'
import ModelSettings from './ModelSettings.vue'
import SearchSettings from './SearchSettings.vue'
import AgentSettings from './AgentSettings.vue'
import SkillsSettings from './SkillsSettings.vue'
import UsageSettings from './UsageSettings.vue'
import type { TabItem, SubPageConfig } from './SettingsTabs.vue'

const router = useRouter()

// Use global settings dialog state
const { isSettingsDialogOpen, defaultTab } = useSettingsDialog()

// Navigation state for sub-pages
const currentSubPage = ref<string | null>(null)

// Tab configuration
const tabs: TabItem[] = [
  {
    id: 'account',
    label: 'Account',
    icon: UserRound
  },
  {
    id: 'settings',
    label: 'General',
    icon: Settings2
  },
  {
    id: 'model',
    label: 'AI Model',
    icon: Bot
  },
  {
    id: 'search',
    label: 'Search',
    icon: Search
  },
  {
    id: 'agent',
    label: 'Agent',
    icon: Workflow
  },
  {
    id: 'skills',
    label: 'Skills',
    icon: Puzzle
  },
  {
    id: 'usage',
    label: 'Usage',
    icon: BarChart2
  }
]

// Sub-page configuration
const subPageConfigs: SubPageConfig[] = [
  {
    id: 'profile',
    title: 'Profile',
    parentTabId: 'account'
  }
]

// Handle tab change
const onTabChange = (_tabId: string) => {
  // Reset sub-page when changing tabs
  currentSubPage.value = null
}

// Navigate to profile sub-page
const navigateToProfile = () => {
  currentSubPage.value = 'profile'
}

// Go back to main view
const goBack = () => {
  currentSubPage.value = null
}

// Handle "Build with Pythinker" - insert skill creation prompt into chat input
const handleBuildWithPythinker = () => {
  // Close the settings dialog first
  isSettingsDialogOpen.value = false

  // The skill creation message
  const skillCreationMessage = 'Help me create a skill together using /skill-creator. First ask me what the skill should do.'

  // Dispatch event to insert message into HomePage chat input
  window.dispatchEvent(new CustomEvent('pythinker:insert-chat-message', {
    detail: { message: skillCreationMessage }
  }))

  // Navigate to home page if not already there
  if (router.currentRoute.value.path !== '/') {
    router.push('/')
  }
}
</script>