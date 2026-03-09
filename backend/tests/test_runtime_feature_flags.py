"""Regression tests for runtime feature flag exposure."""

from __future__ import annotations

from types import SimpleNamespace

from app.core.config import get_feature_flags


def test_runtime_feature_flags_are_exposed(monkeypatch) -> None:
    """New runtime flags must be present in get_feature_flags()."""
    fake_settings = SimpleNamespace(
        feature_tree_of_thoughts=False,
        feature_self_consistency=False,
        feature_plan_validation_v2=False,
        feature_reflection_advanced=False,
        feature_context_optimization=False,
        feature_tool_tracing=False,
        feature_reward_hacking_detection=False,
        feature_failure_prediction=False,
        feature_circuit_breaker_adaptive=False,
        feature_workflow_checkpointing=False,
        feature_hitl_enabled=False,
        feature_taskgroup_enabled=False,
        feature_sse_v2=False,
        feature_structured_outputs=False,
        feature_parallel_memory=False,
        feature_enhanced_research=False,
        feature_phased_research=False,
        feature_shadow_mode=True,
        feature_url_verification=True,
        feature_claim_provenance=True,
        feature_enhanced_grounding=True,
        feature_cove_verification=False,
        feature_lettuce_verification=True,
        feature_semantic_citation_validation=True,
        feature_strict_numeric_verification=True,
        feature_reject_ungrounded_reports=False,
        feature_delivery_integrity_gate=True,
        feature_delivery_scope_isolation=False,
        feature_adaptive_verbosity_shadow=False,
        feature_pre_planning_search=False,
        confirmation_summary_enabled=False,
        feature_url_failure_guard_enabled=True,
        feature_tool_result_store_enabled=True,
        feature_graduated_compaction_enabled=True,
        feature_scratchpad_enabled=False,
        feature_structured_compaction_enabled=False,
        feature_live_shell_streaming=False,
        live_shell_poll_interval_ms=500,
        live_shell_max_polls=600,
        feature_token_budget_manager=False,
        feature_live_file_streaming=False,
        feature_lead_agent_runtime=True,
        feature_runtime_workspace_contracts=True,
        feature_runtime_clarification_gate=True,
        feature_runtime_dangling_recovery=True,
        feature_runtime_quality_gates=True,
        feature_runtime_insight_promotion=True,
        feature_runtime_capability_manifest=True,
        feature_runtime_skill_discovery=True,
        feature_runtime_research_trace=True,
        feature_runtime_delegate_tool=True,
        feature_runtime_channel_overlay=True,
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: fake_settings)

    flags = get_feature_flags()

    assert flags["feature_lead_agent_runtime"] is True
    assert flags["feature_runtime_quality_gates"] is True
    assert flags["feature_runtime_channel_overlay"] is True
