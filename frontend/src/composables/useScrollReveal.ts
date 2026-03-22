import { onUnmounted, type ComponentPublicInstance } from 'vue'

interface ScrollRevealOptions {
  /** Intersection threshold (0.0–1.0). Default: 0.15 */
  threshold?: number
  /** Observer root margin. Default: '0px 0px -50px 0px' */
  rootMargin?: string
  /** Unobserve after first reveal. Default: true */
  once?: boolean
}

/**
 * IntersectionObserver-based scroll-reveal composable.
 *
 * Elements start hidden (`opacity: 0; translateY(24px)`) and transition
 * to visible when they enter the viewport. Adds the CSS class `revealed`
 * on intersection.
 *
 * Usage:
 * ```vue
 * <div :ref="revealRef" class="scroll-reveal">...</div>
 * ```
 */
export function useScrollReveal(options: ScrollRevealOptions = {}) {
  const { threshold = 0.15, rootMargin = '0px 0px -50px 0px', once = true } = options

  const elements = new Set<Element>()
  const prefersReducedMotion =
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

  let observer: IntersectionObserver | null = null

  if (typeof window !== 'undefined' && 'IntersectionObserver' in window) {
    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add('revealed')
            if (once) {
              observer?.unobserve(entry.target)
              elements.delete(entry.target)
            }
          }
        }
      },
      { threshold, rootMargin },
    )
  }

  /** Bind as a template ref callback: `:ref="revealRef"` */
  const revealRef = (el: Element | ComponentPublicInstance | null) => {
    const target = el instanceof Element ? el : el?.$el
    if (!target || !(target instanceof Element)) return

    if (prefersReducedMotion) {
      target.classList.add('revealed')
      return
    }

    elements.add(target)
    observer?.observe(target)
  }

  onUnmounted(() => {
    observer?.disconnect()
    elements.clear()
  })

  return { revealRef }
}
