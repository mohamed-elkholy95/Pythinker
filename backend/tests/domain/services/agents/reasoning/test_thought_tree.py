"""Tests for thought_tree module: ThoughtNode, ThoughtPath, ValueFunction, PruningStrategy."""

from __future__ import annotations

import pytest

from app.domain.models.thought import ThoughtType
from app.domain.services.agents.reasoning.thought_tree import (
    ExplorationMode,
    ExplorationResult,
    NodeState,
    PruningStrategy,
    ThoughtNode,
    ThoughtPath,
    ValueFunction,
)

# ── NodeState enum ──────────────────────────────────────────────────────────


class TestNodeState:
    def test_all_members_exist(self) -> None:
        names = {m.value for m in NodeState}
        assert names == {"unexplored", "exploring", "evaluated", "pruned", "selected", "dead_end"}

    def test_string_comparison(self) -> None:
        assert NodeState.UNEXPLORED == "unexplored"
        assert NodeState.PRUNED == "pruned"


# ── ExplorationMode enum ───────────────────────────────────────────────────


class TestExplorationMode:
    def test_all_members_exist(self) -> None:
        names = {m.value for m in ExplorationMode}
        assert names == {"full", "shallow", "linear", "beam"}


# ── ThoughtNode ─────────────────────────────────────────────────────────────


class TestThoughtNode:
    def _make_node(self, **kwargs) -> ThoughtNode:
        defaults = {
            "id": "node-1",
            "content": "Test thought",
            "thought_type": ThoughtType.OBSERVATION,
        }
        defaults.update(kwargs)
        return ThoughtNode(**defaults)

    def test_default_values(self) -> None:
        node = self._make_node()
        assert node.state == NodeState.UNEXPLORED
        assert node.value == 0.0
        assert node.confidence == 0.5
        assert node.depth == 0
        assert node.is_terminal is False
        assert node.children == []
        assert node.parent_id is None

    def test_is_leaf_with_no_children(self) -> None:
        node = self._make_node()
        assert node.is_leaf() is True

    def test_is_leaf_with_children(self) -> None:
        parent = self._make_node(id="parent")
        child = self._make_node(id="child")
        parent.add_child(child)
        assert parent.is_leaf() is False

    def test_add_child_sets_parent_and_depth(self) -> None:
        parent = self._make_node(id="parent", depth=2)
        child = self._make_node(id="child")
        parent.add_child(child)
        assert child.parent_id == "parent"
        assert child.depth == 3
        assert child in parent.children

    def test_add_multiple_children(self) -> None:
        parent = self._make_node(id="root")
        for i in range(3):
            parent.add_child(self._make_node(id=f"child-{i}"))
        assert len(parent.children) == 3
        assert all(c.depth == 1 for c in parent.children)

    def test_is_promising_above_threshold(self) -> None:
        node = self._make_node(value=0.5)
        assert node.is_promising(threshold=0.4) is True

    def test_is_promising_below_threshold(self) -> None:
        node = self._make_node(value=0.2)
        assert node.is_promising(threshold=0.4) is False

    def test_is_promising_pruned_node_always_false(self) -> None:
        node = self._make_node(value=0.9, state=NodeState.PRUNED)
        assert node.is_promising(threshold=0.1) is False

    def test_is_promising_at_exact_threshold(self) -> None:
        node = self._make_node(value=0.4)
        assert node.is_promising(threshold=0.4) is True

    def test_is_promising_default_threshold(self) -> None:
        node = self._make_node(value=0.5)
        assert node.is_promising() is True

    def test_metadata_is_mutable_dict(self) -> None:
        node = self._make_node()
        node.metadata["has_evidence"] = True
        assert node.metadata["has_evidence"] is True


# ── ThoughtPath ─────────────────────────────────────────────────────────────


class TestThoughtPath:
    def _make_node(self, value: float = 0.5, confidence: float = 0.7, **kwargs) -> ThoughtNode:
        defaults = {
            "id": "n",
            "content": "thought",
            "thought_type": ThoughtType.ANALYSIS,
            "value": value,
            "confidence": confidence,
        }
        defaults.update(kwargs)
        return ThoughtNode(**defaults)

    def test_empty_path(self) -> None:
        path = ThoughtPath(nodes=[])
        assert path.total_value == 0.0
        assert path.average_confidence == 0.0

    def test_single_node_path(self) -> None:
        node = self._make_node(value=0.8, confidence=0.9)
        path = ThoughtPath(nodes=[node])
        assert path.total_value == 0.8
        assert path.average_confidence == 0.9

    def test_multi_node_path_sums_values(self) -> None:
        nodes = [self._make_node(value=v) for v in [0.3, 0.5, 0.7]]
        path = ThoughtPath(nodes=nodes)
        assert path.total_value == pytest.approx(1.5)

    def test_multi_node_path_averages_confidence(self) -> None:
        nodes = [self._make_node(confidence=c) for c in [0.4, 0.6, 0.8]]
        path = ThoughtPath(nodes=nodes)
        assert path.average_confidence == pytest.approx(0.6)

    def test_get_conclusion_from_terminal_node(self) -> None:
        terminal = self._make_node(is_terminal=True)
        terminal.content = "Final answer"
        path = ThoughtPath(nodes=[self._make_node(), terminal])
        assert path.get_conclusion() == "Final answer"

    def test_get_conclusion_non_terminal_returns_none(self) -> None:
        path = ThoughtPath(nodes=[self._make_node()])
        assert path.get_conclusion() is None

    def test_get_conclusion_empty_path(self) -> None:
        path = ThoughtPath(nodes=[])
        assert path.get_conclusion() is None


# ── ValueFunction ───────────────────────────────────────────────────────────


class TestValueFunction:
    def test_evaluate_returns_between_zero_and_one(self) -> None:
        vf = ValueFunction()
        node = ThoughtNode(id="n", content="test", thought_type=ThoughtType.OBSERVATION, confidence=0.5)
        val = vf.evaluate(node)
        assert 0.0 <= val <= 1.0

    def test_decision_node_higher_than_observation(self) -> None:
        vf = ValueFunction()
        obs = ThoughtNode(id="o", content="obs", thought_type=ThoughtType.OBSERVATION, confidence=0.5)
        dec = ThoughtNode(id="d", content="dec", thought_type=ThoughtType.DECISION, confidence=0.5)
        assert vf.evaluate(dec) > vf.evaluate(obs)

    def test_evidence_bonus(self) -> None:
        vf = ValueFunction()
        without = ThoughtNode(id="a", content="a", thought_type=ThoughtType.ANALYSIS, confidence=0.5)
        with_ev = ThoughtNode(
            id="b", content="b", thought_type=ThoughtType.ANALYSIS, confidence=0.5, metadata={"has_evidence": True}
        )
        assert vf.evaluate(with_ev) > vf.evaluate(without)

    def test_depth_penalty_reduces_value(self) -> None:
        vf = ValueFunction()
        shallow = ThoughtNode(id="s", content="s", thought_type=ThoughtType.ANALYSIS, confidence=0.5, depth=0)
        deep = ThoughtNode(id="d", content="d", thought_type=ThoughtType.ANALYSIS, confidence=0.5, depth=5)
        assert vf.evaluate(shallow) > vf.evaluate(deep)

    def test_high_confidence_increases_value(self) -> None:
        vf = ValueFunction()
        low_conf = ThoughtNode(id="l", content="l", thought_type=ThoughtType.ANALYSIS, confidence=0.2)
        high_conf = ThoughtNode(id="h", content="h", thought_type=ThoughtType.ANALYSIS, confidence=0.9)
        assert vf.evaluate(high_conf) > vf.evaluate(low_conf)

    def test_progress_scores_mapping(self) -> None:
        vf = ValueFunction()
        scores = {
            ThoughtType.OBSERVATION: 0.3,
            ThoughtType.ANALYSIS: 0.4,
            ThoughtType.HYPOTHESIS: 0.5,
            ThoughtType.DECISION: 0.9,
        }
        for tt, expected in scores.items():
            assert vf._calculate_progress_signal(ThoughtNode(id="x", content="x", thought_type=tt)) == expected

    def test_novelty_decision_highest(self) -> None:
        vf = ValueFunction()
        decision_novelty = vf._calculate_novelty(ThoughtNode(id="x", content="x", thought_type=ThoughtType.DECISION))
        eval_novelty = vf._calculate_novelty(ThoughtNode(id="y", content="y", thought_type=ThoughtType.EVALUATION))
        assert decision_novelty > eval_novelty


# ── PruningStrategy ─────────────────────────────────────────────────────────


class TestPruningStrategy:
    def _make_node(self, **kwargs) -> ThoughtNode:
        defaults = {
            "id": "n",
            "content": "thought",
            "thought_type": ThoughtType.ANALYSIS,
            "value": 0.5,
            "confidence": 0.5,
        }
        defaults.update(kwargs)
        return ThoughtNode(**defaults)

    def test_should_prune_low_value(self) -> None:
        ps = PruningStrategy(value_threshold=0.3)
        node = self._make_node(value=0.1)
        assert ps.should_prune(node) is True

    def test_should_not_prune_above_threshold(self) -> None:
        ps = PruningStrategy(value_threshold=0.3)
        node = self._make_node(value=0.5)
        assert ps.should_prune(node) is False

    def test_should_prune_very_low_confidence(self) -> None:
        ps = PruningStrategy()
        node = self._make_node(value=0.5, confidence=0.1)
        assert ps.should_prune(node) is True

    def test_should_prune_deep_uncertainty_node(self) -> None:
        ps = PruningStrategy()
        node = self._make_node(
            thought_type=ThoughtType.UNCERTAINTY,
            depth=4,
            value=0.5,
            confidence=0.5,
        )
        assert ps.should_prune(node) is True

    def test_should_not_prune_shallow_uncertainty(self) -> None:
        ps = PruningStrategy()
        node = self._make_node(
            thought_type=ThoughtType.UNCERTAINTY,
            depth=2,
            value=0.5,
            confidence=0.5,
        )
        assert ps.should_prune(node) is False

    def test_select_children_top_k(self) -> None:
        ps = PruningStrategy(max_children=2)
        children = [self._make_node(id=f"c{i}", value=v) for i, v in enumerate([0.3, 0.9, 0.6, 0.1])]
        selected = ps.select_children_to_explore(children)
        assert len(selected) == 2
        assert selected[0].value == 0.9
        assert selected[1].value == 0.6

    def test_select_children_empty_list(self) -> None:
        ps = PruningStrategy()
        assert ps.select_children_to_explore([]) == []

    def test_select_beam_paths_top_k(self) -> None:
        ps = PruningStrategy(beam_width=2)
        paths = [ThoughtPath(nodes=[self._make_node(value=v)]) for v in [0.2, 0.8, 0.5]]
        selected = ps.select_beam_paths(paths)
        assert len(selected) == 2
        assert selected[0].total_value == 0.8

    def test_select_beam_paths_empty(self) -> None:
        ps = PruningStrategy()
        assert ps.select_beam_paths([]) == []


# ── ExplorationResult ───────────────────────────────────────────────────────


class TestExplorationResult:
    def test_construction(self) -> None:
        result = ExplorationResult(
            best_path=None,
            all_paths=[],
            nodes_explored=10,
            nodes_pruned=3,
            max_depth_reached=4,
            exploration_mode=ExplorationMode.BEAM,
        )
        assert result.nodes_explored == 10
        assert result.nodes_pruned == 3
        assert result.exploration_mode == ExplorationMode.BEAM
        assert result.best_path is None
