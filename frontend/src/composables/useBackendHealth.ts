import { ref, onUnmounted } from 'vue';
import { apiClient } from '@/api/client';

interface HealthStatus {
  isHealthy: boolean;
  isChecking: boolean;
  lastCheck: Date | null;
  error: string | null;
}

/**
 * Composable for monitoring backend health and connectivity
 *
 * Usage:
 * ```typescript
 * const { isHealthy, checkHealth, startMonitoring, stopMonitoring } = useBackendHealth();
 *
 * // Manual check
 * await checkHealth();
 *
 * // Automatic monitoring (every 30s)
 * startMonitoring();
 * ```
 */
export function useBackendHealth() {
  const status = ref<HealthStatus>({
    isHealthy: false,
    isChecking: false,
    lastCheck: null,
    error: null,
  });

  let monitoringInterval: NodeJS.Timeout | null = null;

  /**
   * Perform a single health check
   */
  const checkHealth = async (): Promise<boolean> => {
    if (status.value.isChecking) {
      return status.value.isHealthy;
    }

    status.value.isChecking = true;
    status.value.error = null;

    try {
      const response = await apiClient.get('/health', {
        timeout: 5000, // 5 second timeout
      });

      const isHealthy = response.status === 200 && response.data?.status === 'healthy';

      status.value.isHealthy = isHealthy;
      status.value.lastCheck = new Date();

      return isHealthy;
    } catch (error: any) {
      status.value.isHealthy = false;
      status.value.error = error.message || 'Backend is unreachable';
      status.value.lastCheck = new Date();

      console.warn('Backend health check failed:', error);
      return false;
    } finally {
      status.value.isChecking = false;
    }
  };

  /**
   * Start periodic health monitoring (every 30 seconds)
   */
  const startMonitoring = (intervalMs: number = 30000) => {
    if (monitoringInterval) {
      return; // Already monitoring
    }

    // Initial check
    checkHealth();

    // Set up periodic checks
    monitoringInterval = setInterval(() => {
      checkHealth();
    }, intervalMs);
  };

  /**
   * Stop periodic health monitoring
   */
  const stopMonitoring = () => {
    if (monitoringInterval) {
      clearInterval(monitoringInterval);
      monitoringInterval = null;
    }
  };

  /**
   * Wait for backend to become healthy (useful during startup)
   */
  const waitForHealthy = async (
    maxAttempts: number = 10,
    delayMs: number = 2000
  ): Promise<boolean> => {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const isHealthy = await checkHealth();
      if (isHealthy) {
        return true;
      }

      if (attempt < maxAttempts - 1) {
        await new Promise(resolve => setTimeout(resolve, delayMs));
      }
    }

    return false;
  };

  // Cleanup on unmount
  onUnmounted(() => {
    stopMonitoring();
  });

  return {
    status,
    isHealthy: () => status.value.isHealthy,
    isChecking: () => status.value.isChecking,
    lastCheck: () => status.value.lastCheck,
    error: () => status.value.error,
    checkHealth,
    startMonitoring,
    stopMonitoring,
    waitForHealthy,
  };
}
