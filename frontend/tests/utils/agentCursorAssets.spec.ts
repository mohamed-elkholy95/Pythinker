import { describe, expect, it } from 'vitest'

import type { AgentActionType } from '@/types/liveViewer'
import {
  getAllAppleCursorAssetUrls,
  getCursorAssetForAction,
  getWaitCursorFrameUrl,
} from '@/utils/agentCursorAssets'

describe('agentCursorAssets', () => {
  it('loads full apple cursor asset bundle into manifest', () => {
    const urls = getAllAppleCursorAssetUrls()
    expect(urls.length).toBeGreaterThan(40)
  })

  it('returns an asset url for each supported action type', () => {
    const actionTypes: AgentActionType[] = [
      'click',
      'type',
      'scroll',
      'navigate',
      'move',
      'press_key',
      'select',
      'extract',
      'wait',
    ]

    for (const actionType of actionTypes) {
      expect(getCursorAssetForAction(actionType)).toMatch(/^\/|^data:|^https?:/)
    }
  })

  it('cycles wait cursor frames safely by index', () => {
    const frameA = getWaitCursorFrameUrl(0)
    const frameB = getWaitCursorFrameUrl(1)

    expect(frameA).toMatch(/^\/|^data:|^https?:/)
    expect(frameB).toMatch(/^\/|^data:|^https?:/)
    expect(frameA).not.toBe('')
    expect(frameB).not.toBe('')
  })
})
