"""Price history persistence for deal tracking and trend analysis.

Stores every price check in MongoDB's ``deal_price_history`` collection,
enabling:
- Historical price trend charts (7d/30d/90d sparklines)
- All-time low detection ("This is the lowest price in 90 days!")
- Seasonal pattern analysis
- Price manipulation detection (raise-before-sale patterns)

Uses Motor async driver via ``get_mongodb().database`` singleton.
Non-blocking: failures are logged but never break the deal search flow.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.infrastructure.storage.mongodb import get_mongodb

if TYPE_CHECKING:
    from app.domain.external.deal_finder import DealResult

logger = logging.getLogger(__name__)

COLLECTION_NAME = "deal_price_history"


def _get_collection():
    """Get the deal_price_history Motor collection."""
    return get_mongodb().database[COLLECTION_NAME]


async def ensure_indexes() -> None:
    """Create indexes for efficient price history queries.

    Called once during app lifespan startup (non-blocking).
    """
    try:
        col = _get_collection()
        await col.create_index(
            [("product_id", 1), ("store", 1), ("checked_at", -1)],
            name="product_store_time",
        )
        await col.create_index(
            [("user_id", 1), ("checked_at", -1)],
            name="user_time",
        )
        await col.create_index(
            [("checked_at", 1)],
            name="time_ttl",
            expireAfterSeconds=90 * 86400,  # 90-day auto-cleanup
        )
        logger.info("Deal price history indexes ensured")
    except Exception as exc:
        logger.warning("Failed to create deal_price_history indexes: %s", exc)


def _normalize_product_id(product_name: str, store: str) -> str:
    """Create a stable product identifier from name + store.

    Normalizes whitespace, case, and common suffixes for consistent grouping.
    """
    normalized = product_name.lower().strip()
    # Remove common noise suffixes
    for suffix in (" - ", " | ", " \u2014 ", " \u2013 "):
        if suffix in normalized:
            normalized = normalized.split(suffix)[0].strip()
    return f"{store.lower()}:{normalized}"


async def record_price(
    deal: DealResult,
    query: str = "",
    user_id: str | None = None,
) -> None:
    """Persist a single price check result.

    Non-blocking: exceptions are logged but never propagated.
    Called by the adapter after each successful price extraction.
    """
    try:
        doc = {
            "product_id": _normalize_product_id(deal.product_name, deal.store),
            "product_name": deal.product_name,
            "store": deal.store,
            "price": deal.price,
            "original_price": deal.original_price,
            "currency": "USD",
            "url": deal.url,
            "query": query,
            "checked_at": datetime.now(UTC),
            "extraction_strategy": deal.extraction_strategy,
            "extraction_confidence": deal.extraction_confidence,
            "consensus_method": getattr(deal, "_consensus_method", None),
            "in_stock": deal.in_stock,
            "source_type": deal.source_type,
            "user_id": user_id,
        }
        await _get_collection().insert_one(doc)
    except Exception as exc:
        logger.debug("Failed to record price history: %s", exc)


async def record_prices_bulk(
    deals: list[DealResult],
    query: str = "",
    user_id: str | None = None,
) -> None:
    """Bulk-persist multiple price checks from a single search.

    Uses ``insert_many`` for efficiency. Non-blocking.
    """
    if not deals:
        return
    try:
        now = datetime.now(UTC)
        docs = [
            {
                "product_id": _normalize_product_id(d.product_name, d.store),
                "product_name": d.product_name,
                "store": d.store,
                "price": d.price,
                "original_price": d.original_price,
                "currency": "USD",
                "url": d.url,
                "query": query,
                "checked_at": now,
                "extraction_strategy": d.extraction_strategy,
                "extraction_confidence": d.extraction_confidence,
                "in_stock": d.in_stock,
                "source_type": d.source_type,
                "user_id": user_id,
            }
            for d in deals
            if d.price > 0  # Skip mention-only results
        ]
        if docs:
            await _get_collection().insert_many(docs, ordered=False)
            logger.debug("Recorded %d price history entries for query '%s'", len(docs), query[:30])
    except Exception as exc:
        logger.debug("Failed to bulk-record price history: %s", exc)


async def get_price_history(
    product_name: str,
    store: str | None = None,
    days: int = 30,
    limit: int = 100,
) -> list[dict]:
    """Retrieve price history for a product.

    Args:
        product_name: Product name to search for
        store: Optional store filter
        days: Number of days to look back
        limit: Maximum records to return

    Returns:
        List of price records sorted by checked_at descending
    """
    try:
        since = datetime.now(UTC) - timedelta(days=days)
        query: dict = {"checked_at": {"$gte": since}}

        if store:
            pid = _normalize_product_id(product_name, store)
            query["product_id"] = pid
        else:
            # Fuzzy match on product_name (case-insensitive prefix)
            query["product_name"] = {
                "$regex": f"^{_escape_regex(product_name)}",
                "$options": "i",
            }

        cursor = _get_collection().find(query, {"_id": 0}).sort("checked_at", -1).limit(limit)
        return await cursor.to_list(length=limit)
    except Exception as exc:
        logger.warning("Failed to get price history: %s", exc)
        return []


async def get_price_stats(
    product_name: str,
    store: str,
    days: int = 90,
) -> dict | None:
    """Get aggregated price statistics for a product at a specific store.

    Returns:
        Dict with min, max, avg, current, all_time_low, price_trend
        or None if no data found.
    """
    try:
        pid = _normalize_product_id(product_name, store)
        since = datetime.now(UTC) - timedelta(days=days)

        pipeline = [
            {"$match": {"product_id": pid, "checked_at": {"$gte": since}, "price": {"$gt": 0}}},
            {
                "$group": {
                    "_id": None,
                    "min_price": {"$min": "$price"},
                    "max_price": {"$max": "$price"},
                    "avg_price": {"$avg": "$price"},
                    "count": {"$sum": 1},
                    "latest_price": {"$last": "$price"},
                    "first_price": {"$first": "$price"},
                }
            },
        ]

        result = await _get_collection().aggregate(pipeline).to_list(length=1)
        if not result:
            return None

        stats = result[0]
        latest = stats["latest_price"]
        first = stats["first_price"]

        # Determine trend
        if latest < first:
            trend = "decreasing"
        elif latest > first:
            trend = "increasing"
        else:
            trend = "stable"

        is_all_time_low = latest <= stats["min_price"]

        return {
            "min_price": stats["min_price"],
            "max_price": stats["max_price"],
            "avg_price": round(stats["avg_price"], 2),
            "current_price": latest,
            "data_points": stats["count"],
            "period_days": days,
            "trend": trend,
            "is_all_time_low": is_all_time_low,
        }
    except Exception as exc:
        logger.warning("Failed to get price stats: %s", exc)
        return None


async def get_sparkline_data(
    product_name: str,
    store: str,
    days: int = 30,
    points: int = 30,
) -> list[float]:
    """Get price data points for sparkline chart rendering.

    Returns a list of ``points`` prices, evenly distributed across ``days``.
    Missing days are filled with the last known price.
    """
    try:
        pid = _normalize_product_id(product_name, store)
        since = datetime.now(UTC) - timedelta(days=days)

        # Get daily price aggregation
        pipeline = [
            {"$match": {"product_id": pid, "checked_at": {"$gte": since}, "price": {"$gt": 0}}},
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$checked_at"}},
                    "price": {"$last": "$price"},  # Last check of the day
                }
            },
            {"$sort": {"_id": 1}},
            {"$limit": points},
        ]

        result = await _get_collection().aggregate(pipeline).to_list(length=points)
        if not result:
            return []

        return [r["price"] for r in result]
    except Exception as exc:
        logger.debug("Failed to get sparkline data: %s", exc)
        return []


def _escape_regex(text: str) -> str:
    """Escape special regex characters in text for MongoDB $regex."""
    return (
        text.replace("\\", "\\\\")
        .replace(".", "\\.")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("*", "\\*")
        .replace("+", "\\+")
        .replace("?", "\\?")
        .replace("^", "\\^")
        .replace("$", "\\$")
        .replace("|", "\\|")
    )
