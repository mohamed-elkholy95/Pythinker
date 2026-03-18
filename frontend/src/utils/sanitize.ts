import DOMPurify from 'dompurify'

/**
 * Sanitize HTML string using DOMPurify.
 * Use this before any v-html binding as defense-in-depth.
 */
export function sanitizeHtml(dirty: string): string {
  if (!dirty || typeof dirty !== 'string') return ''
  return DOMPurify.sanitize(dirty)
}
