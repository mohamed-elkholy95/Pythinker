import { describe, it, expect } from 'vitest'
import { stripCmdMarkers, cleanPs1, cleanShellOutput } from '@/utils/shellSanitizer'

describe('stripCmdMarkers', () => {
  it('removes [CMD_BEGIN] marker', () => {
    expect(stripCmdMarkers('[CMD_BEGIN]output')).toBe('output')
  })

  it('removes [CMD_END] marker', () => {
    expect(stripCmdMarkers('output[CMD_END]')).toBe('output')
  })

  it('removes both markers from a full block', () => {
    expect(stripCmdMarkers('[CMD_BEGIN]\nhello world\n[CMD_END]')).toBe('\nhello world\n')
  })

  it('removes multiple occurrences', () => {
    expect(stripCmdMarkers('[CMD_BEGIN]a[CMD_END][CMD_BEGIN]b[CMD_END]')).toBe('ab')
  })

  it('returns unchanged text when no markers present', () => {
    expect(stripCmdMarkers('just normal text')).toBe('just normal text')
  })

  it('handles empty string', () => {
    expect(stripCmdMarkers('')).toBe('')
  })
})

describe('cleanPs1', () => {
  it('strips markers and trims whitespace', () => {
    expect(cleanPs1('[CMD_BEGIN]  user@host  ')).toBe('user@host $')
  })

  it('does not double-append $ if already present', () => {
    expect(cleanPs1('user@host $')).toBe('user@host $')
  })

  it('returns empty string for empty input', () => {
    expect(cleanPs1('')).toBe('')
  })

  it('appends $ to prompt without one', () => {
    expect(cleanPs1('user@host:')).toBe('user@host: $')
  })
})

describe('cleanShellOutput', () => {
  it('strips markers and removes command echo header', () => {
    const output = '[CMD_BEGIN]\nuser@host $ ls\nfile1\nfile2\n[CMD_END]'
    expect(cleanShellOutput(output, 'ls')).toBe('file1\nfile2\n')
  })

  it('strips markers without command', () => {
    const output = '[CMD_BEGIN]\nhello\n[CMD_END]'
    expect(cleanShellOutput(output)).toBe('hello\n')
  })

  it('removes leading newlines from cleaned output', () => {
    const output = '\n\n\nactual output'
    expect(cleanShellOutput(output)).toBe('actual output')
  })

  it('handles output that does not contain command echo', () => {
    const output = '[CMD_BEGIN]\nsome output\n[CMD_END]'
    expect(cleanShellOutput(output, 'nonexistent')).toBe('some output\n')
  })

  it('handles empty output', () => {
    expect(cleanShellOutput('')).toBe('')
  })
})
