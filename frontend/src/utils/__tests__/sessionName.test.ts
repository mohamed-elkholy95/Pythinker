import { describe, it, expect } from 'vitest'
import { deriveSessionName } from '@/utils/sessionName'

describe('deriveSessionName', () => {
  it('returns "terminal" for undefined command', () => {
    expect(deriveSessionName(undefined)).toBe('terminal')
  })

  it('returns "terminal" for empty string', () => {
    expect(deriveSessionName('')).toBe('terminal')
  })

  it('extracts script name from python command', () => {
    expect(deriveSessionName('python3 my_script.py')).toBe('my_script')
  })

  it('extracts script name from node command', () => {
    expect(deriveSessionName('node server.js')).toBe('server')
  })

  it('extracts script name from bash command', () => {
    expect(deriveSessionName('bash deploy.sh')).toBe('deploy')
  })

  it('returns "terminal" for python without script arg', () => {
    expect(deriveSessionName('python3')).toBe('terminal')
  })

  it('skips interpreter flags for python', () => {
    expect(deriveSessionName('python3 -u script.py')).toBe('script')
  })

  it('skips interpreter flags for node', () => {
    expect(deriveSessionName('node --experimental-modules app.js')).toBe('app')
  })

  it('skips interpreter flags for bash', () => {
    expect(deriveSessionName('bash -x deploy.sh')).toBe('deploy')
  })

  it('detects package install commands', () => {
    expect(deriveSessionName('pip install requests')).toBe('package_install')
    expect(deriveSessionName('npm install lodash')).toBe('package_install')
    expect(deriveSessionName('bun install vitest')).toBe('package_install')
  })

  it('detects file creation via heredoc', () => {
    expect(deriveSessionName('cat << EOF > output.txt')).toBe('file_creation')
  })

  it('detects git subcommands', () => {
    expect(deriveSessionName('git commit -m "fix"')).toBe('git_commit')
    expect(deriveSessionName('git push origin main')).toBe('git_push')
    expect(deriveSessionName('git')).toBe('git_operation')
  })

  it('detects docker commands', () => {
    expect(deriveSessionName('docker compose up -d')).toBe('docker')
  })

  it('detects make/build commands', () => {
    expect(deriveSessionName('make build')).toBe('build')
  })

  it('returns "terminal" for generic commands', () => {
    expect(deriveSessionName('ls -la')).toBe('terminal')
    expect(deriveSessionName('curl https://example.com')).toBe('terminal')
  })

  it('handles piped commands by using first segment', () => {
    expect(deriveSessionName('python3 analyze.py | head -10')).toBe('analyze')
  })

  it('handles redirected output by using first segment', () => {
    expect(deriveSessionName('python3 gen.py > output.txt')).toBe('gen')
  })
})
