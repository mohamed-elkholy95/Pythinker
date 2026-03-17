from pydantic import BaseModel, Field


class SearchResultItem(BaseModel):
    """Single search result item"""

    title: str = Field(..., description="Title of the search result")
    link: str = Field(..., description="URL link of the search result")
    snippet: str = Field(default="", description="Snippet or description of the search result")


class SearchResultMeta(BaseModel):
    """Metadata about a search request (for observability and vendor support)."""

    provider: str = Field(..., description="Search provider name (e.g. serper, tavily, brave)")
    latency_ms: float = Field(default=0.0, description="Round-trip latency in milliseconds")
    provider_request_id: str | None = Field(
        default=None,
        description="Vendor request ID from response headers (x-request-id / x-trace-id / cf-ray)",
    )
    estimated_credits: float = Field(
        default=1.0,
        description="Estimated API credits consumed (1.0=basic, 2.0=advanced for Tavily; 1.0 for Serper)",
    )
    cached: bool = Field(default=False, description="Whether result was served from cache")
    canonical_query: str = Field(default="", description="Canonicalized form of the query used for cache keying")


class SearchResults(BaseModel):
    """Complete search results data structure"""

    query: str = Field(..., description="Original search query")
    date_range: str | None = Field(default=None, description="Date range filter applied")
    total_results: int = Field(default=0, description="Total results count")
    results: list[SearchResultItem] = Field(default_factory=list, description="List of search results")
    meta: SearchResultMeta | None = Field(default=None, description="Request metadata for observability")
