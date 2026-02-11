<template>
  <div v-if="showBanner" class="connector-banner" @click="openConnectorDialog()">
    <div class="connector-banner-icon-wrap">
      <Cable :size="16" class="connector-banner-icon" />
    </div>
    <span class="connector-banner-text">{{ t('Connect your tools to Pythinker') }}</span>
    <div class="connector-banner-right">
      <img
        alt="Connectors preview"
        class="connector-banner-preview"
        src="https://files.manuscdn.com/webapp/_next/static/media/connectorsLight.907a46cd.png"
      />
      <button class="connector-banner-close" @click.stop="handleClose">
        <X :size="16" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { Cable, X } from 'lucide-vue-next';
import { useConnectorDialog } from '@/composables/useConnectorDialog';
import { useConnectors } from '@/composables/useConnectors';

const { t } = useI18n();
const { openConnectorDialog } = useConnectorDialog();
const { connectedCount, bannerDismissed, dismissBanner } = useConnectors();
const props = withDefaults(
  defineProps<{
    forceVisible?: boolean;
  }>(),
  {
    forceVisible: false,
  }
);
const emit = defineEmits<{
  (e: 'close'): void;
}>();

const manuallyHidden = ref(false);

const showBanner = computed(() => {
  if (manuallyHidden.value) return false;
  return props.forceVisible || (connectedCount.value === 0 && !bannerDismissed.value);
});

const handleClose = () => {
  manuallyHidden.value = true;
  emit('close');
  // In normal mode, persist dismissal behavior.
  // In forceVisible mode (home hero), hide only for current view.
  if (!props.forceVisible) {
    dismissBanner();
  }
};
</script>

<style scoped>
.connector-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 18px;
  padding: 0;
  border-radius: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  transition: color 0.15s ease, background-color 0.15s ease;
}

.connector-banner-icon {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.connector-banner-icon-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
}

.connector-banner-text {
  font-size: 13px;
  line-height: 18px;
  font-weight: 500;
  letter-spacing: -0.091px;
  color: var(--text-secondary);
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.connector-banner-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-shrink: 0;
}

.connector-banner-preview {
  height: 22px;
  width: auto;
  display: block;
}

.connector-banner-close {
  width: 20px;
  height: 20px;
  border-radius: 9999px;
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
  opacity: 0.7;
}

.connector-banner:hover .connector-banner-icon,
.connector-banner:hover .connector-banner-text {
  color: var(--text-primary);
}

:global(.dark) .connector-banner:hover .connector-banner-icon,
:global(.dark) .connector-banner:hover .connector-banner-text {
  color: #edf2f9;
}

:global(.dark) .connector-banner-close {
  color: #aeb7c5;
}

:global(.dark) .connector-banner-close:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #eef3fb;
  opacity: 1;
}

:global(.dark) .connector-banner-preview {
  filter: brightness(0.88) saturate(0.9);
}

@media (max-width: 900px) {
  .connector-banner-text {
    font-size: 12px;
  }
}
</style>
