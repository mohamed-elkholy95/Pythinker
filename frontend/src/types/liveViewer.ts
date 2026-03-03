/**
 * Live Viewer TypeScript types.
 *
 * Defines the type system for the Konva.js-powered live viewer,
 * including screencast state, agent action overlays, user annotations,
 * and zoom/pan controls.
 */

// ---------------------------------------------------------------------------
// Zoom & Pan
// ---------------------------------------------------------------------------

export interface ZoomState {
  /** Current zoom level (0.1 – 5.0, 1.0 = 100%) */
  zoom: number
  /** Horizontal pan offset in stage coordinates */
  panX: number
  /** Vertical pan offset in stage coordinates */
  panY: number
}

export const ZOOM_DEFAULTS: Readonly<ZoomState> = {
  zoom: 1,
  panX: 0,
  panY: 0,
}

export const ZOOM_MIN = 0.1
export const ZOOM_MAX = 5.0
export const ZOOM_STEP = 0.2

// ---------------------------------------------------------------------------
// Screencast Frame
// ---------------------------------------------------------------------------

export interface FrameDimensions {
  width: number
  height: number
}

export interface ScreencastStats {
  frameCount: number
  bytesReceived: number
  fps: number
  bytesPerSec: number
  lastFrameTime: number
}

// ---------------------------------------------------------------------------
// Agent Action Overlay
// ---------------------------------------------------------------------------

/** Browser actions that can be visualized on the overlay */
export type AgentActionType =
  | 'click'
  | 'type'
  | 'scroll'
  | 'navigate'
  | 'move'
  | 'press_key'
  | 'select'
  | 'extract'
  | 'wait'

/** Cursor state for the persistent agent pointer overlay */
export type CursorState = 'idle' | 'moving' | 'clicking'

/** A single agent action to visualize on the overlay layer */
export interface AgentAction {
  /** Unique identifier for this action */
  id: string
  /** Type of browser action */
  type: AgentActionType
  /** X coordinate in sandbox viewport space (0–1280) */
  x: number
  /** Y coordinate in sandbox viewport space (0–900) */
  y: number
  /** Timestamp when the action was received */
  timestamp: number
  /** Display label (e.g., "Click", "Type: hello") */
  label: string
  /** Tool function name that triggered this action */
  functionName: string
  /** Animation progress 0.0 – 1.0 (managed by the overlay composable) */
  progress: number
  /** Duration of the animation in ms */
  duration: number
  /** Optional extra data (e.g., typed text, URL, key name) */
  meta?: Record<string, unknown>
}

/**
 * Maps tool function names to AgentActionType.
 * Used to classify incoming tool events for overlay visualization.
 */
export const FUNCTION_TO_ACTION_TYPE: Record<string, AgentActionType> = {
  // BrowserTool
  browser_click: 'click',
  browser_input: 'type',
  browser_move_mouse: 'move',
  browser_press_key: 'press_key',
  browser_select_option: 'select',
  browser_scroll_up: 'scroll',
  browser_scroll_down: 'scroll',
  browser_navigate: 'navigate',
  browser_view: 'navigate',
  browser_agent_run: 'wait',
  browser_agent_extract: 'extract',
  browsing: 'wait',

  // browser-use internal actions
  click_element: 'click',
  input_text: 'type',
  scroll_down: 'scroll',
  scroll_up: 'scroll',
  go_to_url: 'navigate',
  go_back: 'navigate',
  send_keys: 'press_key',
  scroll_to_text: 'scroll',
  get_dropdown_options: 'select',
  select_dropdown_option: 'select',
  extract_content: 'extract',
  wait: 'wait',

  // Playwright
  playwright_click: 'click',
  playwright_fill: 'type',
  playwright_type: 'type',
  playwright_navigate: 'navigate',
  playwright_select_option: 'select',
  playwright_stealth_navigate: 'navigate',
}

/** Animation durations per action type (ms) */
export const ACTION_ANIMATION_DURATION: Record<AgentActionType, number> = {
  click: 800,
  type: 1200,
  scroll: 600,
  navigate: 1000,
  move: 400,
  press_key: 500,
  select: 700,
  extract: 1000,
  wait: 2000,
}

/** Colors per action type (for overlay shapes) */
export const ACTION_COLORS: Record<AgentActionType, string> = {
  click: '#3b82f6',     // Blue
  type: '#8b5cf6',      // Purple
  scroll: '#f59e0b',    // Amber
  navigate: '#10b981',  // Emerald
  move: '#6b7280',      // Gray
  press_key: '#ec4899', // Pink
  select: '#06b6d4',    // Cyan
  extract: '#f97316',   // Orange
  wait: '#9ca3af',      // Light gray
}

// ---------------------------------------------------------------------------
// Annotation Layer
// ---------------------------------------------------------------------------

/** Element types that can be persisted as annotations */
export type AnnotationElementType =
  | 'pen'
  | 'rectangle'
  | 'ellipse'
  | 'arrow'
  | 'text'

/** Tool types available in the annotation toolbar (includes destructive tools) */
export type AnnotationToolType = AnnotationElementType | 'eraser'

export interface AnnotationStyle {
  color: string
  strokeWidth: number
  opacity: number
  fontSize?: number
}

export const DEFAULT_ANNOTATION_STYLE: Readonly<AnnotationStyle> = {
  color: '#ef4444',
  strokeWidth: 3,
  opacity: 1,
  fontSize: 16,
}

/** A single user annotation element */
export interface AnnotationElement {
  /** Unique ID */
  id: string
  /** Element type (only persistable types, never 'eraser') */
  type: AnnotationElementType
  /** Points array for pen/arrow (flat [x1,y1,x2,y2,...]) */
  points?: number[]
  /** Position for rect/ellipse/text */
  x?: number
  y?: number
  /** Dimensions for rect/ellipse */
  width?: number
  height?: number
  /** Text content for text annotations */
  text?: string
  /** Visual style */
  style: AnnotationStyle
  /** Creation timestamp */
  timestamp: number
}

// ---------------------------------------------------------------------------
// Live Viewer State (aggregated)
// ---------------------------------------------------------------------------

export interface LiveViewerState {
  /** Zoom & pan state */
  zoom: ZoomState
  /** Whether annotation mode is active */
  annotationMode: boolean
  /** Active annotation tool */
  annotationTool: AnnotationToolType
  /** Annotation style settings */
  annotationStyle: AnnotationStyle
  /** Whether agent action overlay is visible */
  showAgentActions: boolean
  /** Whether stats overlay is visible */
  showStats: boolean
}

// ---------------------------------------------------------------------------
// Sandbox viewport constants
// ---------------------------------------------------------------------------

/** Sandbox browser viewport width (matches Playwright DEFAULT_VIEWPORT) */
export const SANDBOX_WIDTH = 1280
/** Sandbox browser viewport height (matches Playwright DEFAULT_VIEWPORT) */
export const SANDBOX_HEIGHT = 900
