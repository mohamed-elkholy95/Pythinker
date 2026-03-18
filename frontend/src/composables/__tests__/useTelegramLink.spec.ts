import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'

const { generateLinkCodeMock, getLinkedChannelsMock, openMock, writeTextMock } = vi.hoisted(() => ({
  generateLinkCodeMock: vi.fn(),
  getLinkedChannelsMock: vi.fn(),
  openMock: vi.fn(),
  writeTextMock: vi.fn(),
}))

vi.mock('@/api/channelLinks', () => ({
  generateLinkCode: generateLinkCodeMock,
  getLinkedChannels: getLinkedChannelsMock,
}))

import { useTelegramLink } from '../useTelegramLink'

type TelegramLinkComposable = ReturnType<typeof useTelegramLink>

let clipboardWriteSpy: { mockRestore: () => void } | null = null

const mountUseTelegramLink = (onLinkSuccess?: () => void) => {
  let composable: TelegramLinkComposable | null = null
  const wrapper = mount(
    defineComponent({
      setup() {
        composable = useTelegramLink({ onLinkSuccess })
        return () => h('div')
      },
    }),
  )

  if (!composable) {
    throw new Error('Failed to initialize composable')
  }

  return {
    composable: composable as TelegramLinkComposable,
    wrapper,
  }
}

describe('useTelegramLink', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()

    vi.stubGlobal('open', openMock)
    clipboardWriteSpy = vi.spyOn(navigator.clipboard, 'writeText').mockImplementation(writeTextMock)
  })

  afterEach(() => {
    clipboardWriteSpy?.mockRestore()
    clipboardWriteSpy = null
    vi.useRealTimers()
  })

  it('generate() initializes command draft, opens deep link, and starts polling', async () => {
    generateLinkCodeMock.mockResolvedValue({
      code: 'ABC123',
      bind_command: ':bind ABC123',
      bot_url: 'https://t.me/pythinker_bot',
      deep_link_url: 'https://t.me/pythinker_bot?start=bind_ABC123',
      expires_in_seconds: 120,
    })
    getLinkedChannelsMock.mockResolvedValue([])

    const { composable, wrapper } = mountUseTelegramLink()

    await composable.generate()

    expect(generateLinkCodeMock).toHaveBeenCalledWith('telegram')
    expect(composable.bindCommand.value).toBe(':bind ABC123')
    expect(composable.countdown.value).toBe(120)
    expect(openMock).toHaveBeenCalledWith(
      'https://t.me/pythinker_bot?start=bind_ABC123',
      '_blank',
      'noopener,noreferrer',
    )

    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()

    expect(getLinkedChannelsMock).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('copyCommand() writes to clipboard and resets copied state after 2 seconds', async () => {
    writeTextMock.mockResolvedValue(undefined)
    const { composable, wrapper } = mountUseTelegramLink()

    composable.bindCommand.value = ':bind ABC123'
    await composable.copyCommand()

    expect(writeTextMock).toHaveBeenCalledWith(':bind ABC123')
    expect(composable.isCopied.value).toBe(true)

    await vi.advanceTimersByTimeAsync(2000)
    expect(composable.isCopied.value).toBe(false)
    wrapper.unmount()
  })

  it('openDeepLink() prefers deep_link_url over bot_url', () => {
    const { composable, wrapper } = mountUseTelegramLink()

    composable.botUrl.value = 'https://t.me/fallback_bot'
    composable.deepLinkUrl.value = 'https://t.me/preferred_bot?start=bind_ABC123'

    composable.openDeepLink()

    expect(openMock).toHaveBeenCalledWith(
      'https://t.me/preferred_bot?start=bind_ABC123',
      '_blank',
      'noopener,noreferrer',
    )
    wrapper.unmount()
  })

  it('countdown expiry clears draft and marks link as expired', async () => {
    generateLinkCodeMock.mockResolvedValue({
      code: 'ABC123',
      bind_command: ':bind ABC123',
      bot_url: 'https://t.me/pythinker_bot',
      deep_link_url: 'https://t.me/pythinker_bot?start=bind_ABC123',
      expires_in_seconds: 1,
    })
    getLinkedChannelsMock.mockResolvedValue([])
    openMock.mockReturnValue({})

    const { composable, wrapper } = mountUseTelegramLink()

    await composable.generate()
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()

    expect(composable.bindCommand.value).toBeNull()
    expect(composable.feedback.value).toBe('Link expired. Generate a new one.')
    wrapper.unmount()
  })

  it('polling detects linked channel and clears draft with success callback', async () => {
    const onLinkSuccess = vi.fn()
    generateLinkCodeMock.mockResolvedValue({
      code: 'ABC123',
      bind_command: ':bind ABC123',
      bot_url: 'https://t.me/pythinker_bot',
      deep_link_url: 'https://t.me/pythinker_bot?start=bind_ABC123',
      expires_in_seconds: 120,
    })
    getLinkedChannelsMock.mockResolvedValueOnce([
      {
        channel: 'telegram',
        sender_id: '5829880422|john',
        linked_at: '2026-03-03T12:00:00Z',
      },
    ])
    openMock.mockReturnValue({})

    const { composable, wrapper } = mountUseTelegramLink(onLinkSuccess)

    await composable.generate()
    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()

    expect(composable.bindCommand.value).toBeNull()
    expect(onLinkSuccess).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})
