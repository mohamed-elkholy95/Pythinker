import { ref, type Ref, onUnmounted } from 'vue'
import { shareSession, unshareSession } from '@/api/agent'
import { copyToClipboard } from '@/utils/dom'
import { showErrorToast, showSuccessToast } from '@/utils/toast'
import { useI18n } from 'vue-i18n'

/**
 * Composable that encapsulates all share-popover state and handlers.
 *
 * @param sessionId - Reactive ref to the current session ID.
 */
export function useShareSession(sessionId: Ref<string | undefined>) {
  const { t } = useI18n()

  const shareMode = ref<'private' | 'public'>('private')
  const linkCopied = ref(false)
  const sharingLoading = ref(false)

  let linkCopiedTimer: ReturnType<typeof setTimeout> | null = null

  /** Initialise share mode from a persisted session record. */
  const initFromSession = (isShared: boolean) => {
    shareMode.value = isShared ? 'public' : 'private'
  }

  /** Toggle between private / public and call the backend accordingly. */
  const handleShareModeChange = async (mode: 'private' | 'public') => {
    if (!sessionId.value || sharingLoading.value) return

    // If mode is same as current, no need to call API
    if (shareMode.value === mode) {
      linkCopied.value = false
      return
    }

    try {
      sharingLoading.value = true

      if (mode === 'public') {
        await shareSession(sessionId.value)
      } else {
        await unshareSession(sessionId.value)
      }

      shareMode.value = mode
      linkCopied.value = false
    } catch {
      showErrorToast(t('Failed to change sharing settings'))
    } finally {
      sharingLoading.value = false
    }
  }

  /** One-click share: make public immediately. */
  const handleInstantShare = async () => {
    if (!sessionId.value) return

    try {
      sharingLoading.value = true
      await shareSession(sessionId.value)
      shareMode.value = 'public'
      linkCopied.value = false
    } catch {
      showErrorToast(t('Failed to share session'))
    } finally {
      sharingLoading.value = false
    }
  }

  /** Copy the public share link to the clipboard. */
  const handleCopyLink = async () => {
    if (!sessionId.value) return

    const shareUrl = `${window.location.origin}/share/${sessionId.value}`

    try {
      const success = await copyToClipboard(shareUrl)

      if (success) {
        linkCopied.value = true
        if (linkCopiedTimer) clearTimeout(linkCopiedTimer)
        linkCopiedTimer = setTimeout(() => {
          linkCopiedTimer = null
          linkCopied.value = false
        }, 3000)
        showSuccessToast(t('Link copied to clipboard'))
      } else {
        showErrorToast(t('Failed to copy link'))
      }
    } catch {
      showErrorToast(t('Failed to copy link'))
    }
  }

  /** Clean up the copy-feedback timer. */
  const cleanup = () => {
    if (linkCopiedTimer) {
      clearTimeout(linkCopiedTimer)
      linkCopiedTimer = null
    }
  }

  onUnmounted(cleanup)

  return {
    shareMode,
    linkCopied,
    sharingLoading,
    handleShareModeChange,
    handleInstantShare,
    handleCopyLink,
    initFromSession,
    cleanup,
  }
}
