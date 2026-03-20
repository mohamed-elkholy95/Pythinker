/**
 * Injects ANSI green (xterm color 32 → theme "prompt" green) into plain-text
 * terminal streams so sandbox prompts and `$ command` echoes match static Shiki styling.
 */

const ESC = '\u001b'
const ANSI_SGR_RE = new RegExp(`${ESC}\\[[\\d;]*m`)

const GREEN = `${ESC}[32m`
const RESET = `${ESC}[0m`

function hasExistingAnsi(line: string): boolean {
  return ANSI_SGR_RE.test(line)
}

/** user@host:path$ or user@host:path# (common bash PS1) */
export function isLikelyShellPromptLine(line: string): boolean {
  const t = line.replace(/\r$/, '')
  if (!t.trim()) return false
  if (hasExistingAnsi(t)) return false
  if (/^.+@\S+:\S*[$#]/.test(t)) return true
  if (/^.+@sandbox\b/.test(t) && /[$#]\s*$/.test(t.trimEnd())) return true
  return false
}

/** Echoed user command lines: `$ curl ...` */
export function isLikelyDollarCommandLine(line: string): boolean {
  const t = line.replace(/\r$/, '')
  if (!t.trim()) return false
  if (hasExistingAnsi(t)) return false
  return /^\s*\$\s+\S/.test(t)
}

function colorizeLine(line: string): string {
  if (isLikelyShellPromptLine(line) || isLikelyDollarCommandLine(line)) {
    return `${GREEN}${line}${RESET}`
  }
  return line
}

/**
 * Buffers incomplete lines across SSE chunks, then colorizes complete lines.
 */
export class TerminalStreamAnsiTransformer {
  private incomplete = ''

  reset(): void {
    this.incomplete = ''
  }

  transform(chunk: string): string {
    const full = this.incomplete + chunk
    const parts = full.split(/\r?\n/)
    this.incomplete = parts.pop() ?? ''
    if (parts.length === 0) return ''
    return parts.map((l) => colorizeLine(l)).join('\r\n') + '\r\n'
  }

  /** Flush trailing text without a final newline (e.g. stream end). */
  flush(): string {
    const tail = this.incomplete
    this.incomplete = ''
    if (!tail) return ''
    return colorizeLine(tail)
  }
}
