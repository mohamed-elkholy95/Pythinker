# Agent Robustness Baseline Latency Reference

**Date:** 2026-02-13
**Plan:** 2026-02-13-agent-robustness-context7-delivery-and-step-naming-plan.md
**Phase 0 Task 0.3**

## Purpose

Baseline reference for PlanActFlow SUMMARIZING phase latency before and after guardrails.
Used to validate that additional guardrail latency stays within the acceptance criterion:
**Additional guardrail latency < 150ms P95 over baseline.**

## Instrumentation

- `workflow_phase_duration` histogram with `phase="summarizing"` records end-to-end summarization duration
- `guardrail_latency_seconds` with `phase="relevance"` records OutputGuardrails.analyze() duration (when enabled)

## Measurement Instructions

1. Run 20+ representative prompts through the flow (mix of research, browse, knowledge queries)
2. Query Prometheus for `pythinker_workflow_phase_duration_seconds_bucket{phase="summarizing"}`
3. Compute P50/P95/P99 from histogram buckets
4. Store results below when available

## Baseline Results (To Be Populated)

| Metric | P50 | P95 | P99 |
|--------|-----|-----|-----|
| summarization_total | - | - | - |
| guardrail_analyze (when enabled) | - | - | - |

## Notes

- Baseline should be captured with `enable_output_guardrails_in_flow=False`
- Post-baseline run with `enable_output_guardrails_in_flow=True` to measure guardrail overhead
