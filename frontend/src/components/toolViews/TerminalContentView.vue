<template>
  <ContentContainer :scrollable="false" padding="none" class="terminal-view">
    <div class="terminal-body">
      <div class="terminal-shell" :class="{ 'dark-mode': isDarkMode }">
        <div ref="terminalRef" class="terminal-surface"></div>
        <EmptyState
          v-if="!content"
          :message="emptyLabel"
          :icon="emptyIcon"
          overlay
        />
      </div>
    </div>
  </ContentContainer>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted, nextTick } from 'vue';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
import EmptyState from '@/components/toolViews/shared/EmptyState.vue';

const props = defineProps<{
  content: string;
  contentType?: 'shell' | 'file' | 'browser' | 'code' | 'generic';
  isLive?: boolean;
  isWriting?: boolean;
  autoScroll?: boolean;
}>();

const emit = defineEmits<{
  newContent: [];
}>();

const terminalRef = ref<HTMLElement>();
const terminal = ref<Terminal | null>(null);
const fitAddon = ref<FitAddon | null>(null);
const lastContent = ref('');
const isDarkMode = ref(false);
let resizeObserver: ResizeObserver | null = null;

// Light theme (matching the decorated design)
const lightTheme = {
  background: '#ffffff',
  foreground: '#1f2937',
  cursor: '#1f2937',
  cursorAccent: '#ffffff',
  selectionBackground: 'rgba(0, 0, 0, 0.2)',
  selectionForeground: '#1f2937',
  black: '#1f2937',
  red: '#dc2626',
  green: '#16a34a',
  yellow: '#ca8a04',
  blue: '#2563eb',
  magenta: '#9333ea',
  cyan: '#0891b2',
  white: '#f8f9fa',
  brightBlack: '#6b7280',
  brightRed: '#ef4444',
  brightGreen: '#22c55e',
  brightYellow: '#eab308',
  brightBlue: '#3b82f6',
  brightMagenta: '#a855f7',
  brightCyan: '#06b6d4',
  brightWhite: '#ffffff',
};

// Dark theme
const darkTheme = {
  background: '#1a1a1a',
  foreground: '#e5e7eb',
  cursor: '#e5e7eb',
  cursorAccent: '#1a1a1a',
  selectionBackground: 'rgba(0, 0, 0, 0.3)',
  selectionForeground: '#e5e7eb',
  black: '#1f2937',
  red: '#f87171',
  green: '#4ade80',
  yellow: '#facc15',
  blue: '#60a5fa',
  magenta: '#c084fc',
  cyan: '#22d3ee',
  white: '#f8f9fa',
  brightBlack: '#9ca3af',
  brightRed: '#fca5a5',
  brightGreen: '#86efac',
  brightYellow: '#fde047',
  brightBlue: '#93c5fd',
  brightMagenta: '#d8b4fe',
  brightCyan: '#67e8f9',
  brightWhite: '#ffffff',
};

// Detect system/app dark mode
const checkDarkMode = () => {
  isDarkMode.value = document.documentElement.classList.contains('dark');
  if (terminal.value) {
    terminal.value.options.theme = isDarkMode.value ? darkTheme : lightTheme;
  }
};

// Watch for theme changes
let themeObserver: MutationObserver | null = null;

const emptyLabel = computed(() => {
  if (props.contentType === 'shell' || props.contentType === 'code') {
    return 'Waiting for output...';
  }
  if (props.contentType === 'file') {
    return props.isWriting ? 'Generating content...' : 'Reading file...';
  }
  if (props.contentType === 'browser') {
    return 'Browser activity...';
  }
  return 'No output yet...';
});

const emptyIcon = computed(() => {
  if (props.contentType === 'shell') return 'terminal';
  if (props.contentType === 'code') return 'code';
  if (props.contentType === 'file') return 'file';
  if (props.contentType === 'browser') return 'browser';
  return 'inbox';
});

const writeContent = async (nextContent: string) => {
  if (!terminal.value) return;

  const normalized = (nextContent || '').replace(/\r?\n/g, '\r\n');
  let hasNewContent = false;

  if (!lastContent.value) {
    // Initial content - write and scroll
    terminal.value.clear();
    terminal.value.write(normalized);
    lastContent.value = nextContent;
    hasNewContent = true;
  } else if (nextContent.startsWith(lastContent.value)) {
    // Delta update - append new content
    const delta = nextContent.slice(lastContent.value.length);
    if (delta) {
      terminal.value.write(delta.replace(/\r?\n/g, '\r\n'));
      hasNewContent = true;
    }
    lastContent.value = nextContent;
  } else if (nextContent !== lastContent.value) {
    // Content changed completely - rewrite but don't auto-scroll for full rewrites
    terminal.value.clear();
    terminal.value.write(normalized);
    lastContent.value = nextContent;
    // Note: no hasNewContent = true here to prevent scroll on full rewrites
  }
  // If content is identical, do nothing

  // Only emit and scroll when there's actually new content
  if (hasNewContent) {
    emit('newContent');
    if (props.autoScroll !== false) {
      await nextTick();
      terminal.value.scrollToBottom();
    }
  }
};

onMounted(async () => {
  if (!terminalRef.value) return;

  // Check initial dark mode
  checkDarkMode();

  // Initialize FitAddon
  fitAddon.value = new FitAddon();

  terminal.value = new Terminal({
    disableStdin: true,
    convertEol: true,
    fontFamily: "'SF Mono', Menlo, Monaco, 'Cascadia Code', 'Courier New', monospace",
    fontSize: 13,
    lineHeight: 1.5,
    letterSpacing: 0,
    scrollback: 5000,
    cursorBlink: false,
    cursorStyle: 'block',
    theme: isDarkMode.value ? darkTheme : lightTheme,
    scrollOnUserInput: true,
    cols: 80, // Set a reasonable default column count
    rows: 24,
  });
  terminal.value.loadAddon(fitAddon.value);
  terminal.value.open(terminalRef.value);

  // Delay initial fit to ensure container has proper dimensions
  // Use multiple RAF cycles to ensure layout is complete
  await nextTick();
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      if (fitAddon.value && terminalRef.value) {
        const width = terminalRef.value.offsetWidth;
        // Only fit if container has reasonable width (> 200px to avoid narrow columns)
        if (width > 200) {
          try {
            fitAddon.value.fit();
          } catch (e) {
            console.debug('Initial fit failed:', e);
          }
        }
      }
    });
  });

  writeContent(props.content || '');

  // Debounce resize to avoid rapid refitting
  let resizeTimeout: ReturnType<typeof setTimeout> | null = null;
  resizeObserver = new ResizeObserver((entries) => {
    const entry = entries[0];
    if (entry && entry.contentRect.width > 200) {
      // Debounce to avoid too frequent refits
      if (resizeTimeout) clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(() => {
        requestAnimationFrame(() => {
          if (fitAddon.value && terminal.value) {
            try {
              fitAddon.value.fit();
            } catch (e) {
              console.debug('Resize fit failed:', e);
            }
          }
        });
      }, 100);
    }
  });
  resizeObserver.observe(terminalRef.value);

  // Watch for theme changes
  themeObserver = new MutationObserver(checkDarkMode);
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class'],
  });
});

onUnmounted(() => {
  // Disconnect theme observer
  if (themeObserver) {
    themeObserver.disconnect();
    themeObserver = null;
  }

  // Disconnect resize observer
  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }

  // Safely dispose FitAddon
  if (fitAddon.value) {
    try {
      fitAddon.value.dispose();
    } catch (e) {
      // Addon already disposed or not properly loaded
      console.debug('FitAddon disposal skipped:', e);
    }
    fitAddon.value = null;
  }

  // Dispose terminal
  if (terminal.value) {
    try {
      terminal.value.dispose();
    } catch (e) {
      console.debug('Terminal disposal error:', e);
    }
    terminal.value = null;
  }
});

watch(
  () => props.content,
  (next) => {
    writeContent(next || '');
  },
);
</script>

<style scoped>
.terminal-view {
  position: relative;
  flex: 1;
  min-height: 0;
  min-width: 0;
  width: 100%;
}

.terminal-body {
  display: flex;
  width: 100%;
  height: 100%;
  min-width: 200px; /* Prevent xterm from calculating 0-width columns */
  overflow: hidden;
}

.terminal-shell {
  position: relative;
  flex: 1;
  width: 100%;
  height: 100%;
  background: var(--bolt-elements-bg-depth-1);
  color: var(--bolt-elements-textPrimary);
  font-family: 'SF Mono', Menlo, Monaco, 'Cascadia Code', 'Courier New', monospace;
  font-size: 13px;
  overflow: hidden;
}

.terminal-surface {
  width: 100%;
  height: 100%;
  padding: 12px 16px;
  box-sizing: border-box;
}

/* Ensure xterm fills the surface properly */
.terminal-surface :deep(.xterm) {
  width: 100% !important;
  height: 100% !important;
}

.terminal-surface :deep(.xterm-screen) {
  width: 100% !important;
}


/* xterm.js customization */
.terminal-shell :deep(.xterm) {
  padding: 0;
}

.terminal-shell :deep(.xterm-viewport) {
  overflow-y: auto !important;
}

/* Enhanced scrollbar for terminal */
.terminal-shell :deep(.xterm-viewport::-webkit-scrollbar) {
  width: 8px;
}

.terminal-shell :deep(.xterm-viewport::-webkit-scrollbar-track) {
  background: transparent;
  margin: 8px 0;
}

.terminal-shell :deep(.xterm-viewport::-webkit-scrollbar-thumb) {
  background: rgba(0, 0, 0, 0.12);
  border-radius: 8px;
  border: 2px solid transparent;
  background-clip: padding-box;
  transition: background 0.15s ease;
}

.terminal-shell :deep(.xterm-viewport::-webkit-scrollbar-thumb:hover) {
  background: rgba(0, 0, 0, 0.22);
  background-clip: padding-box;
}

.terminal-shell.dark-mode :deep(.xterm-viewport::-webkit-scrollbar-thumb) {
  background: rgba(255, 255, 255, 0.12);
  background-clip: padding-box;
}

.terminal-shell.dark-mode :deep(.xterm-viewport::-webkit-scrollbar-thumb:hover) {
  background: rgba(255, 255, 255, 0.22);
  background-clip: padding-box;
}

/* Selection styling */
.terminal-shell :deep(.xterm-selection div) {
  background: rgba(0, 0, 0, 0.2) !important;
}

.terminal-shell.dark-mode :deep(.xterm-selection div) {
  background: rgba(0, 0, 0, 0.3) !important;
}

/* Empty state overlay */
.terminal-view :deep(.empty-state.overlay) {
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(4px);
}

.terminal-shell.dark-mode + :deep(.empty-state.overlay),
.terminal-view:has(.dark-mode) :deep(.empty-state.overlay) {
  background: rgba(26, 26, 26, 0.9);
}

:global(.dark) .terminal-view :deep(.empty-state.overlay) {
  background: rgba(26, 26, 26, 0.9);
}

.terminal-view :deep(.empty-icon) {
  color: rgba(31, 41, 55, 0.5);
}

.terminal-view :deep(.empty-message) {
  color: rgba(31, 41, 55, 0.8);
  font-weight: 500;
}

.terminal-shell.dark-mode ~ :deep(.empty-icon),
:global(.dark) .terminal-view :deep(.empty-icon) {
  color: rgba(229, 231, 235, 0.5);
}

.terminal-shell.dark-mode ~ :deep(.empty-message),
:global(.dark) .terminal-view :deep(.empty-message) {
  color: rgba(229, 231, 235, 0.8);
  font-weight: 500;
}
</style>
