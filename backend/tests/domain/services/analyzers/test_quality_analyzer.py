"""Tests for the code quality analyzer."""

import pytest

from app.domain.services.analyzers.quality_analyzer import (
    CodeMetrics,
    ComplexityVisitor,
    FunctionMetrics,
    QualityAnalyzer,
    QualityIssue,
    QualityRating,
)

# ---------------------------------------------------------------------------
# QualityRating enum
# ---------------------------------------------------------------------------


class TestQualityRating:
    """Test QualityRating enum values and string behaviour."""

    def test_all_members_present(self) -> None:
        """All five rating levels must exist."""
        members = {r.value for r in QualityRating}
        assert members == {"excellent", "good", "moderate", "poor", "critical"}

    def test_is_str_enum(self) -> None:
        """QualityRating is a str enum — values compare equal to plain strings."""
        assert QualityRating.EXCELLENT == "excellent"
        assert QualityRating.GOOD == "good"
        assert QualityRating.MODERATE == "moderate"
        assert QualityRating.POOR == "poor"
        assert QualityRating.CRITICAL == "critical"

    def test_membership_from_value(self) -> None:
        """Should construct members from their string values."""
        assert QualityRating("excellent") is QualityRating.EXCELLENT
        assert QualityRating("critical") is QualityRating.CRITICAL

    def test_ordering_of_constants(self) -> None:
        """EXCELLENT should not equal CRITICAL."""
        assert QualityRating.EXCELLENT != QualityRating.CRITICAL


# ---------------------------------------------------------------------------
# ComplexityVisitor
# ---------------------------------------------------------------------------


class TestComplexityVisitor:
    """Test AST complexity visitor increments correctly."""

    def _visit(self, source: str) -> ComplexityVisitor:
        import ast

        tree = ast.parse(source)
        v = ComplexityVisitor()
        v.visit(tree)
        return v

    def test_base_complexity_is_one(self) -> None:
        """An empty module starts at complexity 1."""
        v = self._visit("x = 1")
        assert v.complexity == 1

    def test_if_adds_one(self) -> None:
        """Each If branch adds 1 to complexity."""
        v = self._visit("if x:\n    pass")
        assert v.complexity == 2

    def test_for_loop_adds_one(self) -> None:
        """A for loop adds 1 to complexity."""
        v = self._visit("for i in range(10):\n    pass")
        assert v.complexity == 2

    def test_while_loop_adds_one(self) -> None:
        """A while loop adds 1 to complexity."""
        v = self._visit("while True:\n    break")
        assert v.complexity == 2

    def test_boolop_and_two_operands_adds_one(self) -> None:
        """'a and b' (2 values) adds len(values)-1 == 1."""
        v = self._visit("result = a and b")
        assert v.complexity == 2

    def test_boolop_or_three_operands_adds_two(self) -> None:
        """'a or b or c' (3 values) adds 2."""
        v = self._visit("result = a or b or c")
        assert v.complexity == 3

    def test_if_increments_nesting(self) -> None:
        """If statement must update max_nesting."""
        v = self._visit("if x:\n    pass")
        assert v.max_nesting == 1

    def test_for_increments_nesting(self) -> None:
        """For loop must update max_nesting."""
        v = self._visit("for i in []:\n    pass")
        assert v.max_nesting == 1

    def test_while_increments_nesting(self) -> None:
        """While loop must update max_nesting."""
        v = self._visit("while False:\n    pass")
        assert v.max_nesting == 1

    def test_nested_if_inside_for_nesting_depth_two(self) -> None:
        """For with an inner if must reach nesting depth 2."""
        source = "for i in []:\n    if i:\n        pass"
        v = self._visit(source)
        assert v.max_nesting == 2

    def test_with_statement_increments_nesting_only(self) -> None:
        """With does not add to complexity but does add nesting."""
        source = "with open('f') as f:\n    pass"
        v = self._visit(source)
        # complexity stays at 1, nesting goes to 1
        assert v.complexity == 1
        assert v.max_nesting == 1

    def test_except_handler_adds_complexity(self) -> None:
        """ExceptHandler adds 1 to complexity."""
        source = "try:\n    pass\nexcept Exception:\n    pass"
        v = self._visit(source)
        assert v.complexity == 2

    def test_list_comprehension_adds_complexity(self) -> None:
        """Comprehension clause adds 1."""
        source = "[x for x in items]"
        v = self._visit(source)
        assert v.complexity == 2

    def test_lambda_adds_complexity(self) -> None:
        """Lambda adds 1."""
        source = "fn = lambda x: x"
        v = self._visit(source)
        assert v.complexity == 2

    def test_combined_constructs_accumulate(self) -> None:
        """Multiple constructs accumulate correctly."""
        source = "for i in range(10):\n    if i > 5:\n        pass\n    elif i == 3:\n        pass\n"
        v = self._visit(source)
        # for=1, if=1, elif treated as additional If by AST = 1 → base 1 + 3 = 4
        assert v.complexity >= 4


# ---------------------------------------------------------------------------
# QualityAnalyzer.analyze — Python path
# ---------------------------------------------------------------------------


SIMPLE_PYTHON = """\
def add(a, b):
    return a + b
"""

COMPLEX_PYTHON = """\
def big_function(a, b, c, d, e, f):
    if a:
        for i in range(10):
            if b:
                while c:
                    if d:
                        pass
    elif e:
        pass
    if a and b and c:
        pass
    return a or b
"""


class TestAnalyzePython:
    """Test analyze() for Python source code."""

    def test_returns_tuple_of_metrics_and_issues(self) -> None:
        """analyze() must return a (CodeMetrics, list) tuple."""
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(SIMPLE_PYTHON, "simple.py", "python")
        assert isinstance(result, tuple)
        assert len(result) == 2
        metrics, issues = result
        assert isinstance(metrics, CodeMetrics)
        assert isinstance(issues, list)

    def test_simple_code_has_no_issues(self) -> None:
        """A two-line function should raise no quality issues."""
        analyzer = QualityAnalyzer()
        _, issues = analyzer.analyze(SIMPLE_PYTHON, "simple.py", "python")
        assert issues == []

    def test_simple_code_function_count(self) -> None:
        """Simple code with one function should report one function."""
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(SIMPLE_PYTHON, "simple.py", "python")
        assert len(metrics.functions) == 1
        assert metrics.functions[0].name == "add"

    def test_function_parameter_count(self) -> None:
        """Function metrics capture the correct parameter count."""
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(SIMPLE_PYTHON, "simple.py", "python")
        assert metrics.functions[0].parameters == 2

    def test_file_path_stored(self) -> None:
        """file_path is preserved in CodeMetrics."""
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(SIMPLE_PYTHON, "my/file.py", "python")
        assert metrics.file_path == "my/file.py"

    def test_line_counts_are_positive(self) -> None:
        """Line counts must be non-negative and sum to total_lines."""
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(SIMPLE_PYTHON, "f.py", "python")
        assert metrics.total_lines > 0
        assert metrics.code_lines + metrics.comment_lines + metrics.blank_lines == metrics.total_lines

    def test_comment_line_counted(self) -> None:
        """Lines starting with # must be counted as comment lines."""
        source = "# comment\nx = 1\n"
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(source, "f.py", "python")
        assert metrics.comment_lines == 1

    def test_blank_line_counted(self) -> None:
        """Blank lines must be counted separately."""
        source = "x = 1\n\ny = 2\n"
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(source, "f.py", "python")
        assert metrics.blank_lines >= 1

    def test_import_counted(self) -> None:
        """Import statements must be counted."""
        source = "import os\nfrom pathlib import Path\nx = 1\n"
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(source, "f.py", "python")
        assert metrics.imports == 2

    def test_class_counted(self) -> None:
        """Class definitions must be counted."""
        source = "class Foo:\n    pass\nclass Bar:\n    pass\n"
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(source, "f.py", "python")
        assert metrics.classes == 2

    def test_quality_rating_type(self) -> None:
        """quality_rating must be a QualityRating member."""
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(SIMPLE_PYTHON, "f.py", "python")
        assert isinstance(metrics.quality_rating, QualityRating)

    def test_average_complexity_at_least_one(self) -> None:
        """average_complexity must be >= 1 for any code."""
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(SIMPLE_PYTHON, "f.py", "python")
        assert metrics.average_complexity >= 1.0

    def test_no_functions_gives_default_complexity(self) -> None:
        """Code with no functions defaults avg/max complexity to 1."""
        source = "x = 1\ny = 2\n"
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(source, "f.py", "python")
        assert metrics.average_complexity == 1.0
        assert metrics.max_complexity == 1

    def test_complex_code_max_complexity_gt_simple(self) -> None:
        """Complex branching code should have higher max complexity."""
        analyzer = QualityAnalyzer()
        simple_metrics, _ = analyzer.analyze(SIMPLE_PYTHON, "s.py", "python")
        complex_metrics, _ = analyzer.analyze(COMPLEX_PYTHON, "c.py", "python")
        assert complex_metrics.max_complexity > simple_metrics.max_complexity

    def test_to_dict_returns_dict(self) -> None:
        """CodeMetrics.to_dict() must return a plain dict."""
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(SIMPLE_PYTHON, "f.py", "python")
        d = metrics.to_dict()
        assert isinstance(d, dict)
        assert "file_path" in d
        assert "quality_rating" in d
        # quality_rating in dict is the string value, not the enum
        assert isinstance(d["quality_rating"], str)

    def test_to_dict_comment_ratio_key_present(self) -> None:
        """CodeMetrics.to_dict() must include a comment_ratio key."""
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(SIMPLE_PYTHON, "f.py", "python")
        d = metrics.to_dict()
        assert "comment_ratio" in d

    def test_async_function_detected(self) -> None:
        """Async functions must be detected the same as regular ones."""
        source = "async def fetch(url):\n    return url\n"
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(source, "f.py", "python")
        assert len(metrics.functions) == 1
        assert metrics.functions[0].name == "fetch"


# ---------------------------------------------------------------------------
# Non-Python fallback
# ---------------------------------------------------------------------------


class TestAnalyzeNonPython:
    """Test analyze() generic fallback for non-Python languages."""

    def test_javascript_returns_metrics(self) -> None:
        """Non-Python code must still return CodeMetrics."""
        analyzer = QualityAnalyzer()
        source = "// comment\nconst x = 1;\n"
        metrics, issues = analyzer.analyze(source, "app.js", "javascript")
        assert isinstance(metrics, CodeMetrics)
        assert issues == []

    def test_non_python_has_no_functions(self) -> None:
        """Generic analysis always has empty functions list."""
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze("function foo(){}", "f.js", "javascript")
        assert metrics.functions == []

    def test_non_python_fixed_complexity(self) -> None:
        """Generic analysis sets complexity to 1."""
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze("x = 1;", "f.js", "javascript")
        assert metrics.average_complexity == 1.0
        assert metrics.max_complexity == 1

    def test_non_python_moderate_rating(self) -> None:
        """Generic analysis always returns MODERATE quality rating."""
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze("x = 1;", "f.js", "javascript")
        assert metrics.quality_rating == QualityRating.MODERATE

    def test_non_python_fixed_maintainability(self) -> None:
        """Generic analysis sets maintainability to 50."""
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze("x;", "f.js", "javascript")
        assert metrics.maintainability_index == 50.0

    def test_non_python_counts_comment_lines(self) -> None:
        """// and # comment prefixes must be counted for generic code."""
        source = "// comment\n# another\nconst x = 1;\n"
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(source, "f.js", "javascript")
        assert metrics.comment_lines == 2


# ---------------------------------------------------------------------------
# Syntax error fallback
# ---------------------------------------------------------------------------


class TestSyntaxErrorFallback:
    """analyze() must gracefully handle syntax errors."""

    def test_syntax_error_falls_back_to_generic(self) -> None:
        """Invalid Python falls back to generic analysis returning MODERATE."""
        analyzer = QualityAnalyzer()
        bad_code = "def foo(:\n    pass\n"
        metrics, issues = analyzer.analyze(bad_code, "bad.py", "python")
        assert isinstance(metrics, CodeMetrics)
        assert issues == []
        assert metrics.quality_rating == QualityRating.MODERATE

    def test_syntax_error_has_no_functions(self) -> None:
        """Fallback from syntax error returns no function metrics."""
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze("def (:", "err.py", "python")
        assert metrics.functions == []


# ---------------------------------------------------------------------------
# _calculate_maintainability_index
# ---------------------------------------------------------------------------


class TestCalculateMaintainabilityIndex:
    """Test the maintainability index calculation directly."""

    def setup_method(self) -> None:
        self.analyzer = QualityAnalyzer()

    def test_zero_loc_returns_100(self) -> None:
        """Zero lines of code must return 100.0 (perfect)."""
        mi = self.analyzer._calculate_maintainability_index(0, 1.0, 0)
        assert mi == 100.0

    def test_result_clamped_to_0_100(self) -> None:
        """Result must always be in [0, 100]."""
        for loc in [1, 10, 100, 1000]:
            for cc in [1.0, 10.0, 50.0]:
                mi = self.analyzer._calculate_maintainability_index(loc, cc, 0)
                assert 0.0 <= mi <= 100.0

    def test_comments_improve_score(self) -> None:
        """More comment lines should yield a higher or equal MI than no comments."""
        mi_no_comments = self.analyzer._calculate_maintainability_index(50, 5.0, 0)
        mi_with_comments = self.analyzer._calculate_maintainability_index(50, 5.0, 20)
        assert mi_with_comments >= mi_no_comments

    def test_higher_complexity_lowers_score(self) -> None:
        """Higher cyclomatic complexity must reduce the MI.

        Uses loc=200 to ensure the log(LOC) factor brings the raw MI below
        100 for both inputs, so the complexity contribution is not masked
        by the max(0, min(100, ...)) clamp.
        """
        mi_low = self.analyzer._calculate_maintainability_index(200, 2.0, 0)
        mi_high = self.analyzer._calculate_maintainability_index(200, 20.0, 0)
        assert mi_low > mi_high

    def test_larger_loc_generally_lowers_score(self) -> None:
        """Many lines of code tends to reduce MI (log factor dominates)."""
        mi_small = self.analyzer._calculate_maintainability_index(10, 1.0, 0)
        mi_large = self.analyzer._calculate_maintainability_index(500, 1.0, 0)
        assert mi_small > mi_large


# ---------------------------------------------------------------------------
# _get_quality_rating boundaries
# ---------------------------------------------------------------------------


class TestGetQualityRating:
    """Test the rating bucket boundaries exactly."""

    def setup_method(self) -> None:
        self.analyzer = QualityAnalyzer()

    def test_100_is_excellent(self) -> None:
        assert self.analyzer._get_quality_rating(100.0) == QualityRating.EXCELLENT

    def test_80_is_excellent(self) -> None:
        assert self.analyzer._get_quality_rating(80.0) == QualityRating.EXCELLENT

    def test_79_is_good(self) -> None:
        assert self.analyzer._get_quality_rating(79.9) == QualityRating.GOOD

    def test_60_is_good(self) -> None:
        assert self.analyzer._get_quality_rating(60.0) == QualityRating.GOOD

    def test_59_is_moderate(self) -> None:
        assert self.analyzer._get_quality_rating(59.9) == QualityRating.MODERATE

    def test_40_is_moderate(self) -> None:
        assert self.analyzer._get_quality_rating(40.0) == QualityRating.MODERATE

    def test_39_is_poor(self) -> None:
        assert self.analyzer._get_quality_rating(39.9) == QualityRating.POOR

    def test_20_is_poor(self) -> None:
        assert self.analyzer._get_quality_rating(20.0) == QualityRating.POOR

    def test_19_is_critical(self) -> None:
        assert self.analyzer._get_quality_rating(19.9) == QualityRating.CRITICAL

    def test_0_is_critical(self) -> None:
        assert self.analyzer._get_quality_rating(0.0) == QualityRating.CRITICAL


# ---------------------------------------------------------------------------
# _estimate_duplication
# ---------------------------------------------------------------------------


class TestEstimateDuplication:
    """Test duplication estimation logic."""

    def setup_method(self) -> None:
        self.analyzer = QualityAnalyzer()

    def test_short_input_returns_zero(self) -> None:
        """Files with fewer than 10 lines always return 0.0."""
        lines = ["x = 1"] * 5
        assert self.analyzer._estimate_duplication(lines) == 0.0

    def test_no_duplication_returns_zero(self) -> None:
        """Unique lines must yield 0.0 duplication."""
        lines = [f"x_{i} = {i}" for i in range(20)]
        ratio = self.analyzer._estimate_duplication(lines)
        assert ratio == 0.0

    def test_full_duplication_returns_high_ratio(self) -> None:
        """Many identical long lines should produce a ratio > 0."""
        lines = ["very_long_duplicated_line_of_code = True"] * 20
        ratio = self.analyzer._estimate_duplication(lines)
        assert ratio > 0.0

    def test_short_lines_not_counted(self) -> None:
        """Lines with 10 or fewer characters must be ignored in duplication."""
        # All lines are <= 10 chars so no duplicates counted
        lines = ["x = 1"] * 20
        ratio = self.analyzer._estimate_duplication(lines)
        assert ratio == 0.0

    def test_comment_lines_excluded(self) -> None:
        """Lines starting with # are excluded from duplication detection."""
        lines = ["# comment"] * 20 + [f"y_{i} = {i}" for i in range(5)]
        ratio = self.analyzer._estimate_duplication(lines)
        assert ratio == 0.0


# ---------------------------------------------------------------------------
# get_summary
# ---------------------------------------------------------------------------


class TestGetSummary:
    """Test get_summary across multiple CodeMetrics objects."""

    def _make_metrics(
        self,
        file_path: str = "f.py",
        code_lines: int = 10,
        mi: float = 75.0,
        rating: QualityRating = QualityRating.GOOD,
        functions: list[FunctionMetrics] | None = None,
    ) -> CodeMetrics:
        return CodeMetrics(
            file_path=file_path,
            total_lines=code_lines,
            code_lines=code_lines,
            comment_lines=0,
            blank_lines=0,
            functions=functions or [],
            classes=0,
            imports=0,
            average_complexity=1.0,
            max_complexity=1,
            maintainability_index=mi,
            quality_rating=rating,
        )

    def test_empty_list_returns_files_zero(self) -> None:
        """Empty metrics list must return {'files': 0}."""
        analyzer = QualityAnalyzer()
        result = analyzer.get_summary([])
        assert result == {"files": 0}

    def test_files_analyzed_count(self) -> None:
        """files_analyzed must match the length of the input list."""
        analyzer = QualityAnalyzer()
        metrics = [self._make_metrics(f"f{i}.py") for i in range(3)]
        result = analyzer.get_summary(metrics)
        assert result["files_analyzed"] == 3

    def test_total_lines_of_code_summed(self) -> None:
        """total_lines_of_code must be the sum of all code_lines."""
        analyzer = QualityAnalyzer()
        metrics = [self._make_metrics(code_lines=20), self._make_metrics(code_lines=30)]
        result = analyzer.get_summary(metrics)
        assert result["total_lines_of_code"] == 50

    def test_total_functions_summed(self) -> None:
        """total_functions must count functions across all files."""
        analyzer = QualityAnalyzer()
        fn = FunctionMetrics(
            name="foo",
            line_start=1,
            line_end=5,
            cyclomatic_complexity=1,
            lines_of_code=5,
            parameters=0,
            nesting_depth=0,
        )
        m1 = self._make_metrics(functions=[fn])
        m2 = self._make_metrics(functions=[fn, fn])
        result = analyzer.get_summary([m1, m2])
        assert result["total_functions"] == 3

    def test_average_maintainability_computed(self) -> None:
        """average_maintainability must be the mean of all MI values."""
        analyzer = QualityAnalyzer()
        metrics = [self._make_metrics(mi=80.0), self._make_metrics(mi=60.0)]
        result = analyzer.get_summary(metrics)
        assert result["average_maintainability"] == pytest.approx(70.0, rel=1e-3)

    def test_quality_distribution_keys(self) -> None:
        """quality_distribution must contain all QualityRating values as keys."""
        analyzer = QualityAnalyzer()
        metrics = [self._make_metrics()]
        result = analyzer.get_summary(metrics)
        dist = result["quality_distribution"]
        for rating in QualityRating:
            assert rating.value in dist

    def test_quality_distribution_counts(self) -> None:
        """quality_distribution must count files per rating correctly."""
        analyzer = QualityAnalyzer()
        m_good = self._make_metrics(rating=QualityRating.GOOD)
        m_poor = self._make_metrics(rating=QualityRating.POOR)
        result = analyzer.get_summary([m_good, m_good, m_poor])
        assert result["quality_distribution"]["good"] == 2
        assert result["quality_distribution"]["poor"] == 1
        assert result["quality_distribution"]["excellent"] == 0


# ---------------------------------------------------------------------------
# Issue detection
# ---------------------------------------------------------------------------


class TestIssueDetection:
    """Test that issues are raised for known threshold violations."""

    def test_high_complexity_warning_issued(self) -> None:
        """A function with complexity >= 10 (warning) must generate an issue."""
        # Build a function that crosses the 10-threshold but not 20
        branches = "\n".join(f"    if x_{i}:\n        pass" for i in range(10))
        source = f"def complex_fn(x_0, x_1, x_2, x_3, x_4, x_5, x_6, x_7, x_8, x_9):\n{branches}\n"
        analyzer = QualityAnalyzer()
        _, issues = analyzer.analyze(source, "f.py", "python")
        complexity_issues = [i for i in issues if i.type == "high_complexity"]
        assert len(complexity_issues) >= 1
        assert any(i.severity in ("warning", "critical") for i in complexity_issues)

    def test_high_complexity_critical_issued(self) -> None:
        """A function with complexity >= 20 must be flagged as critical."""
        # 20 if branches inside a function → complexity = 1 + 20 = 21
        branches = "\n".join(f"    if cond_{i}:\n        pass" for i in range(20))
        params = ", ".join(f"cond_{i}" for i in range(20))
        source = f"def very_complex({params}):\n{branches}\n"
        analyzer = QualityAnalyzer()
        _, issues = analyzer.analyze(source, "f.py", "python")
        critical = [i for i in issues if i.type == "high_complexity" and i.severity == "critical"]
        assert len(critical) >= 1

    def test_long_function_warning_issued(self) -> None:
        """A function with 50+ lines must generate a long_function issue."""
        body = "\n".join(f"    x_{i} = {i}" for i in range(55))
        source = f"def long_fn():\n{body}\n"
        analyzer = QualityAnalyzer()
        _, issues = analyzer.analyze(source, "f.py", "python")
        long_issues = [i for i in issues if i.type == "long_function"]
        assert len(long_issues) >= 1

    def test_too_many_parameters_issued(self) -> None:
        """A function with more than 5 parameters must generate a too_many_parameters issue."""
        source = "def many_params(a, b, c, d, e, f):\n    pass\n"
        analyzer = QualityAnalyzer()
        _, issues = analyzer.analyze(source, "f.py", "python")
        param_issues = [i for i in issues if i.type == "too_many_parameters"]
        assert len(param_issues) == 1
        assert param_issues[0].severity == "warning"
        assert param_issues[0].function_name == "many_params"

    def test_deep_nesting_issued(self) -> None:
        """Nesting deeper than 4 levels must generate a deep_nesting issue."""
        source = (
            "def deep(a, b, c, d, e):\n"
            "    if a:\n"
            "        if b:\n"
            "            if c:\n"
            "                if d:\n"
            "                    if e:\n"
            "                        pass\n"
        )
        analyzer = QualityAnalyzer()
        _, issues = analyzer.analyze(source, "f.py", "python")
        nesting_issues = [i for i in issues if i.type == "deep_nesting"]
        assert len(nesting_issues) >= 1

    def test_issue_to_dict_has_required_keys(self) -> None:
        """QualityIssue.to_dict() must include all standard keys."""
        issue = QualityIssue(
            type="high_complexity",
            severity="warning",
            description="desc",
            file_path="f.py",
            line_number=10,
            function_name="fn",
            recommendation="refactor",
        )
        d = issue.to_dict()
        for key in ("type", "severity", "description", "file_path", "line_number", "function_name", "recommendation"):
            assert key in d

    def test_issue_line_number_matches_function_start(self) -> None:
        """Issue line_number must point to the function definition line."""
        source = "\n\ndef simple_fn(a, b, c, d, e, f):\n    pass\n"
        analyzer = QualityAnalyzer()
        _, issues = analyzer.analyze(source, "f.py", "python")
        param_issues = [i for i in issues if i.type == "too_many_parameters"]
        assert len(param_issues) == 1
        # Function starts on line 3 (two blank lines precede it)
        assert param_issues[0].line_number == 3


# ---------------------------------------------------------------------------
# FunctionMetrics dataclass
# ---------------------------------------------------------------------------


class TestFunctionMetrics:
    """Test FunctionMetrics dataclass construction and serialisation."""

    def test_to_dict_contains_all_fields(self) -> None:
        fm = FunctionMetrics(
            name="foo",
            line_start=1,
            line_end=10,
            cyclomatic_complexity=3,
            lines_of_code=10,
            parameters=2,
            nesting_depth=1,
        )
        d = fm.to_dict()
        assert d["name"] == "foo"
        assert d["line_start"] == 1
        assert d["line_end"] == 10
        assert d["cyclomatic_complexity"] == 3
        assert d["lines_of_code"] == 10
        assert d["parameters"] == 2
        assert d["nesting_depth"] == 1

    def test_lines_of_code_computed_by_analyzer(self) -> None:
        """lines_of_code in FunctionMetrics must equal line_end - line_start + 1."""
        source = "def fn():\n    x = 1\n    y = 2\n    return x + y\n"
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(source, "f.py", "python")
        fn = metrics.functions[0]
        assert fn.lines_of_code == fn.line_end - fn.line_start + 1

    def test_vararg_counted_as_parameter(self) -> None:
        """*args must add 1 to the parameter count."""
        source = "def fn(a, b, *args):\n    pass\n"
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(source, "f.py", "python")
        assert metrics.functions[0].parameters == 3

    def test_kwarg_counted_as_parameter(self) -> None:
        """**kwargs must add 1 to the parameter count."""
        source = "def fn(a, **kwargs):\n    pass\n"
        analyzer = QualityAnalyzer()
        metrics, _ = analyzer.analyze(source, "f.py", "python")
        assert metrics.functions[0].parameters == 2
