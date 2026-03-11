import type { ToolContent } from '@/types/message'
import type { ScreenshotMetadata } from '@/types/screenshot'
import { toEpochSeconds } from '@/utils/time'

/**
 * Find the best replay frame for a tool event using tool_call_id first and
 * timestamp proximity as a fallback.
 */
export const findReplayFrameIndexForTool = (
  tool: Pick<ToolContent, 'tool_call_id' | 'timestamp'>,
  screenshots: ScreenshotMetadata[],
): number => {
  if (screenshots.length === 0) return -1

  const toolId = tool.tool_call_id
  const isSynthetic = toolId.startsWith('tool-progress:')
  const parentToolId = isSynthetic
    ? toolId.split(':').slice(1, -1).join(':')
    : toolId
  const toolEpoch = toEpochSeconds(tool.timestamp as number | string)

  let bestIdx = -1

  if (isSynthetic && toolEpoch !== null) {
    let bestDiff = Infinity
    for (let i = 0; i < screenshots.length; i += 1) {
      if (screenshots[i].tool_call_id !== parentToolId) continue
      const screenshotEpoch = toEpochSeconds(screenshots[i].timestamp as number | string)
      if (screenshotEpoch === null) continue
      const diff = Math.abs(screenshotEpoch - toolEpoch)
      if (diff < bestDiff) {
        bestDiff = diff
        bestIdx = i
      }
    }
  } else {
    for (let i = screenshots.length - 1; i >= 0; i -= 1) {
      if (screenshots[i].tool_call_id === toolId) {
        bestIdx = i
        if (screenshots[i].trigger === 'tool_after') break
      }
    }
  }

  if (bestIdx >= 0 || toolEpoch === null) return bestIdx

  let bestDiff = Infinity
  for (let i = 0; i < screenshots.length; i += 1) {
    const screenshotEpoch = toEpochSeconds(screenshots[i].timestamp as number | string)
    if (screenshotEpoch === null) continue
    const diff = Math.abs(screenshotEpoch - toolEpoch)
    if (diff < bestDiff) {
      bestDiff = diff
      bestIdx = i
    }
  }

  return bestIdx
}
