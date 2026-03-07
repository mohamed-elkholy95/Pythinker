# Telegram Report Integrity Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent reused Telegram sessions from contaminating current report delivery, block weakly grounded final reports from being sent, and reduce unnecessary end-of-run latency.

**Architecture:** Introduce a per-run delivery scope inside a reused session, tag synced files with that scope, and filter sweep/summarization/attachment merging to the active scope only. Tighten delivery integrity so report-structured Telegram output either passes grounding checks or falls back to the already-captured full draft instead of sending a polished but weak summary. Keep the emoji cleanup as a scoped follow-up, not the primary remediation.

**Tech Stack:** Python 3.12, pytest, async domain services, Telegram PDF delivery policy, file sync/session repository pipeline, existing summarization and delivery-integrity gates.

---

## Root Cause Summary

- Reused Telegram sessions currently keep the same workspace root under `/workspace/<session_id>`, so old run artifacts remain present between requests.
- The pre-summary sweep scans the whole session workspace and can upload stale files if they were never registered in `session.files`.
- `PlanActFlow` injects every `session.files` entry into the summarization prompt and final attachment merge, so once a stale file is present, it is eligible for the final report and Telegram delivery path.
- The delivery-integrity gate currently allows some report-quality failures to degrade to warnings, which means a final report can still be emitted even when grounding is weak or verification was skipped.
- The current emoji-removal changes are valid as formatting cleanup, but they do not address the Telegram monitoring report's highest-severity failures.

## Design Decision

**Recommended approach:** delivery-scope isolation + scope-aware file filtering + stricter report grounding gate + pre-trim draft fallback.

Why this approach:
- It fixes the contamination bug at the source instead of masking it during delivery.
- It preserves Telegram session continuity without reusing the same deliverable workspace for every run.
- It lets the system reuse the existing full draft (`_pre_trim_report_cache`) when summarization quality regresses.
- It keeps cosmetic cleanup separate from correctness and evidence integrity.

Rejected alternatives:
- Disable Telegram completed-session reuse entirely: fixes contamination, but breaks the continuity policy that the repo explicitly added for Telegram.
- Rely on basename dedup during file sweep only: insufficient because stale files are already valid deliverables and can still be injected through `session.files`.
- Keep warning-only delivery for weak reports: unacceptable for final-only Telegram delivery because the user receives the degraded artifact with no safer fallback.

### Backward Compatibility Note

The workspace restructuring moves report outputs from `/workspace/{session_id}/output/` to `/workspace/{session_id}/runs/{scope_id}/output/`. Existing reused Telegram sessions already have files at the old flat path. On the first run after deploy:

- `_filter_files_for_delivery_scope()` will correctly exclude old files (no `delivery_scope` metadata, path outside the new scope root).
- The pre-trim cache is in-memory (not path-based), so the Task 4 fallback still works even if the cached draft was originally written to the old flat path.
- This means the first run on an existing session produces a clean break from stale artifacts, which is the desired behavior.

No migration script is needed — the old flat-path files simply become inert. Verify this with a manual test against a long-lived Telegram session after deploy.

---

### Task 1: Lock the contamination and grounding regressions with failing tests

**Files:**
- Create: `backend/tests/domain/services/flows/test_plan_act_delivery_scope.py`
- Modify: `backend/tests/domain/services/test_file_sweep.py`
- Modify: `backend/tests/integration/test_delivery_integrity_gate.py`
- Modify: `backend/tests/unit/agents/test_report_output_sanitizer.py`

**Step 1: Write a failing flow test for scope-filtered session files**

Create `backend/tests/domain/services/flows/test_plan_act_delivery_scope.py` with a focused test like:

```python
from types import SimpleNamespace

from app.domain.models.file import FileInfo


def test_filter_session_files_for_active_delivery_scope_prefers_metadata():
    from app.domain.services.flows.plan_act import PlanActFlow

    active_scope = "run-2"
    scope_root = "/workspace/s1/runs/run-2"
    files = [
        FileInfo(
            filename="old-report.md",
            file_path="/workspace/s1/runs/run-1/reports/old-report.md",
            metadata={"delivery_scope": "run-1"},
        ),
        FileInfo(
            filename="current-report.md",
            file_path="/workspace/s1/runs/run-2/reports/current-report.md",
            metadata={"delivery_scope": "run-2"},
        ),
    ]

    result = PlanActFlow._filter_files_for_delivery_scope(files, active_scope, scope_root)

    assert [f.filename for f in result] == ["current-report.md"]
```

**Step 2: Write a failing sweep test for workspace-root scoping**

Extend `backend/tests/domain/services/test_file_sweep.py` with a test that proves stale files outside the active scope are ignored:

```python
@pytest.mark.asyncio
async def test_sweep_ignores_files_outside_active_delivery_scope(...):
    manager.set_delivery_scope("run-2", "/workspace/test-session/runs/run-2")
    mock_sandbox.exec_command = AsyncMock(
        return_value=ToolResult(
            success=True,
            data={
                "output": (
                    "/workspace/test-session/runs/run-1/report-old.md\n"
                    "/workspace/test-session/runs/run-2/report-current.md\n"
                )
            },
        )
    )

    result = await manager.sweep_workspace_files()

    assert [f.filename for f in result] == ["report-current.md"]
```

**Step 3: Write a failing delivery-integrity regression test**

Extend `backend/tests/integration/test_delivery_integrity_gate.py` with a case where:
- the summary is report-shaped
- references are missing or verification is skipped
- `_pre_trim_report_cache` contains a grounded draft

Expected behavior:
- the final emitted `ReportEvent` uses the pre-trim draft
- no degraded weak summary is emitted

**Step 4: Write a failing sanitizer guardrail test**

Extend `backend/tests/unit/agents/test_report_output_sanitizer.py` with:

```python
def test_sanitize_report_output_preserves_quoted_source_content() -> None:
    content = "> Survey wording copied from source"

    result = sanitize_report_output(content)

    assert result == content
```

**Step 5: Run the new focused tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= \
  tests/domain/services/flows/test_plan_act_delivery_scope.py \
  tests/domain/services/test_file_sweep.py \
  tests/integration/test_delivery_integrity_gate.py \
  tests/unit/agents/test_report_output_sanitizer.py -q
```

Expected: FAIL. The current implementation does not yet have delivery-scope filtering or weak-summary fallback, and the sanitizer still strips generic blockquotes.

**Step 6: Commit**

```bash
git add \
  backend/tests/domain/services/flows/test_plan_act_delivery_scope.py \
  backend/tests/domain/services/test_file_sweep.py \
  backend/tests/integration/test_delivery_integrity_gate.py \
  backend/tests/unit/agents/test_report_output_sanitizer.py
git commit -m "test: lock telegram report integrity regressions"
```

### Task 2: Introduce an active delivery scope for each run inside a reused session

**Files:**
- Modify: `backend/app/core/config_features.py`
- Modify: `backend/app/domain/services/flows/plan_act.py`
- Modify: `backend/app/domain/services/file_sync_manager.py`
- Modify: `backend/app/domain/services/agent_task_runner.py`
- Modify: `backend/app/domain/services/prompts/execution.py`
- Extend: `backend/tests/domain/services/flows/test_plan_act_delivery_scope.py`
- Extend: `backend/tests/domain/services/test_file_sweep.py`

**Step 1: Add a feature flag for delivery-scope isolation**

In `backend/app/core/config_features.py`, add:

```python
feature_delivery_scope_isolation: bool = False  # Isolate deliverables per run in reused sessions
```

Wire it into the feature-flags dict in `config.py` alongside the other flags.

When this flag is disabled, all scope-related behavior must fall back to the current flat `/workspace/{session_id}/` structure. Every scope-dependent code path added in Tasks 2-6 must check this flag and use the legacy path when disabled.

**Step 2: Add delivery-scope state to `PlanActFlow`**

In `PlanActFlow.__init__`, add:

```python
self._delivery_scope_id: str | None = None
self._delivery_scope_root: str | None = None
```

Then add a small helper on `PlanActFlow`:

```python
def _initialize_delivery_scope(self) -> None:
    if not self._feature_flags.get("delivery_scope_isolation"):
        return
    scope_id = self._task_id or str(uuid.uuid4())
    self._delivery_scope_id = scope_id
    self._delivery_scope_root = f"/workspace/{self._session_id}/runs/{scope_id}"
```

Call it once at the start of `run()` before any workspace creation or file sweep.

**Step 3: Move report workspaces under the active scope**

Replace the session-wide deep-research output path:

```python
workspace_base = f"/workspace/{self._session_id}"
workspace_path = f"{workspace_base}/output"
```

with:

```python
workspace_base = self._delivery_scope_root or f"/workspace/{self._session_id}"
workspace_path = f"{workspace_base}/output"
```

Keep the `reports`, `charts`, `data`, and `code` subdirectories unchanged beneath that active scope.

**Step 4: Thread the active scope into file sync via `agent_task_runner.py`**

Add a setter to `FileSyncManager`:

```python
def set_delivery_scope(self, scope_id: str, workspace_root: str) -> None:
    self._delivery_scope_id = scope_id
    self._workspace_root = workspace_root.rstrip("/")
```

Then use `self._workspace_root` (when set) instead of `f"/workspace/{self._session_id}"` in `sweep_workspace_files()`. When `self._workspace_root` is `None`, fall back to the legacy session-root path.

**Critical wiring step:** In `agent_task_runner.py`, propagate the scope from `PlanActFlow` to `FileSyncManager`. The scope is initialized inside `PlanActFlow.run()` but the `FileSyncManager` instance lives on `AgentTaskRunner`. Thread this by either:

- (a) Passing the `FileSyncManager` reference into `PlanActFlow` and calling `set_delivery_scope()` from `_initialize_delivery_scope()`, or
- (b) Adding a `scope_callback` parameter to `PlanActFlow.__init__` (alongside the existing `file_sweep_callback`) that `AgentTaskRunner` provides to bridge the scope back:

```python
# In agent_task_runner.py, when constructing PlanActFlow:
def _set_delivery_scope(scope_id: str, root: str) -> None:
    self._file_sync_manager.set_delivery_scope(scope_id, root)

flow = PlanActFlow(
    ...,
    file_sweep_callback=self._sweep_workspace_files,
    scope_callback=_set_delivery_scope,
)
```

Choose whichever approach is simpler given the existing constructor signatures. The key requirement is that `FileSyncManager.set_delivery_scope()` is called **before** `sweep_workspace_files()` runs.

**Step 5: Tag synced files with delivery-scope metadata**

When `sync_file_to_storage()` registers a file, merge:

```python
scope_metadata = {
    "delivery_scope": self._delivery_scope_id,
    "delivery_root": self._workspace_root,
}
```

into the stored `FileInfo.metadata`. Also include `"is_report": True` when the file lives under `/output/reports/` or its basename starts with `report-` or `full-report-`. This metadata flag is used in Task 5 to scope the sanitizer correctly.

**Step 6: Update prompt instructions to use the active scope root**

Where `build_workspace_context()` is injected, pass the scope-specific workspace path so the model saves report files into the current run root instead of the session root.

**Step 7: Prune old scope directories (bounded retention)**

Add a helper to `FileSyncManager` or call it from `_initialize_delivery_scope()`:

```python
async def _prune_old_delivery_scopes(self, keep_latest: int = 3) -> None:
    """Remove old scope directories to prevent disk growth on long-lived sessions."""
    runs_root = f"/workspace/{self._session_id}/runs"
    ls_cmd = f"ls -1t {runs_root} 2>/dev/null"
    result = await self._sandbox.exec_command("prune", runs_root, ls_cmd)
    if not result.success:
        return
    dirs = [d.strip() for d in (result.data or {}).get("output", "").strip().split("\n") if d.strip()]
    stale = dirs[keep_latest:]
    for d in stale:
        rm_cmd = f"rm -rf {runs_root}/{d}"
        await self._sandbox.exec_command("prune", runs_root, rm_cmd)
```

Call this once after `_initialize_delivery_scope()`, before the main execution loop. This keeps at most 3 scope directories per session and prevents unbounded disk growth on long-lived Telegram sessions.

**Step 8: Run the scope tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= \
  tests/domain/services/flows/test_plan_act_delivery_scope.py \
  tests/domain/services/test_file_sweep.py -q
```

Expected: PASS

**Step 9: Commit**

```bash
git add \
  backend/app/core/config_features.py \
  backend/app/core/config.py \
  backend/app/domain/services/flows/plan_act.py \
  backend/app/domain/services/file_sync_manager.py \
  backend/app/domain/services/agent_task_runner.py \
  backend/app/domain/services/prompts/execution.py \
  backend/tests/domain/services/flows/test_plan_act_delivery_scope.py \
  backend/tests/domain/services/test_file_sweep.py
git commit -m "fix: isolate telegram deliverables by active run scope"
```

### Task 3: Filter session files, manifests, and final attachments to the active scope

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py`
- Modify: `backend/app/domain/services/agent_task_runner.py`
- Modify: `backend/app/core/prometheus_metrics.py`
- Modify: `backend/tests/domain/services/flows/test_plan_act_artifact_manifest.py`
- Modify: `backend/tests/domain/services/test_report_file_attachment.py`

**Step 1: Add a pure helper for scope filtering**

In `PlanActFlow`, add:

```python
@staticmethod
def _filter_files_for_delivery_scope(
    files: list[FileInfo],
    delivery_scope_id: str | None,
    delivery_scope_root: str | None,
) -> list[FileInfo]:
    if not delivery_scope_id and not delivery_scope_root:
        return files  # Feature disabled or no scope — pass everything through
    filtered: list[FileInfo] = []
    for file_info in files:
        metadata = file_info.metadata or {}
        if delivery_scope_id and metadata.get("delivery_scope") == delivery_scope_id:
            filtered.append(file_info)
            continue
        if delivery_scope_root and file_info.file_path and file_info.file_path.startswith(f"{delivery_scope_root}/"):
            filtered.append(file_info)
    return filtered
```

Note: when both `delivery_scope_id` and `delivery_scope_root` are `None` (feature flag off), the function returns all files unchanged, preserving legacy behavior.

**Step 2: Filter `session_files` before prompt injection**

Change the summarization path from:

```python
session_files = session.files
```

to:

```python
session_files = self._filter_files_for_delivery_scope(
    session.files or [],
    self._delivery_scope_id,
    self._delivery_scope_root,
)
```

This same filtered list must drive:
- the `## Session Deliverables` prompt block
- `_report_attachments`
- the final `all_attachments` merge before report emission

**Step 3: Keep pre-summarization full reports in the active scope**

Update `AgentTaskRunner._persist_report_content_as_attachment()` so:
- `full-report-<event.id>.md`
- `report-<event.id>.md`

are written under the active delivery root when one is available, and carry the same `delivery_scope` metadata as synced files.

**Step 4: Add observability for scope filtering**

In `backend/app/core/prometheus_metrics.py`, add:

```python
delivery_scope_files_filtered_total = Counter(
    name="pythinker_delivery_scope_files_filtered_total",
    documentation="Files excluded from delivery by scope filtering",
    labelnames=["reason"],  # "metadata_mismatch", "path_mismatch"
)
```

Wire it into the metrics adapter. In `_filter_files_for_delivery_scope()`, record the count of excluded files:

```python
excluded_count = len(files) - len(filtered)
if excluded_count > 0:
    logger.info("Delivery scope filtered %d of %d files", excluded_count, len(files))
    # Emit metric via the metrics adapter if available
```

This gives production visibility into whether contamination is actually being prevented.

**Step 5: Extend manifest and attachment tests**

Add tests that prove:
- stale attachments from another scope are excluded from the deliverables manifest
- final `ReportEvent.attachments` only contains files from the current scope
- when scope isolation is disabled (feature flag off), all files pass through unchanged

**Step 6: Run the filtering tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= \
  tests/domain/services/flows/test_plan_act_delivery_scope.py \
  tests/domain/services/flows/test_plan_act_artifact_manifest.py \
  tests/domain/services/test_report_file_attachment.py -q
```

Expected: PASS

**Step 7: Commit**

```bash
git add \
  backend/app/domain/services/flows/plan_act.py \
  backend/app/domain/services/agent_task_runner.py \
  backend/app/core/prometheus_metrics.py \
  backend/app/infrastructure/observability/metrics_port_adapter.py \
  backend/tests/domain/services/flows/test_plan_act_artifact_manifest.py \
  backend/tests/domain/services/test_report_file_attachment.py
git commit -m "fix: restrict report manifests and attachments to active scope"
```

### Task 4: Make report grounding failures block final-only Telegram delivery and fall back to the full draft

**Files:**
- Modify: `backend/app/domain/services/agents/execution.py`
- Modify: `backend/app/domain/services/agents/response_generator.py`
- Modify: `backend/tests/integration/test_delivery_integrity_gate.py`
- Modify: `backend/tests/unit/agents/test_report_quality_pipeline.py`

**Step 1: Add delivery-channel awareness to the integrity gate**

Add a `delivery_channel: str | None` parameter to `ResponseGenerator.run_delivery_integrity_gate()`:

```python
def run_delivery_integrity_gate(
    self,
    content: str,
    ...,
    delivery_channel: str | None = None,
) -> tuple[bool, list[str]]:
```

When `delivery_channel == "telegram"` (or any future final-only channel), treat the following as **blocking** for report-structured outputs:
- `hallucination_verification_skipped`
- missing references when inline citations exist or collected sources exist
- `coverage_missing:artifact references` for final report delivery

When `delivery_channel` is `None` or `"web"`, preserve the current behavior (warnings, not blocking). This keeps the web UI experience unchanged while tightening Telegram-specific gates.

Thread the `delivery_channel` value from `PlanActFlow` (which knows the session's channel) through `ExecutionAgent` to the gate call.

**Step 2: Reuse the existing delivery-integrity gate for pre-trim fallback (not a new helper)**

In `ExecutionAgent.summarize()`, after the delivery-integrity gate fails on the summary, run the **same gate** on the pre-trim cache instead of introducing a separate `_report_has_grounding()` helper:

```python
if self._pre_trim_report_cache:
    cache_passed, cache_issues = self._run_delivery_integrity_gate(
        self._pre_trim_report_cache,
        ...,
        delivery_channel=delivery_channel,
    )
    if cache_passed:
        logger.info(
            "Summary failed gate but pre-trim draft passed (%d chars) — using draft",
            len(self._pre_trim_report_cache),
        )
        message_content = self._pre_trim_report_cache
        gate_passed = True
        gate_issues = []
```

This avoids creating a fourth parallel verification path alongside `OutputVerifier`, `run_delivery_integrity_gate()`, and `citation_integrity`. All grounding assessment stays unified through the existing gate.

**Step 3: Fail closed when neither summary nor pre-trim draft is acceptable**

If the summary fails and the pre-trim draft also fails the gate:
- emit `ErrorEvent`
- do not send a final `ReportEvent`

That is the correct trade-off for Telegram final-only delivery.

**Step 4: Extend integration coverage**

Add three tests:

1. `test_completed_plan_summary_uses_pretrim_report_when_summary_drops_references`
2. `test_completed_plan_summary_blocks_when_summary_and_pretrim_report_both_fail_grounding`
3. `test_delivery_integrity_gate_applies_strict_blocking_only_for_telegram_channel` — verify that the same issues that block Telegram delivery are only warnings for the web channel

**Step 5: Run the grounding tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= \
  tests/integration/test_delivery_integrity_gate.py \
  tests/unit/agents/test_report_quality_pipeline.py -q
```

Expected: PASS

**Step 6: Commit**

```bash
git add \
  backend/app/domain/services/agents/execution.py \
  backend/app/domain/services/agents/response_generator.py \
  backend/tests/integration/test_delivery_integrity_gate.py \
  backend/tests/unit/agents/test_report_quality_pipeline.py
git commit -m "fix: block weak telegram reports and fall back to full draft"
```

### Task 5: Narrow the emoji sanitizer so it does not rewrite quoted source content

**Files:**
- Modify: `backend/app/domain/services/agents/report_output_sanitizer.py`
- Modify: `backend/app/domain/services/tools/file.py`
- Modify: `backend/tests/unit/agents/test_report_output_sanitizer.py`
- Modify: `backend/tests/domain/services/tools/test_file_tool_read_retry.py`

**Step 1: Restrict sanitization to headings and known notices**

Replace the generic blockquote rule with a targeted notice rule such as:

```python
_NOTICE_PREFIX_RE = re.compile(
    r"^(>\s+)(?:(?:⚠️|⚠)\s+)?(\*\*(?:Incomplete Report|Partial Report):\*\*.*)$"
)
```

Keep heading cleanup, but stop stripping emoji from arbitrary quoted text.

**Step 2: Use metadata to scope sanitization in `file.py`**

In `file.py`, only call `sanitize_report_output()` when the file is a known report artifact. Since Task 2 Step 5 already adds `"is_report": True` metadata during sync, prefer the metadata check:

```python
is_report = (metadata or {}).get("is_report", False)
if not is_report:
    # Fallback: check path/basename heuristics
    basename = os.path.basename(file_path)
    is_report = (
        basename.startswith("report-")
        or basename.startswith("full-report-")
        or "/output/reports/" in file_path
    )

if is_report:
    cleaned = sanitize_report_output(cleaned)
```

This uses a single source of truth (metadata) with a path-based fallback, and avoids running the sanitizer on every `.md`, `.txt`, or `.rst` file write.

**Step 3: Extend tests for preservation**

Add assertions that:
- report headings are still cleaned
- quoted source text is preserved
- generic markdown documents outside report paths are not rewritten
- files with `is_report: True` metadata are sanitized regardless of path

**Step 4: Run the sanitizer tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= \
  tests/unit/agents/test_report_output_sanitizer.py \
  tests/domain/services/tools/test_file_tool_read_retry.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add \
  backend/app/domain/services/agents/report_output_sanitizer.py \
  backend/app/domain/services/tools/file.py \
  backend/tests/unit/agents/test_report_output_sanitizer.py \
  backend/tests/domain/services/tools/test_file_tool_read_retry.py
git commit -m "fix: narrow report emoji sanitization to report artifacts"
```

### Task 6: Cut Telegram latency by skipping redundant summarization when the current draft is already deliverable

**Files:**
- Modify: `backend/app/domain/services/agents/execution.py`
- Modify: `backend/tests/integration/test_delivery_integrity_gate.py`
- Modify: `backend/tests/unit/agents/test_report_quality_pipeline.py`

**Step 1: Add a short-circuit eligibility helper**

Add a named constant and helper in `ExecutionAgent`:

```python
MIN_DIRECT_DELIVERY_REPORT_LENGTH = 1200  # Minimum chars for a report to skip summarization

def _can_deliver_pretrim_report_directly(self, delivery_channel: str | None = None) -> bool:
    """Check if the pre-trim draft can be sent without a summarization pass.

    Only applies when the draft passes the full delivery-integrity gate
    and exceeds the minimum length threshold. The 1200-char floor prevents
    short stubs or partial drafts from bypassing quality-improving summarization.
    """
    if not self._pre_trim_report_cache:
        return False
    if len(self._pre_trim_report_cache) < MIN_DIRECT_DELIVERY_REPORT_LENGTH:
        return False
    cache_passed, _ = self._run_delivery_integrity_gate(
        self._pre_trim_report_cache,
        ...,
        delivery_channel=delivery_channel,
    )
    return cache_passed
```

Note: this reuses `_run_delivery_integrity_gate()` for consistency with Task 4's approach of keeping all grounding checks unified.

**Step 2: Skip summarization when the full draft already passes**

Before launching the summarization stream, if `_can_deliver_pretrim_report_directly()` is true:
- use `_pre_trim_report_cache`
- still run citation/delivery-integrity checks
- emit the final report without incurring the extra summarize call
- log the decision and time saved:

```python
logger.info(
    "Skipping summarization — pre-trim draft passed gate directly (%d chars)",
    len(self._pre_trim_report_cache),
)
```

**Step 3: Add latency-focused regression coverage**

Add a test that proves:
- `ask_stream()` is not called for summarization when the cached draft is already deliverable
- a valid `ReportEvent` is still emitted
- the test verifies gate was invoked on the cached content (not skipped entirely)

**Step 4: Run the targeted latency tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= \
  tests/integration/test_delivery_integrity_gate.py \
  tests/unit/agents/test_report_quality_pipeline.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add \
  backend/app/domain/services/agents/execution.py \
  backend/tests/integration/test_delivery_integrity_gate.py \
  backend/tests/unit/agents/test_report_quality_pipeline.py
git commit -m "perf: skip redundant telegram report summarization"
```

### Task 7: End-to-end integration test, full verification, and docs update

**Files:**
- Create: `backend/tests/integration/test_telegram_delivery_scope_e2e.py`
- Modify: `docs/reports/telegram-gateway-monitoring-2026-03-07.md`
- Modify: `docs/plans/2026-03-07-session-report-emoji-removal.md`
- Reference: `docs/plans/2026-03-07-telegram-report-integrity-remediation.md`

**Step 1: Add an end-to-end integration test for the full delivery chain**

Create `backend/tests/integration/test_telegram_delivery_scope_e2e.py` with a test that exercises the real `PlanActFlow` -> `FileSyncManager` -> `ExecutionAgent` -> `ResponseGenerator` chain with mocked sandbox and LLM:

```python
@pytest.mark.asyncio
async def test_reused_telegram_session_excludes_stale_artifacts_from_delivery():
    """Full chain: reused session -> scope init -> scoped sweep -> gate -> report emission.

    Verifies that a reused Telegram session with stale workspace files:
    1. Initializes a new delivery scope
    2. Scopes the file sweep to the active run
    3. Excludes stale files from the deliverables manifest
    4. Runs the delivery-integrity gate on the summary
    5. Falls back to the pre-trim draft when the summary is weak
    6. Emits a ReportEvent with only current-scope attachments
    """
    ...
```

This test should:
- Pre-populate the mock sandbox workspace with a stale file from a previous scope
- Execute the flow with `delivery_scope_isolation` enabled
- Assert the final `ReportEvent.attachments` contains zero stale files
- Assert the delivered content passed the integrity gate (or fell back to the draft)

**Step 2: Correct the monitoring report issue count**

Update the report summary so the top-level issue count matches the enumerated sections.

**Step 3: Mark the emoji-removal plan as a secondary follow-up**

At the top of `docs/plans/2026-03-07-session-report-emoji-removal.md`, add a short note that:
- the plan remains valid for presentation cleanup
- the primary Telegram remediation plan is `2026-03-07-telegram-report-integrity-remediation.md`

**Step 4: Run backend verification**

Run:

```bash
conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/
```

Expected: PASS

**Step 5: Commit**

```bash
git add \
  backend/tests/integration/test_telegram_delivery_scope_e2e.py \
  docs/reports/telegram-gateway-monitoring-2026-03-07.md \
  docs/plans/2026-03-07-session-report-emoji-removal.md \
  docs/plans/2026-03-07-telegram-report-integrity-remediation.md
git commit -m "docs: align telegram monitoring findings with remediation plan"
```

## Notes for the Implementer

- Preserve Telegram completed-session continuity. The fix is scoped deliverable isolation, not session-identity churn.
- Prefer metadata-based filtering over basename heuristics whenever possible.
- Do not broaden integrity blocking for short non-report assistant responses.
- Treat the emoji cleanup as a follow-up after correctness and evidence integrity are enforced.
- If active-scope metadata cannot be threaded everywhere cleanly, use the active workspace-root prefix as the temporary fallback, but keep the metadata hooks in place for durability.
- The `agent_task_runner.py` is the orchestrator that owns `FileSyncManager` and constructs `PlanActFlow`. Any scope state initialized inside `PlanActFlow.run()` must be propagated back to `FileSyncManager` through the runner before the sweep runs. Do not assume these objects share state implicitly.
- All scope-dependent behavior must degrade gracefully when `feature_delivery_scope_isolation` is disabled. The filter function returns all files unchanged, the workspace path falls back to the flat session root, and no scope directories are created or pruned.
- Reuse `run_delivery_integrity_gate()` for all grounding checks, including the pre-trim fallback. Do not introduce a separate `_report_has_grounding()` helper — keep verification unified through one path.
- Delivery-channel strictness applies only to Telegram (final-only) channels. Web UI users see streaming output and can evaluate incrementally, so the same issues should remain warnings, not blocks.

## Documentation Validation

- Internal code-path validation completed for the plan against:
  - `backend/app/domain/services/flows/plan_act.py`
  - `backend/app/domain/services/file_sync_manager.py`
  - `backend/app/domain/services/agent_task_runner.py`
  - `backend/app/domain/services/agents/execution.py`
  - `backend/app/domain/services/agents/response_generator.py`
  - `backend/app/domain/services/channels/message_router.py`
  - `backend/app/domain/services/channels/telegram_delivery_policy.py`
  - `backend/app/core/config_features.py`
  - `backend/app/core/prometheus_metrics.py`
