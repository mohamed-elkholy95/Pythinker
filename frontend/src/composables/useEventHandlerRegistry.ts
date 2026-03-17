/**
 * Event handler registry — Strategy pattern for SSE event dispatch.
 *
 * Replaces a 160-line if/else chain in processEvent() with a Map-based
 * handler registry. O(1) lookup, open for extension without modifying
 * the dispatch logic.
 */

import type { EventType } from '../types/event'

/** Generic event handler accepting typed data payload. */
export type EventHandler<T = unknown> = (data: T) => void

/**
 * Create a typed event handler registry from a plain object.
 * Keys are SSE event type strings, values are handler functions.
 *
 * Uses `Partial<Record<EventType, …>>` so known event names get
 * autocomplete and typo detection at compile time.
 */
export function createEventHandlerRegistry(
  handlers: Partial<Record<EventType, EventHandler>>,
): Map<string, EventHandler> {
  return new Map(Object.entries(handlers))
}

/**
 * Dispatch an SSE event to its registered handler.
 *
 * @returns true if a handler was found and invoked, false otherwise.
 */
export function dispatchEvent(
  registry: Map<string, EventHandler>,
  eventType: string,
  data: unknown,
): boolean {
  const handler = registry.get(eventType)
  if (handler) {
    handler(data)
    return true
  }
  return false
}
