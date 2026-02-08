<template>
  <div
    class="vnc-mini-preview"
    :class="sizeClass"
    @click="emit('click')"
  >
    <!-- Initializing state - sandbox environment starting up -->
    <div v-if="isInitializing" class="init-preview">
      <div class="init-container">
        <!-- Animated monitor icon with boot sequence effect -->
        <div class="init-monitor">
          <div class="monitor-frame">
            <div class="monitor-screen">
              <div class="scan-line"></div>
              <div class="boot-dots">
                <span class="boot-dot"></span>
                <span class="boot-dot"></span>
                <span class="boot-dot"></span>
              </div>
            </div>
            <div class="monitor-stand"></div>
          </div>
        </div>
        <span class="init-label">Initializing<span class="init-ellipsis"></span></span>
      </div>
      <!-- Subtle grid pattern background -->
      <div class="init-grid"></div>
    </div>

    <!-- Wide Research view (parallel multi-source search) -->
    <WideResearchMiniPreview
      v-else-if="isWideResearch && wideResearchState"
      :state="wideResearchState"
      :is-active="isActive"
    />

    <!-- Terminal view (shell, code_executor) -->
    <div v-else-if="currentViewType === 'terminal' && contentPreview" class="content-preview terminal-preview">
      <div class="terminal-window">
        <div class="terminal-header">
          <span class="terminal-title">{{ terminalTitle }}</span>
        </div>
        <div class="terminal-body">
          <div class="terminal-accent"></div>
          <div class="terminal-content-area">
            <pre class="preview-text terminal-text" v-html="styledTerminalContent"></pre>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Terminal tool running without content yet - show VNC -->
    <div v-else-if="currentViewType === 'terminal' && isActive && sessionId && enabled" class="vnc-container">
      <VNCViewer
        :session-id="sessionId"
        :enabled="enabled"
        :view-only="true"
      />
    </div>

    <!-- Search results view (search, info tools) -->
    <div v-else-if="currentViewType === 'search'" class="content-preview search-preview">
      <div class="search-window">
        <div class="search-header">
          <Search :size="10" class="search-header-icon" />
          <span class="search-title">{{ truncate(searchQuery || 'Search', 20) }}</span>
        </div>
        <div class="search-body">
          <div class="search-content-area">
            <div v-if="searchResults.length > 0" class="search-results-mini">
              <div v-for="(result, idx) in searchResults.slice(0, 3)" :key="idx" class="search-result-item">
                <img
                  :src="getFavicon(result.url || result.link)"
                  alt=""
                  class="result-favicon"
                  @error="handleFaviconError"
                />
                <div class="result-text">
                  <span class="result-title">{{ truncate(result.title || result.name || 'Result', 25) }}</span>
                  <span v-if="result.snippet" class="result-snippet">{{ truncate(result.snippet, 40) }}</span>
                </div>
              </div>
              <div v-if="searchResults.length > 3" class="results-more">
                +{{ searchResults.length - 3 }} more results
              </div>
            </div>
            <div v-else-if="isActive" class="search-loading">
              <div class="loading-dots">
                <span class="dot"></span>
                <span class="dot"></span>
                <span class="dot"></span>
              </div>
              <span class="loading-text">Searching...</span>
            </div>
            <div v-else class="search-empty">
              <Search :size="14" class="empty-search-icon" />
              <span>No results</span>
            </div>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Editor view (file tools) -->
    <div v-else-if="currentViewType === 'editor' && contentPreview" class="content-preview file-preview">
      <div class="file-window">
        <div class="file-header">
          <span class="file-title">{{ fileName }}</span>
        </div>
        <div class="file-body">
          <div class="file-accent"></div>
          <div class="file-content-area">
            <pre class="preview-text">{{ contentPreview }}</pre>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Generic/MCP view -->
    <div v-else-if="currentViewType === 'generic'" class="content-preview generic-preview">
      <div class="generic-window">
        <div class="generic-header">
          <Wrench :size="10" class="generic-header-icon" />
          <span class="generic-title">{{ toolFunction || toolName || 'Tool' }}</span>
        </div>
        <div class="generic-body">
          <div class="generic-accent"></div>
          <div class="generic-content-area">
            <div v-if="genericResult" class="generic-result-mini">
              <pre class="preview-text">{{ truncate(genericResultText, 100) }}</pre>
            </div>
            <div v-else-if="isActive" class="generic-loading">
              <Loader2 :size="14" class="loading-spinner" />
              <span class="loading-text">Executing...</span>
            </div>
            <div v-else class="generic-empty">
              <component :is="toolIcon" class="empty-icon" />
            </div>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Git view -->
    <div v-else-if="currentViewType === 'git'" class="content-preview git-preview">
      <div class="tool-card-window">
        <div class="tool-card-header git-header">
          <GitBranch :size="10" class="tool-card-header-icon" />
          <span class="tool-card-title">{{ gitOperationLabel }}</span>
        </div>
        <div class="tool-card-body">
          <div class="tool-card-accent git-accent"></div>
          <div class="tool-card-content-area">
            <div v-if="gitInfo?.branch" class="git-branch-badge">
              <GitBranch :size="8" />
              <span>{{ truncate(gitInfo.branch, 15) }}</span>
            </div>
            <div v-if="contentPreview" class="git-output">
              <pre class="preview-text terminal-text">{{ truncate(contentPreview, 80) }}</pre>
            </div>
            <div v-else-if="isActive" class="tool-card-loading">
              <Loader2 :size="14" class="loading-spinner" />
              <span class="loading-text">{{ gitOperationLabel }}...</span>
            </div>
            <div v-else class="tool-card-empty">
              <GitBranch :size="16" class="empty-icon" />
            </div>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Test runner view -->
    <div v-else-if="currentViewType === 'test'" class="content-preview test-preview">
      <div class="tool-card-window">
        <div class="tool-card-header test-header">
          <TestTube :size="10" class="tool-card-header-icon" />
          <span class="tool-card-title">Tests</span>
        </div>
        <div class="tool-card-body">
          <div class="tool-card-accent test-accent"></div>
          <div class="tool-card-content-area">
            <div v-if="testResults" class="test-results-mini">
              <div class="test-stat passed">
                <CheckCircle :size="10" />
                <span>{{ testResults.passed || 0 }}</span>
              </div>
              <div class="test-stat failed">
                <XCircle :size="10" />
                <span>{{ testResults.failed || 0 }}</span>
              </div>
              <div v-if="testResults.skipped" class="test-stat skipped">
                <AlertCircle :size="10" />
                <span>{{ testResults.skipped }}</span>
              </div>
            </div>
            <div v-else-if="isActive" class="tool-card-loading">
              <Loader2 :size="14" class="loading-spinner" />
              <span class="loading-text">Running tests...</span>
            </div>
            <div v-else class="tool-card-empty">
              <TestTube :size="16" class="empty-icon" />
            </div>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Skill view -->
    <div v-else-if="currentViewType === 'skill'" class="content-preview skill-preview">
      <div class="tool-card-window">
        <div class="tool-card-header skill-header">
          <Wand2 :size="10" class="tool-card-header-icon" />
          <span class="tool-card-title">{{ skillInfo?.name || 'Skill' }}</span>
        </div>
        <div class="tool-card-body">
          <div class="tool-card-accent skill-accent"></div>
          <div class="tool-card-content-area">
            <div v-if="skillInfo?.status" class="skill-status">
              <Wand2 :size="14" class="skill-icon" />
              <span class="skill-status-text">{{ skillInfo.status }}</span>
            </div>
            <div v-else-if="isActive" class="tool-card-loading">
              <Loader2 :size="14" class="loading-spinner" />
              <span class="loading-text">Loading skill...</span>
            </div>
            <div v-else class="tool-card-empty">
              <Wand2 :size="16" class="empty-icon" />
            </div>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Export view -->
    <div v-else-if="currentViewType === 'export'" class="content-preview export-preview">
      <div class="tool-card-window">
        <div class="tool-card-header export-header">
          <Download :size="10" class="tool-card-header-icon" />
          <span class="tool-card-title">Export</span>
        </div>
        <div class="tool-card-body">
          <div class="tool-card-accent export-accent"></div>
          <div class="tool-card-content-area">
            <div v-if="exportInfo?.filename" class="export-info">
              <Download :size="14" class="export-icon" />
              <span class="export-filename">{{ truncate(exportInfo.filename, 20) }}</span>
              <span v-if="exportInfo.format" class="export-format">.{{ exportInfo.format }}</span>
            </div>
            <div v-else-if="isActive" class="tool-card-loading">
              <Loader2 :size="14" class="loading-spinner" />
              <span class="loading-text">Exporting...</span>
            </div>
            <div v-else class="tool-card-empty">
              <Download :size="16" class="empty-icon" />
            </div>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Slides view -->
    <div v-else-if="currentViewType === 'slides'" class="content-preview slides-preview">
      <div class="tool-card-window">
        <div class="tool-card-header slides-header">
          <Presentation :size="10" class="tool-card-header-icon" />
          <span class="tool-card-title">{{ slidesInfo?.title || 'Slides' }}</span>
        </div>
        <div class="tool-card-body">
          <div class="tool-card-accent slides-accent"></div>
          <div class="tool-card-content-area">
            <div v-if="slidesInfo?.count" class="slides-info">
              <Presentation :size="14" class="slides-icon" />
              <span class="slides-count">{{ slidesInfo.count }} slides</span>
            </div>
            <div v-else-if="isActive" class="tool-card-loading">
              <Loader2 :size="14" class="loading-spinner" />
              <span class="loading-text">Creating slides...</span>
            </div>
            <div v-else class="tool-card-empty">
              <Presentation :size="16" class="empty-icon" />
            </div>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Workspace view -->
    <div v-else-if="currentViewType === 'workspace'" class="content-preview workspace-preview">
      <div class="tool-card-window">
        <div class="tool-card-header workspace-header">
          <FolderTree :size="10" class="tool-card-header-icon" />
          <span class="tool-card-title">{{ workspaceInfo?.type || 'Workspace' }}</span>
        </div>
        <div class="tool-card-body">
          <div class="tool-card-accent workspace-accent"></div>
          <div class="tool-card-content-area">
            <div v-if="workspaceInfo?.filesCount" class="workspace-info">
              <FolderTree :size="14" class="workspace-icon" />
              <span class="workspace-count">{{ workspaceInfo.filesCount }} files</span>
            </div>
            <div v-else-if="isActive" class="tool-card-loading">
              <Loader2 :size="14" class="loading-spinner" />
              <span class="loading-text">Organizing...</span>
            </div>
            <div v-else class="tool-card-empty">
              <FolderTree :size="16" class="empty-icon" />
            </div>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Schedule view -->
    <div v-else-if="currentViewType === 'schedule'" class="content-preview schedule-preview">
      <div class="tool-card-window">
        <div class="tool-card-header schedule-header">
          <Calendar :size="10" class="tool-card-header-icon" />
          <span class="tool-card-title">Schedule</span>
        </div>
        <div class="tool-card-body">
          <div class="tool-card-accent schedule-accent"></div>
          <div class="tool-card-content-area">
            <div v-if="scheduleInfo?.time" class="schedule-info">
              <Calendar :size="14" class="schedule-icon" />
              <span class="schedule-time">{{ scheduleInfo.time }}</span>
            </div>
            <div v-else-if="isActive" class="tool-card-loading">
              <Loader2 :size="14" class="loading-spinner" />
              <span class="loading-text">Scheduling...</span>
            </div>
            <div v-else class="tool-card-empty">
              <Calendar :size="16" class="empty-icon" />
            </div>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Scan/Analyzer view -->
    <div v-else-if="currentViewType === 'scan'" class="content-preview scan-preview">
      <div class="tool-card-window">
        <div class="tool-card-header scan-header">
          <Scan :size="10" class="tool-card-header-icon" />
          <span class="tool-card-title">{{ scanInfo?.type || 'Analysis' }}</span>
        </div>
        <div class="tool-card-body">
          <div class="tool-card-accent scan-accent"></div>
          <div class="tool-card-content-area">
            <div v-if="scanInfo?.findingsCount !== undefined" class="scan-info">
              <Scan :size="14" class="scan-icon" />
              <span class="scan-count">{{ scanInfo.findingsCount }} findings</span>
            </div>
            <div v-else-if="isActive" class="tool-card-loading">
              <Loader2 :size="14" class="loading-spinner" />
              <span class="loading-text">Analyzing...</span>
            </div>
            <div v-else class="tool-card-empty">
              <Scan :size="16" class="empty-icon" />
            </div>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- VNC view (browser, browser_agent, browsing) -->
    <div v-else-if="currentViewType === 'vnc' && sessionId && enabled" class="vnc-container">
      <VNCViewer
        :session-id="sessionId"
        :enabled="enabled"
        :view-only="true"
      />
    </div>

    <!-- Generic tool indicator (fallback when no session or unknown tool) -->
    <div v-else class="tool-preview">
      <div class="tool-preview-content">
        <component :is="toolIcon" class="tool-preview-icon" />
        <span class="tool-preview-label">{{ toolLabel }}</span>
      </div>
      <div v-if="isActive" class="activity-pulse"></div>
    </div>

    <!-- Hover overlay -->
    <div class="hover-overlay">
      <Monitor class="hover-icon" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue';
import { Monitor, Terminal, FileText, Globe, Code, Wrench, Search, Loader2, GitBranch, TestTube, Wand2, Download, Presentation, FolderTree, Calendar, Scan, CheckCircle, XCircle, AlertCircle } from 'lucide-vue-next';
import VNCViewer from '@/components/VNCViewer.vue';
import WideResearchMiniPreview from '@/components/WideResearchMiniPreview.vue';
import { useContentConfig } from '@/composables/useContentConfig';
import { useWideResearchGlobal } from '@/composables/useWideResearch';
import type { ToolContent } from '@/types/message';

const props = withDefaults(defineProps<{
  sessionId?: string;
  enabled?: boolean;
  size?: 'sm' | 'md' | 'lg';
  toolName?: string;
  toolFunction?: string;
  isActive?: boolean;
  /** Content to preview (file content, terminal output, etc.) */
  contentPreview?: string;
  /** File path for file operations */
  filePath?: string;
  /** Whether the sandbox environment is initializing */
  isInitializing?: boolean;
  /** Search results for search/info tools */
  searchResults?: Array<{ title?: string; name?: string; url?: string; link?: string; snippet?: string }>;
  /** Search query for search/info tools */
  searchQuery?: string;
  /** Generic result for MCP/generic tools */
  genericResult?: unknown;
  /** Full tool content for content config */
  toolContent?: ToolContent;
  /** Git operation info */
  gitInfo?: { operation?: string; branch?: string; output?: string };
  /** Test results */
  testResults?: { total?: number; passed?: number; failed?: number; skipped?: number };
  /** Skill info */
  skillInfo?: { name?: string; status?: string };
  /** Export info */
  exportInfo?: { format?: string; filename?: string };
  /** Slides info */
  slidesInfo?: { title?: string; count?: number };
  /** Workspace info */
  workspaceInfo?: { type?: string; filesCount?: number };
  /** Schedule info */
  scheduleInfo?: { time?: string; status?: string };
  /** Scan info */
  scanInfo?: { type?: string; findingsCount?: number };
}>(), {
  enabled: true,
  size: 'md',
  toolName: '',
  toolFunction: '',
  isActive: false,
  contentPreview: '',
  filePath: '',
  isInitializing: false,
  searchResults: () => [],
  searchQuery: '',
  genericResult: undefined,
  toolContent: undefined,
  gitInfo: undefined,
  testResults: undefined,
  skillInfo: undefined,
  exportInfo: undefined,
  slidesInfo: undefined,
  workspaceInfo: undefined,
  scheduleInfo: undefined,
  scanInfo: undefined
});

const emit = defineEmits<{
  click: [];
}>();

// Build a minimal toolContent object if not provided
const effectiveToolContent = computed<ToolContent | undefined>(() => {
  if (props.toolContent) return props.toolContent;
  if (!props.toolName) return undefined;
  return {
    name: props.toolName,
    function: props.toolFunction,
    args: {},
    content: props.genericResult,
    status: props.isActive ? 'calling' : 'completed'
  } as ToolContent;
});

// Use content config to determine view type
const { currentViewType } = useContentConfig(toRef(() => effectiveToolContent.value));

// Wide research state
const { miniState: wideResearchState, isActive: wideResearchActive } = useWideResearchGlobal();

// Check if this is a wide research tool
const isWideResearch = computed(() => {
  const toolName = props.toolName?.toLowerCase() || '';
  const toolFunc = props.toolFunction?.toLowerCase() || '';
  return (toolName.includes('wide_research') || toolFunc.includes('wide_research')) && wideResearchActive.value;
});

// Helper to truncate text
const truncate = (text: string, maxLength: number): string => {
  if (!text) return '';
  return text.length > maxLength ? text.slice(0, maxLength - 3) + '...' : text;
};

// Convert generic result to displayable text
const genericResultText = computed(() => {
  if (!props.genericResult) return '';
  if (typeof props.genericResult === 'string') return props.genericResult;
  try {
    return JSON.stringify(props.genericResult, null, 2);
  } catch {
    return String(props.genericResult);
  }
});

// Get favicon URL for a given link using Google's favicon service
const getFavicon = (link: string): string => {
  if (!link) return '';
  try {
    const url = new URL(link);
    return `https://www.google.com/s2/favicons?domain=${url.hostname}&sz=32`;
  } catch {
    return '';
  }
};

// Handle favicon load error by hiding the image
const handleFaviconError = (event: Event) => {
  const img = event.target as HTMLImageElement;
  img.style.visibility = 'hidden';
};

// Extract filename from path
const fileName = computed(() => {
  if (!props.filePath) return 'File';
  const parts = props.filePath.split('/');
  const name = parts[parts.length - 1] || 'File';
  // Truncate long names
  return name.length > 20 ? name.slice(0, 17) + '...' : name;
});

// Terminal title from content or default
const terminalTitle = computed(() => {
  // Try to extract a meaningful title from the terminal session name
  const preview = props.contentPreview || '';
  // Look for common shell session names in first line
  const match = preview.match(/^setup_env|^[a-z_]+@[a-z]+:/i);
  if (match) return match[0].replace(/:$/, '');
  return 'Terminal';
});

// Style terminal content with green prompts (ubuntu@sandbox:~ $)
const styledTerminalContent = computed(() => {
  const content = props.contentPreview || '';
  // Escape HTML first
  const escaped = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Style shell prompts in green (matches patterns like "ubuntu@sandbox:~ $" or "user@host:/path $")
  const styled = escaped.replace(
    /^(\s*)([a-z_][a-z0-9_-]*@[a-z0-9_-]+:[^$#]*[$#])/gim,
    '$1<span class="shell-prompt">$2</span>'
  );

  return styled;
});

// Git operation label
const gitOperationLabel = computed(() => {
  const func = props.toolFunction || '';
  if (func.includes('clone')) return 'Cloning';
  if (func.includes('status')) return 'Status';
  if (func.includes('diff')) return 'Diff';
  if (func.includes('log')) return 'Log';
  if (func.includes('branch')) return 'Branches';
  return 'Git';
});

// Get appropriate icon for fallback
const toolIcon = computed(() => {
  const name = props.toolName || '';
  const func = props.toolFunction || '';

  if (name.includes('browser') || name.includes('web')) return Globe;
  if (name.includes('playwright')) return Globe;
  if (name.includes('file') || func.includes('file')) return FileText;
  if (name.includes('shell') || func.includes('shell')) return Terminal;
  if (name.includes('search') || name.includes('info')) return Search;
  if (name.includes('code') || func.includes('code')) return Code;
  if (name.includes('mcp')) return Wrench;
  if (name.includes('git')) return GitBranch;
  if (name.includes('test')) return TestTube;
  if (name.includes('skill')) return Wand2;
  if (name.includes('export')) return Download;
  if (name.includes('slide')) return Presentation;
  if (name.includes('workspace') || name.includes('repo_map')) return FolderTree;
  if (name.includes('schedule')) return Calendar;
  if (name.includes('scan') || name.includes('analyz')) return Scan;
  return Monitor;
});

// Get label for fallback
const toolLabel = computed(() => {
  const func = props.toolFunction || '';

  if (func.includes('file_write')) return 'Writing';
  if (func.includes('file_read')) return 'Reading';
  if (func.includes('shell') || func.includes('exec')) return 'Terminal';
  if (func.includes('browser')) return 'Browser';
  if (func.includes('search')) return 'Search';
  if (func.includes('code')) return 'Code';

  return props.toolName || 'Working';
});

const sizeClass = computed(() => {
  switch (props.size) {
    case 'sm': return 'size-sm';
    case 'lg': return 'size-lg';
    default: return 'size-md';
  }
});
</script>

<style scoped>
.vnc-mini-preview {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  background: var(--bolt-elements-bg-depth-2);
  border: 1px solid var(--bolt-elements-borderColor);
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px var(--shadow-XS);
  aspect-ratio: 16 / 10;
}

.vnc-mini-preview:hover {
  transform: scale(1.02);
  border-color: var(--bolt-elements-borderColorActive);
  box-shadow: 0 4px 16px var(--shadow-S);
}

/* Size variants */
.size-sm { width: 96px; }
.size-md { width: 144px; }
.size-lg { width: 176px; }

@media (max-width: 640px) {
  .size-sm { width: 72px; }
  .size-md { width: 112px; }
  .size-lg { width: 136px; }
}

/* VNC Container */
.vnc-container {
  position: absolute;
  inset: 0;
  background: var(--bolt-elements-bg-depth-2);
}

/* Content Preview (File/Terminal) */
.content-preview {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.file-preview {
  background: var(--bolt-elements-bg-depth-1);
}

/* Decorated file window */
.file-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bolt-elements-bg-depth-1);
  border-radius: 6px;
  overflow: hidden;
}

.file-header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 8px;
  background: var(--bolt-elements-bg-depth-2);
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  flex-shrink: 0;
}

.file-title {
  font-size: 8px;
  font-weight: 500;
  color: var(--bolt-elements-textPrimary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.file-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.file-accent {
  width: 2px;
  background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%);
  flex-shrink: 0;
}

.file-content-area {
  flex: 1;
  padding: 4px 6px;
  overflow: hidden;
  background: var(--bolt-elements-bg-depth-1);
}

.terminal-preview {
  background: var(--bolt-elements-bg-depth-1);
}

/* ===== Search Preview ===== */
.search-preview {
  background: var(--bolt-elements-bg-depth-2);
}

.search-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bolt-elements-bg-depth-2);
  border-radius: 6px;
  overflow: hidden;
}

.search-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 3px 6px;
  background: var(--bolt-elements-bg-depth-3);
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  flex-shrink: 0;
}

.search-header-icon {
  color: #6366f1;
  flex-shrink: 0;
}

.search-title {
  font-size: 7px;
  font-weight: 500;
  color: var(--bolt-elements-textPrimary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 85%;
}

.search-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.search-content-area {
  flex: 1;
  padding: 3px 4px;
  overflow: hidden;
  background: var(--bolt-elements-bg-depth-2);
}

.search-results-mini {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.search-result-item {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  padding: 3px 4px;
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  overflow: hidden;
}

.search-result-item:last-child {
  border-bottom: none;
}

.result-favicon {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  margin-top: 1px;
  border-radius: 2px;
}

.result-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  flex: 1;
}

.result-title {
  font-size: 6px;
  font-weight: 600;
  color: var(--bolt-elements-textPrimary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
  line-height: 1.3;
}

.result-snippet {
  font-size: 5px;
  color: var(--bolt-elements-textSecondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
  line-height: 1.2;
}

.results-more {
  font-size: 5px;
  color: var(--bolt-elements-textTertiary);
  text-align: center;
  padding: 2px 0;
}

.search-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 4px;
}

.loading-dots {
  display: flex;
  gap: 3px;
}

.loading-dots .dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #6366f1;
  animation: bounce 1.4s infinite ease-in-out both;
}

.loading-dots .dot:nth-child(1) { animation-delay: -0.32s; }
.loading-dots .dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.loading-text {
  font-size: 6px;
  color: var(--bolt-elements-textSecondary);
}

.search-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 3px;
  font-size: 6px;
  color: var(--bolt-elements-textTertiary);
}

.empty-search-icon {
  color: var(--bolt-elements-textTertiary);
}

/* ===== Generic/MCP Preview ===== */
.generic-preview {
  background: var(--bolt-elements-bg-depth-1);
}

.generic-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bolt-elements-bg-depth-1);
  border-radius: 6px;
  overflow: hidden;
}

.generic-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 4px 8px;
  background: var(--bolt-elements-bg-depth-2);
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  flex-shrink: 0;
}

.generic-header-icon {
  color: #8b5cf6;
  flex-shrink: 0;
}

.generic-title {
  font-size: 7px;
  font-weight: 500;
  color: var(--bolt-elements-textPrimary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 80%;
}

.generic-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.generic-accent {
  width: 2px;
  background: linear-gradient(180deg, #8b5cf6 0%, #7c3aed 100%);
  flex-shrink: 0;
}

.generic-content-area {
  flex: 1;
  padding: 4px 6px;
  overflow: hidden;
  background: var(--bolt-elements-bg-depth-1);
}

.generic-result-mini {
  height: 100%;
  overflow: hidden;
}

.generic-result-mini .preview-text {
  font-size: 5px;
  line-height: 1.2;
}

.generic-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 4px;
}

.loading-spinner {
  color: #8b5cf6;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.generic-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.empty-icon {
  width: 16px;
  height: 16px;
  color: var(--bolt-elements-textTertiary);
}

/* Decorated terminal window */
.terminal-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bolt-elements-bg-depth-1);
  border-radius: 6px;
  overflow: hidden;
}

.terminal-header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 8px;
  background: var(--bolt-elements-bg-depth-2);
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  flex-shrink: 0;
}

.terminal-title {
  font-size: 8px;
  font-weight: 500;
  color: var(--bolt-elements-textPrimary);
}

.terminal-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.terminal-accent {
  width: 2px;
  background: linear-gradient(180deg, #f97316 0%, #ea580c 100%);
  flex-shrink: 0;
}

.terminal-content-area {
  flex: 1;
  padding: 4px 6px;
  overflow: hidden;
  background: var(--bolt-elements-bg-depth-1);
}

.terminal-content-area.terminal-running {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.running-icon {
  width: 16px;
  height: 16px;
  color: #f97316;
  animation: pulse 1.5s ease-in-out infinite;
}

.running-text {
  font-size: 7px;
  font-weight: 500;
  color: var(--bolt-elements-textSecondary);
}

.preview-text {
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
  font-size: 6px;
  line-height: 1.4;
  color: var(--bolt-elements-textPrimary);
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.terminal-text {
  color: var(--bolt-elements-textPrimary);
  font-size: 5px;
  line-height: 1.3;
}

/* Green shell prompt (ubuntu@sandbox:~ $) */
.terminal-text :deep(.shell-prompt) {
  color: #16a34a;
  font-weight: 500;
}

/* Activity indicator */
.activity-indicator {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 6px;
  height: 6px;
  background: #3b82f6;
  border-radius: 50%;
  animation: pulse 1.5s ease-in-out infinite;
}

/* Tool Preview (fallback) */
.tool-preview {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bolt-elements-bg-depth-2);
}

.tool-preview-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.tool-preview-icon {
  width: 24px;
  height: 24px;
  color: var(--bolt-elements-textSecondary);
}

.tool-preview-label {
  font-size: 10px;
  font-weight: 500;
  color: var(--bolt-elements-textSecondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.activity-pulse {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 8px;
  height: 8px;
  background: #3b82f6;
  border-radius: 50%;
  animation: pulse 1.5s ease-in-out infinite;
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.6);
}

@keyframes pulse {
  0%, 100% { opacity: 0.6; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

/* ===== Initialization State ===== */
.init-preview {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bolt-elements-bg-depth-2);
  overflow: hidden;
}

.init-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  z-index: 2;
}

.init-monitor {
  position: relative;
}

.monitor-frame {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.monitor-screen {
  width: 28px;
  height: 20px;
  background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
  border-radius: 3px;
  border: 2px solid #475569;
  position: relative;
  overflow: hidden;
  box-shadow:
    inset 0 0 8px rgba(59, 130, 246, 0.15),
    0 2px 8px rgba(0, 0, 0, 0.15);
}

.scan-line {
  position: absolute;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg,
    transparent 0%,
    rgba(59, 130, 246, 0.4) 20%,
    rgba(59, 130, 246, 0.6) 50%,
    rgba(59, 130, 246, 0.4) 80%,
    transparent 100%
  );
  animation: scan 1.8s ease-in-out infinite;
}

@keyframes scan {
  0% { top: -2px; opacity: 0; }
  10% { opacity: 1; }
  90% { opacity: 1; }
  100% { top: calc(100% + 2px); opacity: 0; }
}

.boot-dots {
  position: absolute;
  bottom: 3px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 3px;
}

.boot-dot {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: #3b82f6;
  animation: boot-pulse 1.2s ease-in-out infinite;
}

.boot-dot:nth-child(2) { animation-delay: 0.2s; }
.boot-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes boot-pulse {
  0%, 100% {
    opacity: 0.3;
    transform: scale(0.8);
    box-shadow: 0 0 0 0 rgba(59, 130, 246, 0);
  }
  50% {
    opacity: 1;
    transform: scale(1);
    box-shadow: 0 0 4px 1px rgba(59, 130, 246, 0.4);
  }
}

.monitor-stand {
  width: 8px;
  height: 4px;
  background: linear-gradient(180deg, #64748b 0%, #475569 100%);
  border-radius: 0 0 2px 2px;
  margin-top: -1px;
}

.init-label {
  font-family: 'SF Mono', Monaco, 'Cascadia Code', ui-monospace, monospace;
  font-size: 8px;
  font-weight: 500;
  color: var(--bolt-elements-textSecondary);
  letter-spacing: 0.5px;
  text-transform: uppercase;
}

.init-ellipsis::after {
  content: '';
  animation: ellipsis 1.5s steps(4, end) infinite;
}

@keyframes ellipsis {
  0% { content: ''; }
  25% { content: '.'; }
  50% { content: '..'; }
  75% { content: '...'; }
  100% { content: ''; }
}

.init-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(71, 85, 105, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(71, 85, 105, 0.03) 1px, transparent 1px);
  background-size: 8px 8px;
  pointer-events: none;
}

/* Dark mode for init state - only animation-specific overrides */

/* Hover overlay */
.hover-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(2px);
  opacity: 0;
  transition: opacity 0.2s ease;
  z-index: 10;
}

.vnc-mini-preview:hover .hover-overlay {
  opacity: 1;
}

.hover-icon {
  width: 20px;
  height: 20px;
  color: white;
}

/* Dark mode - handled by CSS variables, only accent overrides needed */

/* ===== Unified Tool Card Styles (for git, test, skill, export, slides, workspace, schedule, scan) ===== */
.tool-card-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bolt-elements-bg-depth-1);
  border-radius: 6px;
  overflow: hidden;
}

.tool-card-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 4px 8px;
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  flex-shrink: 0;
}

.tool-card-header-icon {
  flex-shrink: 0;
}

.tool-card-title {
  font-size: 7px;
  font-weight: 500;
  color: var(--bolt-elements-textPrimary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 80%;
}

.tool-card-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.tool-card-accent {
  width: 2px;
  flex-shrink: 0;
}

.tool-card-content-area {
  flex: 1;
  padding: 4px 6px;
  overflow: hidden;
  background: var(--bolt-elements-bg-depth-1);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.tool-card-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 4px;
}

.tool-card-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

/* Git preview */
.git-preview { background: var(--bolt-elements-bg-depth-1); }
.git-header { background: #fef3c7; }
.git-header .tool-card-header-icon { color: #d97706; }
.git-accent { background: linear-gradient(180deg, #f59e0b 0%, #d97706 100%); }

.git-branch-badge {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  background: var(--fill-tsp-white-main);
  border-radius: 4px;
  font-size: 6px;
  color: var(--bolt-elements-textSecondary);
}

.git-output {
  width: 100%;
  overflow: hidden;
}

.git-output .preview-text {
  font-size: 5px;
  line-height: 1.2;
}

/* Test preview */
.test-preview { background: var(--bolt-elements-bg-depth-1); }
.test-header { background: #ecfdf5; }
.test-header .tool-card-header-icon { color: #059669; }
.test-accent { background: linear-gradient(180deg, #10b981 0%, #059669 100%); }

.test-results-mini {
  display: flex;
  gap: 8px;
  align-items: center;
}

.test-stat {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 8px;
  font-weight: 600;
}

.test-stat.passed { color: #059669; }
.test-stat.failed { color: #dc2626; }
.test-stat.skipped { color: var(--bolt-elements-textTertiary); }

/* Skill preview */
.skill-preview { background: var(--bolt-elements-bg-depth-1); }
.skill-header { background: #faf5ff; }
.skill-header .tool-card-header-icon { color: #7c3aed; }
.skill-accent { background: linear-gradient(180deg, #8b5cf6 0%, #7c3aed 100%); }

.skill-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.skill-icon { color: #7c3aed; }
.skill-status-text { font-size: 7px; color: var(--bolt-elements-textSecondary); }

/* Export preview */
.export-preview { background: var(--bolt-elements-bg-depth-1); }
.export-header { background: #eff6ff; }
.export-header .tool-card-header-icon { color: #2563eb; }
.export-accent { background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%); }

.export-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.export-icon { color: #2563eb; }
.export-filename { font-size: 7px; color: var(--bolt-elements-textPrimary); }
.export-format { font-size: 6px; color: var(--bolt-elements-textTertiary); }

/* Slides preview */
.slides-preview { background: var(--bolt-elements-bg-depth-1); }
.slides-header { background: #fff7ed; }
.slides-header .tool-card-header-icon { color: #ea580c; }
.slides-accent { background: linear-gradient(180deg, #f97316 0%, #ea580c 100%); }

.slides-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.slides-icon { color: #ea580c; }
.slides-count { font-size: 7px; color: var(--bolt-elements-textPrimary); }

/* Workspace preview */
.workspace-preview { background: var(--bolt-elements-bg-depth-1); }
.workspace-header { background: #f0fdf4; }
.workspace-header .tool-card-header-icon { color: #16a34a; }
.workspace-accent { background: linear-gradient(180deg, #22c55e 0%, #16a34a 100%); }

.workspace-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.workspace-icon { color: #16a34a; }
.workspace-count { font-size: 7px; color: var(--bolt-elements-textPrimary); }

/* Schedule preview */
.schedule-preview { background: var(--bolt-elements-bg-depth-1); }
.schedule-header { background: #fdf4ff; }
.schedule-header .tool-card-header-icon { color: #c026d3; }
.schedule-accent { background: linear-gradient(180deg, #d946ef 0%, #c026d3 100%); }

.schedule-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.schedule-icon { color: #c026d3; }
.schedule-time { font-size: 7px; color: var(--bolt-elements-textPrimary); }

/* Scan preview */
.scan-preview { background: var(--bolt-elements-bg-depth-1); }
.scan-header { background: #fef2f2; }
.scan-header .tool-card-header-icon { color: #dc2626; }
.scan-accent { background: linear-gradient(180deg, #ef4444 0%, #dc2626 100%); }

.scan-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.scan-icon { color: #dc2626; }
.scan-count { font-size: 7px; color: var(--bolt-elements-textPrimary); }

/* Dark mode for tool card accent headers */
:global(.dark) .git-header { background: rgba(217, 119, 6, 0.15); }
:global(.dark) .test-header { background: rgba(5, 150, 105, 0.15); }
:global(.dark) .skill-header { background: rgba(124, 58, 237, 0.15); }
:global(.dark) .export-header { background: rgba(37, 99, 235, 0.15); }
:global(.dark) .slides-header { background: rgba(234, 88, 12, 0.15); }
:global(.dark) .workspace-header { background: rgba(22, 163, 74, 0.15); }
:global(.dark) .schedule-header { background: rgba(192, 38, 211, 0.15); }
:global(.dark) .scan-header { background: rgba(220, 38, 38, 0.15); }

</style>
