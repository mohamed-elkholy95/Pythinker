# Jina + Multi-Provider Search Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate Jina AI into the existing search stack so the app can use `jina` alongside `tavily`, `duckduckgo`, and `serper`, with optional Jina reranking for higher relevance.

**Architecture:** Keep the current provider-chain/fallback model intact and add Jina as a first-class provider in the same registry pattern. Then add an optional post-search rerank step (feature-flagged) that calls Jina Reranker API on returned result snippets. This minimizes risk, preserves current behavior by default, and enables incremental rollout.

**Tech Stack:** FastAPI, Pydantic v2, httpx, existing SearchProviderRegistry + APIKeyPool patterns, Vue 3 settings UI, pytest, ruff, bun lint/type-check.

---

## Scope and assumptions

- Existing default search chain remains `tavily -> duckduckgo -> serper` unless explicitly reconfigured.
- `jina` is added as an optional provider in chain and UI selector.
- Jina API auth uses `Authorization: Bearer <JINA_API_KEY>`.
- Reranking is optional (`feature flag`), not mandatory for initial provider support.

## Official docs and references used for this plan

- Tavily Search API: https://docs.tavily.com/documentation/api-reference/endpoint/search
- Jina Reader repo/usage (`r.jina.ai`, `s.jina.ai`): https://github.com/jina-ai/reader
- Jina API endpoint reference (including `/v1/rerank`): https://raw.githubusercontent.com/jina-ai/meta-prompt/main/v5.txt
- Serper official site/API product page: https://serper.dev/
- DuckDuckGo Instant Answer API context (not full web SERP): https://www.postman.com/api-evangelist/duckduckgo/documentation/i9r819s/duckduckgo-instant-answer-api
- Current app search factory and providers:
  - `backend/app/infrastructure/external/search/factory.py`
  - `backend/app/infrastructure/external/search/tavily_search.py`
  - `backend/app/infrastructure/external/search/serper_search.py`
  - `backend/app/infrastructure/external/search/duckduckgo_search.py`

---

### Task 1: Add `jina` to provider policy and settings normalization

**Files:**
- Modify: `backend/app/core/search_provider_policy.py`
- Modify: `backend/tests/interfaces/schemas/test_settings_schema_search_provider_chain.py`
- Modify: `backend/tests/application/services/test_settings_service_caching.py`

**Step 1: Write failing tests for allowlist normalization**

```python
def test_update_user_settings_request_accepts_jina_in_chain() -> None:
    request = UpdateUserSettingsRequest(search_provider_chain=["jina", "duckduckgo", "unknown"])
    assert request.search_provider_chain == ["jina", "duckduckgo"]
```

**Step 2: Run tests to confirm failure**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces/schemas/test_settings_schema_search_provider_chain.py -v`
Expected: FAIL because `jina` is filtered out.

**Step 3: Implement minimal policy update**

Add `"jina"` to `ALLOWED_SEARCH_PROVIDERS` in `search_provider_policy.py`.

**Step 4: Re-run tests**

Run same command.
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/core/search_provider_policy.py backend/tests/interfaces/schemas/test_settings_schema_search_provider_chain.py backend/tests/application/services/test_settings_service_caching.py
git commit -m "feat(search): allow jina in provider chain normalization"
```

---

### Task 2: Add Jina config fields to backend settings

**Files:**
- Modify: `backend/app/core/config_features.py`
- Modify: `backend/.env.example`
- Modify: `.env.example`
- Modify: `backend/README.md`

**Step 1: Write failing config loading test (if absent, add one)**

Create/extend settings tests to assert `jina_api_key` is loadable from env.

**Step 2: Run targeted tests**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_settings_service_caching.py -v`
Expected: FAIL (missing field path/usage).

**Step 3: Add config fields**

Add in `SearchSettingsMixin`:
- `jina_api_key: str | None = None`
- Optional fallback keys if desired: `jina_api_key_2.._5`

Add corresponding commented env entries and README note.

**Step 4: Re-run tests**

Expected: PASS for updated settings behavior.

**Step 5: Commit**

```bash
git add backend/app/core/config_features.py backend/.env.example .env.example backend/README.md
git commit -m "feat(config): add jina search api key settings"
```

---

### Task 3: Implement `JinaSearchEngine` provider

**Files:**
- Create: `backend/app/infrastructure/external/search/jina_search.py`
- Create: `backend/tests/infrastructure/external/search/test_jina_search.py`

**Step 1: Write failing tests first**

Cover:
- Request shape (`POST https://s.jina.ai/`, JSON body with `q`)
- Required headers (`Authorization`, `Accept: application/json`, `Content-Type`)
- Response parsing into `SearchResultItem` list
- Unauthorized/quota/error path handling

**Step 2: Run the new test file**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/search/test_jina_search.py -v`
Expected: FAIL because provider does not exist.

**Step 3: Implement provider using existing API provider patterns**

- Use `SearchEngineBase` and `@SearchProviderRegistry.register("jina")`
- Build request body with `{"q": query}` and optional date-hint suffix
- Parse Jina `data[]` items into `title/link/snippet`
- Reuse sanitization and robust error handling patterns from `exa_search.py` / `serper_search.py`

**Step 4: Re-run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/search/jina_search.py backend/tests/infrastructure/external/search/test_jina_search.py
git commit -m "feat(search): add jina search provider implementation"
```

---

### Task 4: Wire Jina provider into factory and fallback chain resolution

**Files:**
- Modify: `backend/app/infrastructure/external/search/factory.py`
- Modify: `backend/tests/infrastructure/external/search/test_search_factory_chain_policy.py`

**Step 1: Add failing factory test**

```python
def test_chain_can_include_jina_provider() -> None:
    ...
    assert [name for name, _ in engine._providers] == ["tavily", "jina", "duckduckgo"]
```

**Step 2: Run targeted factory tests**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/search/test_search_factory_chain_policy.py -v`
Expected: FAIL.

**Step 3: Implement wiring**

- Add provider import attempt for `jina_search`
- Extend `_provider_kwargs()` for `jina` with API key handling
- Preserve existing default chain behavior unless explicitly changed

**Step 4: Re-run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/search/factory.py backend/tests/infrastructure/external/search/test_search_factory_chain_policy.py
git commit -m "feat(search): register jina provider in factory chain"
```

---

### Task 5: Expose Jina in settings API and frontend selector

**Files:**
- Modify: `backend/app/interfaces/api/settings_routes.py`
- Modify: `backend/app/domain/models/user_settings.py`
- Modify: `frontend/src/components/settings/SearchSettings.vue`
- Modify: `frontend/src/api/settings.ts` (if type updates needed)

**Step 1: Add backend test coverage (or extend existing) for providers endpoint**

Assert `search_providers` includes `{"id": "jina", ...}`.

**Step 2: Run targeted backend tests**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces -v`
Expected: FAIL until backend list/model comments are updated.

**Step 3: Implement provider exposure**

- Add `jina` to `SEARCH_PROVIDERS` route list
- Update any search provider comments/enums in user settings model
- Add Jina description/icon/class mapping in Vue selector UI

**Step 4: Frontend verification**

Run:
- `cd frontend && bun run lint`
- `cd frontend && bun run type-check`

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/interfaces/api/settings_routes.py backend/app/domain/models/user_settings.py frontend/src/components/settings/SearchSettings.vue frontend/src/api/settings.ts
git commit -m "feat(settings): add jina provider to backend and frontend settings"
```

---

### Task 6: Add optional Jina reranker stage (feature-flagged)

**Files:**
- Create: `backend/app/infrastructure/external/search/jina_reranker.py`
- Modify: `backend/app/core/config_features.py`
- Modify: `backend/app/domain/services/tools/search.py`
- Create: `backend/tests/infrastructure/external/search/test_jina_reranker.py`
- Modify: `backend/tests/domain/services/tools/test_search_tool_error_reporting.py` (or nearest search tool behavior test)

**Step 1: Write failing reranker unit tests**

Cover:
- Input query + documents -> ordered indices/scores
- Top-N truncation
- Failure fallback returns original order

**Step 2: Run reranker tests**

Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/search/test_jina_reranker.py -v`
Expected: FAIL.

**Step 3: Implement minimal reranker + guarded integration**

- Add config flags (example):
  - `search_use_jina_rerank: bool = False`
  - `search_jina_rerank_top_n: int = 8`
- In search tool pipeline, rerank only when:
  - flag enabled
  - Jina key configured
  - result count >= 2
- On any rerank exception, log and return original ordering.

**Step 4: Re-run targeted tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/search/jina_reranker.py backend/app/core/config_features.py backend/app/domain/services/tools/search.py backend/tests/infrastructure/external/search/test_jina_reranker.py backend/tests/domain/services/tools/test_search_tool_error_reporting.py
git commit -m "feat(search): add optional jina reranker post-processing"
```

---

### Task 7: End-to-end regression verification

**Files:**
- No new files (verification task)

**Step 1: Run backend lint + format checks**

Run:
- `conda activate pythinker && cd backend && ruff check .`
- `conda activate pythinker && cd backend && ruff format --check .`

Expected: PASS.

**Step 2: Run backend tests**

Run: `conda activate pythinker && cd backend && pytest tests/`
Expected: PASS.

**Step 3: Run frontend checks**

Run:
- `cd frontend && bun run lint`
- `cd frontend && bun run type-check`

Expected: PASS.

**Step 4: Manual smoke test**

- Set `SEARCH_PROVIDER=jina` and valid `JINA_API_KEY`.
- Query from chat that triggers search tool.
- Confirm results rendered in UI and fallback chain works if provider fails.

**Step 5: Commit verification-only artifacts if needed**

```bash
# Usually no commit for verification alone unless snapshots/docs changed.
```

---

## Risk controls

- Preserve default provider chain to avoid unplanned behavior change.
- Keep Jina reranker behind a feature flag for incremental rollout.
- Fail-open design: reranker failures never block core search result delivery.
- Reuse existing `SearchEngineBase` + factory patterns to avoid new abstractions.

## Out of scope (this plan)

- Full multi-provider fan-out search with result merging in one request.
- Personalized ranking or learning-to-rank.
- Cost dashboards per provider (can be a follow-up).

