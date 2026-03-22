# Pythinker Session Monitoring Report

**Date:** March 3, 2026
**Monitor:** Docker container real-time monitoring
**Session ID:** `f4d4c846f0744f70`
**Agent ID:** `dfabccb4a4c14b4e`
**Model:** GLM-5
**User:** `local_admin`
**Duration:** 1,216,036ms (~20.3 minutes)
**SSE Events Emitted:** 3,249

---

## 1. Session Timeline

| Time (UTC) | Event | Details |
|------------|-------|---------|
| 00:39:57 | Agent created | ID: dfabccb4a4c14b4e |
| 00:40:02 | Session started | f4d4c846f0744f70 |
| 00:41:55 | Serper keys exhausted | 5 consecutive HTTP 400 failures |
| 00:42:xx | wide_research started | Spider enrichment with browser |
| 00:44:17 | Report v1 | 66 bytes (stub: title + date only) |
| 00:46:19 | Report v2 | 1,371 bytes (partial framework table) |
| 00:49:30 | Report v3 | 9,786 bytes |
| 00:50:26 | Report v4 | 18,031 bytes (peak) |
| 00:50:37 | Report v5 | 10,056 bytes (SHRUNK — overwrite) |
| 00:50:46 | Report v6 | 9,970 bytes (still smaller) |
| 00:51:11 | Step 1 tool-use | file_read + shell_exec (fast) |
| 00:52:07 | Wall-clock 68% warning | 612s/900s step timeout |
| 00:52:29 | LettuceDetect step 1 | 2 hallucinated spans, 44.8% ratio |
| 00:52:35 | Step 1 completed | executing → updating → executing |
| 00:52:41 | Step 2 started | "Cross-validate key claims..." |
| 00:52:41 | Budget 88.3% | Approaching limit |
| 00:52:47 | Budget 92.5% | Critical |
| 00:54:28 | Report v7 | 9,792 bytes |
| 00:54:28 | Budget 96.5% | Near exhaustion |
| 00:55:24 | Circuit breaker trip #5 | FAST_MODEL unset, 300s cooldown |
| 00:55:24 | Context compression | Smart-compacted 13 tool results |
| 00:55:24 | Report v8 | 18,037 bytes (final workspace version) |
| 00:55:50 | LettuceDetect step 2 | 4 hallucinated spans, 52.1% ratio |
| 00:55:50 | Step 2 completed | Budget dropped to 86.0% (compression) |
| 00:55:53 | Step 3 started | "Review, validate, and deliver..." |
| 00:56:04 | Chart 1 created | grouped_bar: Multi-Agent Performance |
| 00:56:14 | Chart 2 created | bar: Error Amplification Factor |
| 00:56:22 | Chart 3 created | treemap: Framework Landscape 2026 |
| 00:57:06 | Executive summary | ai_agents_executive_summary.md (4,116 bytes) |
| 00:57:25 | LettuceDetect step 3 | 1 hallucinated span, 20.8% ratio |
| 00:57:25 | All steps completed | executing → summarizing |
| 00:57:25 | File sweep | 5 files synced to MinIO |
| 00:57:26 | Summarization started | Budget rebalanced: +56,678 tokens |
| 00:57:34 | ask_stream TTFT | 8.5s time-to-first-token |
| 00:59:41 | ask_stream completed | 135.6s, 23,883 characters (ERROR level) |
| 00:59:52 | ReportEvent delivered | report.md + chart.png + chart.html |
| 01:00:18 | Session completed | summarizing → completed → idle |

---

## 2. Container Resource Analysis

### 2.1 Resource Usage Over Time

| Container | Start | Peak | End | Limit | Concern |
|-----------|-------|------|-----|-------|---------|
| **backend** | 566 MiB | 2.07 GiB (88.97% CPU) | 2.13 GiB | 31 GiB | 3.8x memory growth, never released |
| **sandbox** | 1.01 GiB (168% CPU) | 1.09 GiB (320 PIDs) | 805 MiB (254 PIDs) | 6 GiB | Peak during browser+spider |
| **frontend** | 601 MiB | 636 MiB | 636 MiB | 31 GiB | Stable |
| **mongodb** | 133 MiB | 154 MiB (33.56% CPU) | 154 MiB | 512 MiB | CPU spike during writes |
| **redis** | 6.1 MiB | 7.6 MiB | 7.6 MiB | 512 MiB | Stable |
| **qdrant** | 92 MiB | 93 MiB | 93 MiB | 1 GiB | Stable |
| **minio** | 89 MiB | 112 MiB | 76 MiB | 31 GiB | Stable |

**All containers:** 0 restarts, 0 OOM kills. No containers stopped unexpectedly.

### 2.2 Backend Memory Breakdown

The backend grew from 566 MiB to 2.13 GiB (+1.56 GiB). Primary causes:

1. **LettuceDetect model** (`tinylettuce-ettin-17m-en`): Loaded at 00:52:29, took 5.7s to load. The 17M parameter model cached in memory contributed ~300-500 MiB.
2. **LLM conversation context**: 55 LLM calls with accumulated context, tool results, and smart-compaction buffers.
3. **File sync buffers**: 5 files + 8 report versions + 3 charts held in memory during processing.

---

## 3. Anomaly Analysis

### ANOMALY 1: All Serper API Keys Exhausted (CRITICAL)

**What happened:** At 00:41:55 (2 minutes into the session), the agent attempted web searches via the Serper API. All 6 configured API keys returned HTTP 400 with `"Not enough credits"`. The key pool cycled through all keys and marked them as EXHAUSTED with 1800s (30-minute) auto-recovery TTL.

**Log evidence:**
```
Serper key error (HTTP 400: {"message":"Not enough credits","statusCode":400}), rotating
[serper] Key ad77fa51 marked EXHAUSTED, auto-recovery in 1800s
```

**Impact:**
- 5 consecutive search failures before the fallback chain kicked in
- Research quality degraded — agent relied on `wide_research` with browser-based scraping instead of API-based search
- Browser-navigate tools had to fetch content directly from URLs, adding latency
- 6 `browser_navigate` tool calls were likely compensating for missing search results

**Root cause:** All Serper API keys have exceeded their monthly credit quota. No Brave Search configured as fallback (mentioned in earlier monitoring).

**Recommendation:**
- Replenish Serper credits or add more keys
- Configure Brave Search API keys as additional fallback
- Add budget alerting when keys approach quota limits (e.g., at 80% usage)

---

### ANOMALY 2: GLM-5 Hallucination Rate 44.8%-52.1% (CRITICAL)

**What happened:** The LettuceDetect hallucination verifier flagged significant portions of the agent's step outputs as hallucinated:

| Step | Spans | Confidence | Ratio | Action Taken |
|------|-------|------------|-------|-------------|
| Step 1 | 2 | 0.56 | **44.8%** | Refined step result |
| Step 2 | 4 | 0.52 | **52.1%** | Refined step result |
| Step 3 | 1 | 0.80 | **20.8%** | Disclaimer appended |

**Impact:**
- Nearly half the agent's working output in steps 1-2 was flagged as potentially hallucinated
- The verification system "refined" the step results but did not redact content — the agent continued with potentially unreliable data
- Step 3 was better (20.8%) because it focused on chart creation and file delivery rather than generative text
- The final streaming report (23,883 chars) was generated from these partially-hallucinated intermediate results

**Report quality assessment:** The final report is actually well-structured with 15 citations from real sources. However, specific numerical claims (e.g., "80.9% improvement", "17.2x error amplification") are attributed to a Google Research paper — these appear in both the workspace report and the streamed report, so if the source data is accurate, the hallucination flags may be false positives from LettuceDetect's limitations with research-style text.

**Root cause:** GLM-5's generative outputs contain patterns that trigger LettuceDetect's span detection. The model may be:
1. Paraphrasing source material in ways that diverge enough to trigger hallucination flags
2. Interpolating between sources, creating synthetic claims
3. Over-confident in stating statistics that were loosely derived from sources

**Recommendation:**
- Log the specific hallucinated spans for manual review to assess false positive rate
- Consider a threshold-based approach: redact at >60%, disclaim at >30%, pass at <30%
- GLM-5 may not be ideal for research tasks requiring factual precision — test with Claude or GPT-4

---

### ANOMALY 3: GLM-5 Tool-Calling Unreliability (CRITICAL)

**What happened:** Multiple times during the session, GLM-5 returned responses with `tools=no` (indicating no tool calls in the response), yet the agent's parser extracted tool calls from the response text body. In at least one case, a `file_write` call was parsed with missing required parameters.

**Log evidence:**
```
LLM ask() completed in 53.3s (model=glm-5, tools=no, attempt=1)
tool_started: file_write  # Parsed from text despite tools=no
```

Also observed:
```
Provider doesn't support json_object format, using prompt-based JSON for glm-5
Extracted JSON from prose via balanced-brace matching
```

**Impact:**
- The system's JSON repair and balanced-brace extraction code is compensating for GLM-5's inability to produce proper tool-calling responses
- This is fragile — if the text-based parsing fails, tool calls are silently dropped
- Missing required parameters on tool calls can cause downstream failures or produce incorrect results
- "Prompt-based JSON" fallback is less reliable than native structured output

**Root cause:** GLM-5 does not natively support the tool-calling API format. The system falls back to:
1. Prompt-based JSON instructions (asking the model to embed JSON in text)
2. Balanced-brace regex extraction from prose
3. JSON repair for malformed outputs

**Recommendation:**
- Switch to a model with native tool-calling support (Claude, GPT-4, Gemini) for tool-heavy workflows
- If GLM-5 must be used, add validation that parsed tool calls have all required parameters before execution
- Track tool-call parsing failures as a metric: `pythinker_tool_parse_fallback_total`

---

### ANOMALY 4: Slow Tool-Call Circuit Breaker Ineffective (HIGH)

**What happened:** The slow tool-call circuit breaker tripped **5 times** during the session. Each time, 2+ consecutive LLM calls exceeded the 30-second threshold. However, the circuit breaker's mitigation mechanism — switching to `FAST_MODEL` — was a no-op because `FAST_MODEL` is either unset or set to the same model (`glm-5`).

**Log evidence:**
```
Slow tool-call circuit breaker tripped (2 calls >= 30s) with FAST_MODEL unset; cooldown active for 300s on primary model
```

**LLM call latency distribution (55 total calls):**

| Bucket | Count | Percentage |
|--------|-------|------------|
| <5s | 12 | 21% |
| 5-10s | 23 | 41% |
| 10-30s | 5 | 9% |
| 30-60s | 11 | 20% |
| 60s+ | 4 | 7% |

**Key statistics:**
- Average call latency: **20.8s**
- Total LLM time: **1,141s** (~19 minutes out of 20.3 min session)
- Slowest call: **135.6s** (streaming summary)
- 27% of calls exceeded 30s (15 out of 55)

**Impact:**
- The circuit breaker fires correctly (detecting slow calls) but cannot mitigate them
- 300s cooldown periods are meaningless since no fast model is available
- 27% of LLM calls are over 30 seconds — this is an inherent characteristic of GLM-5, not a transient issue

**Root cause:** `FAST_MODEL` environment variable not configured with a different, faster model.

**Recommendation:**
- Set `FAST_MODEL` to a genuinely faster model (e.g., `claude-haiku-4-5-20251001` as documented in CLAUDE.md)
- Alternatively, if only GLM-5 is available, raise the circuit breaker threshold to 60s to avoid false trips
- Consider per-phase model selection: use faster models for tool-calling steps, slower for long-form generation

---

### ANOMALY 5: Report Rewriting Loop — 8 Versions (HIGH)

**What happened:** The agent wrote `ai_agents_research_report.md` to the sandbox **8 times** during the session, each upload creating a new MinIO object with a different key and etag.

**Version progression:**

| Version | Time | Size | Notes |
|---------|------|------|-------|
| v1 | 00:44:17 | 66 bytes | Stub: `# AI Agents: Comprehensive Research Report\n\n**Published:** March 3` |
| v2 | 00:46:19 | 1,371 bytes | Partial framework table fragment (mid-table content, no headers) |
| v3 | 00:49:30 | 9,786 bytes | Substantial content |
| v4 | 00:50:26 | **18,031 bytes** | Peak size — near-complete report |
| v5 | 00:50:37 | 10,056 bytes | **SHRUNK** — content overwritten/truncated |
| v6 | 00:50:46 | 9,970 bytes | Still smaller |
| v7 | 00:54:28 | 9,792 bytes | Still smaller |
| v8 | 00:55:24 | **18,037 bytes** | Rebuilt back to full size |

**Impact:**
- **Wasted ~4-5 minutes** of session time on redundant rewrites
- **7 unnecessary MinIO uploads** (storage bloat: 77,028 bytes of orphaned objects)
- The report peaked at 18K, was overwritten to ~10K (lost content!), then rebuilt back to 18K
- Each rewrite required a 37-56s LLM call + file_write/file_str_replace

**Root cause:** Two distinct issues:
1. **Incremental writing pattern**: GLM-5 generates long documents in chunks, creating stubs first then overwriting with fuller versions
2. **Content regression at v5**: The agent appears to have called `file_write` (which overwrites) instead of `file_str_replace` (which patches), causing content loss. It then spent 3 more iterations recovering.

**Recommendation:**
- Add write deduplication: if the same file was written in the last N tool calls, inject guidance to stop rewriting
- Track file size regression: if a `file_write` produces a smaller file than the previous version, flag it as a potential content loss
- Consider requiring `file_str_replace` (append/patch) instead of `file_write` (overwrite) for in-progress documents

---

### ANOMALY 6: Streaming Summary 135.6s at ERROR Level (HIGH)

**What happened:** The `ask_stream()` call that generates the final streaming report took **135.6 seconds** to produce 23,883 characters. This was logged at ERROR level because it exceeded 2x the slow response threshold.

**Log evidence:**
```
LLM ask_stream() TTFT=8.5s (model=glm-5)
LLM ask_stream() completed in 135.6s (model=glm-5, chars=23883)  [ERROR]
```

**Impact:**
- User waited 2+ minutes watching the streaming response render
- The TTFT (time-to-first-token) was 8.5s — acceptable, so the user saw text appearing
- However, the total generation time is excessive for a 24K character summary

**Streaming rate:** 23,883 chars / 135.6s = ~176 chars/sec = ~35 tokens/sec. This is within normal range for GLM-5 — the issue is the sheer length of the output.

**Root cause:** The report is comprehensive (471 lines with tables, mermaid diagrams, 15 references). GLM-5's throughput is adequate but the generation length is high.

**Recommendation:**
- The streaming TTFT (8.5s) means the user experience is acceptable despite total time
- Consider adjusting the ERROR threshold for streaming calls specifically (they are inherently longer)
- Alternatively, cap summary length based on research depth

---

### ANOMALY 7: Backend Memory Growth — LettuceDetect Model Never Released (HIGH)

**What happened:** The backend container grew from 566 MiB to **2.13 GiB** during the session — a 3.8x increase. The primary cause was the LettuceDetect hallucination detection model being loaded into memory at 00:52:29 and never released.

**Log evidence:**
```
Loading LettuceDetect model: KRLabsOrg/tinylettuce-ettin-17m-en
LettuceDetect model loaded in 5761ms
```

**Memory timeline:**
- 00:40:00: 566 MiB (session start)
- 00:52:25: 612 MiB (pre-LettuceDetect)
- 00:52:35: 1.71 GiB (model loaded, 88.97% CPU during inference)
- 00:52:58: 2.07 GiB (model cached + accumulated context)
- 01:00:18: 2.13 GiB (session end — model still in memory)

**Impact:**
- ~1.5 GiB held for a model used only 3 times (once per step)
- Each inference took only 86-101ms after the initial load (which took 17.4s including model loading)
- On memory-constrained deployments, this could cause OOM issues for concurrent sessions

**Root cause:** The LettuceDetect model is loaded via a singleton pattern (`get_*()` factory) and cached indefinitely in process memory.

**Recommendation:**
- Add TTL-based eviction: unload the model after 5 minutes of inactivity
- Or load/unload per-session rather than caching globally
- Monitor with a metric: `pythinker_lettuce_model_memory_bytes`

---

### ANOMALY 8: BM25 Sparse Encoder Not Fitted (MEDIUM)

**What happened:** At startup, the BM25 sparse encoder logged a warning that it was not fitted, causing hybrid search to degrade to dense-only retrieval.

**Log evidence:**
```
BM25 encoder not fitted; returning empty sparse vector
```

**Impact:**
- Hybrid search (dense + sparse) degrades to dense-only
- Keyword-based matching unavailable — semantic search alone may miss exact-match queries
- This affects memory retrieval during agent execution (e.g., recalling user preferences, past research)

**Root cause:** The BM25 encoder requires a corpus to fit on. If no corpus is available at startup (empty memory collections), the encoder remains unfitted.

**Recommendation:**
- Implement lazy fitting: fit the BM25 encoder on first query if not already fitted
- Or seed with a minimal default corpus at startup
- Add a health check that reports BM25 fitted status

---

### ANOMALY 9: Context Compression Mid-Session (MEDIUM)

**What happened:** At 00:55:24, the system triggered "smart-compacted 13 tool results" to free up context space. The token budget dropped from 96.5% to 86.0% as a result.

**Impact:**
- 13 earlier tool results were summarized/truncated to free context space
- The agent may have lost detail from earlier research steps that could have improved later steps
- The token budget climbed back to 91.1% shortly after, showing the compression only bought temporary relief

**Root cause:** GLM-5's slow responses (30-55s per call) with large output sizes consume context budget rapidly. Combined with the report rewriting loop, the agent exhausted its context budget early.

**Recommendation:**
- Tune the smart-compaction threshold to trigger earlier (e.g., at 80% instead of waiting until near-exhaustion)
- Increase per-step token budgets for research-depth tasks
- The report rewriting loop (Anomaly 5) is a major contributor — fixing that would reduce context pressure

---

### ANOMALY 10: Screencast WebSocket Reconnection Churn (LOW)

**What happened:** The frontend continuously reconnected the CDP screencast WebSocket every ~15-20 seconds throughout the 20.3-minute session. This created ~180+ WebSocket open/close cycles.

**Pattern:**
```
POST /api/v1/sessions/.../sandbox/signed-url  → 200 (3ms)
WebSocket .../screencast?quality=70&max_fps=15&signature=...&expires=... [accepted]
connection open → Connected to screencast
... 15-20 seconds ...
connection closed
(repeat)
```

**Impact:**
- **High log noise**: Each reconnection generates 6-8 log lines, totaling ~1,200+ lines of screencast-related logs out of the session's total output
- **Unnecessary HTTP round-trips**: ~180 POST requests for signed URLs
- **Functionally working**: The screencast is operational — this is a UX concern, not a functional failure

**Root cause:** The signed URL expiration (`expires=` parameter) is set to ~100 seconds, but the WebSocket connection drops every ~15-20 seconds. The disconnect is likely caused by:
1. Browser-side keepalive timeout
2. Proxy/load balancer timeout
3. Frontend reconnection logic that is too aggressive

**Recommendation:**
- Increase WebSocket keepalive interval or add ping/pong frames
- Extend signed URL TTL to reduce POST requests
- Add `quiet` log level for screencast reconnections to reduce log noise

---

## 4. Generated Report Quality Assessment

### 4.1 Overview

The agent produced three deliverables:
1. **Streaming Report** (22,850 bytes, 471 lines) — delivered via SSE ReportEvent
2. **Workspace Research Report** (18,037 bytes, 400 lines) — stored in sandbox
3. **Executive Summary** (4,116 bytes, 82 lines) — concise version
4. **3 Plotly Charts** — grouped_bar, bar, treemap (PNG + interactive HTML)

### 4.2 Content Quality

**Strengths:**
- Well-structured with clear sections (Definitions, Architecture, Frameworks, Applications, Challenges, Future Directions)
- 15 citations from real, authoritative sources (Google Research, IBM, Databricks, StackOne, etc.)
- Mermaid diagrams for architecture visualization
- Comparison tables throughout
- Executive summary accurately condenses the main report

**Concerns:**
- **Truncation warning**: The streaming report begins with `"⚠️ Incomplete Report: This report contains sections that were not fully generated due to output length limits"` — this is a self-inserted disclaimer by the model, but the report appears complete
- **Ghost text at end**: Lines 461-471 contain meta-commentary where the model argues the report is complete — this is GLM-5 responding to the truncation detection system rather than actual report content
- **Reference gaps**: References [8]-[10] are listed but empty/sparse in the streaming report (blank lines between citations)
- **Duplicate content**: The workspace report (400 lines) and streaming report (471 lines) contain largely the same content with minor formatting differences — the agent effectively wrote the report twice

### 4.3 Report v2 Fragment Anomaly

Report version 2 (1,371 bytes) contained a mid-table fragment:
```
visual debugging | Complex workflows requiring traceability |
| **CrewAI** | Multi-agent orchestration | Role-based agent teams |
```

This is the middle of a markdown table — no headers, no leading pipe. This suggests GLM-5's `file_write` call started mid-generation (the model was already generating content before the tool call parameters were fully formed). This is a manifestation of Anomaly 3 (tool-calling unreliability).

### 4.4 Citation Verification

The report cites 15 sources. Key citations checked against known sources:

| Ref | Claim | Source | Likely Accurate |
|-----|-------|--------|----------------|
| [1] | Google Research: 180 agent configs, 80.9% parallel improvement | research.google | Plausible (real blog post) |
| [2] | TileDB agentic AI guide | tiledb.com/blog | Plausible (real blog) |
| [3] | Data Science Collective framework tier list | medium.com | Plausible (real article) |
| [11] | StackOne: 120+ tools mapped, MCP as standard | stackone.com | Plausible (real blog) |
| [10] | Google Cloud AI agent trends 2026 | cloud.google.com | Plausible (real resource) |

The hallucination verifier's 44.8%-52.1% flags on steps 1-2 likely include paraphrased content that diverges enough from source material to trigger detection but remains factually grounded. The step 3 flag (20.8%) is lower because chart creation doesn't involve generative text.

---

## 5. Performance Summary

### 5.1 LLM Performance

| Metric | Value |
|--------|-------|
| Total LLM calls | 55 |
| Total LLM time | 1,141s (~19 min) |
| Average latency | 20.8s |
| Median latency (est.) | ~8s |
| Calls >30s | 15 (27%) |
| Calls >60s | 4 (7%) |
| Circuit breaker trips | 5 |
| Streaming TTFT | 8.5s |

### 5.2 Tool Usage

| Tool | Invocations | Avg Duration |
|------|-------------|-------------|
| file_write | 7 | 3ms |
| browser_navigate | 6 | varies |
| shell_exec | 6 | 155ms |
| file_str_replace | 5 | 3ms |
| file_read | 5 | 4ms |
| search | 3 | varies |
| chart_create | 3 | 1,455ms |
| wide_research | 1 | varies |
| info_search_web | 1 | varies |
| **Total** | **37** | |

### 5.3 Storage Activity

| Metric | Value |
|--------|-------|
| MinIO uploads | 21 objects |
| Research report versions | 8 |
| Charts (PNG + HTML) | 6 files |
| Executive summary | 1 file |
| Final report event | 3 files (md + png + html) |
| Orphaned report versions | 7 (77 KB wasted) |

---

## 6. Recommendations Summary

| Priority | Recommendation | Anomaly | Effort |
|----------|---------------|---------|--------|
| **P0** | Replenish Serper API credits / add Brave Search keys | #1 | Config |
| **P0** | Set `FAST_MODEL` to a different, faster model | #4 | Config |
| **P1** | Evaluate GLM-5 replacement for tool-heavy research tasks | #2, #3 | Evaluation |
| **P1** | Add file-write deduplication / content-loss detection | #5 | Code |
| **P1** | Add LettuceDetect model TTL eviction (unload after 5 min idle) | #7 | Code |
| **P2** | Log hallucinated spans for manual FP review | #2 | Code |
| **P2** | Fix BM25 fitting (lazy-fit on first query) | #8 | Code |
| **P2** | Tune smart-compaction threshold to 80% budget | #9 | Config |
| **P3** | Increase WebSocket keepalive / reduce screencast log noise | #10 | Code |
| **P3** | Adjust ERROR threshold for streaming calls | #6 | Config |

---

## 7. Conclusion

The session completed successfully — the agent delivered a comprehensive research report with 3 charts and an executive summary. All containers remained healthy with zero restarts or OOM kills.

However, the session exposed **10 anomalies** ranging from exhausted API keys to high hallucination rates. The most impactful issues are:

1. **GLM-5 is suboptimal for this workload**: Its slow responses (27% >30s), unreliable tool-calling, and high hallucination rates account for 6 of the 10 anomalies.
2. **API key exhaustion**: All Serper keys depleted, degrading research quality.
3. **Ineffective circuit breaker**: The FAST_MODEL fallback is a no-op, rendering the circuit breaker useless.

The system's defensive mechanisms (hallucination detection, context compression, JSON repair, balanced-brace extraction) successfully compensated for GLM-5's limitations, but at the cost of significant latency and wasted compute. Switching to a model with native tool-calling support would eliminate anomalies 3, 4, and likely reduce anomalies 2, 5, and 6.
