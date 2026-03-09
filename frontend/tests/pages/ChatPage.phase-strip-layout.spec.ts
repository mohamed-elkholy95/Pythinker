import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

describe('ChatPage - Phase strip layout', () => {
  it('centers the phase strip inside the chat content width', () => {
    const chatPageSource = readFileSync('src/pages/ChatPage.vue', 'utf-8')

    expect(chatPageSource).toMatch(
      /<div\s+v-if="showPhaseStrip"\s+class="mx-auto w-full max-w-full px-5 sm:max-w-\[768px\] sm:min-w-\[400px\]"\s*>\s*<PhaseStrip/s
    )
  })
})
