<template>
  <div class="h-screen flex overflow-hidden bg-[var(--background-white-main)]">
    <a href="#main-content" class="skip-to-content">Skip to main content</a>
    <LeftPanel />
    <main id="main-content" class="flex-1 min-w-0 h-full py-0 pr-0 relative">
      <div class="flex h-full bg-[var(--background-gray-main)]">
        <div class="flex flex-1 min-w-0 min-h-0">
          <router-view />
          <FilePanel />
        </div>
      </div>
    </main>
  </div>
  <TakeOverView />
  <CustomDialog />
  <PromptDialog />
  <SessionFileList />
  <SettingsDialog />
  <ContextMenu />
</template>

<script setup lang="ts">
import LeftPanel from '@/components/LeftPanel.vue';
import CustomDialog from '@/components/ui/CustomDialog.vue';
import PromptDialog from '@/components/ui/PromptDialog.vue';
import ContextMenu from '@/components/ui/ContextMenu.vue';
import TakeOverView from '@/components/TakeOverView.vue';
import SessionFileList from '@/components/SessionFileList.vue';
import FilePanel from '@/components/FilePanel.vue';
import SettingsDialog from '@/components/settings/SettingsDialog.vue';
</script>

<style scoped>
.skip-to-content {
  position: absolute;
  left: -9999px;
  top: auto;
  width: 1px;
  height: 1px;
  overflow: hidden;
}
.skip-to-content:focus {
  position: fixed;
  top: 8px;
  left: 8px;
  width: auto;
  height: auto;
  padding: 8px 16px;
  background: var(--color-primary, #000);
  color: white;
  z-index: 9999;
  border-radius: 4px;
  text-decoration: none;
  font-size: 14px;
}

</style>
