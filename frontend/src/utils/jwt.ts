/**
 * JWT utility — shared token parsing helpers.
 *
 * Used by both the API client (proactive token refresh) and the auth store
 * (schedule refresh timer) to avoid duplicating the same JWT decode logic.
 */

/**
 * Parse JWT expiry. Returns seconds remaining until expiry, or 0 if expired/invalid.
 *
 * Only reads the payload segment (base64url-encoded) — does NOT verify the signature.
 */
export function tokenExpiresIn(token: string): number {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return 0
    // base64url -> base64 -> decode
    const payload = parts[1]!.replace(/-/g, '+').replace(/_/g, '/')
    const decoded = JSON.parse(atob(payload)) as { exp?: number }
    if (typeof decoded.exp !== 'number') return 0
    return Math.max(0, decoded.exp - Math.floor(Date.now() / 1000))
  } catch {
    return 0
  }
}
