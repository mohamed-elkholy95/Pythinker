"""
Thought chain builder for structured reasoning.

This module provides utilities for constructing and manipulating
reasoning chains from LLM outputs.
"""

import logging
import re
from datetime import UTC, datetime
from typing import Any

from app.domain.exceptions.base import InvalidStateException
from app.domain.models.thought import (
    Decision,
    ReasoningStep,
    Thought,
    ThoughtChain,
    ThoughtQuality,
    ThoughtType,
)

logger = logging.getLogger(__name__)

# Patterns for detecting thought types in text
THOUGHT_TYPE_PATTERNS = {
    ThoughtType.OBSERVATION: [
        r"I (?:notice|see|observe|find) that",
        r"(?:The|This) (?:shows|indicates|suggests)",
        r"Looking at",
        r"From the (?:context|data|information)",
    ],
    ThoughtType.ANALYSIS: [
        r"Breaking (?:this|it) down",
        r"(?:Analyzing|Examining|Considering)",
        r"The (?:key|main|core) (?:aspects|factors|elements)",
        r"Let me (?:analyze|examine|break down)",
    ],
    ThoughtType.HYPOTHESIS: [
        r"(?:I think|I believe|It seems|Perhaps|Maybe|Possibly)",
        r"(?:This|It) (?:could|might|may) be",
        r"(?:One|A) possible (?:explanation|reason|cause)",
        r"If (?:I|we) assume",
    ],
    ThoughtType.INFERENCE: [
        r"(?:Therefore|Thus|Hence|Consequently|So)",
        r"This (?:means|implies|suggests) that",
        r"(?:Based|Building) on (?:this|these)",
        r"(?:We|I) can (?:conclude|infer|deduce)",
    ],
    ThoughtType.EVALUATION: [
        r"(?:Comparing|Weighing|Evaluating|Assessing)",
        r"The (?:pros|cons|advantages|disadvantages)",
        r"(?:Better|Worse|More|Less) than",
        r"(?:On balance|Overall|In total)",
    ],
    ThoughtType.DECISION: [
        r"(?:I will|I should|I need to|The best (?:option|approach|solution))",
        r"(?:Deciding|Choosing) to",
        r"(?:My|The) (?:decision|choice|recommendation) is",
        r"(?:Let's|I'll) (?:go with|proceed with|use)",
    ],
    ThoughtType.REFLECTION: [
        r"(?:Looking back|Reflecting|Reconsidering)",
        r"(?:I|We) (?:should|could) have",
        r"(?:On second thought|Actually|Wait)",
        r"(?:This|That) reminds me",
    ],
    ThoughtType.UNCERTAINTY: [
        r"(?:I'm not sure|I don't know|Uncertain|Unclear)",
        r"(?:This is|It's) (?:unclear|ambiguous|uncertain)",
        r"(?:More|Additional) (?:information|context|data) (?:is needed|would help)",
        r"(?:I lack|Without) (?:information|knowledge|context)",
    ],
}

# Quality indicators
HIGH_QUALITY_INDICATORS = [
    r"because",
    r"evidence",
    r"data shows",
    r"according to",
    r"specifically",
    r"for example",
    r"research indicates",
]

LOW_QUALITY_INDICATORS = [
    r"I guess",
    r"maybe",
    r"not sure",
    r"probably",
    r"I think",
    r"might be",
]


class ThoughtChainBuilder:
    """Builder for constructing thought chains from LLM reasoning.

    Parses structured reasoning output and builds a coherent
    ThoughtChain with proper typing and quality assessment.
    """

    def __init__(self) -> None:
        """Initialize the thought chain builder."""
        self._current_chain: ThoughtChain | None = None
        self._current_step: ReasoningStep | None = None

    def start_chain(self, problem: str, context: dict[str, Any] | None = None) -> ThoughtChain:
        """Start a new thought chain for a problem.

        Args:
            problem: The problem or question being reasoned about
            context: Optional context information

        Returns:
            The initialized thought chain
        """
        self._current_chain = ThoughtChain(
            problem=problem,
            context=context or {},
        )
        return self._current_chain

    def start_step(self, name: str) -> ReasoningStep:
        """Start a new reasoning step.

        Args:
            name: The name of the reasoning step

        Returns:
            The initialized reasoning step
        """
        if not self._current_chain:
            raise InvalidStateException("Must start a chain before starting a step")

        self._current_step = ReasoningStep(name=name)
        return self._current_step

    def add_thought(
        self,
        content: str,
        thought_type: ThoughtType | None = None,
        confidence: float | None = None,
        supporting_evidence: list[str] | None = None,
    ) -> Thought:
        """Add a thought to the current step.

        If thought_type is not provided, it will be inferred from content.
        If confidence is not provided, it will be estimated.

        Args:
            content: The thought content
            thought_type: Optional explicit thought type
            confidence: Optional explicit confidence
            supporting_evidence: Optional list of evidence

        Returns:
            The created thought
        """
        if not self._current_step:
            raise InvalidStateException("Must start a step before adding thoughts")

        # Infer type if not provided
        if thought_type is None:
            thought_type = self._infer_thought_type(content)

        # Estimate confidence if not provided
        if confidence is None:
            confidence = self._estimate_confidence(content)

        # Assess quality
        quality = self._assess_quality(content, confidence)

        thought = Thought(
            type=thought_type,
            content=content,
            confidence=confidence,
            quality=quality,
            supporting_evidence=supporting_evidence or [],
        )

        self._current_step.add_thought(thought)
        return thought

    def complete_step(self, conclusion: str | None = None) -> ReasoningStep:
        """Complete the current reasoning step.

        Args:
            conclusion: Optional conclusion for the step

        Returns:
            The completed reasoning step
        """
        if not self._current_step:
            raise InvalidStateException("No current step to complete")
        if not self._current_chain:
            raise InvalidStateException("No current chain")

        self._current_step.conclusion = conclusion
        self._current_step.confidence = self._current_step.get_average_confidence()
        self._current_step.is_complete = True

        self._current_chain.add_step(self._current_step)
        completed = self._current_step
        self._current_step = None

        return completed

    def complete_chain(self, final_decision: str) -> ThoughtChain:
        """Complete the thought chain with a final decision.

        Args:
            final_decision: The final decision/action

        Returns:
            The completed thought chain
        """
        if not self._current_chain:
            raise InvalidStateException("No current chain to complete")

        # Complete any pending step
        if self._current_step:
            self.complete_step()

        self._current_chain.final_decision = final_decision
        self._current_chain.overall_confidence = self._current_chain.calculate_overall_confidence()
        self._current_chain.completed_at = datetime.now(UTC)

        completed = self._current_chain
        self._current_chain = None

        return completed

    def parse_reasoning_text(
        self,
        text: str,
        problem: str,
        context: dict[str, Any] | None = None,
    ) -> ThoughtChain:
        """Parse unstructured reasoning text into a thought chain.

        Attempts to extract structure from free-form reasoning text
        by identifying thought types and grouping related thoughts.

        Args:
            text: The reasoning text to parse
            problem: The original problem
            context: Optional context

        Returns:
            Parsed thought chain
        """
        self.start_chain(problem, context)

        # Split into paragraphs/sections
        sections = self._split_into_sections(text)

        for i, section in enumerate(sections):
            step_name = self._infer_step_name(section, i)
            self.start_step(step_name)

            # Split section into sentences/thoughts
            sentences = self._split_into_sentences(section)

            for sentence in sentences:
                if sentence.strip():
                    self.add_thought(sentence.strip())

            # Extract conclusion if present
            conclusion = self._extract_conclusion(section)
            self.complete_step(conclusion)

        # Extract final decision
        final_decision = self._extract_final_decision(text)
        return self.complete_chain(final_decision or "No explicit decision reached")

    def extract_decision(self, chain: ThoughtChain) -> Decision:
        """Extract a decision from a completed thought chain.

        Args:
            chain: The completed thought chain

        Returns:
            The extracted decision with rationale
        """
        # Get decision thoughts
        decision_thoughts = chain.get_decisions()

        if not decision_thoughts:
            # Use final decision if no explicit decision thoughts
            action = chain.final_decision or "Unable to determine action"
        else:
            # Use most confident decision thought
            best_decision = max(decision_thoughts, key=lambda t: t.confidence)
            action = best_decision.content

        # Build rationale from inference and evaluation thoughts
        inferences = chain.get_thoughts_by_type(ThoughtType.INFERENCE)
        evaluations = chain.get_thoughts_by_type(ThoughtType.EVALUATION)

        rationale_parts = [thought.content for thought in (inferences + evaluations)[:3]]

        rationale = " ".join(rationale_parts) if rationale_parts else "Based on analysis"

        # Extract risks from uncertainties
        risks = [u.content for u in chain.get_uncertainties()[:3]]

        # Extract alternatives from hypothesis thoughts
        hypotheses = chain.get_thoughts_by_type(ThoughtType.HYPOTHESIS)
        alternatives = [h.content for h in hypotheses[:2]]

        return Decision(
            action=action,
            rationale=rationale,
            confidence=chain.overall_confidence,
            alternatives_considered=alternatives,
            risks=risks,
            source_chain_id=chain.id,
        )

    def _infer_thought_type(self, content: str) -> ThoughtType:
        """Infer the thought type from content using pattern matching."""
        for thought_type, patterns in THOUGHT_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    return thought_type

        # Default to analysis if no pattern matches
        return ThoughtType.ANALYSIS

    def _estimate_confidence(self, content: str) -> float:
        """Estimate confidence level from content."""
        content_lower = content.lower()

        # Start with neutral confidence
        confidence = 0.5

        # Boost for high-quality indicators
        for indicator in HIGH_QUALITY_INDICATORS:
            if indicator in content_lower:
                confidence += 0.1

        # Reduce for low-quality indicators
        for indicator in LOW_QUALITY_INDICATORS:
            if indicator in content_lower:
                confidence -= 0.1

        # Clamp to valid range
        return max(0.1, min(0.9, confidence))

    def _assess_quality(self, content: str, confidence: float) -> ThoughtQuality:
        """Assess the quality of a thought."""
        content_lower = content.lower()

        # Check for evidence
        has_evidence = any(ind in content_lower for ind in HIGH_QUALITY_INDICATORS)

        # Check for uncertainty markers
        is_uncertain = any(ind in content_lower for ind in LOW_QUALITY_INDICATORS)

        if has_evidence and confidence >= 0.7:
            return ThoughtQuality.HIGH
        if is_uncertain or confidence < 0.4:
            return ThoughtQuality.LOW
        if confidence < 0.3:
            return ThoughtQuality.UNCERTAIN
        return ThoughtQuality.MEDIUM

    def _split_into_sections(self, text: str) -> list[str]:
        """Split text into logical sections."""
        # Try splitting by common section patterns
        patterns = [
            r"\n\n+",  # Double newlines
            r"\n(?=\d+[\.\)])",  # Numbered lists
            r"\n(?=[-*])",  # Bullet points
            r"\n(?=[A-Z][a-z]+:)",  # Section headers
        ]

        sections = [text]
        for pattern in patterns:
            new_sections = []
            for section in sections:
                parts = re.split(pattern, section)
                new_sections.extend([p.strip() for p in parts if p.strip()])
            if len(new_sections) > 1:
                sections = new_sections
                break

        return sections if len(sections) > 1 else [text]

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        # Split by sentence-ending punctuation
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _infer_step_name(self, section: str, index: int) -> str:
        """Infer a step name from section content."""
        section_lower = section.lower()

        if any(word in section_lower for word in ["first", "begin", "start", "initial"]):
            return "Initial Analysis"
        if any(word in section_lower for word in ["then", "next", "after"]):
            return f"Step {index + 1}"
        if any(word in section_lower for word in ["finally", "conclude", "decision", "therefore"]):
            return "Conclusion"
        if any(word in section_lower for word in ["option", "alternative", "compare"]):
            return "Option Evaluation"
        if any(word in section_lower for word in ["risk", "issue", "problem", "concern"]):
            return "Risk Assessment"
        return f"Reasoning Step {index + 1}"

    def _extract_conclusion(self, section: str) -> str | None:
        """Extract a conclusion from a section if present."""
        conclusion_patterns = [
            r"(?:Therefore|Thus|Hence|So|Consequently),?\s*(.+?)(?:\.|$)",
            r"(?:In conclusion|To conclude),?\s*(.+?)(?:\.|$)",
            r"(?:This means|This indicates),?\s*(.+?)(?:\.|$)",
        ]

        for pattern in conclusion_patterns:
            match = re.search(pattern, section, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _extract_final_decision(self, text: str) -> str | None:
        """Extract the final decision from full text."""
        decision_patterns = [
            r"(?:I will|I should|I need to)\s+(.+?)(?:\.|$)",
            r"(?:The best|The optimal|The recommended)\s+(?:option|approach|solution)\s+is\s+(.+?)(?:\.|$)",
            r"(?:My decision|My recommendation|I recommend)\s+(?:is to|is that)?\s*(.+?)(?:\.|$)",
        ]

        for pattern in decision_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None


def create_thought_chain(
    problem: str,
    reasoning_text: str,
    context: dict[str, Any] | None = None,
) -> ThoughtChain:
    """Convenience function to create a thought chain from text.

    Args:
        problem: The problem being reasoned about
        reasoning_text: The reasoning text to parse
        context: Optional context

    Returns:
        Parsed thought chain
    """
    builder = ThoughtChainBuilder()
    return builder.parse_reasoning_text(reasoning_text, problem, context)


def extract_decision_from_reasoning(
    problem: str,
    reasoning_text: str,
    context: dict[str, Any] | None = None,
) -> Decision:
    """Convenience function to extract a decision from reasoning text.

    Args:
        problem: The problem being reasoned about
        reasoning_text: The reasoning text to parse
        context: Optional context

    Returns:
        Extracted decision
    """
    builder = ThoughtChainBuilder()
    chain = builder.parse_reasoning_text(reasoning_text, problem, context)
    return builder.extract_decision(chain)
