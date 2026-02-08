import { ref } from 'vue';

export type ConnectorTab = 'apps' | 'custom-api' | 'custom-mcp';

const isConnectorDialogOpen = ref(false);
const defaultTab = ref<ConnectorTab>('apps');

export function useConnectorDialog() {
  function openConnectorDialog(tab?: ConnectorTab) {
    if (tab) {
      defaultTab.value = tab;
    }
    isConnectorDialogOpen.value = true;
  }

  function closeConnectorDialog() {
    isConnectorDialogOpen.value = false;
  }

  return {
    isConnectorDialogOpen,
    defaultTab,
    openConnectorDialog,
    closeConnectorDialog,
  };
}
