# Bubbly Shimmying Parasol Review

This note corrects the current plan against the live Pythinker codebase and the Claude Code reference implementation.

## What The Plan Gets Wrong

- `SecurityAssessmentMiddleware` does not allow everything. The allow-all behavior is in `SecurityAssessor.assess_action()`, while the middleware is already wired into both the default agent pipeline and the session-scoped context factory.
- `ToolName` is already a live classification layer, not just static enums. It already exposes `is_read_only`, `is_action`, `is_safe_parallel`, `is_safe_mcp_tool`, and phase gating.
- `ToolResultStore` is already integrated into `BaseAgent._serialize_tool_result_for_memory()`. The plan incorrectly treats it as not yet wired.
- The middleware pipeline is not only a `plan_act.py` concern. It is also constructed in `BaseAgent` and `AgentContextFactory`.

## Missing Claude Code Patterns

- `buildTool` in Claude supplies more than read-only / concurrency metadata. It also defaults `isEnabled`, `checkPermissions`, `toAutoClassifierInput`, and `userFacingName`.
- Claude’s tool result sizing has two layers:
  - per-tool `maxResultSizeChars`
  - per-message aggregate result budgets
- Claude’s deferred tool search includes cache invalidation when the deferred tool set changes.
- Claude’s agent/tool orchestration includes explicit lifecycle tools such as `Agent`, `Task`, `SendMessage`, `TaskStop`, and `TaskOutput`, plus coordinator-mode allowlists.

## Risks And Ordering Issues

- Do not remove the current parallelism constants before a `ToolMetadataIndex` or equivalent exists.
- Register any permission middleware in both `BaseAgent._build_default_pipeline()` and `AgentContextFactory.create()`, not only in `plan_act.py`.
- Extend the existing `ToolResultStore` flow before introducing a second persistence/retrieval mechanism.
- Stage shell work as:
  1. command classification
  2. timeout tiers
  3. background execution

## Reuse Guidance

- Keep `ToolDefaults` and `build_tool()` as the source of truth for tool-method defaults.
- Keep `ToolName` as the fallback classifier and migration cross-check.
- Keep the existing middleware pipeline and add one adapter, rather than building a parallel policy path.
- Extend `ToolResultStore` and `BaseAgent._serialize_tool_result_for_memory()` before adding any new retrieval tool.

## Recommended Plan Adjustments

1. Expand tool metadata work to include Claude’s missing defaults:
   - `isEnabled`
   - `checkPermissions`
   - `toAutoClassifierInput`
   - `userFacingName`
2. Make parallel execution metadata-driven only after a metadata index exists and `ToolName` fallback behavior is preserved.
3. Reframe permission work as a middleware adapter registered in both pipeline construction paths.
4. Extend current result storage before designing any new retrieval surface.
5. Add deferred tool search behavior, including cache invalidation and direct selection.
6. Keep shell classification and timeout tiers separate from background process support.

