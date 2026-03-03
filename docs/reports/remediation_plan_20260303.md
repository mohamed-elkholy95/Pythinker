# Session Anomaly Remediation Plan

**Date:** March 3, 2026
**Based on:** `session_monitoring_report_20260303.md`
**Validated against:** Context7 MCP (FastAPI, Pydantic Settings, Redis, pytest)
**Anomalies addressed:** 10 (3 CRITICAL, 4 HIGH, 2 MEDIUM, 1 LOW)

---

## Remediation Summary

| ID | Anomaly | Priority | Effort | Type | Files Changed |
|----|---------|----------|--------|------|---------------|
| R1 | Serper API key exhaustion + budget alerting | P0 | Config + Code | Resilience | 3 |
| R2 | FAST_MODEL not configured (circuit breaker no-op) | P0 | Config | Config | 1 |
| R3 | LettuceDetect model TTL eviction | P1 | Code | Memory | 1 |
| R4 | File-write content-loss detection | P1 | Code | Correctness | 2 |
| R5 | Hallucination span logging for FP review | P1 | Code | Observability | 2 |
| R6 | BM25 lazy-fit on first query | P2 | Code | Search quality | 1 |
| R7 | Smart-compaction threshold tuning | P2 | Config + Code | Context mgmt | 2 |
| R8 | GLM-5 tool-call validation guard | P1 | Code | Correctness | 1 |
| R9 | Screencast WebSocket log noise reduction | P3 | Code | Logging | 2 |
| R10 | Streaming call ERROR threshold adjustment | P3 | Config | Logging | 1 |

---

## P0: Immediate Configuration Fixes

### R1: Serper API Key Exhaustion + Budget Alerting

**Anomaly:** All 6 Serper keys returned HTTP 400 ("Not enough credits") within 2 minutes. Agent fell back to slow browser-based scraping.

**Root cause:** Monthly credit quota exhausted across all keys. No proactive alerting before exhaustion.

**Current implementation:** `key_pool.py` marks keys EXHAUSTED with 1800s TTL. The `search_provider_policy.py` defines `DEFAULT_SEARCH_PROVIDER_CHAIN = ("serper", "brave", "tavily", "exa")` but Brave keys are not configured.

#### Fix 1a: Configure backup search provider keys

**File:** `.env`
```bash
# Add Brave Search as first fallback (free tier: 2000 queries/mo)
BRAVE_API_KEY=<key1>
BRAVE_API_KEY_2=<key2>

# Replenish Serper credits OR add more keys
SERPER_API_KEY_7=<key>  # If budget allows
```

**Rationale:** The fallback chain (`serper → brave → tavily → exa`) only works if fallback providers have valid keys. Brave Search offers a generous free tier (2,000 queries/month) suitable as a backup.

#### Fix 1b: Key budget alerting via health check

**File:** `backend/app/infrastructure/external/key_pool.py`

Add a method that reports key pool health at the pool level, not just per-key. The existing `_health_by_key` dict tracks individual states, but there's no aggregate warning when pool capacity drops below a threshold.

```python
# Add to KeyPool class

async def check_pool_health(self) -> dict[str, Any]:
    """Return pool-level health metrics for monitoring."""
    total = len(self._keys)
    healthy = sum(1 for h in self._health_by_key.values() if h.state == KeyState.HEALTHY)
    exhausted = sum(1 for h in self._health_by_key.values() if h.state == KeyState.EXHAUSTED)
    invalid = sum(1 for h in self._health_by_key.values() if h.state == KeyState.INVALID)

    health_ratio = healthy / total if total > 0 else 0.0

    if health_ratio <= 0.0:
        logger.critical(
            "[%s] ALL keys exhausted (%d/%d). Search degraded to fallback chain.",
            self._provider, exhausted, total,
        )
    elif health_ratio <= 0.25:
        logger.warning(
            "[%s] Key pool critically low: %d/%d healthy, %d exhausted.",
            self._provider, healthy, total, exhausted,
        )

    return {
        "provider": self._provider,
        "total": total,
        "healthy": healthy,
        "exhausted": exhausted,
        "invalid": invalid,
        "health_ratio": health_ratio,
    }
```

**File:** `backend/app/domain/services/tools/search.py`

Call `check_pool_health()` after each key exhaustion event, not just on rotation. This surfaces the aggregate state.

**File:** `backend/app/infrastructure/external/prometheus_metrics.py`

Add gauge:
```python
search_key_pool_healthy_keys = Gauge(
    "pythinker_search_key_pool_healthy_keys",
    "Number of healthy API keys per search provider",
    ["provider"],
)
```

**Validation:** Context7/Redis docs confirm Lua-based rate limiting is the right pattern for distributed key state. The existing `rate_governor.py` already uses Redis Lua scripts — this extension follows the same pattern.

---

### R2: FAST_MODEL Not Configured (Circuit Breaker No-Op)

**Anomaly:** Slow tool-call circuit breaker tripped 5 times but `FAST_MODEL` is empty, so no model switch occurred. 27% of LLM calls exceeded 30s.

**Root cause:** `config_llm.py` defines `fast_model: str = ""` (empty default). The circuit breaker in `openai_llm.py` correctly detects slow calls but `_resolve_distinct_fast_model()` returns `""` when unconfigured.

#### Fix: Set FAST_MODEL in .env

**File:** `.env`
```bash
# Circuit breaker fallback — MUST differ from primary MODEL_NAME
FAST_MODEL=claude-haiku-4-5-20251001
```

**Why `claude-haiku-4-5-20251001`:**
- Already documented in CLAUDE.md as the recommended fast model
- Native tool-calling support (unlike GLM-5)
- ~3-5s response times (vs GLM-5's 20-55s average)
- Resolves anomalies #4 (circuit breaker effectiveness) and partially #3 (tool-calling reliability during fallback)

**Validation:** The existing `_resolve_slow_tool_breaker_model()` in `openai_llm.py` (lines 286-328) already validates that FAST_MODEL differs from the primary model. No code changes needed — pure configuration fix.

**Risk:** Cross-provider routing (GLM-5 primary → Claude Haiku fallback) requires both providers to be configured. Verify `ANTHROPIC_API_KEY` is set in `.env`.

---

## P1: Code Fixes (Correctness + Memory)

### R3: LettuceDetect Model TTL Eviction

**Anomaly:** Backend memory grew 3.8x (566 MiB → 2.13 GiB). The LettuceDetect model (~300-500 MiB) is loaded once via singleton and never released.

**Current implementation:** `lettuce_verifier.py` uses a module-level `_verifier_instance` singleton with `get_lettuce_verifier()`. The model loads lazily on first `verify()` call and persists indefinitely.

**Best practice (Context7/FastAPI):** FastAPI's lifespan pattern shows explicit resource cleanup:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    ml_models["model"] = load_model()
    yield
    ml_models.clear()  # Clean up on shutdown
```

#### Fix: Add TTL-based eviction to the singleton

**File:** `backend/app/domain/services/agents/lettuce_verifier.py`

Replace the bare singleton with a time-aware wrapper that unloads after idle period:

```python
import time
import threading

_TTL_SECONDS: float = 300.0  # 5 minutes idle → unload

class _VerifierHolder:
    """Thread-safe singleton with TTL-based eviction."""

    def __init__(self) -> None:
        self._instance: LettuceVerifier | None = None
        self._last_used: float = 0.0
        self._lock = threading.Lock()
        self._eviction_timer: threading.Timer | None = None

    def get(self) -> LettuceVerifier:
        with self._lock:
            if self._instance is None:
                self._instance = self._create()
            self._last_used = time.monotonic()
            self._schedule_eviction()
            return self._instance

    def _create(self) -> LettuceVerifier:
        from app.core.config import get_settings
        settings = get_settings()
        return LettuceVerifier(
            model_path=settings.lettuce_model_path,
            confidence_threshold=settings.lettuce_confidence_threshold,
            min_response_length=settings.lettuce_min_response_length,
        )

    def _schedule_eviction(self) -> None:
        if self._eviction_timer is not None:
            self._eviction_timer.cancel()
        self._eviction_timer = threading.Timer(_TTL_SECONDS, self._try_evict)
        self._eviction_timer.daemon = True
        self._eviction_timer.start()

    def _try_evict(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_used
            if elapsed >= _TTL_SECONDS and self._instance is not None:
                logger.info(
                    "LettuceDetect model idle for %.0fs, unloading to free memory",
                    elapsed,
                )
                # Release model reference; GC + PyTorch will free GPU/CPU memory
                self._instance._detector = None
                self._instance = None

_holder = _VerifierHolder()

def get_lettuce_verifier() -> LettuceVerifier:
    return _holder.get()
```

**Impact:** ~300-500 MiB freed after 5 minutes of inactivity. Model reloads in ~5.7s on next verification (acceptable — occurs once per step).

**Test:** Add a unit test that verifies eviction fires and `_instance` becomes `None` after TTL expires.

```python
# tests/domain/services/agents/test_lettuce_eviction.py
def test_verifier_evicts_after_ttl(monkeypatch):
    monkeypatch.setattr("app.domain.services.agents.lettuce_verifier._TTL_SECONDS", 0.1)
    holder = _VerifierHolder()
    # Mock create to avoid real model load
    holder._create = lambda: MagicMock(spec=LettuceVerifier)
    instance = holder.get()
    assert holder._instance is not None
    time.sleep(0.3)
    assert holder._instance is None
```

---

### R4: File-Write Content-Loss Detection

**Anomaly:** Report went from 18,031 bytes (v4) to 10,056 bytes (v5) — a 44% content regression. The agent called `file_write` (overwrite) instead of `file_str_replace` (patch), losing content.

**Current implementation:** `file.py` tracks recent writes in `_recent_writes` (5-minute window, 256 entries) for read-after-write retry. But it does NOT compare file sizes between consecutive writes to the same path.

#### Fix: Detect and warn on content regression

**File:** `backend/app/domain/services/tools/file.py`

Add size regression detection to the file_write handler:

```python
# Add to the class that handles file_write

_recent_write_sizes: dict[str, int] = {}  # path → last known byte size

async def _check_content_regression(
    self, path: str, new_content: str
) -> str | None:
    """Return a warning string if new content is significantly smaller."""
    new_size = len(new_content.encode("utf-8"))
    prev_size = self._recent_write_sizes.get(path)

    if prev_size is not None and prev_size > 500:  # Only check non-trivial files
        shrink_ratio = new_size / prev_size
        if shrink_ratio < 0.6:  # >40% content loss
            warning = (
                f"WARNING: file_write to '{path}' would shrink content from "
                f"{prev_size:,} to {new_size:,} bytes ({shrink_ratio:.0%}). "
                f"Consider using file_str_replace to patch instead of overwrite."
            )
            logger.warning(warning)
            self._recent_write_sizes[path] = new_size
            return warning

    self._recent_write_sizes[path] = new_size
    return None
```

**File:** `backend/app/domain/services/agents/execution.py` (or wherever tool results are processed)

Surface the warning in the tool result so the LLM sees it:

```python
regression_warning = await self._check_content_regression(path, content)
if regression_warning:
    tool_result = f"{tool_result}\n\n{regression_warning}"
```

**Rationale:** The agent doesn't have visibility into file size history. By surfacing regression warnings in the tool result, the LLM can self-correct in the next turn. This follows the existing pattern where the tool efficiency monitor injects nudges into the conversation.

**Validation:** The existing `_recent_writes` dict in `file.py` already tracks paths with timestamps. This adds size tracking to the same pattern.

---

### R5: Hallucination Span Logging for FP Review

**Anomaly:** LettuceDetect flagged 44.8%-52.1% hallucination rate on research steps, but we don't know if these are false positives (paraphrased source material) or true hallucinations.

**Current implementation:** `lettuce_verifier.py` returns `LettuceVerificationResult` with `hallucinated_spans: list[HallucinatedSpan]` (text, confidence, start/end positions). These are processed in `output_verifier.py` but the specific span text is not persisted for later review.

#### Fix: Log spans to structured events

**File:** `backend/app/domain/services/agents/output_verifier.py`

After verification, emit span details as a structured log entry (not just count/ratio):

```python
if result.has_hallucinations:
    for span in result.hallucinated_spans:
        logger.info(
            "Hallucinated span detected | step=%s | confidence=%.2f | "
            "text_preview=%.200s | position=%d-%d",
            step_id,
            span.confidence,
            span.text,  # First 200 chars via format spec
            span.start,
            span.end,
        )
```

**File:** `backend/app/infrastructure/external/prometheus_metrics.py`

Add histogram for hallucination confidence distribution:
```python
hallucination_span_confidence = Histogram(
    "pythinker_hallucination_span_confidence",
    "Confidence scores of detected hallucination spans",
    ["model", "step_type"],
    buckets=[0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)
```

**Outcome:** Enables post-hoc analysis of FP rate by model. If GLM-5 consistently produces spans at 0.5-0.6 confidence on paraphrased research content, the `lettuce_confidence_threshold` (currently 0.8) can be validated or adjusted per-model.

---

### R8: GLM-5 Tool-Call Validation Guard

**Anomaly:** GLM-5 returned `tools=no` but the balanced-brace parser extracted tool calls from prose. In at least one case, extracted `file_write` was missing required parameters.

**Current implementation:** `openai_llm.py` falls back to prompt-based JSON + balanced-brace extraction when the provider doesn't support native tool-calling. The extracted JSON is passed through `json_repair` but there's no schema validation against the tool's required parameters.

#### Fix: Validate extracted tool calls against tool schema before execution

**File:** `backend/app/infrastructure/external/llm/openai_llm.py`

After balanced-brace extraction and JSON repair, validate required fields:

```python
def _validate_extracted_tool_call(
    self,
    tool_call: dict[str, Any],
    available_tools: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Validate that a text-extracted tool call has required parameters.

    Returns (is_valid, error_message).
    """
    tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name")
    if not tool_name:
        return False, "Missing tool name in extracted call"

    arguments = tool_call.get("arguments") or tool_call.get("function", {}).get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return False, f"Unparseable arguments for {tool_name}"

    # Find matching tool schema
    tool_schema = None
    for tool in available_tools:
        fn = tool.get("function", {})
        if fn.get("name") == tool_name:
            tool_schema = fn.get("parameters", {})
            break

    if tool_schema is None:
        return False, f"Unknown tool: {tool_name}"

    # Check required parameters
    required = tool_schema.get("required", [])
    missing = [p for p in required if p not in arguments]
    if missing:
        return False, f"Tool {tool_name} missing required params: {missing}"

    return True, ""
```

Add a Prometheus counter for tracking:
```python
tool_parse_fallback_total = Counter(
    "pythinker_tool_parse_fallback_total",
    "Tool calls extracted via text parsing (not native API)",
    ["model", "valid"],
)
```

**Impact:** Prevents execution of malformed tool calls. Invalid calls are logged and skipped, reducing downstream errors. The counter tracks how often text-based parsing produces valid vs invalid calls per model — data for deciding whether to keep using GLM-5 for tool-heavy tasks.

---

## P2: Search Quality + Context Management

### R6: BM25 Lazy-Fit on First Query

**Anomaly:** BM25 encoder logged "not fitted; returning empty sparse vector" at startup, degrading hybrid search to dense-only.

**Current implementation:** `bm25_encoder.py` has a `fit(corpus)` method called during app startup. If the memory collection is empty (no prior memories), the encoder remains unfitted. The `encode()` method returns an empty dict when unfitted.

#### Fix: Lazy-fit on first query with seed corpus

**File:** `backend/app/domain/services/embeddings/bm25_encoder.py`

```python
# Modify encode() to lazy-fit if unfitted

_SEED_CORPUS: list[str] = [
    "user preference setting configuration",
    "search query web research information",
    "code implementation function class method",
    "error bug fix debug troubleshoot",
    "file document report summary analysis",
    "task plan step workflow process",
]

def encode(self, text: str) -> dict[int, float]:
    """Encode text to sparse vector. Lazy-fits on seed corpus if unfitted."""
    if not self._is_fitted:
        logger.info("BM25 encoder unfitted — lazy-fitting on seed corpus (%d docs)", len(_SEED_CORPUS))
        self.fit(_SEED_CORPUS)
        # The seed corpus provides minimal vocabulary coverage.
        # Real documents added via incremental_fit() will improve quality.

    if not self._is_fitted:
        return {}  # fit() failed — graceful degradation

    # ... existing encode logic ...
```

**Rationale:** A seed corpus ensures BM25 always produces non-empty sparse vectors, even on first boot with empty memory. As real documents are added via `incremental_fit()`, the vocabulary improves naturally. The seed terms cover common query patterns in an agent system.

**Test:**
```python
def test_bm25_lazy_fit_on_empty_startup():
    encoder = BM25Encoder()
    assert not encoder._is_fitted
    result = encoder.encode("search query")
    assert encoder._is_fitted
    assert len(result) > 0  # Non-empty sparse vector
```

---

### R7: Smart-Compaction Threshold Tuning

**Anomaly:** Context compression triggered at 96.5% budget — too late. It only freed ~10% before climbing back to 91.1%.

**Current implementation:** The context compression pipeline triggers based on token budget percentage. The current threshold appears to be near the exhaustion point (~95%).

#### Fix: Lower trigger threshold + add incremental compression

**File:** `backend/app/core/config_features.py`

Add configurable threshold:
```python
# Context compression
context_compression_trigger_pct: float = 0.80  # Trigger at 80% (was ~95%)
context_compression_target_pct: float = 0.65   # Compress down to 65%
```

**File:** `backend/app/domain/services/agents/execution.py` (or wherever budget is checked)

Replace the single-shot compression with a two-stage approach:

```python
budget_pct = self._token_budget.usage_ratio()

if budget_pct >= settings.context_compression_trigger_pct:
    # Stage 1: Summarize verbose tool outputs (cheap, preserves intent)
    compressed = await self._compressor.compress(
        messages=self._messages,
        strategy="summarize",
        target_ratio=settings.context_compression_target_pct,
    )

    if self._token_budget.usage_ratio() >= 0.90:
        # Stage 2: Truncate + drop old messages (aggressive, loses detail)
        compressed = await self._compressor.compress(
            messages=compressed,
            strategy="truncate_and_drop",
            target_ratio=settings.context_compression_target_pct,
        )
```

**Rationale:** Triggering at 80% gives the system headroom. The two-stage approach (summarize first, truncate only if needed) preserves more context detail. The existing 3-stage pipeline (summarize → truncate → drop) already supports this — it just needs to trigger earlier.

**Validation:** The report rewriting loop (Anomaly #5) was a major contributor to context bloat. Fixing R4 (content-loss detection) will also reduce context pressure by preventing the agent from wasting turns rebuilding lost content.

---

## P3: Logging + UX Fixes

### R9: Screencast WebSocket Log Noise Reduction

**Anomaly:** ~180 WebSocket reconnection cycles generated ~1,200 log lines during the 20-minute session. Each reconnect produces 6-8 lines (POST signed-url, WS accept, connected, frames, disconnected).

**Current implementation:** Backend logs every WebSocket accept/disconnect at INFO level. The frontend reconnects every 15-20s (expected behavior — backend PING interval is 20s with 10s PONG timeout).

**Important finding from exploration:** The reconnection is actually working as designed. The backend uses `ping_interval=20, ping_timeout=10` (RFC 6455 compliant). The frontend has a 120s stall timeout. The 15-20s cycle suggests the WebSocket is being closed by the sandbox side (not the frontend or backend).

#### Fix: Reduce log level for routine screencast reconnections

**File:** `backend/app/interfaces/api/session_routes.py`

```python
# In the screencast_websocket handler, change routine connect/disconnect to DEBUG

# Connection established
logger.debug("Screencast WebSocket connected for session %s", session_id)

# Normal close (code 1000, 1001) → DEBUG
# Abnormal close (other codes) → WARNING
if close_code in (1000, 1001, None):
    logger.debug("Screencast WebSocket closed normally for session %s (code=%s)", session_id, close_code)
else:
    logger.warning("Screencast WebSocket closed abnormally for session %s (code=%s, reason=%s)", session_id, close_code, close_reason)
```

**File:** `backend/app/interfaces/api/session_routes.py` (signed-url endpoint)

```python
# Signed URL generation for screencast → DEBUG (high-frequency, routine)
logger.debug("Signed URL generated for %s/%s", session_id, target)
```

**Impact:** Reduces screencast log volume by ~90% during normal operation. Abnormal closes still logged at WARNING for debugging.

---

### R10: Streaming Call ERROR Threshold Adjustment

**Anomaly:** `ask_stream()` took 135.6s and logged at ERROR level. But the streaming TTFT was 8.5s (acceptable UX) and the throughput was ~35 tokens/sec (normal for GLM-5). The total time is a function of output length, not a performance problem.

**Current implementation:** `openai_llm.py` logs at ERROR when duration exceeds 2x the `llm_slow_request_threshold` (45s × 2 = 90s).

#### Fix: Use separate threshold for streaming calls

**File:** `backend/app/core/config_llm.py`

```python
# Add streaming-specific threshold
llm_slow_stream_threshold: float = 180.0  # 3 minutes for streaming (vs 45s for non-streaming)
```

**File:** `backend/app/infrastructure/external/llm/openai_llm.py`

In the `ask_stream()` completion logging, use the streaming threshold:

```python
stream_threshold = self._settings.llm_slow_stream_threshold

if duration > stream_threshold * 2:
    logger.error("LLM ask_stream() completed in %.1fs (>%.0fs)", duration, stream_threshold * 2)
elif duration > stream_threshold:
    logger.warning("LLM ask_stream() completed in %.1fs (>%.0fs)", duration, stream_threshold)
else:
    logger.info("LLM ask_stream() completed in %.1fs", duration)
```

**Rationale:** Streaming calls are inherently longer because they generate full documents (10K-24K chars). A 135s streaming call at 35 tok/s is normal. The current shared threshold causes false ERROR alerts that obscure real problems.

---

## Cross-Cutting Recommendation: GLM-5 Evaluation

Anomalies #2, #3, #4, #5, #6 are all symptoms of using GLM-5 for a tool-heavy research workflow:

| Issue | GLM-5 | Claude/GPT-4 |
|-------|-------|-------------|
| Tool-calling | Text-based JSON (fragile) | Native API (reliable) |
| Avg latency | 20.8s | 3-8s |
| Hallucination rate | 44-52% (LettuceDetect) | Expected <20% |
| Report stability | 8 rewrites, content regression | Typically 1-2 writes |
| Context efficiency | High token waste (verbose JSON) | Structured output (compact) |

**Recommendation:** Run a comparative evaluation:
1. Execute the same research task ("AI Agents comprehensive report") with Claude Sonnet and GLM-5
2. Measure: wall-clock time, LLM calls, tool-call success rate, LettuceDetect scores, report quality
3. Use the `adaptive_model_selection_enabled` flag to route research tasks to `POWERFUL_MODEL` (Claude Sonnet) while keeping GLM-5 for simpler tasks

This is not a code fix but a strategic decision that would eliminate 6 of 10 anomalies.

---

## Implementation Sequence

```
Week 1 (P0 — Config):
  ├── R2: Set FAST_MODEL=claude-haiku-4-5-20251001 in .env          [5 min]
  ├── R1a: Add Brave Search API keys to .env                        [10 min]
  └── R1b: Add key pool health check + Prometheus gauge             [1 hr]

Week 1 (P1 — Code):
  ├── R3: LettuceDetect TTL eviction (_VerifierHolder)              [2 hr]
  ├── R4: File-write content-loss detection                         [1.5 hr]
  ├── R5: Hallucination span structured logging                     [1 hr]
  └── R8: Tool-call schema validation guard                         [2 hr]

Week 2 (P2 — Quality):
  ├── R6: BM25 lazy-fit with seed corpus                            [1 hr]
  └── R7: Smart-compaction threshold (80% trigger, 65% target)      [1.5 hr]

Week 2 (P3 — Polish):
  ├── R9: Screencast WebSocket log level → DEBUG                    [30 min]
  └── R10: Streaming call separate ERROR threshold                  [30 min]

Week 3 (Strategic):
  └── GLM-5 vs Claude comparative evaluation                       [4 hr]
```

---

## Testing Strategy

Each fix requires:

1. **Unit test** — validates the fix logic in isolation
2. **Integration test** — validates the fix within the pipeline
3. **Regression guard** — ensures the anomaly doesn't recur

| Fix | Unit Test | Integration Test |
|-----|-----------|-----------------|
| R1b | `test_key_pool_health_check()` — pool with 0/6 healthy keys logs CRITICAL | `test_search_fallback_on_exhaustion()` — verify chain fallback |
| R3 | `test_verifier_evicts_after_ttl()` — mock timer fires, instance cleared | `test_memory_after_eviction()` — RSS drops after idle period |
| R4 | `test_content_regression_detected()` — 18K→10K returns warning | `test_agent_sees_regression_warning()` — warning in tool result |
| R5 | `test_spans_logged_with_text()` — structured log contains span preview | N/A (observability only) |
| R6 | `test_bm25_lazy_fit_on_empty()` — unfitted encoder produces vectors | `test_hybrid_search_with_seed_corpus()` — non-empty sparse results |
| R7 | `test_compression_triggers_at_80pct()` — verify threshold respected | `test_two_stage_compression()` — summarize before truncate |
| R8 | `test_validate_extracted_tool_call()` — missing params rejected | `test_glm5_invalid_tool_call_skipped()` — bad call not executed |
| R9 | N/A (log level change) | Verify log volume reduction in staging |
| R10 | N/A (threshold change) | Verify streaming calls log at INFO not ERROR |

---

## Monitoring & Verification

After deploying all fixes, run a monitoring session identical to the one that produced the anomalies:

1. **Same task:** "Research AI Agents — comprehensive report"
2. **Same model:** GLM-5 (to verify fixes work with the same model)
3. **Monitor:** Backend logs, container stats, Prometheus metrics
4. **Success criteria:**

| Metric | Before (Anomaly Session) | Target |
|--------|--------------------------|--------|
| Search failures before fallback | 5 | 0-1 |
| Circuit breaker model switch | 0 (no-op) | >0 (successful switch) |
| Backend peak memory | 2.13 GiB | <1.5 GiB (TTL eviction) |
| Report rewrites | 8 (with regression) | <4 (no regression) |
| Hallucination FP data | None (no span logging) | Spans logged for review |
| BM25 unfitted warnings | 1 | 0 |
| Compression trigger point | 96.5% | ~80% |
| Screencast log lines | ~1,200 | <200 |
| Streaming ERROR alerts | 1 (false positive) | 0 |

---

## References

- **Monitoring Report:** `docs/reports/session_monitoring_report_20260303.md`
- **FastAPI Lifespan (Context7):** Resource cleanup via `@asynccontextmanager` — applied to R3
- **Redis Lua Scripting (Context7):** Atomic rate limiting — validates existing `rate_governor.py` pattern (R1b)
- **Pydantic Settings (Context7):** `SettingsConfigDict` patterns — validates existing config approach (R7, R10)
- **Circuit Breaker Code:** `openai_llm.py` lines 232-328 — R2 is config-only, no code change needed
- **File Tool:** `file.py` recent-write tracking pattern — extended for R4
- **LettuceDetect:** `lettuce_verifier.py` singleton pattern — replaced with TTL holder for R3
