export interface CursorMotionConfig {
  baseSmoothing: number
  minSmoothing: number
  maxSmoothing: number
  distanceBoost: number
  maxSpeedPxPerSec: number
  settleThresholdPx: number
  jitterThresholdPx: number
}

export interface CursorStepResult {
  x: number
  y: number
  settled: boolean
}

export function adaptiveSmoothing(distance: number, config: CursorMotionConfig): number {
  const raw = config.baseSmoothing + distance * config.distanceBoost
  if (raw < config.minSmoothing) return config.minSmoothing
  if (raw > config.maxSmoothing) return config.maxSmoothing
  return raw
}

export function isJitterMove(
  currentX: number,
  currentY: number,
  targetX: number,
  targetY: number,
  config: CursorMotionConfig,
): boolean {
  const dx = targetX - currentX
  const dy = targetY - currentY
  const distance = Math.hypot(dx, dy)
  return distance < config.jitterThresholdPx
}

export function stepTowards(
  currentX: number,
  currentY: number,
  targetX: number,
  targetY: number,
  dtSeconds: number,
  config: CursorMotionConfig,
  reducedMotion: boolean,
): CursorStepResult {
  if (reducedMotion) {
    return { x: targetX, y: targetY, settled: true }
  }

  const dx = targetX - currentX
  const dy = targetY - currentY
  const distance = Math.hypot(dx, dy)

  if (distance <= config.settleThresholdPx) {
    return { x: targetX, y: targetY, settled: true }
  }

  const smoothing = adaptiveSmoothing(distance, config)
  const alpha = 1 - Math.exp(-smoothing * dtSeconds)

  let nextX = currentX + dx * alpha
  let nextY = currentY + dy * alpha

  const movedX = nextX - currentX
  const movedY = nextY - currentY
  const movedDistance = Math.hypot(movedX, movedY)
  const maxStepDistance = config.maxSpeedPxPerSec * dtSeconds

  if (movedDistance > maxStepDistance && movedDistance > 0) {
    const ratio = maxStepDistance / movedDistance
    nextX = currentX + movedX * ratio
    nextY = currentY + movedY * ratio
  }

  const remaining = Math.hypot(targetX - nextX, targetY - nextY)
  return { x: nextX, y: nextY, settled: remaining <= config.settleThresholdPx }
}
