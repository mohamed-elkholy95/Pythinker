"""DealScraperTool — multi-store deal search, price comparison, and coupon finding.

Exposes three agent-callable tools:
  - deal_search:         search for deals across major retailers
  - deal_compare_prices: compare prices for specific product URLs
  - deal_find_coupons:   find coupons/promo codes for a store

Enabled via DEAL_SCRAPER_ENABLED=true in .env.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import AsyncGenerator
from dataclasses import asdict
from typing import TYPE_CHECKING

from app.domain.models.event import ToolProgressEvent
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

if TYPE_CHECKING:
    from app.domain.external.deal_finder import CouponSearchResult, DealComparison, DealFinder

logger = logging.getLogger(__name__)

# Queue capacity — prevents unbounded memory growth
_QUEUE_MAX_SIZE = 200

# Noise words stripped during store name normalization (domain layer copy —
# mirrors infrastructure's _STORE_NOISE_WORDS but lives here to avoid
# importing from infrastructure).
_COUPON_NOISE_WORDS: frozenset[str] = frozenset(
    {
        "coupon",
        "coupons",
        "code",
        "codes",
        "promo",
        "discount",
        "deal",
        "deals",
        "offer",
        "sale",
        "free",
        "best",
        "top",
        "latest",
        "new",
        "online",
    }
)


def _build_deal_report_message(comparison: DealComparison) -> str:
    """Build a structured report message from a DealComparison.

    Provides factual summary, best deal callout, failed stores,
    coupon summary, and formatting instructions for the LLM.
    """
    lines: list[str] = []

    best = comparison.best_deal
    best_summary = ""
    if best:
        best_summary = f"Best: ${best.price:.2f} at {best.store}"
        if best.discount_percent:
            best_summary += f" ({best.discount_percent}% off)"

    lines.append(
        f"Found {len(comparison.deals)} deal(s) across {len(comparison.searched_stores)} stores. {best_summary}"
    )

    # Community/web sources
    if comparison.community_sources_searched:
        lines.append(
            f"Also found {comparison.community_sources_searched} community/web deal mention(s) "
            "(Reddit, Slickdeals, forums — prices may be approximate)"
        )

    # Failed stores
    if comparison.store_errors:
        failed_names = [e["store"] for e in comparison.store_errors]
        lines.append(f"Could not check: {', '.join(failed_names)}")

    # Coupon summary
    if comparison.coupons_found:
        verified = sum(1 for c in comparison.coupons_found if c.verified)
        lines.append(f"Coupons: {len(comparison.coupons_found)} found ({verified} verified)")

    # FORMAT instruction for the LLM
    lines.append(
        "FORMAT: Present as Markdown table with Store, Price, Original, "
        "Discount, Score, Stock columns. Prioritize same-day and last-7-days deals. "
        "Flag deals older than 1-2 months as likely expired. "
        "Do NOT validate deals against the product's official website. "
        'Add disclaimer: "Prices checked just now and may change. Verify before purchasing."'
    )

    return "\n".join(lines)


class DealScraperTool(BaseTool):
    """Multi-store deal search, price comparison, and coupon aggregation tool."""

    name: str = "deal_scraper"
    supports_progress: bool = True

    def __init__(
        self,
        deal_finder: DealFinder,
        max_observe: int | None = None,
    ) -> None:
        super().__init__(max_observe=max_observe)
        self._deal_finder = deal_finder
        self._progress_queue: asyncio.Queue[ToolProgressEvent] = asyncio.Queue(
            maxsize=_QUEUE_MAX_SIZE,
        )
        self._active_tool_call_id: str = ""
        self._active_function_name: str = ""
        self._start_time: float = 0.0
        # Session-level store dedup: prevents LLM from re-searching same store
        # with name variations like "Anthropic coupons" then "anthropic promo codes"
        self._coupon_searched_stores: set[str] = set()

    # ── Progress helpers ──────────────────────────────────────────

    def _enqueue_progress(
        self,
        current_step: str,
        steps_completed: int,
        steps_total: int | None,
    ) -> None:
        """Enqueue a ToolProgressEvent (non-blocking, drops if queue full)."""
        pct = min(99, int(steps_completed / steps_total * 100)) if steps_total and steps_total > 0 else 0
        elapsed = (time.monotonic() - self._start_time) * 1000 if self._start_time else 0
        event = ToolProgressEvent(
            tool_call_id=self._active_tool_call_id,
            tool_name=self.name,
            function_name=self._active_function_name,
            progress_percent=pct,
            current_step=current_step,
            steps_completed=steps_completed,
            steps_total=steps_total,
            elapsed_ms=elapsed,
        )
        try:
            self._progress_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.debug("Progress queue full, dropping event: %s", current_step)

    async def _progress_callback(
        self,
        current_step: str,
        steps_completed: int,
        steps_total: int | None,
    ) -> None:
        """Async callback passed to the DealFinder adapter."""
        self._enqueue_progress(current_step, steps_completed, steps_total)

    async def drain_progress_events(self) -> AsyncGenerator[ToolProgressEvent, None]:
        """Drain all queued progress events (non-blocking)."""
        while not self._progress_queue.empty():
            try:
                yield self._progress_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _normalize_store_name(raw: str) -> str:
        """Normalize a store name for session-level dedup.

        Strips coupon noise words, trailing years, and lowercases.
        E.g. "Anthropic Claude Code Coupons 2026" → "anthropic claude code"
        """
        name = raw.strip().lower()
        # Strip trailing year
        name = re.sub(r"\b20\d{2}\b", "", name)
        tokens = name.split()
        meaningful = [t for t in tokens if t and t not in _COUPON_NOISE_WORDS and len(t) > 1]
        if not meaningful:
            meaningful = [t for t in tokens if t][:1]
        return " ".join(meaningful[:3])

    # ── Tool methods ──────────────────────────────────────────────

    @tool(
        name="deal_search",
        description=(
            "Search for the best deals across major retailers "
            "(Amazon, Walmart, Best Buy, Target, Costco, etc.).\n\n"
            "USE WHEN:\n"
            "- User wants to find the cheapest price for a product\n"
            "- User asks to compare prices across stores\n"
            "- User wants deal recommendations or bargain hunting\n\n"
            "EXAMPLE:\n"
            'deal_search(query="Sony WH-1000XM5 headphones", '
            'stores=["amazon.com", "bestbuy.com"])\n\n'
            "RETURNS: Ranked deal comparison with prices, discount percentages, "
            "deal scores, and any coupons found.\n\n"
            "FRESHNESS RULES (CRITICAL):\n"
            "- Deals are TIME-SENSITIVE. Always prioritize same-day and last-7-days deals.\n"
            "- Deals up to 1-2 months old MAY still be valid but flag them: "
            '"⚠️ This deal is from [date] and may have expired."\n'
            "- Deals older than 2 months should be labeled as likely expired.\n"
            "- When presenting results, sort by recency first, then by score.\n"
            "- Include the date/age of each deal when available.\n\n"
            "SOURCE RULES:\n"
            "- Deals come from many sources: retailers, deal aggregators, coupon sites, "
            "cashback portals — NOT only from the product's official website.\n"
            "- Do NOT cross-check or validate deals against the manufacturer's main website. "
            "Authorized retailers and third-party deal sites are legitimate sources.\n"
            "- Never discard a deal just because it's not on the official product page.\n\n"
            "FORMAT GUIDANCE:\n"
            '1. Summary: "Found N deals across M stores. Best: $X at Store (Y% off)"\n'
            "2. Price comparison table:\n"
            "   | Store | Price | Original | Discount | Score | Stock |\n"
            "3. Best Deal callout with reasoning\n"
            "4. Coupons section (verified first, show expiry dates)\n"
            "5. Partial failures: note which stores couldn't be checked\n"
            '6. Disclaimer: "Prices checked at [time] and may change. '
            'Verify deals before purchasing."\n'
            "NEVER invent prices. Only use data from this tool."
        ),
        parameters={
            "query": {
                "type": "string",
                "description": "Product search query (e.g. 'MacBook Air M3' or 'wireless earbuds under $50')",
            },
            "stores": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "(Optional) Specific store domains to search "
                    "(e.g. ['amazon.com', 'walmart.com']). Defaults to all major retailers."
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "(Optional) Maximum number of deals to return. Default: 10.",
            },
        },
        required=["query"],
    )
    async def deal_search(
        self,
        query: str,
        stores: list[str] | None = None,
        max_results: int = 10,
    ) -> ToolResult:
        """Search for deals across multiple stores."""
        if not query.strip():
            return ToolResult(success=False, message="query must not be empty")

        self._start_time = time.monotonic()

        try:
            comparison = await self._deal_finder.search_deals(
                query=query,
                stores=stores,
                max_results=max_results,
                progress=self._progress_callback,
            )
        except Exception as exc:
            logger.exception("Deal search failed for query=%s", query)
            return ToolResult(
                success=False,
                message=f"Deal search failed: {exc}",
            )

        if comparison.error:
            return ToolResult(success=False, message=comparison.error)

        if not comparison.deals:
            return ToolResult(
                success=True,
                message=f"No deals found for '{query}' across {len(comparison.searched_stores)} stores",
                data={
                    "query": query,
                    "deals": [],
                    "searched_stores": comparison.searched_stores,
                    "store_errors": comparison.store_errors,
                },
            )

        # Format deals for display
        deals_data = []
        for deal in comparison.deals:
            deal_dict = asdict(deal)
            # Add formatted price string
            deal_dict["price_display"] = f"${deal.price:.2f}"
            if deal.original_price:
                deal_dict["original_price_display"] = f"${deal.original_price:.2f}"
            if deal.discount_percent:
                deal_dict["discount_display"] = f"{deal.discount_percent}% off"
            deals_data.append(deal_dict)

        coupons_data = [asdict(c) for c in comparison.coupons_found] if comparison.coupons_found else []

        return ToolResult(
            success=True,
            message=_build_deal_report_message(comparison),
            data={
                "query": query,
                "deals": deals_data,
                "best_deal": asdict(comparison.best_deal) if comparison.best_deal else None,
                "coupons": coupons_data,
                "searched_stores": comparison.searched_stores,
                "store_errors": comparison.store_errors,
            },
        )

    @tool(
        name="deal_compare_prices",
        description=(
            "Compare prices for a product across specific URLs.\n\n"
            "USE WHEN:\n"
            "- User provides specific product URLs and wants to know which is cheapest\n"
            "- User found products on different sites and wants a side-by-side comparison\n\n"
            "EXAMPLE:\n"
            'deal_compare_prices(urls=["https://amazon.com/dp/B0C...", '
            '"https://walmart.com/ip/..."])\n\n'
            "RETURNS: Price comparison sorted from lowest to highest with savings.\n\n"
            "FRESHNESS RULES (CRITICAL):\n"
            "- Prices are live snapshots — always note when they were checked.\n"
            "- If any URL appears to show an old/cached price, flag it.\n\n"
            "SOURCE RULES:\n"
            "- Accept prices from any retailer or authorized seller URL.\n"
            "- Do NOT validate prices against the manufacturer's official website.\n"
            "- Third-party retailers often have different (and better) prices.\n\n"
            "FORMAT GUIDANCE:\n"
            '1. Winner: "Cheapest: $X at Store — saves $Y"\n'
            "2. Table: | # | Store | Price | Savings | Confidence |\n"
            "3. Failed URLs with reason\n"
            "4. Disclaimer about shipping/tax and price timing\n"
            "NEVER invent prices. Only use data from this tool."
        ),
        parameters={
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of product URLs to compare (max 10)",
            },
        },
        required=["urls"],
    )
    async def deal_compare_prices(self, urls: list[str]) -> ToolResult:
        """Compare prices across specific product URLs."""
        if not urls:
            return ToolResult(success=False, message="urls list must not be empty")

        urls = urls[:10]  # Hard cap
        self._start_time = time.monotonic()

        try:
            comparison = await self._deal_finder.compare_prices(
                urls,
                progress=self._progress_callback,
            )
        except Exception as exc:
            logger.exception("Price comparison failed")
            return ToolResult(
                success=False,
                message=f"Price comparison failed: {exc}",
            )

        if not comparison.deals:
            msg = "Could not extract prices from any of the provided URLs"
            if comparison.store_errors:
                failed = [f"{e['store']}: {e['error']}" for e in comparison.store_errors]
                msg += f". Errors: {'; '.join(failed)}"
            return ToolResult(
                success=True,
                message=msg,
                data={
                    "urls": urls,
                    "deals": [],
                    "store_errors": comparison.store_errors,
                },
            )

        deals_data = []
        for deal in comparison.deals:
            deal_dict = asdict(deal)
            deal_dict["price_display"] = f"${deal.price:.2f}"
            deals_data.append(deal_dict)

        # Calculate potential savings
        prices = [d.price for d in comparison.deals]
        savings = max(prices) - min(prices) if len(prices) > 1 else 0

        # Build message
        lines = [
            f"Compared {len(comparison.deals)} product(s). "
            f"Cheapest: ${min(prices):.2f} at {comparison.deals[0].store}"
            + (f" (save ${savings:.2f} vs highest)" if savings > 0 else ""),
        ]
        if comparison.store_errors:
            failed_names = [e["store"] for e in comparison.store_errors]
            lines.append(f"Could not check: {', '.join(failed_names)}")
        lines.append(
            "FORMAT: Present as numbered table with Store, Price, Savings, "
            "Confidence columns. Add shipping/tax disclaimer."
        )

        return ToolResult(
            success=True,
            message="\n".join(lines),
            data={
                "deals": deals_data,
                "savings": round(savings, 2),
                "searched_stores": comparison.searched_stores,
                "store_errors": comparison.store_errors,
            },
        )

    @tool(
        name="deal_find_coupons",
        description=(
            "Find coupons, promo codes, and current deals for a specific store.\n\n"
            "USE WHEN:\n"
            "- User asks for coupons or promo codes for a store\n"
            "- User wants to know about current sales at a retailer\n"
            "- User is about to buy and wants to check for discounts\n\n"
            "EXAMPLE:\n"
            'deal_find_coupons(store_name="Amazon")\n\n'
            "RETURNS: List of available coupon codes with verification status.\n\n"
            "FRESHNESS RULES (CRITICAL):\n"
            "- Coupons are TIME-SENSITIVE. Prioritize same-day and last-7-days coupons.\n"
            "- Coupons up to 1-2 months old: include but warn they may have expired.\n"
            "- Coupons older than 2 months: label as likely expired.\n"
            "- Always show expiry dates when available. Sort by freshness, then verified status.\n"
            "- If a coupon has no date, note that its validity is unknown.\n\n"
            "SOURCE RULES:\n"
            "- Coupons come from deal aggregators and coupon databases, not the store itself.\n"
            "- Do NOT validate coupons by checking the store's official website.\n"
            "- Third-party coupon sites (Slickdeals, RetailMeNot, Coupons.com) are valid sources.\n\n"
            "FORMAT GUIDANCE:\n"
            '1. Summary: "Found N coupons for Store (M verified)"\n'
            "2. List (verified first, then by freshness): "
            "**CODE** — description (status, expiry/age)\n"
            '3. Disclaimer: "Verify at checkout. Coupons are time-sensitive '
            'and may expire without notice."\n'
            "NEVER invent coupon codes. Only use data from this tool."
        ),
        parameters={
            "store_name": {
                "type": "string",
                "description": "Store name to find coupons for (e.g. 'Amazon', 'Best Buy', 'Target')",
            },
            "product_url": {
                "type": "string",
                "description": "(Optional) Specific product URL to find coupons for",
            },
        },
        required=["store_name"],
    )
    async def deal_find_coupons(
        self,
        store_name: str,
        product_url: str | None = None,
    ) -> ToolResult:
        """Find coupons and promo codes for a store."""
        if not store_name.strip():
            return ToolResult(success=False, message="store_name must not be empty")

        # Session-level store dedup: normalize and check if already searched
        normalized_store = self._normalize_store_name(store_name)
        if normalized_store in self._coupon_searched_stores:
            return ToolResult(
                success=True,
                message=(
                    f"Already searched coupons for this store (normalized: '{normalized_store}'). "
                    "Results from the previous search still apply. "
                    "Do NOT call deal_find_coupons again with a different name variant."
                ),
                data={"store": store_name, "normalized": normalized_store, "deduplicated": True},
            )
        self._coupon_searched_stores.add(normalized_store)

        self._start_time = time.monotonic()

        try:
            result: CouponSearchResult = await self._deal_finder.find_coupons(
                store=store_name,
                product_url=product_url,
                progress=self._progress_callback,
            )
        except Exception as exc:
            logger.exception("Coupon search failed for store=%s", store_name)
            return ToolResult(
                success=False,
                message=f"Coupon search failed: {exc}",
            )

        coupons = result.coupons

        if not coupons:
            # Build detailed failure report so the LLM doesn't retry via browser
            failure_lines = [f"No coupons found for '{store_name}'."]
            if result.source_failures:
                failure_lines.append("Sources checked:")
                failure_lines.extend(f"  - {sf['source']}: {sf['reason']}" for sf in result.source_failures)
            if result.urls_checked:
                failure_lines.append("URLs checked:")
                failure_lines.extend(f"  - {u}" for u in result.urls_checked)
            failure_lines.append("Do NOT re-visit these URLs via browser_navigate — they return identical results.")
            return ToolResult(
                success=True,
                message="\n".join(failure_lines),
                data={
                    "store": store_name,
                    "coupons": [],
                    "source_failures": result.source_failures,
                    "urls_checked": result.urls_checked,
                },
            )

        coupons_data = [asdict(c) for c in coupons]
        verified_count = sum(1 for c in coupons if c.verified)

        # Build report message
        lines = [
            f"Found {len(coupons)} coupon(s) for {store_name} ({verified_count} verified)",
        ]
        sources_used = {c.source for c in coupons if c.source}
        if sources_used:
            lines.append(f"Sources: {', '.join(sorted(sources_used))}")
        lines.append(
            'FORMAT: List verified coupons first with **CODE** — description. Add "Verify at checkout" disclaimer.'
        )

        return ToolResult(
            success=True,
            message="\n".join(lines),
            data={
                "store": store_name,
                "coupons": coupons_data,
                "total": len(coupons),
                "verified_count": verified_count,
            },
        )
