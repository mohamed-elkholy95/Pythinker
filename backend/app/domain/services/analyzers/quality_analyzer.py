"""
Code quality analyzer for measuring complexity and maintainability.

Calculates metrics including:
- Cyclomatic complexity
- Maintainability index
- Code duplication
- Lines of code
- Comment ratio
"""

import re
import ast
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
import math

logger = logging.getLogger(__name__)


class QualityRating(str, Enum):
    """Quality rating levels."""
    EXCELLENT = "excellent"  # 80-100
    GOOD = "good"  # 60-79
    MODERATE = "moderate"  # 40-59
    POOR = "poor"  # 20-39
    CRITICAL = "critical"  # 0-19


@dataclass
class FunctionMetrics:
    """Metrics for a single function/method."""
    name: str
    line_start: int
    line_end: int
    cyclomatic_complexity: int
    lines_of_code: int
    parameters: int
    nesting_depth: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "cyclomatic_complexity": self.cyclomatic_complexity,
            "lines_of_code": self.lines_of_code,
            "parameters": self.parameters,
            "nesting_depth": self.nesting_depth,
        }


@dataclass
class CodeMetrics:
    """Overall code metrics for a file."""
    file_path: str
    total_lines: int
    code_lines: int
    comment_lines: int
    blank_lines: int
    functions: List[FunctionMetrics]
    classes: int
    imports: int
    average_complexity: float
    max_complexity: int
    maintainability_index: float
    quality_rating: QualityRating
    duplication_ratio: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "total_lines": self.total_lines,
            "code_lines": self.code_lines,
            "comment_lines": self.comment_lines,
            "blank_lines": self.blank_lines,
            "functions": [f.to_dict() for f in self.functions],
            "classes": self.classes,
            "imports": self.imports,
            "average_complexity": round(self.average_complexity, 2),
            "max_complexity": self.max_complexity,
            "maintainability_index": round(self.maintainability_index, 2),
            "quality_rating": self.quality_rating.value,
            "duplication_ratio": round(self.duplication_ratio, 2),
            "comment_ratio": round(self.comment_lines / max(self.code_lines, 1) * 100, 1),
        }


@dataclass
class QualityIssue:
    """A code quality issue."""
    type: str
    severity: str
    description: str
    file_path: str
    line_number: Optional[int]
    function_name: Optional[str]
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type,
            "severity": self.severity,
            "description": self.description,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "function_name": self.function_name,
            "recommendation": self.recommendation,
        }


class ComplexityVisitor(ast.NodeVisitor):
    """AST visitor for calculating cyclomatic complexity."""

    def __init__(self):
        self.complexity = 1  # Base complexity
        self.nesting_depth = 0
        self.max_nesting = 0
        self.decision_points = []

    def _add_complexity(self, node, points: int = 1):
        """Add complexity points."""
        self.complexity += points
        self.decision_points.append(node.__class__.__name__)

    def visit_If(self, node):
        self._add_complexity(node)
        self.nesting_depth += 1
        self.max_nesting = max(self.max_nesting, self.nesting_depth)
        self.generic_visit(node)
        self.nesting_depth -= 1

    def visit_For(self, node):
        self._add_complexity(node)
        self.nesting_depth += 1
        self.max_nesting = max(self.max_nesting, self.nesting_depth)
        self.generic_visit(node)
        self.nesting_depth -= 1

    def visit_While(self, node):
        self._add_complexity(node)
        self.nesting_depth += 1
        self.max_nesting = max(self.max_nesting, self.nesting_depth)
        self.generic_visit(node)
        self.nesting_depth -= 1

    def visit_ExceptHandler(self, node):
        self._add_complexity(node)
        self.generic_visit(node)

    def visit_With(self, node):
        self.nesting_depth += 1
        self.max_nesting = max(self.max_nesting, self.nesting_depth)
        self.generic_visit(node)
        self.nesting_depth -= 1

    def visit_BoolOp(self, node):
        # Each 'and' or 'or' adds complexity
        self._add_complexity(node, len(node.values) - 1)
        self.generic_visit(node)

    def visit_comprehension(self, node):
        self._add_complexity(node)
        self.generic_visit(node)

    def visit_Assert(self, node):
        self._add_complexity(node)
        self.generic_visit(node)

    def visit_Lambda(self, node):
        self._add_complexity(node)
        self.generic_visit(node)


class QualityAnalyzer:
    """
    Analyzes code quality and calculates metrics.

    Supports Python code analysis using AST parsing.
    """

    # Thresholds for quality issues
    COMPLEXITY_WARNING = 10
    COMPLEXITY_CRITICAL = 20
    FUNCTION_LENGTH_WARNING = 50
    FUNCTION_LENGTH_CRITICAL = 100
    PARAMETER_WARNING = 5
    NESTING_WARNING = 4

    def __init__(self):
        """Initialize quality analyzer."""
        self._duplicate_hashes: Dict[str, List[Tuple[str, int]]] = {}

    def analyze(
        self,
        code: str,
        file_path: str = "unknown",
        language: str = "python",
    ) -> Tuple[CodeMetrics, List[QualityIssue]]:
        """
        Analyze code quality.

        Args:
            code: Source code to analyze
            file_path: Path to the file
            language: Programming language

        Returns:
            Tuple of (CodeMetrics, List[QualityIssue])
        """
        if language != "python":
            # For non-Python, return basic metrics
            return self._analyze_generic(code, file_path)

        return self._analyze_python(code, file_path)

    def _analyze_python(
        self,
        code: str,
        file_path: str,
    ) -> Tuple[CodeMetrics, List[QualityIssue]]:
        """Analyze Python code using AST."""
        issues = []
        lines = code.split('\n')

        # Count line types
        total_lines = len(lines)
        code_lines = 0
        comment_lines = 0
        blank_lines = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                blank_lines += 1
            elif stripped.startswith('#'):
                comment_lines += 1
            else:
                code_lines += 1

        # Parse AST
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return self._analyze_generic(code, file_path)

        # Extract functions and classes
        functions = []
        classes = 0
        imports = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
                imports += 1
            elif isinstance(node, ast.ClassDef):
                classes += 1
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                func_metrics = self._analyze_function(node, code, lines)
                functions.append(func_metrics)

                # Check for issues
                if func_metrics.cyclomatic_complexity >= self.COMPLEXITY_CRITICAL:
                    issues.append(QualityIssue(
                        type="high_complexity",
                        severity="critical",
                        description=f"Very high cyclomatic complexity ({func_metrics.cyclomatic_complexity})",
                        file_path=file_path,
                        line_number=func_metrics.line_start,
                        function_name=func_metrics.name,
                        recommendation="Break down into smaller functions",
                    ))
                elif func_metrics.cyclomatic_complexity >= self.COMPLEXITY_WARNING:
                    issues.append(QualityIssue(
                        type="high_complexity",
                        severity="warning",
                        description=f"High cyclomatic complexity ({func_metrics.cyclomatic_complexity})",
                        file_path=file_path,
                        line_number=func_metrics.line_start,
                        function_name=func_metrics.name,
                        recommendation="Consider simplifying the function",
                    ))

                if func_metrics.lines_of_code >= self.FUNCTION_LENGTH_CRITICAL:
                    issues.append(QualityIssue(
                        type="long_function",
                        severity="critical",
                        description=f"Very long function ({func_metrics.lines_of_code} lines)",
                        file_path=file_path,
                        line_number=func_metrics.line_start,
                        function_name=func_metrics.name,
                        recommendation="Break down into smaller functions",
                    ))
                elif func_metrics.lines_of_code >= self.FUNCTION_LENGTH_WARNING:
                    issues.append(QualityIssue(
                        type="long_function",
                        severity="warning",
                        description=f"Long function ({func_metrics.lines_of_code} lines)",
                        file_path=file_path,
                        line_number=func_metrics.line_start,
                        function_name=func_metrics.name,
                        recommendation="Consider splitting into smaller functions",
                    ))

                if func_metrics.parameters > self.PARAMETER_WARNING:
                    issues.append(QualityIssue(
                        type="too_many_parameters",
                        severity="warning",
                        description=f"Too many parameters ({func_metrics.parameters})",
                        file_path=file_path,
                        line_number=func_metrics.line_start,
                        function_name=func_metrics.name,
                        recommendation="Consider using a configuration object or data class",
                    ))

                if func_metrics.nesting_depth > self.NESTING_WARNING:
                    issues.append(QualityIssue(
                        type="deep_nesting",
                        severity="warning",
                        description=f"Deep nesting ({func_metrics.nesting_depth} levels)",
                        file_path=file_path,
                        line_number=func_metrics.line_start,
                        function_name=func_metrics.name,
                        recommendation="Refactor to reduce nesting depth",
                    ))

        # Calculate aggregate metrics
        if functions:
            avg_complexity = sum(f.cyclomatic_complexity for f in functions) / len(functions)
            max_complexity = max(f.cyclomatic_complexity for f in functions)
        else:
            avg_complexity = 1.0
            max_complexity = 1

        # Calculate maintainability index
        maintainability = self._calculate_maintainability_index(
            code_lines, avg_complexity, comment_lines
        )

        # Determine quality rating
        rating = self._get_quality_rating(maintainability)

        # Check for duplication
        duplication = self._estimate_duplication(lines)

        metrics = CodeMetrics(
            file_path=file_path,
            total_lines=total_lines,
            code_lines=code_lines,
            comment_lines=comment_lines,
            blank_lines=blank_lines,
            functions=functions,
            classes=classes,
            imports=imports,
            average_complexity=avg_complexity,
            max_complexity=max_complexity,
            maintainability_index=maintainability,
            quality_rating=rating,
            duplication_ratio=duplication,
        )

        return metrics, issues

    def _analyze_function(
        self,
        node: ast.FunctionDef,
        code: str,
        lines: List[str],
    ) -> FunctionMetrics:
        """Analyze a single function."""
        # Get line range
        line_start = node.lineno
        line_end = node.end_lineno or line_start

        # Count parameters
        params = len(node.args.args) + len(node.args.kwonlyargs)
        if node.args.vararg:
            params += 1
        if node.args.kwarg:
            params += 1

        # Calculate complexity
        visitor = ComplexityVisitor()
        visitor.visit(node)

        return FunctionMetrics(
            name=node.name,
            line_start=line_start,
            line_end=line_end,
            cyclomatic_complexity=visitor.complexity,
            lines_of_code=line_end - line_start + 1,
            parameters=params,
            nesting_depth=visitor.max_nesting,
        )

    def _analyze_generic(
        self,
        code: str,
        file_path: str,
    ) -> Tuple[CodeMetrics, List[QualityIssue]]:
        """Generic analysis for non-Python code."""
        lines = code.split('\n')
        total_lines = len(lines)
        code_lines = sum(1 for l in lines if l.strip() and not l.strip().startswith(('//', '#', '*')))
        comment_lines = sum(1 for l in lines if l.strip().startswith(('//', '#', '*')))
        blank_lines = sum(1 for l in lines if not l.strip())

        metrics = CodeMetrics(
            file_path=file_path,
            total_lines=total_lines,
            code_lines=code_lines,
            comment_lines=comment_lines,
            blank_lines=blank_lines,
            functions=[],
            classes=0,
            imports=0,
            average_complexity=1.0,
            max_complexity=1,
            maintainability_index=50.0,
            quality_rating=QualityRating.MODERATE,
        )

        return metrics, []

    def _calculate_maintainability_index(
        self,
        loc: int,
        avg_complexity: float,
        comment_lines: int,
    ) -> float:
        """
        Calculate the Maintainability Index.

        Uses the Microsoft formula:
        MI = 171 - 5.2 * ln(HV) - 0.23 * CC - 16.2 * ln(LOC) + 50 * sin(sqrt(2.4 * CM))

        Simplified version without Halstead Volume (HV).
        """
        if loc == 0:
            return 100.0

        # Simplified calculation
        loc_factor = 16.2 * math.log(max(loc, 1))
        complexity_factor = 0.23 * avg_complexity

        # Comment modifier (bonus for comments)
        comment_ratio = comment_lines / max(loc, 1)
        comment_factor = 50 * math.sin(math.sqrt(2.4 * comment_ratio))

        mi = 171 - complexity_factor - loc_factor + comment_factor

        # Normalize to 0-100
        return max(0, min(100, mi))

    def _get_quality_rating(self, maintainability: float) -> QualityRating:
        """Get quality rating from maintainability index."""
        if maintainability >= 80:
            return QualityRating.EXCELLENT
        elif maintainability >= 60:
            return QualityRating.GOOD
        elif maintainability >= 40:
            return QualityRating.MODERATE
        elif maintainability >= 20:
            return QualityRating.POOR
        else:
            return QualityRating.CRITICAL

    def _estimate_duplication(self, lines: List[str]) -> float:
        """Estimate code duplication ratio."""
        # Simple line-based duplication detection
        if len(lines) < 10:
            return 0.0

        # Normalize lines
        normalized = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                normalized.append(stripped)

        if not normalized:
            return 0.0

        # Count duplicates
        line_counts: Dict[str, int] = {}
        for line in normalized:
            if len(line) > 10:  # Ignore short lines
                line_counts[line] = line_counts.get(line, 0) + 1

        duplicated = sum(count - 1 for count in line_counts.values() if count > 1)
        return duplicated / len(normalized)

    def get_summary(
        self,
        metrics_list: List[CodeMetrics],
    ) -> Dict[str, Any]:
        """Generate a summary across multiple files."""
        if not metrics_list:
            return {"files": 0}

        total_loc = sum(m.code_lines for m in metrics_list)
        total_functions = sum(len(m.functions) for m in metrics_list)
        avg_mi = sum(m.maintainability_index for m in metrics_list) / len(metrics_list)

        return {
            "files_analyzed": len(metrics_list),
            "total_lines_of_code": total_loc,
            "total_functions": total_functions,
            "average_maintainability": round(avg_mi, 2),
            "quality_distribution": {
                rating.value: sum(1 for m in metrics_list if m.quality_rating == rating)
                for rating in QualityRating
            },
        }
