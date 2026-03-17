"""Tests for the dataset builder: curated loading, session extraction, splits."""

from __future__ import annotations

from app.domain.models.prompt_optimization import CaseSplit
from app.domain.models.prompt_profile import PromptTarget
from app.domain.services.prompt_optimization.dataset_builder import (
    DatasetBuilder,
    _case_split,
    extract_cases_from_session_events,
    load_curated_cases,
)


class TestCaseSplit:
    """Deterministic split assignment."""

    def test_determinism(self) -> None:
        """Same inputs always produce the same split."""
        s1 = _case_split("case_001", "planner", "medium")
        s2 = _case_split("case_001", "planner", "medium")
        assert s1 == s2

    def test_different_ids_may_differ(self) -> None:
        """Different case IDs can land in different splits."""
        splits = {_case_split(f"case_{i:03d}", "planner", "medium") for i in range(20)}
        # With 20 different IDs, we should see at least 2 distinct splits
        assert len(splits) >= 2

    def test_all_splits_possible(self) -> None:
        """Over many IDs, all three splits should be represented."""
        splits = {_case_split(f"test_{i}", "execution", "easy") for i in range(200)}
        assert CaseSplit.TRAIN in splits
        assert CaseSplit.VAL in splits
        assert CaseSplit.TEST in splits


class TestLoadCuratedCases:
    """Load and verify the bundled curated dataset."""

    def test_loads_all_cases(self) -> None:
        """After Fix 5, we expect 22 total cases (15 exec + 12 planner - 5 original = 22)."""
        cases = load_curated_cases()
        assert len(cases) == 22, f"Expected 22 curated cases, got {len(cases)}"

    def test_planner_cases_count(self) -> None:
        """After Fix 5, there should be 12 planner cases."""
        cases = load_curated_cases()
        planner = [c for c in cases if c.target == PromptTarget.PLANNER]
        assert len(planner) == 12

    def test_planner_train_split_sufficient(self) -> None:
        """At least 5 planner cases land in TRAIN split (orchestrator requirement)."""
        cases = load_curated_cases()
        planner_train = [c for c in cases if c.target == PromptTarget.PLANNER and c.split == CaseSplit.TRAIN]
        assert len(planner_train) >= 5, f"Need ≥5 planner TRAIN cases, got {len(planner_train)}"

    def test_nonexistent_path_returns_empty(self, tmp_path) -> None:
        """Graceful handling of missing dataset file."""
        cases = load_curated_cases(tmp_path / "does_not_exist.json")
        assert cases == []


class TestExtractCasesFromSessionEvents:
    """Session event mining with Fix 4 (uses 'description' field)."""

    def test_extracts_planner_case_from_plan_event(self) -> None:
        events = [
            {"type": "message", "sender": "user", "content": "Build an API"},
            {
                "type": "plan",
                "status": "created",
                "session_id": "sess-1",
                "plan": {
                    "steps": [
                        {"description": "Set up project"},
                        {"description": "Implement endpoints"},
                    ]
                },
            },
        ]
        cases = extract_cases_from_session_events(events)
        planner_cases = [c for c in cases if c.target == PromptTarget.PLANNER]
        assert len(planner_cases) == 1
        assert planner_cases[0].input.user_request == "Build an API"
        assert planner_cases[0].expected.min_steps == 1
        assert planner_cases[0].expected.max_steps == 5

    def test_uses_description_field_for_step(self) -> None:
        """Fix 4: step extraction should use 'description', not 'name'."""
        events = [
            {"type": "message", "sender": "user", "content": "Fix the bug"},
            {
                "type": "step",
                "status": "started",
                "step": {"description": "Read and patch the file"},
            },
            {"type": "tool", "tool_name": "file_read"},
            {"type": "tool", "tool_name": "file_write"},
            {
                "type": "step",
                "status": "completed",
                "step": {"description": "Read and patch the file"},
            },
        ]
        cases = extract_cases_from_session_events(events)
        exec_cases = [c for c in cases if c.target == PromptTarget.EXECUTION]
        assert len(exec_cases) == 1
        assert exec_cases[0].input.step_description == "Read and patch the file"
        assert set(exec_cases[0].expected.must_call_tools) == {"file_read", "file_write"}

    def test_name_fallback_still_works(self) -> None:
        """Backward compat: 'name' field is used if 'description' is absent."""
        events = [
            {"type": "message", "sender": "user", "content": "Do work"},
            {
                "type": "step",
                "status": "started",
                "step": {"name": "legacy step name"},
            },
            {"type": "tool", "tool_name": "terminal_execute"},
            {
                "type": "step",
                "status": "completed",
                "step": {"name": "legacy step name"},
            },
        ]
        cases = extract_cases_from_session_events(events)
        exec_cases = [c for c in cases if c.target == PromptTarget.EXECUTION]
        assert len(exec_cases) == 1
        assert exec_cases[0].input.step_description == "legacy step name"

    def test_no_cases_without_user_message(self) -> None:
        """Without a preceding user message, no cases are created."""
        events = [
            {
                "type": "step",
                "status": "started",
                "step": {"description": "orphan step"},
            },
            {"type": "tool", "tool_name": "file_read"},
            {"type": "step", "status": "completed", "step": {}},
        ]
        cases = extract_cases_from_session_events(events)
        assert cases == []


class TestDatasetBuilder:
    """Integration: build + split pipeline."""

    def test_split_filters_by_target(self) -> None:
        builder = DatasetBuilder()
        cases = builder.build_from_curated()
        split_map = builder.split(cases, target=PromptTarget.PLANNER)
        for split_cases in split_map.values():
            for c in split_cases:
                assert c.target == PromptTarget.PLANNER
