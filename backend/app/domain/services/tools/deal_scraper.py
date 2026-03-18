"""DealScraperTool — multi-store deal search, price comparison, and coupon finding.

Exposes three agent-callable tools:
  - deal_search:         search for deals across major retailers
  - deal_compare_prices: compare prices for specific product URLs
  - deal_find_coupons:   find coupons/promo codes for a store

Enabled via DEAL_SCRAPER_ENABLED=true in .env.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
import urllib.parse
from collections.abc import AsyncGenerator
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from app.domain.models.event import ToolProgressEvent
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

if TYPE_CHECKING:
    from app.domain.external.browser import Browser
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


def _empty_category_summary() -> dict[str, int]:
    """Create a canonical item-category summary structure."""
    return {"digital": 0, "physical": 0, "unknown": 0}


def _count_item_categories(items: list[Any]) -> dict[str, int]:
    """Count digital/physical/unknown item categories from dataclass-like objects."""
    summary = _empty_category_summary()
    for item in items:
        category = getattr(item, "item_category", "unknown")
        if category not in summary:
            category = "unknown"
        summary[category] += 1
    return summary


def _build_progress_html(query: str, action: str = "Searching Deals") -> str:
    """Build an inline HTML progress page for the CDP screencast live view.

    Displayed in the sandbox browser while deal tools fetch data via HTTP,
    so the user sees activity instead of a blank/stale page.
    """
    safe_query = query[:80].replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    safe_action = action.replace("&", "&amp;").replace("<", "&lt;")
    return f"""\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#1a1a2e;color:#e0e0e0;font-family:system-ui,-apple-system,sans-serif;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  height:100vh;text-align:center;padding:24px}}
.ring{{width:56px;height:56px;border:4px solid #2d2d4e;border-top-color:#6c5ce7;
  border-radius:50%;animation:spin .9s linear infinite;margin-bottom:28px}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
h2{{font-size:1.4rem;margin-bottom:10px;font-weight:600}}
.query{{color:#a29bfe;font-size:1.05rem;margin-bottom:20px;
  max-width:480px;word-break:break-word}}
.stores{{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;max-width:420px}}
.chip{{background:#2d2d4e;border-radius:6px;padding:5px 12px;font-size:.8rem;
  color:#888;animation:fade 2s ease-in-out infinite alternate}}
@keyframes fade{{from{{opacity:.5}}to{{opacity:1}}}}
.chip:nth-child(2){{animation-delay:.3s}}
.chip:nth-child(3){{animation-delay:.6s}}
.chip:nth-child(4){{animation-delay:.9s}}
.chip:nth-child(5){{animation-delay:1.2s}}
</style></head><body>
<div class="ring"></div>
<h2>{safe_action}</h2>
<p class="query">{safe_query}</p>
<div class="stores">
  <span class="chip">All Stores</span>
  <span class="chip">Google Shopping</span>
  <span class="chip">Coupon Sites</span>
  <span class="chip">Deal Aggregators</span>
  <span class="chip">Retailer Websites</span>
</div>
</body></html>"""


def _confidence_label(confidence: float) -> str:
    """Map a 0-1 confidence score to a human-readable label."""
    if confidence >= 0.8:
        return "High"
    if confidence >= 0.5:
        return "Medium"
    return "Low"


def _escape_md_pipe(text: str) -> str:
    """Escape pipe characters to prevent Markdown table breakage."""
    return text.replace("|", "\\|")


def _build_coupon_table(coupons: list[Any]) -> list[str]:
    """Build a professional Markdown table of promo codes with validation and sources.

    Sorted: verified first (descending confidence), then unverified.
    """
    lines: list[str] = []
    verified = sum(1 for c in coupons if c.verified)
    lines.append(f"## Promo Codes & Coupons — {len(coupons)} found ({verified} verified)")
    lines.append("")
    lines.append("| # | Code | Description | Store | Status | Confidence | Expiry | Source | Link |")
    lines.append("|---|------|-------------|-------|--------|------------|--------|--------|------|")

    # Sort: verified first, then by confidence descending
    sorted_coupons = sorted(coupons, key=lambda c: (not c.verified, -c.confidence))

    for idx, coupon in enumerate(sorted_coupons, 1):
        code = f"`{_escape_md_pipe(coupon.code)}`" if coupon.code else "—"
        desc = _escape_md_pipe(coupon.description[:60]) if coupon.description else "—"
        store = _escape_md_pipe(coupon.store) if coupon.store else "—"
        status = "Verified" if coupon.verified else "Unverified"
        conf = _confidence_label(coupon.confidence)
        expiry = _escape_md_pipe(coupon.expiry) if coupon.expiry else "—"
        source = _escape_md_pipe(coupon.source) if coupon.source else "—"
        link = f"[Source]({coupon.source_url})" if coupon.source_url else "—"
        lines.append(f"| {idx} | {code} | {desc} | {store} | {status} | {conf} | {expiry} | {source} | {link} |")

    lines.append("")
    return lines


def _build_deal_report_message(comparison: DealComparison) -> str:
    """Build a structured report message from a DealComparison.

    Report structure (priority order):
    1. Promo codes & coupons table (top — most actionable for users)
    2. Summary and best deal callout
    3. Plotly-compatible price comparison table
    4. Failed stores and category info
    5. FORMAT instructions for the LLM
    """
    lines: list[str] = []

    # ── 1. PROMO CODES TABLE (top priority) ──────────────────────
    if comparison.coupons_found:
        lines.extend(_build_coupon_table(comparison.coupons_found))

    # ── 2. SUMMARY ───────────────────────────────────────────────
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

    # ── 3. PRICE COMPARISON TABLE ────────────────────────────────
    if comparison.deals:
        lines.append("")
        lines.append("| Store | Price ($) | Original ($) | Discount (%) | Score | Stock |")
        lines.append("|-------|-----------|-------------|-------------|-------|-------|")
        for deal in comparison.deals:
            orig = f"{deal.original_price:.2f}" if deal.original_price else "—"
            disc = f"{deal.discount_percent}" if deal.discount_percent else "—"
            stock = "Yes" if deal.in_stock else "—"
            lines.append(f"| {deal.store} | {deal.price:.2f} | {orig} | {disc} | {deal.score} | {stock} |")
        lines.append("")

    # ── 4. FAILED STORES & CATEGORIES ────────────────────────────
    if comparison.store_errors:
        failed_names = [e["store"] for e in comparison.store_errors]
        lines.append(f"Could not check: {', '.join(failed_names)}")

    deal_categories = _count_item_categories(comparison.deals)
    if deal_categories["digital"] or deal_categories["physical"]:
        lines.append(
            "Item categories: "
            f"{deal_categories['physical']} physical, "
            f"{deal_categories['digital']} digital, "
            f"{deal_categories['unknown']} unknown"
        )

    # ── 5. FORMAT INSTRUCTION ────────────────────────────────────
    lines.append(
        "FORMAT: Present promo codes/coupons table FIRST at the top of your response — "
        "this is the most actionable section for the user. "
        "Then present the price comparison table. "
        "Prioritize same-day and last-7-days deals. "
        "Flag deals older than 1-2 months as likely expired. "
        "Do NOT validate deals against the product's official website. "
        'Add disclaimer: "Prices checked just now and may change. '
        'Verify coupon codes at checkout before purchasing."'
    )

    return "\n".join(lines)


class DealScraperTool(BaseTool):
    """Multi-store deal search, price comparison, and coupon aggregation tool."""

    name: str = "deal_scraper"
    supports_progress: bool = True

    def __init__(
        self,
        deal_finder: DealFinder,
        browser: Browser | None = None,
        max_observe: int | None = None,
    ) -> None:
        super().__init__(max_observe=max_observe)
        self._deal_finder = deal_finder
        self._browser = browser
        self._progress_queue: asyncio.Queue[ToolProgressEvent] = asyncio.Queue(
            maxsize=_QUEUE_MAX_SIZE,
        )
        self._active_tool_call_id: str = ""
        self._active_function_name: str = ""
        self._start_time: float = 0.0
        # Session-level store dedup: prevents LLM from re-searching same store
        # with name variations like "Anthropic coupons" then "anthropic promo codes"
        self._coupon_searched_stores: set[str] = set()
        # Accumulates partial deal state for live-view checkpoint_data
        self._partial_state: dict[str, Any] = {
            "store_statuses": [],
            "partial_deals": [],
            "query": "",
        }

    # ── Progress helpers ──────────────────────────────────────────

    def _enqueue_progress(
        self,
        current_step: str,
        steps_completed: int,
        steps_total: int | None,
        checkpoint_data: dict[str, Any] | None = None,
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
            checkpoint_data=checkpoint_data,
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
        partial_data: dict[str, Any] | None = None,
    ) -> None:
        """Async callback passed to the DealFinder adapter.

        Parses current_step messages to build store_statuses and accumulates
        partial deals into checkpoint_data for the live frontend view.
        """
        # Parse store status from step message (e.g. "Searched Amazon (5 results)")
        import re as _re

        store_match = _re.match(r"Searched (\S.*?) \((\d+) results?\)", current_step)
        fail_match = _re.match(r"Searched (\S.*?) \(failed\)", current_step)
        if store_match:
            store_name, count_str = store_match.group(1), store_match.group(2)
            count = int(count_str)
            status = "found" if count > 0 else "empty"
            self._partial_state["store_statuses"].append(
                {"store": store_name, "status": status, "result_count": count},
            )
        elif fail_match:
            store_name = fail_match.group(1)
            self._partial_state["store_statuses"].append(
                {"store": store_name, "status": "failed", "result_count": 0},
            )

        # Accumulate partial deals from adapter (capped at 10)
        if partial_data and "deals" in partial_data:
            for deal in partial_data["deals"]:
                if len(self._partial_state["partial_deals"]) < 10:
                    self._partial_state["partial_deals"].append(deal)

        self._enqueue_progress(
            current_step,
            steps_completed,
            steps_total,
            checkpoint_data=dict(self._partial_state),
        )

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

    async def _show_progress_page(self, query: str, action: str = "Searching Deals") -> None:
        """Navigate sandbox browser to a visual progress page (best-effort).

        Fires-and-forgets so HTTP deal fetching runs concurrently.
        The CDP screencast immediately shows the progress page instead of
        a blank/stale browser tab.
        """
        if not self._browser:
            return
        html = _build_progress_html(query, action)
        data_uri = f"data:text/html,{urllib.parse.quote(html)}"
        with contextlib.suppress(Exception):
            self._display_task = asyncio.create_task(
                self._browser.navigate_for_display(data_uri),
            )

    # ── Tool methods ──────────────────────────────────────────────

    @tool(
        name="deal_search",
        description=(
            "Search for product deals across all online stores.\n\n"
            "Finds the best prices, discounts, and coupon codes for any product by\n"
            "searching Google Shopping and retailer websites. Returns deals sorted\n"
            "by value along with relevant coupon codes.\n\n"
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
            "FORMAT GUIDANCE (PRIORITY ORDER):\n"
            "1. **Promo Codes & Coupons table FIRST** — present ALL found codes at the top:\n"
            "   | # | Code | Description | Store | Status | Confidence | Expiry | Source | Link |\n"
            "   Verified first, then unverified. Include validation status and source links.\n"
            '2. Summary: "Found N deals across M stores. Best: $X at Store (Y% off)"\n'
            "3. Price comparison table:\n"
            "   | Store | Price | Original | Discount | Score | Stock |\n"
            "4. Best Deal callout with reasoning\n"
            "5. Partial failures: note which stores couldn't be checked\n"
            '6. Disclaimer: "Prices checked just now and may change. '
            'Verify coupon codes at checkout before purchasing."\n'
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

        # Reset partial state for this search
        self._partial_state = {
            "store_statuses": [],
            "partial_deals": [],
            "query": query,
        }

        await self._show_progress_page(query, "Searching Deals")
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
            stores_attempted = (
                len(stores) if stores is not None else len(comparison.searched_stores) + len(comparison.store_errors)
            )
            return ToolResult(
                success=True,
                message=f"No deals found for '{query}' across {len(comparison.searched_stores)} stores",
                data={
                    "query": query,
                    "deals": [],
                    "searched_stores": comparison.searched_stores,
                    "store_errors": comparison.store_errors,
                    "empty_reason": comparison.empty_reason.value if comparison.empty_reason else "no_matches",
                    "stores_attempted": stores_attempted,
                    "stores_with_results": len(comparison.searched_stores),
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
        deal_category_summary = _count_item_categories(comparison.deals)
        coupon_category_summary = _count_item_categories(comparison.coupons_found)

        # Generate a slug for suggested deliverable filename
        slug = re.sub(r"[^a-z0-9]+", "_", query.lower().strip())[:40].rstrip("_")

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
                "item_category_summary": deal_category_summary,
                "coupon_item_category_summary": coupon_category_summary,
            },
            suggested_filename=f"deal_report_{slug}.md",
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
        await self._show_progress_page(", ".join(urls[:3]), "Comparing Prices")
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
            "NOTE: The deal_search tool already includes coupon codes in its results. "
            "Only use deal_find_coupons for targeted coupon lookups for a specific store "
            "when the user explicitly asks for more coupons beyond what deal_search found.\n\n"
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

        await self._show_progress_page(store_name, "Finding Coupons")

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
                    "item_category_summary": _empty_category_summary(),
                },
            )

        coupons_data = [asdict(c) for c in coupons]
        verified_count = sum(1 for c in coupons if c.verified)
        category_summary = _count_item_categories(coupons)

        # Build report message
        lines = [
            f"Found {len(coupons)} coupon(s) for {store_name} ({verified_count} verified)",
        ]
        sources_used = {c.source for c in coupons if c.source}
        if sources_used:
            lines.append(f"Sources: {', '.join(sorted(sources_used))}")
        lines.append(
            "Item categories: "
            f"{category_summary['physical']} physical, "
            f"{category_summary['digital']} digital, "
            f"{category_summary['unknown']} unknown"
        )
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
                "item_category_summary": category_summary,
                "source_failures": result.source_failures,
                "urls_checked": result.urls_checked,
            },
        )
