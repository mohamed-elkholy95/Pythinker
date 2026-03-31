export function applyXtermHelperTextareaAccessibility(
  container: HTMLElement | undefined,
  idPrefix: string,
  label: string,
): void {
  const helperTextarea = container?.querySelector<HTMLTextAreaElement>('textarea.xterm-helper-textarea')
  if (!helperTextarea) {
    return
  }

  if (!helperTextarea.id) {
    helperTextarea.id = `${idPrefix}-helper-textarea`
  }
  if (!helperTextarea.name) {
    helperTextarea.name = `${idPrefix}-helper-textarea`
  }
  if (!helperTextarea.getAttribute('aria-label')) {
    helperTextarea.setAttribute('aria-label', label)
  }
}
