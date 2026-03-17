import type { AgentActionType } from '@/types/liveViewer'

type GlobbedModule = Record<string, string>

const APPLE_CURSOR_GLOB = import.meta.glob(
  '../assets/cursors/apple_cursor-main/svg/**/*.svg',
  {
    eager: true,
    import: 'default',
  },
) as GlobbedModule

const ALL_ASSET_PATHS = Object.keys(APPLE_CURSOR_GLOB).sort()
const ALL_ASSET_URLS = ALL_ASSET_PATHS.map(path => APPLE_CURSOR_GLOB[path])

function findAssetUrlByBasename(basename: string): string | null {
  const hit = ALL_ASSET_PATHS.find(path => path.endsWith(`/${basename}`))
  return hit ? APPLE_CURSOR_GLOB[hit] : null
}

const DEFAULT_CURSOR_URL = findAssetUrlByBasename('left_ptr.svg') ?? ALL_ASSET_URLS[0] ?? ''

const ACTION_BASENAME_MAP: Record<AgentActionType, string> = {
  click: 'left_ptr.svg',
  type: 'xterm.svg',
  scroll: 'all-scroll.svg',
  navigate: 'link.svg',
  move: 'left_ptr.svg',
  press_key: 'left_ptr.svg',
  select: 'context-menu.svg',
  extract: 'crosshair.svg',
  wait: 'left_ptr.svg',
}

const WAIT_FRAME_PATHS = ALL_ASSET_PATHS
  .filter(path => path.includes('/left_ptr_watch/'))
  .sort()
const WAIT_FRAME_URLS = WAIT_FRAME_PATHS.map(path => APPLE_CURSOR_GLOB[path])

export function getAllAppleCursorAssetUrls(): string[] {
  return ALL_ASSET_URLS
}

export function getCursorAssetForAction(actionType: AgentActionType): string {
  const basename = ACTION_BASENAME_MAP[actionType]
  const resolved = findAssetUrlByBasename(basename)
  return resolved ?? DEFAULT_CURSOR_URL
}

export function getWaitCursorFrameUrl(frameIndex: number): string {
  if (WAIT_FRAME_URLS.length === 0) return DEFAULT_CURSOR_URL
  const safeIndex = Math.abs(frameIndex) % WAIT_FRAME_URLS.length
  return WAIT_FRAME_URLS[safeIndex]
}
