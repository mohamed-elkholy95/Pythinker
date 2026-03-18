import { describe, expect, it } from 'vitest'

import {
  CHAT_DOCK_CLEARANCE_PX,
  DEFAULT_CHAT_MESSAGES_PADDING_PX,
  resolveChatDockLayout,
} from '@/utils/chatDockLayout'

describe('chatDockLayout', () => {
  it('keeps the legacy message padding when the composer is not pinned', () => {
    expect(resolveChatDockLayout({ isPinned: false, dockHeight: 240 })).toEqual({
      contentPaddingBottomPx: 0,
      messagesPaddingBottomPx: DEFAULT_CHAT_MESSAGES_PADDING_PX,
    })
  })

  it('uses the measured dock height when the pinned composer stack is taller than the fallback', () => {
    expect(resolveChatDockLayout({ isPinned: true, dockHeight: 264 })).toEqual({
      contentPaddingBottomPx: 8,
      messagesPaddingBottomPx: 264 + CHAT_DOCK_CLEARANCE_PX,
    })
  })

  it('never shrinks below the default safe padding when the dock height is missing', () => {
    expect(resolveChatDockLayout({ isPinned: true, dockHeight: 0 })).toEqual({
      contentPaddingBottomPx: 8,
      messagesPaddingBottomPx: DEFAULT_CHAT_MESSAGES_PADDING_PX,
    })
  })
})
