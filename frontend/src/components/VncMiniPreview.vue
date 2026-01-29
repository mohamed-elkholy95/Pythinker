<template>
  <div
    class="vnc-mini-preview"
    :class="sizeClass"
    @click="emit('click')"
  >
    <!-- Live VNC for browser tools -->
    <div v-if="isVisualTool && sessionId && enabled" class="vnc-container">
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

    <!-- Terminal output preview (decorated window style) -->
    <div v-else-if="isShellTool && contentPreview" class="content-preview terminal-preview">
      <div class="terminal-window">
        <div class="terminal-header">
          <span class="terminal-title">Terminal</span>
        </div>
        <div class="terminal-body">
          <div class="terminal-accent"></div>
          <div class="terminal-content-area">
            <pre class="preview-text terminal-text">{{ contentPreview }}</pre>
          </div>
        </div>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Shell tool running without content yet -->
    <div v-else-if="isShellTool && isActive" class="content-preview terminal-preview">
      <div class="terminal-window">
        <div class="terminal-header">
          <span class="terminal-title">Terminal</span>
        </div>
        <div class="terminal-body">
          <div class="terminal-accent"></div>
          <div class="terminal-content-area terminal-running">
            <Terminal class="running-icon" />
            <span class="running-text">Running...</span>
          </div>
        </div>
      </div>
      <div class="activity-indicator"></div>
    </div>

    <!-- Generic tool indicator (fallback) -->
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
      <span class="hover-text">View Pythinker Computer</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Monitor, Terminal, FileText, Globe, Search, Code, Wrench } from 'lucide-vue-next';
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
}>(), {
  enabled: true,
  size: 'md',
  toolName: '',
  toolFunction: '',
  isActive: false,
  contentPreview: '',
  filePath: ''
});

const emit = defineEmits<{
  click: [];
}>();

// Tool type detection
const VISUAL_TOOLS = ['browser', 'browser_agent'];

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

// Get appropriate icon for fallback
const toolIcon = computed(() => {
  const name = props.toolName || '';
  const func = props.toolFunction || '';

  if (name.includes('browser') || name.includes('web')) return Globe;
  if (name.includes('file') || func.includes('file')) return FileText;
  if (name.includes('shell') || func.includes('shell')) return Terminal;
  if (name.includes('search') || name.includes('info')) return Search;
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

.preview-header {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  background: rgba(0, 0, 0, 0.05);
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
}

.preview-header-icon {
  width: 10px;
  height: 10px;
  color: #64748b;
  flex-shrink: 0;
}

.preview-filename {
  font-size: 8px;
  font-weight: 500;
  color: #475569;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preview-content {
  flex: 1;
  overflow: hidden;
  padding: 4px 6px;
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

.hover-text {
  font-size: 9px;
  font-weight: 500;
  color: white;
  text-align: center;
  padding: 0 8px;
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

:global(.dark) .preview-header {
  background: rgba(0, 0, 0, 0.3);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

:global(.dark) .preview-filename {
  color: #94a3b8;
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
