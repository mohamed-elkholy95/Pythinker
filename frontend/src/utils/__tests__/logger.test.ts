import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// logger.ts reads import.meta.env.DEV at module load time, so we patch it
// before importing to control which level is active.
vi.stubGlobal('import', {
  meta: { env: { DEV: true } },
})

// Import after stubbing so the module picks up DEV = true (level = 'debug')
const { logger } = await import('@/utils/logger')

describe('logger', () => {
  let debugSpy: ReturnType<typeof vi.spyOn>
  let infoSpy: ReturnType<typeof vi.spyOn>
  let warnSpy: ReturnType<typeof vi.spyOn>
  let errorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {})
    infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {})
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('logger.debug prefixes message with [DEBUG]', () => {
    logger.debug('hello')
    expect(debugSpy).toHaveBeenCalledWith('[DEBUG] hello')
  })

  it('logger.info prefixes message with [INFO]', () => {
    logger.info('hello')
    expect(infoSpy).toHaveBeenCalledWith('[INFO] hello')
  })

  it('logger.warn prefixes message with [WARN]', () => {
    logger.warn('something')
    expect(warnSpy).toHaveBeenCalledWith('[WARN] something')
  })

  it('logger.error prefixes message with [ERROR]', () => {
    logger.error('boom')
    expect(errorSpy).toHaveBeenCalledWith('[ERROR] boom')
  })

  it('passes extra arguments through', () => {
    const extra = { key: 'value' }
    logger.info('with extra', extra)
    expect(infoSpy).toHaveBeenCalledWith('[INFO] with extra', extra)
  })

  it('passes multiple extra arguments through', () => {
    logger.warn('multi', 1, 2, 3)
    expect(warnSpy).toHaveBeenCalledWith('[WARN] multi', 1, 2, 3)
  })
})
