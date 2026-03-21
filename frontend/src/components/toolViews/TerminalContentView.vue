<template>
  <div class="terminal-view">
    <div class="terminal-body">
      <div
        class="terminal-shell terminal-tool-xterm-hover-scroll"
        :class="{ 'dark-mode': isDarkMode }"
      >
        <div ref="terminalRef" class="terminal-surface"></div>
        <EmptyState
          v-if="!content"
          :message="emptyLabel"
          :icon="emptyIcon"
          overlay
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted, nextTick } from 'vue';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import EmptyState from '@/components/toolViews/shared/EmptyState.vue';
import { createTerminalToolXtermTheme } from '@/config/terminalToolDesign';

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

const lightTheme = createTerminalToolXtermTheme('light');
const darkTheme = createTerminalToolXtermTheme('dark');

// Detect system/app dark mode
const checkDarkMode = () => {
  const root = document.documentElement;
  isDarkMode.value =
    root.classList.contains('dark') || root.getAttribute('data-theme') === 'dark';
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
    fontFamily: "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Monaco, 'Cascadia Code', monospace",
    fontSize: 14,
    lineHeight: 1.625,
    letterSpacing: 0,
    scrollback: 5000,
    cursorBlink: false,
    cursorStyle: 'block',
    theme: isDarkMode.value ? darkTheme : lightTheme,
    scrollOnUserInput: true,
    overviewRulerLanes: 0,
    cols: 80,
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
  height: 100%;
  overflow: hidden;
  background: var(--terminal-tool-viewport-bg);
}

.terminal-body {
  display: flex;
  width: 100%;
  height: 100%;
  min-width: 200px; /* Prevent xterm from calculating 0-width columns */
  overflow: hidden;
  background: var(--terminal-tool-viewport-bg);
}

.terminal-shell {
  position: relative;
  flex: 1;
  width: 100%;
  height: 100%;
  background: var(--terminal-tool-viewport-bg);
  color: var(--terminal-tool-text);
  border: none;
  border-radius: 0;
  box-sizing: border-box;
  font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Monaco, 'Cascadia Code', monospace;
  font-size: 14px;
  overflow: hidden;
}

.terminal-surface {
  width: calc(100% - 24px);
  height: 100%;
  margin-left: 16px;
  box-sizing: border-box;
  background: var(--terminal-tool-viewport-bg);
}

/* Ensure xterm fills the surface properly */
.terminal-surface :deep(.xterm) {
  width: 100% !important;
  height: 100% !important;
  background: var(--terminal-tool-viewport-bg) !important;
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
  background: var(--terminal-tool-viewport-bg) !important;
}

/* Thin scrollbar — scoped styles with higher specificity */
.terminal-shell :deep(.xterm-viewport)::-webkit-scrollbar {
  width: 5px !important;
}
.terminal-shell :deep(.xterm-viewport)::-webkit-scrollbar-track {
  background: transparent !important;
}
.terminal-shell :deep(.xterm-viewport)::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.1) !important;
  border-radius: 3px !important;
}
.terminal-shell:hover :deep(.xterm-viewport)::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.22) !important;
}
.terminal-shell.dark-mode :deep(.xterm-viewport)::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1) !important;
}
.terminal-shell.dark-mode:hover :deep(.xterm-viewport)::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.22) !important;
}

/* Selection styling (neutral — avoid navy/blue tint) */
.terminal-shell :deep(.xterm-selection div) {
  background: rgba(0, 0, 0, 0.18) !important;
}

.terminal-shell.dark-mode :deep(.xterm-selection div) {
  background: rgba(255, 255, 255, 0.12) !important;
}

/* Empty state overlay */
.terminal-view :deep(.empty-state.overlay) {
  background: color-mix(in srgb, var(--terminal-tool-viewport-bg) 88%, transparent);
  backdrop-filter: blur(4px);
}

:global(.dark) .terminal-view :deep(.empty-state.overlay),
:global(html[data-theme='dark']) .terminal-view :deep(.empty-state.overlay) {
  background: color-mix(in srgb, var(--terminal-tool-viewport-bg) 88%, transparent);
}

.terminal-view :deep(.empty-icon) {
  color: var(--terminal-tool-text-muted);
  opacity: 0.85;
}

.terminal-view :deep(.empty-message) {
  color: var(--terminal-tool-text);
  opacity: 0.9;
  font-weight: 500;
}
</style>
