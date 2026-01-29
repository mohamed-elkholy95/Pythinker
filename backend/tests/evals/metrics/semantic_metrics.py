"""Semantic evaluation metrics.

Metrics for evaluating text outputs using semantic similarity
and keyword analysis.
"""

import math
import re
from collections import Counter
from typing import Any

from tests.evals.metrics.base import BaseMetric, MetricScore


class SimilarityMetric(BaseMetric):
    """Measures semantic similarity between actual and expected output.

    Uses cosine similarity on word frequency vectors as a baseline.
    Can be extended to use embeddings for better semantic matching.
    """

    name = "similarity"
    description = "Measures semantic similarity between outputs"

    def evaluate(
        self,
        actual_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> MetricScore:
        expected_output = expected.get("expected_output")

        if not expected_output:
            return MetricScore(
                metric_name=self.name,
                score=1.0,
                passed=True,
                message="No expected output for similarity comparison"
            )

        # Tokenize and create word frequency vectors
        actual_words = self._tokenize(actual_output)
        expected_words = self._tokenize(expected_output)

        # Calculate cosine similarity
        similarity = self._cosine_similarity(actual_words, expected_words)

        threshold = expected.get("min_similarity", self.get_threshold(expected, 0.7))
        passed = similarity >= threshold

        return MetricScore(
            metric_name=self.name,
            score=similarity,
            passed=passed,
            details={
                "similarity": similarity,
                "threshold": threshold,
                "method": "cosine_word_frequency",
                "actual_word_count": len(actual_words),
                "expected_word_count": len(expected_words),
            },
            message=f"Similarity score: {similarity:.3f} (threshold: {threshold})"
        )

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into lowercase words."""
        # Simple word tokenization
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        return words

    def _cosine_similarity(self, words1: list[str], words2: list[str]) -> float:
        """Calculate cosine similarity between two word lists."""
        if not words1 or not words2:
            return 0.0

        # Create frequency counters
        freq1 = Counter(words1)
        freq2 = Counter(words2)

        # Get all unique words
        all_words = set(freq1.keys()) | set(freq2.keys())

        # Calculate dot product and magnitudes
        dot_product = sum(freq1.get(w, 0) * freq2.get(w, 0) for w in all_words)
        mag1 = math.sqrt(sum(v ** 2 for v in freq1.values()))
        mag2 = math.sqrt(sum(v ** 2 for v in freq2.values()))

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)


class KeywordCoverageMetric(BaseMetric):
    """Checks coverage of important keywords in the output.

    Extracts key terms from expected output and verifies they appear
    in the actual output.
    """

    name = "keyword_coverage"
    description = "Checks that important keywords from expected output appear in actual"

    # Common words to ignore
    STOP_WORDS = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "shall", "can", "need", "dare",
        "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by",
        "from", "as", "into", "through", "during", "before", "after",
        "above", "below", "between", "under", "again", "further", "then",
        "once", "here", "there", "when", "where", "why", "how", "all",
        "each", "few", "more", "most", "other", "some", "such", "no", "nor",
        "not", "only", "own", "same", "so", "than", "too", "very", "just",
        "and", "but", "if", "or", "because", "until", "while", "this",
        "that", "these", "those", "what", "which", "who", "whom", "i", "you",
        "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    }

    def evaluate(
        self,
        actual_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> MetricScore:
        # Get keywords from expected or extract from expected output
        keywords = expected.get("expected_keywords", [])

        if not keywords:
            expected_output = expected.get("expected_output", "")
            if expected_output:
                keywords = self._extract_keywords(expected_output)
            else:
                return MetricScore(
                    metric_name=self.name,
                    score=1.0,
                    passed=True,
                    message="No keywords to check"
                )

        if not keywords:
            return MetricScore(
                metric_name=self.name,
                score=1.0,
                passed=True,
                message="No significant keywords found"
            )

        # Check keyword coverage
        actual_lower = actual_output.lower()
        found = []
        missing = []

        for kw in keywords:
            if kw.lower() in actual_lower:
                found.append(kw)
            else:
                missing.append(kw)

        coverage = len(found) / len(keywords)
        threshold = self.get_threshold(expected, 0.7)
        passed = coverage >= threshold

        return MetricScore(
            metric_name=self.name,
            score=coverage,
            passed=passed,
            details={
                "found_keywords": found,
                "missing_keywords": missing,
                "total_keywords": len(keywords),
                "coverage": coverage,
                "threshold": threshold,
            },
            message=f"Keyword coverage: {coverage*100:.1f}% ({len(found)}/{len(keywords)})"
        )

    def _extract_keywords(self, text: str, min_length: int = 4, top_n: int = 10) -> list[str]:
        """Extract significant keywords from text."""
        # Tokenize
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())

        # Filter stop words and short words
        filtered = [w for w in words if w not in self.STOP_WORDS and len(w) >= min_length]

        # Get most common
        word_freq = Counter(filtered)
        return [word for word, _ in word_freq.most_common(top_n)]


class JaccardSimilarityMetric(BaseMetric):
    """Measures Jaccard similarity between word sets."""

    name = "jaccard_similarity"
    description = "Measures Jaccard similarity (intersection over union) of word sets"

    def evaluate(
        self,
        actual_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> MetricScore:
        expected_output = expected.get("expected_output")

        if not expected_output:
            return MetricScore(
                metric_name=self.name,
                score=1.0,
                passed=True,
                message="No expected output for Jaccard comparison"
            )

        # Tokenize into sets
        actual_words = set(re.findall(r'\b[a-zA-Z]+\b', actual_output.lower()))
        expected_words = set(re.findall(r'\b[a-zA-Z]+\b', expected_output.lower()))

        # Calculate Jaccard similarity
        if not actual_words or not expected_words:
            similarity = 0.0
        else:
            intersection = len(actual_words & expected_words)
            union = len(actual_words | expected_words)
            similarity = intersection / union if union > 0 else 0.0

        threshold = self.get_threshold(expected, 0.5)
        passed = similarity >= threshold

        return MetricScore(
            metric_name=self.name,
            score=similarity,
            passed=passed,
            details={
                "jaccard_similarity": similarity,
                "intersection_size": len(actual_words & expected_words),
                "union_size": len(actual_words | expected_words),
                "threshold": threshold,
            },
            message=f"Jaccard similarity: {similarity:.3f}"
        )
