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

  it('keeps search view in replay mode even when a screenshot exists', () => {
    // In replay, structured search results are more useful than a static
    // browser screenshot of a search engine page.
    expect(shouldPreferBrowserPreviewForSearch({
      baseViewType: 'search',
      enabled: true,
      isReplayMode: true,
      hasReplayScreenshot: true,
    })).toBe(false);
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

  it('does not prefer browser preview when disabled', () => {
    expect(shouldPreferBrowserPreviewForSearch({
      baseViewType: 'search',
      sessionId: 'session-123',
      enabled: false,
    })).toBe(false);
  });

  it('falls back to search view when session is complete (live mode)', () => {
    expect(resolveLivePreviewViewType({
      baseViewType: 'search',
      sessionId: 'session-123',
      enabled: true,
      isReplayMode: false,
      isSessionComplete: true,
    })).toBe('search');
  });

  it('falls back to search in replay mode without screenshot', () => {
    expect(shouldPreferBrowserPreviewForSearch({
      baseViewType: 'search',
      enabled: true,
      isReplayMode: true,
      hasReplayScreenshot: false,
    })).toBe(false);
  });
});
