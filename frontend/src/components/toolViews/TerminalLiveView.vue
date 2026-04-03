<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { createTerminalToolXtermTheme } from '@/config/terminalToolDesign'
import { TerminalStreamAnsiTransformer } from '@/utils/terminalStreamAnsi'

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
const streamAnsi = new TerminalStreamAnsiTransformer()

const lightTheme = createTerminalToolXtermTheme('light')
const darkTheme = createTerminalToolXtermTheme('dark')

function checkDarkMode() {
  const root = document.documentElement
  isDarkMode.value =
    root.classList.contains('dark') || root.getAttribute('data-theme') === 'dark'
  if (terminal) {
    terminal.options.theme = isDarkMode.value ? darkTheme : lightTheme
  }
}

function initTerminal() {
  if (!terminalRef.value) return

  checkDarkMode()

  terminal = new Terminal({
    theme: isDarkMode.value ? darkTheme : lightTheme,
    fontSize: 14,
    fontFamily: "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Monaco, 'Cascadia Code', monospace",
    lineHeight: 1.625,
    cursorBlink: true,
    cursorStyle: 'bar',
    scrollback: 5000,
    convertEol: true,
    disableStdin: true,
    overviewRulerLanes: 0,
    cols: 80,
    rows: 24,
  })

  fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)
  terminal.open(terminalRef.value)
  applyXtermHelperTextareaAccessibility(terminalRef.value, 'live-terminal', 'Live terminal output')

  // Delay initial fit to ensure container has proper dimensions
  nextTick(() => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (fitAddon && terminalRef.value) {
          const width = terminalRef.value.offsetWidth
          if (width > 200) {
            try {
              fitAddon.fit()
            } catch {
              // Initial fit may fail if container not yet sized
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
            } catch {
              // Resize fit may fail during rapid layout changes
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
    attributeFilter: ['class', 'data-theme'],
  })

  // Write the command prompt if provided
  if (props.command) {
    terminal.writeln(`\x1b[32m$\x1b[0m ${props.command.replace(/\r?\n/g, '\r\n')}`)
  }
}

function writeData(data: string) {
  if (!terminal || !data) return
  const colored = streamAnsi.transform(data)
  if (colored) terminal.write(colored)
}

function writeComplete(exitCode: number) {
  if (terminal) {
    const tail = streamAnsi.flush()
    if (tail) terminal.write(tail)
    terminal.writeln('')
    if (exitCode === 0) {
      terminal.writeln(`\x1b[32m[Process exited with code ${exitCode}]\x1b[0m`)
    } else {
      terminal.writeln(`\x1b[31m[Process exited with code ${exitCode}]\x1b[0m`)
    }
  }
}

function clear() {
  streamAnsi.reset()
  terminal?.clear()
}

watch(
  () => props.shellSessionId,
  () => {
    streamAnsi.reset()
  },
)

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
    } catch {
      // FitAddon disposal may fail if already detached
    }
    fitAddon = null
  }

  // Dispose terminal
  if (terminal) {
    try {
      terminal.dispose()
    } catch {
      // Terminal disposal may fail if already disposed
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
  <div
    class="terminal-live-container terminal-tool-xterm-hover-scroll"
    :class="{ 'dark-mode': isDarkMode }"
  >
    <div ref="terminalRef" class="terminal-element" />
  </div>
</template>

<style scoped>
.terminal-live-container {
  width: 100%;
  height: 100%;
  min-height: 120px;
  background: var(--terminal-tool-viewport-bg);
  color: var(--terminal-tool-text);
  border: none;
  border-radius: 0;
  overflow: hidden;
  box-sizing: border-box;
}

.terminal-element {
  width: 100%;
  height: 100%;
  padding: 0 12px;
  box-sizing: border-box;
}

/* Ensure xterm fills the surface properly */
.terminal-element :deep(.xterm) {
  width: 100% !important;
  height: 100% !important;
  background: var(--terminal-tool-viewport-bg) !important;
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
  background: var(--terminal-tool-viewport-bg) !important;
}

/* Selection styling (neutral — avoid navy/blue tint) */
.terminal-live-container :deep(.xterm-selection div) {
  background: rgba(0, 0, 0, 0.18) !important;
}

:global(.dark) .terminal-live-container :deep(.xterm-selection div),
:global(html[data-theme='dark']) .terminal-live-container :deep(.xterm-selection div) {
  background: rgba(255, 255, 255, 0.12) !important;
}
</style>
