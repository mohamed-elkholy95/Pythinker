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

    <!-- Terminal output preview - prioritize over VNC to show actual command output -->
    <div v-else-if="isShellTool && contentPreview" class="content-preview terminal-preview">
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

    <!-- Shell tool running without content yet - show VNC to see terminal activity -->
    <div v-else-if="isShellTool && isActive && sessionId && enabled" class="vnc-container">
      <VNCViewer
        :session-id="sessionId"
        :enabled="enabled"
        :view-only="true"
      />
    </div>

    <!-- Live VNC for visual tools (browser, search, etc.) -->
    <div v-else-if="isVisualTool && sessionId && enabled" class="vnc-container">
      <VNCViewer
        :session-id="sessionId"
        :enabled="enabled"
        :view-only="true"
      />
    </div>

    <!-- File content preview (decorated window style) -->
    <div v-else-if="isFileTool && contentPreview" class="content-preview file-preview">
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

    <!-- Default: Show VNC for any tool when session is available -->
    <div v-else-if="sessionId && enabled" class="vnc-container">
      <VNCViewer
        :session-id="sessionId"
        :enabled="enabled"
        :view-only="true"
      />
    </div>

    <!-- Generic tool indicator (fallback when no session) -->
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
import { computed } from 'vue';
import { Monitor, Terminal, FileText, Globe, Code, Wrench } from 'lucide-vue-next';
import VNCViewer from '@/components/VNCViewer.vue';

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
}>(), {
  enabled: true,
  size: 'md',
  toolName: '',
  toolFunction: '',
  isActive: false,
  contentPreview: '',
  filePath: '',
  isInitializing: false
});

const emit = defineEmits<{
  click: [];
}>();

// Tool type detection - tools that show live VNC preview
// Shell tools are handled separately to prioritize terminal content preview
const VISUAL_TOOLS = ['browser', 'browser_agent', 'info', 'search'];

const isVisualTool = computed(() => {
  if (!props.toolName) return false;
  return VISUAL_TOOLS.some(t => props.toolName?.includes(t));
});

const isFileTool = computed(() => {
  const name = props.toolName || '';
  const func = props.toolFunction || '';
  return name.includes('file') || func.includes('file');
});

const isShellTool = computed(() => {
  const name = props.toolName || '';
  const func = props.toolFunction || '';
  return name.includes('shell') || func.includes('shell') || func.includes('exec');
});

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
</style>
