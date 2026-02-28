"""Deal Scraper settings mixin.

Controls the deal finder feature: multi-store price comparison,
coupon aggregation, and deal scoring.
"""


class DealScraperSettingsMixin:
    """Deal Scraper configuration."""

    # Feature flag
    deal_scraper_enabled: bool = False

    # Search limits
    deal_scraper_max_stores: int = 10
    deal_scraper_timeout: int = 30  # Per-store fetch timeout (seconds)

    # Coupon sources (comma-separated)
    deal_scraper_coupon_sources: str = "slickdeals,retailmenot,couponscom"

    # Community & open-web search
    deal_scraper_community_search: bool = True  # Reddit/forums/deal sites
    deal_scraper_open_web_search: bool = True  # Unrestricted web search
    deal_scraper_community_max_queries: int = 3  # Budget cap on community API calls

    # Cache TTL for deal results (seconds)
    deal_scraper_cache_ttl: int = 3600  # 1 hour

    # --- Phase 1 Enhancements ---

    # Price Voting: Run all extraction methods and vote on correct price
    # (vs waterfall which stops at first hit). Catches ~40-60% more errors.
    deal_scraper_price_voting_enabled: bool = True

    # LLM Fallback: Use AI to extract price when traditional methods disagree.
    # Requires LLM service. ~$0.001 per extraction with fast-tier models.
    deal_scraper_llm_extraction_enabled: bool = False
    deal_scraper_llm_max_per_search: int = 5  # Cap LLM extractions per search call

    # Price History: Persist results to MongoDB for trend analysis.
    # Enables sparkline charts, all-time-low detection, seasonal patterns.
    deal_scraper_history_enabled: bool = True
