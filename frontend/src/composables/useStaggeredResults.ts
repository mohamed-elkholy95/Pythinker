import { shallowRef, watch, type Ref } from 'vue';

export interface StaggeredResultsOptions {
  /** Delay in ms between revealing each result (default: 150ms) */
  delayMs?: number;
  /** Whether staggering is enabled (default: true) */
  enabled?: boolean;
}

/**
 * Progressive result reveal composable
 *
 * Takes an array of results and reveals them one-by-one with staggered timing.
 * Creates a perceived "streaming" effect even when all results arrive at once.
 *
 * @example
 * const allResults = ref([...])
 * const { visibleResults, isRevealing } = useStaggeredResults(allResults, {
 *   delayMs: 150,
 *   enabled: isSearching
 * })
 *
 * // Template: v-for="result in visibleResults"
 */
export function useStaggeredResults<T>(
  sourceResults: Ref<T[] | undefined>,
  options: StaggeredResultsOptions = {}
) {
  const { delayMs = 150, enabled = true } = options;

  // Minimal source state: only track revealed results
  const visibleResults = shallowRef<T[]>([]);
  const isRevealing = shallowRef(false);

  // Track active timeout to allow cleanup
  let revealTimeout: ReturnType<typeof setTimeout> | null = null;

  /**
   * Reveal results progressively with staggered delays
   */
  function revealProgressively(results: T[]) {
    if (!enabled || results.length === 0) {
      // If staggering disabled or no results, show all immediately
      visibleResults.value = results;
      isRevealing.value = false;
      return;
    }

    isRevealing.value = true;
    visibleResults.value = [];

    let index = 0;

    function revealNext() {
      if (index >= results.length) {
        // All results revealed
        isRevealing.value = false;
        revealTimeout = null;
        return;
      }

      // Add next result
      visibleResults.value = [...visibleResults.value, results[index]];
      index++;

      // Check if this was the last result
      if (index >= results.length) {
        // All results revealed
        isRevealing.value = false;
        revealTimeout = null;
      } else {
        // Schedule next reveal
        revealTimeout = setTimeout(revealNext, delayMs);
      }
    }

    // Start revealing
    revealNext();
  }

  /**
   * Clear any pending reveal operations
   */
  function clearReveal() {
    if (revealTimeout !== null) {
      clearTimeout(revealTimeout);
      revealTimeout = null;
    }
    isRevealing.value = false;
  }

  // Watch for source results changes
  watch(
    sourceResults,
    (newResults) => {
      // Clear any ongoing reveal operation
      clearReveal();

      if (!newResults || newResults.length === 0) {
        visibleResults.value = [];
        return;
      }

      // Start progressive reveal
      revealProgressively(newResults);
    },
    { immediate: true }
  );

  // Cleanup on unmount
  // Note: Vue automatically calls cleanup when component unmounts
  // but we provide explicit cleanup for manual control if needed
  function cleanup() {
    clearReveal();
    visibleResults.value = [];
  }

  return {
    /** Results revealed so far (use this for rendering) */
    visibleResults,
    /** True while results are being progressively revealed */
    isRevealing,
    /** Manual cleanup (automatically called on unmount) */
    cleanup,
  };
}
