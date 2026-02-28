import type { ToolContent } from '@/types/message';
import type { DealToolContent } from '@/types/toolContent';

const COUPON_FUNCTION = 'deal_find_coupons';

const asDealToolContent = (tool: ToolContent | undefined): DealToolContent | null => {
  if (!tool?.content) return null;
  const content = tool.content as DealToolContent;
  if (!Array.isArray(content.deals) || !Array.isArray(content.coupons)) return null;
  return content;
};

const hasDealOrCouponResults = (tool: ToolContent | undefined): boolean => {
  const content = asDealToolContent(tool);
  if (!content) return false;
  return content.deals.length > 0 || content.coupons.length > 0;
};

/**
 * Keep whatever tool is currently visible on the live panel when a coupon follow-up
 * call would otherwise overwrite it with an empty payload.
 *
 * Guards ANY current panel (browser, search, deal) — not only deal tools — because
 * real sessions often sequence browser_navigate → deal_find_coupons (0 results).
 */
export const shouldPreserveDealToolInLiveView = (
  current: ToolContent | undefined,
  incoming: ToolContent,
): boolean => {
  // Only intercept coupon calls — everything else goes through normally.
  if (incoming.function !== COUPON_FUNCTION) return false;
  if (!current) return false;

  // While coupons are in-flight, keep showing the current panel (any tool type).
  if (incoming.status === 'calling' || incoming.status === 'running') {
    return true;
  }

  // If coupon call completed with real output, allow switching to it.
  if (incoming.status === 'called' && hasDealOrCouponResults(incoming)) {
    return false;
  }

  // Completed coupon call with empty results: always preserve the current panel.
  return true;
};
