<template>
  <div v-if="showBanner" class="connector-banner" @click="openConnectorDialog()">
    <div class="connector-banner-left">
      <Cable :size="16" class="connector-banner-icon" />
      <span class="connector-banner-text">{{ t('Connect your tools to Pythinker') }}</span>
    </div>
    <div class="connector-banner-right">
      <div class="connector-banner-logos">
        <div
          v-for="app in previewApps"
          :key="app.id"
          class="connector-banner-logo"
          :style="{ backgroundColor: app.color + '20', color: app.color }"
        >
          <component :is="app.icon" :size="14" />
        </div>
      </div>
      <button class="connector-banner-close" @click.stop="dismissBanner">
        <X :size="14" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  Cable,
  X,
  Globe,
  Mail,
  HardDrive,
  MessageSquare,
  BookOpen,
  Calendar,
} from 'lucide-vue-next';
import { useConnectorDialog } from '@/composables/useConnectorDialog';
import { useConnectors } from '@/composables/useConnectors';

const { t } = useI18n();
const { openConnectorDialog } = useConnectorDialog();
const { connectedCount, bannerDismissed, dismissBanner } = useConnectors();

const showBanner = computed(() => connectedCount.value === 0 && !bannerDismissed.value);

interface PreviewApp {
  id: string;
  icon: Component;
  color: string;
}

const previewApps: PreviewApp[] = [
  { id: 'browser', icon: Globe, color: '#3b82f6' },
  { id: 'gmail', icon: Mail, color: '#ea4335' },
  { id: 'outlook', icon: Mail, color: '#0078d4' },
  { id: 'drive', icon: HardDrive, color: '#34a853' },
  { id: 'slack', icon: MessageSquare, color: '#4a154b' },
  { id: 'github', icon: BookOpen, color: '#24292f' },
  { id: 'notion', icon: Calendar, color: '#000000' },
];
</script>

<style scoped>
.connector-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-main);
  background: var(--background-white-main);
  cursor: pointer;
  transition: all 0.15s ease;
  margin-bottom: 8px;
}

.connector-banner:hover {
  border-color: var(--border-dark);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.connector-banner-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.connector-banner-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.connector-banner-text {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.connector-banner-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.connector-banner-logos {
  display: flex;
  gap: 4px;
  align-items: center;
}

.connector-banner-logo {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.connector-banner-close {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: none;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.connector-banner-close:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}
</style>
