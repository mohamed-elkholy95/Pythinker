<template>
  <Popover v-model:open="isOpen">
    <PopoverTrigger as-child>
      <button class="connector-btn" :title="t('Connectors')">
        <Cable :size="16" />
        <span v-if="connectedCount > 0" class="connector-badge">{{ connectedCount }}</span>
      </button>
    </PopoverTrigger>
    <PopoverContent side="bottom" :side-offset="8" align="start" :avoid-collisions="false" class="connector-popover">
      <div class="connector-popover-content">
        <!-- Connector list -->
        <div class="connector-list">
          <div v-if="loadingCatalog" class="connector-list-empty">
            {{ t('Loading...') }}
          </div>
          <template v-else>
            <div
              v-for="conn in topConnectors"
              :key="conn.id"
              class="connector-item"
              @click="handleToggle(conn)"
            >
              <div class="connector-item-icon" :style="{ color: conn.brand_color }">
                <component :is="getIcon(conn.icon)" :size="16" />
              </div>
              <span class="connector-item-name">{{ conn.name }}</span>
              <div class="connector-item-action">
                <template v-if="mutatingId === conn.id">
                  <div class="connector-spinner" />
                </template>
                <template v-else-if="isConnected(conn.id)">
                  <div class="connector-toggle connector-toggle--on">
                    <div class="connector-toggle-thumb" />
                  </div>
                </template>
                <template v-else>
                  <span class="connector-action-text">{{ t('Connect') }}</span>
                </template>
              </div>
            </div>
          </template>
        </div>

        <!-- Footer -->
        <div class="connector-footer">
          <button class="connector-footer-btn connector-footer-btn--border" @click="handleAddConnectors">
            <Plus :size="14" />
            <span>{{ t('Add connectors') }}</span>
          </button>
          <button class="connector-footer-btn" @click="handleManageConnectors">
            <SlidersHorizontal :size="14" />
            <span>{{ t('Manage connectors') }}</span>
          </button>
        </div>
      </div>
    </PopoverContent>
  </Popover>
</template>

<script setup lang="ts">
import { ref, computed, watch, type Component } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  Cable,
  Plus,
  SlidersHorizontal,
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
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useConnectorDialog } from '@/composables/useConnectorDialog';
import { useConnectors } from '@/composables/useConnectors';
import type { CatalogConnector } from '@/api/connectors';

const { t } = useI18n();
const { openConnectorDialog } = useConnectorDialog();
const {
  catalogConnectors,
  userConnectors,
  connectedCount,
  loadingCatalog,
  loadCatalog,
  loadUserConnectors,
  connectAppConnector,
  disconnectConnector,
} = useConnectors();

const ICON_MAP: Record<string, LucideIcon> = {
  Globe, Mail, Calendar, HardDrive, MessageSquare,
  BookOpen, Zap, CheckSquare, LayoutGrid, Server,
};

const isOpen = ref(false);
const mutatingId = ref<string | null>(null);

const topConnectors = computed(() => catalogConnectors.value.slice(0, 6));

function getIcon(iconName: string): Component {
  return ICON_MAP[iconName] ?? Globe;
}

function isConnected(connectorId: string): boolean {
  return userConnectors.value.some(
    (uc) => uc.connector_id === connectorId && uc.status === 'connected' && uc.enabled,
  );
}

async function handleToggle(conn: CatalogConnector) {
  if (mutatingId.value) return;
  mutatingId.value = conn.id;

  const existing = userConnectors.value.find(
    (uc) => uc.connector_id === conn.id && uc.status === 'connected',
  );
  if (existing) {
    await disconnectConnector(existing.id);
  } else {
    await connectAppConnector(conn.id);
  }
  mutatingId.value = null;
}

function handleAddConnectors() {
  isOpen.value = false;
  openConnectorDialog('custom-api');
}

function handleManageConnectors() {
  isOpen.value = false;
  openConnectorDialog('apps');
}

// Lazy load on first open
let loaded = false;
watch(isOpen, (open) => {
  if (open && !loaded) {
    loaded = true;
    loadCatalog();
    loadUserConnectors();
  }
});
</script>

<style scoped>
.connector-btn {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s ease;
  background: var(--background-white-main);
  border: 1px solid var(--border-main);
  color: var(--text-secondary);
  position: relative;
}

.connector-btn:hover {
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-dark);
  color: var(--text-primary);
}

.connector-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  /* --bolt-elements-item-contentAccent: #000 light / #fff dark */
  background: var(--bolt-elements-item-contentAccent);
  /* --text-onblack: #fff light / rgba(0,0,0,0.85) dark — always contrasts with contentAccent */
  color: var(--text-onblack);
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.connector-popover {
  width: 260px !important;
  padding: 0 !important;
}

.connector-popover-content {
  display: flex;
  flex-direction: column;
}

.connector-list {
  padding: 2px 0;
}

.connector-list-empty {
  padding: 12px 10px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 12px;
}

.connector-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  cursor: pointer;
  transition: background 0.1s ease;
  border-bottom: 1px solid var(--border-light, var(--border-main));
}

.connector-item:last-child {
  border-bottom: none;
}

.connector-item:hover {
  background: var(--fill-tsp-gray-main);
}

.connector-item-icon {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.connector-item-name {
  flex: 1;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
}

.connector-item-action {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.connector-action-text {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.connector-item:hover .connector-action-text {
  color: var(--text-secondary);
}

/* Toggle switch */
.connector-toggle {
  width: 30px;
  height: 16px;
  border-radius: 8px;
  padding: 2px;
  cursor: pointer;
  transition: background 0.2s ease;
  background: var(--fill-tsp-gray-dark, #e5e7eb);
}

.connector-toggle--on {
  background: #22c55e;
}

.connector-toggle-thumb {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: white;
  transition: transform 0.2s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}

.connector-toggle--on .connector-toggle-thumb {
  transform: translateX(14px);
}

.connector-spinner {
  width: 14px;
  height: 14px;
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

/* Footer */
.connector-footer {
  border-top: 1px solid var(--border-light, var(--border-main));
  padding: 2px 0;
}

.connector-footer-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  border: none;
  background: transparent;
  transition: all 0.1s ease;
}

.connector-footer-btn--border {
  border-bottom: 1px solid var(--border-light, var(--border-main));
}

.connector-footer-btn:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}
</style>
