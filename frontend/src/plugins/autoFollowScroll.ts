import type { App, Directive, DirectiveBinding } from 'vue';

export interface AutoFollowScrollOptions {
  enabled?: boolean;
  threshold?: number;
  behavior?: ScrollBehavior;
  onFollowChange?: (isFollowing: boolean) => void;
}

interface ResolvedAutoFollowScrollOptions {
  enabled: boolean;
  threshold: number;
  behavior: ScrollBehavior;
  onFollowChange?: (isFollowing: boolean) => void;
}

interface AutoFollowDirectiveState {
  options: ResolvedAutoFollowScrollOptions;
  isFollowing: boolean;
  rafId: number | null;
  resizeObserver: ResizeObserver | null;
  mutationObserver: MutationObserver | null;
  onScroll: () => void;
  scheduleSync: () => void;
  cleanup: () => void;
}

const AUTO_FOLLOW_STATE_KEY = Symbol('auto-follow-scroll-state');
type AutoFollowElement = HTMLElement & {
  [AUTO_FOLLOW_STATE_KEY]?: AutoFollowDirectiveState;
};

const DEFAULT_THRESHOLD = 24;

const isNearBottom = (el: HTMLElement, threshold: number): boolean => {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= threshold;
};

const normalizeOptions = (
  binding: DirectiveBinding<AutoFollowScrollOptions | undefined>,
): ResolvedAutoFollowScrollOptions => {
  const value = binding.value ?? {};
  return {
    enabled: value.enabled ?? true,
    threshold: value.threshold ?? DEFAULT_THRESHOLD,
    behavior: value.behavior ?? 'auto',
    onFollowChange: value.onFollowChange,
  };
};

const notifyFollowChange = (state: AutoFollowDirectiveState, isFollowing: boolean): void => {
  if (state.isFollowing === isFollowing) return;
  state.isFollowing = isFollowing;
  state.options.onFollowChange?.(isFollowing);
};

const createDirectiveState = (
  el: HTMLElement,
  options: ResolvedAutoFollowScrollOptions,
): AutoFollowDirectiveState => {
  // Track last known scrollHeight to avoid no-op scrollTo calls
  let lastScrollHeight = el.scrollHeight;

  const state: AutoFollowDirectiveState = {
    options,
    isFollowing: isNearBottom(el, options.threshold),
    rafId: null,
    resizeObserver: null,
    mutationObserver: null,
    onScroll: () => {
      notifyFollowChange(state, isNearBottom(el, state.options.threshold));
    },
    scheduleSync: () => {
      if (state.rafId !== null) return; // already scheduled
      state.rafId = window.requestAnimationFrame(() => {
        state.rafId = null;
        if (!state.options.enabled || !state.isFollowing) return;

        // Only scroll if content actually grew (avoids jank from irrelevant mutations)
        const currentHeight = el.scrollHeight;
        if (currentHeight === lastScrollHeight) return;
        lastScrollHeight = currentHeight;

        el.scrollTo({
          top: currentHeight,
          behavior: state.options.behavior,
        });
      });
    },
    cleanup: () => {
      el.removeEventListener('scroll', state.onScroll);
      state.resizeObserver?.disconnect();
      state.mutationObserver?.disconnect();
      if (state.rafId !== null) {
        window.cancelAnimationFrame(state.rafId);
        state.rafId = null;
      }
    },
  };
  return state;
};

export const autoFollowScrollDirective: Directive<
  HTMLElement,
  AutoFollowScrollOptions | undefined
> = {
  mounted(el, binding) {
    const host = el as AutoFollowElement;
    const options = normalizeOptions(binding);
    const state = createDirectiveState(el, options);
    host[AUTO_FOLLOW_STATE_KEY] = state;

    el.addEventListener('scroll', state.onScroll, { passive: true });
    state.options.onFollowChange?.(state.isFollowing);

    // Observe the CONTENT (first child) for size changes, not the scroll container itself.
    // When content grows (new messages, expanded elements), we need to scroll.
    const contentEl = el.firstElementChild as HTMLElement | null;
    if (typeof ResizeObserver !== 'undefined' && contentEl) {
      state.resizeObserver = new ResizeObserver(() => {
        state.scheduleSync();
      });
      state.resizeObserver.observe(contentEl);
    }

    // Use childList only (not characterData) to avoid firing on every streaming text chunk.
    // New messages add/remove DOM nodes (childList), while streaming updates text content
    // within existing nodes. ResizeObserver on the content element catches both cases
    // since text changes resize the content div.
    if (typeof MutationObserver !== 'undefined') {
      state.mutationObserver = new MutationObserver(() => {
        state.scheduleSync();
      });
      state.mutationObserver.observe(el, {
        childList: true,
        subtree: true,
      });
    }

    state.scheduleSync();
  },

  updated(el, binding) {
    const host = el as AutoFollowElement;
    const state = host[AUTO_FOLLOW_STATE_KEY];
    if (!state) return;

    state.options = normalizeOptions(binding);
    state.options.onFollowChange?.(state.isFollowing);

    if (state.options.enabled && state.isFollowing) {
      state.scheduleSync();
    }
  },

  unmounted(el) {
    const host = el as AutoFollowElement;
    const state = host[AUTO_FOLLOW_STATE_KEY];
    if (!state) return;
    state.cleanup();
    delete host[AUTO_FOLLOW_STATE_KEY];
  },
};

const autoFollowScrollPlugin = {
  install(app: App): void {
    app.directive('auto-follow-scroll', autoFollowScrollDirective);
  },
};

export default autoFollowScrollPlugin;
