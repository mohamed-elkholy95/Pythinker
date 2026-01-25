# Testing and Evaluation Framework

**Date:** January 24, 2026
**Project:** Pythinker AI Agent System
**Version:** 1.0

---

## Executive Summary

This document establishes a comprehensive benchmark suite for quantitatively evaluating Pythinker agent performance before and after optimization. It defines success criteria, testing methodologies, and metrics for measuring response speed, accuracy, hallucination rates, and task completion.

---

## Table of Contents

1. [Evaluation Dimensions](#1-evaluation-dimensions)
2. [Benchmark Suite Design](#2-benchmark-suite-design)
3. [Performance Metrics](#3-performance-metrics)
4. [Accuracy and Quality Metrics](#4-accuracy-and-quality-metrics)
5. [Hallucination Detection Metrics](#5-hallucination-detection-metrics)
6. [A/B Testing Methodology](#6-ab-testing-methodology)
7. [Success Criteria](#7-success-criteria)
8. [Implementation Guide](#8-implementation-guide)

---

## 1. Evaluation Dimensions

### 1.1 The CLASSIC Framework

| Dimension | What It Measures | Key Metrics |
|-----------|-----------------|-------------|
| **C**ost | Resource consumption | Tokens used, API costs, compute time |
| **L**atency | Response speed | TTFT, TTLT, p50/p95/p99 |
| **A**ccuracy | Correctness | Task completion, factual accuracy |
| **S**tability | Consistency | Variance across runs, reproducibility |
| **S**ecurity | Safety | Policy violations, data leaks |
| **I**ntelligence | Reasoning quality | Plan quality, tool selection |
| **C**ompleteness | Task coverage | Full vs partial completion |

### 1.2 Agent-Specific Dimensions

| Dimension | Description |
|-----------|-------------|
| **Goal Completion Rate** | End-to-end multi-step task success |
| **Tool Usage Efficiency** | Correct tool selection and execution |
| **Memory & Recall** | Remembering earlier context |
| **Adaptability** | Recovery from errors and edge cases |
| **Iteration Efficiency** | Steps required to complete task |

---

## 2. Benchmark Suite Design

### 2.1 Task Categories

```python
# backend/tests/benchmarks/task_categories.py

from enum import Enum
from dataclasses import dataclass
from typing import List, Optional

class TaskCategory(Enum):
    RESEARCH = "research"           # Web search, information gathering
    FILE_OPERATIONS = "file_ops"    # Read, write, analyze files
    CODE_GENERATION = "code_gen"    # Write and modify code
    DATA_ANALYSIS = "data_analysis" # Process and analyze data
    MULTI_STEP = "multi_step"       # Complex multi-tool workflows
    CONVERSATIONAL = "conversational" # Q&A, clarification

@dataclass
class BenchmarkTask:
    id: str
    name: str
    category: TaskCategory
    description: str
    expected_tools: List[str]
    expected_steps: int
    timeout_seconds: int
    ground_truth: Optional[str] = None
    success_criteria: Optional[str] = None
```

### 2.2 Standard Benchmark Tasks

```python
# backend/tests/benchmarks/standard_tasks.py

BENCHMARK_TASKS = [
    # Research Tasks
    BenchmarkTask(
        id="research_001",
        name="Product Comparison",
        category=TaskCategory.RESEARCH,
        description="Compare the top 3 Python web frameworks (Django, Flask, FastAPI) in terms of performance, ease of use, and community support.",
        expected_tools=["info_search_web", "browser_view"],
        expected_steps=5,
        timeout_seconds=120,
        success_criteria="Must cite at least 3 sources, include performance benchmarks, and provide a recommendation."
    ),

    BenchmarkTask(
        id="research_002",
        name="Current Events Summary",
        category=TaskCategory.RESEARCH,
        description="Find the latest news about AI regulation in the EU and summarize the key points.",
        expected_tools=["info_search_web"],
        expected_steps=3,
        timeout_seconds=60,
        success_criteria="Must include dates, specific regulations mentioned, and sources from last 30 days."
    ),

    # File Operations Tasks
    BenchmarkTask(
        id="file_001",
        name="Log Analysis",
        category=TaskCategory.FILE_OPERATIONS,
        description="Analyze the provided log file and identify the top 5 most frequent error types.",
        expected_tools=["file_read", "shell_exec"],
        expected_steps=3,
        timeout_seconds=60,
        ground_truth="error_types.json"  # Reference file for validation
    ),

    BenchmarkTask(
        id="file_002",
        name="Config Update",
        category=TaskCategory.FILE_OPERATIONS,
        description="Update the database connection string in config.yaml from localhost to production server.",
        expected_tools=["file_read", "file_write"],
        expected_steps=2,
        timeout_seconds=30,
    ),

    # Code Generation Tasks
    BenchmarkTask(
        id="code_001",
        name="Function Implementation",
        category=TaskCategory.CODE_GENERATION,
        description="Write a Python function that validates email addresses using regex.",
        expected_tools=["file_write"],
        expected_steps=2,
        timeout_seconds=60,
        success_criteria="Function must pass all test cases in test_email_validator.py"
    ),

    # Multi-Step Tasks
    BenchmarkTask(
        id="multi_001",
        name="API Integration",
        category=TaskCategory.MULTI_STEP,
        description="Fetch data from the weather API, save to a JSON file, and generate a summary report.",
        expected_tools=["browser_view", "file_write", "shell_exec"],
        expected_steps=5,
        timeout_seconds=180,
    ),

    BenchmarkTask(
        id="multi_002",
        name="Codebase Analysis",
        category=TaskCategory.MULTI_STEP,
        description="Analyze the project structure, identify the main entry point, and document the API endpoints.",
        expected_tools=["file_read", "file_search", "shell_exec"],
        expected_steps=6,
        timeout_seconds=240,
    ),
]
```

### 2.3 Benchmark Runner

```python
# backend/tests/benchmarks/runner.py

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any
from datetime import datetime

@dataclass
class BenchmarkResult:
    task_id: str
    success: bool
    duration_seconds: float
    tokens_used: int
    iterations: int
    tools_used: List[str]
    errors: List[str]
    ttft_ms: float  # Time to first token
    ttlt_ms: float  # Time to last token
    memory_peak_tokens: int
    output: str
    metadata: Dict[str, Any] = field(default_factory=dict)

class BenchmarkRunner:
    def __init__(self, agent_factory, config: BenchmarkConfig):
        self.agent_factory = agent_factory
        self.config = config
        self.results: List[BenchmarkResult] = []

    async def run_suite(self, tasks: List[BenchmarkTask]) -> List[BenchmarkResult]:
        """Run all benchmark tasks."""
        results = []

        for task in tasks:
            print(f"Running benchmark: {task.name}")

            # Run multiple times for statistical significance
            task_results = []
            for run in range(self.config.runs_per_task):
                result = await self.run_single(task)
                task_results.append(result)
                await asyncio.sleep(1)  # Avoid rate limiting

            # Aggregate results
            aggregated = self._aggregate_results(task.id, task_results)
            results.append(aggregated)

        self.results = results
        return results

    async def run_single(self, task: BenchmarkTask) -> BenchmarkResult:
        """Run a single benchmark task."""
        agent = self.agent_factory.create()

        start_time = time.perf_counter()
        ttft = None
        tokens_used = 0
        iterations = 0
        tools_used = []
        errors = []
        output = ""

        try:
            async for event in agent.execute(task.description):
                if ttft is None:
                    ttft = (time.perf_counter() - start_time) * 1000

                if event.type == "tool_call":
                    tools_used.append(event.data.get("tool_name"))
                    iterations += 1
                elif event.type == "error":
                    errors.append(event.data.get("message"))
                elif event.type == "complete":
                    output = event.data.get("result", "")
                    tokens_used = event.data.get("tokens_used", 0)

        except asyncio.TimeoutError:
            errors.append("Timeout exceeded")

        end_time = time.perf_counter()
        duration = end_time - start_time

        success = self._evaluate_success(task, output, errors)

        return BenchmarkResult(
            task_id=task.id,
            success=success,
            duration_seconds=duration,
            tokens_used=tokens_used,
            iterations=iterations,
            tools_used=tools_used,
            errors=errors,
            ttft_ms=ttft or 0,
            ttlt_ms=duration * 1000,
            memory_peak_tokens=agent.memory.get_token_count(),
            output=output
        )

    def _evaluate_success(self, task: BenchmarkTask, output: str, errors: List[str]) -> bool:
        """Evaluate if task completed successfully."""
        if errors:
            return False

        if task.ground_truth:
            return self._compare_to_ground_truth(output, task.ground_truth)

        if task.success_criteria:
            return self._evaluate_criteria(output, task.success_criteria)

        return len(output) > 50  # Basic completion check

    def _aggregate_results(self, task_id: str, results: List[BenchmarkResult]) -> BenchmarkResult:
        """Aggregate multiple runs into single result."""
        return BenchmarkResult(
            task_id=task_id,
            success=sum(r.success for r in results) / len(results) >= 0.8,
            duration_seconds=sum(r.duration_seconds for r in results) / len(results),
            tokens_used=sum(r.tokens_used for r in results) // len(results),
            iterations=sum(r.iterations for r in results) // len(results),
            tools_used=results[0].tools_used,  # Use first run
            errors=[e for r in results for e in r.errors],
            ttft_ms=sum(r.ttft_ms for r in results) / len(results),
            ttlt_ms=sum(r.ttlt_ms for r in results) / len(results),
            memory_peak_tokens=max(r.memory_peak_tokens for r in results),
            output=results[0].output,
            metadata={
                "runs": len(results),
                "success_rate": sum(r.success for r in results) / len(results),
                "duration_std": self._std([r.duration_seconds for r in results]),
            }
        )
```

---

## 3. Performance Metrics

### 3.1 Latency Metrics

```python
# backend/tests/benchmarks/metrics/latency.py

from dataclasses import dataclass
from typing import List
import numpy as np

@dataclass
class LatencyMetrics:
    ttft_p50_ms: float      # Time to first token (median)
    ttft_p95_ms: float      # Time to first token (95th percentile)
    ttft_p99_ms: float      # Time to first token (99th percentile)
    ttlt_p50_ms: float      # Time to last token (median)
    ttlt_p95_ms: float
    ttlt_p99_ms: float
    itl_avg_ms: float       # Inter-token latency (average)
    total_duration_avg: float

class LatencyCalculator:
    def calculate(self, results: List[BenchmarkResult]) -> LatencyMetrics:
        """Calculate latency metrics from benchmark results."""
        ttft_values = [r.ttft_ms for r in results if r.ttft_ms > 0]
        ttlt_values = [r.ttlt_ms for r in results]
        durations = [r.duration_seconds for r in results]

        return LatencyMetrics(
            ttft_p50_ms=np.percentile(ttft_values, 50),
            ttft_p95_ms=np.percentile(ttft_values, 95),
            ttft_p99_ms=np.percentile(ttft_values, 99),
            ttlt_p50_ms=np.percentile(ttlt_values, 50),
            ttlt_p95_ms=np.percentile(ttlt_values, 95),
            ttlt_p99_ms=np.percentile(ttlt_values, 99),
            itl_avg_ms=self._calculate_itl(results),
            total_duration_avg=np.mean(durations)
        )

    def _calculate_itl(self, results: List[BenchmarkResult]) -> float:
        """Calculate average inter-token latency."""
        # Approximation: total_time / estimated_tokens
        total_time = sum(r.ttlt_ms for r in results)
        total_tokens = sum(r.tokens_used for r in results)
        if total_tokens == 0:
            return 0
        return total_time / total_tokens
```

### 3.2 Throughput Metrics

```python
# backend/tests/benchmarks/metrics/throughput.py

@dataclass
class ThroughputMetrics:
    tokens_per_second: float
    requests_per_minute: float
    tasks_per_hour: float
    concurrent_capacity: int

class ThroughputCalculator:
    def calculate(self, results: List[BenchmarkResult], duration_seconds: float) -> ThroughputMetrics:
        """Calculate throughput metrics."""
        total_tokens = sum(r.tokens_used for r in results)
        total_tasks = len(results)

        return ThroughputMetrics(
            tokens_per_second=total_tokens / duration_seconds,
            requests_per_minute=(total_tasks / duration_seconds) * 60,
            tasks_per_hour=(total_tasks / duration_seconds) * 3600,
            concurrent_capacity=self._estimate_concurrency(results)
        )
```

### 3.3 Cost Metrics

```python
# backend/tests/benchmarks/metrics/cost.py

@dataclass
class CostMetrics:
    tokens_input_total: int
    tokens_output_total: int
    tokens_cached: int
    cache_hit_rate: float
    estimated_cost_usd: float
    cost_per_task_usd: float

class CostCalculator:
    # Pricing per 1M tokens (example rates)
    INPUT_COST_PER_M = 3.00   # $3/million input tokens
    OUTPUT_COST_PER_M = 15.00  # $15/million output tokens
    CACHED_COST_PER_M = 0.30   # $0.30/million cached tokens

    def calculate(self, results: List[BenchmarkResult], cache_stats: Dict) -> CostMetrics:
        """Calculate cost metrics."""
        total_input = sum(r.metadata.get('input_tokens', 0) for r in results)
        total_output = sum(r.tokens_used for r in results)
        total_cached = cache_stats.get('tokens_cached', 0)

        cache_hit_rate = total_cached / max(total_input, 1)

        cost = (
            (total_input - total_cached) * self.INPUT_COST_PER_M / 1_000_000 +
            total_cached * self.CACHED_COST_PER_M / 1_000_000 +
            total_output * self.OUTPUT_COST_PER_M / 1_000_000
        )

        return CostMetrics(
            tokens_input_total=total_input,
            tokens_output_total=total_output,
            tokens_cached=total_cached,
            cache_hit_rate=cache_hit_rate,
            estimated_cost_usd=cost,
            cost_per_task_usd=cost / max(len(results), 1)
        )
```

---

## 4. Accuracy and Quality Metrics

### 4.1 Task Completion Metrics

```python
# backend/tests/benchmarks/metrics/accuracy.py

@dataclass
class AccuracyMetrics:
    task_completion_rate: float      # % of tasks fully completed
    partial_completion_rate: float   # % of tasks partially completed
    failure_rate: float              # % of tasks that failed
    first_pass_success_rate: float   # % successful without retries
    average_iterations: float        # Average tool calls per task
    tool_selection_accuracy: float   # % correct tool selections

class AccuracyCalculator:
    def calculate(self, results: List[BenchmarkResult], tasks: List[BenchmarkTask]) -> AccuracyMetrics:
        """Calculate accuracy metrics."""
        task_map = {t.id: t for t in tasks}

        completed = sum(1 for r in results if r.success)
        partial = sum(1 for r in results if not r.success and len(r.output) > 100)
        failed = len(results) - completed - partial

        first_pass = sum(1 for r in results if r.success and r.iterations <= task_map[r.task_id].expected_steps)

        tool_correct = sum(
            len(set(r.tools_used) & set(task_map[r.task_id].expected_tools))
            for r in results
        )
        tool_total = sum(len(r.tools_used) for r in results)

        return AccuracyMetrics(
            task_completion_rate=completed / len(results),
            partial_completion_rate=partial / len(results),
            failure_rate=failed / len(results),
            first_pass_success_rate=first_pass / len(results),
            average_iterations=sum(r.iterations for r in results) / len(results),
            tool_selection_accuracy=tool_correct / max(tool_total, 1)
        )
```

### 4.2 Quality Scoring

```python
# backend/tests/benchmarks/metrics/quality.py

from typing import Optional
import re

@dataclass
class QualityMetrics:
    citation_coverage: float     # % of claims with citations
    source_diversity: float      # Unique sources per response
    formatting_score: float      # Markdown/structure quality
    completeness_score: float    # Coverage of requested information
    coherence_score: float       # Logical flow and consistency

class QualityEvaluator:
    def evaluate(self, result: BenchmarkResult, task: BenchmarkTask) -> QualityMetrics:
        """Evaluate output quality."""
        output = result.output

        # Citation analysis
        citations = re.findall(r'\[(\d+)\]', output)
        claims = self._count_claims(output)
        citation_coverage = len(set(citations)) / max(claims, 1)

        # Source diversity
        source_urls = re.findall(r'https?://[^\s\)]+', output)
        source_diversity = len(set(source_urls))

        # Formatting (presence of headers, lists, code blocks)
        formatting_score = self._score_formatting(output)

        # Completeness (keyword coverage from task description)
        completeness_score = self._score_completeness(output, task.description)

        # Coherence (sentence flow, no contradictions)
        coherence_score = self._score_coherence(output)

        return QualityMetrics(
            citation_coverage=min(citation_coverage, 1.0),
            source_diversity=min(source_diversity / 5, 1.0),  # Normalize to 5 sources
            formatting_score=formatting_score,
            completeness_score=completeness_score,
            coherence_score=coherence_score
        )

    def _count_claims(self, text: str) -> int:
        """Count factual claims in text."""
        # Heuristic: sentences with numbers or definitive statements
        sentences = re.split(r'[.!?]', text)
        claims = [s for s in sentences if re.search(r'\d+|always|never|is|are|was|were|will', s, re.I)]
        return len(claims)

    def _score_formatting(self, text: str) -> float:
        """Score markdown formatting quality."""
        score = 0.0

        if re.search(r'^#+\s', text, re.M):  # Headers
            score += 0.25
        if re.search(r'^\s*[-*]\s', text, re.M):  # Lists
            score += 0.25
        if '```' in text:  # Code blocks
            score += 0.25
        if re.search(r'\*\*.*\*\*', text):  # Bold
            score += 0.125
        if re.search(r'\[.*\]\(.*\)', text):  # Links
            score += 0.125

        return min(score, 1.0)

    def _score_completeness(self, output: str, task_description: str) -> float:
        """Score how completely the output addresses the task."""
        # Extract key terms from task
        task_words = set(re.findall(r'\b\w{4,}\b', task_description.lower()))
        output_words = set(re.findall(r'\b\w{4,}\b', output.lower()))

        overlap = len(task_words & output_words)
        return overlap / max(len(task_words), 1)

    def _score_coherence(self, text: str) -> float:
        """Score logical coherence of text."""
        # Simple heuristic: check for transition words and logical flow
        transitions = ['however', 'therefore', 'additionally', 'furthermore',
                       'in conclusion', 'as a result', 'because', 'thus']
        transition_count = sum(1 for t in transitions if t in text.lower())
        return min(transition_count / 5, 1.0)
```

---

## 5. Hallucination Detection Metrics

### 5.1 Hallucination Rate Measurement

```python
# backend/tests/benchmarks/metrics/hallucination.py

from dataclasses import dataclass
from typing import List, Tuple
import re

@dataclass
class HallucinationMetrics:
    tool_hallucination_rate: float   # % invalid tool calls
    fact_hallucination_rate: float   # % unverifiable claims
    citation_hallucination_rate: float  # % fake/broken citations
    consistency_error_rate: float    # % self-contradictions
    overall_hallucination_score: float

class HallucinationDetector:
    def __init__(self, valid_tools: List[str], fact_checker=None):
        self.valid_tools = set(valid_tools)
        self.fact_checker = fact_checker

    def analyze(self, results: List[BenchmarkResult]) -> HallucinationMetrics:
        """Analyze hallucination rates across results."""

        tool_hallu = self._detect_tool_hallucinations(results)
        fact_hallu = self._detect_fact_hallucinations(results)
        cite_hallu = self._detect_citation_hallucinations(results)
        consist_err = self._detect_consistency_errors(results)

        overall = (
            tool_hallu * 0.3 +
            fact_hallu * 0.3 +
            cite_hallu * 0.2 +
            consist_err * 0.2
        )

        return HallucinationMetrics(
            tool_hallucination_rate=tool_hallu,
            fact_hallucination_rate=fact_hallu,
            citation_hallucination_rate=cite_hallu,
            consistency_error_rate=consist_err,
            overall_hallucination_score=overall
        )

    def _detect_tool_hallucinations(self, results: List[BenchmarkResult]) -> float:
        """Detect invalid tool calls."""
        total_calls = 0
        invalid_calls = 0

        for result in results:
            for tool in result.tools_used:
                total_calls += 1
                if tool not in self.valid_tools:
                    invalid_calls += 1

        return invalid_calls / max(total_calls, 1)

    def _detect_fact_hallucinations(self, results: List[BenchmarkResult]) -> float:
        """Detect unverifiable factual claims."""
        if not self.fact_checker:
            return 0.0  # Skip if no fact checker available

        total_claims = 0
        unverified_claims = 0

        for result in results:
            claims = self._extract_claims(result.output)
            for claim in claims:
                total_claims += 1
                if not self.fact_checker.verify(claim):
                    unverified_claims += 1

        return unverified_claims / max(total_claims, 1)

    def _detect_citation_hallucinations(self, results: List[BenchmarkResult]) -> float:
        """Detect fake or broken citations."""
        total_citations = 0
        broken_citations = 0

        for result in results:
            # Extract citation references and URLs
            citations = re.findall(r'\[(\d+)\]', result.output)
            urls = re.findall(r'https?://[^\s\)]+', result.output)

            # Check if citations have matching sources
            source_section = result.output.split("Sources:")[-1] if "Sources:" in result.output else ""

            for cite_num in set(citations):
                total_citations += 1
                if f"[{cite_num}]" not in source_section and f"{cite_num}." not in source_section:
                    broken_citations += 1

        return broken_citations / max(total_citations, 1)

    def _detect_consistency_errors(self, results: List[BenchmarkResult]) -> float:
        """Detect self-contradictions in outputs."""
        errors = 0
        total = len(results)

        for result in results:
            if self._has_contradiction(result.output):
                errors += 1

        return errors / max(total, 1)

    def _has_contradiction(self, text: str) -> bool:
        """Simple contradiction detection."""
        # Look for patterns like "X is Y" followed by "X is not Y"
        sentences = text.split('.')
        statements = {}

        for sent in sentences:
            # Extract simple "X is Y" patterns
            match = re.search(r'(\w+)\s+is\s+(\w+)', sent, re.I)
            if match:
                subject, predicate = match.groups()
                key = subject.lower()

                if key in statements and statements[key] != predicate.lower():
                    return True
                statements[key] = predicate.lower()

        return False

    def _extract_claims(self, text: str) -> List[str]:
        """Extract factual claims from text."""
        sentences = re.split(r'[.!?]', text)
        claims = [s.strip() for s in sentences
                  if re.search(r'\d+|always|never|is|are|was|were', s, re.I)]
        return claims
```

### 5.2 Hallucination Severity Classification

```python
# backend/tests/benchmarks/metrics/hallucination_severity.py

from enum import Enum

class HallucinationSeverity(Enum):
    CRITICAL = "critical"   # Dangerous misinformation
    MAJOR = "major"         # Significantly incorrect
    MINOR = "minor"         # Small inaccuracies
    COSMETIC = "cosmetic"   # Style/format issues only

@dataclass
class HallucinationInstance:
    text: str
    type: str  # tool, fact, citation, consistency
    severity: HallucinationSeverity
    context: str
    suggested_fix: Optional[str] = None

class HallucinationClassifier:
    def classify(self, hallucination: str, context: str) -> HallucinationSeverity:
        """Classify severity of a hallucination."""
        # Critical: Medical, legal, financial advice that's wrong
        critical_domains = ['health', 'medical', 'legal', 'financial', 'safety']
        if any(domain in context.lower() for domain in critical_domains):
            return HallucinationSeverity.CRITICAL

        # Major: Factual claims about entities
        if re.search(r'(company|person|organization|product)', context, re.I):
            return HallucinationSeverity.MAJOR

        # Minor: Date/number inaccuracies
        if re.search(r'\d+', hallucination):
            return HallucinationSeverity.MINOR

        return HallucinationSeverity.COSMETIC
```

---

## 6. A/B Testing Methodology

### 6.1 Experiment Design

```python
# backend/tests/benchmarks/ab_testing.py

from dataclasses import dataclass
from typing import Callable, Dict, Any
import random
from scipy import stats

@dataclass
class ExperimentConfig:
    name: str
    description: str
    control_config: Dict[str, Any]
    treatment_config: Dict[str, Any]
    sample_size: int = 100
    confidence_level: float = 0.95

class ABTestRunner:
    def __init__(self, agent_factory: Callable, tasks: List[BenchmarkTask]):
        self.agent_factory = agent_factory
        self.tasks = tasks

    async def run_experiment(self, config: ExperimentConfig) -> Dict[str, Any]:
        """Run A/B test experiment."""

        # Split tasks randomly
        random.shuffle(self.tasks)
        mid = len(self.tasks) // 2

        control_tasks = self.tasks[:mid]
        treatment_tasks = self.tasks[mid:]

        # Run control group
        control_agent = self.agent_factory(config.control_config)
        control_runner = BenchmarkRunner(control_agent, BenchmarkConfig())
        control_results = await control_runner.run_suite(control_tasks)

        # Run treatment group
        treatment_agent = self.agent_factory(config.treatment_config)
        treatment_runner = BenchmarkRunner(treatment_agent, BenchmarkConfig())
        treatment_results = await treatment_runner.run_suite(treatment_tasks)

        # Statistical analysis
        analysis = self._analyze_results(control_results, treatment_results, config)

        return {
            "experiment": config.name,
            "control_results": control_results,
            "treatment_results": treatment_results,
            "analysis": analysis
        }

    def _analyze_results(
        self,
        control: List[BenchmarkResult],
        treatment: List[BenchmarkResult],
        config: ExperimentConfig
    ) -> Dict[str, Any]:
        """Perform statistical analysis of A/B test."""

        # Latency comparison
        control_latency = [r.duration_seconds for r in control]
        treatment_latency = [r.duration_seconds for r in treatment]
        latency_ttest = stats.ttest_ind(control_latency, treatment_latency)

        # Success rate comparison
        control_success = sum(r.success for r in control) / len(control)
        treatment_success = sum(r.success for r in treatment) / len(treatment)

        # Token usage comparison
        control_tokens = sum(r.tokens_used for r in control)
        treatment_tokens = sum(r.tokens_used for r in treatment)

        return {
            "latency": {
                "control_mean": np.mean(control_latency),
                "treatment_mean": np.mean(treatment_latency),
                "improvement_pct": (np.mean(control_latency) - np.mean(treatment_latency)) / np.mean(control_latency) * 100,
                "p_value": latency_ttest.pvalue,
                "significant": latency_ttest.pvalue < (1 - config.confidence_level)
            },
            "success_rate": {
                "control": control_success,
                "treatment": treatment_success,
                "improvement_pct": (treatment_success - control_success) / control_success * 100
            },
            "tokens": {
                "control_total": control_tokens,
                "treatment_total": treatment_tokens,
                "reduction_pct": (control_tokens - treatment_tokens) / control_tokens * 100
            }
        }
```

### 6.2 Experiment Templates

```python
# backend/tests/benchmarks/experiments.py

# Pre-defined experiments for optimization validation

EXPERIMENTS = {
    "prompt_caching": ExperimentConfig(
        name="Prompt Caching A/B Test",
        description="Compare performance with and without Anthropic prompt caching",
        control_config={"enable_prompt_caching": False},
        treatment_config={"enable_prompt_caching": True},
        sample_size=50
    ),

    "parallel_tools": ExperimentConfig(
        name="Parallel Tool Execution A/B Test",
        description="Compare sequential vs parallel tool execution",
        control_config={"max_concurrent_tools": 1},
        treatment_config={"max_concurrent_tools": 5},
        sample_size=50
    ),

    "fact_checking": ExperimentConfig(
        name="Fact-Check Layer A/B Test",
        description="Compare outputs with and without pre-delivery fact checking",
        control_config={"enable_fact_checking": False},
        treatment_config={"enable_fact_checking": True},
        sample_size=30  # Smaller sample, focus on accuracy
    ),

    "execution_cot": ExperimentConfig(
        name="Execution CoT A/B Test",
        description="Compare direct execution vs chain-of-thought reasoning",
        control_config={"enable_execution_cot": False},
        treatment_config={"enable_execution_cot": True},
        sample_size=40
    ),
}
```

---

## 7. Success Criteria

### 7.1 Performance Targets

| Metric | Baseline | Target | Improvement |
|--------|----------|--------|-------------|
| **TTFT (p50)** | 2000ms | 800ms | 60% reduction |
| **TTLT (p50)** | 15s | 10s | 33% reduction |
| **Token cost per task** | $0.15 | $0.05 | 67% reduction |
| **Cache hit rate** | 0% | 60%+ | N/A |

### 7.2 Accuracy Targets

| Metric | Baseline | Target | Improvement |
|--------|----------|--------|-------------|
| **Task completion rate** | 75% | 90% | 20% improvement |
| **First-pass success rate** | 50% | 70% | 40% improvement |
| **Tool selection accuracy** | 80% | 95% | 19% improvement |

### 7.3 Quality Targets

| Metric | Baseline | Target | Improvement |
|--------|----------|--------|-------------|
| **Citation coverage** | 30% | 80% | 167% improvement |
| **Hallucination rate** | 15% | 5% | 67% reduction |
| **Consistency score** | 0.7 | 0.9 | 29% improvement |

### 7.4 Success Criteria Summary

```python
# backend/tests/benchmarks/success_criteria.py

SUCCESS_CRITERIA = {
    # Performance (must meet ALL)
    "performance": {
        "ttft_p50_ms": {"max": 800, "required": True},
        "ttlt_p50_ms": {"max": 10000, "required": True},
        "cache_hit_rate": {"min": 0.5, "required": False},
        "token_reduction_pct": {"min": 50, "required": True},
    },

    # Accuracy (must meet ALL)
    "accuracy": {
        "task_completion_rate": {"min": 0.85, "required": True},
        "first_pass_success_rate": {"min": 0.65, "required": True},
        "tool_selection_accuracy": {"min": 0.90, "required": True},
    },

    # Quality (must meet 2 of 3)
    "quality": {
        "citation_coverage": {"min": 0.70, "required": False},
        "hallucination_rate": {"max": 0.08, "required": True},
        "consistency_score": {"min": 0.85, "required": False},
    },
}

def evaluate_success(metrics: Dict[str, float]) -> Tuple[bool, List[str]]:
    """Evaluate if optimization meets success criteria."""
    failures = []

    for category, criteria in SUCCESS_CRITERIA.items():
        for metric, thresholds in criteria.items():
            value = metrics.get(metric, 0)

            if "min" in thresholds and value < thresholds["min"]:
                if thresholds.get("required", False):
                    failures.append(f"{metric}: {value:.2f} < {thresholds['min']} (required)")
                else:
                    failures.append(f"{metric}: {value:.2f} < {thresholds['min']} (optional)")

            if "max" in thresholds and value > thresholds["max"]:
                if thresholds.get("required", False):
                    failures.append(f"{metric}: {value:.2f} > {thresholds['max']} (required)")

    required_failures = [f for f in failures if "required" in f]
    return len(required_failures) == 0, failures
```

---

## 8. Implementation Guide

### 8.1 Running Benchmarks

```bash
# Run full benchmark suite
cd backend
python -m pytest tests/benchmarks/ -v --benchmark

# Run specific category
python -m pytest tests/benchmarks/ -v -k "research"

# Run A/B experiment
python -m tests.benchmarks.run_experiment --experiment prompt_caching

# Generate report
python -m tests.benchmarks.generate_report --output findings/benchmark_report.md
```

### 8.2 Benchmark Report Generation

```python
# backend/tests/benchmarks/report_generator.py

class BenchmarkReportGenerator:
    def generate(self, results: List[BenchmarkResult], metrics: Dict) -> str:
        """Generate markdown benchmark report."""

        report = f"""# Pythinker Benchmark Report

**Generated:** {datetime.now().isoformat()}
**Tasks Run:** {len(results)}
**Duration:** {sum(r.duration_seconds for r in results):.1f}s

## Executive Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Task Completion | {metrics['accuracy']['task_completion_rate']:.1%} | 85% | {'✅' if metrics['accuracy']['task_completion_rate'] >= 0.85 else '❌'} |
| TTFT (p50) | {metrics['latency']['ttft_p50_ms']:.0f}ms | 800ms | {'✅' if metrics['latency']['ttft_p50_ms'] <= 800 else '❌'} |
| Token Cost | ${metrics['cost']['cost_per_task_usd']:.3f}/task | $0.05 | {'✅' if metrics['cost']['cost_per_task_usd'] <= 0.05 else '❌'} |
| Hallucination Rate | {metrics['hallucination']['overall_hallucination_score']:.1%} | <8% | {'✅' if metrics['hallucination']['overall_hallucination_score'] < 0.08 else '❌'} |

## Detailed Metrics

### Performance
- **TTFT p50/p95/p99:** {metrics['latency']['ttft_p50_ms']:.0f}ms / {metrics['latency']['ttft_p95_ms']:.0f}ms / {metrics['latency']['ttft_p99_ms']:.0f}ms
- **TTLT p50/p95/p99:** {metrics['latency']['ttlt_p50_ms']:.0f}ms / {metrics['latency']['ttlt_p95_ms']:.0f}ms / {metrics['latency']['ttlt_p99_ms']:.0f}ms
- **Cache Hit Rate:** {metrics['cost']['cache_hit_rate']:.1%}

### Accuracy
- **Task Completion:** {metrics['accuracy']['task_completion_rate']:.1%}
- **First-Pass Success:** {metrics['accuracy']['first_pass_success_rate']:.1%}
- **Tool Selection:** {metrics['accuracy']['tool_selection_accuracy']:.1%}

### Quality
- **Citation Coverage:** {metrics['quality']['citation_coverage']:.1%}
- **Consistency Score:** {metrics['quality']['coherence_score']:.2f}

### Hallucination Analysis
- **Tool Hallucinations:** {metrics['hallucination']['tool_hallucination_rate']:.1%}
- **Fact Hallucinations:** {metrics['hallucination']['fact_hallucination_rate']:.1%}
- **Citation Hallucinations:** {metrics['hallucination']['citation_hallucination_rate']:.1%}

## Task Breakdown

| Task | Category | Success | Duration | Tokens |
|------|----------|---------|----------|--------|
"""
        for result in results:
            report += f"| {result.task_id} | {result.metadata.get('category', 'N/A')} | {'✅' if result.success else '❌'} | {result.duration_seconds:.1f}s | {result.tokens_used:,} |\n"

        return report
```

### 8.3 CI/CD Integration

```yaml
# .github/workflows/benchmarks.yml

name: Performance Benchmarks

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 0 * * 0'  # Weekly

jobs:
  benchmark:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r backend/requirements.txt
          pip install pytest-benchmark

      - name: Run benchmarks
        env:
          API_KEY: ${{ secrets.API_KEY }}
        run: |
          cd backend
          python -m pytest tests/benchmarks/ -v --benchmark-json=benchmark_results.json

      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-results
          path: backend/benchmark_results.json

      - name: Check regression
        run: |
          python scripts/check_regression.py backend/benchmark_results.json
```

---

## Summary

This testing and evaluation framework provides:

1. **Comprehensive Metrics:** Latency, throughput, accuracy, quality, and hallucination detection
2. **Standard Benchmark Tasks:** Reproducible test suite across categories
3. **A/B Testing Methodology:** Statistical validation of optimizations
4. **Clear Success Criteria:** Measurable targets for all optimization goals
5. **CI/CD Integration:** Automated regression detection

Use this framework to validate all optimizations before production deployment.

---

*Framework designed based on industry best practices for LLM agent evaluation.*
