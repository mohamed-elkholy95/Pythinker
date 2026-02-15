/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_LIVE_RENDERER: 'cdp' | 'vnc'
  readonly VITE_SSE_DEBUG?: string
  readonly VITE_ENABLE_EVENTSOURCE_RESUME?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
} 
