/**
 * Canvas editor TypeScript types.
 * Mirrors backend domain models for canvas projects.
 */

export type ElementType = 'rectangle' | 'ellipse' | 'text' | 'image' | 'line' | 'path' | 'group'

export type EditorTool =
  | 'select'
  | 'rectangle'
  | 'ellipse'
  | 'text'
  | 'image'
  | 'pen'
  | 'line'
  | 'hand'

export type FillType = 'solid' | 'gradient'
export type GradientType = 'linear' | 'radial'

export interface SolidFill {
  type: 'solid'
  color: string
}

export interface GradientStop {
  offset: number
  color: string
}

export interface GradientFill {
  type: 'gradient'
  gradient_type: GradientType
  stops: GradientStop[]
  angle: number
}

export type Fill = SolidFill | GradientFill

export interface Stroke {
  color: string
  width: number
  dash?: number[]
}

export interface Shadow {
  color: string
  blur: number
  offset_x: number
  offset_y: number
}

export interface TextStyle {
  font_family: string
  font_size: number
  font_weight: string
  font_style: string
  text_align: string
  vertical_align: string
  line_height: number
  letter_spacing: number
  text_decoration: string
}

export interface CanvasElement {
  id: string
  type: ElementType
  name: string
  x: number
  y: number
  width: number
  height: number
  rotation: number
  scale_x: number
  scale_y: number
  opacity: number
  visible: boolean
  locked: boolean
  z_index: number
  fill?: Fill
  stroke?: Stroke
  shadow?: Shadow
  corner_radius: number
  text?: string
  text_style?: TextStyle
  src?: string
  points?: number[]
  children?: string[]
}

export interface CanvasPage {
  id: string
  name: string
  width: number
  height: number
  background: string
  elements: CanvasElement[]
  sort_order: number
}

export interface CanvasProject {
  id: string
  user_id: string
  session_id: string | null
  name: string
  description: string
  pages: CanvasPage[]
  width: number
  height: number
  background: string
  thumbnail: string | null
  version: number
  created_at: string
  updated_at: string
}

export interface CanvasProjectSyncState {
  session_id: string | null
  version: number
  updated_at: string
}

export type CanvasSyncStatus = 'live' | 'saved' | 'syncing' | 'stale' | 'conflict'

export interface CanvasRemoteSyncState {
  sessionId: string | null
  serverVersion: number
  pendingRemoteVersion: number | null
  hasRemoteConflict: boolean
  isStale: boolean
  lastRemoteOperation: string | null
  lastRemoteSource: 'agent' | 'manual' | 'system' | null
  lastChangedElementIds: string[]
  highlightedElementIds: string[]
}

export interface CanvasVersion {
  id: string
  project_id: string
  version: number
  name: string
  created_at: string
}

export interface EditorState {
  activeTool: EditorTool
  activePageIndex: number
  selectedElementIds: string[]
  zoom: number
  panX: number
  panY: number
  showGrid: boolean
  snapEnabled: boolean
  isDirty: boolean
}
