export function normalizeHeaderModelName(modelName: string | null | undefined): string {
  return modelName?.trim() || ''
}

/**
 * Resolve the model name for header display.
 * Prefers model_display_name (custom branding) over the raw model ID.
 */
export function resolveInitialHeaderModelName(
  liveServerModelName: string | null | undefined,
  savedSettingsModelName: string | null | undefined,
  displayName?: string | null | undefined,
): string {
  const custom = normalizeHeaderModelName(displayName)
  if (custom) return custom
  return normalizeHeaderModelName(liveServerModelName) || normalizeHeaderModelName(savedSettingsModelName)
}

export function resolveNextHeaderModelName(
  currentModelName: string,
  incomingModelName: string | null | undefined,
): string {
  const normalizedIncomingModelName = normalizeHeaderModelName(incomingModelName)
  return normalizedIncomingModelName || currentModelName
}
