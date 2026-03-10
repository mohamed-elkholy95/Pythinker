import { describe, expect, it } from 'vitest';

import { resolveLivePreviewViewType, shouldPreferBrowserPreviewForSearch } from '../livePreviewSelection';

describe('livePreviewSelection', () => {
  it('prefers live preview for active search sessions with a sandbox browser', () => {
    expect(resolveLivePreviewViewType({
      baseViewType: 'search',
      sessionId: 'session-123',
      enabled: true,
      isReplayMode: false,
      isSessionComplete: false,
    })).toBe('live_preview');
  });

  it('prefers replayed browser preview for search timeline steps when a screenshot exists', () => {
    expect(shouldPreferBrowserPreviewForSearch({
      baseViewType: 'search',
      enabled: true,
      isReplayMode: true,
      hasReplayScreenshot: true,
    })).toBe(true);
  });

  it('keeps the search view when no live or replay browser state is available', () => {
    expect(resolveLivePreviewViewType({
      baseViewType: 'search',
      enabled: true,
      isReplayMode: false,
      isSessionComplete: false,
    })).toBe('search');
  });

  it('does not override non-search tools', () => {
    expect(resolveLivePreviewViewType({
      baseViewType: 'terminal',
      sessionId: 'session-123',
      enabled: true,
      isReplayMode: false,
      isSessionComplete: false,
    })).toBe('terminal');
  });
});
