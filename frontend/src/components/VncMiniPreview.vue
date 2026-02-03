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

    <!-- Content fetched success state (text-only operations like browser_get_content) -->
    <div v-else-if="isTextOnlyCompleted" class="content-preview content-fetched-preview">
      <div class="content-fetched-window">
        <div class="content-fetched-body">
          <div class="content-fetched-icon">
            <svg class="check-icon" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="1.5" class="check-circle" />
              <path d="M7 12.5l3 3 7-7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-mark" />
            </svg>
          </div>
          <span class="content-fetched-label">Content fetched</span>
          <span v-if="contentFetchedDetail" class="content-fetched-detail">{{ contentFetchedDetail }}</span>
        </div>
      </div>
    </div>

    <!-- Text-only operation loading state (fetching content) -->
    <div v-else-if="isTextOnlyOperation && props.isActive" class="content-preview content-fetching-preview">
      <div class="content-fetching-window">
        <div class="content-fetching-body">
          <div class="content-fetching-icon">
            <Globe :size="18" class="globe-spinning" />
          </div>
          <span class="content-fetching-label">Fetching content<span class="fetching-dots"></span></span>
          <span v-if="contentFetchedDetail" class="content-fetching-detail">{{ contentFetchedDetail }}</span>
        </div>
      </div>
      <div class="activity-indicator"></div>
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
import { Monitor, Terminal, FileText, Globe, Code, Wrench, Search, Loader2 } from 'lucide-vue-next';
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
  toolContent: undefined
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
const { currentViewType, isTextOnlyOperation } = useContentConfig(toRef(() => effectiveToolContent.value));

// Wide research state
const { miniState: wideResearchState, isActive: wideResearchActive } = useWideResearchGlobal();

// Check if this is a wide research tool
const isWideResearch = computed(() => {
  const toolName = props.toolName?.toLowerCase() || '';
  const toolFunc = props.toolFunction?.toLowerCase() || '';
  return (toolName.includes('wide_research') || toolFunc.includes('wide_research')) && wideResearchActive.value;
});

// Check if this is a completed text-only operation (show "Content fetched" state)
const isTextOnlyCompleted = computed(() => {
  return isTextOnlyOperation.value && !props.isActive;
});

// Get URL detail for content fetched display
const contentFetchedDetail = computed(() => {
  const args = props.toolContent?.args || effectiveToolContent.value?.args || {};
  if (args.url) {
    try {
      const u = new URL(args.url);
      const path = u.pathname.length > 25 ? u.pathname.slice(0, 22) + '...' : u.pathname;
      return u.hostname + path;
    } catch {
      return args.url.slice(0, 35) + (args.url.length > 35 ? '...' : '');
    }
  }
  return '';
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

// Get appropriate icon for fallback
const toolIcon = computed(() => {
  const name = props.toolName || '';
  const func = props.toolFunction || '';

  if (name.includes('browser') || name.includes('web')) return Globe;
  if (name.includes('file') || func.includes('file')) return FileText;
  if (name.includes('shell') || func.includes('shell')) return Terminal;
  if (name.includes('search') || name.includes('info')) return Globe;
  if (name.includes('code') || func.includes('code')) return Code;
  if (name.includes('mcp')) return Wrench;
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
  background: #f8fafc;
  border: 1px solid var(--bolt-elements-borderColor);
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  aspect-ratio: 16 / 10;
}

.vnc-mini-preview:hover {
  transform: scale(1.02);
  border-color: var(--bolt-elements-borderColorActive);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
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
  background: #f1f5f9;
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
  background: #ffffff;
}

/* Decorated file window */
.file-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #ffffff;
  border-radius: 6px;
  overflow: hidden;
}

.file-header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 8px;
  background: #fafafa;
  border-bottom: 1px solid #e5e5e5;
  flex-shrink: 0;
}

.file-title {
  font-size: 8px;
  font-weight: 500;
  color: #374151;
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
  background: #ffffff;
}

.terminal-preview {
  background: #ffffff;
}

/* ===== Search Preview ===== */
.search-preview {
  background: #f5f5f4;
}

.search-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f5f5f4;
  border-radius: 6px;
  overflow: hidden;
}

.search-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 3px 6px;
  background: #ebebea;
  border-bottom: 1px solid #e0e0df;
  flex-shrink: 0;
}

.search-header-icon {
  color: #6366f1;
  flex-shrink: 0;
}

.search-title {
  font-size: 7px;
  font-weight: 500;
  color: #374151;
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
  background: #f5f5f4;
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
  border-bottom: 1px solid #e5e5e5;
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
  color: #1a1a1a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
  line-height: 1.3;
}

.result-snippet {
  font-size: 5px;
  color: #6b6b6b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
  line-height: 1.2;
}

.results-more {
  font-size: 5px;
  color: #9a9a9a;
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
  color: #6b7280;
}

.search-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 3px;
  font-size: 6px;
  color: #9ca3af;
}

.empty-search-icon {
  color: #d1d5db;
}

/* ===== Generic/MCP Preview ===== */
.generic-preview {
  background: #ffffff;
}

.generic-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #ffffff;
  border-radius: 6px;
  overflow: hidden;
}

.generic-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 4px 8px;
  background: #fafafa;
  border-bottom: 1px solid #e5e5e5;
  flex-shrink: 0;
}

.generic-header-icon {
  color: #8b5cf6;
  flex-shrink: 0;
}

.generic-title {
  font-size: 7px;
  font-weight: 500;
  color: #374151;
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
  background: #ffffff;
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
  color: #9ca3af;
}

/* Decorated terminal window */
.terminal-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #ffffff;
  border-radius: 6px;
  overflow: hidden;
}

.terminal-header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 8px;
  background: #fafafa;
  border-bottom: 1px solid #e5e5e5;
  flex-shrink: 0;
}

.terminal-title {
  font-size: 8px;
  font-weight: 500;
  color: #374151;
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
  background: #ffffff;
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
  color: #6b7280;
}

.preview-text {
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
  font-size: 6px;
  line-height: 1.4;
  color: #1e293b;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.terminal-text {
  color: #1f2937;
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
  background: linear-gradient(145deg, #f8fafc 0%, #e2e8f0 100%);
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
  color: #64748b;
}

.tool-preview-label {
  font-size: 10px;
  font-weight: 500;
  color: #64748b;
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
  background: linear-gradient(145deg, #f0f4f8 0%, #e2e8f0 100%);
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
  color: #475569;
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

/* Dark mode for init state */
:global(.dark) .init-preview {
  background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);
}

:global(.dark) .monitor-screen {
  background: linear-gradient(180deg, #0f172a 0%, #020617 100%);
  border-color: #334155;
  box-shadow:
    inset 0 0 12px rgba(59, 130, 246, 0.2),
    0 2px 8px rgba(0, 0, 0, 0.4);
}

:global(.dark) .scan-line {
  background: linear-gradient(90deg,
    transparent 0%,
    rgba(96, 165, 250, 0.3) 20%,
    rgba(96, 165, 250, 0.5) 50%,
    rgba(96, 165, 250, 0.3) 80%,
    transparent 100%
  );
}

:global(.dark) .boot-dot {
  background: #60a5fa;
}

:global(.dark) .monitor-stand {
  background: linear-gradient(180deg, #475569 0%, #334155 100%);
}

:global(.dark) .init-label {
  color: #94a3b8;
}

:global(.dark) .init-grid {
  background-image:
    linear-gradient(rgba(148, 163, 184, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.04) 1px, transparent 1px);
}

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

/* Dark mode */
:global(.dark) .vnc-mini-preview {
  background: #1a1a1a;
  border-color: rgba(255, 255, 255, 0.1);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

:global(.dark) .vnc-mini-preview:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
}

:global(.dark) .vnc-container {
  background: #282828;
}

:global(.dark) .file-preview {
  background: #1a1a1a;
}

:global(.dark) .file-window {
  background: #1a1a1a;
}

:global(.dark) .file-header {
  background: #252525;
  border-bottom: 1px solid #333333;
}

:global(.dark) .file-title {
  color: #d1d5db;
}

:global(.dark) .file-content-area {
  background: #1a1a1a;
}

:global(.dark) .terminal-preview {
  background: #1a1a1a;
}

:global(.dark) .terminal-window {
  background: #1a1a1a;
}

:global(.dark) .terminal-header {
  background: #252525;
  border-bottom: 1px solid #333333;
}

:global(.dark) .terminal-title {
  color: #d1d5db;
}

:global(.dark) .terminal-content-area {
  background: #1a1a1a;
}

:global(.dark) .running-text {
  color: #9ca3af;
}

:global(.dark) .terminal-text {
  color: #e5e7eb;
}

:global(.dark) .terminal-text :deep(.shell-prompt) {
  color: #4ade80;
}

:global(.dark) .preview-text {
  color: #e2e8f0;
}

:global(.dark) .tool-preview {
  background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);
}

:global(.dark) .tool-preview-icon {
  color: #94a3b8;
}

/* Dark mode for search preview */
:global(.dark) .search-preview {
  background: #1e1e1e;
}

:global(.dark) .search-window {
  background: #1e1e1e;
}

:global(.dark) .search-header {
  background: #2a2a2a;
  border-bottom: 1px solid #3a3a3a;
}

:global(.dark) .search-header-icon {
  color: #818cf8;
}

:global(.dark) .search-title {
  color: #d1d5db;
}

:global(.dark) .search-content-area {
  background: #1e1e1e;
}

:global(.dark) .search-result-item {
  background: transparent;
  border-bottom-color: #3a3a3a;
}

:global(.dark) .result-title {
  color: #e5e5e5;
}

:global(.dark) .result-snippet {
  color: #9a9a9a;
}

:global(.dark) .results-more {
  color: #6b6b6b;
}

:global(.dark) .loading-dots .dot {
  background: #818cf8;
}

:global(.dark) .loading-text {
  color: #9ca3af;
}

:global(.dark) .search-empty {
  color: #6b7280;
}

:global(.dark) .empty-search-icon {
  color: #4b5563;
}

/* Dark mode for generic preview */
:global(.dark) .generic-preview {
  background: #1a1a1a;
}

:global(.dark) .generic-window {
  background: #1a1a1a;
}

:global(.dark) .generic-header {
  background: #252525;
  border-bottom: 1px solid #333333;
}

:global(.dark) .generic-header-icon {
  color: #a78bfa;
}

:global(.dark) .generic-title {
  color: #d1d5db;
}

:global(.dark) .generic-content-area {
  background: #1a1a1a;
}

:global(.dark) .generic-result-mini .preview-text {
  color: #e5e7eb;
}

:global(.dark) .loading-spinner {
  color: #a78bfa;
}

:global(.dark) .empty-icon {
  color: #6b7280;
}

/* ===== Content Fetched Success State ===== */
.content-fetched-preview {
  background: #ffffff;
}

.content-fetched-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #ffffff;
  border-radius: 6px;
  overflow: hidden;
}

.content-fetched-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 4px;
  padding: 8px;
}

.content-fetched-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.content-fetched-icon .check-icon {
  width: 100%;
  height: 100%;
  color: #22c55e;
}

.content-fetched-icon .check-circle {
  opacity: 0.3;
}

.content-fetched-icon .check-mark {
  stroke-dasharray: 20;
  stroke-dashoffset: 0;
  animation: draw-check-mini 0.4s ease-out forwards;
}

@keyframes draw-check-mini {
  from {
    stroke-dashoffset: 20;
  }
  to {
    stroke-dashoffset: 0;
  }
}

.content-fetched-label {
  font-size: 8px;
  font-weight: 600;
  color: #22c55e;
  text-align: center;
}

.content-fetched-detail {
  font-size: 6px;
  color: #6b7280;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 90%;
}

:global(.dark) .content-fetched-preview {
  background: #1a1a1a;
}

:global(.dark) .content-fetched-window {
  background: #1a1a1a;
}

:global(.dark) .content-fetched-icon .check-icon {
  color: #4ade80;
}

:global(.dark) .content-fetched-label {
  color: #4ade80;
}

:global(.dark) .content-fetched-detail {
  color: #9ca3af;
}

/* ===== Content Fetching Loading State ===== */
.content-fetching-preview {
  background: #ffffff;
}

.content-fetching-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #ffffff;
  border-radius: 6px;
  overflow: hidden;
}

.content-fetching-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 4px;
  padding: 8px;
}

.content-fetching-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #3b82f6;
}

.globe-spinning {
  animation: globe-pulse 2s ease-in-out infinite;
}

@keyframes globe-pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 0.8;
  }
  50% {
    transform: scale(1.1);
    opacity: 1;
  }
}

.content-fetching-label {
  font-size: 7px;
  font-weight: 500;
  color: #3b82f6;
  text-align: center;
}

.fetching-dots::after {
  content: '';
  animation: fetching-ellipsis 1.5s steps(4, end) infinite;
}

@keyframes fetching-ellipsis {
  0% { content: ''; }
  25% { content: '.'; }
  50% { content: '..'; }
  75% { content: '...'; }
  100% { content: ''; }
}

.content-fetching-detail {
  font-size: 6px;
  color: #6b7280;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 90%;
}

:global(.dark) .content-fetching-preview {
  background: #1a1a1a;
}

:global(.dark) .content-fetching-window {
  background: #1a1a1a;
}

:global(.dark) .content-fetching-icon {
  color: #60a5fa;
}

:global(.dark) .content-fetching-label {
  color: #60a5fa;
}

:global(.dark) .content-fetching-detail {
  color: #9ca3af;
}
</style>
