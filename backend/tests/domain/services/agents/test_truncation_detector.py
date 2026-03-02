"""
Unit tests for TruncationDetector (Incomplete Output Detection).

Tests cover:
- TruncationPattern validation
- TruncationAssessment structure
- Pattern-based detection (5 patterns)
- Confidence scoring
- Continuation prompt generation
- Finish reason detection
- Singleton factory pattern
- Edge cases
"""

import pytest

from app.domain.services.agents.truncation_detector import (
    TruncationAssessment,
    TruncationDetector,
    TruncationPattern,
    get_truncation_detector,
)

# ============================================================================
# Test Class 1: TruncationPattern Validation
# ============================================================================


class TestTruncationPatternValidation:
    """Test TruncationPattern Pydantic validation."""

    def test_pattern_valid(self):
        """Valid TruncationPattern should pass validation."""
        pattern = TruncationPattern(
            name="test_pattern",
            pattern=r"test.*pattern",
            truncation_type="test_type",
            confidence=0.85,
            continuation_prompt="Please continue...",
        )
        assert pattern.name == "test_pattern"
        assert pattern.confidence == 0.85

    def test_pattern_confidence_validation_invalid_high(self):
        """Confidence > 1.0 should raise ValueError."""
        with pytest.raises(ValueError):
            TruncationPattern(
                name="test",
                pattern=r"test",
                truncation_type="test",
                confidence=1.5,
                continuation_prompt="test",
            )

    def test_pattern_confidence_validation_invalid_low(self):
        """Confidence < 0.0 should raise ValueError."""
        with pytest.raises(ValueError):
            TruncationPattern(
                name="test",
                pattern=r"test",
                truncation_type="test",
                confidence=-0.1,
                continuation_prompt="test",
            )

    def test_pattern_default_confidence(self):
        """Pattern should have default confidence of 0.8."""
        pattern = TruncationPattern(
            name="test",
            pattern=r"test",
            truncation_type="test",
            continuation_prompt="test",
        )
        assert pattern.confidence == 0.8


# ============================================================================
# Test Class 2: TruncationAssessment Structure
# ============================================================================


class TestTruncationAssessmentStructure:
    """Test TruncationAssessment dataclass."""

    def test_assessment_no_truncation(self):
        """Assessment with no truncation should have correct defaults."""
        assessment = TruncationAssessment(is_truncated=False)
        assert assessment.is_truncated is False
        assert assessment.truncation_type is None
        assert assessment.confidence == 1.0
        assert assessment.continuation_prompt is None

    def test_assessment_with_truncation(self):
        """Assessment with truncation should include all details."""
        assessment = TruncationAssessment(
            is_truncated=True,
            truncation_type="mid_code",
            confidence=0.95,
            continuation_prompt="Please complete...",
            evidence=["Pattern: unclosed_code"],
        )
        assert assessment.is_truncated is True
        assert assessment.truncation_type == "mid_code"
        assert assessment.confidence == 0.95
        assert len(assessment.evidence) == 1


# ============================================================================
# Test Class 3: Default Patterns
# ============================================================================


class TestDefaultPatterns:
    """Test DEFAULT_PATTERNS class variable."""

    def test_default_patterns_exist(self):
        """DEFAULT_PATTERNS should be defined with truncation placeholder coverage."""
        assert len(TruncationDetector.DEFAULT_PATTERNS) == 6

    def test_default_patterns_types(self):
        """All default patterns should be TruncationPattern objects."""
        for pattern in TruncationDetector.DEFAULT_PATTERNS:
            assert isinstance(pattern, TruncationPattern)
            assert 0.0 <= pattern.confidence <= 1.0

    def test_default_pattern_names(self):
        """Should have expected pattern names."""
        pattern_names = [p.name for p in TruncationDetector.DEFAULT_PATTERNS]
        expected = [
            "unclosed_code_block",
            "mid_sentence_no_punctuation",
            "unclosed_json_structure",
            "incomplete_list",
            "truncation_phrase",
            "placeholder_ellipsis_artifact",
        ]
        for expected_name in expected:
            assert expected_name in pattern_names


# ============================================================================
# Test Class 4: Detector Initialization
# ============================================================================


class TestDetectorInitialization:
    """Test TruncationDetector initialization."""

    def test_init_with_defaults(self):
        """Detector should initialize with default patterns."""
        detector = TruncationDetector()
        assert len(detector.patterns) == 6

    def test_init_with_custom_patterns(self):
        """Detector should accept custom patterns."""
        custom = [
            TruncationPattern(
                name="custom",
                pattern=r"custom",
                truncation_type="custom",
                continuation_prompt="Custom",
            )
        ]
        detector = TruncationDetector(patterns=custom)
        assert len(detector.patterns) == 1
        assert detector.patterns[0].name == "custom"


# ============================================================================
# Test Class 5: Unclosed Code Block Detection
# ============================================================================


class TestUnclosedCodeBlockDetection:
    """Test unclosed_code_block pattern."""

    def test_detects_unclosed_python(self):
        """Should detect unclosed Python code block."""
        detector = TruncationDetector()
        content = "```python\ndef function():\n    return"

        assessment = detector.detect(content)
        assert assessment.is_truncated is True
        assert assessment.confidence > 0.9

    def test_closed_code_not_truncated(self):
        """Should not detect closed code block."""
        detector = TruncationDetector()
        content = "```python\ndef function():\n    return 42\n```"

        assessment = detector.detect(content)
        assert assessment.is_truncated is False


# ============================================================================
# Test Class 6: Finish Reason Detection
# ============================================================================


class TestFinishReasonDetection:
    """Test finish_reason parameter handling."""

    def test_finish_reason_length_triggers(self):
        """finish_reason='length' should trigger truncation."""
        detector = TruncationDetector()
        assessment = detector.detect("Normal content", finish_reason="length")

        assert assessment.is_truncated is True
        assert assessment.truncation_type == "max_tokens"
        assert assessment.confidence == 0.99

    def test_finish_reason_stop_no_trigger(self):
        """finish_reason='stop' should not auto-trigger."""
        detector = TruncationDetector()
        assessment = detector.detect("Complete sentence.", finish_reason="stop")

        assert assessment.is_truncated is False


# ============================================================================
# Test Class 7: Continuation Decision
# ============================================================================


class TestContinuationDecision:
    """Test should_request_continuation method."""

    def test_should_continue_high_confidence(self):
        """High confidence truncation should request continuation."""
        detector = TruncationDetector()
        assessment = TruncationAssessment(
            is_truncated=True,
            confidence=0.95,
            continuation_prompt="Continue...",
        )

        assert detector.should_request_continuation(assessment, confidence_threshold=0.8) is True

    def test_should_not_continue_low_confidence(self):
        """Low confidence should not request continuation."""
        detector = TruncationDetector()
        assessment = TruncationAssessment(
            is_truncated=True,
            confidence=0.5,
            continuation_prompt="Continue...",
        )

        assert detector.should_request_continuation(assessment, confidence_threshold=0.8) is False

    def test_should_not_continue_not_truncated(self):
        """Non-truncated should not request continuation."""
        detector = TruncationDetector()
        assessment = TruncationAssessment(is_truncated=False)

        assert detector.should_request_continuation(assessment) is False


# ============================================================================
# Test Class 8: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_content(self):
        """Empty content should not be truncated."""
        detector = TruncationDetector()
        assessment = detector.detect("")
        assert assessment.is_truncated is False

    def test_whitespace_only(self):
        """Whitespace-only should not be truncated."""
        detector = TruncationDetector()
        assessment = detector.detect("   \n\t  ")
        assert assessment.is_truncated is False

    def test_very_long_content(self):
        """Very long content should not break detection."""
        detector = TruncationDetector()
        long_content = "x" * 100000
        assessment = detector.detect(long_content)
        assert isinstance(assessment, TruncationAssessment)

    def test_detects_placeholder_ellipsis_artifact(self):
        """Standalone '[...]' / '[…]' placeholders should be treated as truncation artifacts."""
        detector = TruncationDetector()
        assessment = detector.detect("Report content\n[...]")
        assert assessment.is_truncated is True


# ============================================================================
# Test Class 9: Singleton Factory
# ============================================================================


class TestSingletonFactory:
    """Test get_truncation_detector singleton."""

    def test_singleton_returns_same_instance(self):
        """Should return same instance on multiple calls."""
        # Clear singleton
        import app.domain.services.agents.truncation_detector as module

        module._truncation_detector = None

        detector1 = get_truncation_detector()
        detector2 = get_truncation_detector()

        assert detector1 is detector2


# ============================================================================
# Test Class 10: Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for full workflow."""

    def test_complete_workflow_incomplete_code(self):
        """Full workflow: detect → assess → decide continuation."""
        detector = TruncationDetector()

        # Step 1: Detect
        content = "```python\ndef incomplete():\n    pass"
        assessment = detector.detect(content)

        # Step 2: Verify detection
        assert assessment.is_truncated is True
        assert assessment.confidence > 0.9

        # Step 3: Check continuation decision
        should_continue = detector.should_request_continuation(assessment, confidence_threshold=0.85)
        assert should_continue is True

    def test_complete_workflow_with_finish_stop(self):
        """Finish reason 'stop' with simple content should not trigger."""
        detector = TruncationDetector()

        content = "This is a complete sentence with proper ending."
        assessment = detector.detect(content, finish_reason="stop")

        # Should not be truncated (no patterns match)
        assert assessment.is_truncated is False
        should_continue = detector.should_request_continuation(assessment)
        assert should_continue is False
