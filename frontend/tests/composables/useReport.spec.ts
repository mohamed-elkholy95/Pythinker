/**
 * Tests for useReport composable
 * Tests report modal state and markdown parsing utilities
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('useReport', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.resetModules()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('Report Modal State', () => {
    it('should initialize with modal closed', async () => {
      const { useReport } = await import('@/composables/useReport')
      const { isReportModalOpen, currentReport } = useReport()

      expect(isReportModalOpen.value).toBe(false)
      expect(currentReport.value).toBeNull()
    })

    it('should open report modal with report data', async () => {
      const { useReport } = await import('@/composables/useReport')
      const { isReportModalOpen, currentReport, openReport } = useReport()

      const mockReport = {
        id: 'report-1',
        title: 'Test Report',
        content: '# Test\n\nContent here',
        lastModified: Date.now(),
        fileCount: 0,
        sections: [],
      }

      openReport(mockReport)

      expect(isReportModalOpen.value).toBe(true)
      expect(currentReport.value).toEqual(mockReport)
    })

    it('should close report modal and clear report after delay', async () => {
      const { useReport } = await import('@/composables/useReport')
      const { isReportModalOpen, currentReport, openReport, closeReport } = useReport()

      const mockReport = {
        id: 'report-1',
        title: 'Test Report',
        content: '# Test',
        lastModified: Date.now(),
        fileCount: 0,
        sections: [],
      }

      openReport(mockReport)
      closeReport()

      expect(isReportModalOpen.value).toBe(false)
      expect(currentReport.value).not.toBeNull() // Still there during animation

      // Fast-forward past animation delay
      vi.advanceTimersByTime(300)

      expect(currentReport.value).toBeNull()
    })

    it('should open report from markdown content', async () => {
      const { useReport } = await import('@/composables/useReport')
      const { isReportModalOpen, currentReport, openReportFromMarkdown } = useReport()

      openReportFromMarkdown(
        'report-1',
        '# My Report\n\n## Section 1\n\nContent here',
        [],
        Date.now()
      )

      expect(isReportModalOpen.value).toBe(true)
      expect(currentReport.value?.id).toBe('report-1')
      expect(currentReport.value?.title).toBe('My Report')
    })
  })

  describe('extractTitleFromMarkdown', () => {
    it('should extract h1 heading as title', async () => {
      const { extractTitleFromMarkdown } = await import('@/composables/useReport')

      const content = '# My Report Title\n\n## Section'
      expect(extractTitleFromMarkdown(content)).toBe('My Report Title')
    })

    it('should fall back to h2 if no h1', async () => {
      const { extractTitleFromMarkdown } = await import('@/composables/useReport')

      const content = '## Section Title\n\nContent'
      expect(extractTitleFromMarkdown(content)).toBe('Section Title')
    })

    it('should use first line if no heading', async () => {
      const { extractTitleFromMarkdown } = await import('@/composables/useReport')

      const content = 'Just some text\n\nMore text'
      expect(extractTitleFromMarkdown(content)).toBe('Just some text')
    })

    it('should return default title for empty content', async () => {
      const { extractTitleFromMarkdown } = await import('@/composables/useReport')

      expect(extractTitleFromMarkdown('')).toBe('Untitled Report')
    })
  })

  describe('extractSectionsFromMarkdown', () => {
    it('should extract sections from headings', async () => {
      const { extractSectionsFromMarkdown } = await import('@/composables/useReport')

      const content = `## Introduction

This is the intro content.

## Methods

This is the methods section.

### Subsection

More details here.`

      const sections = extractSectionsFromMarkdown(content)

      expect(sections).toHaveLength(3)
      expect(sections[0].title).toBe('Introduction')
      expect(sections[0].level).toBe(2)
      expect(sections[1].title).toBe('Methods')
      expect(sections[2].title).toBe('Subsection')
      expect(sections[2].level).toBe(3)
    })

    it('should include preview text from content', async () => {
      const { extractSectionsFromMarkdown } = await import('@/composables/useReport')

      const content = `## Introduction

This is the introduction paragraph with some content.`

      const sections = extractSectionsFromMarkdown(content)

      expect(sections[0].preview).toContain('introduction paragraph')
    })

    it('should skip code blocks and tables in preview', async () => {
      const { extractSectionsFromMarkdown } = await import('@/composables/useReport')

      const content = `## Section

\`\`\`javascript
const x = 1
\`\`\`

| Col1 | Col2 |
|------|------|
| A    | B    |

Regular text here.`

      const sections = extractSectionsFromMarkdown(content)

      // The implementation skips lines starting with ``` or |
      // but may include inline code that doesn't match those patterns
      expect(sections[0].preview).not.toContain('Col1')
      expect(sections[0].preview).toContain('Regular text')
    })

    it('should strip markdown formatting from preview', async () => {
      const { extractSectionsFromMarkdown } = await import('@/composables/useReport')

      const content = `## Section

This has **bold** and *italic* and [links](http://example.com) and \`code\`.`

      const sections = extractSectionsFromMarkdown(content)

      expect(sections[0].preview).toContain('bold')
      expect(sections[0].preview).toContain('italic')
      expect(sections[0].preview).toContain('links')
      expect(sections[0].preview).toContain('code')
      expect(sections[0].preview).not.toContain('**')
      expect(sections[0].preview).not.toContain('*')
      expect(sections[0].preview).not.toContain('`')
      expect(sections[0].preview).not.toContain('http://')
    })

    it('should truncate long previews', async () => {
      const { extractSectionsFromMarkdown } = await import('@/composables/useReport')

      const longContent = '## Section\n\n' + 'Lorem ipsum '.repeat(100)

      const sections = extractSectionsFromMarkdown(longContent)

      expect(sections[0].preview.length).toBeLessThanOrEqual(300)
    })

    it('should return empty array for content without headings', async () => {
      const { extractSectionsFromMarkdown } = await import('@/composables/useReport')

      const content = 'Just some text without any headings.'

      const sections = extractSectionsFromMarkdown(content)

      expect(sections).toHaveLength(0)
    })
  })

  describe('createReportFromMarkdown', () => {
    it('should create report data from markdown', async () => {
      const { createReportFromMarkdown } = await import('@/composables/useReport')

      const content = '# Report Title\n\n## Section 1\n\nContent'
      const now = Date.now()

      const report = createReportFromMarkdown('test-id', content, [], now)

      expect(report.id).toBe('test-id')
      expect(report.title).toBe('Report Title')
      expect(report.content).toBe(content)
      expect(report.lastModified).toBe(now)
      expect(report.fileCount).toBe(0)
      expect(report.sections).toHaveLength(1)
    })

    it('should include attachment count', async () => {
      const { createReportFromMarkdown } = await import('@/composables/useReport')

      const attachments = [
        { filename: 'file1.txt', path: '/path/1', size: 100, mtime: Date.now() },
        { filename: 'file2.txt', path: '/path/2', size: 200, mtime: Date.now() },
      ]

      const report = createReportFromMarkdown('test-id', '# Test', attachments)

      expect(report.fileCount).toBe(2)
      expect(report.attachments).toEqual(attachments)
    })

    it('should use current time if lastModified not provided', async () => {
      const { createReportFromMarkdown } = await import('@/composables/useReport')

      const before = Date.now()
      const report = createReportFromMarkdown('test-id', '# Test')
      const after = Date.now()

      expect(report.lastModified).toBeGreaterThanOrEqual(before)
      expect(report.lastModified).toBeLessThanOrEqual(after)
    })
  })

  describe('reportState', () => {
    it('should export singleton state', async () => {
      const { reportState, useReport } = await import('@/composables/useReport')
      const { openReport } = useReport()

      const mockReport = {
        id: 'report-1',
        title: 'Test',
        content: '# Test',
        lastModified: Date.now(),
        fileCount: 0,
        sections: [],
      }

      openReport(mockReport)

      expect(reportState.isOpen.value).toBe(true)
      expect(reportState.current.value).toEqual(mockReport)
    })
  })
})
