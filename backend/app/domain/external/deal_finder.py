"""Deal Finder service gateway interface (domain layer).

Follows the same Protocol pattern as domain/external/scraper.py.
The domain layer depends only on this abstraction — never imports
infrastructure adapters directly.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

# Callback signature: (current_step, steps_completed, steps_total | None, checkpoint_data | None) → awaitable
DealProgressCallback = Callable[[str, int, int | None, dict[str, Any] | None], Awaitable[None]]


@dataclass
class DealResult:
    """A single deal from a store."""

    product_name: str
    store: str
    price: float
    url: str
    original_price: float | None = None
    discount_percent: float | None = None
    coupon_code: str | None = None
    in_stock: bool = True
    image_url: str | None = None
    score: int = 0  # 0-100 deal quality score
    extraction_strategy: str | None = None  # "json_ld", "css", "generic"
    extraction_confidence: float = 0.0  # 0-1 price reliability
    source_type: str = "store"  # "store" | "community" | "open_web"


@dataclass
class CouponInfo:
    """A coupon or promo code."""

    code: str
    description: str
    store: str
    expiry: str | None = None
    verified: bool = False
    source: str = ""  # Which aggregator found it
    confidence: float = 0.5  # 0-1 reliability score


@dataclass
class CouponSearchResult:
    """Result of a coupon search with structured failure info."""

    coupons: list[CouponInfo] = field(default_factory=list)
    source_failures: list[dict[str, str]] = field(default_factory=list)
    urls_checked: list[str] = field(default_factory=list)


@dataclass
class DealComparison:
    """Result of a multi-store deal search or price comparison."""

    query: str
    deals: list[DealResult] = field(default_factory=list)
    best_deal: DealResult | None = None
    coupons_found: list[CouponInfo] = field(default_factory=list)
    searched_stores: list[str] = field(default_factory=list)
    error: str | None = None
    store_errors: list[dict[str, str]] = field(default_factory=list)
    community_sources_searched: int = 0


class DealFinder(Protocol):
    """Deal Finder service gateway interface.

    Defines the contract for multi-store deal search, price comparison,
    and coupon aggregation implementations.
    """

    async def search_deals(
        self,
        query: str,
        stores: list[str] | None = None,
        max_results: int = 10,
        progress: DealProgressCallback | None = None,
    ) -> DealComparison:
        """Search for deals across multiple stores."""
        ...

    async def find_coupons(
        self,
        store: str,
        product_url: str | None = None,
        progress: DealProgressCallback | None = None,
    ) -> CouponSearchResult:
        """Find coupons/promo codes for a specific store."""
        ...

    async def compare_prices(
        self,
        product_urls: list[str],
        progress: DealProgressCallback | None = None,
    ) -> DealComparison:
        """Compare prices for specific product URLs."""
        ...
