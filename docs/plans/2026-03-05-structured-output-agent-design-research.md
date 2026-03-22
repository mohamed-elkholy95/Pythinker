# Structured Output Reliability Research and Agent Design Upgrade

Date: 2026-03-05
Scope: Backend agent architecture (`backend/app`) and frontend contract validation (`frontend`)
Objective: Upgrade the agent to a verified, provider-aware, schema-first design that minimizes malformed JSON and unsafe fallbacks while keeping DDD boundaries clean.

**Validation Status**: Enhanced and validated against Context7 MCP documentation (2026-03-05).

## 1) Research Method and Sources

This recommendation set is based on:

- In-repo implementation audit of current LLM + agent parsing paths (full codebase exploration).
- Context7 MCP library documentation queries for Anthropic, OpenAI, Pydantic, FastAPI, Zod, and Instructor.
- Ref MCP documentation lookup (supplementary).

Primary references are listed in Section 13.

## 2) Current State (What We Actually Run Today)

### 2.1 Strong pieces already present

- Pydantic response contracts exist and are used in many critical paths.
- **Anthropic backend** has a strict structured method (`anthropic_llm.py:553-645`) that:
  - Builds schema from `response_model.model_json_schema()`.
  - Wraps as tool with `tool_choice="required"` (tool-calling approach, not `output_config.format`).
  - Validates with `response_model.model_validate(...)`.
  - Retries with graduated temperature reduction (normal → 0.3 → 0.0) and validation error feedback.
  - Applies ephemeral cache control on system prompt + last tool definition (45-80% cost reduction).
- **OpenAI backend** (`openai_llm.py:2051-2357`) supports:
  - `response_format: json_schema` strict mode when available (capability-detected).
  - Optional Instructor path with mode selection (`TOOLS_STRICT`, `JSON_SCHEMA`, `MD_JSON`).
  - Validation and retries with exponential backoff (1-30s).
  - Thinking API special-case retry handling.
  - JSON repair on truncation (balanced-brace extraction + partial Pydantic validation).
- **Capability registry** exists (`llm_capabilities.py`) with glob-pattern matching per model family.
- Strict tool argument parsing exists at execution boundary (rejects malformed JSON tool args rather than silently repairing).
- **Instructor adapter** (`instructor_adapter.py`) with soft import and automatic mode selection.
- **Retry framework** (`core/retry.py`) with provider-specific presets (Anthropic 2s, OpenAI 1s, GLM 3s, DeepSeek 2s).

### 2.2 Architectural drift/risk points

- Runtime still injects a global permissive parser (`LLMJsonParser`) with a 5-stage fallback chain:
  1. Direct JSON parse
  2. Channel marker extraction (local LLM format)
  3. Markdown block extraction
  4. Cleanup & repair (trailing commas, single quotes, unescaped quotes, Qwen3 `<think>` tags)
  5. **LLM-powered extraction** (`_try_llm_extract_and_fix`) — calls LLM with `response_format={"type": "json_object"}`
- Fallback path can alter payload semantics (LLM repair may hallucinate fields or change values).
- `domain/utils/json_repair.py` provides additional repair layer (`extract_json_text`, `parse_json_response`, `parse_json_model`).
- Structured-output usage is not universal across all agent decision points — `UniversalLLM.ask_json()` falls back to lenient parsing that returns `None` on failure.
- **Anthropic still uses tool-calling for structured output** instead of the newer `output_config.format` API (see Section 3.1 correction).
- Capability detection in OpenAI provider uses hardcoded string matching instead of the centralized `llm_capabilities.py` registry.

### 2.3 Quantitative snapshot (corrected via full codebase audit)

- `ask_structured(...)` call sites: **11** (was 8 — undercount)
- `response_format={"type":"json_object"}` call sites: **3** (openai_llm.py fallback, universal_llm.py, llm_json_parser.py)
- `json_parser.parse(...)` call sites: **16+** (across agents, flows, and infrastructure)
- `parse_json_response(...)` call sites: **2+** (domain utils)

### 2.4 Detailed call-site classification (NEW)

| Call Site | File | Schema Model | Current Tier |
|-----------|------|-------------|--------------|
| Plan creation | `planner.py:620` | `PlanResponse` | A (critical) |
| Plan updates | `planner.py:776` | `PlanUpdateResponse` | A (critical) |
| Replan generation | `planner.py:1162` | `PlanResponse` | A (critical) |
| Report generation | `report_generator.py:64` | `ResearchReport` / `ComparisonReport` / `AnalysisReport` | A (critical) |
| Output review | `critic.py:555` | `CriticReview` | B (important) |
| Fact checking | `critic.py:822` | `FactCheckResult` | B (important) |
| Structured feedback | `critic.py:949` | `StructuredFeedback` | B (important) |
| Five-check validation | `critic.py:1131` | `FiveCheckResult` | B (important) |
| Query decomposition | `research_query_decomposer.py:107` | `DecomposedQueries` | B (important) |
| Canvas plan creation | `canvas_service.py:371` | `PlanResponse` | B (important) |
| Universal LLM delegation | `universal_llm.py` | (passthrough) | varies |

Interpretation: design intent is strong, but operationally the system still relies heavily on permissive parsing patterns, and the tier assignment is implicit rather than explicit.

## 3) Verified Best Practices (Cross-Provider)

### 3.1 Anthropic (Claude) — Context7 MCP Validated

**Current API** (validated 2026-03-05):

Two structured output mechanisms:

1. **JSON Schema output** via `output_config.format`:
   ```json
   {
     "output_config": {
       "effort": "high",
       "format": {
         "type": "json_schema",
         "schema": { "type": "object", "properties": {...}, "required": [...] }
       }
     }
   }
   ```
   - `output_format` parameter is **deprecated** — must use `output_config.format` instead.
   - Can be combined with `effort` level (`low`/`medium`/`high`/`max`) for thinking control.

2. **Strict tool validation** via `strict: true` on tool definitions:
   ```json
   {
     "name": "return_structured",
     "input_schema": { "type": "object", ... },
     "strict": true
   }
   ```
   - When `strict: true`, guarantees schema validation on tool names and inputs.
   - Supports `cache_control` with TTL (`5m` or `1h`) for cost optimization.

**Important operational caveats**:

- First request per new schema incurs grammar compilation latency (cached 24h).
- Schema/tool shape changes invalidate cache.
- Refusals (`stop_reason="refusal"`) and truncation (`stop_reason="max_tokens"`) can produce non-schema-compliant outputs and must be explicitly handled.
- Complexity limits apply (strict tool count, optional params, union types), and excessive complexity can fail compilation.

**Correction for this repo**: Pythinker currently uses tool-calling (mechanism 2) for Anthropic structured output. The plan should include a **migration path to `output_config.format`** (mechanism 1) which is the primary structured output API — tool-calling for structured output is a workaround pattern.

Design implications:

- For critical workflows, always classify/refusal-handle and truncation-retry before trusting output.
- Keep strict schemas lean; avoid over-nested optional unions.
- Migrate Anthropic structured output from tool-calling to `output_config.format` to use native constrained decoding.
- Use `effort` parameter to balance quality vs latency per tier.

### 3.2 OpenAI — Context7 MCP Validated

**Chat Completions API** (validated):

```python
response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "schema_name",
        "schema": { ... },
        "strict": True  # Required for constrained decoding
    }
}
```

- `strict: True` requires: `additionalProperties: false` on all objects, all fields in `required` (optional via `["type", "null"]` unions).

**Function calling strict mode** (validated):

```json
{
  "function": {
    "name": "fn_name",
    "strict": true,
    "parameters": {
      "type": "object",
      "properties": { ... },
      "required": [...],
      "additionalProperties": false
    }
  }
}
```

**Responses API** (NEW — not in original plan):

OpenAI's newer Responses API uses a different parameter path:
```python
response = client.responses.create(
    model="gpt-5",
    input="...",
    text={"format": {"type": "json_schema", "name": "...", "strict": True, "schema": {...}}}
)
```
This is relevant if Pythinker adopts OpenAI Responses API in the future.

**SDK typed parsing helpers** (validated):
```python
completion = client.chat.completions.parse(
    model="gpt-4o",
    response_format=MyPydanticModel,
    messages=[...]
)
# completion.choices[0].message.parsed  → typed model
# completion.choices[0].message.refusal → refusal string or None
```

**Edge case handling** (validated — enhanced from original):

Must check for **four** distinct stop conditions (not just two):
1. `finish_reason == "stop"` → success, parse content
2. `finish_reason == "length"` → truncation, retry with higher `max_tokens`
3. `finish_reason == "content_filter"` → **safety filter** (NEW — missing from original plan), handle as content policy violation
4. `message.refusal` field present → model refusal, return policy-safe error

Design implications:

- Strict mode is the baseline for decision-critical data.
- JSON object / prompt-only fallback is acceptable only in low-risk paths.
- **Content filter** must be added to the typed failure taxonomy (was missing).
- Consider Responses API path for future-proofing.

### 3.3 Pydantic v2 — Context7 MCP Validated

- Domain schemas as single source of truth (`model_json_schema()`, `model_validate`, `model_validate_json`).
- Use strict validation where semantics matter: `model_validate({'x': '123'}, strict=True)` rejects string→int coercion.
- Model-level strict mode: `model_config = ConfigDict(strict=True)` with per-field override via `Field(strict=False)`.
- `@field_validator` should use classmethod signature style.

**Performance optimization** (NEW — missing from original plan):

```python
# Preferred: 30-50% faster (avoids intermediate dict)
model = MyModel.model_validate_json(json_string)

# Slower: double conversion
model = MyModel.model_validate(json.loads(json_string))
```

`model_validate_json()` validates directly from raw JSON string via Rust-based parser. This should be used in the structured output service for all provider responses that arrive as JSON strings.

Design implications:

- Keep business constraints in domain models, not parser glue or route handlers.
- Use `model_validate_json()` instead of `json.loads()` + `model_validate()` in hot paths.

### 3.4 FastAPI — Context7 MCP Validated

- Use `response_model` consistently to validate/filter outgoing payloads.
- `response_model` filters fields at serialization boundary (not just docs — active enforcement).
- Use separate input/output models for sensitive data (e.g., `UserIn` vs `UserOut`).
- Leverage model inheritance for DRY output models.

Design implication:

- Ensure all agent-facing API responses that carry structured payloads are declared with response models.

### 3.5 Zod — Context7 MCP Validated

**Core pattern** (validated):
```typescript
const result = MySchema.safeParse(apiResponse);
if (!result.success) {
  console.log(result.error.issues);
  // [{ code: "invalid_type", path: ["field"], message: "..." }]
} else {
  store.setState(result.data); // typed, validated
}
```

- `.safeParse()` returns discriminated union: `{ success: true, data: T } | { success: false, error: ZodError }`.
- `.parse()` throws `ZodError` on failure (use only in contexts where exceptions are expected).
- Issues include `code`, `path`, `message` — useful for structured error reporting.

**Zod 4** is now available (2026) with significant performance improvements and smaller bundle via "Zod Mini" variant. Consider adopting Zod 4 for the frontend contracts.

Design implication:

- Add schema-gated adapter layer between API client and state mutations.
- Use `.safeParse()` exclusively (never `.parse()`) at API boundaries.
- Report schema mismatches with structured error context (endpoint, path, expected type).

### 3.6 Instructor — Context7 MCP Validated

**Mode selection** (validated and expanded):

```python
import instructor
from instructor import Mode

# Provider-specific modes
client = instructor.from_provider("openai/gpt-4o", mode=Mode.TOOLS)           # Default
client = instructor.from_provider("openai/gpt-4o", mode=Mode.TOOLS_STRICT)    # Strict enforcement
client = instructor.from_provider("openai/gpt-4o", mode=Mode.JSON_SCHEMA)     # Native schema
client = instructor.from_provider("anthropic/claude-3-5-sonnet", mode=Mode.ANTHROPIC_TOOLS)

# Core modes (use these):
# TOOLS — tool/function calling (default for most)
# JSON_SCHEMA — native schema support (when provider has it)
# MD_JSON — JSON extracted from text/code blocks (fallback)
# TOOLS_STRICT — strict schema enforcement
# PARALLEL_TOOLS — multiple tool calls in one response
# RESPONSES_TOOLS — OpenAI Responses API tools (NEW)
```

**Retry mechanism** (validated):
```python
user = client.chat.completions.create(
    response_model=User,
    max_retries=3,  # Simple: retries on validation failure
    messages=[...],
)

# Advanced: tenacity-based retry configuration
user = client.chat.completions.create(
    response_model=User,
    max_retries=tenacity.Retrying(
        stop=tenacity.stop_after_attempt(3),
        before=lambda rs: print(f"Attempt {rs.attempt_number}"),
    ),
    messages=[...],
)
```

- Validation errors are automatically fed back to the LLM for self-correction.
- Mode selection tips: `TOOLS` for most cases, `JSON_SCHEMA` when provider supports it, `MD_JSON` as fallback.

Design implications:

- Keep Instructor optional and capability-gated, with deterministic fallback.
- Map Instructor modes to the strategy enum (Section 5.2) for consistency.
- Use `from_provider()` string-based init for cleaner provider abstraction.
- Current Pythinker `instructor_adapter.py` mode selection logic aligns well with these recommendations.

## 4) Gap Analysis vs Target Three-Layer Defense

Target model: **Constrain → Validate → Retry**.

### Where current system matches:

| Layer | Anthropic | OpenAI (capable) | OpenAI (limited/GLM) | Ollama |
|-------|-----------|-------------------|-----------------------|--------|
| Constrain | Tool strict ✅ | json_schema strict ✅ | Prompt-only ❌ | Native structured (partial) |
| Validate | Pydantic ✅ | Pydantic ✅ | Pydantic ✅ | Pydantic ✅ |
| Retry | Temp reduction ✅ | Exp backoff ✅ | Exp backoff ✅ | Parser fallback ⚠️ |

### Where current system diverges:

1. **Critical flows can degrade into permissive parser/repair** — no tier enforcement prevents this.
2. **LLM-assisted JSON repair** (`_try_llm_extract_and_fix`) is still available in default parser stack and can be invoked for any tier.
3. **Frontend lacks Zod parity** with backend contracts — unvalidated API payloads flow directly into Pinia stores.
4. **Anthropic uses tool-calling workaround** instead of native `output_config.format` structured output API.
5. **OpenAI provider duplicates capability detection** — hardcoded string matching in `openai_llm.py` instead of using centralized `llm_capabilities.py`.
6. **Content filter stop reason** (`finish_reason="content_filter"`) is not handled as a typed outcome.
7. **No `model_validate_json()` optimization** — providers deserialize JSON then validate dict (slower path).
8. **No explicit tier tagging** on structured output requests — impossible to enforce tier-specific policies.

### NEW: Provider capability matrix (from `llm_capabilities.py` audit)

| Model Family | json_schema | json_object | tool_use | vision | thinking |
|-------------|-------------|-------------|----------|--------|----------|
| claude-* | ✅ | — | ✅ | ✅ | ✅ |
| gpt-4o* | ✅ | ✅ | ✅ | ✅ | ❌ |
| gpt-5* | ✅ | ✅ | ✅ | ✅ | ✅ |
| glm-* | ❌ | ❌ | ✅ | ❌ | ❌ |
| deepseek* | ✅ | ✅ | ✅ | ❌ | ❌ |
| qwen* | ✅ | ✅ | ✅ | ❌ | ❌ |
| llama* | ❌ | ❌ | ✅ | ❌ | ❌ |

**Critical implication**: GLM and Llama families have **no** json_schema or json_object support. For these providers, Tier A structured output is impossible via constrained decoding — must use tool-calling with Pydantic validation as the constrain layer, or restrict these models to Tier C tasks only.

## 5) Proposed Agent Design Upgrade (DDD-Compatible)

### 5.1 Reliability tiers by decision risk

Introduce explicit output reliability tiers:

- **Tier A (critical)**: planner decisions, verifier verdicts, tool args, policy gates, report generation.
  - Must use strict structured mode (tool strict or strict json_schema).
  - No permissive repair fallback.
  - On failure: bounded retry → explicit typed error.
  - `model_validate_json()` for validation (performance path).
  - **Provider gate**: If provider lacks json_schema AND tool strict, reject at strategy selection with typed error (do not silently degrade).

- **Tier B (important)**: critic reports, reflections, scoring, query decomposition, canvas planning.
  - Structured-first; one controlled fallback allowed (Instructor MD_JSON or prompt-based JSON).
  - No LLM semantic repair if schema still invalid.
  - Validation errors reported but task not failed (graceful degradation to raw text).

- **Tier C (non-critical)**: advisory summaries, UX hints, chat-mode responses.
  - May use lenient parse and repair with clear observability tags.
  - `LLMJsonParser` full chain permitted (including LLM repair).

### 5.2 Central capability + strategy router

Add one central strategy decision point in the **application layer**:

- **Input**: provider capabilities (from `llm_capabilities.py`), model name, task tier, schema complexity profile.
- **Output**: generation strategy enum:

```python
class StructuredOutputStrategy(StrEnum):
    ANTHROPIC_OUTPUT_CONFIG = "anthropic_output_config"      # output_config.format json_schema (preferred)
    ANTHROPIC_STRICT_TOOL = "anthropic_strict_tool"          # tool-calling with strict: true (current)
    OPENAI_STRICT_JSON_SCHEMA = "openai_strict_json_schema"  # response_format json_schema strict
    OPENAI_STRICT_FUNCTION = "openai_strict_function"        # function calling with strict: true
    INSTRUCTOR_TOOLS_STRICT = "instructor_tools_strict"      # Instructor with TOOLS_STRICT mode
    INSTRUCTOR_JSON_SCHEMA = "instructor_json_schema"        # Instructor with JSON_SCHEMA mode
    INSTRUCTOR_MD_JSON = "instructor_md_json"                # Instructor MD_JSON fallback (Tier B)
    LENIENT_JSON_OBJECT = "lenient_json_object"              # json_object + parse (Tier C only)
    PROMPT_BASED_JSON = "prompt_based_json"                  # Prompt injection + extraction (Tier C only)
    UNSUPPORTED = "unsupported"                              # Provider cannot satisfy tier requirement
```

**Selection logic** (pseudocode):
```
if tier == A:
    if anthropic → ANTHROPIC_OUTPUT_CONFIG (or ANTHROPIC_STRICT_TOOL as interim)
    if openai + json_schema → OPENAI_STRICT_JSON_SCHEMA
    if instructor + tools_strict → INSTRUCTOR_TOOLS_STRICT
    else → UNSUPPORTED (raise StructuredOutputUnsupportedError)
elif tier == B:
    prefer strict strategies, fallback to INSTRUCTOR_MD_JSON
elif tier == C:
    LENIENT_JSON_OBJECT or PROMPT_BASED_JSON
```

This removes ad-hoc fallback behavior spread across agents and **leverages the existing `llm_capabilities.py` registry** instead of duplicating detection logic.

### 5.3 Unified structured execution contract

Create a typed orchestrator service (application layer) with:

**Request**:
```python
@dataclass(frozen=True)
class StructuredOutputRequest:
    request_id: str
    schema_model: type[BaseModel]
    tier: OutputTier  # A, B, C
    messages: list[dict]
    max_schema_retries: int = 3
    max_transport_retries: int = 3
    complexity_profile: SchemaComplexityProfile | None = None
```

**Response**:
```python
@dataclass(frozen=True)
class StructuredOutputResult(Generic[T]):
    parsed: T | None
    strategy_used: StructuredOutputStrategy
    stop_reason: StopReason  # SUCCESS, REFUSAL, TRUNCATED, CONTENT_FILTER, SCHEMA_INVALID, TRANSPORT_ERROR, TIMEOUT, UNSUPPORTED
    refusal_message: str | None
    error_type: ErrorCategory | None  # transport, schema, safety, timeout, unsupported
    attempts: int
    latency_ms: float
    request_id: str
```

All agents consume this single API. This is the **only** path for structured LLM output — no direct `ask_structured()` calls from agent code.

### 5.4 Separate transport retries from schema retries

Two retry loops with separate limits and backoff strategies:

- **Transport retries** (outer loop):
  - Triggers: `RateLimitError` (429), `APIConnectionError`, `APITimeoutError`, network transient.
  - Strategy: exponential backoff with jitter (provider-specific presets from `core/retry.py`).
  - Limit: `max_transport_retries` (default 3).
  - **Key rotation**: integrate with `APIKeyPool` on 429/401 (existing infrastructure).

- **Schema retries** (inner loop):
  - Triggers: `ValidationError`, refusal, truncation, content filter.
  - Strategy:
    - `SCHEMA_INVALID`: re-prompt with validation error context (Instructor-style feedback).
    - `REFUSAL`: return typed error (do not retry — model has refused deliberately).
    - `TRUNCATED`: retry with increased `max_tokens` (1.5x) or simplified schema.
    - `CONTENT_FILTER`: return typed error (do not retry — safety system intervention).
  - Limit: `max_schema_retries` (default 3).

Benefits:

- Better observability (separate Prometheus counters).
- Prevents runaway retries (transport × schema ≤ 9 total calls max).
- Easier SLO control per dimension.

### 5.5 Refusal/truncation/content-filter as first-class outcomes

Do not treat refusal, truncation, or content filter as generic parse failures.

Typed handling:

- **`REFUSAL`**: Return policy-safe user message or escalation path. Log with `structured_output_refusals_total` counter. Do not retry.
- **`TRUNCATED`**: Increase `max_tokens` (1.5x original, capped at model limit) or simplify schema (strip optional fields), then retry. Log with `structured_output_truncations_total`.
- **`CONTENT_FILTER`** (NEW): Return typed safety error. Log with `structured_output_content_filter_total`. Do not retry. Escalate to user with safe message.
- **`SCHEMA_INVALID`**: Retry with validation feedback injected into next prompt. Log with `structured_output_schema_retries_total`.

### 5.6 Schema complexity guardrail

Before request submission, compute a simple complexity score from schema:

```python
@dataclass(frozen=True)
class SchemaComplexityProfile:
    optional_field_count: int
    union_count: int          # anyOf/nullable count
    max_nesting_depth: int
    total_property_count: int
    strict_tool_count: int    # tools in request
    score: float              # weighted composite

    @property
    def is_strict_eligible(self) -> bool:
        """Whether schema is simple enough for constrained decoding."""
        return (
            self.union_count <= 5
            and self.max_nesting_depth <= 4
            and self.total_property_count <= 30
            and self.strict_tool_count <= 10
        )
```

If above thresholds, auto-select mitigation:

- Split schema into multi-step extraction (decompose complex union types).
- Reduce optionals (make required with sensible defaults).
- Break into nested calls (extract outer structure first, then fill inner details).

**Integration point**: The `StructuredOutputService` computes this before strategy selection and may override the tier downward or split the request.

### 5.7 Frontend contract parity

Adopt backend-to-frontend schema parity:

- Generate/maintain Zod schemas for API responses consumed by stateful UI.
- Validate in API adapter before Pinia writes.
- Log schema mismatch events with endpoint + contract version.
- **Consider Zod 4** for better performance and smaller bundle size.

**Error reporting strategy** (NEW):

```typescript
// frontend/src/api/validatedClient.ts
function validateResponse<T>(schema: z.ZodType<T>, data: unknown, endpoint: string): T {
  const result = schema.safeParse(data);
  if (!result.success) {
    logger.warn('Schema mismatch', {
      endpoint,
      issues: result.error.issues.map(i => ({ path: i.path, code: i.code, message: i.message })),
      contractVersion: SCHEMA_VERSION,
    });
    // Tier A: throw, Tier B/C: return data with warning
    throw new SchemaValidationError(endpoint, result.error);
  }
  return result.data;
}
```

### 5.8 Anthropic structured output migration (NEW)

**Current state**: Pythinker wraps structured output as a tool call (`return_structured_response` tool with `tool_choice="required"`).

**Target state**: Use `output_config.format` with `json_schema` for native constrained decoding.

**Migration plan**:
1. Add `output_config` path to `anthropic_llm.py` alongside existing tool-calling path.
2. Feature-flag: `anthropic_use_output_config_format: bool = False` (default off initially).
3. Run both paths in shadow mode (Phase 0) to compare reliability.
4. Migrate Tier A calls first, then B, then C.
5. Remove tool-calling structured output path after validation.

**Benefits**:
- Native constrained decoding (grammar-level guarantee).
- Combinable with `effort` parameter for thinking control.
- Eliminates tool-call overhead for pure structured output requests.
- Aligns with Anthropic's primary API path (deprecated `output_format` → current `output_config.format`).

### 5.9 Provider capability consolidation (NEW)

**Current state**: `openai_llm.py` has 5+ boolean flags (`_is_mlx_mode`, `_is_glm_api`, `_is_openrouter`, `_is_deepseek`, `_is_thinking_api`) and hardcoded string matching for capability detection, duplicating logic in `llm_capabilities.py`.

**Target state**: Single source of truth via `llm_capabilities.get_capabilities(model, api_base)`.

**Migration**:
1. Extend `llm_capabilities.py` to cover all capabilities currently detected ad-hoc in `openai_llm.py`.
2. Replace `_supports_structured_output()`, `_supports_json_object_format()`, `_supports_response_format_with_tools()` with capability registry lookups.
3. Strategy router (Section 5.2) consumes capabilities from registry only.

## 6) Concrete Changes for This Repo

### 6.1 Backend: strategy centralization

Create:

- `backend/app/application/services/structured_output_service.py`
  - Single entrypoint for structured generation.
  - Tier-based strategy enforcement via `StructuredOutputStrategy` enum.
  - Unified retry and error typing via `StructuredOutputResult`.
  - Schema complexity preflight check.
  - Prometheus metrics per strategy/tier/outcome.

- `backend/app/domain/services/validation/schema_profile.py`
  - `SchemaComplexityProfile` computation from Pydantic model JSON schema.
  - Strict eligibility check.

Update call sites to use it first:

- Planner critical paths (`planner.py` — 3 call sites).
- Report generator (`report_generator.py` — 1 call site).
- Critic verdict paths (`critic.py` — 4 call sites).
- Research query decomposer (`research_query_decomposer.py` — 1 call site).
- Canvas service (`canvas_service.py` — 1 call site).

### 6.2 Backend: demote permissive parser to Tier C only

Current parser:

- `backend/app/infrastructure/utils/llm_json_parser.py`
- `backend/app/domain/utils/json_repair.py`

Refactor:

- Keep local extraction (stages 1-4) for backward compatibility and Tier B fallback.
- **Disable `_try_llm_extract_and_fix`** (stage 5) by default for Tier A/B.
- Gate with explicit flag: `allow_llm_json_repair: bool` parameter on parse methods.
- Add `tier` parameter to `LLMJsonParser.parse()` that controls which stages are permitted.

### 6.3 Backend: schema profiles + strict presets

Add:

- `backend/app/domain/services/validation/schema_profile.py`
  - Complexity metrics and strict eligibility.
  - JSON schema traversal for union/optional/depth counting.

Enforce:

- `additionalProperties: false` normalization where needed for OpenAI strict compatibility.
- Schema validation at service construction (fail-fast if schema is incompatible with required tier).

### 6.4 Backend: typed failure taxonomy

Add domain exceptions/enums:

```python
class StopReason(StrEnum):
    SUCCESS = "success"
    REFUSAL = "refusal"
    TRUNCATED = "truncated"
    CONTENT_FILTER = "content_filter"       # NEW
    SCHEMA_INVALID = "schema_invalid"
    TRANSPORT_ERROR = "transport_error"
    TIMEOUT = "timeout"
    UNSUPPORTED = "unsupported"             # NEW: provider can't satisfy tier

class StructuredOutputError(Exception):
    """Base for all structured output errors."""
    stop_reason: StopReason

class StructuredRefusalError(StructuredOutputError): ...
class StructuredTruncationError(StructuredOutputError): ...
class StructuredContentFilterError(StructuredOutputError): ...   # NEW
class StructuredSchemaValidationError(StructuredOutputError): ...
class StructuredOutputExhaustedError(StructuredOutputError): ...
class StructuredOutputUnsupportedError(StructuredOutputError): ...  # NEW
```

Route to interface layer for stable API error payloads.

### 6.5 Backend: Pydantic validation optimization (NEW)

In the `StructuredOutputService`, use `model_validate_json()` instead of `json.loads()` + `model_validate()`:

```python
# Current (slower):
data = json.loads(response_text)
result = response_model.model_validate(data)

# Optimized (30-50% faster validation):
result = response_model.model_validate_json(response_text)
```

This is a targeted optimization for the hot path — all structured output validation flows through the central service.

### 6.6 Backend: Anthropic output_config migration (NEW)

Add `output_config.format` support to `anthropic_llm.py`:

- New method: `_ask_structured_output_config()` alongside existing `_ask_structured_tool()`.
- Feature flag: `anthropic_use_output_config_format: bool` in `config_llm.py`.
- Combine with `effort` parameter when extended thinking is needed.
- Handle `stop_reason` mapping: `"refusal"` → `REFUSAL`, `"max_tokens"` → `TRUNCATED`, `"end_turn"` → `SUCCESS`.

### 6.7 Frontend: Zod boundary validation

Add:

- `frontend/src/contracts/*.schema.ts` — Zod schemas mirroring backend response models.
- `frontend/src/api/validatedClient.ts` — Validated fetch wrapper.

Pattern:

- Fetch → `safeParse` → accept/reject before store writes.
- Schema mismatch logging with endpoint + path + expected type.
- Consider Zod 4 for performance improvements.

## 7) Phased Rollout Plan

### Phase 0: Instrumentation and no-behavior-change baseline

- Add per-strategy Prometheus metrics labels and current failure counters.
- Track: refusal rate, truncation rate, content filter rate, schema retry count, parse fallback rate, strategy selection distribution.
- Add `tier` label to existing `llm_structured_output_*` metrics.
- **Shadow-test `output_config.format`** for Anthropic alongside existing tool-calling path (log comparison, no behavior change).

Success criteria:

- Baseline dashboard available for all agent runs.
- Shadow comparison data for Anthropic `output_config.format` vs tool-calling.

### Phase 1: Tier A migration

- Create `StructuredOutputService` with strategy routing.
- Migrate planner/verifier/report-generator critical outputs to strict-only path via the service.
- Remove permissive fallback for those flows.
- Implement `SchemaComplexityProfile` preflight checks.
- Gate `LLMJsonParser._try_llm_extract_and_fix` behind tier parameter.

Success criteria:

- Tier A parse-fallback rate → 0%.
- No increase in user-visible task failures beyond agreed threshold (< 2% regression).
- All Tier A calls have explicit `StopReason` in response.

### Phase 2: Tier B migration + Anthropic output_config

- Migrate critic/reflection/scoring/decomposition to structured-first with controlled fallback via the service.
- Enable `anthropic_use_output_config_format` for Tier A after Phase 0 validation.
- Consolidate OpenAI capability detection to use `llm_capabilities.py`.

Success criteria:

- 90%+ B-tier calls resolved without generic parser path.
- Anthropic `output_config.format` validated and active for Tier A.
- Zero duplicated capability detection logic in `openai_llm.py`.

### Phase 3: Frontend parity

- Add Zod validation for high-impact endpoints (session events, plan responses, agent messages).
- Implement `validatedClient.ts` adapter.
- Add schema mismatch telemetry.

Success criteria:

- 100% of store-mutating API calls pass schema guardrails.
- Schema mismatch events reported and actionable.

### Phase 4: Cleanup and hardening

- Remove dead parser branches (unused fallback strategies).
- Remove tool-calling structured output from Anthropic (after `output_config.format` is stable).
- Tighten exception mapping and docs.
- Audit all remaining `json_parser.parse()` calls — classify and tag by tier.

Success criteria:

- Simplified code paths and reduced maintenance burden.
- All structured output paths go through `StructuredOutputService`.

## 8) KPIs and SLO Targets

| KPI | Target | Measurement |
|-----|--------|-------------|
| Structured success rate (A-tier) | ≥ 99.5% | `structured_output_success_total{tier="A"} / structured_output_requests_total{tier="A"}` |
| A-tier permissive fallback usage | 0 | `structured_output_fallback_total{tier="A"}` |
| B-tier permissive fallback usage | ≤ 5% | `structured_output_fallback_total{tier="B"} / structured_output_requests_total{tier="B"}` |
| Mean schema retries per successful call | ≤ 0.3 | `structured_output_schema_retries_total / structured_output_success_total` |
| Refusal handling correctness (typed, non-500) | 100% | Zero untyped refusal errors in error logs |
| Content filter handling (typed, non-500) | 100% | Zero untyped content filter errors in error logs |
| Frontend schema-violation leak to store | 0 | `frontend_schema_mismatch_total` where data still entered store |
| `model_validate_json()` adoption in hot path | 100% | All `StructuredOutputService` validation uses direct JSON path |

## 9) Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Strict schemas increase first-call latency (Anthropic grammar compilation) | Medium | Low-Medium | Warm up known schemas at service startup; keep schema shapes stable across deploys |
| Schema complexity compilation failures | Low | High | Schema profiler preflight + split extraction; fail-fast with `StructuredOutputUnsupportedError` |
| Over-strictness reduces task completion on noisy models (GLM, Llama) | Medium | Medium | Tiered strategy ensures noisy models only get Tier C tasks; provider capability gate prevents silent degradation |
| Migration churn across many agents (11 call sites) | Medium | Medium | Central service wrapper and phased adoption; backward-compatible API |
| `output_config.format` behavioral differences from tool-calling | Low | Medium | Shadow testing in Phase 0; feature-flag rollout |
| Zod version compatibility (v3 vs v4) | Low | Low | Pin Zod version; evaluate v4 in Phase 3 |
| Instructor library breaking changes | Low | Medium | Soft import with graceful degradation (already implemented); pin version |

## 10) Recommended Default Policy (Immediate)

1. Default all new critical agent outputs to strict structured mode.
2. Disallow LLM-based JSON repair for critical and important tiers.
3. Require explicit justification to use permissive parser paths.
4. Require frontend boundary validation before state writes.
5. **NEW**: Tag all `ask_structured()` call sites with explicit tier annotation (even before service migration).
6. **NEW**: Use `model_validate_json()` for all new structured output validation.
7. **NEW**: Handle `content_filter` as a typed stop reason in all providers.

## 11) Suggested Backlog Tickets

1. **[P0]** Implement `StructuredOutputService` with tier routing, strategy selection, and typed outcomes.
2. **[P0]** Create `SchemaComplexityProfile` and preflight guardrails.
3. **[P0]** Add typed failure taxonomy (domain exceptions + `StopReason` enum).
4. **[P1]** Integrate service into Planner and Report Generator first (Tier A).
5. **[P1]** Gate `LLMJsonParser._try_llm_extract_and_fix` behind Tier C-only flag.
6. **[P1]** Add `content_filter` handling to OpenAI provider stop reason mapping.
7. **[P1]** Migrate Pydantic validation to `model_validate_json()` in structured output paths.
8. **[P2]** Add Anthropic `output_config.format` path (feature-flagged, shadow mode).
9. **[P2]** Consolidate OpenAI capability detection to use `llm_capabilities.py` registry.
10. **[P2]** Integrate service into Critic (Tier B — 4 call sites).
11. **[P3]** Introduce Zod contracts for top 5 store-mutating frontend endpoints.
12. **[P3]** Add dashboards for structured-output reliability KPIs.
13. **[P4]** Remove tool-calling structured output from Anthropic after `output_config.format` validated.
14. **[P4]** Audit and classify all remaining `json_parser.parse()` call sites.

## 12) Validation Checklist for Future Changes

- [ ] Does this output path use a domain model as schema source?
- [ ] Is the output tier (A/B/C) explicitly declared?
- [ ] Is constrained decoding enforced for its tier?
- [ ] Is validation explicit, typed, and using `model_validate_json()` where possible?
- [ ] Are retries bounded and categorized (transport vs schema)?
- [ ] Are refusal/truncation/content-filter handled as separate typed outcomes?
- [ ] Is permissive repair disabled for A/B tiers?
- [ ] Is the provider capability checked via `llm_capabilities.py` (not ad-hoc string matching)?
- [ ] Is frontend state boundary protected (when applicable)?
- [ ] Is schema complexity profiled before strict mode submission?

## 13) References

### Context7 MCP Validated Sources (2026-03-05)

- **Anthropic Claude API** — `/websites/platform_claude_en_api` (Score: 73.6, 9837 snippets)
  - `output_config.format` structured outputs, `strict: true` tool definitions
  - `output_format` deprecated → use `output_config.format`
  - Effort levels: `low`/`medium`/`high`/`max`
  - Cache control: `ephemeral` with TTL `5m`/`1h`

- **OpenAI API** — `/websites/developers_openai_api` (Score: 74.1, 10043 snippets)
  - `response_format.type = "json_schema"` with `strict: true`
  - `additionalProperties: false` + all fields in `required` for strict mode
  - Refusal via `message.refusal` field, truncation via `finish_reason == "length"`, content filter via `finish_reason == "content_filter"`
  - SDK `chat.completions.parse()` typed helper
  - Responses API `text.format` (newer path)

- **Pydantic v2** — `/pydantic/pydantic` (Score: 88.9, 742 snippets)
  - `model_validate()`, `model_validate_json()` (faster), `model_validate_strings()`
  - `ConfigDict(strict=True)`, `Field(strict=False)` per-field override
  - `@field_validator` classmethod pattern

- **Instructor** — `/jxnl/instructor` (Score: 88.1, 3509 snippets)
  - `from_provider()` unified interface
  - Modes: `TOOLS`, `TOOLS_STRICT`, `JSON_SCHEMA`, `MD_JSON`, `ANTHROPIC_TOOLS`, `RESPONSES_TOOLS`
  - `max_retries` with tenacity support, validation error feedback loop

- **Zod** — `/colinhacks/zod` (Score: 95.4, 536 snippets)
  - `.safeParse()` discriminated union: `{ success, data/error }`
  - Error issues: `code`, `path`, `message`
  - Zod 4 available with performance improvements

- **FastAPI** — `/fastapi/fastapi` (Score: 82.5, 813 snippets)
  - `response_model` filters and validates outgoing payloads
  - Separate input/output models for security
  - Model inheritance for DRY response schemas

### Additional Documentation

- Anthropic Structured Outputs (official):
  https://platform.claude.com/docs/en/build-with-claude/structured-outputs

- OpenAI Structured Outputs guide:
  https://developers.openai.com/api/docs/guides/structured-outputs

- OpenAI Function Calling strict mode:
  https://developers.openai.com/api/docs/guides/function-calling

- OpenAI Python structured parsing helpers:
  https://github.com/openai/openai-python/blob/main/helpers.md

- Pydantic validators:
  https://github.com/pydantic/pydantic/blob/main/docs/concepts/validators.md

- FastAPI `response_model`:
  https://fastapi.tiangolo.com/tutorial/response-model

- Zod basics and `safeParse`:
  https://zod.dev/basics

- Instructor structured outputs and retries:
  https://github.com/jxnl/instructor

## 14) Appendix: Current Codebase File Map

Key files involved in this upgrade:

| File | Role | Phase |
|------|------|-------|
| `backend/app/application/services/structured_output_service.py` | **NEW** — Central service | P0 |
| `backend/app/domain/services/validation/schema_profile.py` | **NEW** — Complexity profiler | P0 |
| `backend/app/domain/models/structured_output.py` | **NEW** — Typed results/errors | P0 |
| `backend/app/infrastructure/external/llm/anthropic_llm.py` | Migrate to output_config.format | P2 |
| `backend/app/infrastructure/external/llm/openai_llm.py` | Consolidate capability detection | P2 |
| `backend/app/infrastructure/external/llm/ollama_llm.py` | Tier C strategy enforcement | P2 |
| `backend/app/infrastructure/external/llm/universal_llm.py` | Route through service | P1 |
| `backend/app/infrastructure/external/llm/instructor_adapter.py` | Mode mapping to strategy enum | P1 |
| `backend/app/infrastructure/utils/llm_json_parser.py` | Tier-gated fallback chain | P1 |
| `backend/app/domain/utils/json_repair.py` | Tier-gated repair | P1 |
| `backend/app/domain/external/llm_capabilities.py` | Extend for consolidated detection | P2 |
| `backend/app/domain/services/agents/planner.py` | Tier A migration (3 call sites) | P1 |
| `backend/app/domain/services/agents/critic.py` | Tier B migration (4 call sites) | P2 |
| `backend/app/domain/services/agents/report_generator.py` | Tier A migration (1 call site) | P1 |
| `backend/app/domain/services/agents/research_query_decomposer.py` | Tier B migration (1 call site) | P2 |
| `backend/app/domain/services/canvas_service.py` | Tier B migration (1 call site) | P2 |
| `backend/app/core/config_llm.py` | Feature flags | P0 |
| `backend/app/infrastructure/metrics/prometheus_metrics.py` | New counters | P0 |
| `frontend/src/contracts/*.schema.ts` | **NEW** — Zod schemas | P3 |
| `frontend/src/api/validatedClient.ts` | **NEW** — Validated adapter | P3 |
