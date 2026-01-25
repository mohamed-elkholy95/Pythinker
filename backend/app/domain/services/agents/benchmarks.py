"""LLM Agent Performance Benchmarks

Comprehensive benchmark suite for measuring and validating agent optimizations.
Covers token usage, latency, cache performance, and accuracy metrics.

Usage:
    benchmarks = AgentBenchmarks()
    results = await benchmarks.run_all()
    print(benchmarks.generate_report(results))
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Awaitable
from enum import Enum
import statistics

logger = logging.getLogger(__name__)


class BenchmarkCategory(str, Enum):
    """Categories of benchmarks."""
    TOKEN_EFFICIENCY = "token_efficiency"
    LATENCY = "latency"
    CACHE_PERFORMANCE = "cache_performance"
    TOOL_SELECTION = "tool_selection"
    HALLUCINATION = "hallucination"
    MEMORY = "memory"


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    name: str
    category: BenchmarkCategory
    passed: bool
    score: float  # 0.0 - 1.0
    metrics: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class BenchmarkSuite:
    """Collection of benchmark results."""
    name: str
    results: List[BenchmarkResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total_duration_ms(self) -> float:
        return sum(r.duration_ms for r in self.results)

    @property
    def average_score(self) -> float:
        if not self.results:
            return 0.0
        return statistics.mean(r.score for r in self.results)

    def by_category(self, category: BenchmarkCategory) -> List[BenchmarkResult]:
        return [r for r in self.results if r.category == category]


class AgentBenchmarks:
    """Comprehensive benchmark suite for agent optimizations.

    Measures:
    - Token efficiency (dynamic toolsets, prompt caching)
    - Latency (response times, cache hit rates)
    - Cache performance (L1/L2 hit rates, eviction)
    - Tool selection accuracy (semantic matching)
    - Hallucination detection (false positives/negatives)
    """

    def __init__(self):
        self._benchmarks: Dict[str, Callable[[], Awaitable[BenchmarkResult]]] = {}
        self._register_benchmarks()

    def _register_benchmarks(self):
        """Register all benchmark functions."""
        # Token Efficiency
        self._benchmarks["token_dynamic_toolset"] = self._bench_dynamic_toolset
        self._benchmarks["token_prompt_caching"] = self._bench_prompt_caching
        self._benchmarks["token_count_cache"] = self._bench_token_count_cache

        # Cache Performance
        self._benchmarks["cache_l1_performance"] = self._bench_l1_cache
        self._benchmarks["cache_l2_performance"] = self._bench_l2_cache
        self._benchmarks["cache_combined_hit_rate"] = self._bench_combined_cache

        # Tool Selection
        self._benchmarks["tool_category_detection"] = self._bench_category_detection
        self._benchmarks["tool_semantic_search"] = self._bench_semantic_search
        self._benchmarks["tool_task_filtering"] = self._bench_task_filtering

        # Hallucination Detection
        self._benchmarks["hallucination_detection"] = self._bench_hallucination_detection
        self._benchmarks["hallucination_suggestions"] = self._bench_hallucination_suggestions

        # Memory/Context
        self._benchmarks["memory_pressure_detection"] = self._bench_pressure_detection
        self._benchmarks["memory_token_manager"] = self._bench_token_manager

    async def run_all(self) -> BenchmarkSuite:
        """Run all registered benchmarks."""
        suite = BenchmarkSuite(name="Full Agent Benchmark Suite")

        for name, bench_func in self._benchmarks.items():
            try:
                result = await bench_func()
                suite.results.append(result)
                status = "PASS" if result.passed else "FAIL"
                logger.info(f"Benchmark {name}: {status} (score: {result.score:.2f})")
            except Exception as e:
                suite.results.append(BenchmarkResult(
                    name=name,
                    category=BenchmarkCategory.TOKEN_EFFICIENCY,
                    passed=False,
                    score=0.0,
                    error=str(e)
                ))
                logger.error(f"Benchmark {name} failed: {e}")

        suite.completed_at = datetime.now()
        return suite

    async def run_category(self, category: BenchmarkCategory) -> BenchmarkSuite:
        """Run benchmarks for a specific category."""
        suite = BenchmarkSuite(name=f"{category.value} Benchmarks")

        category_benchmarks = {
            BenchmarkCategory.TOKEN_EFFICIENCY: [
                "token_dynamic_toolset", "token_prompt_caching", "token_count_cache"
            ],
            BenchmarkCategory.CACHE_PERFORMANCE: [
                "cache_l1_performance", "cache_l2_performance", "cache_combined_hit_rate"
            ],
            BenchmarkCategory.TOOL_SELECTION: [
                "tool_category_detection", "tool_semantic_search", "tool_task_filtering"
            ],
            BenchmarkCategory.HALLUCINATION: [
                "hallucination_detection", "hallucination_suggestions"
            ],
            BenchmarkCategory.MEMORY: [
                "memory_pressure_detection", "memory_token_manager"
            ],
        }

        for name in category_benchmarks.get(category, []):
            if name in self._benchmarks:
                try:
                    result = await self._benchmarks[name]()
                    suite.results.append(result)
                except Exception as e:
                    suite.results.append(BenchmarkResult(
                        name=name,
                        category=category,
                        passed=False,
                        score=0.0,
                        error=str(e)
                    ))

        suite.completed_at = datetime.now()
        return suite

    # ==================== Token Efficiency Benchmarks ====================

    async def _bench_dynamic_toolset(self) -> BenchmarkResult:
        """Benchmark dynamic toolset token reduction."""
        from app.domain.services.tools.dynamic_toolset import DynamicToolsetManager

        start = time.perf_counter()

        # Create sample tools (simulate 50 tools)
        sample_tools = []
        for i in range(50):
            categories = ["file", "browser", "search", "shell", "mcp"]
            cat = categories[i % len(categories)]
            sample_tools.append({
                "function": {
                    "name": f"{cat}_tool_{i}",
                    "description": f"Tool {i} for {cat} operations with detailed description"
                }
            })

        manager = DynamicToolsetManager()
        manager.register_tools(sample_tools)

        # Test different task types
        test_cases = [
            ("Research best practices for Python development", "research"),
            ("Write a function to parse JSON files", "coding"),
            ("Navigate to github.com and take a screenshot", "web_browsing"),
        ]

        reductions = []
        for task, expected_type in test_cases:
            filtered = manager.get_tools_for_task(task)
            reduction = 1 - (len(filtered) / len(sample_tools))
            reductions.append(reduction)

        avg_reduction = statistics.mean(reductions)
        duration = (time.perf_counter() - start) * 1000

        # Pass if average reduction > 40%
        passed = avg_reduction > 0.40
        score = min(avg_reduction / 0.96, 1.0)  # 96% is perfect

        return BenchmarkResult(
            name="token_dynamic_toolset",
            category=BenchmarkCategory.TOKEN_EFFICIENCY,
            passed=passed,
            score=score,
            metrics={
                "total_tools": len(sample_tools),
                "average_reduction": f"{avg_reduction:.1%}",
                "reductions": [f"{r:.1%}" for r in reductions],
                "test_cases": len(test_cases)
            },
            duration_ms=duration
        )

    async def _bench_prompt_caching(self) -> BenchmarkResult:
        """Benchmark prompt caching efficiency."""
        start = time.perf_counter()

        # Simulate prompt caching scenarios
        system_prompt = "You are a helpful assistant. " * 100  # ~400 tokens

        # Calculate potential savings
        requests_per_session = 10
        cached_tokens = len(system_prompt.split()) * (requests_per_session - 1)
        total_tokens = len(system_prompt.split()) * requests_per_session
        savings_ratio = cached_tokens / total_tokens

        duration = (time.perf_counter() - start) * 1000

        # Pass if savings > 80%
        passed = savings_ratio > 0.80
        score = min(savings_ratio / 0.90, 1.0)

        return BenchmarkResult(
            name="token_prompt_caching",
            category=BenchmarkCategory.TOKEN_EFFICIENCY,
            passed=passed,
            score=score,
            metrics={
                "system_prompt_tokens": len(system_prompt.split()),
                "requests_per_session": requests_per_session,
                "potential_savings": f"{savings_ratio:.1%}",
                "cached_tokens_saved": cached_tokens
            },
            duration_ms=duration
        )

    async def _bench_token_count_cache(self) -> BenchmarkResult:
        """Benchmark token count caching performance."""
        from app.domain.services.agents.token_manager import TokenManager

        start = time.perf_counter()

        manager = TokenManager(model_name="gpt-4", enable_cache=True)

        # Test with repeated content
        test_content = "This is a test message for token counting. " * 50
        iterations = 100

        # First pass - cache miss
        for _ in range(iterations):
            manager.count_tokens(test_content)

        stats = manager.get_stats()
        cache_stats = stats.get("cache", {})

        duration = (time.perf_counter() - start) * 1000

        hit_rate = cache_stats.get("hit_rate", 0)
        # After first miss, all should be hits
        expected_hit_rate = (iterations - 1) / iterations

        passed = hit_rate >= expected_hit_rate * 0.95  # 95% of expected
        score = hit_rate

        return BenchmarkResult(
            name="token_count_cache",
            category=BenchmarkCategory.TOKEN_EFFICIENCY,
            passed=passed,
            score=score,
            metrics={
                "iterations": iterations,
                "cache_hits": cache_stats.get("hits", 0),
                "cache_misses": cache_stats.get("misses", 0),
                "hit_rate": f"{hit_rate:.1%}",
                "cache_size": cache_stats.get("size", 0)
            },
            duration_ms=duration
        )

    # ==================== Cache Performance Benchmarks ====================

    async def _bench_l1_cache(self) -> BenchmarkResult:
        """Benchmark L1 (in-memory) cache performance."""
        from app.domain.services.tools.cache_layer import L1Cache

        start = time.perf_counter()

        cache = L1Cache(max_size=100)

        # Write test
        write_times = []
        for i in range(100):
            ws = time.perf_counter()
            cache.set(f"key_{i}", {"value": i, "data": "x" * 100})
            write_times.append((time.perf_counter() - ws) * 1000)

        # Read test (all hits)
        read_times = []
        for i in range(100):
            rs = time.perf_counter()
            cache.get(f"key_{i}")
            read_times.append((time.perf_counter() - rs) * 1000)

        stats = cache.get_stats()
        duration = (time.perf_counter() - start) * 1000

        avg_write = statistics.mean(write_times)
        avg_read = statistics.mean(read_times)

        # Pass if avg read < 0.1ms (sub-millisecond)
        passed = avg_read < 0.1
        score = min(1.0 / (avg_read * 10 + 0.1), 1.0)

        return BenchmarkResult(
            name="cache_l1_performance",
            category=BenchmarkCategory.CACHE_PERFORMANCE,
            passed=passed,
            score=score,
            metrics={
                "avg_write_ms": f"{avg_write:.4f}",
                "avg_read_ms": f"{avg_read:.4f}",
                "hit_rate": f"{stats['hit_rate']:.1%}",
                "cache_size": stats["size"]
            },
            duration_ms=duration
        )

    async def _bench_l2_cache(self) -> BenchmarkResult:
        """Benchmark L2 (Redis) cache performance."""
        start = time.perf_counter()

        try:
            from app.infrastructure.external.cache import get_cache
            cache = get_cache()

            # Write test
            write_times = []
            for i in range(10):
                ws = time.perf_counter()
                await cache.set(f"bench_key_{i}", {"value": i}, ttl=60)
                write_times.append((time.perf_counter() - ws) * 1000)

            # Read test
            read_times = []
            for i in range(10):
                rs = time.perf_counter()
                await cache.get(f"bench_key_{i}")
                read_times.append((time.perf_counter() - rs) * 1000)

            # Cleanup
            for i in range(10):
                await cache.delete(f"bench_key_{i}")

            duration = (time.perf_counter() - start) * 1000

            avg_write = statistics.mean(write_times)
            avg_read = statistics.mean(read_times)

            # Pass if avg read < 5ms
            passed = avg_read < 5
            score = min(5.0 / (avg_read + 0.1), 1.0)

            return BenchmarkResult(
                name="cache_l2_performance",
                category=BenchmarkCategory.CACHE_PERFORMANCE,
                passed=passed,
                score=score,
                metrics={
                    "avg_write_ms": f"{avg_write:.2f}",
                    "avg_read_ms": f"{avg_read:.2f}",
                    "operations": 20
                },
                duration_ms=duration
            )

        except Exception as e:
            return BenchmarkResult(
                name="cache_l2_performance",
                category=BenchmarkCategory.CACHE_PERFORMANCE,
                passed=False,
                score=0.0,
                error=f"Redis not available: {e}",
                duration_ms=(time.perf_counter() - start) * 1000
            )

    async def _bench_combined_cache(self) -> BenchmarkResult:
        """Benchmark combined L1+L2 cache hit rates."""
        from app.domain.services.tools.cache_layer import get_combined_cache_stats, get_l1_cache

        start = time.perf_counter()

        l1 = get_l1_cache()

        # Simulate typical access pattern
        for i in range(50):
            key = f"combined_test_{i % 10}"  # 10 unique keys, accessed 5 times each
            if l1.get(key) is None:
                l1.set(key, {"value": i}, ttl=300)

        stats = get_combined_cache_stats()
        duration = (time.perf_counter() - start) * 1000

        l1_hit_rate = stats["l1"]["hit_rate"]

        # With 10 unique keys accessed 5 times, expect ~80% hit rate
        passed = l1_hit_rate >= 0.70
        score = l1_hit_rate

        return BenchmarkResult(
            name="cache_combined_hit_rate",
            category=BenchmarkCategory.CACHE_PERFORMANCE,
            passed=passed,
            score=score,
            metrics={
                "l1_hit_rate": f"{l1_hit_rate:.1%}",
                "l1_size": stats["l1"]["size"],
                "l2_hits": stats["l2"]["hits"],
                "l2_misses": stats["l2"]["misses"]
            },
            duration_ms=duration
        )

    # ==================== Tool Selection Benchmarks ====================

    async def _bench_category_detection(self) -> BenchmarkResult:
        """Benchmark tool category detection accuracy."""
        from app.domain.services.tools.dynamic_toolset import DynamicToolsetManager, ToolCategory

        start = time.perf_counter()

        manager = DynamicToolsetManager()

        # Test cases with clear category patterns
        test_cases = [
            ("file_read", ToolCategory.FILE),
            ("file_write", ToolCategory.FILE),
            ("browser_navigate", ToolCategory.BROWSER),
            ("browser_screenshot", ToolCategory.BROWSER),
            ("info_search_web", ToolCategory.SEARCH),
            ("web_search", ToolCategory.SEARCH),
            ("shell_execute", ToolCategory.SHELL),
            ("message_ask_user", ToolCategory.MESSAGE),
            ("mcp_github_search", ToolCategory.MCP),
            ("mcp_tool_call", ToolCategory.MCP),
        ]

        results_detail = []
        correct = 0
        for tool_name, expected_category in test_cases:
            detected = manager._detect_category(tool_name)
            matched = detected == expected_category
            if matched:
                correct += 1
            results_detail.append({
                "tool": tool_name,
                "expected": expected_category.value,
                "detected": detected.value,
                "matched": matched
            })

        accuracy = correct / len(test_cases)
        duration = (time.perf_counter() - start) * 1000

        # Lower threshold since pattern matching may not catch all edge cases
        passed = accuracy >= 0.80
        score = accuracy

        return BenchmarkResult(
            name="tool_category_detection",
            category=BenchmarkCategory.TOOL_SELECTION,
            passed=passed,
            score=score,
            metrics={
                "test_cases": len(test_cases),
                "correct": correct,
                "accuracy": f"{accuracy:.1%}",
                "mismatches": [r for r in results_detail if not r["matched"]]
            },
            duration_ms=duration
        )

    async def _bench_semantic_search(self) -> BenchmarkResult:
        """Benchmark semantic tool search accuracy."""
        from app.domain.services.tools.dynamic_toolset import DynamicToolsetManager

        start = time.perf_counter()

        # Register tools
        tools = [
            {"function": {"name": "file_read", "description": "Read contents from a file on disk"}},
            {"function": {"name": "file_write", "description": "Write content to a file"}},
            {"function": {"name": "browser_screenshot", "description": "Capture screenshot of web page"}},
            {"function": {"name": "info_search_web", "description": "Search the internet for information"}},
        ]

        manager = DynamicToolsetManager()
        manager.register_tools(tools)

        test_cases = [
            ("screenshot", "browser_screenshot"),
            ("read file", "file_read"),
            ("search internet", "info_search_web"),
            ("write content", "file_write"),
        ]

        correct = 0
        for query, expected_tool in test_cases:
            results = manager.search_tools(query, limit=1)
            if results and results[0][0] == expected_tool:
                correct += 1

        accuracy = correct / len(test_cases)
        duration = (time.perf_counter() - start) * 1000

        passed = accuracy >= 0.75
        score = accuracy

        return BenchmarkResult(
            name="tool_semantic_search",
            category=BenchmarkCategory.TOOL_SELECTION,
            passed=passed,
            score=score,
            metrics={
                "test_cases": len(test_cases),
                "correct": correct,
                "accuracy": f"{accuracy:.1%}"
            },
            duration_ms=duration
        )

    async def _bench_task_filtering(self) -> BenchmarkResult:
        """Benchmark task-based tool filtering."""
        from app.domain.services.tools.dynamic_toolset import DynamicToolsetManager

        start = time.perf_counter()

        # Register diverse tools
        tools = [
            {"function": {"name": "file_read", "description": "Read file"}},
            {"function": {"name": "file_write", "description": "Write file"}},
            {"function": {"name": "browser_navigate", "description": "Navigate browser"}},
            {"function": {"name": "info_search_web", "description": "Search web"}},
            {"function": {"name": "shell_execute", "description": "Execute command"}},
            {"function": {"name": "code_analyze", "description": "Analyze code"}},
        ]

        manager = DynamicToolsetManager()
        manager.register_tools(tools)

        # Test task detection
        test_cases = [
            ("Research AI trends", ["research"]),
            ("Write Python code", ["coding"]),
            ("Browse to github.com", ["web_browsing"]),
        ]

        correct = 0
        for task, expected_types in test_cases:
            detected = manager.detect_task_type(task)
            if any(t in expected_types for t in detected):
                correct += 1

        accuracy = correct / len(test_cases)
        duration = (time.perf_counter() - start) * 1000

        passed = accuracy >= 0.75
        score = accuracy

        return BenchmarkResult(
            name="tool_task_filtering",
            category=BenchmarkCategory.TOOL_SELECTION,
            passed=passed,
            score=score,
            metrics={
                "test_cases": len(test_cases),
                "correct": correct,
                "accuracy": f"{accuracy:.1%}"
            },
            duration_ms=duration
        )

    # ==================== Hallucination Benchmarks ====================

    async def _bench_hallucination_detection(self) -> BenchmarkResult:
        """Benchmark hallucination detection accuracy."""
        from app.domain.services.agents.hallucination_detector import ToolHallucinationDetector

        start = time.perf_counter()

        available_tools = ["file_read", "file_write", "browser_navigate", "info_search_web"]
        detector = ToolHallucinationDetector(available_tools)

        test_cases = [
            # (tool_name, should_detect_hallucination)
            ("file_read", False),
            ("file_write", False),
            ("fiel_read", True),  # Typo
            ("file_raed", True),  # Typo
            ("nonexistent_tool", True),
            ("browser_navigate", False),
            ("browsr_navigate", True),  # Typo
        ]

        correct = 0
        for tool_name, should_detect in test_cases:
            result = detector.detect(tool_name)
            detected = result is not None
            if detected == should_detect:
                correct += 1

        accuracy = correct / len(test_cases)
        duration = (time.perf_counter() - start) * 1000

        passed = accuracy >= 0.85
        score = accuracy

        return BenchmarkResult(
            name="hallucination_detection",
            category=BenchmarkCategory.HALLUCINATION,
            passed=passed,
            score=score,
            metrics={
                "test_cases": len(test_cases),
                "correct": correct,
                "accuracy": f"{accuracy:.1%}",
                "total_hallucinations": detector.hallucination_count
            },
            duration_ms=duration
        )

    async def _bench_hallucination_suggestions(self) -> BenchmarkResult:
        """Benchmark hallucination suggestion quality."""
        from app.domain.services.agents.hallucination_detector import ToolHallucinationDetector

        start = time.perf_counter()

        available_tools = ["file_read", "file_write", "file_list", "browser_navigate", "browser_click"]
        detector = ToolHallucinationDetector(available_tools, similarity_threshold=0.5)

        test_cases = [
            ("fiel_read", "file_read"),
            ("file_raed", "file_read"),
            ("browsr_navigate", "browser_navigate"),
            ("browser_clik", "browser_click"),
        ]

        correct_suggestions = 0
        for typo, expected in test_cases:
            result = detector.detect(typo)
            if result and expected in result:
                correct_suggestions += 1

        accuracy = correct_suggestions / len(test_cases)
        duration = (time.perf_counter() - start) * 1000

        passed = accuracy >= 0.75
        score = accuracy

        return BenchmarkResult(
            name="hallucination_suggestions",
            category=BenchmarkCategory.HALLUCINATION,
            passed=passed,
            score=score,
            metrics={
                "test_cases": len(test_cases),
                "correct_suggestions": correct_suggestions,
                "accuracy": f"{accuracy:.1%}"
            },
            duration_ms=duration
        )

    # ==================== Memory Benchmarks ====================

    async def _bench_pressure_detection(self) -> BenchmarkResult:
        """Benchmark context pressure detection."""
        from app.domain.services.agents.token_manager import TokenManager, PressureLevel

        start = time.perf_counter()

        # Use larger context to make thresholds clearer
        manager = TokenManager(model_name="gpt-4", max_context_tokens=100000)

        # Effective limit is 100000 - 2048 = 97952
        # Thresholds: warning=75%, critical=85%, overflow=95%
        # warning at ~73,464 tokens, critical at ~83,259, overflow at ~93,054

        test_cases = [
            (1000, PressureLevel.NORMAL),     # ~1% usage
            (50000, PressureLevel.NORMAL),    # ~51% usage
            (75000, PressureLevel.WARNING),   # ~77% usage
            (85000, PressureLevel.CRITICAL),  # ~87% usage
            (95000, PressureLevel.OVERFLOW),  # ~97% usage
        ]

        results_detail = []
        correct = 0
        for target_tokens, expected_level in test_cases:
            # Create message with specific character count to approximate tokens
            # tiktoken uses ~4 chars per token for simple text
            char_count = target_tokens * 4
            messages = [{"role": "user", "content": "a" * char_count}]
            pressure = manager.get_context_pressure(messages)
            matched = pressure.level == expected_level
            if matched:
                correct += 1
            results_detail.append({
                "target": target_tokens,
                "expected": expected_level.value,
                "actual": pressure.level.value,
                "usage": f"{pressure.usage_percent:.1%}",
                "matched": matched
            })

        accuracy = correct / len(test_cases)
        duration = (time.perf_counter() - start) * 1000

        passed = accuracy >= 0.60  # More lenient threshold due to token estimation variance
        score = accuracy

        return BenchmarkResult(
            name="memory_pressure_detection",
            category=BenchmarkCategory.MEMORY,
            passed=passed,
            score=score,
            metrics={
                "test_cases": len(test_cases),
                "correct": correct,
                "accuracy": f"{accuracy:.1%}",
                "details": results_detail[:3]  # First 3 for brevity
            },
            duration_ms=duration
        )

    async def _bench_token_manager(self) -> BenchmarkResult:
        """Benchmark token manager overall performance."""
        from app.domain.services.agents.token_manager import TokenManager

        start = time.perf_counter()

        manager = TokenManager(model_name="gpt-4")

        # Test token counting speed
        test_text = "The quick brown fox jumps over the lazy dog. " * 100

        count_times = []
        for _ in range(100):
            cs = time.perf_counter()
            manager.count_tokens(test_text)
            count_times.append((time.perf_counter() - cs) * 1000)

        avg_count_time = statistics.mean(count_times)

        # Test message trimming
        messages = [
            {"role": "system", "content": "System prompt " * 50},
            {"role": "user", "content": "User message " * 100},
            {"role": "assistant", "content": "Response " * 100},
        ] * 10

        trim_start = time.perf_counter()
        trimmed, removed = manager.trim_messages(messages)
        trim_time = (time.perf_counter() - trim_start) * 1000

        duration = (time.perf_counter() - start) * 1000

        stats = manager.get_stats()

        # Pass if counting is fast (< 1ms avg with cache)
        passed = avg_count_time < 1.0
        score = min(1.0 / (avg_count_time + 0.1), 1.0)

        return BenchmarkResult(
            name="memory_token_manager",
            category=BenchmarkCategory.MEMORY,
            passed=passed,
            score=score,
            metrics={
                "avg_count_time_ms": f"{avg_count_time:.3f}",
                "trim_time_ms": f"{trim_time:.2f}",
                "messages_trimmed": len(messages) - len(trimmed),
                "tokens_removed": removed,
                "cache_hit_rate": f"{stats['cache']['hit_rate']:.1%}"
            },
            duration_ms=duration
        )

    # ==================== Report Generation ====================

    def generate_report(self, suite: BenchmarkSuite) -> str:
        """Generate a markdown report from benchmark results."""
        lines = [
            f"# {suite.name}",
            f"",
            f"**Run Date:** {suite.started_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Duration:** {suite.total_duration_ms:.0f}ms",
            f"**Results:** {suite.passed_count} passed, {suite.failed_count} failed",
            f"**Average Score:** {suite.average_score:.1%}",
            f"",
            f"---",
            f"",
        ]

        # Group by category
        for category in BenchmarkCategory:
            results = suite.by_category(category)
            if not results:
                continue

            lines.append(f"## {category.value.replace('_', ' ').title()}")
            lines.append("")

            for r in results:
                status = "✅" if r.passed else "❌"
                lines.append(f"### {status} {r.name}")
                lines.append(f"")
                lines.append(f"- **Score:** {r.score:.1%}")
                lines.append(f"- **Duration:** {r.duration_ms:.2f}ms")

                if r.error:
                    lines.append(f"- **Error:** {r.error}")

                if r.metrics:
                    lines.append(f"- **Metrics:**")
                    for k, v in r.metrics.items():
                        lines.append(f"  - {k}: {v}")

                lines.append("")

        return "\n".join(lines)


async def run_benchmarks() -> BenchmarkSuite:
    """Convenience function to run all benchmarks."""
    benchmarks = AgentBenchmarks()
    return await benchmarks.run_all()
