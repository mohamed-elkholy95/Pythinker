"""Ragas-Style Evaluation Metrics for Agent Performance.

Provides evaluation metrics inspired by the RAGAS framework for assessing:
- Faithfulness: Does the answer align with provided context?
- Answer Relevance: How relevant is the answer to the question?
- Tool Selection Accuracy: Did the agent select appropriate tools?
- Context Relevance: How relevant is the retrieved context?

Usage:
    evaluator = RagasEvaluator(llm_client=llm)

    # Evaluate faithfulness
    result = await evaluator.evaluate_faithfulness(
        question="What is the capital of France?",
        answer="The capital of France is Paris.",
        context=["France is a country in Europe. Its capital is Paris."]
    )
    print(f"Faithfulness score: {result.score}")

    # Evaluate tool selection
    result = await evaluator.evaluate_tool_selection(
        task="Read the contents of config.py",
        available_tools=["file_read", "shell_execute", "browser_navigate"],
        selected_tools=["file_read"]
    )
    print(f"Tool selection accuracy: {result.score}")
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class EvalMetricType(str, Enum):
    """Types of evaluation metrics."""

    FAITHFULNESS = "faithfulness"
    ANSWER_RELEVANCE = "answer_relevance"
    CONTEXT_RELEVANCE = "context_relevance"
    TOOL_SELECTION_ACCURACY = "tool_selection_accuracy"
    RESPONSE_COMPLETENESS = "response_completeness"
    HALLUCINATION_SCORE = "hallucination_score"


@dataclass
class EvalResult:
    """Result of an evaluation metric."""

    metric_type: EvalMetricType
    score: float  # 0.0 to 1.0
    passed: bool  # True if score >= threshold
    threshold: float = 0.7
    reasoning: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.passed = self.score >= self.threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_type": self.metric_type.value,
            "score": round(self.score, 4),
            "passed": self.passed,
            "threshold": self.threshold,
            "reasoning": self.reasoning,
            "details": self.details,
            "metadata": self.metadata,
        }


@dataclass
class ToolSelectionResult(EvalResult):
    """Specialized result for tool selection evaluation."""

    expected_tools: list[str] = field(default_factory=list)
    selected_tools: list[str] = field(default_factory=list)
    correct_selections: list[str] = field(default_factory=list)
    missed_tools: list[str] = field(default_factory=list)
    unnecessary_tools: list[str] = field(default_factory=list)

    def __post_init__(self):
        super().__post_init__()
        self.details = {
            "expected_tools": self.expected_tools,
            "selected_tools": self.selected_tools,
            "correct_selections": self.correct_selections,
            "missed_tools": self.missed_tools,
            "unnecessary_tools": self.unnecessary_tools,
        }


@dataclass
class EvaluationBatch:
    """Batch of evaluation results for aggregate analysis."""

    results: list[EvalResult] = field(default_factory=list)
    session_id: str | None = None
    task_id: str | None = None

    @property
    def average_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.passed) / len(self.results)

    def get_by_metric(self, metric_type: EvalMetricType) -> list[EvalResult]:
        return [r for r in self.results if r.metric_type == metric_type]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "total_evaluations": len(self.results),
            "average_score": round(self.average_score, 4),
            "pass_rate": round(self.pass_rate, 4),
            "results": [r.to_dict() for r in self.results],
        }


class LLMClientProtocol(Protocol):
    """Protocol for LLM client interface."""

    async def ask(
        self,
        messages: list[dict[str, str]],
        **kwargs,
    ) -> dict[str, Any]:
        ...


class EvaluatorInterface(ABC):
    """Abstract interface for evaluators."""

    @abstractmethod
    async def evaluate_faithfulness(
        self,
        question: str,
        answer: str,
        context: list[str],
    ) -> EvalResult:
        """Evaluate faithfulness of answer to context."""
        ...

    @abstractmethod
    async def evaluate_relevance(
        self,
        question: str,
        answer: str,
    ) -> EvalResult:
        """Evaluate relevance of answer to question."""
        ...

    @abstractmethod
    async def evaluate_tool_selection(
        self,
        task: str,
        available_tools: list[str],
        selected_tools: list[str],
        expected_tools: list[str] | None = None,
    ) -> ToolSelectionResult:
        """Evaluate tool selection accuracy."""
        ...


class RagasEvaluator(EvaluatorInterface):
    """Ragas-style evaluator for agent responses.

    Uses LLM-as-judge pattern to evaluate response quality across
    multiple dimensions inspired by the RAGAS framework.
    """

    # Prompts for LLM-based evaluation
    FAITHFULNESS_PROMPT = """You are an expert evaluator assessing whether an answer is faithful to the given context.

Question: {question}

Context:
{context}

Answer: {answer}

Evaluate the faithfulness of the answer to the context. Consider:
1. Does the answer only contain information that can be derived from the context?
2. Are there any claims in the answer that contradict the context?
3. Does the answer introduce any information not present in the context?

Respond with JSON:
{{
    "score": <float between 0.0 and 1.0>,
    "faithful_claims": ["list of claims that are supported by context"],
    "unfaithful_claims": ["list of claims NOT supported by context"],
    "reasoning": "brief explanation of the score"
}}"""

    RELEVANCE_PROMPT = """You are an expert evaluator assessing answer relevance.

Question: {question}

Answer: {answer}

Evaluate how relevant and complete the answer is to the question. Consider:
1. Does the answer directly address what was asked?
2. Is the answer complete or does it miss key aspects?
3. Is there unnecessary or off-topic information?

Respond with JSON:
{{
    "score": <float between 0.0 and 1.0>,
    "addresses_question": true/false,
    "completeness": "high/medium/low",
    "off_topic_content": ["list of off-topic elements if any"],
    "reasoning": "brief explanation of the score"
}}"""

    TOOL_SELECTION_PROMPT = """You are an expert evaluator assessing tool selection for an AI agent task.

Task: {task}

Available Tools: {available_tools}

Selected Tools: {selected_tools}

Evaluate whether the tool selection is appropriate for the task. Consider:
1. Are the selected tools capable of accomplishing the task?
2. Were any necessary tools missed?
3. Were any unnecessary tools selected?

Respond with JSON:
{{
    "score": <float between 0.0 and 1.0>,
    "expected_tools": ["list of tools you would expect to be used"],
    "correct_selections": ["tools correctly selected"],
    "missed_tools": ["necessary tools that were not selected"],
    "unnecessary_tools": ["tools selected but not needed"],
    "reasoning": "brief explanation of the score"
}}"""

    def __init__(
        self,
        llm_client: LLMClientProtocol | None = None,
        default_threshold: float = 0.7,
        use_llm_evaluation: bool = True,
    ):
        """Initialize the evaluator.

        Args:
            llm_client: LLM client for evaluation (required for LLM-based eval)
            default_threshold: Default passing threshold for metrics
            use_llm_evaluation: Whether to use LLM for evaluation (vs heuristics)
        """
        self.llm_client = llm_client
        self.default_threshold = default_threshold
        self.use_llm_evaluation = use_llm_evaluation

    async def evaluate_faithfulness(
        self,
        question: str,
        answer: str,
        context: list[str],
        threshold: float | None = None,
    ) -> EvalResult:
        """Evaluate faithfulness of answer to context.

        Faithfulness measures whether the answer only contains information
        that can be derived from the provided context.

        Args:
            question: The original question
            answer: The generated answer
            context: List of context passages
            threshold: Custom passing threshold

        Returns:
            EvalResult with faithfulness score
        """
        threshold = threshold or self.default_threshold

        if self.use_llm_evaluation and self.llm_client:
            return await self._evaluate_faithfulness_llm(
                question, answer, context, threshold
            )
        return self._evaluate_faithfulness_heuristic(
            question, answer, context, threshold
        )

    async def _evaluate_faithfulness_llm(
        self,
        question: str,
        answer: str,
        context: list[str],
        threshold: float,
    ) -> EvalResult:
        """LLM-based faithfulness evaluation."""
        context_str = "\n---\n".join(context)
        prompt = self.FAITHFULNESS_PROMPT.format(
            question=question,
            context=context_str,
            answer=answer,
        )

        try:
            response = await self.llm_client.ask(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )

            content = response.get("content", "{}")
            result = self._parse_json_response(content)

            return EvalResult(
                metric_type=EvalMetricType.FAITHFULNESS,
                score=float(result.get("score", 0.0)),
                threshold=threshold,
                reasoning=result.get("reasoning", ""),
                details={
                    "faithful_claims": result.get("faithful_claims", []),
                    "unfaithful_claims": result.get("unfaithful_claims", []),
                },
            )

        except Exception as e:
            logger.warning(f"LLM faithfulness evaluation failed: {e}")
            return self._evaluate_faithfulness_heuristic(
                question, answer, context, threshold
            )

    def _evaluate_faithfulness_heuristic(
        self,
        question: str,
        answer: str,
        context: list[str],
        threshold: float,
    ) -> EvalResult:
        """Heuristic-based faithfulness evaluation.

        Uses keyword overlap and sentence matching as a simple proxy.
        """
        context_text = " ".join(context).lower()
        answer_lower = answer.lower()

        # Extract key terms from answer
        answer_words = set(re.findall(r'\b\w{4,}\b', answer_lower))
        context_words = set(re.findall(r'\b\w{4,}\b', context_text))

        if not answer_words:
            return EvalResult(
                metric_type=EvalMetricType.FAITHFULNESS,
                score=1.0,
                threshold=threshold,
                reasoning="Empty answer has trivial faithfulness",
            )

        # Calculate overlap
        overlap = answer_words & context_words
        overlap_ratio = len(overlap) / len(answer_words)

        # Check for specific factual claims in answer
        # Simple check: numbers and proper nouns should appear in context
        numbers_in_answer = set(re.findall(r'\b\d+(?:\.\d+)?\b', answer))
        numbers_in_context = set(re.findall(r'\b\d+(?:\.\d+)?\b', " ".join(context)))
        number_overlap = (
            len(numbers_in_answer & numbers_in_context) / len(numbers_in_answer)
            if numbers_in_answer
            else 1.0
        )

        # Combine scores
        score = 0.7 * overlap_ratio + 0.3 * number_overlap

        return EvalResult(
            metric_type=EvalMetricType.FAITHFULNESS,
            score=score,
            threshold=threshold,
            reasoning=f"Keyword overlap: {overlap_ratio:.2%}, Number match: {number_overlap:.2%}",
            details={
                "keyword_overlap": overlap_ratio,
                "number_match": number_overlap,
                "overlapping_terms": list(overlap)[:20],
            },
        )

    async def evaluate_relevance(
        self,
        question: str,
        answer: str,
        threshold: float | None = None,
    ) -> EvalResult:
        """Evaluate relevance of answer to question.

        Answer relevance measures how well the answer addresses
        the question asked.

        Args:
            question: The original question
            answer: The generated answer
            threshold: Custom passing threshold

        Returns:
            EvalResult with relevance score
        """
        threshold = threshold or self.default_threshold

        if self.use_llm_evaluation and self.llm_client:
            return await self._evaluate_relevance_llm(question, answer, threshold)
        return self._evaluate_relevance_heuristic(question, answer, threshold)

    async def _evaluate_relevance_llm(
        self,
        question: str,
        answer: str,
        threshold: float,
    ) -> EvalResult:
        """LLM-based relevance evaluation."""
        prompt = self.RELEVANCE_PROMPT.format(question=question, answer=answer)

        try:
            response = await self.llm_client.ask(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )

            content = response.get("content", "{}")
            result = self._parse_json_response(content)

            return EvalResult(
                metric_type=EvalMetricType.ANSWER_RELEVANCE,
                score=float(result.get("score", 0.0)),
                threshold=threshold,
                reasoning=result.get("reasoning", ""),
                details={
                    "addresses_question": result.get("addresses_question", False),
                    "completeness": result.get("completeness", "unknown"),
                    "off_topic_content": result.get("off_topic_content", []),
                },
            )

        except Exception as e:
            logger.warning(f"LLM relevance evaluation failed: {e}")
            return self._evaluate_relevance_heuristic(question, answer, threshold)

    def _evaluate_relevance_heuristic(
        self,
        question: str,
        answer: str,
        threshold: float,
    ) -> EvalResult:
        """Heuristic-based relevance evaluation."""
        question_lower = question.lower()
        answer_lower = answer.lower()

        # Extract question type
        is_what_question = question_lower.startswith("what")
        is_how_question = question_lower.startswith("how")
        is_why_question = question_lower.startswith("why")
        is_yes_no = question_lower.startswith(("is ", "are ", "does ", "do ", "can ", "will "))

        # Check if answer addresses the question type
        addresses_question = True
        if is_yes_no:
            # Should start with yes/no or contain affirmative/negative
            has_yes_no = any(
                word in answer_lower.split()[:10]
                for word in ["yes", "no", "correct", "incorrect", "true", "false"]
            )
            addresses_question = has_yes_no

        # Check keyword overlap between question and answer
        question_words = set(re.findall(r'\b\w{4,}\b', question_lower))
        answer_words = set(re.findall(r'\b\w{4,}\b', answer_lower))
        stopwords = {"what", "where", "when", "which", "would", "could", "should", "have", "this", "that", "with"}
        question_words -= stopwords

        overlap = question_words & answer_words
        overlap_ratio = len(overlap) / len(question_words) if question_words else 1.0

        # Answer length check (too short or too long may indicate issues)
        answer_len = len(answer.split())
        length_penalty = 1.0
        if answer_len < 5:
            length_penalty = 0.7
        elif answer_len > 500:
            length_penalty = 0.9

        score = (0.5 * overlap_ratio + 0.5 * (1.0 if addresses_question else 0.5)) * length_penalty

        return EvalResult(
            metric_type=EvalMetricType.ANSWER_RELEVANCE,
            score=min(score, 1.0),
            threshold=threshold,
            reasoning=f"Keyword coverage: {overlap_ratio:.2%}, Addresses question: {addresses_question}",
            details={
                "keyword_overlap": overlap_ratio,
                "addresses_question": addresses_question,
                "answer_length": answer_len,
                "length_penalty": length_penalty,
            },
        )

    async def evaluate_tool_selection(
        self,
        task: str,
        available_tools: list[str],
        selected_tools: list[str],
        expected_tools: list[str] | None = None,
        threshold: float | None = None,
    ) -> ToolSelectionResult:
        """Evaluate tool selection accuracy.

        Args:
            task: The task description
            available_tools: List of tools available to the agent
            selected_tools: List of tools actually selected
            expected_tools: Optional ground truth of expected tools
            threshold: Custom passing threshold

        Returns:
            ToolSelectionResult with accuracy metrics
        """
        threshold = threshold or self.default_threshold

        # If expected tools provided, use exact matching
        if expected_tools:
            return self._evaluate_tool_selection_exact(
                task, available_tools, selected_tools, expected_tools, threshold
            )

        # Otherwise, use LLM or heuristic evaluation
        if self.use_llm_evaluation and self.llm_client:
            return await self._evaluate_tool_selection_llm(
                task, available_tools, selected_tools, threshold
            )
        return self._evaluate_tool_selection_heuristic(
            task, available_tools, selected_tools, threshold
        )

    def _evaluate_tool_selection_exact(
        self,
        task: str,
        available_tools: list[str],
        selected_tools: list[str],
        expected_tools: list[str],
        threshold: float,
    ) -> ToolSelectionResult:
        """Exact match evaluation when expected tools are known."""
        selected_set = set(selected_tools)
        expected_set = set(expected_tools)

        correct = selected_set & expected_set
        missed = expected_set - selected_set
        unnecessary = selected_set - expected_set

        # F1-style score
        precision = len(correct) / len(selected_set) if selected_set else 0.0
        recall = len(correct) / len(expected_set) if expected_set else 1.0

        if precision + recall > 0:
            score = 2 * (precision * recall) / (precision + recall)
        else:
            score = 0.0

        return ToolSelectionResult(
            metric_type=EvalMetricType.TOOL_SELECTION_ACCURACY,
            score=score,
            threshold=threshold,
            reasoning=f"Precision: {precision:.2%}, Recall: {recall:.2%}",
            expected_tools=expected_tools,
            selected_tools=selected_tools,
            correct_selections=list(correct),
            missed_tools=list(missed),
            unnecessary_tools=list(unnecessary),
            metadata={"precision": precision, "recall": recall},
        )

    async def _evaluate_tool_selection_llm(
        self,
        task: str,
        available_tools: list[str],
        selected_tools: list[str],
        threshold: float,
    ) -> ToolSelectionResult:
        """LLM-based tool selection evaluation."""
        prompt = self.TOOL_SELECTION_PROMPT.format(
            task=task,
            available_tools=", ".join(available_tools),
            selected_tools=", ".join(selected_tools),
        )

        try:
            response = await self.llm_client.ask(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )

            content = response.get("content", "{}")
            result = self._parse_json_response(content)

            return ToolSelectionResult(
                metric_type=EvalMetricType.TOOL_SELECTION_ACCURACY,
                score=float(result.get("score", 0.0)),
                threshold=threshold,
                reasoning=result.get("reasoning", ""),
                expected_tools=result.get("expected_tools", []),
                selected_tools=selected_tools,
                correct_selections=result.get("correct_selections", []),
                missed_tools=result.get("missed_tools", []),
                unnecessary_tools=result.get("unnecessary_tools", []),
            )

        except Exception as e:
            logger.warning(f"LLM tool selection evaluation failed: {e}")
            return self._evaluate_tool_selection_heuristic(
                task, available_tools, selected_tools, threshold
            )

    def _evaluate_tool_selection_heuristic(
        self,
        task: str,
        available_tools: list[str],
        selected_tools: list[str],
        threshold: float,
    ) -> ToolSelectionResult:
        """Heuristic-based tool selection evaluation.

        Uses keyword matching to estimate expected tools.
        """
        task_lower = task.lower()

        # Tool keyword mapping
        tool_keywords = {
            "file_read": ["read", "file", "content", "view", "cat", "open"],
            "file_write": ["write", "create", "save", "file", "output"],
            "file_search": ["search", "find", "grep", "locate"],
            "shell_execute": ["run", "execute", "command", "terminal", "shell", "install", "build"],
            "browser_navigate": ["browse", "url", "website", "web", "visit", "open"],
            "browser_screenshot": ["screenshot", "capture", "image"],
            "browser_click": ["click", "button", "press"],
            "search": ["search", "google", "find", "lookup", "query"],
        }

        # Infer expected tools from task
        expected = []
        for tool, keywords in tool_keywords.items():
            if tool in available_tools:
                if any(kw in task_lower for kw in keywords):
                    expected.append(tool)

        # Default to shell if task mentions running/executing
        if not expected and any(kw in task_lower for kw in ["run", "execute"]):
            if "shell_execute" in available_tools:
                expected = ["shell_execute"]

        if not expected:
            # Can't infer expectations, give partial credit if tools were selected
            score = 0.5 if selected_tools else 0.0
            return ToolSelectionResult(
                metric_type=EvalMetricType.TOOL_SELECTION_ACCURACY,
                score=score,
                threshold=threshold,
                reasoning="Could not infer expected tools from task description",
                expected_tools=[],
                selected_tools=selected_tools,
                correct_selections=[],
                missed_tools=[],
                unnecessary_tools=[],
            )

        return self._evaluate_tool_selection_exact(
            task, available_tools, selected_tools, expected, threshold
        )

    async def evaluate_context_relevance(
        self,
        question: str,
        context: list[str],
        threshold: float | None = None,
    ) -> EvalResult:
        """Evaluate relevance of retrieved context to the question.

        Args:
            question: The original question
            context: List of context passages
            threshold: Custom passing threshold

        Returns:
            EvalResult with context relevance score
        """
        threshold = threshold or self.default_threshold

        # Heuristic: keyword overlap between question and context
        question_lower = question.lower()
        context_text = " ".join(context).lower()

        question_words = set(re.findall(r'\b\w{4,}\b', question_lower))
        context_words = set(re.findall(r'\b\w{4,}\b', context_text))

        stopwords = {"what", "where", "when", "which", "would", "could", "should", "have", "this", "that"}
        question_words -= stopwords

        if not question_words:
            return EvalResult(
                metric_type=EvalMetricType.CONTEXT_RELEVANCE,
                score=1.0,
                threshold=threshold,
                reasoning="No significant question terms to match",
            )

        overlap = question_words & context_words
        score = len(overlap) / len(question_words)

        return EvalResult(
            metric_type=EvalMetricType.CONTEXT_RELEVANCE,
            score=score,
            threshold=threshold,
            reasoning=f"Question term coverage in context: {score:.2%}",
            details={
                "question_terms": list(question_words),
                "matching_terms": list(overlap),
                "coverage": score,
            },
        )

    async def evaluate_hallucination(
        self,
        answer: str,
        context: list[str],
        threshold: float | None = None,
    ) -> EvalResult:
        """Evaluate potential hallucination in the answer.

        Lower score = more hallucination detected.

        Args:
            answer: The generated answer
            context: List of context passages
            threshold: Custom passing threshold

        Returns:
            EvalResult with hallucination score (1.0 = no hallucination)
        """
        threshold = threshold or self.default_threshold

        context_text = " ".join(context).lower()
        answer_lower = answer.lower()

        # Check for specific factual claims that should be grounded
        # Numbers, dates, proper nouns

        # Extract numbers from answer
        answer_numbers = set(re.findall(r'\b\d+(?:[.,]\d+)?\b', answer))
        context_numbers = set(re.findall(r'\b\d+(?:[.,]\d+)?\b', " ".join(context)))

        # Extract potential proper nouns (capitalized words not at sentence start)
        answer_caps = set(re.findall(r'(?<!^)(?<!\. )[A-Z][a-z]+', answer))
        context_caps = set(re.findall(r'(?<!^)(?<!\. )[A-Z][a-z]+', " ".join(context)))

        # Calculate grounding scores
        number_grounding = (
            len(answer_numbers & context_numbers) / len(answer_numbers)
            if answer_numbers
            else 1.0
        )
        name_grounding = (
            len(answer_caps & context_caps) / len(answer_caps) if answer_caps else 1.0
        )

        # Combined score (higher = less hallucination)
        score = 0.5 * number_grounding + 0.5 * name_grounding

        hallucination_indicators = []
        ungrounded_numbers = answer_numbers - context_numbers
        ungrounded_names = answer_caps - context_caps

        if ungrounded_numbers:
            hallucination_indicators.append(f"Ungrounded numbers: {ungrounded_numbers}")
        if ungrounded_names:
            hallucination_indicators.append(f"Ungrounded names: {ungrounded_names}")

        return EvalResult(
            metric_type=EvalMetricType.HALLUCINATION_SCORE,
            score=score,
            threshold=threshold,
            reasoning=(
                "No hallucination indicators"
                if not hallucination_indicators
                else "; ".join(hallucination_indicators)
            ),
            details={
                "number_grounding": number_grounding,
                "name_grounding": name_grounding,
                "ungrounded_numbers": list(ungrounded_numbers),
                "ungrounded_names": list(ungrounded_names),
            },
        )

    async def evaluate_all(
        self,
        question: str,
        answer: str,
        context: list[str],
        selected_tools: list[str] | None = None,
        available_tools: list[str] | None = None,
    ) -> EvaluationBatch:
        """Run all applicable evaluation metrics.

        Args:
            question: The original question
            answer: The generated answer
            context: List of context passages
            selected_tools: Optional list of tools selected
            available_tools: Optional list of available tools

        Returns:
            EvaluationBatch with all results
        """
        results = []

        # Core evaluations
        faithfulness = await self.evaluate_faithfulness(question, answer, context)
        results.append(faithfulness)

        relevance = await self.evaluate_relevance(question, answer)
        results.append(relevance)

        context_relevance = await self.evaluate_context_relevance(question, context)
        results.append(context_relevance)

        hallucination = await self.evaluate_hallucination(answer, context)
        results.append(hallucination)

        # Tool selection if applicable
        if selected_tools is not None and available_tools is not None:
            tool_eval = await self.evaluate_tool_selection(
                task=question,
                available_tools=available_tools,
                selected_tools=selected_tools,
            )
            results.append(tool_eval)

        return EvaluationBatch(results=results)

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        """Parse JSON from LLM response, handling markdown code blocks."""
        content = content.strip()

        # Handle markdown code blocks
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first and last lines (```json and ```)
            lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            content = "\n".join(lines)

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from the content
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            return {}


# Factory function
def create_evaluator(
    llm_client: LLMClientProtocol | None = None,
    use_llm: bool = True,
    default_threshold: float = 0.7,
) -> RagasEvaluator:
    """Create a RagasEvaluator instance.

    Args:
        llm_client: Optional LLM client for LLM-based evaluation
        use_llm: Whether to use LLM evaluation (falls back to heuristics if False)
        default_threshold: Default passing threshold

    Returns:
        Configured RagasEvaluator
    """
    return RagasEvaluator(
        llm_client=llm_client,
        default_threshold=default_threshold,
        use_llm_evaluation=use_llm and llm_client is not None,
    )
