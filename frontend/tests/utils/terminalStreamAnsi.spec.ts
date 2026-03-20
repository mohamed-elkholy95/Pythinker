import { describe, expect, it } from 'vitest'
import {
  TerminalStreamAnsiTransformer,
  isLikelyDollarCommandLine,
  isLikelyShellPromptLine,
} from '@/utils/terminalStreamAnsi'

describe('terminalStreamAnsi', () => {
  it('detects ubuntu-style prompts', () => {
    expect(isLikelyShellPromptLine('ubuntu@sandbox:/workspace$')).toBe(true)
    expect(isLikelyShellPromptLine('ubuntu@sandbox:/workspace $')).toBe(true)
    expect(isLikelyShellPromptLine('user@host:~$')).toBe(true)
    expect(isLikelyShellPromptLine('plain text')).toBe(false)
  })

  it('detects dollar command echoes', () => {
    expect(isLikelyDollarCommandLine('$ curl https://example.com')).toBe(true)
    expect(isLikelyDollarCommandLine('  $ jq .')).toBe(true)
    expect(isLikelyDollarCommandLine('{ "a": 1 }')).toBe(false)
  })

  it('buffers and colorizes across chunks', () => {
    const t = new TerminalStreamAnsiTransformer()
    expect(t.transform('ubuntu@sandbox')).toBe('')
    const out = t.transform(':/workspace$\n')
    expect(out).toContain('\x1b[32m')
    expect(out).toContain('ubuntu@sandbox:/workspace$')
    expect(out).toContain('\x1b[0m')
  })

  it('flush handles trailing line without newline', () => {
    const t = new TerminalStreamAnsiTransformer()
    t.transform('ubuntu@sandbox:~$')
    const tail = t.flush()
    expect(tail).toContain('\x1b[32m')
    expect(t.flush()).toBe('')
  })
})
