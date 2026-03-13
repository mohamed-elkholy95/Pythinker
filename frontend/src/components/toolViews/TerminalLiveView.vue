<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'

const props = defineProps<{
  sessionId: string
  shellSessionId: string
  command?: string
}>()

const terminalRef = ref<HTMLDivElement>()
let terminal: Terminal | null = null
let fitAddon: FitAddon | null = null
let resizeObserver: ResizeObserver | null = null
let themeObserver: MutationObserver | null = null
const isDarkMode = ref(true)

// Light theme (matching project's light mode)
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
}

// Dark theme (Tokyo Night inspired — matching project's dark mode)
const darkTheme = {
  background: '#1a1b26',
  foreground: '#c0caf5',
  cursor: '#c0caf5',
  cursorAccent: '#1a1b26',
  selectionBackground: '#33467c',
  selectionForeground: '#c0caf5',
  black: '#15161e',
  red: '#f7768e',
  green: '#9ece6a',
  yellow: '#e0af68',
  blue: '#7aa2f7',
  magenta: '#bb9af7',
  cyan: '#7dcfff',
  white: '#a9b1d6',
  brightBlack: '#414868',
  brightRed: '#f7768e',
  brightGreen: '#9ece6a',
  brightYellow: '#e0af68',
  brightBlue: '#7aa2f7',
  brightMagenta: '#bb9af7',
  brightCyan: '#7dcfff',
  brightWhite: '#c0caf5',
}

function checkDarkMode() {
  isDarkMode.value = document.documentElement.classList.contains('dark')
  if (terminal) {
    terminal.options.theme = isDarkMode.value ? darkTheme : lightTheme
  }
}

function initTerminal() {
  if (!terminalRef.value) return

  checkDarkMode()

  terminal = new Terminal({
    theme: isDarkMode.value ? darkTheme : lightTheme,
    fontSize: 13,
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
    lineHeight: 1.5,
    cursorBlink: true,
    cursorStyle: 'bar',
    scrollback: 5000,
    convertEol: true,
    disableStdin: true,
    cols: 80,
    rows: 24,
  })

  fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)
  terminal.open(terminalRef.value)

  // Delay initial fit to ensure container has proper dimensions
  nextTick(() => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (fitAddon && terminalRef.value) {
          const width = terminalRef.value.offsetWidth
          if (width > 200) {
            try {
              fitAddon.fit()
            } catch (e) {
              console.debug('Initial fit failed:', e)
            }
          }
        }
      })
    })
  })

  // Debounced resize observer
  let resizeTimeout: ReturnType<typeof setTimeout> | null = null
  resizeObserver = new ResizeObserver((entries) => {
    const entry = entries[0]
    if (entry && entry.contentRect.width > 200) {
      if (resizeTimeout) clearTimeout(resizeTimeout)
      resizeTimeout = setTimeout(() => {
        requestAnimationFrame(() => {
          if (fitAddon && terminal) {
            try {
              fitAddon.fit()
            } catch (e) {
              console.debug('Resize fit failed:', e)
            }
          }
        })
      }, 100)
    }
  })
  resizeObserver.observe(terminalRef.value)

  // Watch for theme changes
  themeObserver = new MutationObserver(checkDarkMode)
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class'],
  })

  // Write the command prompt if provided
  if (props.command) {
    terminal.writeln(`\x1b[32m$\x1b[0m ${props.command}`)
  }
}

function writeData(data: string) {
  terminal?.write(data)
}

function writeComplete(exitCode: number) {
  if (terminal) {
    terminal.writeln('')
    if (exitCode === 0) {
      terminal.writeln(`\x1b[32m[Process exited with code ${exitCode}]\x1b[0m`)
    } else {
      terminal.writeln(`\x1b[31m[Process exited with code ${exitCode}]\x1b[0m`)
    }
  }
}

function clear() {
  terminal?.clear()
}

onMounted(() => {
  initTerminal()
})

onUnmounted(() => {
  // Disconnect theme observer
  if (themeObserver) {
    themeObserver.disconnect()
    themeObserver = null
  }

  // Disconnect resize observer
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }

  // Safely dispose FitAddon
  if (fitAddon) {
    try {
      fitAddon.dispose()
    } catch (e) {
      console.debug('FitAddon disposal skipped:', e)
    }
    fitAddon = null
  }

  // Dispose terminal
  if (terminal) {
    try {
      terminal.dispose()
    } catch (e) {
      console.debug('Terminal disposal error:', e)
    }
    terminal = null
  }
})

defineExpose({
  writeData,
  writeComplete,
  clear,
})
</script>

<template>
  <div class="terminal-live-container" :class="{ 'dark-mode': isDarkMode }">
    <div ref="terminalRef" class="terminal-element" />
  </div>
</template>

<style scoped>
.terminal-live-container {
  width: 100%;
  height: 100%;
  min-height: 120px;
  background: #ffffff;
  border-radius: 6px;
  overflow: hidden;
}

:global(.dark) .terminal-live-container {
  background: #1a1b26;
}

.terminal-element {
  width: 100%;
  height: 100%;
  padding: 12px 16px;
  box-sizing: border-box;
}

/* Ensure xterm fills the surface properly */
.terminal-element :deep(.xterm) {
  width: 100% !important;
  height: 100% !important;
}

.terminal-element :deep(.xterm-screen) {
  width: 100% !important;
}

/* xterm.js customization */
.terminal-live-container :deep(.xterm) {
  padding: 0;
}

.terminal-live-container :deep(.xterm-viewport) {
  overflow-y: auto !important;
}

/* Enhanced scrollbar for terminal */
.terminal-live-container :deep(.xterm-viewport::-webkit-scrollbar) {
  width: 8px;
}

.terminal-live-container :deep(.xterm-viewport::-webkit-scrollbar-track) {
  background: transparent;
  margin: 8px 0;
}

.terminal-live-container :deep(.xterm-viewport::-webkit-scrollbar-thumb) {
  background: rgba(0, 0, 0, 0.12);
  border-radius: 8px;
  border: 2px solid transparent;
  background-clip: padding-box;
  transition: background 0.15s ease;
}

.terminal-live-container :deep(.xterm-viewport::-webkit-scrollbar-thumb:hover) {
  background: rgba(0, 0, 0, 0.22);
  background-clip: padding-box;
}

:global(.dark) .terminal-live-container :deep(.xterm-viewport::-webkit-scrollbar-thumb) {
  background: rgba(255, 255, 255, 0.12);
  background-clip: padding-box;
}

:global(.dark) .terminal-live-container :deep(.xterm-viewport::-webkit-scrollbar-thumb:hover) {
  background: rgba(255, 255, 255, 0.22);
  background-clip: padding-box;
}

/* Selection styling */
.terminal-live-container :deep(.xterm-selection div) {
  background: rgba(0, 0, 0, 0.2) !important;
}

:global(.dark) .terminal-live-container :deep(.xterm-selection div) {
  background: rgba(0, 0, 0, 0.3) !important;
}
</style>
