import mitt from 'mitt'

/**
 * Typed event bus events.
 * All events emitted/listened on the bus must be declared here.
 */
export type EventBusEvents = {
  EVENT_SHOW_TOOL_PANEL: void
  EVENT_SHOW_FILE_PANEL: void
  EVENT_TOOL_PANEL_STATE_CHANGE: boolean
}

export const eventBus = mitt<EventBusEvents>()
