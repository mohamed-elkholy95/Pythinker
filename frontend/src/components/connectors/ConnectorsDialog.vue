<template>
  <Dialog v-model:open="isConnectorDialogOpen">
    <DialogContent
      class="w-[95vw] max-w-[900px] h-[80vh] max-h-[800px]"
      title="Connectors"
      description="Connect external APIs and MCP servers"
      :hideCloseButton="false"
    >
      <div class="connectors-dialog">
        <!-- Header -->
        <div class="connectors-header">
          <h2 class="connectors-title">{{ t('Connectors') }}</h2>
        </div>

        <!-- Tab bar + search on same row -->
        <div class="connectors-tabs-row">
          <div class="connectors-tabs">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              class="connectors-tab"
              :class="{ 'connectors-tab--active': activeTab === tab.id }"
              @click="activeTab = tab.id"
            >
              {{ tab.label }}
            </button>
          </div>
          <div v-if="activeTab === 'apps'" class="connectors-search">
            <Search :size="14" class="connectors-search-icon" />
            <input
              v-model="searchQuery"
              type="text"
              class="connectors-search-input"
              :placeholder="t('Search')"
            />
          </div>
        </div>

        <!-- Content -->
        <div class="connectors-content">
          <!-- Apps tab -->
          <div v-if="activeTab === 'apps'" class="connectors-apps">
            <!-- Setup form overlay -->
            <template v-if="setupConnector">
              <AppSetupForm
                ref="setupFormRef"
                :connector="setupConnector"
                @submit="handleSetupSubmit"
                @cancel="setupConnector = null"
              />
            </template>

            <!-- Normal grid -->
            <template v-else>
              <div v-if="loadingCatalog" class="connectors-loading">
                <div class="connectors-spinner" />
                <span>{{ t('Loading connectors...') }}</span>
              </div>
              <div v-else class="connectors-grid">
                <ConnectorCard
                  v-for="conn in filteredCatalog"
                  :key="conn.id"
                  :connector="conn"
                  :userConnector="getUserConnectorFor(conn.id)"
                  :loading="mutatingId === conn.id"
                  @connect="handleConnect"
                  @disconnect="handleDisconnect"
                  @setup="handleSetup"
                />
              </div>
              <div v-if="!loadingCatalog && filteredCatalog.length === 0" class="connectors-empty">
                {{ t('No connectors found') }}
              </div>
            </template>
          </div>

          <!-- Custom API tab -->
          <div v-if="activeTab === 'custom-api'" class="connectors-custom">
            <div class="connectors-custom-form-section">
              <h3 class="connectors-section-title">{{ t('Add Custom API') }}</h3>
              <CustomApiForm @submit="handleCreateApi" @cancel="activeTab = 'apps'" />
            </div>
            <div v-if="customApiConnectors.length > 0" class="connectors-custom-list">
              <h3 class="connectors-section-title">{{ t('Your API Connectors') }}</h3>
              <div v-for="uc in customApiConnectors" :key="uc.id" class="connectors-custom-item">
                <div class="connectors-custom-item-info">
                  <Globe :size="16" class="connectors-custom-item-icon" />
                  <div>
                    <div class="connectors-custom-item-name">{{ uc.name }}</div>
                    <div class="connectors-custom-item-detail">
                      {{ uc.api_config?.base_url }}
                      <span v-if="uc.status === 'error'" class="connectors-status-error">{{ uc.error_message }}</span>
                    </div>
                  </div>
                </div>
                <div class="connectors-custom-item-actions">
                  <button class="connectors-icon-btn" :title="t('Test')" @click="handleTest(uc.id)">
                    <Zap :size="14" />
                  </button>
                  <button class="connectors-icon-btn connectors-icon-btn--danger" :title="t('Delete')" @click="handleDelete(uc.id)">
                    <Trash2 :size="14" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Custom MCP tab -->
          <div v-if="activeTab === 'custom-mcp'" class="connectors-custom">
            <div class="connectors-custom-form-section">
              <h3 class="connectors-section-title">{{ t('Add MCP Server') }}</h3>
              <CustomMcpForm @submit="handleCreateMcp" @cancel="activeTab = 'apps'" />
            </div>
            <div v-if="customMcpConnectors.length > 0" class="connectors-custom-list">
              <h3 class="connectors-section-title">{{ t('Your MCP Servers') }}</h3>
              <div v-for="uc in customMcpConnectors" :key="uc.id" class="connectors-custom-item">
                <div class="connectors-custom-item-info">
                  <Server :size="16" class="connectors-custom-item-icon" />
                  <div>
                    <div class="connectors-custom-item-name">{{ uc.name }}</div>
                    <div class="connectors-custom-item-detail">
                      {{ uc.mcp_config?.transport }}
                      <template v-if="uc.mcp_config?.command"> &middot; {{ uc.mcp_config.command }}</template>
                      <template v-if="uc.mcp_config?.url"> &middot; {{ uc.mcp_config.url }}</template>
                      <span v-if="uc.status === 'error'" class="connectors-status-error">{{ uc.error_message }}</span>
                    </div>
                  </div>
                </div>
                <div class="connectors-custom-item-actions">
                  <button class="connectors-icon-btn" :title="t('Test')" @click="handleTest(uc.id)">
                    <Zap :size="14" />
                  </button>
                  <button class="connectors-icon-btn connectors-icon-btn--danger" :title="t('Delete')" @click="handleDelete(uc.id)">
                    <Trash2 :size="14" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { Search, Globe, Server, Zap, Trash2 } from 'lucide-vue-next';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { useConnectorDialog } from '@/composables/useConnectorDialog';
import { useConnectors } from '@/composables/useConnectors';
import { showInfoToast, showErrorToast } from '@/utils/toast';
import ConnectorCard from './ConnectorCard.vue';
import CustomApiForm from './CustomApiForm.vue';
import CustomMcpForm from './CustomMcpForm.vue';
import AppSetupForm from './AppSetupForm.vue';
import type {
  CatalogConnector,
  CreateCustomApiRequest,
  CreateCustomMcpRequest,
  UserConnector,
} from '@/api/connectors';

const { t } = useI18n();
const { isConnectorDialogOpen, defaultTab } = useConnectorDialog();
const {
  catalogConnectors,
  userConnectors,
  customApiConnectors,
  customMcpConnectors,
  loadingCatalog,
  loadCatalog,
  loadUserConnectors,
  connectAppConnector,
  disconnectConnector,
  addCustomApi,
  addCustomMcp,
  removeConnector,
  testConnectorConnection,
} = useConnectors();

const tabs = [
  { id: 'apps' as const, label: 'Apps' },
  { id: 'custom-api' as const, label: 'Custom API' },
  { id: 'custom-mcp' as const, label: 'Custom MCP' },
];

const activeTab = ref<'apps' | 'custom-api' | 'custom-mcp'>('apps');
const searchQuery = ref('');
const mutatingId = ref<string | null>(null);
const setupConnector = ref<CatalogConnector | null>(null);
const setupFormRef = ref<InstanceType<typeof AppSetupForm> | null>(null);

const filteredCatalog = computed(() => {
  const query = searchQuery.value.toLowerCase().trim();
  if (!query) return catalogConnectors.value;
  return catalogConnectors.value.filter(
    (c) =>
      c.name.toLowerCase().includes(query) || c.description.toLowerCase().includes(query),
  );
});

function getUserConnectorFor(connectorId: string): UserConnector | null {
  return userConnectors.value.find((uc) => uc.connector_id === connectorId) ?? null;
}

// Lazy load on first open
let loaded = false;
watch(isConnectorDialogOpen, async (open) => {
  if (open) {
    activeTab.value = defaultTab.value;
    setupConnector.value = null;
    if (!loaded) {
      loaded = true;
      await Promise.all([loadCatalog(), loadUserConnectors()]);
    }
  }
});

function handleSetup(connector: CatalogConnector) {
  setupConnector.value = connector;
}

async function handleSetupSubmit(connectorId: string, credentials: Record<string, string>) {
  setupFormRef.value?.setSubmitting(true);
  setupFormRef.value?.setError(null);
  const result = await connectAppConnector(connectorId, credentials);
  setupFormRef.value?.setSubmitting(false);
  if (result) {
    if (result.status === 'error' && result.error_message) {
      setupFormRef.value?.setError(result.error_message);
    } else {
      setupConnector.value = null;
      showInfoToast(t('Connected'));
    }
  } else {
    setupFormRef.value?.setError('Failed to connect. Check your credentials and try again.');
  }
}

async function handleConnect(connectorId: string) {
  mutatingId.value = connectorId;
  const result = await connectAppConnector(connectorId);
  mutatingId.value = null;
  if (result) {
    showInfoToast(t('Connected'));
  }
}

async function handleDisconnect(userConnectorId: string) {
  const uc = userConnectors.value.find((c) => c.id === userConnectorId);
  if (uc?.connector_id) {
    mutatingId.value = uc.connector_id;
  }
  await disconnectConnector(userConnectorId);
  mutatingId.value = null;
}

async function handleCreateApi(data: CreateCustomApiRequest) {
  const result = await addCustomApi(data);
  if (result) {
    showInfoToast(t('API connector created'));
  } else {
    showErrorToast(t('Failed to create connector'));
  }
}

async function handleCreateMcp(data: CreateCustomMcpRequest) {
  const result = await addCustomMcp(data);
  if (result) {
    showInfoToast(t('MCP server added'));
  } else {
    showErrorToast(t('Failed to add MCP server'));
  }
}

async function handleDelete(id: string) {
  const success = await removeConnector(id);
  if (success) {
    showInfoToast(t('Connector removed'));
  }
}

async function handleTest(id: string) {
  const result = await testConnectorConnection(id);
  if (result) {
    if (result.ok) {
      const latency = result.latency_ms ? ` (${Math.round(result.latency_ms)}ms)` : '';
      showInfoToast(`${result.message}${latency}`);
    } else {
      showErrorToast(result.message);
    }
  }
}
</script>

<style scoped>
.connectors-dialog {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.connectors-header {
  padding: 20px 24px 0;
}

.connectors-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.connectors-tabs-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding: 12px 24px 0;
  border-bottom: 1px solid var(--border-main);
}

.connectors-search {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  background: var(--background-white-main);
  width: 220px;
}

.connectors-search-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.connectors-search-input {
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  color: var(--text-primary);
  width: 100%;
}

.connectors-search-input::placeholder {
  color: var(--text-disable);
}

.connectors-tabs {
  display: flex;
  gap: 0;
}

.connectors-tab {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-tertiary);
  border: none;
  background: transparent;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: all 0.15s;
}

.connectors-tab:hover {
  color: var(--text-primary);
}

.connectors-tab--active {
  color: var(--text-primary);
  border-bottom-color: var(--text-primary);
}

.connectors-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px 24px;
}

.connectors-apps {
  display: flex;
  flex-direction: column;
}

.connectors-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

@media (max-width: 640px) {
  .connectors-grid {
    grid-template-columns: 1fr;
  }
}

.connectors-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 0;
  color: var(--text-tertiary);
  font-size: 14px;
}

.connectors-spinner {
  width: 20px;
  height: 20px;
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

.connectors-empty {
  text-align: center;
  padding: 40px 0;
  color: var(--text-tertiary);
  font-size: 14px;
}

.connectors-custom {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.connectors-custom-form-section {
  padding: 16px;
  border-radius: 12px;
  border: 1px solid var(--border-main);
  background: var(--background-white-main);
}

.connectors-section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px;
}

.connectors-custom-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.connectors-custom-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid var(--border-main);
  background: var(--background-white-main);
}

.connectors-custom-item-info {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.connectors-custom-item-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.connectors-custom-item-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.connectors-custom-item-detail {
  font-size: 12px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.connectors-status-error {
  color: #ef4444;
  margin-left: 6px;
}

.connectors-custom-item-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.connectors-icon-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid var(--border-main);
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: all 0.15s;
}

.connectors-icon-btn:hover {
  border-color: var(--border-dark);
  color: var(--text-primary);
  background: var(--fill-tsp-gray-main);
}

.connectors-icon-btn--danger:hover {
  background: #fee2e2;
  color: #ef4444;
  border-color: #fecaca;
}
</style>
