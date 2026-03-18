# Agent Usage Settings Design

## Summary

This design upgrades the existing Settings `Usage` tab from a token-and-cost summary into a compact agent-usage dashboard that can answer three distinct questions reliably:

1. What did the user spend?
2. What did the agent do?
3. How efficiently did the agent complete work?

The recommended approach is a hybrid billing-plus-execution model.

- Billing remains grounded in provider-native usage fields and versioned pricing snapshots.
- Agent execution is modeled explicitly with `run` and `step` records.
- The Settings `Usage` tab remains compact and operationally useful instead of becoming a full trace explorer.

This design preserves the current legacy endpoints and daily/monthly rollups while adding a new agent-usage layer for future-facing reporting.

## Problem Statement

The current implementation tracks usage primarily as LLM token counts, estimated cost, and daily/monthly aggregates.

That is useful for coarse spend tracking, but it is not sufficient for agent systems because it cannot answer questions such as:

- how many agent runs succeeded or failed
- which tools or MCP servers dominate latency
- which model/provider combinations are driving cost
- whether cache usage is improving efficiency
- what the average cost per successful run looks like

The current UI also presents "usage" mostly as daily token consumption, which is a weak mental model for an agent product. Users reason about runs, outcomes, and execution quality more naturally than they reason about raw daily token totals.

## Goals

- Keep the existing Settings `Usage` tab as the primary surface for user-visible usage reporting.
- Preserve legacy token/cost reporting during migration.
- Add first-class agent execution tracking using `run` and `step` concepts.
- Separate billing metrics from execution metrics while showing both in one coherent UI.
- Calculate cost from provider-aware token fields and versioned pricing snapshots.
- Support current and future provider token dimensions such as cached tokens and reasoning tokens.
- Expose clear summary, trend, breakdown, and recent-run views without requiring a dedicated observability page.
- Keep the design aligned with current observability conventions for GenAI and MCP telemetry.

## Non-Goals

- No full trace explorer inside Settings.
- No attempt to backfill old history into fake per-run detail.
- No replacement of Prometheus with MongoDB or vice versa.
- No new external paid observability dependency.
- No requirement to make billing exact for self-hosted or local models.

## Current Constraints

- The existing frontend usage tab is centered on today/month token totals, daily charts, and recent daily activity rows.
- The frontend API contract currently exposes summary, daily, monthly, session, and pricing endpoints.
- The backend records individual LLM usage with prompt tokens, completion tokens, cached tokens, and estimated cost.
- Tool calls are tracked as activity counts, not as first-class execution steps.
- A richer `SessionMetrics` model already exists in the domain but is not currently surfaced by the settings UI.
- The current pricing table is hardcoded and explicitly marked as "Prices as of January 2025", which is stale as of March 17, 2026.
- This repo is development-only, so forward migration without historical perfection is acceptable.

## Alternatives Considered

### Extend The Existing Token Dashboard

This would add more cards and charts to the current implementation without introducing `run` and `step` records.

Pros:

- fastest implementation path
- smallest schema change
- lowest immediate risk

Cons:

- still does not model agent execution explicitly
- cannot support reliable success-rate, run-duration, or tool/MCP efficiency reporting
- would lock the product into a "usage means tokens" mental model

### Hybrid Billing Plus Execution Model

This is the recommended approach.

Pros:

- matches how serious agent systems are typically instrumented
- supports both spend control and execution analysis
- fits the existing Settings tab without overbuilding

Cons:

- requires new backend documents and aggregation logic
- requires modest frontend redesign

### Full Observability Console In Settings

This would embed deep trace inspection directly into the Settings tab.

Pros:

- strongest debugging depth

Cons:

- too complex for the current Settings surface
- higher storage and UI complexity
- overlaps with a future dedicated observability screen if one is later added

## Recommended Approach

Use a hybrid model with three reporting layers:

1. Billing layer
   Tracks provider-reported or provider-normalized token usage and estimated cost.
2. Execution layer
   Tracks agent runs and steps, including success/failure, duration, tool calls, and MCP usage.
3. Efficiency layer
   Derives metrics such as cost per successful run, tokens per run, cache savings, and tool density.

The frontend Settings `Usage` tab will present all three layers in a compact layout, while the backend stores raw per-step detail and aggregated per-run summaries.

## Architecture

### Core Usage Model

The system will model usage at three levels:

- `session`
  Existing conversation container. This remains unchanged and continues to group runs.
- `run`
  A single agent execution triggered by a user turn or explicit action.
- `step`
  A unit inside a run such as an LLM call, tool execution, MCP request, reflection, or verification phase.

This creates a stable hierarchy:

`user -> session -> run -> step`

### Run Model

Add a persistent `AgentRun` model and document with these fields:

- `run_id`
- `user_id`
- `session_id`
- `agent_id`
- `entrypoint`
- `status`
- `started_at`
- `completed_at`
- `duration_ms`
- `step_count`
- `tool_call_count`
- `mcp_call_count`
- `error_count`
- `total_input_tokens`
- `total_cached_input_tokens`
- `total_output_tokens`
- `total_reasoning_tokens`
- `total_tokens`
- `estimated_cost_usd`
- `provider_billed_cost_usd`
- `billing_status`
- `primary_model`
- `primary_provider`

Recommended `status` values:

- `running`
- `completed`
- `failed`
- `cancelled`

Recommended `billing_status` values:

- `estimated`
- `provider_reported`
- `self_hosted`

### Step Model

Add a persistent `AgentStep` model and document with these fields:

- `step_id`
- `run_id`
- `session_id`
- `user_id`
- `step_type`
- `provider`
- `model`
- `tool_name`
- `mcp_server`
- `status`
- `started_at`
- `completed_at`
- `duration_ms`
- `input_tokens`
- `cached_input_tokens`
- `output_tokens`
- `reasoning_tokens`
- `total_tokens`
- `estimated_cost_usd`
- `provider_billed_cost_usd`
- `error_type`
- `provider_usage_raw`

Recommended `step_type` values:

- `llm`
- `tool`
- `mcp`
- `retrieval`
- `reflection`
- `verification`

### Normalized Token Model

The backend should store normalized token fields even when providers use different names.

Canonical fields:

- `input_tokens`
- `cached_input_tokens`
- `output_tokens`
- `reasoning_tokens`
- `total_tokens`

Provider-native usage data must also be stored in `provider_usage_raw` to avoid flattening away useful billing detail.

This matters because provider usage shapes differ:

- OpenAI usage fields expose input, output, cached, and reasoning token dimensions.
- Anthropic prompt caching distinguishes cache creation from cache read behavior and pricing.

The normalized layer is for reporting. The raw layer is for correctness and future evolution.

### Billing And Pricing Model

Replace the current single hardcoded pricing table with versioned pricing snapshots.

Add a `PricingSnapshot` model with:

- `provider`
- `model_pattern`
- `effective_from`
- `effective_to`
- `input_price_per_1m`
- `output_price_per_1m`
- `cached_read_price_per_1m`
- `cache_write_price_per_1m`
- `currency`
- `source_url`
- `source_retrieved_at`

Rules:

- cost is calculated from the pricing snapshot active at event time
- if provider-billed cost is available later, retain it separately
- self-hosted models should not be treated as normal paid API usage
- reporting should distinguish estimated costs from provider-reported costs clearly

### Usage Aggregation Strategy

Preserve the current legacy aggregate flow and add new run/step aggregations alongside it.

Legacy usage remains responsible for:

- today/month summary
- daily usage history
- monthly usage history
- session-level usage summary

New agent usage will power:

- run summary
- recent runs
- model/provider/tool/MCP breakdowns
- trend charts focused on runs, outcomes, and efficiency

### Observability Alignment

The design should align with current OpenTelemetry GenAI and MCP semantic conventions.

At minimum, instrumentation should retain:

- operation name
- provider name
- request model
- response model when available
- operation duration
- input tokens
- output tokens
- error type
- tool or MCP method identifiers where relevant

This does not require exposing raw OTel spans directly in the settings UI. It only means the internal usage model should not diverge from stable telemetry vocabulary.

## API Contract

### Keep Existing Endpoints

Keep these routes for backward compatibility:

- `GET /usage/summary`
- `GET /usage/daily`
- `GET /usage/monthly`
- `GET /usage/session/{session_id}`
- `GET /usage/pricing`

### Add Agent Usage Endpoints

#### `GET /usage/agent/summary?range=7d|30d|90d`

Returns:

- `run_count`
- `completed_run_count`
- `failed_run_count`
- `success_rate`
- `avg_run_duration_ms`
- `total_cost`
- `total_input_tokens`
- `total_cached_input_tokens`
- `total_output_tokens`
- `total_reasoning_tokens`
- `total_tool_calls`
- `total_mcp_calls`
- `cache_savings_estimate`

#### `GET /usage/agent/runs?range=30d&limit=20`

Returns recent runs:

- `run_id`
- `session_id`
- `started_at`
- `completed_at`
- `status`
- `duration_ms`
- `total_cost`
- `total_tokens`
- `tool_call_count`
- `mcp_call_count`
- `primary_model`
- `primary_provider`

#### `GET /usage/agent/breakdown?range=30d&group_by=model|provider|tool|mcp_server`

Returns grouped rows with:

- `key`
- `run_count`
- `input_tokens`
- `cached_input_tokens`
- `output_tokens`
- `reasoning_tokens`
- `cost`
- `avg_duration_ms`
- `error_rate`

#### `GET /usage/agent/timeseries?range=30d&bucket=day`

Returns time buckets with:

- `date`
- `run_count`
- `success_count`
- `failed_count`
- `cost`
- `input_tokens`
- `cached_input_tokens`
- `output_tokens`
- `reasoning_tokens`
- `tool_calls`
- `mcp_calls`

### Compatibility Rules

- The frontend must tolerate a mixed historical state where only legacy usage data exists.
- New agent endpoints should return empty but valid payloads rather than transport-level failure when no run data exists.
- Existing usage endpoints remain the fallback for migration safety.

## Frontend UX Design

### Overall Layout

Keep the existing Settings `Usage` tab and redesign its content into four stacked sections:

1. Summary cards
2. Trend chart
3. Recent runs
4. Breakdown and efficiency strip

This keeps the interaction compact enough for the current Settings dialog width.

### Summary Cards

Replace the current "Today" and "This Month" hero emphasis with four top-level cards:

- `Cost`
- `Agent Runs`
- `Success Rate`
- `Avg Run Duration`

Each card should include concise supporting detail:

- `Cost`
  Show input, cached, output, and reasoning token totals underneath.
- `Agent Runs`
  Show completed vs failed counts.
- `Success Rate`
  Show failure count and trend over the selected period.
- `Avg Run Duration`
  Show tool call count and MCP call count.

### Usage Trends

Replace the current daily token-only chart with a metric-switching chart.

Period controls:

- `7d`
- `30d`
- `90d`

Metric controls:

- `Cost`
- `Runs`
- `Tokens`
- `Tools`

Behavior:

- `Cost` charts estimated total cost over time.
- `Runs` charts success vs failed runs as stacked series.
- `Tokens` charts input, cached, output, and reasoning tokens as stacked series when available.
- `Tools` charts tool calls and MCP calls.

### Recent Runs

Replace the current recent daily activity table with a recent-runs table.

Columns:

- `Status`
- `Start`
- `Duration`
- `Cost`
- `Tokens`
- `Tools`
- `Primary Model`

Interaction:

- clicking a row opens a compact run-detail expander or drawer
- the detail view remains summary-oriented rather than becoming a full trace inspector

### Breakdown Section

Add a grouped breakdown section with a segmented control:

- `By Model`
- `By Provider`
- `By Tool`
- `By MCP`

Columns:

- `Runs`
- `Cost`
- `Tokens`
- `Avg Duration`
- `Error Rate`

### Efficiency Strip

Add a small derived-metrics strip below the breakdown section:

- `Cost per successful run`
- `Tokens per run`
- `Cache savings`
- `Avg tools per run`

### Legacy Fallback Behavior

If only legacy usage data exists:

- summary cards should still render using available token/cost data
- agent-specific panels should display empty-state messaging rather than broken layout
- no UI should imply fake historical run-level precision

### Pricing Disclosure

The UI should display a small pricing disclosure:

`Estimated from pricing snapshot effective YYYY-MM-DD`

For self-hosted models, show:

- `self-hosted`
- or `$0.00 estimate`

Do not blend those silently into paid provider spend without labeling them.

## Data Flow

### Run Lifecycle

1. User triggers agent execution in a session.
2. Backend creates an `AgentRun` with `status=running`.
3. As orchestration proceeds, backend appends `AgentStep` records for LLM, tool, MCP, reflection, and verification steps as applicable.
4. Provider-level usage data populates step token and cost fields.
5. Tool and MCP steps populate execution counts and latency fields even if direct dollar cost is zero.
6. At completion or failure, backend finalizes the run and writes aggregate totals onto the `AgentRun`.

### Settings Tab Load

1. Frontend loads `GET /usage/agent/summary`.
2. Frontend loads `GET /usage/agent/timeseries`.
3. Frontend loads `GET /usage/agent/runs`.
4. Frontend loads `GET /usage/agent/breakdown`.
5. If agent endpoints return empty historical data, frontend may still use legacy endpoints for coarse cards and charts.

## Error Handling

### Provider Usage Gaps

If a provider does not expose a token dimension such as `reasoning_tokens`:

- store `0` or `null` according to the chosen schema convention
- do not fabricate values
- hide or de-emphasize absent dimensions in the UI

### Pricing Gaps

If no pricing snapshot matches the event:

- retain usage counts
- mark cost as estimated from default fallback only if that fallback is explicit
- set `billing_status=estimated`
- log the pricing mismatch for operator follow-up

### Partial Run Data

If a run crashes before finalization:

- preserve the partial run
- mark it `failed` or `cancelled` according to the shutdown reason
- keep step-level usage already recorded

### UI Failures

If agent endpoints fail:

- show an error state within the affected panel
- do not block the whole settings dialog
- keep legacy summary data visible when possible

## Migration Strategy

### Phase 1: Add New Models And Writes

- add `AgentRun` and `AgentStep` domain models
- add corresponding Mongo documents and indexes
- add usage services to create, append, finalize, and aggregate run data

### Phase 2: Instrument Orchestration

- create run lifecycle hooks in the orchestration boundary
- attach LLM calls, tool calls, and MCP requests to the active run
- preserve existing raw usage recording

### Phase 3: Add Agent Usage Routes

- add `/usage/agent/summary`
- add `/usage/agent/runs`
- add `/usage/agent/breakdown`
- add `/usage/agent/timeseries`

### Phase 4: Redesign Frontend Usage Tab

- keep the settings tab location unchanged
- switch the chart and table to run-oriented reporting
- introduce breakdown and efficiency views
- keep legacy fallback behavior during migration

### Phase 5: Replace Hardcoded Pricing With Snapshots

- introduce pricing snapshot persistence or versioned configuration
- calculate event cost from the snapshot active at event time
- keep explicit source URLs and retrieval timestamps

### Historical Data Policy

Do not attempt deep historical backfill into invented run/step records.

Accept these tradeoffs:

- legacy daily and session data remains usable
- detailed run analytics become reliable from the migration point forward

This is appropriate for the repo's development-only environment.

## Testing Strategy

### Backend Tests

- verify OpenAI usage normalization captures input, cached, output, and reasoning dimensions when present
- verify Anthropic usage normalization preserves cache-related raw fields and maps normalized cached input appropriately
- verify local/self-hosted models are labeled correctly
- verify pricing snapshot selection chooses the correct snapshot by event timestamp
- verify run finalization computes:
  - success rate inputs
  - total tokens
  - total cost
  - average duration inputs
- verify `/usage/agent/*` routes return stable empty payloads for users with no run history

### Frontend Tests

- verify summary cards render correctly for agent-aware data
- verify legacy fallback mode renders without agent-run history
- verify chart metric switching among `Cost`, `Runs`, `Tokens`, and `Tools`
- verify recent-runs table rendering and expansion behavior
- verify grouped breakdown rendering for model/provider/tool/MCP modes
- verify loading, empty, and panel-level error states

### Operational Verification

- detailed run/step data stays in MongoDB rather than being forced into high-cardinality Prometheus labels
- Prometheus retains coarse aggregated metrics only
- indexes exist for:
  - `user_id + started_at`
  - `session_id + started_at`
  - `run_id`
  - `run_id + step_id`
  - grouped breakdown dimensions where justified

## Sustainability Considerations

- separating `run` and `step` makes future observability work easier without changing the Settings UX contract
- storing raw provider usage prevents schema churn when vendors add new billing dimensions
- pricing snapshots prevent stale estimates from silently distorting historical reporting
- explicit self-hosted labeling prevents a misleading blend of free and paid usage

## Sources

Primary references consulted on March 17, 2026:

- OpenTelemetry GenAI semantic conventions
  - https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/
- OpenTelemetry MCP semantic conventions
  - https://opentelemetry.io/docs/specs/semconv/gen-ai/mcp/
- OpenAI API pricing
  - https://openai.com/api/pricing/
- OpenAI API usage fields and organization usage endpoints
  - https://platform.openai.com/docs/api-reference/chat/create-chat-completion
  - https://developers.openai.com/api/reference/resources/organization/subresources/audit_logs/subresources/usage
- Anthropic prompt caching and pricing
  - https://platform.claude.com/docs/en/build-with-claude/prompt-caching
  - https://platform.claude.com/docs/about-claude/pricing
- Langfuse data model and observability concepts
  - https://langfuse.com/docs/observability/data-model
