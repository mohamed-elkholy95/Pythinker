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
