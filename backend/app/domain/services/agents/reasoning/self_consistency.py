"""
Self-Consistency Validation for reasoning.

This module implements self-consistency checking by generating
multiple reasoning paths and selecting the most consistent answer.
"""

import asyncio
import logging
from collections import Counter
from typing import Any

from app.domain.external.llm import LLM
from app.domain.models.thought import Decision, ThoughtChain
from app.domain.services.agents.reasoning.thought_chain import ThoughtChainBuilder

logger = logging.getLogger(__name__)


class ReasoningPath(ThoughtChain):
    """A single reasoning path with similarity tracking."""

    path_id: str = ""
    similarity_to_others: float = 0.0


class ConsensusResult:
    """Result of consensus analysis across multiple reasoning paths."""

    def __init__(
        self,
        paths: list[ReasoningPath],
        consensus_decision: Decision | None,
        agreement_score: float,
        dissenting_views: list[str],
    ) -> None:
        """Initialize consensus result.

        Args:
            paths: The reasoning paths analyzed
            consensus_decision: The consensus decision if reached
            agreement_score: Score indicating agreement level (0-1)
            dissenting_views: List of dissenting perspectives
        """
        self.paths = paths
        self.consensus_decision = consensus_decision
        self.agreement_score = agreement_score
        self.dissenting_views = dissenting_views

    @property
    def has_consensus(self) -> bool:
        """Check if consensus was reached."""
        return self.agreement_score >= 0.6 and self.consensus_decision is not None

    @property
    def is_strong_consensus(self) -> bool:
        """Check if there is strong consensus (>80% agreement)."""
        return self.agreement_score >= 0.8

    @property
    def needs_more_paths(self) -> bool:
        """Check if more paths are needed for confidence."""
        return len(self.paths) < 3 or (0.4 <= self.agreement_score < 0.6)

    def get_summary(self) -> str:
        """Get a summary of the consensus analysis."""
        lines = [
            f"Analyzed {len(self.paths)} reasoning paths",
            f"Agreement score: {self.agreement_score:.2f}",
        ]

        if self.has_consensus:
            lines.append(f"Consensus: {self.consensus_decision.action if self.consensus_decision else 'None'}")
        else:
            lines.append("No clear consensus reached")

        if self.dissenting_views:
            lines.append(f"Dissenting views: {len(self.dissenting_views)}")

        return "\n".join(lines)


class SelfConsistencyChecker:
    """Checker for self-consistency across multiple reasoning paths.

    Generates multiple independent reasoning paths for the same problem
    and analyzes them for consistency to improve decision confidence.
    """

    def __init__(
        self,
        llm: LLM,
        default_n_paths: int = 3,
        temperature_variance: float = 0.2,
    ) -> None:
        """Initialize the self-consistency checker.

        Args:
            llm: The LLM to use for generating paths
            default_n_paths: Default number of paths to generate
            temperature_variance: How much to vary temperature between paths
        """
        self.llm = llm
        self.default_n_paths = default_n_paths
        self.temperature_variance = temperature_variance
        self._chain_builder = ThoughtChainBuilder()

    async def generate_paths(
        self,
        problem: str,
        n_paths: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[ReasoningPath]:
        """Generate multiple independent reasoning paths for a problem.

        Uses temperature variation and prompt shuffling to generate
        diverse but valid reasoning approaches.

        Args:
            problem: The problem to reason about
            n_paths: Number of paths to generate (default: 3)
            context: Optional context information

        Returns:
            List of reasoning paths
        """
        n_paths = n_paths or self.default_n_paths
        n_paths = min(n_paths, 5)  # Cap at 5 paths for efficiency

        logger.info(f"Generating {n_paths} reasoning paths for consistency check")

        # Generate paths with slight variations
        tasks = []
        for i in range(n_paths):
            prompt_variant = self._create_prompt_variant(problem, i)
            tasks.append(self._generate_single_path(prompt_variant, context, i))

        # Run in parallel
        paths = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out failures
        valid_paths = []
        for i, path in enumerate(paths):
            if isinstance(path, Exception):
                logger.warning(f"Path {i} generation failed: {path}")
            else:
                valid_paths.append(path)

        if not valid_paths:
            logger.error("All reasoning paths failed to generate")
            return []

        # Calculate similarity scores
        self._calculate_similarities(valid_paths)

        return valid_paths

    async def aggregate_paths(
        self,
        paths: list[ReasoningPath],
    ) -> ConsensusResult:
        """Aggregate multiple reasoning paths into a consensus.

        Analyzes paths for common conclusions and builds consensus
        from majority agreement.

        Args:
            paths: List of reasoning paths

        Returns:
            Consensus result with agreement analysis
        """
        if not paths:
            return ConsensusResult(
                paths=[],
                consensus_decision=None,
                agreement_score=0.0,
                dissenting_views=[],
            )

        # Extract decisions from each path
        decisions = []
        for path in paths:
            decision = self._chain_builder.extract_decision(path)
            decisions.append(decision)

        # Analyze agreement
        agreement_score = self._calculate_agreement(decisions)

        # Find consensus decision
        consensus_decision = self._find_consensus_decision(decisions)

        # Identify dissenting views
        dissenting_views = self._find_dissenting_views(decisions, consensus_decision)

        # Adjust confidence based on agreement
        if consensus_decision:
            consensus_decision.confidence *= agreement_score

        result = ConsensusResult(
            paths=paths,
            consensus_decision=consensus_decision,
            agreement_score=agreement_score,
            dissenting_views=dissenting_views,
        )

        logger.info(
            f"Consensus analysis complete: agreement={agreement_score:.2f}, has_consensus={result.has_consensus}"
        )

        return result

    def calculate_agreement_score(self, paths: list[ReasoningPath]) -> float:
        """Calculate agreement score across paths.

        Args:
            paths: List of reasoning paths

        Returns:
            Agreement score (0-1)
        """
        if len(paths) < 2:
            return 1.0 if paths else 0.0

        decisions = [self._chain_builder.extract_decision(p) for p in paths]
        return self._calculate_agreement(decisions)

    async def check_consistency(
        self,
        problem: str,
        context: dict[str, Any] | None = None,
        min_agreement: float = 0.6,
    ) -> tuple[ConsensusResult, bool]:
        """Perform full consistency check on a problem.

        Generates paths and checks for consensus, returning
        whether the consistency threshold is met.

        Args:
            problem: The problem to check
            context: Optional context
            min_agreement: Minimum agreement threshold

        Returns:
            Tuple of (ConsensusResult, passed_check)
        """
        paths = await self.generate_paths(problem, context=context)
        result = await self.aggregate_paths(paths)

        passed = result.agreement_score >= min_agreement
        return result, passed

    async def _generate_single_path(
        self,
        prompt: str,
        context: dict[str, Any] | None,
        path_index: int,
    ) -> ReasoningPath:
        """Generate a single reasoning path."""
        messages = [
            {"role": "system", "content": self._get_reasoning_prompt(path_index)},
            {"role": "user", "content": prompt},
        ]

        response = await self.llm.ask(messages, tools=None, response_format=None)
        reasoning_text = response.get("content", "")

        # Parse into chain
        chain = self._chain_builder.parse_reasoning_text(
            reasoning_text,
            prompt,
            context,
        )

        # Convert to ReasoningPath
        return ReasoningPath(
            id=chain.id,
            problem=chain.problem,
            context=chain.context,
            steps=chain.steps,
            final_decision=chain.final_decision,
            overall_confidence=chain.overall_confidence,
            created_at=chain.created_at,
            completed_at=chain.completed_at,
            path_id=f"path_{path_index}",
        )

    def _create_prompt_variant(self, problem: str, variant_index: int) -> str:
        """Create a prompt variant for diversity."""
        prefixes = [
            "Think carefully about this problem:",
            "Analyze this step by step:",
            "Consider all aspects of this:",
            "Reason through this thoroughly:",
            "Evaluate this problem carefully:",
        ]

        suffixes = [
            "What is the best approach?",
            "What should be done?",
            "What is the right decision?",
            "How should this be handled?",
            "What action should be taken?",
        ]

        prefix = prefixes[variant_index % len(prefixes)]
        suffix = suffixes[variant_index % len(suffixes)]

        return f"{prefix}\n\n{problem}\n\n{suffix}"

    def _get_reasoning_prompt(self, variant_index: int) -> str:
        """Get system prompt for reasoning with variation."""
        base = "You are a careful reasoner. Think step by step."

        emphases = [
            " Focus on evidence and facts.",
            " Consider alternative viewpoints.",
            " Identify potential risks and issues.",
            " Look for the most practical solution.",
            " Consider long-term implications.",
        ]

        emphasis = emphases[variant_index % len(emphases)]
        return base + emphasis

    def _calculate_similarities(self, paths: list[ReasoningPath]) -> None:
        """Calculate pairwise similarities between paths."""
        if len(paths) < 2:
            for path in paths:
                path.similarity_to_others = 1.0
            return

        for i, path in enumerate(paths):
            similarities = []
            for j, other in enumerate(paths):
                if i != j:
                    sim = self._path_similarity(path, other)
                    similarities.append(sim)
            path.similarity_to_others = sum(similarities) / len(similarities)

    def _path_similarity(self, path1: ReasoningPath, path2: ReasoningPath) -> float:
        """Calculate similarity between two paths."""
        # Compare final decisions
        if path1.final_decision and path2.final_decision:
            decision_sim = self._text_similarity(
                path1.final_decision,
                path2.final_decision,
            )
        else:
            decision_sim = 0.0

        # Compare thought types distribution
        types1 = Counter(t.type for t in path1.get_all_thoughts())
        types2 = Counter(t.type for t in path2.get_all_thoughts())
        type_sim = self._distribution_similarity(types1, types2)

        # Compare confidence levels
        conf_sim = 1.0 - abs(path1.overall_confidence - path2.overall_confidence)

        # Weighted average
        return decision_sim * 0.5 + type_sim * 0.3 + conf_sim * 0.2

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity using word overlap."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _distribution_similarity(
        self,
        dist1: Counter,
        dist2: Counter,
    ) -> float:
        """Calculate similarity between two distributions."""
        all_keys = set(dist1.keys()) | set(dist2.keys())
        if not all_keys:
            return 1.0

        total1 = sum(dist1.values()) or 1
        total2 = sum(dist2.values()) or 1

        similarity = 0.0
        for key in all_keys:
            p1 = dist1.get(key, 0) / total1
            p2 = dist2.get(key, 0) / total2
            similarity += min(p1, p2)

        return similarity

    def _calculate_agreement(self, decisions: list[Decision]) -> float:
        """Calculate agreement score from decisions."""
        if len(decisions) < 2:
            return 1.0

        # Extract key phrases from each decision
        key_phrases = []
        for d in decisions:
            phrases = self._extract_key_phrases(d.action)
            key_phrases.append(phrases)

        # Count phrase overlaps
        all_phrases = [p for phrases in key_phrases for p in phrases]
        phrase_counts = Counter(all_phrases)

        # Calculate agreement based on common phrases
        if not phrase_counts:
            return 0.5  # Neutral if no phrases

        most_common = phrase_counts.most_common(3)
        agreement_phrases = [p for p, c in most_common if c >= len(decisions) * 0.5]

        if not agreement_phrases:
            return 0.3  # Low agreement

        # Score based on how many decisions share common phrases
        scores = []
        for phrases in key_phrases:
            overlap = len(set(phrases) & set(agreement_phrases))
            scores.append(overlap / max(len(agreement_phrases), 1))

        return sum(scores) / len(scores)

    def _extract_key_phrases(self, text: str) -> list[str]:
        """Extract key phrases from decision text."""
        # Simple extraction - get noun phrases and verb phrases
        words = text.lower().split()
        phrases = []

        # Get 2-3 word phrases
        for i in range(len(words)):
            if i + 1 < len(words):
                phrases.append(f"{words[i]} {words[i + 1]}")
            if i + 2 < len(words):
                phrases.append(f"{words[i]} {words[i + 1]} {words[i + 2]}")

        return phrases

    def _find_consensus_decision(
        self,
        decisions: list[Decision],
    ) -> Decision | None:
        """Find the consensus decision from multiple decisions."""
        if not decisions:
            return None

        if len(decisions) == 1:
            return decisions[0]

        # Score decisions by agreement with others
        scores = []
        for i, decision in enumerate(decisions):
            score = 0.0
            for j, other in enumerate(decisions):
                if i != j:
                    score += self._text_similarity(decision.action, other.action)
            scores.append(score / (len(decisions) - 1))

        # Return highest scoring decision
        best_idx = scores.index(max(scores))
        consensus = decisions[best_idx]

        # Boost confidence for consensus
        consensus.confidence = min(1.0, consensus.confidence * 1.1)

        return consensus

    def _find_dissenting_views(
        self,
        decisions: list[Decision],
        consensus: Decision | None,
    ) -> list[str]:
        """Identify views that differ from consensus."""
        if not consensus or len(decisions) < 2:
            return []

        dissenting = []
        for decision in decisions:
            similarity = self._text_similarity(decision.action, consensus.action)
            if similarity < 0.3:
                dissenting.append(decision.action)

        return dissenting[:3]  # Limit to top 3


# Global instance
_consistency_checker: SelfConsistencyChecker | None = None


def get_consistency_checker(llm: LLM | None = None) -> SelfConsistencyChecker:
    """Get or create the global self-consistency checker."""
    global _consistency_checker
    if _consistency_checker is None:
        if llm is None:
            raise ValueError("LLM required to initialize consistency checker")
        _consistency_checker = SelfConsistencyChecker(llm)
    return _consistency_checker


def reset_consistency_checker() -> None:
    """Reset the global consistency checker."""
    global _consistency_checker
    _consistency_checker = None
