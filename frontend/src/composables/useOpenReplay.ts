/**
 * OpenReplay Session Recording Composable
 *
 * Provides session recording, replay, and co-browsing (Assist) functionality
 * for the Pythinker frontend. Captures DOM changes, user interactions, network
 * requests, console logs, and canvas content (sandbox viewer).
 */
import { ref, computed, readonly } from 'vue'
import Tracker from '@openreplay/tracker'
import trackerAssist from '@openreplay/tracker-assist'

// Singleton tracker instance
let trackerInstance: Tracker | null = null

// Reactive state
const isInitialized = ref(false)
const isRecording = ref(false)
const sessionId = ref<string | null>(null)
const sessionURL = ref<string | null>(null)
const assistConnected = ref(false)
const remoteControlGranted = ref(false)
const error = ref<string | null>(null)

// Configuration from environment
const config = {
  projectKey: import.meta.env.VITE_OPENREPLAY_PROJECT_KEY || 'pythinker-dev',
  ingestPoint: import.meta.env.VITE_OPENREPLAY_INGEST_URL || 'http://localhost:9001/ingest',
  assistUrl: import.meta.env.VITE_OPENREPLAY_ASSIST_URL || 'ws://localhost:9003',
  canvasQuality: (import.meta.env.VITE_OPENREPLAY_CANVAS_QUALITY || 'medium') as 'low' | 'medium' | 'high',
  canvasFps: parseInt(import.meta.env.VITE_OPENREPLAY_CANVAS_FPS || '6', 10),
  enabled: import.meta.env.VITE_OPENREPLAY_ENABLED === 'true'
}

// File extension mapping for canvas quality
const fileExtForQuality: Record<'low' | 'medium' | 'high', 'webp' | 'png' | 'jpeg'> = {
  low: 'jpeg',
  medium: 'webp',
  high: 'png'
}

/**
 * Initialize the OpenReplay tracker
 * Must be called once at app startup, before any recording
 */
function initializeTracker(): Tracker | null {
  if (!config.enabled) {
    console.info('[OpenReplay] Disabled via configuration')
    return null
  }

  if (trackerInstance) {
    return trackerInstance
  }

  try {
    trackerInstance = new Tracker({
      projectKey: config.projectKey,
      ingestPoint: config.ingestPoint,
      __DISABLE_SECURE_MODE: true, // Allow non-HTTPS in development
      respectDoNotTrack: false,
      // Canvas recording for sandbox viewer
      canvas: {
        disableCanvas: false,
        fileExt: fileExtForQuality[config.canvasQuality],
        useAnimationFrame: true
      },
      // Network capture configuration
      network: {
        capturePayload: true,
        failuresOnly: false,
        ignoreHeaders: ['Authorization', 'Cookie', 'X-Auth-Token'],
        sessionTokenHeader: 'X-Session-Token',
        captureInIframes: false
      },
      // Privacy settings
      obscureTextEmails: true,
      obscureInputEmails: true,
      defaultInputMode: 0, // Plain text (no masking by default)
      // Performance settings
      connAttemptCount: 10,
      connAttemptGap: 5000,
      resourceBaseHref: undefined,
      captureIFrames: false
    })

    // Initialize Assist for co-browsing (call/remote-control UI disabled)
    // The Assist call window injects a position:fixed iframe at z-index ~2.1B
    // which overlays and conflicts with our VNC Take Over controls.
    // We keep Assist for session linking but disable the call/control UI.
    trackerInstance.use(
      trackerAssist({
        serverURL: config.assistUrl,
        // Disable call/control confirmation dialogs — prevents the iframe
        // widget from appearing and conflicting with VNC overlay buttons
        callConfirm: undefined,
        controlConfirm: undefined,
        onAgentConnect: () => {
          assistConnected.value = true
          console.info('[OpenReplay Assist] Agent connected')
          return () => {
            assistConnected.value = false
            remoteControlGranted.value = false
            console.info('[OpenReplay Assist] Agent disconnected')
          }
        },
        onRemoteControlStart: () => {
          remoteControlGranted.value = true
          console.info('[OpenReplay Assist] Remote control started')
          return () => {
            remoteControlGranted.value = false
            console.info('[OpenReplay Assist] Remote control ended')
          }
        }
      })
    )

    // Suppress any residual OpenReplay Assist iframe overlay that may still
    // be injected — prevents z-index conflicts with VNC controls
    const style = document.createElement('style')
    style.textContent = 'iframe[data-openreplay-ignore] { display: none !important; }'
    document.head.appendChild(style)

    isInitialized.value = true
    console.info('[OpenReplay] Tracker initialized', { projectKey: config.projectKey })
    return trackerInstance
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to initialize tracker'
    console.error('[OpenReplay] Initialization failed:', err)
    return null
  }
}

/**
 * Start recording a new session
 * @param metadata - Optional metadata to attach to the session
 */
async function startSession(metadata?: Record<string, string>): Promise<string | null> {
  const tracker = initializeTracker()
  if (!tracker) {
    return null
  }

  if (isRecording.value) {
    console.warn('[OpenReplay] Session already recording')
    return sessionId.value
  }

  try {
    // Start the tracker
    const result = await tracker.start()

    if (result.success) {
      sessionId.value = result.sessionID ?? null
      // Get session URL from tracker method instead of result
      sessionURL.value = tracker.getSessionURL() ?? null
      isRecording.value = true

      // Set initial metadata
      if (metadata) {
        Object.entries(metadata).forEach(([key, value]) => {
          tracker.setMetadata(key, value)
        })
      }

      console.info('[OpenReplay] Session started', {
        sessionId: sessionId.value,
        sessionURL: sessionURL.value
      })
    } else {
      console.warn('[OpenReplay] Failed to start session', result.reason)
    }

    return sessionId.value
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to start session'
    console.error('[OpenReplay] Start session failed:', err)
    return null
  }
}

/**
 * Stop the current recording session
 */
function stopSession(): void {
  if (!trackerInstance || !isRecording.value) {
    return
  }

  try {
    trackerInstance.stop()
    isRecording.value = false
    console.info('[OpenReplay] Session stopped', { sessionId: sessionId.value })
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to stop session'
    console.error('[OpenReplay] Stop session failed:', err)
  }
}

/**
 * Set user identification for the current session
 * @param userId - Unique user identifier
 * @param userInfo - Optional additional user information
 */
function setUser(userId: string, userInfo?: Record<string, string>): void {
  if (!trackerInstance) return

  trackerInstance.setUserID(userId)

  if (userInfo) {
    Object.entries(userInfo).forEach(([key, value]) => {
      trackerInstance?.setMetadata(key, value)
    })
  }
}

/**
 * Set metadata for the current session
 * @param key - Metadata key
 * @param value - Metadata value
 */
function setMetadata(key: string, value: string): void {
  if (!trackerInstance) return
  trackerInstance.setMetadata(key, value)
}

/**
 * Track a custom event
 * @param name - Event name (e.g., 'agent_tool_start')
 * @param payload - Event data
 */
function trackEvent(name: string, payload?: Record<string, unknown>): void {
  if (!trackerInstance) return
  trackerInstance.event(name, payload ?? {})
}

/**
 * Track an issue/error
 * @param name - Issue name
 * @param payload - Issue data
 */
function trackIssue(name: string, payload?: Record<string, unknown>): void {
  if (!trackerInstance) return
  trackerInstance.issue(name, payload ?? {})
}

/**
 * Get the current session URL for sharing/viewing
 */
function getSessionURL(): string | null {
  return trackerInstance?.getSessionURL() ?? sessionURL.value
}

/**
 * Get the current session ID
 */
function getSessionID(): string | null {
  return trackerInstance?.getSessionID() ?? sessionId.value
}

/**
 * Associate a Pythinker session with the OpenReplay session
 * @param pythinkerSessionId - The Pythinker session ID
 */
function linkPythinkerSession(pythinkerSessionId: string): void {
  if (!trackerInstance) return
  trackerInstance.setMetadata('pythinker_session_id', pythinkerSessionId)
  trackEvent('session_linked', { pythinker_session_id: pythinkerSessionId })
}

/**
 * Mark a canvas element for recording
 * OpenReplay automatically captures canvases, but this ensures the sandbox viewer
 * canvas is properly identified and prioritized
 * @param canvas - The canvas element to track
 */
function markCanvasForRecording(canvas: HTMLCanvasElement): void {
  if (!canvas) return
  canvas.setAttribute('data-openreplay-canvas', 'true')
  canvas.setAttribute('data-openreplay-canvas-quality', config.canvasQuality)
}

/**
 * Main composable export
 */
export function useOpenReplay() {
  return {
    // State (readonly)
    isInitialized: readonly(isInitialized),
    isRecording: readonly(isRecording),
    sessionId: readonly(sessionId),
    sessionURL: readonly(sessionURL),
    assistConnected: readonly(assistConnected),
    remoteControlGranted: readonly(remoteControlGranted),
    error: readonly(error),

    // Computed
    isEnabled: computed(() => config.enabled),

    // Methods
    initializeTracker,
    startSession,
    stopSession,
    setUser,
    setMetadata,
    trackEvent,
    trackIssue,
    getSessionURL,
    getSessionID,
    linkPythinkerSession,
    markCanvasForRecording
  }
}

// Export singleton access for non-component usage
export { initializeTracker, trackEvent, trackIssue, setMetadata, markCanvasForRecording }
