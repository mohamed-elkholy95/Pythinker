/**
 * Animation Registry
 *
 * Provides type-safe lazy loading of Lottie animations
 */

/**
 * Available animation keys
 */
export type AnimationKey =
  // Loading animations
  | 'loading-spinner'
  | 'loading-dots'
  | 'loading-thinking'
  // Status animations
  | 'status-success'
  | 'status-error'
  | 'status-warning'
  // Tool animations
  | 'tool-browser'
  | 'tool-terminal'
  | 'tool-file'
  | 'tool-search'
  | 'tool-code'
  // Agent animations
  | 'agent-thinking'
  | 'agent-working'
  | 'agent-complete'
  // Empty state animations
  | 'empty-no-results'
  | 'empty-welcome'

/**
 * Animation category type
 */
export type AnimationCategory = 'loading' | 'status' | 'tools' | 'agent' | 'empty'

/**
 * Get category from animation key
 */
export function getAnimationCategory(key: AnimationKey): AnimationCategory {
  const prefix = key.split('-')[0]
  switch (prefix) {
    case 'loading':
      return 'loading'
    case 'status':
      return 'status'
    case 'tool':
      return 'tools'
    case 'agent':
      return 'agent'
    case 'empty':
      return 'empty'
    default:
      return 'loading'
  }
}

/**
 * Animation cache to prevent duplicate loads
 */
const animationCache = new Map<AnimationKey, object>()

/**
 * Animation loader map
 *
 * Each animation is lazily imported to reduce bundle size
 * Animations are loaded on-demand when first requested
 */
const animationLoaders: Record<AnimationKey, () => Promise<{ default: object }>> = {
  // Loading animations
  'loading-spinner': () => import('./loading/spinner.json'),
  'loading-dots': () => import('./loading/dots.json'),
  'loading-thinking': () => import('./loading/thinking.json'),

  // Status animations
  'status-success': () => import('./status/success.json'),
  'status-error': () => import('./status/error.json'),
  'status-warning': () => import('./status/warning.json'),

  // Tool animations
  'tool-browser': () => import('./tools/browser.json'),
  'tool-terminal': () => import('./tools/terminal.json'),
  'tool-file': () => import('./tools/file.json'),
  'tool-search': () => import('./tools/search.json'),
  'tool-code': () => import('./tools/code.json'),

  // Agent animations
  'agent-thinking': () => import('./agent/thinking.json'),
  'agent-working': () => import('./agent/working.json'),
  'agent-complete': () => import('./agent/complete.json'),

  // Empty state animations
  'empty-no-results': () => import('./empty/no-results.json'),
  'empty-welcome': () => import('./empty/welcome.json'),
}

/**
 * Load an animation by key
 *
 * Returns cached animation if already loaded
 */
export async function loadAnimation(key: AnimationKey): Promise<object> {
  // Check cache first
  const cached = animationCache.get(key)
  if (cached) {
    return cached
  }

  // Load animation
  const loader = animationLoaders[key]
  if (!loader) {
    throw new Error(`Unknown animation key: ${key}`)
  }

  try {
    const module = await loader()
    const data = module.default
    animationCache.set(key, data)
    return data
  } catch (error) {
    console.error(`Failed to load animation: ${key}`, error)
    throw error
  }
}

/**
 * Preload animations (call early for critical animations)
 */
export async function preloadAnimations(keys: AnimationKey[]): Promise<void> {
  await Promise.all(keys.map((key) => loadAnimation(key)))
}

/**
 * Preload critical animations (spinner, success, error)
 */
export async function preloadCriticalAnimations(): Promise<void> {
  await preloadAnimations(['loading-spinner', 'status-success', 'status-error'])
}

/**
 * Clear animation cache
 */
export function clearAnimationCache(): void {
  animationCache.clear()
}

/**
 * Check if animation is cached
 */
export function isAnimationCached(key: AnimationKey): boolean {
  return animationCache.has(key)
}

/**
 * Get all available animation keys
 */
export function getAvailableAnimations(): AnimationKey[] {
  return Object.keys(animationLoaders) as AnimationKey[]
}

/**
 * Map existing CSS animation types to Lottie animation keys
 * Used for migration from CSS-based animations
 */
export const ANIMATION_TYPE_MAP: Record<string, AnimationKey> = {
  spinner: 'loading-spinner',
  globe: 'tool-browser',
  search: 'tool-search',
  file: 'tool-file',
  terminal: 'tool-terminal',
  code: 'tool-code',
  check: 'status-success',
}

/**
 * Get Lottie animation key from legacy animation type
 */
export function getLottieKey(legacyType: string): AnimationKey | null {
  return ANIMATION_TYPE_MAP[legacyType] || null
}
