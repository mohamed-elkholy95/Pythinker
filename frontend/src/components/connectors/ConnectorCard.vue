<template>
  <div
    class="connector-card"
    :class="{ 'connector-card--connected': isConnected }"
    @click="handleClick"
  >
    <div class="connector-card-icon" :style="{ backgroundColor: connector.brand_color + '14' }">
      <component :is="iconComponent" :size="24" :color="connector.brand_color" />
    </div>
    <div class="connector-card-info">
      <div class="connector-card-name">{{ connector.name }}</div>
      <div class="connector-card-desc">{{ connector.description }}</div>
    </div>
    <div class="connector-card-action">
      <div v-if="loading" class="connector-card-spinner" />
      <Check v-else-if="isConnected" :size="18" class="connector-card-check" />
      <Plus v-else :size="18" class="connector-card-plus" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import {
  Check,
  Plus,
  Globe,
  Mail,
  Calendar,
  HardDrive,
  MessageSquare,
  BookOpen,
  Zap,
  CheckSquare,
  LayoutGrid,
  Server,
  type LucideIcon,
} from 'lucide-vue-next';
import type { CatalogConnector, UserConnector } from '@/api/connectors';

// Avoid importing Github directly since it may not exist in all lucide versions
// Use a safe icon map
const ICON_MAP: Record<string, LucideIcon> = {
  Globe,
  Mail,
  Calendar,
  HardDrive,
  MessageSquare,
  BookOpen,
  Zap,
  CheckSquare,
  LayoutGrid,
  Server,
};

const props = defineProps<{
  connector: CatalogConnector;
  userConnector: UserConnector | null;
  loading: boolean;
}>();

const emit = defineEmits<{
  (e: 'connect', connectorId: string): void;
  (e: 'disconnect', userConnectorId: string): void;
}>();

const isConnected = computed(
  () => props.userConnector?.status === 'connected' && props.userConnector?.enabled,
);

const iconComponent = computed(() => ICON_MAP[props.connector.icon] ?? Globe);

function handleClick() {
  if (props.loading) return;
  if (isConnected.value && props.userConnector) {
    emit('disconnect', props.userConnector.id);
  } else {
    emit('connect', props.connector.id);
  }
}
</script>

<style scoped>
.connector-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--border-main);
  background: var(--background-white-main);
  cursor: pointer;
  transition: all 0.15s ease;
}

.connector-card:hover {
  border-color: var(--border-dark);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  transform: translateY(-1px);
}

.connector-card--connected {
  border-color: #22c55e40;
  background: #22c55e08;
}

.connector-card--connected:hover {
  border-color: #ef444440;
}

.connector-card-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.connector-card-info {
  flex: 1;
  min-width: 0;
}

.connector-card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
}

.connector-card-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.connector-card-action {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.connector-card-check {
  color: #22c55e;
}

.connector-card-plus {
  color: var(--text-tertiary);
}

.connector-card:hover .connector-card-plus {
  color: var(--text-primary);
}

.connector-card--connected:hover .connector-card-check {
  color: #ef4444;
}

.connector-card-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border-main);
  border-top-color: var(--text-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
