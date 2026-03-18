<template>
  <div class="skill-file-preview">
    <!-- No file selected state -->
    <div v-if="!file" class="empty-state">
      <FileText :size="48" class="empty-icon" />
      <p>Select a file to preview</p>
    </div>

    <!-- File preview -->
    <template v-else>
      <!-- YAML frontmatter for SKILL.md -->
      <div v-if="hasYamlFrontmatter" class="yaml-section">
        <div class="yaml-header">
          <span class="yaml-label">YAML</span>
          <button class="copy-btn" @click="copyYaml" title="Copy YAML">
            <Copy :size="14" />
          </button>
        </div>
        <div class="yaml-content">
          <div
            v-for="(value, key) in yamlMetadata"
            :key="key"
            class="yaml-row"
          >
            <span class="yaml-key">{{ key }}:</span>
            <span class="yaml-value">{{ formatYamlValue(value) }}</span>
          </div>
        </div>
      </div>

      <!-- Markdown content -->
      <div
        v-if="isMarkdown"
        class="markdown-content"
        v-html="renderedMarkdown"
      />

      <!-- Code content -->
      <div v-else-if="isCode" class="code-content">
        <pre><code :class="`language-${codeLanguage}`">{{ displayContent }}</code></pre>
      </div>

      <!-- Plain text -->
      <div v-else class="text-content">
        <pre>{{ displayContent }}</pre>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FileText, Copy } from 'lucide-vue-next'
import { marked } from 'marked'
import { sanitizeHtml } from '@/utils/sanitize'
import type { SkillPackageFile } from '@/types/message'

interface Props {
  file?: SkillPackageFile
}

const props = defineProps<Props>()

// File extension helpers
const fileExtension = computed(() => {
  if (!props.file) return ''
  return props.file.path.split('.').pop()?.toLowerCase() || ''
})

const isMarkdown = computed(() => fileExtension.value === 'md')

const isCode = computed(() => {
  return ['py', 'js', 'ts', 'json', 'yaml', 'yml', 'sh', 'bash'].includes(fileExtension.value)
})

const codeLanguage = computed(() => {
  const langMap: Record<string, string> = {
    py: 'python',
    js: 'javascript',
    ts: 'typescript',
    json: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    sh: 'bash',
    bash: 'bash',
  }
  return langMap[fileExtension.value] || 'text'
})

// YAML frontmatter parsing for SKILL.md
const hasYamlFrontmatter = computed(() => {
  if (!props.file || !isMarkdown.value) return false
  return props.file.content.trim().startsWith('---')
})

const yamlMetadata = computed(() => {
  if (!hasYamlFrontmatter.value || !props.file) return {}

  const content = props.file.content
  const match = content.match(/^---\n([\s\S]*?)\n---/)
  if (!match) return {}

  const yamlStr = match[1]
  const metadata: Record<string, string> = {}

  // Simple YAML parsing (key: value pairs)
  yamlStr.split('\n').forEach(line => {
    const colonIndex = line.indexOf(':')
    if (colonIndex > 0) {
      const key = line.slice(0, colonIndex).trim()
      const value = line.slice(colonIndex + 1).trim()
      if (key && value) {
        metadata[key] = value
      }
    }
  })

  return metadata
})

// Content without frontmatter
const displayContent = computed(() => {
  if (!props.file) return ''

  if (hasYamlFrontmatter.value) {
    // Remove frontmatter
    const content = props.file.content
    const match = content.match(/^---\n[\s\S]*?\n---\n?/)
    if (match) {
      return content.slice(match[0].length).trim()
    }
  }

  return props.file.content
})

// Rendered markdown
const renderedMarkdown = computed(() => {
  if (!isMarkdown.value) return ''
  const rawHtml = marked(displayContent.value, {
    breaks: true,
    gfm: true,
  })
  return sanitizeHtml(rawHtml as string)
})

// Format YAML value for display (handle long strings)
const formatYamlValue = (value: string) => {
  if (value.length > 80) {
    return value.slice(0, 80) + '...'
  }
  return value
}

// Copy YAML frontmatter
const copyYaml = async () => {
  if (!props.file) return
  const content = props.file.content
  const match = content.match(/^---\n([\s\S]*?)\n---/)
  if (match) {
    try {
      await navigator.clipboard.writeText(match[1])
    } catch {
      // Copy to clipboard failed
    }
  }
}
</script>

<style scoped>
.skill-file-preview {
  height: 100%;
  overflow-y: auto;
  padding: 20px 24px;
}

/* Empty state */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
}

.empty-icon {
  color: var(--bolt-elements-textTertiary);
}

.empty-state p {
  color: var(--bolt-elements-textSecondary);
  font-size: 14px;
}

/* YAML section */
.yaml-section {
  background: var(--bolt-elements-bg-depth-2);
  border: 1px solid var(--bolt-elements-borderColor);
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 20px;
}

.yaml-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--bolt-elements-bg-depth-3);
  border-bottom: 1px solid var(--bolt-elements-borderColor);
}

.yaml-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--bolt-elements-textSecondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--bolt-elements-textTertiary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.copy-btn:hover {
  background: var(--bolt-elements-bg-depth-4);
  color: var(--bolt-elements-textPrimary);
}

.yaml-content {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.yaml-row {
  display: flex;
  gap: 8px;
  font-size: 13px;
  font-family: var(--font-mono);
}

.yaml-key {
  color: #22c55e;
  font-weight: 500;
}

.yaml-value {
  color: var(--bolt-elements-textPrimary);
}

/* Markdown content */
.markdown-content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--bolt-elements-textPrimary);
}

.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3) {
  margin-top: 24px;
  margin-bottom: 12px;
  font-weight: 600;
  color: var(--bolt-elements-textPrimary);
}

.markdown-content :deep(h1) {
  font-size: 24px;
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  padding-bottom: 8px;
}

.markdown-content :deep(h2) {
  font-size: 20px;
}

.markdown-content :deep(h3) {
  font-size: 16px;
}

.markdown-content :deep(p) {
  margin-bottom: 12px;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  margin-bottom: 12px;
  padding-left: 24px;
}

.markdown-content :deep(li) {
  margin-bottom: 4px;
}

.markdown-content :deep(code) {
  background: var(--bolt-elements-bg-depth-3);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 13px;
}

.markdown-content :deep(pre) {
  background: var(--bolt-elements-bg-depth-2);
  border: 1px solid var(--bolt-elements-borderColor);
  border-radius: 8px;
  padding: 14px;
  overflow-x: auto;
  margin-bottom: 12px;
}

.markdown-content :deep(pre code) {
  background: transparent;
  padding: 0;
}

.markdown-content :deep(blockquote) {
  border-left: 3px solid var(--bolt-elements-borderColorActive);
  padding-left: 16px;
  margin-left: 0;
  color: var(--bolt-elements-textSecondary);
  font-style: italic;
}

/* Code content */
.code-content {
  background: var(--bolt-elements-bg-depth-2);
  border: 1px solid var(--bolt-elements-borderColor);
  border-radius: 10px;
  overflow-x: auto;
}

.code-content pre {
  margin: 0;
  padding: 16px;
}

.code-content code {
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
  color: var(--bolt-elements-textPrimary);
}

/* Text content */
.text-content {
  background: var(--bolt-elements-bg-depth-2);
  border: 1px solid var(--bolt-elements-borderColor);
  border-radius: 10px;
  overflow-x: auto;
}

.text-content pre {
  margin: 0;
  padding: 16px;
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
  color: var(--bolt-elements-textPrimary);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
