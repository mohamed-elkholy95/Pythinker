import { describe, expect, it } from 'vitest';

import type { ToolContent } from '@/types/message';
import type { DealToolContent } from '@/types/toolContent';

import { shouldPreserveDealToolInLiveView } from '../dealLiveViewSelection';

const makeDealContent = (overrides: Partial<DealToolContent> = {}): DealToolContent => ({
  deals: [],
  coupons: [],
  query: 'rtx 5090',
  best_deal_index: null,
  ...overrides,
});

const makeTool = (overrides: Partial<ToolContent>): ToolContent => ({
  tool_call_id: overrides.tool_call_id || 'tool-1',
  name: overrides.name || 'deal_scraper',
  function: overrides.function || 'deal_search',
  args: overrides.args || {},
  status: overrides.status || 'calling',
  timestamp: overrides.timestamp || 1,
  content: overrides.content,
});

describe('shouldPreserveDealToolInLiveView', () => {
  it('keeps an in-flight deal search visible when coupon call starts', () => {
    const current = makeTool({
      tool_call_id: 'deal-search',
      function: 'deal_search',
      status: 'running',
      content: makeDealContent(),
    });
    const incoming = makeTool({
      tool_call_id: 'coupon-search',
      function: 'deal_find_coupons',
      status: 'calling',
    });

    expect(shouldPreserveDealToolInLiveView(current, incoming)).toBe(true);
  });

  it('keeps non-empty deal search visible when coupon result is empty', () => {
    const current = makeTool({
      tool_call_id: 'deal-search',
      function: 'deal_search',
      status: 'called',
      content: makeDealContent({
        deals: [
          {
            store: 'Amazon',
            price: 1999,
            original_price: 2199,
            discount_percent: 9,
            product_name: 'RTX 5090',
            url: 'https://example.com/deal',
            score: 0.92,
            in_stock: true,
            coupon_code: null,
            image_url: null,
          },
        ],
      }),
    });
    const incoming = makeTool({
      tool_call_id: 'coupon-search',
      function: 'deal_find_coupons',
      status: 'called',
      content: makeDealContent({ deals: [], coupons: [] }),
    });

    expect(shouldPreserveDealToolInLiveView(current, incoming)).toBe(true);
  });

  it('allows switching when coupons are found', () => {
    const current = makeTool({
      tool_call_id: 'deal-search',
      function: 'deal_search',
      status: 'called',
      content: makeDealContent({
        deals: [
          {
            store: 'Best Buy',
            price: 2049,
            original_price: 2249,
            discount_percent: 9,
            product_name: 'RTX 5090',
            url: 'https://example.com/deal-2',
            score: 0.89,
            in_stock: true,
            coupon_code: null,
            image_url: null,
          },
        ],
      }),
    });
    const incoming = makeTool({
      tool_call_id: 'coupon-search',
      function: 'deal_find_coupons',
      status: 'called',
      content: makeDealContent({
        coupons: [
          {
            code: 'SAVE50',
            description: 'Save $50',
            store: 'Best Buy',
            expiry: null,
            verified: true,
            source: 'example',
          },
        ],
      }),
    });

    expect(shouldPreserveDealToolInLiveView(current, incoming)).toBe(false);
  });

  it('does not preserve when current tool is not a deal search result', () => {
    const current = makeTool({
      tool_call_id: 'browser-tool',
      name: 'browser',
      function: 'browser_navigate',
      status: 'called',
      content: undefined,
    });
    const incoming = makeTool({
      tool_call_id: 'coupon-search',
      function: 'deal_find_coupons',
      status: 'called',
      content: makeDealContent(),
    });

    expect(shouldPreserveDealToolInLiveView(current, incoming)).toBe(false);
  });
});
