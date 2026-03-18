<template>
  <div
    class="connector-card"
    :class="{
      'connector-card--connected': isConnected,
      'connector-card--disabled': isComingSoon,
    }"
    @click="handleClick"
  >
    <div class="connector-card-icon" :style="{ backgroundColor: connector.brand_color + '14' }">
      <component :is="iconComponent" :size="24" :color="connector.brand_color" />
    </div>
    <div class="connector-card-info">
      <div class="connector-card-name">{{ connector.name }}</div>
      <div class="connector-card-desc">{{ connector.description }}</div>
      <div v-if="isComingSoon" class="connector-card-badge connector-card-badge--soon">
        Coming Soon
      </div>
      <div v-else-if="isBuiltIn && !isConnected" class="connector-card-badge connector-card-badge--builtin">
        Built-in
      </div>
    </div>
    <div class="connector-card-action">
      <div v-if="loading" class="connector-card-spinner" />
      <Check v-else-if="isConnected" :size="18" class="connector-card-check" />
      <Lock v-else-if="isComingSoon" :size="18" class="connector-card-lock" />
      <Plus v-else :size="18" class="connector-card-plus" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import {
  Check,
  Plus,
  Lock,
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
  MapPin,
  type LucideIcon,
} from 'lucide-vue-next';
import type { CatalogConnector, UserConnector } from '@/api/connectors';

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
  MapPin,
};

const props = defineProps<{
  connector: CatalogConnector;
  userConnector: UserConnector | null;
  loading: boolean;
}>();

const emit = defineEmits<{
  (e: 'connect', connectorId: string): void;
  (e: 'disconnect', userConnectorId: string): void;
  (e: 'setup', connector: CatalogConnector): void;
}>();

const isConnected = computed(
  () => props.userConnector?.status === 'connected' && props.userConnector?.enabled,
);

const isComingSoon = computed(() => props.connector.availability === 'coming_soon');
const isBuiltIn = computed(() => props.connector.availability === 'built_in');

const iconComponent = computed(() => ICON_MAP[props.connector.icon] ?? Globe);

function handleClick() {
  if (props.loading || isComingSoon.value) return;
  if (isConnected.value && props.userConnector) {
    emit('disconnect', props.userConnector.id);
  } else if (props.connector.mcp_template) {
    emit('setup', props.connector);
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
  box-shadow: 0 2px 8px var(--shadow-XS);
  transform: translateY(-1px);
}

.connector-card--connected {
  border-color: var(--function-success-border);
  background: var(--function-success-tsp);
}

.connector-card--connected:hover {
  border-color: rgba(239, 68, 68, 0.35);
}

.connector-card--disabled {
  opacity: 0.55;
  cursor: default;
}

.connector-card--disabled:hover {
  border-color: var(--border-main);
  box-shadow: none;
  transform: none;
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

.connector-card-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
  margin-top: 3px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.connector-card-badge--soon {
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
}

.connector-card-badge--builtin {
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
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
  color: var(--function-success);
}

.connector-card-plus {
  color: var(--text-tertiary);
}

.connector-card-lock {
  color: var(--text-disable);
}

.connector-card:hover .connector-card-plus {
  color: var(--text-primary);
}

.connector-card--connected:hover .connector-card-check {
  color: var(--function-error);
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
