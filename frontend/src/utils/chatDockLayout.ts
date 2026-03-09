export const DEFAULT_CHAT_MESSAGES_PADDING_PX = 80
export const CHAT_DOCK_CLEARANCE_PX = 20
const PINNED_CHAT_CONTENT_PADDING_PX = 8

export interface ChatDockLayoutInput {
  isPinned: boolean
  dockHeight: number
}

export interface ChatDockLayout {
  contentPaddingBottomPx: number
  messagesPaddingBottomPx: number
}

export const resolveChatDockLayout = ({
  isPinned,
  dockHeight,
}: ChatDockLayoutInput): ChatDockLayout => {
  if (!isPinned) {
    return {
      contentPaddingBottomPx: 0,
      messagesPaddingBottomPx: DEFAULT_CHAT_MESSAGES_PADDING_PX,
    }
  }

  const measuredDockHeight = Number.isFinite(dockHeight) ? Math.max(Math.ceil(dockHeight), 0) : 0

  return {
    contentPaddingBottomPx: PINNED_CHAT_CONTENT_PADDING_PX,
    messagesPaddingBottomPx: Math.max(
      DEFAULT_CHAT_MESSAGES_PADDING_PX,
      measuredDockHeight + CHAT_DOCK_CLEARANCE_PX,
    ),
  }
}
