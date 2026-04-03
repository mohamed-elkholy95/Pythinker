export function normalizeHeaderModelName(modelName: string | null | undefined): string {
  return modelName?.trim() || ''
}

export function resolveInitialHeaderModelName(
  liveServerModelName: string | null | undefined,
  savedSettingsModelName: string | null | undefined,
): string {
  return normalizeHeaderModelName(liveServerModelName) || normalizeHeaderModelName(savedSettingsModelName)
}

export function resolveNextHeaderModelName(
  currentModelName: string,
  incomingModelName: string | null | undefined,
): string {
  const normalizedIncomingModelName = normalizeHeaderModelName(incomingModelName)
  return normalizedIncomingModelName || currentModelName
}
