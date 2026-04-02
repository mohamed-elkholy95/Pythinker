import { describe, expect, it } from 'vitest';

import { isLiveDomainTool, shouldShowUnifiedStreamingView } from '../viewRouting';

describe('viewRouting', () => {
  it('treats terminal tools as live tools', () => {
    expect(isLiveDomainTool({ name: 'terminal' })).toBe(true);
    expect(isLiveDomainTool({ function: 'terminal_exec' })).toBe(true);
  });

  it('still recognizes shell and browser tools', () => {
    expect(isLiveDomainTool({ name: 'shell' })).toBe(true);
    expect(isLiveDomainTool({ name: 'browser' })).toBe(true);
  });

  it('keeps terminal tools on the dedicated terminal view even when streaming content exists', () => {
    expect(
      shouldShowUnifiedStreamingView({
        isLive: true,
        currentViewType: 'terminal',
        streamingContent: 'echo hello',
        contentType: 'terminal',
      }),
    ).toBe(false);
  });

  it('does not use unified streaming for terminal content when tool config is missing (null view)', () => {
    expect(
      shouldShowUnifiedStreamingView({
        isLive: true,
        currentViewType: null,
        streamingContent: 'output',
        contentType: 'terminal',
      }),
    ).toBe(false);
  });

  it('still allows non-terminal streaming views', () => {
    expect(
      shouldShowUnifiedStreamingView({
        isLive: true,
        currentViewType: 'editor',
        streamingContent: 'print("hello")',
        contentType: 'code',
      }),
    ).toBe(true);
  });
});
