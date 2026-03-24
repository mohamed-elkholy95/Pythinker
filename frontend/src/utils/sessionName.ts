/**
 * Derive a human-readable terminal session name from a shell command.
 * Used as fallback when backend doesn't provide session_name.
 */
export function deriveSessionName(command: string | undefined): string {
  if (!command) return 'terminal'

  const base = command.split('|')[0].split('>')[0].trim()
  const parts = base.split(/\s+/)
  const cmd = parts[0]

  // Script execution: python3 script.py → "script_name"
  // Skip interpreter flags (e.g. python3 -u script.py)
  if (['python3', 'python', 'node', 'bash', 'sh'].includes(cmd)) {
    const script = parts.slice(1).find((p) => !p.startsWith('-'))
    if (script) {
      return script.replace(/\.\w+$/, '').replace(/[^a-zA-Z0-9]/g, '_') || 'terminal'
    }
  }

  // Package install
  if (['pip', 'npm', 'bun', 'yarn'].includes(cmd) && parts[1] === 'install') {
    return 'package_install'
  }

  // File creation via heredoc
  if (cmd === 'cat' && command.includes('<<')) return 'file_creation'

  // Known tool commands
  if (cmd.includes('pdf') || cmd.includes('convert')) return 'pdf_conversion'
  if (cmd === 'git') return `git_${parts[1] || 'operation'}`
  if (cmd === 'docker' || cmd === 'docker-compose') return 'docker'
  if (cmd === 'make') return 'build'

  // Generic commands (curl, ls, cat, etc.) → just show "terminal"
  return 'terminal'
}
