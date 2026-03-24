import { reactive } from 'vue';
import {
  getFaviconUrl,
  markFaviconFailed,
  isFaviconFailed,
  getIconLetterFromUrl,
} from '@/utils/toolDisplay';

/**
 * Composable for managing favicon loading with persistent failure caching.
 *
 * Provides per-component reactive error tracking while leveraging the shared
 * localStorage-backed failure cache in toolDisplay.ts. When a favicon fails,
 * it's marked globally so no other component (or future session) attempts it.
 *
 * Usage:
 * ```vue
 * const { getUrl, handleError, isError, getLetter } = useFavicon()
 *
 * <img v-if="!isError(link)" :src="getUrl(link)" @error="handleError(link)" />
 * <span v-else>{{ getLetter(link, title) }}</span>
 * ```
 */
export function useFavicon() {
  /** Per-component reactive tracking of URLs that errored in this render. */
  const errors: Record<string, boolean> = reactive({});

  /**
   * Get the DuckDuckGo favicon URL for a link.
   * Returns empty string if the hostname is known-bad or pre-filtered.
   */
  function getUrl(url: string): string {
    return getFaviconUrl(url) ?? '';
  }

  /**
   * Check if a favicon should NOT be rendered (known failure or pre-filtered).
   * Combines the persistent global cache with per-component reactive state.
   */
  function isError(url: string): boolean {
    return !!errors[url] || isFaviconFailed(url);
  }

  /**
   * Handle an <img> error event — marks the hostname as failed globally
   * (persisted to localStorage) and updates local reactive state so
   * the component switches to the letter fallback immediately.
   */
  function handleError(url: string): void {
    errors[url] = true;
    markFaviconFailed(url);
  }

  /**
   * Get the single-letter fallback for a URL.
   * Maps well-known domains (GitHub→G, Reddit→R, etc.) or returns first char.
   */
  function getLetter(url: string, title?: string): string {
    return getIconLetterFromUrl(url, title);
  }

  return { getUrl, isError, handleError, getLetter, errors };
}
