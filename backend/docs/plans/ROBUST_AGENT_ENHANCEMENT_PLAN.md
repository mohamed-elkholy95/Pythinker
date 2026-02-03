# Robust Agent Enhancement Plan
## Based on Industry Best Practices 2025-2026

---

## Executive Summary

This plan incorporates cutting-edge research and industry best practices from:
- **Meta AI**: Chain-of-Verification (CoVe) - reduces hallucinations by 50%+
- **Stanford Research**: Multi-layer strategies (RAG + RLHF + guardrails) = 96% reduction
- **Google DeepMind**: FACTS Grounding benchmark methodology
- **Anthropic**: Claude 4.x grounding best practices with `<investigate_before_answering>`
- **LangChain**: Middleware patterns for retry and error recovery
- **RAGAS Framework**: Faithfulness, Answer Relevancy, Context Precision metrics
- **Industry Standards**: Plan-Act-Check-Refine loops, Generator-Critic patterns

### Target Metrics
| Metric | Current (Est.) | Target | Industry Benchmark |
|--------|---------------|--------|-------------------|
| Hallucination Rate | ~10-15% | <2% | <2% for mission-critical |
| Faithfulness Score | ~0.6 | >0.9 | >0.9 enterprise standard |
| Revision Rate | ~30% | <15% | Minimize while maintaining quality |
| Error Recovery Success | Unknown | >80% | 80%+ with learning |

---

## Phase 1: Chain-of-Verification (CoVe) Implementation

### Research Foundation
From Meta AI's CoVe paper (2023): *"CoVe decreases hallucinations across a variety of tasks, from list-based questions to longform text generation."*

Key insight: LLMs are more truthful when asked to **verify a particular fact** rather than use it in their own answer.

### Implementation

Create `backend/app/domain/services/agents/chain_of_verification.py`:

```python
"""Chain-of-Verification (CoVe) Implementation.

Based on Meta AI research: "Chain-of-Verification Reduces Hallucination
in Large Language Models" (Dhuliawala et al., 2023)

Process:
1. Generate baseline response
2. Plan verification questions
3. Answer questions independently (key: don't bias with draft)
4. Generate verified response incorporating answers
"""

from dataclasses import dataclass, field
from typing import Any
import asyncio
import logging

from app.domain.external.llm import LLM
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)


@dataclass
class VerificationQuestion:
    """A verification question for fact-checking."""
    question: str
    claim_being_verified: str
    answer: str | None = None
    verified: bool | None = None


@dataclass
class CoVeResult:
    """Result of Chain-of-Verification process."""
    original_response: str
    verification_questions: list[VerificationQuestion]
    verified_response: str
    claims_verified: int
    claims_contradicted: int
    confidence_score: float


VERIFICATION_PLAN_PROMPT = """
Analyze the following response and generate verification questions
to fact-check the key claims. Focus on:
- Specific dates, numbers, and statistics
- Named entities and their attributes
- Causal claims and relationships
- Comparative statements

Response to verify:
{response}

Generate 3-5 verification questions in JSON format:
{{
    "questions": [
        {{
            "question": "Was X true?",
            "claim": "The specific claim being verified"
        }}
    ]
}}
"""

INDEPENDENT_VERIFY_PROMPT = """
Answer the following verification question based ONLY on your knowledge.
Do NOT reference any previous context or responses.

Question: {question}

Provide a factual answer. If uncertain, say "I cannot verify this claim."
"""

FINAL_RESPONSE_PROMPT = """
You previously generated a response that has been fact-checked.
Revise your response to incorporate the verification results.

Original response:
{original_response}

Verification results:
{verification_results}

Rules:
- Remove or qualify any claims that were contradicted
- Keep claims that were verified
- Add uncertainty markers for unverifiable claims
- Maintain the original structure and intent

Generate the corrected response:
"""


class ChainOfVerification:
    """Implements Meta AI's Chain-of-Verification pattern.

    Usage:
        cove = ChainOfVerification(llm, json_parser)
        result = await cove.verify_and_refine(
            query="What are the best practices for X?",
            response="The agent's initial response...",
            max_questions=5
        )

        if result.claims_contradicted > 0:
            return result.verified_response
    """

    def __init__(
        self,
        llm: LLM,
        json_parser: JsonParser,
        max_questions: int = 5,
        parallel_verification: bool = True,
    ):
        self.llm = llm
        self.json_parser = json_parser
        self.max_questions = max_questions
        self.parallel_verification = parallel_verification

    async def verify_and_refine(
        self,
        query: str,
        response: str,
        context: str | None = None,
    ) -> CoVeResult:
        """Run full CoVe pipeline on a response.

        Args:
            query: Original user query
            response: Response to verify
            context: Optional source context for grounding

        Returns:
            CoVeResult with verified response
        """
        # Step 1: Generate verification questions
        questions = await self._plan_verification(response)

        if not questions:
            return CoVeResult(
                original_response=response,
                verification_questions=[],
                verified_response=response,
                claims_verified=0,
                claims_contradicted=0,
                confidence_score=0.8,  # Baseline confidence
            )

        # Step 2: Answer questions independently (parallel for speed)
        if self.parallel_verification:
            answered = await self._verify_parallel(questions)
        else:
            answered = await self._verify_sequential(questions)

        # Step 3: Generate refined response
        verified_response = await self._generate_verified_response(
            response, answered
        )

        # Calculate metrics
        verified_count = sum(1 for q in answered if q.verified is True)
        contradicted_count = sum(1 for q in answered if q.verified is False)
        total = len(answered)

        confidence = verified_count / max(total, 1)

        logger.info(
            f"CoVe complete: {verified_count}/{total} verified, "
            f"{contradicted_count} contradicted"
        )

        return CoVeResult(
            original_response=response,
            verification_questions=answered,
            verified_response=verified_response,
            claims_verified=verified_count,
            claims_contradicted=contradicted_count,
            confidence_score=confidence,
        )

    async def _plan_verification(
        self, response: str
    ) -> list[VerificationQuestion]:
        """Generate verification questions for claims in response."""
        prompt = VERIFICATION_PLAN_PROMPT.format(response=response)

        try:
            result = await self.llm.ask(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )

            parsed = await self.json_parser.parse(result.get("content", ""))
            questions = parsed.get("questions", [])[:self.max_questions]

            return [
                VerificationQuestion(
                    question=q["question"],
                    claim_being_verified=q.get("claim", ""),
                )
                for q in questions
            ]
        except Exception as e:
            logger.warning(f"Failed to plan verification: {e}")
            return []

    async def _verify_single(
        self, question: VerificationQuestion
    ) -> VerificationQuestion:
        """Verify a single claim independently."""
        prompt = INDEPENDENT_VERIFY_PROMPT.format(question=question.question)

        try:
            result = await self.llm.ask(
                messages=[{"role": "user", "content": prompt}],
            )
            answer = result.get("content", "")
            question.answer = answer

            # Determine if verified or contradicted
            lower_answer = answer.lower()
            if "cannot verify" in lower_answer or "uncertain" in lower_answer:
                question.verified = None  # Unknown
            elif "no" in lower_answer[:20] or "incorrect" in lower_answer:
                question.verified = False
            else:
                question.verified = True

        except Exception as e:
            logger.warning(f"Verification failed: {e}")
            question.verified = None

        return question

    async def _verify_parallel(
        self, questions: list[VerificationQuestion]
    ) -> list[VerificationQuestion]:
        """Verify all questions in parallel."""
        tasks = [self._verify_single(q) for q in questions]
        return await asyncio.gather(*tasks)

    async def _verify_sequential(
        self, questions: list[VerificationQuestion]
    ) -> list[VerificationQuestion]:
        """Verify questions sequentially."""
        for q in questions:
            await self._verify_single(q)
        return questions

    async def _generate_verified_response(
        self,
        original: str,
        questions: list[VerificationQuestion],
    ) -> str:
        """Generate refined response based on verification."""
        # Format verification results
        results = []
        for q in questions:
            status = "VERIFIED" if q.verified else (
                "CONTRADICTED" if q.verified is False else "UNCERTAIN"
            )
            results.append(
                f"- Claim: {q.claim_being_verified}\n"
                f"  Status: {status}\n"
                f"  Evidence: {q.answer}"
            )

        prompt = FINAL_RESPONSE_PROMPT.format(
            original_response=original,
            verification_results="\n".join(results),
        )

        try:
            result = await self.llm.ask(
                messages=[{"role": "user", "content": prompt}],
            )
            return result.get("content", original)
        except Exception as e:
            logger.warning(f"Failed to generate verified response: {e}")
            return original
```

### Integration Point

In `backend/app/domain/services/agents/execution.py`:

```python
async def _maybe_verify_response(
    self,
    response: str,
    task_type: str
) -> str:
    """Apply CoVe for high-risk outputs."""
    if task_type not in ["research", "comparison", "factual"]:
        return response

    if len(response) < 500:  # Skip short responses
        return response

    cove = ChainOfVerification(self.llm, self.json_parser)
    result = await cove.verify_and_refine(
        query=self.current_step,
        response=response,
    )

    if result.claims_contradicted > 0:
        logger.warning(
            f"CoVe found {result.claims_contradicted} contradictions, "
            f"using verified response"
        )
        return result.verified_response

    return response
```

---

## Phase 2: RAGAS-Based Evaluation Pipeline

### Research Foundation
RAGAS framework provides standardized metrics:
- **Faithfulness**: Are claims supported by context? (Target: >0.9)
- **Answer Relevancy**: Does response address the query?
- **Context Precision**: Are retrieved contexts relevant?
- **Context Recall**: Are all relevant contexts retrieved?

### Implementation

Create `backend/app/domain/services/evaluation/ragas_evaluator.py`:

```python
"""RAGAS-style evaluation for agent outputs.

Implements core metrics:
- Faithfulness: Claims grounded in source context
- Answer Relevancy: Response addresses user query
- Context Precision: Retrieved context is relevant
- Groundedness: Combined grounding score
"""

from dataclasses import dataclass
from typing import Any
import asyncio
import logging

from app.domain.external.llm import LLM

logger = logging.getLogger(__name__)


@dataclass
class RAGASScore:
    """Comprehensive RAGAS-style evaluation score."""
    faithfulness: float  # 0-1: Claims supported by context
    answer_relevancy: float  # 0-1: Response addresses query
    context_precision: float  # 0-1: Context is relevant
    groundedness: float  # 0-1: Overall grounding score

    claims_analyzed: int = 0
    claims_supported: int = 0
    claims_contradicted: int = 0

    @property
    def overall_score(self) -> float:
        """Weighted average of all metrics."""
        return (
            self.faithfulness * 0.4 +
            self.answer_relevancy * 0.3 +
            self.context_precision * 0.2 +
            self.groundedness * 0.1
        )

    @property
    def is_acceptable(self) -> bool:
        """Check if scores meet quality threshold."""
        return (
            self.faithfulness >= 0.7 and
            self.answer_relevancy >= 0.6 and
            self.overall_score >= 0.7
        )


FAITHFULNESS_PROMPT = """
Analyze the faithfulness of the response to the source context.

For each claim in the response, determine if it is:
1. SUPPORTED: Directly stated or clearly implied by the context
2. CONTRADICTED: Conflicts with the context
3. NOT_VERIFIABLE: Cannot be verified from context

Source Context:
{context}

Response to evaluate:
{response}

Return JSON:
{{
    "claims": [
        {{"claim": "...", "status": "SUPPORTED|CONTRADICTED|NOT_VERIFIABLE"}}
    ],
    "faithfulness_score": 0.0-1.0,
    "explanation": "..."
}}
"""

RELEVANCY_PROMPT = """
Evaluate how well the response addresses the user's query.

Query: {query}

Response: {response}

Consider:
- Does it directly answer what was asked?
- Is information complete for the query?
- Is there irrelevant information?

Return JSON:
{{
    "relevancy_score": 0.0-1.0,
    "addresses_query": true/false,
    "missing_elements": ["..."],
    "explanation": "..."
}}
"""


class RAGASEvaluator:
    """Evaluates agent outputs using RAGAS-style metrics.

    Usage:
        evaluator = RAGASEvaluator(llm)
        score = await evaluator.evaluate(
            query="What is X?",
            response="X is...",
            contexts=["Source 1...", "Source 2..."]
        )

        if not score.is_acceptable:
            # Trigger revision
            pass
    """

    def __init__(
        self,
        llm: LLM,
        faithfulness_threshold: float = 0.7,
        relevancy_threshold: float = 0.6,
    ):
        self.llm = llm
        self.faithfulness_threshold = faithfulness_threshold
        self.relevancy_threshold = relevancy_threshold

    async def evaluate(
        self,
        query: str,
        response: str,
        contexts: list[str],
    ) -> RAGASScore:
        """Run full RAGAS evaluation.

        Args:
            query: User's original query
            response: Generated response to evaluate
            contexts: Source contexts used for generation

        Returns:
            RAGASScore with all metrics
        """
        # Run evaluations in parallel
        faithfulness_task = self._evaluate_faithfulness(
            response, "\n\n".join(contexts)
        )
        relevancy_task = self._evaluate_relevancy(query, response)

        faithfulness_result, relevancy_result = await asyncio.gather(
            faithfulness_task, relevancy_task
        )

        # Calculate context precision (simple heuristic)
        context_precision = self._calculate_context_precision(
            query, contexts
        )

        # Combine into groundedness score
        groundedness = (faithfulness_result["score"] * 0.6 +
                       context_precision * 0.4)

        return RAGASScore(
            faithfulness=faithfulness_result["score"],
            answer_relevancy=relevancy_result["score"],
            context_precision=context_precision,
            groundedness=groundedness,
            claims_analyzed=faithfulness_result.get("total", 0),
            claims_supported=faithfulness_result.get("supported", 0),
            claims_contradicted=faithfulness_result.get("contradicted", 0),
        )

    async def _evaluate_faithfulness(
        self, response: str, context: str
    ) -> dict[str, Any]:
        """Evaluate faithfulness to source context."""
        prompt = FAITHFULNESS_PROMPT.format(
            context=context[:8000],  # Truncate for token limits
            response=response,
        )

        try:
            result = await self.llm.ask(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )

            import json
            parsed = json.loads(result.get("content", "{}"))

            claims = parsed.get("claims", [])
            supported = sum(1 for c in claims if c.get("status") == "SUPPORTED")
            contradicted = sum(1 for c in claims if c.get("status") == "CONTRADICTED")

            return {
                "score": parsed.get("faithfulness_score", 0.5),
                "total": len(claims),
                "supported": supported,
                "contradicted": contradicted,
            }
        except Exception as e:
            logger.warning(f"Faithfulness evaluation failed: {e}")
            return {"score": 0.5, "total": 0, "supported": 0, "contradicted": 0}

    async def _evaluate_relevancy(
        self, query: str, response: str
    ) -> dict[str, Any]:
        """Evaluate response relevancy to query."""
        prompt = RELEVANCY_PROMPT.format(
            query=query,
            response=response[:4000],
        )

        try:
            result = await self.llm.ask(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )

            import json
            parsed = json.loads(result.get("content", "{}"))

            return {
                "score": parsed.get("relevancy_score", 0.5),
                "addresses_query": parsed.get("addresses_query", False),
            }
        except Exception as e:
            logger.warning(f"Relevancy evaluation failed: {e}")
            return {"score": 0.5, "addresses_query": False}

    def _calculate_context_precision(
        self, query: str, contexts: list[str]
    ) -> float:
        """Simple context precision using keyword overlap."""
        if not contexts:
            return 0.0

        query_words = set(query.lower().split())

        relevant_count = 0
        for ctx in contexts:
            ctx_words = set(ctx.lower().split())
            overlap = len(query_words & ctx_words)
            if overlap >= 2:  # At least 2 words overlap
                relevant_count += 1

        return relevant_count / len(contexts)
```

---

## Phase 3: Enhanced Critic with Generator-Critic Pattern

### Research Foundation
From Google Cloud Architecture Guide:
> *"The review and critique pattern improves the quality and reliability of generated content by using two specialized agents... the critic evaluates against predefined criteria such as factual accuracy, adherence to formatting rules, or safety guidelines."*

### Enhanced Critic Prompt

Update `backend/app/domain/services/prompts/critic.py`:

```python
ENHANCED_CRITIC_SYSTEM_PROMPT = """
You are a specialized Critic Agent responsible for quality assurance.
Your role is to evaluate outputs BEFORE they reach users.

## Evaluation Framework

### 1. FAITHFULNESS CHECK
- Are all claims grounded in the provided sources?
- Are there any fabricated statistics, dates, or facts?
- Are engagement metrics (likes, views, shares) verified from sources?

### 2. DATA CONSISTENCY CHECK (for comparisons)
- Do all compared items have the SAME attributes?
- Are metrics consistent (all quantitative OR explicitly marked unavailable)?
- Is there asymmetry like "Model A: 92%" vs "Model B: strong"?

### 3. TEMPORAL VALIDITY CHECK
- Are all dates in the past or present (not future)?
- Are product versions currently available?
- Are benchmark scores for existing (not announced) products?

### 4. SOURCE GROUNDING CHECK
- Do citations match the claims?
- Are specific numbers traceable to sources?
- Are there unsourced quantitative claims?

### 5. LOGICAL CONSISTENCY CHECK
- Does the conclusion follow from the evidence?
- Are there contradictions between sections?
- Does the comparison table match the narrative?

## Response Format
Always respond with JSON:
{
    "verdict": "approve" | "revise" | "reject",
    "confidence": 0.0-1.0,
    "checks": {
        "faithfulness": {"score": 0.0-1.0, "issues": []},
        "data_consistency": {"score": 0.0-1.0, "issues": []},
        "temporal_validity": {"score": 0.0-1.0, "issues": []},
        "source_grounding": {"score": 0.0-1.0, "issues": []},
        "logical_consistency": {"score": 0.0-1.0, "issues": []}
    },
    "critical_issues": ["List of must-fix issues"],
    "suggestions": ["List of improvements"],
    "summary": "Brief explanation"
}

## Verdicts
- APPROVE: All checks pass with scores >= 0.7
- REVISE: One or more checks fail but fixable (scores 0.4-0.7)
- REJECT: Critical issues found (any score < 0.4 or hallucination detected)
"""

RESEARCH_CRITIC_PROMPT = """
You are reviewing a RESEARCH REPORT. Apply strict evaluation:

## Additional Research-Specific Checks

### Data Parity Rule
Every entity in a comparison MUST have:
- Same attributes evaluated
- Same metric types (all numbers OR "[Not disclosed]")
- No mixing of quantitative and qualitative descriptions

VIOLATION EXAMPLE:
- "Claude: 92% on MMLU" vs "Kimi: Strong reasoning capabilities"
This is UNACCEPTABLE asymmetry.

CORRECT EXAMPLE:
- "Claude: 92% on MMLU" vs "Kimi: MMLU score not publicly disclosed"

### Citation Verification
- Every specific number MUST have a citation
- Every benchmark score MUST be traceable
- Engagement metrics are HIGH RISK for hallucination

### Temporal Grounding
Current date: {current_date}
- Flag any reference to future years as facts
- Flag any unreleased product versions
- Flag any "2026" or later references as potentially hallucinated

---

User Request: {user_request}
Sources Used: {sources}

OUTPUT TO EVALUATE:
{output}
"""
```

---

## Phase 4: Plan-Act-Check-Refine (PACR) Loop

### Research Foundation
From industry best practices:
> *"Agentic approaches turn brittle 'prompt and pray' flows into agentic design patterns with explicit control, memory, and correction."*

Core building blocks:
1. **Planner**: Breaks goals into steps
2. **Executor**: Calls tools and APIs
3. **Checker/Verifier**: Evaluates outputs against rules
4. **Memory**: Stores intermediate results
5. **Escalation Handler**: Decides retry/adjust/human

### Implementation

Create `backend/app/domain/services/flows/pacr_loop.py`:

```python
"""Plan-Act-Check-Refine (PACR) Loop Implementation.

Based on agentic design patterns for self-correcting workflows.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable
import logging

logger = logging.getLogger(__name__)


class CheckResult(str, Enum):
    """Result of a check operation."""
    PASS = "pass"
    FAIL_RETRY = "fail_retry"  # Retry with same approach
    FAIL_REFINE = "fail_refine"  # Retry with different approach
    FAIL_ESCALATE = "fail_escalate"  # Needs human intervention


@dataclass
class PACRState:
    """State maintained across PACR iterations."""
    step_index: int = 0
    attempt: int = 1
    max_attempts: int = 3

    # Results from each phase
    plan: list[str] = field(default_factory=list)
    action_result: Any = None
    check_result: CheckResult = CheckResult.PASS
    check_feedback: str = ""

    # Memory of past attempts
    attempt_history: list[dict] = field(default_factory=list)

    @property
    def should_continue(self) -> bool:
        """Check if we should continue the loop."""
        return (
            self.check_result != CheckResult.PASS and
            self.check_result != CheckResult.FAIL_ESCALATE and
            self.attempt < self.max_attempts
        )


class PACRLoop:
    """Implements Plan-Act-Check-Refine loop for self-correction.

    Usage:
        loop = PACRLoop(
            planner=plan_function,
            actor=act_function,
            checker=check_function,
            refiner=refine_function,
        )

        result = await loop.run(
            goal="Generate a comparison report",
            context={"sources": [...]}
        )
    """

    def __init__(
        self,
        planner: Callable[[str, dict], Awaitable[list[str]]],
        actor: Callable[[str, dict], Awaitable[Any]],
        checker: Callable[[Any, dict], Awaitable[tuple[CheckResult, str]]],
        refiner: Callable[[Any, str, dict], Awaitable[Any]],
        max_attempts: int = 3,
    ):
        self.planner = planner
        self.actor = actor
        self.checker = checker
        self.refiner = refiner
        self.max_attempts = max_attempts

    async def run(
        self,
        goal: str,
        context: dict[str, Any],
    ) -> tuple[Any, PACRState]:
        """Run the PACR loop until success or max attempts.

        Args:
            goal: High-level goal to achieve
            context: Context including sources, constraints, etc.

        Returns:
            Tuple of (final_result, final_state)
        """
        state = PACRState(max_attempts=self.max_attempts)

        # Step 1: PLAN
        logger.info(f"PACR: Planning for goal: {goal[:100]}...")
        state.plan = await self.planner(goal, context)
        logger.info(f"PACR: Created plan with {len(state.plan)} steps")

        # Execute each step with check-refine loop
        for step_idx, step in enumerate(state.plan):
            state.step_index = step_idx
            state.attempt = 1

            while True:
                # Step 2: ACT
                logger.info(f"PACR: Executing step {step_idx+1} (attempt {state.attempt})")
                state.action_result = await self.actor(step, context)

                # Step 3: CHECK
                state.check_result, state.check_feedback = await self.checker(
                    state.action_result, context
                )
                logger.info(f"PACR: Check result: {state.check_result.value}")

                # Record attempt
                state.attempt_history.append({
                    "step": step_idx,
                    "attempt": state.attempt,
                    "result": state.check_result.value,
                    "feedback": state.check_feedback,
                })

                if state.check_result == CheckResult.PASS:
                    break

                if not state.should_continue:
                    if state.check_result == CheckResult.FAIL_ESCALATE:
                        logger.warning("PACR: Escalating to human intervention")
                    else:
                        logger.warning(f"PACR: Max attempts reached for step {step_idx+1}")
                    break

                # Step 4: REFINE
                logger.info(f"PACR: Refining based on feedback...")
                state.action_result = await self.refiner(
                    state.action_result,
                    state.check_feedback,
                    context,
                )
                state.attempt += 1

            # Update context with step result for next step
            context["previous_results"] = context.get("previous_results", [])
            context["previous_results"].append(state.action_result)

        return state.action_result, state
```

---

## Phase 5: Anthropic-Style Grounding Prompts

### Research Foundation
From Anthropic Claude 4.x Best Practices:
> *"Claude 4.x models are less prone to hallucinations... use the `<investigate_before_answering>` tag to instruct the model to never speculate about code it has not opened."*

### Enhanced Prompt Templates

Update `backend/app/domain/services/prompts/execution.py`:

```python
# Anthropic-recommended grounding tag
INVESTIGATE_BEFORE_ANSWERING = """
<investigate_before_answering>
Never speculate about information you have not verified. If the user references
a specific source, you MUST read or search for it before answering.

Make sure to investigate and verify facts BEFORE making claims.
Never make any claims about specific numbers, dates, or metrics before
investigating unless you are certain of the correct answer.

Give grounded and hallucination-free answers.
</investigate_before_answering>
"""

# Chain-of-Verification trigger for research tasks
COVE_TRIGGER = """
<self_verification>
After generating your response, you must verify your key claims:

1. For each specific statistic or number:
   - Ask: "Can I verify this from my sources?"
   - If NO: Remove the claim or mark as "[Unverified]"

2. For each comparison:
   - Ask: "Am I using the same metrics for all items?"
   - If NO: Standardize or explicitly note "[Data unavailable]"

3. For each date or version:
   - Ask: "Is this in the past/present, not future?"
   - If FUTURE: Remove or mark as "[Projected]"

Apply these checks before delivering your response.
</self_verification>
"""

# Data consistency enforcement for comparisons
COMPARISON_CONSISTENCY = """
<comparison_standards>
When comparing multiple items:

1. ATTRIBUTE PARITY: Every item MUST have identical attributes.
   If data unavailable: Use "[Not publicly disclosed]" or "[N/A]"

2. METRIC CONSISTENCY: Never mix types.
   BAD: "Model A: 92%" vs "Model B: Strong performance"
   GOOD: "Model A: 92%" vs "Model B: [Score not published]"

3. TABLE STRUCTURE: Every cell must be same type across rows.
   | Metric   | A    | B    | C       |
   |----------|------|------|---------|
   | MMLU     | 92%  | 89%  | [N/A]   |  <- Acceptable
   | MMLU     | 92%  | Good | Strong  |  <- UNACCEPTABLE

4. CITATION REQUIREMENT: Every specific number needs a source.
</comparison_standards>
"""

# Temporal grounding
TEMPORAL_GROUNDING = """
<temporal_awareness>
Current date: {current_date}

CRITICAL RULES:
- Do NOT reference future years as if they have passed
- Do NOT cite benchmarks for unreleased model versions
- Do NOT present speculation as fact
- If discussing future: Explicitly mark as "[Projected]" or "[Announced]"

Products that do NOT exist yet (as of {current_date}):
- GPT-5, GPT-6
- Claude 4, Claude 5
- Gemini 3.0+
- Any model announced but not released

If you mention these, you MUST clarify they are unreleased.
</temporal_awareness>
"""
```

---

## Phase 6: Self-Consistency Checking

### Research Foundation
From Wang et al. (2022):
> *"Self-consistency generates many chains of thought and chooses the most common result. This method boosted accuracy on math and commonsense benchmarks by statistically canceling out hallucinations."*

### Implementation

Create `backend/app/domain/services/agents/self_consistency.py`:

```python
"""Self-Consistency Checking for Hallucination Reduction.

Based on Wang et al. (2022) - generates multiple responses and
votes on the most consistent answer.
"""

from collections import Counter
from dataclasses import dataclass
import asyncio
import logging

from app.domain.external.llm import LLM

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyResult:
    """Result of self-consistency check."""
    best_response: str
    consistency_score: float  # 0-1: How consistent were responses
    num_samples: int
    agreement_count: int
    divergent_claims: list[str]


class SelfConsistencyChecker:
    """Implements self-consistency checking via multiple generations.

    Usage:
        checker = SelfConsistencyChecker(llm, num_samples=3)
        result = await checker.generate_consistent(
            prompt="What is the capital of France?",
            extract_answer=lambda r: r.split(":")[0]
        )
    """

    def __init__(
        self,
        llm: LLM,
        num_samples: int = 3,
        temperature: float = 0.7,
    ):
        self.llm = llm
        self.num_samples = num_samples
        self.temperature = temperature

    async def generate_consistent(
        self,
        messages: list[dict],
        extract_key_claims: callable = None,
    ) -> ConsistencyResult:
        """Generate multiple responses and return most consistent.

        Args:
            messages: Prompt messages
            extract_key_claims: Function to extract comparable claims

        Returns:
            ConsistencyResult with best response
        """
        # Generate multiple samples in parallel
        tasks = [
            self._generate_sample(messages)
            for _ in range(self.num_samples)
        ]
        responses = await asyncio.gather(*tasks)
        responses = [r for r in responses if r]  # Filter failures

        if not responses:
            return ConsistencyResult(
                best_response="",
                consistency_score=0.0,
                num_samples=0,
                agreement_count=0,
                divergent_claims=[],
            )

        if len(responses) == 1:
            return ConsistencyResult(
                best_response=responses[0],
                consistency_score=1.0,
                num_samples=1,
                agreement_count=1,
                divergent_claims=[],
            )

        # Extract key claims from each response
        if extract_key_claims:
            claims_per_response = [
                set(extract_key_claims(r)) for r in responses
            ]
        else:
            claims_per_response = [
                set(self._extract_facts(r)) for r in responses
            ]

        # Find consensus claims (appear in majority)
        all_claims = [c for claims in claims_per_response for c in claims]
        claim_counts = Counter(all_claims)
        majority_threshold = len(responses) / 2

        consensus_claims = {
            c for c, count in claim_counts.items()
            if count > majority_threshold
        }

        # Score each response by consensus alignment
        scores = []
        for i, claims in enumerate(claims_per_response):
            if not claims:
                scores.append(0)
            else:
                agreement = len(claims & consensus_claims) / len(claims)
                scores.append(agreement)

        # Select best response
        best_idx = scores.index(max(scores))
        best_response = responses[best_idx]

        # Find divergent claims (low agreement)
        divergent = [
            c for c, count in claim_counts.items()
            if count == 1  # Only appeared once
        ]

        consistency = sum(scores) / len(scores)

        logger.info(
            f"Self-consistency: {len(consensus_claims)} consensus claims, "
            f"{len(divergent)} divergent, score={consistency:.2f}"
        )

        return ConsistencyResult(
            best_response=best_response,
            consistency_score=consistency,
            num_samples=len(responses),
            agreement_count=len(consensus_claims),
            divergent_claims=divergent[:5],  # Top 5 divergent
        )

    async def _generate_sample(self, messages: list[dict]) -> str | None:
        """Generate a single sample."""
        try:
            result = await self.llm.ask(
                messages=messages,
                temperature=self.temperature,
            )
            return result.get("content", "")
        except Exception as e:
            logger.warning(f"Sample generation failed: {e}")
            return None

    def _extract_facts(self, text: str) -> list[str]:
        """Extract factual claims from text."""
        import re

        facts = []

        # Extract sentences with numbers
        number_pattern = r'[^.]*\d+[^.]*\.'
        facts.extend(re.findall(number_pattern, text))

        # Extract sentences with specific patterns
        patterns = [
            r'[^.]*is[^.]*\.',  # "X is Y" statements
            r'[^.]*was[^.]*\.',  # "X was Y" statements
            r'[^.]*has[^.]*\.',  # "X has Y" statements
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            facts.extend(matches[:5])  # Limit per pattern

        return list(set(facts))[:20]  # Dedupe and limit
```

---

## Phase 7: Error Recovery with Learning

### Research Foundation
From industry best practices:
> *"Agent performance should be verified at each step. Building monitoring and evaluation into the workflow enables teams to catch mistakes early, refine logic, and continually improve performance."*

Key strategies:
1. **Graceful Degradation**: Fallback mechanisms
2. **Retry with Exponential Backoff**: Handle transient failures
3. **Error Visibility for Self-Correction**: Detailed error messages
4. **Checkpointing**: Resume from last good state

### Enhanced Error Handler

Update `backend/app/domain/services/agents/error_handler.py`:

```python
# Add to existing ErrorHandler class

class LearningErrorHandler(ErrorHandler):
    """Error handler that learns from recovery outcomes."""

    def __init__(self, *args, persistence_path: str = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.persistence_path = persistence_path
        self._outcome_history: list[dict] = []
        self._strategy_scores: dict[str, dict] = {}  # error_type -> strategy -> score

        if persistence_path:
            self._load_history()

    async def handle_with_learning(
        self,
        operation: callable,
        error_type: ErrorType,
        context: dict = None,
    ) -> tuple[Any, bool]:
        """Handle operation with learning from outcomes.

        Returns:
            Tuple of (result, success)
        """
        strategy = self._select_best_strategy(error_type)
        start_time = time.time()

        try:
            result = await self.handle_with_retry(
                operation,
                error_type=error_type,
                context=context,
                strategy=strategy,
            )

            # Record success
            self._record_outcome(
                error_type=error_type,
                strategy=strategy,
                success=True,
                duration=time.time() - start_time,
            )

            return result, True

        except Exception as e:
            # Record failure
            self._record_outcome(
                error_type=error_type,
                strategy=strategy,
                success=False,
                duration=time.time() - start_time,
                error=str(e),
            )

            return None, False

    def _select_best_strategy(self, error_type: ErrorType) -> str:
        """Select best strategy based on historical success."""
        scores = self._strategy_scores.get(error_type.value, {})

        if not scores:
            return "default"

        # Select strategy with highest success rate (min 3 attempts)
        viable = {
            s: data for s, data in scores.items()
            if data.get("attempts", 0) >= 3
        }

        if not viable:
            return "default"

        best = max(viable, key=lambda s: viable[s].get("success_rate", 0))
        return best

    def _record_outcome(
        self,
        error_type: ErrorType,
        strategy: str,
        success: bool,
        duration: float,
        error: str = None,
    ):
        """Record outcome for learning."""
        outcome = {
            "error_type": error_type.value,
            "strategy": strategy,
            "success": success,
            "duration": duration,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        }

        self._outcome_history.append(outcome)

        # Update strategy scores
        if error_type.value not in self._strategy_scores:
            self._strategy_scores[error_type.value] = {}

        if strategy not in self._strategy_scores[error_type.value]:
            self._strategy_scores[error_type.value][strategy] = {
                "attempts": 0,
                "successes": 0,
                "avg_duration": 0,
            }

        stats = self._strategy_scores[error_type.value][strategy]
        stats["attempts"] += 1
        if success:
            stats["successes"] += 1
        stats["success_rate"] = stats["successes"] / stats["attempts"]
        stats["avg_duration"] = (
            (stats["avg_duration"] * (stats["attempts"] - 1) + duration)
            / stats["attempts"]
        )

        # Persist periodically
        if len(self._outcome_history) % 10 == 0:
            self._save_history()

    def get_proactive_guidance(self, error_type: ErrorType) -> str:
        """Get proactive guidance based on learned patterns."""
        best = self._select_best_strategy(error_type)
        scores = self._strategy_scores.get(error_type.value, {})

        if not scores:
            return ""

        lines = []

        if best != "default" and best in scores:
            rate = scores[best].get("success_rate", 0)
            lines.append(f"Recommended: '{best}' strategy ({rate:.0%} success rate)")

        # Warn about poor strategies
        poor = [
            s for s, data in scores.items()
            if data.get("attempts", 0) >= 3 and data.get("success_rate", 0) < 0.3
        ]

        for s in poor[:2]:
            rate = scores[s].get("success_rate", 0)
            lines.append(f"Avoid: '{s}' has low success rate ({rate:.0%})")

        return "\n".join(lines)
```

---

## Implementation Roadmap

### Week 1: Foundation (HIGH PRIORITY)
- [ ] Implement Chain-of-Verification (`chain_of_verification.py`)
- [ ] Add enhanced critic prompts with 5-check framework
- [ ] Integrate `<investigate_before_answering>` tags
- [ ] Add temporal grounding prompt

### Week 2: Evaluation Pipeline
- [ ] Implement RAGAS-style evaluator
- [ ] Add faithfulness and relevancy checks
- [ ] Integrate with CriticAgent
- [ ] Add metrics tracking

### Week 3: Self-Correction Loops
- [ ] Implement PACR loop
- [ ] Add self-consistency checking
- [ ] Integrate with execution flow
- [ ] Add checkpointing

### Week 4: Learning & Optimization
- [ ] Implement learning error handler
- [ ] Add outcome persistence
- [ ] Deploy monitoring dashboards
- [ ] Performance optimization

---

## Metrics Dashboard

Track these metrics in Prometheus/Grafana:

```yaml
# Hallucination metrics
- pythinker_hallucination_rate
- pythinker_cove_corrections_total
- pythinker_claims_verified_total
- pythinker_claims_contradicted_total

# Quality metrics
- pythinker_faithfulness_score
- pythinker_relevancy_score
- pythinker_groundedness_score
- pythinker_ragas_overall_score

# Error recovery metrics
- pythinker_error_recovery_success_rate
- pythinker_strategy_success_rate{strategy, error_type}
- pythinker_revision_count_total
- pythinker_escalation_count_total

# Performance metrics
- pythinker_cove_latency_seconds
- pythinker_critic_latency_seconds
- pythinker_total_llm_calls_per_task
```

---

## Expected Outcomes

Based on research benchmarks:

| Enhancement | Expected Improvement | Source |
|-------------|---------------------|--------|
| Chain-of-Verification | 50%+ reduction in hallucinations | Meta AI 2023 |
| RAG + Guardrails + RLHF | 96% reduction combined | Stanford 2024 |
| Self-Consistency | 10-20% accuracy boost | Wang et al. 2022 |
| RAGAS Faithfulness | >0.9 score achievable | Industry benchmark |
| Learning Error Handler | 47% fewer critical failures | Microsoft Research |

---

## References

1. **Chain-of-Verification**: Dhuliawala et al., Meta AI (2023)
2. **Self-Consistency**: Wang et al. (2022)
3. **RAGAS Framework**: https://docs.ragas.io
4. **FACTS Grounding**: Google DeepMind (2024)
5. **Anthropic Best Practices**: Claude 4.x Documentation
6. **LangChain Patterns**: https://docs.langchain.com
7. **Google Agentic Patterns**: cloud.google.com/architecture
8. **Morphik Hallucination Guide**: morphik.ai/blog (2025)
