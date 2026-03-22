# Deal Finder Domain Pre-Proposal Plan (Pythinker)

Date: 2026-02-23
Owner: Backend / Agent Architecture
Status: Draft (Pre-Proposal, enhanced with research validation and domain-specific integration)
Implementation Status:
- Completed: Plan review, Context7 validation (FastAPI/Pydantic/scikit-learn), latest-source reconciliation, codebase anchor exploration, domain API research (Amazon/Best Buy/Reddit), marketplace dedup research, anti-bot strategy, FTC compliance audit.
- In Progress: None.
- Not Started: Domain/application/infrastructure/interfaces implementation.

---

## 1. Objective

Design a new `Deal Finder` domain capability that enables agents to discover, normalize, score, and explain ecommerce deals with evidence-backed price claims, deterministic ranking, and reproducible run metadata. The system integrates with Amazon (via Creators API), Best Buy (Developer API), Reddit deal communities (r/buildapcsales, r/deals), and general marketplace search providers to deliver cross-merchant price comparison with full provenance.

## 2. Assumptions

ASSUMPTIONS I'M MAKING:
1. v1 targets general ecommerce physical-product deals (not travel, local coupons, or checkout automation).
2. Initial geography is US-focused (`USD`) with extension points for multi-currency via self-hosted Frankfurter API.
3. Existing search provider abstractions and fallback chains are reused first.
4. This repository is development-only, so we optimize for correctness, clarity, and iteration speed.
5. API contracts stabilize before UI-specific behavior.
6. Amazon PA-API 5.0 is being deprecated April 30, 2026 — new integration targets Amazon Creators API.
7. Best Buy Developer API is free-tier (no affiliate enrollment required for product data queries).
8. Reddit API free tier (~100 requests/minute for OAuth apps) is sufficient for hourly deal subreddit polling.
9. All HTTP communication uses existing `HTTPClientPool`; no direct `httpx.AsyncClient` creation.
10. All external API keys use `APIKeyPool` with FAILOVER strategy.
-> Correct these before implementation if any assumption is wrong.

## 3. Scope and Non-Goals

### In Scope
- Domain models for product identity, price evidence, merchant signals, and ranking decisions.
- Discovery and extraction pipeline that prioritizes structured data and preserves provenance.
- Deterministic scoring and explainability payloads for every ranked result.
- Application orchestration for async search runs and retrieval.
- API contracts, validation strategy, and measurable acceptance thresholds.
- **Multi-merchant integration**: Amazon (Creators API), Best Buy (Developer API), Reddit (deal subreddits), general search providers.
- **Cross-merchant deduplication** via GTIN/UPC/MPN identity hierarchy.
- **FTC compliance** with affiliate disclosure metadata in every result payload.

### Out of Scope (Pre-Proposal)
- Automated purchasing or checkout.
- Personalized recommendation ML beyond deterministic ranking.
- Proprietary paid partner APIs as a hard requirement.
- Production SLA promises.
- Price history persistence / CamelCamelCamel-style tracking (v1.1 candidate).
- Reddit comment sentiment analysis (v1.1 candidate).

## 4. Existing Reuse Anchors (Current Codebase)

The design should extend these components:

### 4.1 Search Infrastructure
- **Search protocol**: `backend/app/domain/external/search.py` — `SearchEngine(Protocol)` with `async search(query, date_range) -> ToolResult[SearchResults]`. Deal discovery wraps this protocol.
- **Provider registry**: `backend/app/infrastructure/external/search/factory.py` — Decorator-based `SearchProviderRegistry` with `@register()` auto-registration. `FallbackSearchEngine` iterates providers until `success=True`. Provider chains: `tavily → serper → duckduckgo`.
- **Search result model**: `backend/app/domain/models/search.py` — `SearchResultItem(title, link, snippet)` + `SearchResults(query, total_results, results)`. Deal candidates extend this with price/merchant fields.

### 4.2 Source Quality & Provenance
- **Source quality scoring**: `backend/app/domain/models/source_quality.py` — `SourceQualityScore` with 4-dimension composite (reliability 35% + relevance 30% + freshness 20% + depth 15%). `SourceReliability` tiers: HIGH/MEDIUM/LOW/UNKNOWN.
- **Source filtering**: `backend/app/domain/services/source_filter.py` — `SourceFilterService` with configurable thresholds, domain tiers, age limits, paywall filtering. Deal Finder needs a deal-specific config with higher thresholds.
- **Provenance tracking**: `backend/app/domain/models/source_attribution.py` — `SourceAttribution(claim, source_type, source_url, access_status, confidence, raw_excerpt)`. `AttributionSummary` with reliability scoring and caveat detection. Deal Finder maps each price claim to a `SourceAttribution`.

### 4.3 Task & Scheduling
- **Task templates**: `backend/app/domain/services/task_templates.py` — Existing `price_tracking` template provides baseline. Deal Finder adds `deal_finder_monitor` template with category/discount/price-range parameters.
- **Scheduled tasks**: `backend/app/domain/models/scheduled_task.py` — `ScheduledTask` model with `ScheduleType`, `NotificationConfig`, `OutputConfig`, `ExecutionRecord` tracking.

### 4.4 Event System
- **Events**: `backend/app/domain/models/event.py` — `BaseEvent(type, id, timestamp)` base class. Deal Finder adds `DealFoundEvent`, `DealRunProgressEvent`, `DealPriceChangeEvent`.

### 4.5 Infrastructure Patterns
- **Repository pattern**: `backend/app/infrastructure/repositories/mongo_session_repository.py` — MongoDB with `from_domain()`/`to_domain()` converters, allowlisted `update_by_id()`, `@lru_cache` singleton factories in `dependencies.py`.
- **ToolResult wrapper**: `backend/app/domain/models/tool_result.py` — `ToolResult[T]` with `ok()`/`error()` class methods. All deal operations return `ToolResult`.
- **HTTP pooling**: `backend/app/infrastructure/external/pool/http_client_pool.py` — `HTTPClientPool` for all HTTP requests.
- **API key pooling**: `backend/app/infrastructure/external/pool/api_key_pool.py` — `APIKeyPool` with FAILOVER/ROUND_ROBIN strategies.

### 4.6 API Composition
- **Router**: `backend/app/interfaces/api/routes.py` — `create_api_router()` composes all sub-routers. Deal Finder adds `deal_finder_routes.router`.
- **Dependencies**: `backend/app/interfaces/dependencies.py` — `@lru_cache` factories for service singletons with full dependency injection.

## 5. Standards Validation and Latest Updates (as of 2026-02-23)

### 5.1 Primary-source validation summary
- Robots behavior must follow RFC 9309 matching semantics and cache policy (rules are matched with most-specific path; robots fetches can be cached up to 24 hours unless unreachable conditions apply).
- Product extraction should prefer Schema.org offer terms (`Offer`, `AggregateOffer`) and explicitly parse shipping/return-policy related fields (`shippingDetails`, `hasMerchantReturnPolicy`) when present.
- Google product structured data guidance still requires consistency between markup and visible page content; dynamic JavaScript-generated markup requires extra care to ensure crawlability and consistency.
- Google (November 12, 2025) clarified that shipping and return policy markup can be added directly in structured data without requiring a Merchant Center account.
- Google Search updates in 2025 show that rich-result surface areas can change; implementation must degrade safely when downstream presentation features are reduced.
- FTC endorsement guidance requires clear disclosures for affiliate relationships, and FTC fake-review rule enforcement is active (effective October 21, 2024).
- `ndcg_score` remains suitable for offline ranking quality, with caveats: negative relevance can break the 0..1 expectation and tie behavior should be explicit (`ignore_ties`).
- **Google Shopping GTIN change (November 2025)**: Products can no longer be located by EAN/UPC/GTIN on Google Shopping directly — extraction must rely on product page structured data rather than Google Shopping search.

### 5.2 Context7 validation summary (2026-02-23)
- **FastAPI** (`/websites/fastapi_tiangolo`, Score: 91.4/100): Keep routers modular with `APIRouter` composition and dependency injection at router/app boundaries. Use `BackgroundTasks` only for lightweight tasks (log writes, notifications). Deal search runs must use `asyncio.Task` or queue-based execution, not `BackgroundTasks`. `BackgroundTasks` merges tasks across dependency levels — safe for post-response cleanup only.
- **Pydantic v2** (`/llmstxt/pydantic_dev_llms-full_txt`, Score: 87.6/100): Use discriminated unions with `Field(discriminator='type')` for heterogeneous event/response structures (e.g., `DealFoundEvent | DealRunProgressEvent`). Keep `@field_validator` methods as `@classmethod` (repo guardrail). Use `Literal` types for discriminator fields.
- scikit-learn: use `ndcg_score` with explicit `k`; complement with precision/coverage metrics rather than relying on a single ranking number.

### 5.3 Compliance requirements to encode in v1
- Every displayed price claim must include source URL and retrieval timestamp.
- Affiliate-related outputs must expose disclosure metadata in result payloads.
- Robots checks must execute before fetch attempts in discovery/extraction flow.
- When required price components are missing (shipping/tax), output must include caveats instead of implicit assumptions.
- **FTC penalty context**: $51,744 per violation for fake reviews/undisclosed affiliates (effective Oct 21, 2024). Machine-readable disclosure fields are non-optional.
- **No commission-based ranking**: Rankings must be based on genuine deal quality metrics; affiliate commission must never influence score weights.

### 5.4 RFC 9309 implementation specifics
| robots.txt Status | Crawler Behavior |
|-------------------|-----------------|
| 2xx | MUST follow parseable rules |
| 3xx | Follow up to 5 consecutive redirects |
| 4xx | MAY access any resources (robots.txt considered absent) |
| 5xx | MUST assume complete disallow; after 30 days unreachable, may treat as 4xx |

- Most specific rule (longest path match) takes precedence.
- Allow wins ties against Disallow at same specificity.
- `Crawl-Delay` is NOT standardized in RFC 9309 — self-impose 1-2s between same-host requests anyway.
- Cache robots.txt for max 24 hours per RFC 9309 + RFC 9111 cache-control.

## 6. Target Domain Integration Map

### 6.1 Amazon (Tier 1 — Structured API)

**API**: Amazon Creators API (replaces PA-API 5.0 deprecated April 30, 2026).
- **Migration deadline**: April 30, 2026. PA-API no longer accepting new customers.
- **Docs**: https://affiliate-program.amazon.com/creatorsapi/docs/en-us/introduction
- **Key endpoints**: Product search, item lookup by ASIN, deal/offer data.
- **Deal data**: `OffersV2` returns structured deal info: `AccessType` (ALL/PRIME_EARLY_ACCESS), `Badge`, `StartTime`/`EndTime`, `PercentClaimed`.
- **Note**: No guarantee of start/end time — existence of `DealDetails` object indicates deal is live.
- **Integration pattern**: Register as `@SearchProviderRegistry.register("amazon_creators")`, implement `SearchEngine` protocol. Use `APIKeyPool` with FAILOVER for key rotation.
- **Rate limits**: Throttled based on revenue generated through affiliate links (starts at 1 req/s).

### 6.2 Best Buy (Tier 1 — Free Developer API)

**API**: Best Buy Developer API (https://developer.bestbuy.com/)
- **Access**: Free API key, no affiliate enrollment required for product data queries.
- **Endpoints**: Products API (search, lookup by SKU), Stores API, Categories API.
- **Product data**: Full structured product data including `salePrice`, `regularPrice`, `percentSavings`, `onSale`, `freeShipping`, `shippingCost`, `customerReviewAverage`, `customerReviewCount`.
- **Deal detection**: `onSale: true` + `percentSavings > 0` + `salePrice < regularPrice`.
- **Affiliate integration**: Optional — affiliates add Impact Partner ID (IPID) to query; URL generated credits the affiliate.
- **Integration pattern**: Register as `@SearchProviderRegistry.register("bestbuy")`, implement `SearchEngine` protocol. Use `HTTPClientPool` for all requests.
- **Rate limits**: 5 queries/second per API key (documented in developer portal).

### 6.3 Reddit Deal Communities (Tier 2 — Social Signal)

**API**: Reddit Data API (OAuth2, free tier ~100 req/min).
- **Target subreddits**: r/buildapcsales (PC/electronics), r/deals (general), r/frugal (budget), r/GameDeals (digital games).
- **Data extracted**: Post title (contains product + price + merchant), URL (direct merchant link), upvotes (social validation signal), flair tags (category: CPU, GPU, Monitor, etc.), timestamp.
- **Structured extraction from titles**: r/buildapcsales enforces title format: `[Category] Product Name - $Price (Discount info) @ Merchant`.
- **Cost**: ~8,640 API requests/month for hourly polling of 10 subreddits ($2.07/month at Reddit API rates).
- **Integration pattern**: Dedicated `RedditDealAdapter` behind `SearchEngine` protocol. Parse structured titles via regex. Use upvote count as social validation signal in `intent_match` scoring dimension.
- **Provenance**: Each Reddit deal links to `SourceAttribution` with `source_type=INFERRED` (title-parsed price) or `DIRECT_CONTENT` (if merchant page verified).

### 6.4 General Search Providers (Tier 2 — URL Discovery)

**Existing chain**: Tavily → Serper → DuckDuckGo (via `FallbackSearchEngine`).
- **Role in Deal Finder**: URL discovery for product pages. Search results feed into extraction pipeline.
- **SearXNG limitation**: No built-in shopping engines. Best used as general web search aggregator for URL discovery, not direct product search. Default categories: general, images, videos, news, map, music, IT, science, files, social media.
- **Strategy**: Use general search for `"product name" deal site:amazon.com OR site:bestbuy.com OR site:walmart.com OR site:reddit.com/r/buildapcsales` queries.

### 6.5 Merchant Trust Tiers

| Tier | Domains | Trust Score | Notes |
|------|---------|-------------|-------|
| **Tier 1** | amazon.com, bestbuy.com, walmart.com, target.com, costco.com | 1.0 | Structured APIs available, verified pricing |
| **Tier 2** | newegg.com, bhphotovideo.com, adorama.com, microcenter.com | 0.85 | Reliable but API-limited |
| **Tier 3** | slickdeals.net, reddit.com/r/buildapcsales, dealnews.com, techbargains.com | 0.70 | Aggregators — social signal, not primary price source |
| **Tier 4** | Unknown/unverified merchants | 0.40 | Require additional evidence, caveats attached |

## 7. Proposed Domain Design

### 7.1 Core Domain Models (new)
- `DealSearchRequest`: query, filters, budget constraints, merchant allow/block lists, freshness window, result limits, provider chain override.
- `ProductIdentity`: normalized keys with matching hierarchy:
  - Priority 1: `gtin` (gtin12/UPC, gtin13/EAN, gtin14) — ~99% accuracy, ~70% branded product coverage.
  - Priority 2: `brand` + `mpn` — ~95% accuracy, ~85% coverage.
  - Priority 3: `brand` + `model` — ~90% accuracy, ~60% coverage.
  - Priority 4: Canonical URL host/path signature — merchant-specific fallback.
  - Fields: `gtin`, `mpn`, `sku`, `brand`, `model`, `asin` (Amazon-specific), `bestbuy_sku`, `canonical_url_signature`.
- `DealCandidate`: normalized offer candidate linked to product identity and evidence. Discriminated union with `Literal` type for variant handling (API-sourced vs. scraped vs. Reddit-parsed).
- `PriceBreakdown`: base price, shipping (known/unknown), discount, tax (known/unknown), effective total, `price_completeness_score` (ratio of known components).
- `OfferTerms`: availability (`InStock`/`OutOfStock`/`PreOrder`/`SoldOut`), item condition (`New`/`Used`/`Refurbished`), shipping details, return-policy extract, promotion flags, deal badge (PRIME_EARLY_ACCESS, CLEARANCE, etc.).
- `MerchantProfile`: domain, trust tier (1-4), policy signals, extraction confidence, `has_affiliate_relationship: bool`, `affiliate_disclosure_text: str | None`.
- `DealScore`: weighted dimensions and deterministic tie-break metadata with machine-readable explanation object.
- `DealEvidence`: URL, retrieval timestamp, snippet or selector path, structured-data path/key, access status (reuses `AccessStatus` from `source_attribution.py`).
- `DealSearchRun`: immutable run record with provider chain, timings, warnings, reproducibility metadata, idempotency key.
- `DealQualityGateReport`: gate results (pass/fail), violated rules, caveats array, FTC disclosure compliance status.

### 7.2 Domain Services (new)
- `DealQueryPlannerService`: expands intent into high-recall query variants. Generates site-scoped queries for Tier 1/2 merchants and subreddit-specific queries for Reddit.
- `DealDiscoveryService`: executes multi-provider search and candidate URL collection. Orchestrates Amazon Creators API, Best Buy API, Reddit API, and general search in parallel via `asyncio.gather`.
- `DealFetchPolicyService`: robots compliance checks (RFC 9309), host cooldown (1-2s self-imposed), fetch eligibility decisions. Skipped for API-sourced data (Amazon/Best Buy already authorized).
- `OfferExtractionService`: JSON-LD-first extraction via `extruct` library with Microdata fallback. Handles `@graph` arrays, `AggregateOffer` unwrapping, `shippingDetails`/`hasMerchantReturnPolicy` parsing.
- `OfferPolicyExtractionService`: extracts shipping/returns policy signals from structured fields and page content.
- `DealNormalizationService`: currency normalization via self-hosted Frankfurter API, availability/condition enum mapping, canonical merchant domain mapping.
- `DealDeduplicationService`: merges duplicates using GTIN > Brand+MPN > Brand+Model > normalized title similarity (Jaccard + token overlap). Keeps all merchant offers visible per canonical product (price comparison mode).
- `DealScoringService`: computes deterministic score with explanation payload.
- `DealQualityGateService`: enforces evidence and caveat requirements, FTC disclosure validation.

### 7.3 Repository Contracts (new)
- `DealRunRepository`: persist/retrieve run metadata and ranked candidates. `Protocol` in `domain/repositories/`, MongoDB implementation in `infrastructure/repositories/`.
- `DealFixtureRepository` (internal test utility): fixture retrieval for regression evaluation.
- `DealAlertRepository` (optional v1.1): persist user alert criteria.

## 8. Layered Architecture Plan (Dependency Rule Compliant)

### Domain Layer (`backend/app/domain`)
- Add models under `domain/models/deal.py` for deal entities/value objects.
- Add protocols under `domain/repositories/deal_repository.py`.
- Add services under `domain/services/deals/`.
- Keep domain isolated from infrastructure imports — use `Protocol` for all external dependencies.

### Application Layer (`backend/app/application`)
- Add `DealFinderService` in `application/services/deal_finder_service.py` for run lifecycle orchestration:
  - create run (with idempotency key check)
  - execute discovery/extraction pipeline (delegates to domain services)
  - fetch run status and paginated results
  - return summary and caveat rollups
  - cancel in-progress runs

### Infrastructure Layer (`backend/app/infrastructure`)
- Implement Mongo-backed `DealRunRepository` following existing patterns:
  - `DealRunDocument` with `from_domain()`/`to_domain()` converters.
  - Allowlisted `update_by_id()` for NoSQL injection prevention.
  - Indexes on `(user_id, status)`, `(run_id)`, `(created_at)`.
- Add provider adapters behind `SearchEngine` protocol:
  - `AmazonCreatorsAdapter` — wraps Creators API with `APIKeyPool`.
  - `BestBuyAdapter` — wraps Best Buy Developer API with `HTTPClientPool`.
  - `RedditDealAdapter` — wraps Reddit Data API with OAuth2 + structured title parsing.
- Add reusable fetch helpers that enforce `DealFetchPolicyService` decisions.
- Integrate optional self-hosted SearXNG adapter behind existing search abstractions.
- Add extraction parsers (JSON-LD via `extruct` + HTML helpers) hidden behind domain contracts.

### Interfaces Layer (`backend/app/interfaces`)
- Add `deal_finder_routes.py` with explicit request/response schemas.
- Add `schemas/deal_finder.py` with Pydantic v2 discriminated unions for response variants.
- Register router in `interfaces/api/routes.py`.
- Wire dependencies in `interfaces/dependencies.py` via `@lru_cache` factory.
- Keep business logic in application/domain services, not route handlers.

## 9. API Contract Draft (v1)

### 9.1 Endpoints
- `POST /api/deals/search`
  - Starts an async run.
  - Body: query, filters, budget range, merchant allow/block list, freshness window, `top_k`, optional `idempotency_key`.
  - Returns: `run_id`, normalized request echo, initial state.
  - Heavy work runs as `asyncio.Task`, NOT `BackgroundTasks` (Context7: BackgroundTasks for lightweight only).
- `GET /api/deals/search/{run_id}`
  - Returns run metadata and state (`queued`, `running`, `completed`, `partial`, `failed`, `cancelled`).
- `GET /api/deals/search/{run_id}/results`
  - Returns paginated ranked `DealCandidate` results with score breakdown and evidence.
  - Query params: `offset`, `limit`, `sort` (default deterministic score order).
  - Each result includes `affiliate_disclosure` metadata (FTC compliance).
- `GET /api/deals/search/{run_id}/summary`
  - Returns aggregate highlights, caveat counts, provider chain performance, FTC disclosure summary.
- `POST /api/deals/search/{run_id}/cancel` (optional)
  - Marks in-progress run as canceled when supported by execution backend.

### 9.2 Contract guardrails
- Accept optional idempotency key to avoid duplicate runs from retries.
- Include explicit `warnings` and `caveats` arrays in run and result schemas.
- Keep numeric fields strictly typed; no ambiguous string-number coercion in public payloads.
- `price` fields use `Decimal` serialization for financial accuracy (no IEEE 754 float rounding).
- Response models use Pydantic v2 discriminated unions: `Field(discriminator='source_type')` for API vs. scraped vs. Reddit-sourced deals.

## 10. Initial Scoring Policy (v1, deterministic)

`final_score = 0.45 * price_value + 0.20 * merchant_trust + 0.15 * freshness + 0.10 * extraction_confidence + 0.10 * intent_match`

### 10.1 Dimension definitions

**price_value (0.45)** — Normalized effective total cost.
- `effective_total = base_price + shipping - discount + known_fees`
- Score against reference price: `score = 1 - (effective_total / reference_price)` where reference = best available comparator across merchants.
- Discount from MSRP alone is unreliable; prefer discount from cross-merchant average when available.
- Missing shipping/tax reduces `price_completeness_score` and adds caveat metadata.

**merchant_trust (0.20)** — Domain reputation and policy signals.
- Tier 1 (Amazon, Best Buy, Walmart, Target, Costco) = 1.0
- Tier 2 (Newegg, B&H, Adorama, Micro Center) = 0.85
- Tier 3 (aggregators: Slickdeals, Reddit, DealNews) = 0.70
- Tier 4 (unknown/unverified) = 0.40
- Adjust +0.05 for: return policy present, HTTPS, shipping policy present.

**freshness (0.15)** — Recency of price observation.
- Exponential decay: `score = exp(-lambda * hours_since_observation)` where lambda calibrated so 24h = 0.5.
- API-sourced data (Amazon, Best Buy) = timestamp of API call.
- Reddit data = post timestamp.

**extraction_confidence (0.10)** — Data quality and completeness.
- JSON-LD extraction = 1.0
- API response (Amazon/Best Buy) = 1.0
- Microdata extraction = 0.9
- Reddit title parsing = 0.7
- HTML heuristic = 0.6
- Manual/unverified = 0.3

**intent_match (0.10)** — Query relevance.
- Title similarity to original search query (token overlap).
- Category match, brand match, condition match.
- Reddit upvote count as social validation signal (normalized 0-1).

### 10.2 Deterministic tie-break order
1. Higher `final_score`
2. Lower `effective_total`
3. Newer `retrieved_at`
4. Lexicographic stable key (`merchant_domain + canonical_url`)

### 10.3 Hard quality gates (pre-ranking eligibility)
- At least one price evidence record with URL + timestamp.
- Parse confidence above minimum threshold (configurable, default 0.5).
- No unqualified "best deal" labeling when critical fields are unknown.
- FTC disclosure metadata present for any result with affiliate relationship.
- `price_completeness_score >= 0.5` (at least base price + one of shipping/tax known).

## 11. Phased Execution Plan

### Phase 0 — Contract Freeze and Fixture Pack
Status: Not Started
Deliverables:
- Freeze request/response models and run-state machine.
- Build fixture pack (>= 30 pages) with varied markup quality and merchant types.
  - Include: Amazon product pages (JSON-LD rich), Best Buy product pages, Reddit r/buildapcsales posts, Walmart pages, unknown merchant pages with poor markup.
  - Fixtures must cover: complete JSON-LD, Microdata-only, no structured data, `AggregateOffer`, missing shipping, Reddit title format.
Acceptance:
- Contract approved.
- Fixture set includes expected normalized outputs and caveat expectations.

### Phase 1 — Domain Foundation and Compliance Rules
Status: Not Started
Deliverables:
- Add core domain models, enums, and repository protocols.
- Add compliance primitives (`DealFetchPolicyService`, disclosure/caveat enums).
- Add `ProductIdentity` with GTIN/MPN/SKU/ASIN matching hierarchy.
- Add `MerchantProfile` with trust tier classification for Amazon/BestBuy/Reddit/general.
Acceptance:
- Domain unit tests pass.
- Domain layer has no infrastructure imports.
- Discriminated unions validate correctly via Pydantic v2.

### Phase 2 — Discovery and Fetch Policy
Status: Not Started
Deliverables:
- Query planning + provider-backed discovery (Amazon Creators API, Best Buy API, Reddit API, general search).
- Robots-aware fetch decisioning and host-level throttle policy (1-2s self-imposed).
- Provider adapters registered via `@SearchProviderRegistry.register()`.
Acceptance:
- Integration tests verify policy execution before fetch.
- Partial runs report warnings without silent failures.
- Amazon/Best Buy/Reddit adapters return structured `ToolResult[SearchResults]`.

### Phase 3 — Extraction, Normalization, Dedup
Status: Not Started
Deliverables:
- JSON-LD-first offer extraction via `extruct` with Microdata fallback.
- Reddit title parsing via regex for r/buildapcsales format `[Category] Product - $Price @ Merchant`.
- Currency normalization via self-hosted Frankfurter API.
- Dedup by GTIN > Brand+MPN > Brand+Model > normalized title similarity.
Acceptance:
- Extraction success target on fixtures met (>= 85%).
- Duplicate merge behavior validated with fixture assertions (precision >= 0.90).
- Reddit title parser handles edge cases (missing price, multi-item posts).

### Phase 4 — Scoring, Explainability, Quality Gates
Status: Not Started
Deliverables:
- Deterministic scoring implementation with 5 weighted dimensions.
- Quality-gate enforcement and explanation payload.
- FTC disclosure validation gate.
Acceptance:
- Every ranked result includes explanation + evidence.
- Gate violations surface explicit caveats.
- Affiliate results include disclosure metadata.

### Phase 5 — Application Orchestration and API
Status: Not Started
Deliverables:
- `DealFinderService` lifecycle orchestration.
- API routes, schema validation, dependency wiring.
- Idempotency key support for `POST /api/deals/search`.
Acceptance:
- End-to-end tests pass for create/status/results/summary flows.
- Error mapping is consistent across run states.
- `@lru_cache` dependency factory wired in `dependencies.py`.

### Phase 6 — Observability and Evaluation
Status: Not Started
Deliverables:
- Structured logging and counters for extraction/fetch/gate outcomes.
- Prometheus metrics: `pythinker_deal_searches_total`, `pythinker_deal_extraction_success_rate`, `pythinker_deal_provider_latency_seconds`.
- Offline evaluation suite with ranking and quality metrics.
Acceptance:
- Baseline metrics recorded and reproducible via local/CI command.
- Non-regression checks added.
- Provider-level latency and success rate dashboards available.

## 12. Acceptance Metrics (initial targets)

- Evidence coverage: 100% of returned prices include source URL + timestamp.
- Extraction success rate on fixture pack: target >= 85% (threshold adjustable after baseline).
- Dedup precision on fixture pairs: target >= 0.90.
- Ranking quality: track `NDCG@10` + `Precision@5` + coverage; block regressions beyond agreed tolerance.
- API contract stability: schema compatibility checks enforced in tests.
- FTC disclosure coverage: 100% of affiliate-linked results include disclosure metadata.
- Provider availability: each Tier 1 provider (Amazon, Best Buy) responds successfully >= 95% of runs.
- Cross-merchant match rate: >= 60% of branded products match across at least 2 merchants via GTIN/MPN.

## 13. Risk Register and Mitigations

### Technical Risks
- **Dynamic/anti-bot pages reduce extractability**:
  - Mitigation: Structured-data-first strategy, official APIs for Tier 1 merchants (Amazon/Best Buy), explicit partial-result state, no silent defaults.
  - Detection: Cloudflare (~20% of sites), Akamai, DataDome dominate ecommerce anti-bot. TLS/JA3 fingerprinting detects default Playwright profiles instantly.
  - Ethical approach: API-first for authorized merchants, search engine caches for others, transparent user-agent, 1-2s inter-request delay.
- **Stale or conflicting prices across sources**:
  - Mitigation: timestamped observations, freshness exponential decay, conflict caveats when same product shows different prices across merchants.
- **Amazon PA-API deprecation (April 30, 2026)**:
  - Mitigation: Build directly on Creators API. No PA-API 5.0 dependency.
- **Reddit API pricing changes**:
  - Mitigation: Free tier sufficient for hourly polling (~8,640 req/month). Budget for $2-3/month. Graceful degradation if Reddit unavailable.
- **Google Shopping GTIN lookup removal (Nov 2025)**:
  - Mitigation: GTIN matching via product page structured data extraction, not Google Shopping search.

### Compliance Risks
- **Misleading discount framing**:
  - Mitigation: Score by effective total, not headline discount percentages. Never claim "lowest price" without cross-merchant verification.
- **FTC affiliate disclosure gaps**:
  - Mitigation: Machine-readable `has_affiliate_relationship` + `affiliate_disclosure_text` on every `DealCandidate`. Quality gate blocks results with affiliate links but missing disclosure.
- **Compliance drift as search/result policies evolve**:
  - Mitigation: periodic standards review checkpoint and fallback-safe rendering.

### Architectural Risks
- **Overengineering risk**:
  - Mitigation: Deterministic v1, narrow service boundaries, incremental phase gates.
- **Provider coupling**:
  - Mitigation: All providers behind `SearchEngine` protocol. Provider swaps require zero domain changes.

## 14. Test Plan (Proposal Level)

### Domain unit tests:
- Scoring math (5 dimensions, tie-breaking, edge cases).
- Price normalization (USD conversion, missing components, completeness score).
- Dedup (GTIN match, Brand+MPN match, title similarity threshold, merge behavior).
- Validator behavior (Pydantic v2 discriminated unions, `@field_validator` `@classmethod`).
- ProductIdentity matching hierarchy (priority ordering, partial key matches).

### Integration tests:
- Provider fallback behavior (Amazon → Best Buy → general search chain).
- Robots decision flow (2xx/3xx/4xx/5xx handling per RFC 9309).
- Extraction on fixtures (JSON-LD, Microdata, Reddit title, no-markup fallback).
- Reddit title parser (standard format, edge cases, multi-item posts).
- Best Buy API product lookup and deal detection.

### Contract tests:
- Strict request/response schema validation and state transitions.
- Discriminated union serialization/deserialization.
- Idempotency key collision behavior.

### Quality tests:
- Numeric claim grounding (price accuracy vs. source).
- Caveat coverage (missing shipping → caveat present).
- FTC disclosure field presence (affiliate → disclosure required).
- `price_completeness_score` threshold enforcement.

### Regression tests:
- Fixture-based rank ordering and non-regression metrics.
- Provider latency baselines.
- Cross-merchant dedup precision on fixture pairs.

## 15. Minimal File Plan (Implementation Phase)

### Domain Layer
- `backend/app/domain/models/deal.py` (new) — All domain models, enums, value objects.
- `backend/app/domain/repositories/deal_repository.py` (new) — `DealRunRepository` protocol.

### Domain Services
- `backend/app/domain/services/deals/__init__.py` (new)
- `backend/app/domain/services/deals/deal_query_planner_service.py` (new)
- `backend/app/domain/services/deals/deal_discovery_service.py` (new)
- `backend/app/domain/services/deals/deal_fetch_policy_service.py` (new)
- `backend/app/domain/services/deals/offer_extraction_service.py` (new)
- `backend/app/domain/services/deals/offer_policy_extraction_service.py` (new)
- `backend/app/domain/services/deals/deal_normalization_service.py` (new)
- `backend/app/domain/services/deals/deal_deduplication_service.py` (new)
- `backend/app/domain/services/deals/deal_scoring_service.py` (new)
- `backend/app/domain/services/deals/deal_quality_gate_service.py` (new)

### Application Layer
- `backend/app/application/services/deal_finder_service.py` (new)

### Infrastructure Layer
- `backend/app/infrastructure/repositories/mongo_deal_repository.py` (new)
- `backend/app/infrastructure/external/deals/__init__.py` (new)
- `backend/app/infrastructure/external/deals/amazon_creators_adapter.py` (new)
- `backend/app/infrastructure/external/deals/bestbuy_adapter.py` (new)
- `backend/app/infrastructure/external/deals/reddit_deal_adapter.py` (new)

### Interfaces Layer
- `backend/app/interfaces/schemas/deal_finder.py` (new)
- `backend/app/interfaces/api/deal_finder_routes.py` (new)

### Configuration
- `backend/app/core/config_deal_finder.py` (new) — Feature flags, thresholds, API keys, trust tiers.

### Tests
- `backend/tests/domain/models/test_deal_models.py` (new)
- `backend/tests/domain/services/deals/test_deal_query_planner.py` (new)
- `backend/tests/domain/services/deals/test_deal_discovery.py` (new)
- `backend/tests/domain/services/deals/test_deal_fetch_policy.py` (new)
- `backend/tests/domain/services/deals/test_offer_extraction.py` (new)
- `backend/tests/domain/services/deals/test_deal_normalization.py` (new)
- `backend/tests/domain/services/deals/test_deal_deduplication.py` (new)
- `backend/tests/domain/services/deals/test_deal_scoring.py` (new)
- `backend/tests/domain/services/deals/test_deal_quality_gate.py` (new)
- `backend/tests/infrastructure/deals/test_amazon_creators_adapter.py` (new)
- `backend/tests/infrastructure/deals/test_bestbuy_adapter.py` (new)
- `backend/tests/infrastructure/deals/test_reddit_deal_adapter.py` (new)
- `backend/tests/interfaces/api/test_deal_finder_routes.py` (new)

### Fixtures
- `backend/tests/fixtures/deals/` (new directory)
  - `amazon_product_jsonld.html` — Rich JSON-LD Amazon product page
  - `bestbuy_product_jsonld.html` — Best Buy product page
  - `walmart_product_microdata.html` — Microdata-only page
  - `reddit_buildapcsales_posts.json` — r/buildapcsales post samples
  - `unknown_merchant_no_markup.html` — Poor markup page
  - `aggregate_offer_multi_seller.html` — AggregateOffer with multiple sellers
  - `missing_shipping_details.html` — Page without shippingDetails

## 16. New Dependencies (v1)

| Package | Purpose | Self-Hosted? | License |
|---------|---------|-------------|---------|
| `extruct` | JSON-LD/Microdata/RDFa extraction from HTML | N/A (Python lib) | BSD-3 |
| `frankfurter` | Currency conversion API | Yes (Docker) | MIT |
| `praw` / `asyncpraw` | Reddit API client (OAuth2) | N/A (Python lib) | BSD-2 |

**Note**: `extruct` depends on `w3lib` and `html-metadata-parser`. All BSD/MIT licensed.

## 17. Decision Gates Before Implementation

1. Confirm v1 vertical scope: all ecommerce vs narrowed category (e.g., electronics only).
2. Confirm freshness defaults: ranking window and top-pick recency badge policy.
3. Confirm whether alerts are v1 or v1.1.
4. Confirm whether SearXNG is enabled in v1 provider chain (note: no built-in shopping engines).
5. Confirm initial metric thresholds and regression block policy.
6. Confirm idempotency-key behavior for `POST /api/deals/search`.
7. **NEW**: Confirm Amazon Creators API enrollment timeline (PA-API deprecated April 30, 2026).
8. **NEW**: Confirm Best Buy API key acquisition.
9. **NEW**: Confirm Reddit API app registration (free tier, OAuth2).
10. **NEW**: Confirm Frankfurter API self-hosting (Docker one-liner: `docker run -d -p 80:8080 lineofflight/frankfurter`).
11. **NEW**: Confirm `extruct` library approval for JSON-LD extraction.
12. **NEW**: Confirm trust tier assignments for target merchants.

## References

### Standards & Specifications
- RFC 9309 (Robots Exclusion Protocol): https://datatracker.ietf.org/doc/html/rfc9309
- Schema.org Offer: https://schema.org/Offer
- Schema.org `shippingDetails`: https://schema.org/shippingDetails
- Schema.org `hasMerchantReturnPolicy`: https://schema.org/hasMerchantReturnPolicy
- Schema.org `gtin`: https://schema.org/gtin

### Google Guidelines
- Google Product snippet structured data: https://developers.google.com/search/docs/appearance/structured-data/product-snippet
- Google ecommerce structured data guidance: https://developers.google.com/search/docs/specialty/ecommerce/share-your-product-data-with-google
- Google Search Central update (Jan 2025): https://developers.google.com/search/blog/2025/01/search-updates-january-2025
- Google Search Central update (Jun 2025): https://developers.google.com/search/blog/2025/06/search-updates-june-2025
- Google Developer Blog (Nov 12, 2025 shipping/returns update): https://developers.googleblog.com/en/expanding-structured-data-support-for-merchant-listings/

### FTC Compliance
- FTC Endorsement Guides: https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides
- FTC Consumer Reviews Rule Q&A: https://www.ftc.gov/business-guidance/resources/consumer-reviews-testimonials-rule-questions-answers
- FTC Rule on the Use of Consumer Reviews and Testimonials (effective Oct 21, 2024): https://www.ftc.gov/news-events/news/press-releases/2024/08/federal-trade-commission-rule-combating-fake-consumer-reviews-testimonials-goes-effect
- 16 CFR 255.5 - Disclosure of Material Connections: https://www.law.cornell.edu/cfr/text/16/255.5

### Provider APIs
- Amazon Creators API (replaces PA-API 5.0): https://affiliate-program.amazon.com/creatorsapi/docs/en-us/introduction
- Amazon PA-API 5.0 (deprecated April 30, 2026): https://webservices.amazon.com/paapi5/documentation/
- Amazon PA-API OffersV2: https://webservices.amazon.com/paapi5/documentation/offersV2.html
- Best Buy Developer API: https://bestbuyapis.github.io/api-documentation/
- Best Buy Developer Portal: https://developer.bestbuy.com/
- Best Buy Affiliate Program: https://www.bestbuy.com/site/misc/best-buy-affiliate-program/pcmcat198500050002.c
- Reddit Data API: https://www.reddit.com/dev/api/
- r/buildapcsales: https://www.reddit.com/r/buildapcsales/
- SearXNG Search API: https://docs.searxng.org/dev/search_api.html

### Libraries & Tools
- extruct (structured data extraction): https://github.com/scrapinghub/extruct
- Frankfurter (self-hosted currency API): https://frankfurter.dev/
- asyncpraw (async Reddit client): https://asyncpraw.readthedocs.io/
- scikit-learn `ndcg_score`: https://scikit-learn.org/stable/modules/generated/sklearn.metrics.ndcg_score.html

### Framework Documentation (Context7 Validated)
- FastAPI APIRouter composition: https://fastapi.tiangolo.com/tutorial/bigger-applications/
- FastAPI BackgroundTasks: https://fastapi.tiangolo.com/tutorial/background-tasks/
- Pydantic v2 validators: https://docs.pydantic.dev/latest/concepts/validators/
- Pydantic v2 discriminated unions: https://docs.pydantic.dev/latest/concepts/unions/

### Research & Industry
- Product Deduplication with Multimodal Embeddings (arXiv): https://arxiv.org/abs/2509.15858
- Google Merchant Center GTIN Guidelines: https://support.google.com/merchants/answer/160161
- GTIN/UPC for Google Shopping 2025: https://www.marpipe.com/blog/what-is-a-gtin-for-google-shopping-2025-guide-for-ecommerce-sellers
- Ecommerce Product Data Matching Services: https://www.suntecindia.com/ecommerce-product-data-matching-services.html
- Walmart Product Matching (Deep Learning): https://medium.com/walmartglobaltech/product-matching-in-ecommerce-4f19b6aebaca
