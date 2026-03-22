/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}

declare module '@novnc/novnc/lib/rfb.js' {
  export default class RFB {
    constructor(target: HTMLElement, urlOrChannel: string | WebSocket, options?: {
      shared?: boolean
      credentials?: { username?: string; password?: string; target?: string }
      repeaterID?: string
      wsProtocols?: string[]
    })

    // Properties
    background: string
    capabilities: Record<string, boolean>
    clipViewport: boolean
    compressionLevel: number
    dragViewport: boolean
    focusOnClick: boolean
    qualityLevel: number
    resizeSession: boolean
    scaleViewport: boolean
    showDotCursor: boolean
    viewOnly: boolean

    // Methods
    blur(): void
    clipboardPasteFrom(text: string): void
    disconnect(): void
    focus(options?: FocusOptions): void
    getImageData(): ImageData
    sendCredentials(credentials: { username?: string; password?: string; target?: string }): void
    sendCtrlAltDel(): void
    sendKey(keysym: number, code: string | null, down?: boolean): void
    toBlob(callback: (blob: Blob | null) => void, type?: string, quality?: number): void
    toDataURL(type?: string, encoderOptions?: number): string

    // Events
    addEventListener(event: string, handler: (e: unknown) => void): void
    removeEventListener(event: string, handler: (e: unknown) => void): void
  }
}

// Monaco Editor ESM module declarations
declare module 'monaco-editor/esm/vs/editor/editor.api' {
  export * from 'monaco-editor'
}
declare module 'monaco-editor/esm/vs/editor/editor.worker?worker' {
  const workerConstructor: new () => Worker
  export default workerConstructor
}
declare module 'monaco-editor/esm/vs/language/json/json.worker?worker' {
  const workerConstructor: new () => Worker
  export default workerConstructor
}
declare module 'monaco-editor/esm/vs/language/json/monaco.contribution' {
  const _: unknown
  export default _
}
declare module 'monaco-editor/esm/vs/basic-languages/javascript/javascript.contribution' {
  const _: unknown
  export default _
}
declare module 'monaco-editor/esm/vs/basic-languages/typescript/typescript.contribution' {
  const _: unknown
  export default _
}
declare module 'monaco-editor/esm/vs/basic-languages/html/html.contribution' {
  const _: unknown
  export default _
}
declare module 'monaco-editor/esm/vs/basic-languages/css/css.contribution' {
  const _: unknown
  export default _
}
declare module 'monaco-editor/esm/vs/basic-languages/python/python.contribution' {
  const _: unknown
  export default _
}
declare module 'monaco-editor/esm/vs/basic-languages/java/java.contribution' {
  const _: unknown
  export default _
}
declare module 'monaco-editor/esm/vs/basic-languages/go/go.contribution' {
  const _: unknown
  export default _
}
declare module 'monaco-editor/esm/vs/basic-languages/markdown/markdown.contribution' {
  const _: unknown
  export default _
}

// Plotly.js type declarations (plotly.js-dist-min has no bundled types)
declare namespace Plotly {
  interface Data {
    type?: string
    x?: unknown[]
    y?: unknown[]
    z?: unknown[]
    text?: string | string[]
    name?: string
    mode?: string
    marker?: Record<string, unknown>
    line?: Record<string, unknown>
    orientation?: string
    values?: unknown[]
    labels?: string[]
    [key: string]: unknown
  }

  interface Layout {
    title?: string | { text: string; [key: string]: unknown }
    template?: Template
    margin?: { t?: number; l?: number; r?: number; b?: number }
    font?: { family?: string; size?: number; color?: string }
    xaxis?: Record<string, unknown>
    yaxis?: Record<string, unknown>
    width?: number
    height?: number
    [key: string]: unknown
  }

  type Template = string | Record<string, unknown>

  interface Config {
    responsive?: boolean
    displayModeBar?: boolean
    displaylogo?: boolean
    [key: string]: unknown
  }

  function newPlot(
    root: HTMLElement,
    data: Data[],
    layout?: Partial<Layout>,
    config?: Partial<Config>,
  ): Promise<void>

  function react(
    root: HTMLElement,
    data: Data[],
    layout?: Partial<Layout>,
    config?: Partial<Config>,
  ): Promise<void>

  function purge(root: HTMLElement): void

  function relayout(root: HTMLElement, update: Partial<Layout>): Promise<void>
}

declare module 'plotly.js-dist-min' {
  export default Plotly
}

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_SSE_DEBUG?: string
  readonly VITE_ENABLE_EVENTSOURCE_RESUME?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
} 
