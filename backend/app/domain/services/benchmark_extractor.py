"""Benchmark extraction service using LLM."""

import json
import logging
import re
from typing import Any

from app.domain.external.llm import LLM
from app.domain.models.benchmark import (
    BenchmarkCategory,
    BenchmarkComparison,
    BenchmarkExtractionResult,
    BenchmarkUnit,
    ExtractedBenchmark,
)

logger = logging.getLogger(__name__)


EXTRACTION_PROMPT = """Extract all benchmarks, metrics, and quantitative data from the following content.

For each benchmark found, provide:
1. name: The benchmark name (e.g., "MMLU Score", "Latency", "Accuracy")
2. value: The numeric or descriptive value
3. unit: The unit of measurement
4. category: One of [performance, accuracy, efficiency, cost, latency, throughput, quality, custom]
5. subject: What is being measured (e.g., "GPT-4", "Claude 3", "System X")
6. extracted_text: The exact text where you found this benchmark
7. comparison_baseline: If compared to something, what is the baseline
8. test_conditions: Any mentioned test conditions or methodology

Content to analyze:
---
{content}
---

Source URL: {url}

Respond with a JSON object:
{{
  "benchmarks": [
    {{
      "name": "...",
      "value": "...",
      "unit": "...",
      "category": "...",
      "subject": "...",
      "extracted_text": "...",
      "comparison_baseline": "...",
      "test_conditions": "...",
      "confidence": 0.0-1.0
    }}
  ],
  "extraction_notes": "Any notes about the extraction"
}}"""


class BenchmarkExtractor:
    """Extracts benchmarks from research content."""

    def __init__(self, llm: LLM):
        self.llm = llm

        # Common benchmark patterns for rule-based extraction
        self.patterns: list[tuple[str, BenchmarkUnit | None, BenchmarkCategory]] = [
            # Percentage patterns: "achieves 95.2% accuracy"
            (
                r"(\w+(?:\s+\w+)?)\s+(?:achieves?|scores?|reaches?|attains?|gets?)\s+([\d.]+)%",
                BenchmarkUnit.PERCENTAGE,
                BenchmarkCategory.ACCURACY,
            ),
            # Accuracy patterns
            (r"accuracy\s+(?:of\s+)?([\d.]+)%", BenchmarkUnit.PERCENTAGE, BenchmarkCategory.ACCURACY),
            # Latency patterns: "latency of 50ms"
            (
                r"latency\s+(?:of\s+)?([\d.]+)\s*(ms|milliseconds?)",
                BenchmarkUnit.MILLISECONDS,
                BenchmarkCategory.LATENCY,
            ),
            (r"latency\s+(?:of\s+)?([\d.]+)\s*(s|seconds?)", BenchmarkUnit.SECONDS, BenchmarkCategory.LATENCY),
            # Token throughput: "1000 tokens/second"
            (r"([\d,]+)\s*tokens?[/\s]+(second|s|sec)", BenchmarkUnit.TOKENS_PER_SEC, BenchmarkCategory.THROUGHPUT),
            # Cost patterns: "$0.01 per 1M tokens"
            (
                r"\$?([\d.]+)\s*(?:per|/)\s*(?:1?M|million)?\s*tokens?",
                BenchmarkUnit.USD_PER_MILLION,
                BenchmarkCategory.COST,
            ),
            # Performance scores
            (
                r"(?:score|rating)\s+(?:of\s+)?([\d.]+)(?:\s*/\s*100)?",
                BenchmarkUnit.PERCENTAGE,
                BenchmarkCategory.PERFORMANCE,
            ),
            # F1 score
            (r"F1\s+(?:score)?\s*[:=]?\s*([\d.]+)", BenchmarkUnit.RATIO, BenchmarkCategory.ACCURACY),
            # BLEU score
            (r"BLEU\s+(?:score)?\s*[:=]?\s*([\d.]+)", BenchmarkUnit.RATIO, BenchmarkCategory.QUALITY),
            # Requests per second
            (
                r"([\d,]+)\s*(?:requests?|req)[/\s]+(second|s|sec)",
                BenchmarkUnit.REQUESTS_PER_SEC,
                BenchmarkCategory.THROUGHPUT,
            ),
        ]

    async def extract(
        self,
        sources: list[dict[str, Any]],
    ) -> BenchmarkExtractionResult:
        """Extract benchmarks from multiple sources.

        Args:
            sources: List of {url, content, title} dicts

        Returns:
            BenchmarkExtractionResult with all found benchmarks
        """
        all_benchmarks: list[ExtractedBenchmark] = []
        warnings: list[str] = []

        for source in sources:
            try:
                # Try LLM extraction first
                llm_benchmarks = await self._extract_with_llm(source)
                all_benchmarks.extend(llm_benchmarks)

                # Supplement with rule-based extraction
                rule_benchmarks = self._extract_with_rules(source)

                # Add rule-based benchmarks not already found by LLM
                existing_values = {(b.name.lower(), str(b.value)) for b in llm_benchmarks}
                for rb in rule_benchmarks:
                    if (rb.name.lower(), str(rb.value)) not in existing_values:
                        all_benchmarks.append(rb)

            except Exception as e:
                logger.warning(f"Benchmark extraction failed for {source.get('url')}: {e}")
                warnings.append(f"Failed to extract from {source.get('url')}: {str(e)[:100]}")

        # Build comparisons
        comparisons = self._build_comparisons(all_benchmarks)

        # Calculate overall confidence
        confidence = sum(b.confidence for b in all_benchmarks) / len(all_benchmarks) if all_benchmarks else 0.0

        return BenchmarkExtractionResult(
            benchmarks=all_benchmarks,
            comparisons=comparisons,
            extraction_confidence=confidence,
            sources_analyzed=len(sources),
            benchmarks_found=len(all_benchmarks),
            warnings=warnings,
        )

    async def _extract_with_llm(self, source: dict[str, Any]) -> list[ExtractedBenchmark]:
        """Extract benchmarks using LLM."""
        content = source.get("content", "")[:8000]  # Limit content length
        url = source.get("url", "")

        if not content.strip():
            return []

        prompt = EXTRACTION_PROMPT.format(content=content, url=url)

        try:
            response = await self.llm.ask(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )

            response_content = response.get("content", "")
            data = json.loads(response_content)
            benchmarks = []

            for b in data.get("benchmarks", []):
                try:
                    # Map unit string to enum
                    unit = self._map_unit(b.get("unit", "custom"))
                    category = self._map_category(b.get("category", "custom"))

                    benchmarks.append(
                        ExtractedBenchmark(
                            name=b["name"],
                            value=b["value"],
                            unit=unit,
                            category=category,
                            source_url=url,
                            source_title=source.get("title"),
                            extracted_text=b.get("extracted_text", ""),
                            subject=b.get("subject", "Unknown"),
                            comparison_baseline=b.get("comparison_baseline"),
                            test_conditions=b.get("test_conditions"),
                            confidence=float(b.get("confidence", 0.7)),
                        )
                    )
                except Exception as e:
                    logger.debug(f"Failed to parse benchmark: {e}")
                    continue

            return benchmarks

        except json.JSONDecodeError:
            logger.warning("LLM response was not valid JSON")
            return []
        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")
            return []

    def _extract_with_rules(self, source: dict[str, Any]) -> list[ExtractedBenchmark]:
        """Extract benchmarks using regex patterns."""
        content = source.get("content", "")
        url = source.get("url", "")
        benchmarks = []

        for pattern, default_unit, category in self.patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                try:
                    groups = match.groups()
                    name = groups[0] if len(groups) > 1 else "Metric"
                    value = groups[-1] if groups else ""

                    # Clean up value
                    if isinstance(value, str):
                        value = value.replace(",", "")

                    # Get surrounding context
                    start = max(0, match.start() - 100)
                    end = min(len(content), match.end() + 100)
                    context = content[start:end].strip()

                    # Try to infer subject from context
                    subject = self._infer_subject(context)

                    benchmarks.append(
                        ExtractedBenchmark(
                            name=str(name).title(),
                            value=value,
                            unit=default_unit or BenchmarkUnit.CUSTOM,
                            category=category,
                            source_url=url,
                            extracted_text=context,
                            subject=subject,
                            confidence=0.5,  # Lower confidence for rule-based
                        )
                    )
                except Exception as e:
                    logger.debug(f"Rule-based extraction failed: {e}")
                    continue

        return benchmarks

    def _infer_subject(self, context: str) -> str:
        """Try to infer the subject being measured from context."""
        # Common AI model patterns
        model_patterns = [
            r"(GPT-4|GPT-3\.5|GPT-3)",
            r"(Claude\s*\d*(?:\.\d+)?(?:\s+(?:Opus|Sonnet|Haiku))?)",
            r"(Gemini(?:\s+(?:Pro|Ultra|Nano))?)",
            r"(Llama\s*\d*(?:\.\d+)?)",
            r"(PaLM\s*\d*)",
            r"(BERT|RoBERTa|T5|BART)",
        ]

        for pattern in model_patterns:
            match = re.search(pattern, context, re.IGNORECASE)
            if match:
                return match.group(1)

        return "Unknown"

    def _build_comparisons(self, benchmarks: list[ExtractedBenchmark]) -> list[BenchmarkComparison]:
        """Build comparison tables from benchmarks with same name."""
        # Group by benchmark name
        by_name: dict[str, list[ExtractedBenchmark]] = {}
        for b in benchmarks:
            key = b.name.lower().strip()
            if key not in by_name:
                by_name[key] = []
            by_name[key].append(b)

        comparisons = []
        for _name, group in by_name.items():
            if len(group) >= 2:  # Only create comparison if 2+ entries
                entries = [
                    {
                        "subject": b.subject,
                        "value": b.value,
                        "source_url": b.source_url,
                    }
                    for b in group
                ]

                # Determine winner if numeric
                winner = None
                try:
                    sorted_entries = sorted(entries, key=lambda x: float(x["value"]), reverse=True)
                    winner = sorted_entries[0]["subject"]
                except (ValueError, TypeError):
                    pass

                comparisons.append(
                    BenchmarkComparison(
                        benchmark_name=group[0].name,
                        category=group[0].category,
                        unit=group[0].unit,
                        entries=entries,
                        winner=winner,
                    )
                )

        return comparisons

    def _map_unit(self, unit_str: str) -> BenchmarkUnit:
        """Map unit string to enum."""
        unit_map = {
            "percentage": BenchmarkUnit.PERCENTAGE,
            "%": BenchmarkUnit.PERCENTAGE,
            "percent": BenchmarkUnit.PERCENTAGE,
            "ms": BenchmarkUnit.MILLISECONDS,
            "milliseconds": BenchmarkUnit.MILLISECONDS,
            "millisecond": BenchmarkUnit.MILLISECONDS,
            "s": BenchmarkUnit.SECONDS,
            "seconds": BenchmarkUnit.SECONDS,
            "second": BenchmarkUnit.SECONDS,
            "sec": BenchmarkUnit.SECONDS,
            "tokens/s": BenchmarkUnit.TOKENS_PER_SEC,
            "tokens/sec": BenchmarkUnit.TOKENS_PER_SEC,
            "tokens per second": BenchmarkUnit.TOKENS_PER_SEC,
            "req/s": BenchmarkUnit.REQUESTS_PER_SEC,
            "requests/s": BenchmarkUnit.REQUESTS_PER_SEC,
            "requests per second": BenchmarkUnit.REQUESTS_PER_SEC,
            "usd": BenchmarkUnit.USD,
            "$": BenchmarkUnit.USD,
            "dollars": BenchmarkUnit.USD,
            "usd/1m_tokens": BenchmarkUnit.USD_PER_MILLION,
            "count": BenchmarkUnit.COUNT,
            "ratio": BenchmarkUnit.RATIO,
            "bytes": BenchmarkUnit.BYTES,
            "kb": BenchmarkUnit.KILOBYTES,
            "mb": BenchmarkUnit.MEGABYTES,
            "gb": BenchmarkUnit.GIGABYTES,
        }
        return unit_map.get(unit_str.lower().strip(), BenchmarkUnit.CUSTOM)

    def _map_category(self, cat_str: str) -> BenchmarkCategory:
        """Map category string to enum."""
        try:
            return BenchmarkCategory(cat_str.lower().strip())
        except ValueError:
            return BenchmarkCategory.CUSTOM
