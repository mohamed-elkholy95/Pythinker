"""Scrapling integration settings mixin.

Controls the three-tier fetch escalation system (HTTP → Dynamic → Stealthy),
feature flags, proxy rotation, and adaptive element tracking.
"""


class ScrapingSettingsMixin:
    """Scrapling integration configuration."""

    # Feature flags
    scraping_enhanced_fetch: bool = True  # Use Scrapling in BrowserTool.search()
    scraping_tool_enabled: bool = False  # Enable dedicated ScrapingTool in agent toolset
    scraping_spider_enabled: bool = False  # Use Spider for per-domain throttled batch fetch
    scraping_spider_top_k: int = 5  # How many search result URLs to spider-fetch in wide_research

    # Tier escalation
    scraping_escalation_enabled: bool = True  # Auto-escalate HTTP → Dynamic → Stealthy
    scraping_stealth_enabled: bool = True  # Enable StealthyFetcher tier

    # HTTP Fetcher (Tier 1)
    scraping_default_impersonate: str = "chrome"  # TLS fingerprint: chrome, firefox, edge
    scraping_http_timeout: int = 15  # HTTP fetch timeout (seconds)

    # Browser Fetcher (Tier 2-3)
    scraping_headless: bool = True  # Run browsers headless

    # Proxy rotation (optional)
    scraping_proxy_enabled: bool = False
    scraping_proxy_list: str = ""  # Comma-separated proxy URLs
    scraping_proxy_strategy: str = "cyclic"  # cyclic only in v0.4

    # Adaptive element tracking (Phase 5)
    scraping_adaptive_tracking: bool = False  # Store element fingerprints
    scraping_adaptive_storage_dir: str = "/tmp/scrapling_adaptive"  # SQLite fingerprint storage

    # Content thresholds
    scraping_min_content_length: int = 500  # Minimum text length before escalating
    scraping_max_content_length: int = 100000  # Maximum text length to return
