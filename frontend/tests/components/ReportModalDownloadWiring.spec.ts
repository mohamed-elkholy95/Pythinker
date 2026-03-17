import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'

const readSource = (relativePath: string): string => readFileSync(relativePath, 'utf-8')

describe('Report modal download wiring', () => {
  it('keeps report modal downloads self-contained without parent markdown fallback wiring', () => {
    const chatPageSource = readSource('src/pages/ChatPage.vue')
    const reportModalSource = readSource('src/components/report/ReportModal.vue')

    expect(chatPageSource).not.toContain('@download="handleReportDownload"')
    expect(chatPageSource).not.toContain('const handleReportDownload =')
    expect(chatPageSource).toContain(':sessionId="sessionId"')

    expect(reportModalSource).not.toContain("(e: 'download')")
    expect(reportModalSource).not.toContain("emit('download')")
    expect(reportModalSource).not.toContain("import html2pdf from 'html2pdf.js'")
    expect(reportModalSource).toContain('downloadSessionReportPdf(')
  })
})
