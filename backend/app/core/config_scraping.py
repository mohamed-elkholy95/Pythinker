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
    scraping_http1_fallback_enabled: bool = True  # Retry once with HTTP/1.1 on HTTP/2 transport failures

    # Browser Fetcher (Tier 2-3)
    scraping_headless: bool = True  # Run browsers headless

    # Proxy rotation (optional)
    scraping_proxy_enabled: bool = False
    scraping_proxy_list: str = ""  # Comma-separated proxy URLs
    scraping_proxy_strategy: str = "cyclic"  # cyclic only in v0.4

    # Caching configuration
    scraping_cache_enabled: bool = True
    scraping_cache_l1_max_size: int = 100
    scraping_cache_l2_ttl: int = 300  # Redis TTL in seconds
    scraping_cache_key_include_mode: bool = True  # Include fetch mode in cache key

    # Batch fetching
    scraping_batch_max_concurrency: int = 3

    # Adaptive element tracking (Phase 5)
    scraping_adaptive_tracking: bool = False  # Store element fingerprints
    scraping_adaptive_storage_dir: str = "/tmp/scrapling_adaptive"  # SQLite fingerprint storage

    # Per-domain authentication
    scraping_hf_token: str = ""  # HuggingFace token for gated model pages (HF_TOKEN)

    # Auto-enrichment for info_search_web results
    search_auto_enrich_enabled: bool = True  # Fetch full page content for top-K search results
    search_auto_enrich_top_k: int = 5  # Number of top search result URLs to enrich
    search_auto_enrich_snippet_chars: int = 2000  # Max chars per enriched snippet

    # Content thresholds
    scraping_min_content_length: int = 500  # Minimum text length before escalating
    scraping_max_content_length: int = 100000  # Maximum text length to return
