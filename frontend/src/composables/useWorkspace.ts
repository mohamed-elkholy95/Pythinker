/**
 * Workspace composable for managing workspace state and operations
 */

import { ref, Ref } from 'vue';
import {
  getWorkspaceTemplates,
  getWorkspaceTemplate,
  getSessionWorkspace,
  WorkspaceTemplate,
  SessionWorkspaceResponse
} from '../api/agent';

interface UseWorkspaceReturn {
  // State
  templates: Ref<WorkspaceTemplate[]>;
  currentWorkspace: Ref<SessionWorkspaceResponse | null>;
  loading: Ref<boolean>;
  error: Ref<string | null>;

  // Actions
  loadTemplates: () => Promise<void>;
  loadTemplate: (name: string) => Promise<WorkspaceTemplate | null>;
  loadSessionWorkspace: (sessionId: string) => Promise<void>;
  clearWorkspace: () => void;
  getFolderPath: (sessionId: string, folderName: string) => string;
  isWorkspaceInitialized: () => boolean;
}

/**
 * Composable for workspace management
 */
export function useWorkspace(): UseWorkspaceReturn {
  const templates = ref<WorkspaceTemplate[]>([]);
  const currentWorkspace = ref<SessionWorkspaceResponse | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  /**
   * Load all available workspace templates
   */
  const loadTemplates = async (): Promise<void> => {
    loading.value = true;
    error.value = null;

    try {
      const response = await getWorkspaceTemplates();
      templates.value = response.templates;
    } catch (err: unknown) {
      console.error('Failed to load templates:', err);
      error.value = err instanceof Error ? err.message : 'Failed to load workspace templates';
      throw err;
    } finally {
      loading.value = false;
    }
  };

  /**
   * Load a specific template by name
   */
  const loadTemplate = async (name: string): Promise<WorkspaceTemplate | null> => {
    loading.value = true;
    error.value = null;

    try {
      const template = await getWorkspaceTemplate(name);
      return template;
    } catch (err: unknown) {
      console.error(`Failed to load template '${name}':`, err);
      error.value = err instanceof Error ? err.message : `Failed to load template '${name}'`;
      return null;
    } finally {
      loading.value = false;
    }
  };

  /**
   * Load workspace structure for a session
   */
  const loadSessionWorkspace = async (sessionId: string): Promise<void> => {
    if (!sessionId) {
      currentWorkspace.value = null;
      return;
    }

    loading.value = true;
    error.value = null;

    try {
      const workspace = await getSessionWorkspace(sessionId);
      currentWorkspace.value = workspace;
    } catch (err: unknown) {
      console.error('Failed to load session workspace:', err);
      error.value = err instanceof Error ? err.message : 'Failed to load session workspace';
      currentWorkspace.value = null;
      throw err;
    } finally {
      loading.value = false;
    }
  };

  /**
   * Clear current workspace state
   */
  const clearWorkspace = (): void => {
    currentWorkspace.value = null;
    error.value = null;
  };

  /**
   * Get full path for a workspace folder
   */
  const getFolderPath = (sessionId: string, folderName: string): string => {
    if (currentWorkspace.value?.workspace_root) {
      return `${currentWorkspace.value.workspace_root}/${folderName}`;
    }
    return `/workspace/${sessionId}/${folderName}`;
  };

  /**
   * Check if workspace is initialized for current session
   */
  const isWorkspaceInitialized = (): boolean => {
    return !!(currentWorkspace.value?.workspace_structure);
  };

  return {
    // State
    templates,
    currentWorkspace,
    loading,
    error,

    // Actions
    loadTemplates,
    loadTemplate,
    loadSessionWorkspace,
    clearWorkspace,
    getFolderPath,
    isWorkspaceInitialized,
  };
}
