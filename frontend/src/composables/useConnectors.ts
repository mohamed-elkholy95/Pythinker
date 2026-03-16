import { ref, computed, readonly } from 'vue';
import {
  getCatalogConnectors,
  getUserConnectors,
  connectApp,
  createCustomApi,
  createCustomMcp,
  updateUserConnector,
  deleteUserConnector,
  testConnection,
  type CatalogConnector,
  type UserConnector,
  type CreateCustomApiRequest,
  type CreateCustomMcpRequest,
  type UpdateUserConnectorRequest,
  type TestConnectionResponse,
} from '@/api/connectors';

// Global state
const catalogConnectors = ref<CatalogConnector[]>([]);
const userConnectors = ref<UserConnector[]>([]);
const loadingCatalog = ref(false);
const loadingUser = ref(false);
const loadingMutation = ref(false);
const error = ref<string | null>(null);

const BANNER_DISMISSED_KEY = 'pythinker:connector-banner-dismissed';

export function useConnectors() {
  const connectedCount = computed(() =>
    userConnectors.value.filter((uc) => uc.status === 'connected' && uc.enabled).length,
  );

  const connectedConnectors = computed(() =>
    userConnectors.value.filter((uc) => uc.status === 'connected' && uc.enabled),
  );

  const customApiConnectors = computed(() =>
    userConnectors.value.filter((uc) => uc.connector_type === 'custom_api'),
  );

  const customMcpConnectors = computed(() =>
    userConnectors.value.filter((uc) => uc.connector_type === 'custom_mcp'),
  );

  const loading = computed(
    () => loadingCatalog.value || loadingUser.value || loadingMutation.value,
  );

  const bannerDismissed = ref(localStorage.getItem(BANNER_DISMISSED_KEY) === 'true');

  function dismissBanner() {
    bannerDismissed.value = true;
    localStorage.setItem(BANNER_DISMISSED_KEY, 'true');
  }

  async function loadCatalog(type?: string, search?: string): Promise<void> {
    try {
      loadingCatalog.value = true;
      error.value = null;
      catalogConnectors.value = await getCatalogConnectors(type, search);
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load connectors';
      console.error('Failed to load catalog connectors:', err);
    } finally {
      loadingCatalog.value = false;
    }
  }

  async function loadUserConnectors(): Promise<void> {
    try {
      loadingUser.value = true;
      error.value = null;
      const result = await getUserConnectors();
      userConnectors.value = result.connectors;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load user connectors';
      console.error('Failed to load user connectors:', err);
    } finally {
      loadingUser.value = false;
    }
  }

  async function connectAppConnector(connectorId: string): Promise<UserConnector | null> {
    try {
      loadingMutation.value = true;
      error.value = null;
      const uc = await connectApp(connectorId);
      // Update local state
      const idx = userConnectors.value.findIndex((c) => c.connector_id === connectorId);
      if (idx >= 0) {
        userConnectors.value[idx] = uc;
      } else {
        userConnectors.value.push(uc);
      }
      return uc;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to connect';
      console.error('Failed to connect app connector:', err);
      return null;
    } finally {
      loadingMutation.value = false;
    }
  }

  async function disconnectConnector(userConnectorId: string): Promise<boolean> {
    try {
      loadingMutation.value = true;
      error.value = null;
      await deleteUserConnector(userConnectorId);
      userConnectors.value = userConnectors.value.filter((c) => c.id !== userConnectorId);
      return true;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to disconnect';
      console.error('Failed to disconnect connector:', err);
      return false;
    } finally {
      loadingMutation.value = false;
    }
  }

  async function addCustomApi(data: CreateCustomApiRequest): Promise<UserConnector | null> {
    try {
      loadingMutation.value = true;
      error.value = null;
      const uc = await createCustomApi(data);
      userConnectors.value.push(uc);
      return uc;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to create API connector';
      console.error('Failed to create custom API connector:', err);
      return null;
    } finally {
      loadingMutation.value = false;
    }
  }

  async function addCustomMcp(data: CreateCustomMcpRequest): Promise<UserConnector | null> {
    try {
      loadingMutation.value = true;
      error.value = null;
      const uc = await createCustomMcp(data);
      userConnectors.value.push(uc);
      return uc;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to create MCP connector';
      console.error('Failed to create custom MCP connector:', err);
      return null;
    } finally {
      loadingMutation.value = false;
    }
  }

  async function updateConnector(
    id: string,
    data: UpdateUserConnectorRequest,
  ): Promise<UserConnector | null> {
    try {
      loadingMutation.value = true;
      error.value = null;
      const uc = await updateUserConnector(id, data);
      const idx = userConnectors.value.findIndex((c) => c.id === id);
      if (idx >= 0) {
        userConnectors.value[idx] = uc;
      }
      return uc;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to update connector';
      console.error('Failed to update connector:', err);
      return null;
    } finally {
      loadingMutation.value = false;
    }
  }

  async function removeConnector(id: string): Promise<boolean> {
    try {
      loadingMutation.value = true;
      error.value = null;
      await deleteUserConnector(id);
      userConnectors.value = userConnectors.value.filter((c) => c.id !== id);
      return true;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to delete connector';
      console.error('Failed to delete connector:', err);
      return false;
    } finally {
      loadingMutation.value = false;
    }
  }

  async function testConnectorConnection(id: string): Promise<TestConnectionResponse | null> {
    try {
      loadingMutation.value = true;
      error.value = null;
      const result = await testConnection(id);
      // Refresh user connectors to get updated status
      await loadUserConnectors();
      return result;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Connection test failed';
      console.error('Failed to test connection:', err);
      return null;
    } finally {
      loadingMutation.value = false;
    }
  }

  return {
    catalogConnectors: readonly(catalogConnectors),
    userConnectors: readonly(userConnectors),
    connectedCount,
    connectedConnectors,
    customApiConnectors,
    customMcpConnectors,
    loading,
    loadingCatalog,
    loadingUser,
    loadingMutation,
    error,
    bannerDismissed,
    dismissBanner,
    loadCatalog,
    loadUserConnectors,
    connectAppConnector,
    disconnectConnector,
    addCustomApi,
    addCustomMcp,
    updateConnector,
    removeConnector,
    testConnectorConnection,
  };
}
