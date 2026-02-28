import type { ToolContent } from '@/types/message';
import type { DealToolContent } from '@/types/toolContent';

const PRIMARY_DEAL_FUNCTIONS = new Set(['deal_search', 'deal_compare_prices']);
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
 * Keep the currently visible deal tool on the live panel when coupon follow-up calls
 * would otherwise overwrite richer deal results with an empty payload.
 */
export const shouldPreserveDealToolInLiveView = (
  current: ToolContent | undefined,
  incoming: ToolContent,
): boolean => {
  if (!current) return false;
  if (!PRIMARY_DEAL_FUNCTIONS.has(current.function)) return false;
  if (incoming.function !== COUPON_FUNCTION) return false;

  // While coupons are in-flight, keep showing deal search/compare progress/results.
  if (incoming.status === 'calling' || incoming.status === 'running') {
    return true;
  }

  // If coupon call completed with real output, allow switching to it.
  if (incoming.status === 'called' && hasDealOrCouponResults(incoming)) {
    return false;
  }

  // Completed coupon call without output: preserve any active or non-empty deal result.
  if (current.status === 'calling' || current.status === 'running') {
    return true;
  }
  return hasDealOrCouponResults(current);
};
