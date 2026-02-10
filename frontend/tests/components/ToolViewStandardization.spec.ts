import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'

const readSource = (relativePath: string): string =>
  readFileSync(relativePath, 'utf-8')

const TOOL_VIEW_FILES = [
  'src/components/toolViews/shared/ContentContainer.vue',
  'src/components/toolViews/shared/LoadingState.vue',
  'src/components/toolViews/shared/EmptyState.vue',
  'src/components/toolViews/shared/ErrorState.vue',
  'src/components/toolViews/GenericContentView.vue',
  'src/components/ToolPanelContent.vue',
]

describe('tool view standardization', () => {
  it('keeps tool-view surfaces free from hard-coded hex color literals', () => {
    for (const file of TOOL_VIEW_FILES) {
      const source = readSource(file)
      const withoutHtmlEntities = source
        .replaceAll('&#39;', '')
        .replaceAll('&#34;', '')
      expect(withoutHtmlEntities, file).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    }
  })

  it('routes generic tool rendering through shared loading, empty, and error states', () => {
    const source = readSource('src/components/toolViews/GenericContentView.vue')

    expect(source).toContain("import ContentContainer")
    expect(source).toContain("import LoadingState")
    expect(source).toContain("import EmptyState")
    expect(source).toContain("import ErrorState")

    expect(source).toContain('<LoadingState')
    expect(source).toContain('<EmptyState')
    expect(source).toContain('<ErrorState')
  })

  it('keeps content containers and panel content on shared tokenized layout primitives', () => {
    const contentContainer = readSource('src/components/toolViews/shared/ContentContainer.vue')
    const toolPanel = readSource('src/components/ToolPanelContent.vue')

    expect(contentContainer).toContain('min-height: 0;')
    expect(contentContainer).toContain('var(--space-')
    expect(toolPanel).toContain('panel-content-header')
    expect(toolPanel).toContain('<GenericContentView')
  })
})
