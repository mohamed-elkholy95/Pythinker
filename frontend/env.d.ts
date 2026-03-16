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

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_SSE_DEBUG?: string
  readonly VITE_ENABLE_EVENTSOURCE_RESUME?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
} 
