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

    <!-- File content preview -->
    <div v-else-if="isFileTool && contentPreview" class="content-preview file-preview">
      <div class="preview-header">
        <FileText class="preview-header-icon" />
        <span class="preview-filename">{{ fileName }}</span>
      </div>
      <div class="preview-content">
        <pre class="preview-text">{{ contentPreview }}</pre>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Terminal output preview -->
    <div v-else-if="isShellTool && contentPreview" class="content-preview terminal-preview">
      <div class="preview-header">
        <Terminal class="preview-header-icon" />
        <span class="preview-filename">Terminal</span>
      </div>
      <div class="preview-content terminal-content">
        <pre class="preview-text terminal-text">{{ contentPreview }}</pre>
      </div>
      <div v-if="isActive" class="activity-indicator"></div>
    </div>

    <!-- Generic tool indicator (fallback) -->
    <div v-else class="tool-preview">
      <div class="tool-preview-content">
        <component :is="toolIcon" class="tool-preview-icon" />
        <span class="tool-preview-label">{{ toolLabel }}</span>
      </div>
      <div v-if="isActive" class="activity-pulse"></div>
    </div>

    <!-- Expand icon on hover -->
    <button class="expand-btn" @click.stop="emit('click')">
      <Maximize2 class="expand-icon" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Maximize2, Monitor, Terminal, FileText, Globe, Search, Code, Wrench } from 'lucide-vue-next';
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
  background: #1a1a1a;
  border: 1px solid var(--bolt-elements-borderColor);
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  aspect-ratio: 16 / 10;
}

.vnc-mini-preview:hover {
  transform: scale(1.02);
  border-color: var(--bolt-elements-borderColorActive);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
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
  background: #282828;
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
  background: #1e1e1e;
}

.terminal-preview {
  background: #0d1117;
}

.preview-header {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  background: rgba(0, 0, 0, 0.3);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
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
  color: #94a3b8;
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
  color: #e2e8f0;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.terminal-content {
  background: #0d1117;
}

.terminal-text {
  color: #7ee787;
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
  background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);
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
  color: #94a3b8;
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

/* Expand button */
.expand-btn {
  position: absolute;
  bottom: 4px;
  right: 4px;
  width: 22px;
  height: 22px;
  border-radius: 5px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  color: white;
  opacity: 0;
  transition: opacity 0.15s ease;
  border: none;
  cursor: pointer;
  z-index: 10;
}

.expand-icon {
  width: 12px;
  height: 12px;
}

.vnc-mini-preview:hover .expand-btn {
  opacity: 1;
}

.expand-btn:hover {
  background: rgba(0, 0, 0, 0.8);
}

/* Dark mode */
:global(.dark) .vnc-mini-preview {
  border-color: rgba(255, 255, 255, 0.1);
}
</style>
