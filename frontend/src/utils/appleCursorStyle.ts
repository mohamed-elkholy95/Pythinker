/**
 * macOS-style pointer for CSS `cursor` (takeover + live stream hover).
 * Hotspot matches the 24px `left_ptr.svg` artwork used in the cursor bundle.
 */
import { getCursorAssetForAction } from '@/utils/agentCursorAssets'

const HOTSPOT_X = 8
const HOTSPOT_Y = 5

let _cachedCss: string | null = null

/** CSS `cursor` value, e.g. url(...) 8 5, auto */
export function getApplePointerCursorCss(): string {
  if (_cachedCss !== null) return _cachedCss
  const url = getCursorAssetForAction('move')
  if (!url) {
    _cachedCss = 'auto'
    return _cachedCss
  }
  const safe = url.replace(/\\/g, '\\\\').replace(/'/g, "\\'")
  _cachedCss = `url('${safe}') ${HOTSPOT_X} ${HOTSPOT_Y}, auto`
  return _cachedCss
}
