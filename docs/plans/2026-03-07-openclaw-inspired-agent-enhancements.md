# OpenClaw-Inspired Agent Enhancements Implementation Plan (Repo-Aligned V2)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver OpenClaw-inspired agent capabilities in Pythinker by extending the approval, tool selection, usage, scheduling, shell, and plugin systems that already exist in this repo instead of creating parallel stacks.

**Architecture:** This is a convergence-first plan. Existing Pythinker primitives like `WaitEvent` + `pending_action`, `DynamicToolsetManager`, `SpawnTool`, `UsageService`, `ScheduleTool` / `CronTool`, `ShellTool`, and entry-point plugin loading remain the backbone. New work is limited to pure domain policies, thin infrastructure adapters, and frontend/API extensions where a verified gap still exists.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, MongoDB, Redis, Vue 3 + TypeScript, Vitest, Prometheus metrics, APScheduler (already present in repo), nanobot cron bridge, Docker sandbox.

**Source of Truth:** Pythinker repo inventory first, OpenClaw patterns second. For external guidance, use APScheduler documentation for durable scheduling, Python `importlib.metadata` documentation for plugin discovery, and Prometheus documentation for metric cardinality and labeling.

---

## Current Capability Baseline

The original draft assumed several systems did not exist. That is inaccurate. This section is the execution baseline for the rest of the plan.

| Capability | Status | Existing Evidence | Gap To Close |
|------------|--------|-------------------|--------------|
| Approval plumbing (`WaitEvent`, pending action persistence, confirm endpoint, deterministic replay) | `Completed` | `backend/app/domain/services/agents/base.py`, `backend/app/domain/services/agent_task_runner.py`, `backend/app/interfaces/api/session_routes.py` | Risk policy is too permissive and not source-aware |
| HITL policy / high-risk detection | `In Progress` | `backend/app/domain/services/flows/hitl_policy.py`, `backend/tests/domain/services/flows/test_hitl_policy.py` | Integrate with source/channel policy and make metrics/reporting consistent |
| Dynamic tool filtering | `In Progress` | `backend/app/domain/services/tools/dynamic_toolset.py` | Add better profile hints without breaking current scoring model |
| Subagent spawn tool scaffolding | `In Progress` | `backend/app/domain/services/tools/spawn_tool.py`, `backend/tests/domain/services/tools/test_spawn_tool.py` | Missing infrastructure bridge and PlanActFlow wiring |
| Usage tracking and pricing | `Completed` | `backend/app/application/services/usage_service.py`, `backend/app/domain/models/usage.py`, `backend/app/domain/services/usage/pricing.py` | Add richer queries, export, and better UI breakdowns |
| Usage UI | `In Progress` | `frontend/src/components/settings/UsageSettings.vue`, `frontend/src/components/settings/UsageChart.vue`, `frontend/src/api/usage.ts` | Add session/model/date-range analytics and CSV export |
| Scheduling / cron tools | `In Progress` | `backend/app/domain/services/tools/schedule.py`, `backend/app/domain/services/tools/cron_tool.py`, `backend/app/infrastructure/services/cron_bridge.py` | Unify service layer, add management API, avoid duplicate scheduler models |
| Shell live streaming / long-running session handling | `In Progress` | `backend/app/domain/services/tools/shell.py`, `backend/app/domain/services/tools/shell_output_poller.py`, `backend/app/domain/external/sandbox.py` | Add explicit background execution ergonomics without inventing a second process registry |
| Plugin loading | `In Progress` | `backend/app/infrastructure/plugins/skill_plugin_loader.py`, `backend/app/core/lifespan.py` | Generalize current entry-point loader into a formal plugin SDK with lifecycle hooks |
| Provider-specific tool schema adaptation | `In Progress` | `backend/app/infrastructure/external/llm/anthropic_llm.py`, `backend/app/infrastructure/external/llm/openai_llm.py`, `backend/app/infrastructure/external/llm/provider_profile.py` | Centralize adaptation into one shared normalizer |

### Explicit Non-Goals

Do **not** create any of the following unless a later implementation step proves the existing systems unusable:

- A second approval service separate from `pending_action`
- A new `UsageRecord` stack separate from `backend/app/domain/models/usage.py`
- A second cron job model parallel to `ScheduledTask`, `ScheduledJob`, or `CronBridge`
- A new detached process registry unrelated to shell session IDs
- A filesystem plugin scanner that bypasses Python entry-point discovery

### Repo Rules That This Plan Must Respect

- Domain code stays pure: no `app.core.config` imports in domain services
- Reuse before create: extend current tools, services, models, and UI
- Feature defaults remain factual:
  - `feature_hitl_enabled` is already `True`
  - `feature_url_failure_guard_enabled` is already `True`
  - `cron_service_enabled` is already `False`
  - `subagent_spawning_enabled` is already `False`
  - `feature_live_shell_streaming` is already `False`
- Single-test backend commands must use `-p no:cov -o addopts=`

---

## Phase 1: Tool Governance & Approval Convergence (P0)

**OpenClaw Goal:** Multi-layer tool policy, approval for dangerous actions, and better outbound request safety.

**Why:** Pythinker already has the pause/confirm/resume lifecycle. What is missing is a real policy engine that can classify requests by source, risk, and outbound target before the current approval pipeline executes.

**Integration Points:**

- `backend/app/domain/services/agents/security_assessor.py` — currently always allows everything
- `backend/app/domain/services/flows/hitl_policy.py` — current regex-based approval rules
- `backend/app/domain/services/agents/base.py` — already emits `WaitEvent`
- `backend/app/domain/services/agent_task_runner.py` — already persists and replays `pending_action`
- `backend/app/domain/models/session.py` — already has `source`
- `backend/app/domain/services/agents/url_failure_guard.py` — existing URL pre-check hook

### Task 1.1: Add a Pure Tool Governance Policy

**Files:**

- Create: `backend/app/domain/services/agents/tool_governance.py`
- Modify: `backend/app/domain/services/agents/security_assessor.py`
- Modify: `backend/app/domain/services/flows/hitl_policy.py`
- Test: `backend/tests/domain/services/agents/test_tool_governance.py`

**Step 1: Write the failing tests**

```python
from app.domain.services.agents.tool_governance import (
    GovernanceContext,
    GovernanceDecisionCode,
    ToolGovernancePolicy,
)


def test_web_source_allows_safe_search() -> None:
    policy = ToolGovernancePolicy()
    decision = policy.evaluate(
        "info_search_web",
        {"query": "python typing"},
        GovernanceContext(source="web"),
    )
    assert decision.allowed
    assert not decision.requires_confirmation


def test_telegram_source_blocks_shell_exec() -> None:
    policy = ToolGovernancePolicy()
    decision = policy.evaluate(
        "shell_exec",
        {"command": "ls -la"},
        GovernanceContext(source="telegram"),
    )
    assert not decision.allowed
    assert decision.code == GovernanceDecisionCode.SOURCE_BLOCKED


def test_web_source_requires_confirmation_for_rm_rf() -> None:
    policy = ToolGovernancePolicy()
    decision = policy.evaluate(
        "shell_exec",
        {"command": "rm -rf /tmp/demo"},
        GovernanceContext(source="web"),
    )
    assert decision.allowed
    assert decision.requires_confirmation
    assert decision.code == GovernanceDecisionCode.REQUIRES_CONFIRMATION
```

**Step 2: Run the single test file and verify it fails**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/agents/test_tool_governance.py -v
```

Expected: `FAIL` because `tool_governance.py` does not exist yet.

**Step 3: Implement the minimal policy service**

```python
from dataclasses import dataclass
from enum import StrEnum


class GovernanceDecisionCode(StrEnum):
    ALLOW = "allow"
    SOURCE_BLOCKED = "source_blocked"
    REQUIRES_CONFIRMATION = "requires_confirmation"


@dataclass(frozen=True)
class GovernanceContext:
    source: str = "web"
    allow_destructive_operations: bool = False


@dataclass(frozen=True)
class GovernanceDecision:
    allowed: bool
    requires_confirmation: bool
    code: GovernanceDecisionCode
    reason: str = ""


class ToolGovernancePolicy:
    def evaluate(
        self,
        function_name: str,
        arguments: dict,
        context: GovernanceContext,
    ) -> GovernanceDecision:
        ...
```

Implementation rules:

- Keep this file pure: no settings import, no Prometheus import, no repository access
- Treat source restrictions and dangerous-command confirmation as separate decisions
- Use `HitlPolicy` as an input, not a replacement
- Return bounded decision codes suitable for Prometheus labels

**Step 4: Re-run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/agents/test_tool_governance.py -v
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/tool_governance.py \
        backend/app/domain/services/agents/security_assessor.py \
        backend/app/domain/services/flows/hitl_policy.py \
        backend/tests/domain/services/agents/test_tool_governance.py
git commit -m "feat(agent): add source-aware tool governance policy"
```

### Task 1.2: Wire Governance into the Existing Approval Lifecycle

**Files:**

- Modify: `backend/app/domain/services/agents/base.py`
- Modify: `backend/app/domain/services/agent_task_runner.py`
- Modify: `backend/app/core/prometheus_metrics.py`
- Test: `backend/tests/domain/services/agents/test_pending_action_governance.py`

**Step 1: Write the failing tests**

```python
async def test_high_risk_tool_call_emits_wait_event_and_persists_pending_action() -> None:
    ...


async def test_source_blocked_tool_returns_failure_without_pending_action() -> None:
    ...
```

Success criteria:

- High-risk but allowed calls still use the current `pending_action` pipeline
- Source-blocked calls fail fast and do not create a pending action
- Metrics use bounded labels like `tool`, `source`, and `decision_code`

**Step 2: Run the targeted tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/agents/test_pending_action_governance.py -v
```

Expected: `FAIL`

**Step 3: Implement the wiring**

Implementation requirements:

- Do not emit `WaitEvent` from `BaseTool.invoke_function()`
- Evaluate governance in the agent layer before the existing tool event / `WaitEvent` path
- Reuse the current `pending_action` persistence and `confirm_action()` replay logic
- Add a metric helper that increments low-cardinality counters only
- Pass session source into the governance context from the existing session model

**Step 4: Run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/agents/test_pending_action_governance.py -v
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/base.py \
        backend/app/domain/services/agent_task_runner.py \
        backend/app/core/prometheus_metrics.py \
        backend/tests/domain/services/agents/test_pending_action_governance.py
git commit -m "feat(agent): converge governance with existing pending-action approval flow"
```

### Task 1.3: Add Outbound Private-Network Blocking to the Existing URL Guard Path

**Files:**

- Create: `backend/app/domain/services/agents/outbound_url_policy.py`
- Modify: `backend/app/domain/services/agents/url_failure_guard.py`
- Modify: `backend/app/domain/services/agents/base.py`
- Test: `backend/tests/domain/services/agents/test_outbound_url_policy.py`

**Step 1: Write the failing tests**

```python
from app.domain.services.agents.outbound_url_policy import OutboundUrlPolicy


def test_blocks_localhost() -> None:
    assert not OutboundUrlPolicy().is_allowed("http://127.0.0.1:8080")


def test_blocks_metadata_ip() -> None:
    assert not OutboundUrlPolicy().is_allowed("http://169.254.169.254/latest/meta-data")


def test_allows_public_https() -> None:
    assert OutboundUrlPolicy().is_allowed("https://example.com")
```

**Step 2: Run the test**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/agents/test_outbound_url_policy.py -v
```

Expected: `FAIL`

**Step 3: Implement the policy and integrate it**

Implementation rules:

- Keep the policy pure and synchronous
- Reuse the existing `_extract_url_from_args()` pre-check path in `BaseAgent`
- Return bounded denial messages; do not add free-text reason labels to Prometheus
- Scope this to outbound URL-capable tools only

**Step 4: Re-run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/agents/test_outbound_url_policy.py -v
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/outbound_url_policy.py \
        backend/app/domain/services/agents/url_failure_guard.py \
        backend/app/domain/services/agents/base.py \
        backend/tests/domain/services/agents/test_outbound_url_policy.py
git commit -m "feat(agent): block private-network outbound URLs in shared guard path"
```

---

## Phase 2: Dynamic Toolset Profile Hints (P0)

**OpenClaw Goal:** Fewer irrelevant tools in the prompt.

**Why:** Pythinker already has a strong scoring-based `DynamicToolsetManager`. The missing piece is lightweight task-profile hints that improve ranking without replacing the existing category, keyword, and usage scoring.

**Integration Points:**

- `backend/app/domain/services/tools/dynamic_toolset.py`
- `backend/app/domain/models/tool_capability.py`
- `backend/tests/domain/services/tools/test_tool_contract_validation.py`

### Task 2.1: Add Profile Hints as Score Boosts, Not Hard Prefilters

**Files:**

- Create: `backend/app/domain/services/tools/tool_profile_hints.py`
- Modify: `backend/app/domain/services/tools/dynamic_toolset.py`
- Modify: `backend/app/core/prometheus_metrics.py`
- Test: `backend/tests/domain/services/tools/test_dynamic_toolset_profiles.py`

**Step 1: Write the failing tests**

```python
from app.domain.services.tools.dynamic_toolset import DynamicToolsetManager


def test_coding_task_boosts_shell_and_file_tools() -> None:
    manager = DynamicToolsetManager()
    manager.register_tools(
        [
            {"type": "function", "function": {"name": "shell_exec", "description": "Run shell commands", "parameters": {"type": "object", "properties": {}}}},
            {"type": "function", "function": {"name": "file_read", "description": "Read files", "parameters": {"type": "object", "properties": {}}}},
            {"type": "function", "function": {"name": "search_web", "description": "Search the web", "parameters": {"type": "object", "properties": {}}}},
        ]
    )
    tools = manager.get_tools_for_task("Refactor the Python module and run the tests")
    names = [tool["function"]["name"] for tool in tools]
    assert "shell_exec" in names
    assert "file_read" in names


def test_profile_hints_do_not_remove_always_include_tools() -> None:
    ...
```

**Step 2: Run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/tools/test_dynamic_toolset_profiles.py -v
```

Expected: `FAIL`

**Step 3: Implement hint-driven scoring**

Implementation rules:

- Introduce a small profile hint resolver that returns score multipliers or boosts
- Do not create `_all_tools`; continue using `self._tools`, category index, and keyword index
- Keep `always_include` behavior intact
- Emit a bounded profile-selection metric using a small label set such as `profile`

**Step 4: Re-run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/tools/test_dynamic_toolset_profiles.py -v
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add backend/app/domain/services/tools/tool_profile_hints.py \
        backend/app/domain/services/tools/dynamic_toolset.py \
        backend/app/core/prometheus_metrics.py \
        backend/tests/domain/services/tools/test_dynamic_toolset_profiles.py
git commit -m "feat(tools): add profile hints to dynamic toolset scoring"
```

---

## Phase 3: Subagent Spawning Completion (P1)

**OpenClaw Goal:** Agents can delegate work into child sessions and collect results.

**Why:** The repo already has `SpawnTool` and a feature flag for subagent spawning. The missing piece is the infrastructure bridge that creates child work, enforces limits, and routes results back into the parent session.

**Integration Points:**

- `backend/app/domain/services/tools/spawn_tool.py`
- `backend/app/domain/services/agent_task_runner.py`
- `backend/app/domain/services/flows/plan_act.py`
- `backend/app/core/config_channels.py`

### Task 3.1: Build and Wire a Session-Backed Subagent Bridge

**Files:**

- Create: `backend/app/infrastructure/services/subagent_bridge.py`
- Modify: `backend/app/domain/services/agent_task_runner.py`
- Modify: `backend/app/domain/services/flows/plan_act.py`
- Test: `backend/tests/infrastructure/services/test_subagent_bridge.py`
- Test: `backend/tests/domain/services/agents/test_spawn_tool_wiring.py`

**Step 1: Write the failing tests**

```python
async def test_subagent_bridge_spawns_child_session_and_returns_confirmation() -> None:
    ...


async def test_plan_act_flow_includes_spawn_tool_when_feature_enabled() -> None:
    ...


async def test_bridge_enforces_max_concurrency() -> None:
    ...
```

**Step 2: Run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/services/test_subagent_bridge.py tests/domain/services/agents/test_spawn_tool_wiring.py -v
```

Expected: `FAIL`

**Step 3: Implement the bridge**

Implementation requirements:

- Keep the existing `SubagentManagerProtocol` in `spawn_tool.py`
- The new bridge should create child sessions and queue background execution using existing session/agent services
- Route final subagent summaries back into the parent session as normal assistant events
- Respect `subagent_spawning_enabled`, `subagent_max_concurrent`, and `subagent_max_iterations`
- Do not introduce a duplicate `SubagentTask` persistence model unless execution proves session metadata is insufficient

**Step 4: Re-run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/services/test_subagent_bridge.py tests/domain/services/agents/test_spawn_tool_wiring.py -v
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add backend/app/infrastructure/services/subagent_bridge.py \
        backend/app/domain/services/agent_task_runner.py \
        backend/app/domain/services/flows/plan_act.py \
        backend/tests/infrastructure/services/test_subagent_bridge.py \
        backend/tests/domain/services/agents/test_spawn_tool_wiring.py
git commit -m "feat(agent): wire spawn tool to session-backed subagent bridge"
```

---

## Phase 4: Usage Analytics Extension (P1)

**OpenClaw Goal:** Session- and model-level cost visibility, trends, and export.

**Why:** Pythinker already records usage and exposes a settings UI. The work here is extension, not replacement.

**Integration Points:**

- `backend/app/application/services/usage_service.py`
- `backend/app/interfaces/api/usage_routes.py`
- `backend/app/interfaces/schemas/usage.py`
- `frontend/src/api/usage.ts`
- `frontend/src/components/settings/UsageSettings.vue`
- `frontend/src/components/settings/UsageChart.vue`

### Task 4.1: Extend the Backend Usage API for Date Ranges, Breakdowns, and Export

**Files:**

- Modify: `backend/app/application/services/usage_service.py`
- Modify: `backend/app/interfaces/api/usage_routes.py`
- Modify: `backend/app/interfaces/schemas/usage.py`
- Test: `backend/tests/application/services/test_usage_service.py`
- Test: `backend/tests/interfaces/api/test_usage_routes.py`

**Step 1: Write the failing tests**

```python
async def test_get_usage_breakdown_groups_by_session_and_model() -> None:
    ...


async def test_usage_export_returns_csv_rows_for_date_range() -> None:
    ...
```

Success criteria:

- Backend supports `date_from` / `date_to`
- Backend returns bounded breakdown payloads by session and model
- CSV export is generated from the existing usage source of truth

**Step 2: Run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_usage_service.py tests/interfaces/api/test_usage_routes.py -v
```

Expected: `FAIL`

**Step 3: Implement the extension**

Implementation rules:

- Reuse `UsageRecord`, `SessionUsage`, `DailyUsageAggregate`, and `MODEL_PRICING`
- Add query helpers; do not create a duplicate `mongo_usage_repository.py`
- Keep route payloads additive and backward-compatible
- Export CSV from existing records rather than from Prometheus counters

**Step 4: Re-run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_usage_service.py tests/interfaces/api/test_usage_routes.py -v
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add backend/app/application/services/usage_service.py \
        backend/app/interfaces/api/usage_routes.py \
        backend/app/interfaces/schemas/usage.py \
        backend/tests/application/services/test_usage_service.py \
        backend/tests/interfaces/api/test_usage_routes.py
git commit -m "feat(usage): add range breakdowns and csv export to existing usage API"
```

### Task 4.2: Upgrade the Existing Usage Settings UI

**Files:**

- Create: `frontend/src/components/settings/UsageBreakdownTable.vue`
- Modify: `frontend/src/components/settings/UsageSettings.vue`
- Modify: `frontend/src/components/settings/UsageChart.vue`
- Modify: `frontend/src/api/usage.ts`
- Test: `frontend/src/components/settings/__tests__/UsageSettings.spec.ts`

**Step 1: Write the failing frontend test**

```ts
import { mount } from '@vue/test-utils'
import UsageSettings from '../UsageSettings.vue'

test('renders model breakdown and export controls when usage data loads', async () => {
  ...
})
```

**Step 2: Run the test**

Run:

```bash
cd frontend && bun run test:run -- src/components/settings/__tests__/UsageSettings.spec.ts
```

Expected: `FAIL`

**Step 3: Implement the UI**

Implementation rules:

- Extend the current settings tab; do not create a new `UsagePage.vue`
- Keep the current hero cards and daily chart, then add:
  - date-range controls
  - model/session breakdown table
  - CSV export action
- Reuse existing Plotly-friendly patterns only if the current UI actually needs them

**Step 4: Re-run the test and type checks**

Run:

```bash
cd frontend && bun run test:run -- src/components/settings/__tests__/UsageSettings.spec.ts
cd frontend && bun run type-check
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add frontend/src/components/settings/UsageBreakdownTable.vue \
        frontend/src/components/settings/UsageSettings.vue \
        frontend/src/components/settings/UsageChart.vue \
        frontend/src/api/usage.ts \
        frontend/src/components/settings/__tests__/UsageSettings.spec.ts
git commit -m "feat(frontend): extend usage settings with breakdowns and export"
```

---

## Phase 5: Scheduler Convergence (P2)

**OpenClaw Goal:** Scheduled and recurring agent tasks with management APIs.

**Why:** Pythinker already has one-shot scheduling, cron tooling, and a cron bridge. The missing piece is a unified service and management surface, not a second scheduler stack.

**Integration Points:**

- `backend/app/domain/services/tools/schedule.py`
- `backend/app/domain/services/tools/cron_tool.py`
- `backend/app/infrastructure/services/cron_bridge.py`
- `backend/app/domain/models/scheduled_task.py`
- `backend/app/domain/models/scheduled_job.py`
- `backend/app/core/config_channels.py`

### Task 5.1: Introduce a Unified Scheduling Service over Existing Models

**Files:**

- Create: `backend/app/application/services/scheduling_service.py`
- Modify: `backend/app/domain/services/tools/schedule.py`
- Modify: `backend/app/domain/services/tools/cron_tool.py`
- Modify: `backend/app/infrastructure/services/cron_bridge.py`
- Test: `backend/tests/application/services/test_scheduling_service.py`
- Test: `backend/tests/domain/services/tools/test_schedule_tool.py`
- Test: `backend/tests/infrastructure/services/test_cron_bridge.py`

**Step 1: Write the failing tests**

```python
async def test_schedule_service_creates_one_shot_task() -> None:
    ...


async def test_schedule_service_creates_cron_job() -> None:
    ...


async def test_schedule_service_lists_mixed_scheduled_work() -> None:
    ...
```

**Step 2: Run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_scheduling_service.py tests/domain/services/tools/test_schedule_tool.py tests/infrastructure/services/test_cron_bridge.py -v
```

Expected: `FAIL`

**Step 3: Implement the service**

Implementation rules:

- Keep `ScheduleTool` for deferred / one-shot work
- Keep `CronTool` for cron-like recurring work
- Add a single application service that hides which backend is used
- Reuse existing domain models; do not create a parallel `cron_job.py`
- If the nanobot bridge proves insufficient later, the implementation may migrate behind the same service boundary without changing the tool interfaces

**Step 4: Re-run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_scheduling_service.py tests/domain/services/tools/test_schedule_tool.py tests/infrastructure/services/test_cron_bridge.py -v
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add backend/app/application/services/scheduling_service.py \
        backend/app/domain/services/tools/schedule.py \
        backend/app/domain/services/tools/cron_tool.py \
        backend/app/infrastructure/services/cron_bridge.py \
        backend/tests/application/services/test_scheduling_service.py \
        backend/tests/domain/services/tools/test_schedule_tool.py \
        backend/tests/infrastructure/services/test_cron_bridge.py
git commit -m "feat(schedule): converge deferred and cron scheduling behind one service"
```

### Task 5.2: Add Management APIs on Top of the Unified Service

**Files:**

- Create: `backend/app/interfaces/api/cron_routes.py`
- Modify: `backend/app/interfaces/api/routes.py`
- Create: `backend/app/interfaces/schemas/cron.py`
- Test: `backend/tests/interfaces/api/test_cron_routes.py`

**Step 1: Write the failing tests**

```python
async def test_create_cron_job_route() -> None:
    ...


async def test_list_scheduled_work_route() -> None:
    ...


async def test_delete_scheduled_job_route() -> None:
    ...
```

**Step 2: Run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_cron_routes.py -v
```

Expected: `FAIL`

**Step 3: Implement the routes**

Implementation rules:

- Route handlers stay thin and delegate to `SchedulingService`
- Reuse the existing auth/user dependency stack
- Do not bypass the service layer to talk directly to `CronBridge`

**Step 4: Re-run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_cron_routes.py -v
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add backend/app/interfaces/api/cron_routes.py \
        backend/app/interfaces/schemas/cron.py \
        backend/app/interfaces/api/routes.py \
        backend/tests/interfaces/api/test_cron_routes.py
git commit -m "feat(schedule): add management api for unified scheduled work"
```

---

## Phase 6: Shared Tool Schema Normalization (P2)

**OpenClaw Goal:** Tool calling remains stable across providers.

**Why:** The repo already adapts Anthropic tools and has strict JSON handling in the OpenAI adapter. The missing piece is a shared adapter so provider quirks are declared once.

**Integration Points:**

- `backend/app/infrastructure/external/llm/anthropic_llm.py`
- `backend/app/infrastructure/external/llm/openai_llm.py`
- `backend/app/infrastructure/external/llm/ollama_llm.py`
- `backend/app/infrastructure/external/llm/provider_profile.py`

### Task 6.1: Centralize Tool Schema Adaptation

**Files:**

- Create: `backend/app/domain/services/tools/schema_normalizer.py`
- Modify: `backend/app/infrastructure/external/llm/anthropic_llm.py`
- Modify: `backend/app/infrastructure/external/llm/openai_llm.py`
- Modify: `backend/app/infrastructure/external/llm/ollama_llm.py`
- Test: `backend/tests/domain/services/tools/test_schema_normalizer.py`

**Step 1: Write the failing tests**

```python
from app.domain.services.tools.schema_normalizer import normalize_tool_schema


def test_anthropic_uses_input_schema() -> None:
    tool = {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        },
    }
    normalized = normalize_tool_schema(tool, provider="anthropic")
    assert normalized["input_schema"]["type"] == "object"


def test_openai_compatible_passes_through_function_shape() -> None:
    ...
```

**Step 2: Run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/tools/test_schema_normalizer.py -v
```

Expected: `FAIL`

**Step 3: Implement the shared normalizer**

Implementation rules:

- Keep the normalizer pure and provider-key driven
- Support the providers that exist in this repo today:
  - `anthropic`
  - `openai` / openai-compatible
  - `ollama`
  - `strict_schema` providers if required by `ProviderProfile`
- Do not document Gemini/xAI-specific behavior until those adapters actually exist in the repo

**Step 4: Re-run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/tools/test_schema_normalizer.py -v
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add backend/app/domain/services/tools/schema_normalizer.py \
        backend/app/infrastructure/external/llm/anthropic_llm.py \
        backend/app/infrastructure/external/llm/openai_llm.py \
        backend/app/infrastructure/external/llm/ollama_llm.py \
        backend/tests/domain/services/tools/test_schema_normalizer.py
git commit -m "feat(llm): centralize provider-specific tool schema normalization"
```

---

## Phase 7: Background Shell Execution on Existing Sessions (P3)

**OpenClaw Goal:** Start long-running shell work, keep working, and check back later.

**Why:** Pythinker already has shell sessions, `shell_wait`, `shell_view`, `shell_kill_process`, and live streaming. The missing piece is an explicit background execution contract that uses the existing session ID and process wait APIs.

**Integration Points:**

- `backend/app/domain/services/tools/shell.py`
- `backend/app/domain/external/sandbox.py`
- `backend/app/infrastructure/external/sandbox/docker_sandbox.py`
- `backend/app/domain/services/tools/shell_output_poller.py`

### Task 7.1: Add Background Execution Ergonomics to `ShellTool`

**Files:**

- Modify: `backend/app/domain/services/tools/shell.py`
- Modify: `backend/app/domain/external/sandbox.py`
- Modify: `backend/app/infrastructure/external/sandbox/docker_sandbox.py`
- Test: `backend/tests/domain/services/tools/test_shell_background.py`
- Test: `backend/tests/infrastructure/external/sandbox/test_docker_sandbox_shell_background.py`

**Step 1: Write the failing tests**

```python
async def test_shell_exec_background_returns_running_session_metadata() -> None:
    ...


async def test_shell_exec_background_reuses_same_session_id_for_wait_and_view() -> None:
    ...
```

**Step 2: Run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/tools/test_shell_background.py tests/infrastructure/external/sandbox/test_docker_sandbox_shell_background.py -v
```

Expected: `FAIL`

**Step 3: Implement the contract**

Implementation rules:

- Prefer `background: bool = False` on the existing `shell_exec` tool surface
- Reuse the current shell session ID as the tracking handle
- If sandbox changes are required, add them behind the existing `Sandbox` protocol
- Do not create a separate `process_supervisor.py` registry in Pythinker unless the sandbox API gives no workable non-blocking primitive

**Step 4: Re-run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/tools/test_shell_background.py tests/infrastructure/external/sandbox/test_docker_sandbox_shell_background.py -v
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add backend/app/domain/services/tools/shell.py \
        backend/app/domain/external/sandbox.py \
        backend/app/infrastructure/external/sandbox/docker_sandbox.py \
        backend/tests/domain/services/tools/test_shell_background.py \
        backend/tests/infrastructure/external/sandbox/test_docker_sandbox_shell_background.py
git commit -m "feat(shell): add background execution on existing shell sessions"
```

---

## Phase 8: Plugin Loader Generalization (P3)

**OpenClaw Goal:** Formal plugin SDK with lifecycle hooks and conflict detection.

**Why:** The repo already loads plugins via entry points. The right move is to formalize and extend that loader, not replace it with a filesystem scanner.

**Integration Points:**

- `backend/app/infrastructure/plugins/skill_plugin_loader.py`
- `backend/app/core/lifespan.py`
- `backend/app/domain/services/tools/dynamic_toolset.py`

### Task 8.1: Move Plugin Protocol to the Domain and Extend the Entry-Point Loader

**Files:**

- Create: `backend/app/domain/services/plugins/protocol.py`
- Modify: `backend/app/infrastructure/plugins/skill_plugin_loader.py`
- Modify: `backend/app/core/lifespan.py`
- Test: `backend/tests/infrastructure/plugins/test_skill_plugin_loader.py`

**Step 1: Write the failing tests**

```python
async def test_loader_accepts_domain_protocol_plugin() -> None:
    ...


async def test_loader_calls_optional_on_load_hook() -> None:
    ...


def test_loader_reports_tool_name_conflicts_without_crashing() -> None:
    ...
```

**Step 2: Run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/plugins/test_skill_plugin_loader.py -v
```

Expected: `FAIL`

**Step 3: Implement the generalized loader**

Implementation rules:

- Keep Python entry-point discovery via `importlib.metadata.entry_points(group=...)`
- Move the protocol definition into the domain layer
- Support optional metadata and lifecycle hooks:
  - `plugin_id`
  - `plugin_version`
  - `on_load()`
  - `on_unload()`
- Preserve the current ability to register tools into `DynamicToolsetManager`
- Emit warnings for tool conflicts; do not crash startup over a single plugin

**Step 4: Re-run the tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/plugins/test_skill_plugin_loader.py -v
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add backend/app/domain/services/plugins/protocol.py \
        backend/app/infrastructure/plugins/skill_plugin_loader.py \
        backend/app/core/lifespan.py \
        backend/tests/infrastructure/plugins/test_skill_plugin_loader.py
git commit -m "feat(plugins): formalize entry-point plugin sdk and lifecycle hooks"
```

---

## Implementation Order & Dependencies

```text
Phase 1 (Tool Governance & Approval Convergence)
  └─> Phase 7 (Background Shell Execution) benefits from the same risk model

Phase 2 (Dynamic Toolset Profile Hints)
  └─> Phase 8 (Plugin Loader Generalization) should register plugin tools with the improved scorer

Phase 3 (Subagent Spawning Completion)
  └─> Independent once the bridge contract is agreed

Phase 4 (Usage Analytics Extension)
  └─> Independent

Phase 5 (Scheduler Convergence)
  └─> Independent

Phase 6 (Shared Tool Schema Normalization)
  └─> Independent
```

**Recommended order:**

1. Phase 1
2. Phase 2
3. Phase 4
4. Phase 5
5. Phase 3
6. Phase 6
7. Phase 7
8. Phase 8

**Parallel tracks:**

- Track A: Phase 1 + Phase 2
- Track B: Phase 4 + Phase 5
- Track C: Phase 3
- Track D: Phase 6 + Phase 7
- Track E: Phase 8 after Phase 2 is stable

---

## Feature Flags Summary

### Existing Flags To Reuse

```python
# Existing; keep current defaults factual
feature_hitl_enabled: bool = True
feature_url_failure_guard_enabled: bool = True
cron_service_enabled: bool = False
subagent_spawning_enabled: bool = False
feature_live_shell_streaming: bool = False
```

### New Flags To Add

```python
# Phase 1
feature_tool_governance_enabled: bool = False

# Phase 2
feature_dynamic_tool_profiles_enabled: bool = False

# Phase 4
feature_usage_exports_enabled: bool = False

# Phase 6
feature_tool_schema_adapter_enabled: bool = False

# Phase 7
feature_shell_background_execution_enabled: bool = False

# Phase 8
feature_plugin_lifecycle_hooks_enabled: bool = False
```

Notes:

- Prefer additive flags for new behavior
- Do not introduce new flags when an existing one already controls the capability
- Preserve current defaults exactly unless a migration note explicitly changes them

---

## Testing Strategy

Each phase follows TDD, but test commands must match this repo’s documented workflow.

### Backend Single-Test Runs

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/agents/test_tool_governance.py -v
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/agents/test_pending_action_governance.py -v
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/agents/test_outbound_url_policy.py -v
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/tools/test_dynamic_toolset_profiles.py -v
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/services/test_subagent_bridge.py tests/domain/services/agents/test_spawn_tool_wiring.py -v
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_usage_service.py tests/interfaces/api/test_usage_routes.py -v
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_scheduling_service.py tests/domain/services/tools/test_schedule_tool.py tests/infrastructure/services/test_cron_bridge.py -v
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/tools/test_schema_normalizer.py -v
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/tools/test_shell_background.py tests/infrastructure/external/sandbox/test_docker_sandbox_shell_background.py -v
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/plugins/test_skill_plugin_loader.py -v
```

### Frontend Targeted Test

```bash
cd frontend && bun run test:run -- src/components/settings/__tests__/UsageSettings.spec.ts
```

### Full Verification Before Merge

```bash
conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/
cd frontend && bun run lint && bun run type-check && bun run test:run
```

---

## File Impact Summary

| Phase | New Files | Modified Files | Test Files |
|-------|-----------|----------------|------------|
| 1. Tool Governance | 2 | 6 | 3 |
| 2. Tool Profiles | 1 | 2 | 1 |
| 3. Subagent Bridge | 1 | 2 | 2 |
| 4. Usage Extension | 1 | 6 | 3 |
| 5. Scheduler Convergence | 3 | 4 | 4 |
| 6. Schema Normalization | 1 | 3 | 1 |
| 7. Shell Background Execution | 0 | 3 | 2 |
| 8. Plugin Generalization | 1 | 2 | 1 |
| **Total** | **10** | **28** | **17** |

These counts are directional and should be updated if implementation reveals fewer files are needed. The non-goal remains: avoid duplicate subsystems.

---

## Verification Checklist (Per Phase)

- [ ] Status remains factual: no section is marked `Completed` unless the repo actually contains the working implementation
- [ ] New behavior extends an existing subsystem instead of duplicating it
- [ ] Domain layer remains free of `app.core.config` and infrastructure imports
- [ ] Feature flags default correctly and existing defaults are preserved where unchanged
- [ ] Prometheus metrics use bounded labels only
- [ ] Single-test commands use `-p no:cov -o addopts=`
- [ ] Backend tests pass for the touched phase
- [ ] Frontend tests and type checks pass for the touched phase
- [ ] `ruff check . && ruff format --check .` passes
- [ ] `pytest tests/` passes
- [ ] `cd frontend && bun run lint && bun run type-check && bun run test:run` passes

---

## Notes From External Sources

- APScheduler’s documented recommendation for durable schedules is to use a persistent data store with explicit identifiers and conflict policies; if Pythinker later outgrows the current cron backend, migrate behind the unified `SchedulingService` boundary instead of adding a second public API.
- Prometheus documentation explicitly warns against high-cardinality labels such as free-form reason text; metrics in this plan must use bounded decision codes.
- Python `importlib.metadata` already provides entry-point discovery that fits the current plugin loader; extend that mechanism rather than replacing it with a custom plugin scan path.
