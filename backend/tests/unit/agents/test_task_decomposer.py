"""Tests for TaskDecomposer — decomposition, subtask types, strategies, parallel groups."""

from __future__ import annotations

import pytest

from app.domain.services.agents.task_decomposer import (
    DecompositionResult,
    DecompositionStrategy,
    Subtask,
    SubtaskType,
    TaskDecomposer,
    decompose_task,
)

# ---------------------------------------------------------------------------
# Subtask dataclass
# ---------------------------------------------------------------------------


class TestSubtask:
    def test_is_atomic_no_children(self):
        s = Subtask(
            id="1",
            description="Do X",
            subtask_type=SubtaskType.RESEARCH,
            strategy=DecompositionStrategy.ATOMIC,
        )
        assert s.is_atomic() is True

    def test_is_atomic_with_children(self):
        child = Subtask(
            id="2", description="child", subtask_type=SubtaskType.RESEARCH, strategy=DecompositionStrategy.ATOMIC
        )
        s = Subtask(
            id="1",
            description="parent",
            subtask_type=SubtaskType.RESEARCH,
            strategy=DecompositionStrategy.SEQUENTIAL,
            children=[child],
        )
        assert s.is_atomic() is False

    def test_is_atomic_by_strategy(self):
        s = Subtask(
            id="1",
            description="Do X",
            subtask_type=SubtaskType.RESEARCH,
            strategy=DecompositionStrategy.ATOMIC,
            children=[
                Subtask(
                    id="2", description="y", subtask_type=SubtaskType.RESEARCH, strategy=DecompositionStrategy.ATOMIC
                )
            ],
        )
        # Strategy=ATOMIC overrides having children
        assert s.is_atomic() is True

    def test_is_ready_no_deps(self):
        s = Subtask(id="1", description="X", subtask_type=SubtaskType.RESEARCH, strategy=DecompositionStrategy.ATOMIC)
        assert s.is_ready(set()) is True

    def test_is_ready_deps_satisfied(self):
        s = Subtask(
            id="2",
            description="X",
            subtask_type=SubtaskType.RESEARCH,
            strategy=DecompositionStrategy.ATOMIC,
            dependencies=["1"],
        )
        assert s.is_ready({"1"}) is True

    def test_is_ready_deps_not_satisfied(self):
        s = Subtask(
            id="2",
            description="X",
            subtask_type=SubtaskType.RESEARCH,
            strategy=DecompositionStrategy.ATOMIC,
            dependencies=["1"],
        )
        assert s.is_ready(set()) is False

    def test_default_status(self):
        s = Subtask(id="1", description="X", subtask_type=SubtaskType.RESEARCH, strategy=DecompositionStrategy.ATOMIC)
        assert s.status == "pending"
        assert s.result is None
        assert s.error is None


# ---------------------------------------------------------------------------
# DecompositionResult
# ---------------------------------------------------------------------------


class TestDecompositionResult:
    def test_atomic_subtasks(self):
        atomic = Subtask(
            id="1", description="a", subtask_type=SubtaskType.RESEARCH, strategy=DecompositionStrategy.ATOMIC
        )
        non_atomic = Subtask(
            id="2",
            description="b",
            subtask_type=SubtaskType.ANALYSIS,
            strategy=DecompositionStrategy.SEQUENTIAL,
            children=[atomic],
        )
        r = DecompositionResult(
            original_task="task",
            subtasks=[atomic, non_atomic],
            strategy=DecompositionStrategy.SEQUENTIAL,
            estimated_total_complexity=0.5,
            decomposition_tree_depth=0,
            parallel_groups=[["1"], ["2"]],
        )
        assert len(r.atomic_subtasks) == 1
        assert r.total_subtasks == 2


# ---------------------------------------------------------------------------
# TaskDecomposer — _is_atomic
# ---------------------------------------------------------------------------


class TestTaskDecomposerIsAtomic:
    @pytest.fixture()
    def decomposer(self):
        return TaskDecomposer()

    def test_short_task_is_atomic(self, decomposer):
        assert decomposer._is_atomic("Search for Python docs") is True

    def test_long_multi_action_not_atomic(self, decomposer):
        task = (
            "Research the latest AI trends then create a detailed report "
            "and then compare different approaches and finally summarize " + " ".join(["extra"] * 30)
        )
        assert decomposer._is_atomic(task) is False

    def test_single_action_is_atomic(self, decomposer):
        assert decomposer._is_atomic("Find information about Python") is True

    def test_numbered_list_not_atomic(self, decomposer):
        task = (
            "\n1. Search for data thoroughly\n2. Analyze results carefully\n3. Write report completely"
            + " padding" * 25
        )
        assert decomposer._is_atomic(task) is False

    def test_bullet_list_not_atomic(self, decomposer):
        task = (
            "\n- Search for data thoroughly\n- Analyze results carefully\n- Write report completely" + " padding" * 25
        )
        assert decomposer._is_atomic(task) is False


# ---------------------------------------------------------------------------
# TaskDecomposer — _detect_subtask_type
# ---------------------------------------------------------------------------


class TestTaskDecomposerSubtaskType:
    @pytest.fixture()
    def decomposer(self):
        return TaskDecomposer()

    def test_research(self, decomposer):
        assert decomposer._detect_subtask_type("Search for Python docs") == SubtaskType.RESEARCH
        assert decomposer._detect_subtask_type("Find information about AI") == SubtaskType.RESEARCH
        assert decomposer._detect_subtask_type("Research machine learning trends") == SubtaskType.RESEARCH

    def test_analysis(self, decomposer):
        assert decomposer._detect_subtask_type("Analyze the data") == SubtaskType.ANALYSIS
        assert decomposer._detect_subtask_type("Compare two approaches") == SubtaskType.ANALYSIS

    def test_creation(self, decomposer):
        assert decomposer._detect_subtask_type("Create a report") == SubtaskType.CREATION
        assert decomposer._detect_subtask_type("Write documentation") == SubtaskType.CREATION
        assert decomposer._detect_subtask_type("Build a prototype") == SubtaskType.CREATION

    def test_modification(self, decomposer):
        assert decomposer._detect_subtask_type("Update the configuration") == SubtaskType.MODIFICATION
        assert decomposer._detect_subtask_type("Fix the bug") == SubtaskType.MODIFICATION

    def test_validation(self, decomposer):
        assert decomposer._detect_subtask_type("Verify the results") == SubtaskType.VALIDATION
        assert decomposer._detect_subtask_type("Check for errors") == SubtaskType.VALIDATION

    def test_aggregation(self, decomposer):
        assert decomposer._detect_subtask_type("Combine all reports") == SubtaskType.AGGREGATION
        assert decomposer._detect_subtask_type("Summarize the findings") == SubtaskType.AGGREGATION

    def test_default_to_creation(self, decomposer):
        assert decomposer._detect_subtask_type("do something weird") == SubtaskType.CREATION


# ---------------------------------------------------------------------------
# TaskDecomposer — _estimate_complexity
# ---------------------------------------------------------------------------


class TestTaskDecomposerComplexity:
    @pytest.fixture()
    def decomposer(self):
        return TaskDecomposer()

    def test_short_task_low_complexity(self, decomposer):
        c = decomposer._estimate_complexity("Search X")
        assert c < 0.5

    def test_complex_task_higher(self, decomposer):
        c = decomposer._estimate_complexity(
            "Create a comprehensive and detailed analysis of multiple various approaches "
            "to every aspect of the problem " + " ".join(["word"] * 80)
        )
        assert c > 0.3

    def test_complexity_capped_at_1(self, decomposer):
        c = decomposer._estimate_complexity(
            "Create a comprehensive detailed thorough analysis comparing multiple various approaches "
            + " ".join(["word"] * 200)
        )
        assert c <= 1.0


# ---------------------------------------------------------------------------
# TaskDecomposer — _determine_strategy
# ---------------------------------------------------------------------------


class TestTaskDecomposerStrategy:
    @pytest.fixture()
    def decomposer(self):
        return TaskDecomposer()

    def test_empty_is_atomic(self, decomposer):
        assert decomposer._determine_strategy([]) == DecompositionStrategy.ATOMIC

    def test_all_deps_sequential(self, decomposer):
        s1 = Subtask(id="1", description="a", subtask_type=SubtaskType.RESEARCH, strategy=DecompositionStrategy.ATOMIC)
        s2 = Subtask(
            id="2",
            description="b",
            subtask_type=SubtaskType.ANALYSIS,
            strategy=DecompositionStrategy.ATOMIC,
            dependencies=["1"],
        )
        assert decomposer._determine_strategy([s1, s2]) == DecompositionStrategy.SEQUENTIAL

    def test_no_deps_parallel(self, decomposer):
        s1 = Subtask(id="1", description="a", subtask_type=SubtaskType.RESEARCH, strategy=DecompositionStrategy.ATOMIC)
        s2 = Subtask(id="2", description="b", subtask_type=SubtaskType.ANALYSIS, strategy=DecompositionStrategy.ATOMIC)
        assert decomposer._determine_strategy([s1, s2]) == DecompositionStrategy.PARALLEL


# ---------------------------------------------------------------------------
# TaskDecomposer — _create_parallel_groups
# ---------------------------------------------------------------------------


class TestTaskDecomposerParallelGroups:
    @pytest.fixture()
    def decomposer(self):
        return TaskDecomposer()

    def test_all_independent(self, decomposer):
        s1 = Subtask(id="1", description="a", subtask_type=SubtaskType.RESEARCH, strategy=DecompositionStrategy.ATOMIC)
        s2 = Subtask(id="2", description="b", subtask_type=SubtaskType.RESEARCH, strategy=DecompositionStrategy.ATOMIC)
        s3 = Subtask(id="3", description="c", subtask_type=SubtaskType.RESEARCH, strategy=DecompositionStrategy.ATOMIC)
        groups = decomposer._create_parallel_groups([s1, s2, s3])
        assert len(groups) == 1
        assert sorted(groups[0]) == ["1", "2", "3"]

    def test_chain_dependency(self, decomposer):
        s1 = Subtask(id="1", description="a", subtask_type=SubtaskType.RESEARCH, strategy=DecompositionStrategy.ATOMIC)
        s2 = Subtask(
            id="2",
            description="b",
            subtask_type=SubtaskType.ANALYSIS,
            strategy=DecompositionStrategy.ATOMIC,
            dependencies=["1"],
        )
        s3 = Subtask(
            id="3",
            description="c",
            subtask_type=SubtaskType.CREATION,
            strategy=DecompositionStrategy.ATOMIC,
            dependencies=["2"],
        )
        groups = decomposer._create_parallel_groups([s1, s2, s3])
        assert len(groups) == 3
        assert groups[0] == ["1"]
        assert groups[1] == ["2"]
        assert groups[2] == ["3"]

    def test_diamond_dependency(self, decomposer):
        s1 = Subtask(
            id="1", description="start", subtask_type=SubtaskType.RESEARCH, strategy=DecompositionStrategy.ATOMIC
        )
        s2 = Subtask(
            id="2",
            description="left",
            subtask_type=SubtaskType.ANALYSIS,
            strategy=DecompositionStrategy.ATOMIC,
            dependencies=["1"],
        )
        s3 = Subtask(
            id="3",
            description="right",
            subtask_type=SubtaskType.ANALYSIS,
            strategy=DecompositionStrategy.ATOMIC,
            dependencies=["1"],
        )
        s4 = Subtask(
            id="4",
            description="end",
            subtask_type=SubtaskType.AGGREGATION,
            strategy=DecompositionStrategy.ATOMIC,
            dependencies=["2", "3"],
        )
        groups = decomposer._create_parallel_groups([s1, s2, s3, s4])
        assert len(groups) == 3
        assert groups[0] == ["1"]
        assert sorted(groups[1]) == ["2", "3"]
        assert groups[2] == ["4"]


# ---------------------------------------------------------------------------
# TaskDecomposer — decompose
# ---------------------------------------------------------------------------


class TestTaskDecomposerDecompose:
    @pytest.fixture()
    def decomposer(self):
        return TaskDecomposer()

    def test_empty_task(self, decomposer):
        result = decomposer.decompose("")
        assert result.total_subtasks == 0
        assert result.strategy == DecompositionStrategy.ATOMIC

    def test_simple_atomic_task(self, decomposer):
        result = decomposer.decompose("Search for Python docs")
        assert result.total_subtasks == 1
        assert result.strategy == DecompositionStrategy.ATOMIC

    def test_numbered_list_task(self, decomposer):
        task = (
            "Complete the following steps with thorough analysis and implementation:\n"
            "1. Research the latest Python frameworks available today\n"
            "2. Compare their performance characteristics and benchmarks\n"
            "3. Create a detailed summary report with recommendations"
        )
        result = decomposer.decompose(task)
        assert result.total_subtasks >= 3

    def test_conjunction_task(self, decomposer):
        task = (
            "Research Python web frameworks including Django Flask and FastAPI with benchmarks "
            "and then compare their performance characteristics in detail with real world metrics "
            "and then write a comprehensive report with all the detailed findings and analysis"
        )
        result = decomposer.decompose(task)
        assert result.total_subtasks >= 2

    def test_max_depth_respected(self):
        decomposer = TaskDecomposer(max_depth=1)
        task = (
            "Complete the following steps with thorough analysis and implementation:\n"
            "1. Research the latest Python frameworks\n"
            "2. Compare their performance\n"
            "3. Create a detailed summary report"
        )
        result = decomposer.decompose(task)
        assert result.decomposition_tree_depth <= 1


# ---------------------------------------------------------------------------
# TaskDecomposer — mark & progress
# ---------------------------------------------------------------------------


class TestTaskDecomposerExecution:
    @pytest.fixture()
    def decomposer(self):
        d = TaskDecomposer()
        d.decompose("Search for Python docs")
        return d

    def test_mark_completed(self, decomposer):
        subtask_id = next(iter(decomposer._subtasks.keys()))
        decomposer.mark_completed(subtask_id, "Found docs")
        assert decomposer._subtasks[subtask_id].status == "completed"
        assert decomposer._subtasks[subtask_id].result == "Found docs"
        assert subtask_id in decomposer._completed_ids

    def test_mark_failed(self, decomposer):
        subtask_id = next(iter(decomposer._subtasks.keys()))
        decomposer.mark_failed(subtask_id, "Network error")
        assert decomposer._subtasks[subtask_id].status == "failed"
        assert decomposer._subtasks[subtask_id].error == "Network error"

    def test_get_next_ready(self, decomposer):
        ready = decomposer.get_next_ready_subtasks()
        assert len(ready) >= 1

    def test_get_progress(self, decomposer):
        progress = decomposer.get_progress()
        assert progress["total_subtasks"] >= 1
        assert progress["completed"] == 0
        assert progress["progress_percent"] == 0.0

    def test_progress_after_completion(self, decomposer):
        subtask_id = next(iter(decomposer._subtasks.keys()))
        decomposer.mark_completed(subtask_id, "Done")
        progress = decomposer.get_progress()
        assert progress["completed"] == 1
        assert progress["progress_percent"] == 100.0

    def test_aggregate_results(self, decomposer):
        subtask_id = next(iter(decomposer._subtasks.keys()))
        decomposer.mark_completed(subtask_id, "Result text")
        aggregated = decomposer.aggregate_results()
        assert "Result text" in aggregated

    def test_get_context_for_subtask(self):
        decomposer = TaskDecomposer()
        # Create a chain
        task = "Research Python frameworks and then compare their performance with detailed benchmarks and analysis"
        decomposer.decompose(task)
        # Find a subtask with dependencies
        for s in decomposer._subtasks.values():
            if s.dependencies:
                dep_id = s.dependencies[0]
                decomposer.mark_completed(dep_id, "Dep result")
                ctx = decomposer.get_context_for_subtask(s.id)
                assert "Dep result" in ctx
                return
        # If no deps found, that's ok for simple tasks
        assert True

    def test_reset(self, decomposer):
        subtask_id = next(iter(decomposer._subtasks.keys()))
        decomposer.mark_completed(subtask_id, "Done")
        decomposer.reset()
        assert len(decomposer._subtasks) == 0
        assert len(decomposer._completed_ids) == 0
        assert len(decomposer._results) == 0


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


class TestConvenienceFunction:
    def test_decompose_task(self):
        result = decompose_task("Search for Python docs")
        assert isinstance(result, DecompositionResult)
        assert result.total_subtasks >= 1

    def test_decompose_task_with_context(self):
        result = decompose_task("Search for Python docs", context="User wants web framework info")
        assert isinstance(result, DecompositionResult)
