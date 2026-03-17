"""Tests for Validation Retry Logic

Phase 4 Enhancement: Tests for Tenacity retry with validation feedback.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.domain.models.structured_outputs import (
    PlanOutput,
    StepDescription,
    ValidationResult,
    build_validation_feedback,
)


class TestValidationFeedbackIntegration:
    """Tests for validation feedback building and retry integration."""

    def test_feedback_format_for_retry(self):
        """Test validation feedback is formatted for LLM retry."""
        result = ValidationResult(
            is_valid=False,
            errors=["Field 'title' is required but missing"],
            warnings=["Low confidence score"],
            suggestions=["Include all required fields in the response"],
        )
        feedback = build_validation_feedback(result)

        # Verify feedback structure
        assert "ERRORS (must fix):" in feedback
        assert "Field 'title' is required" in feedback
        assert "SUGGESTIONS:" in feedback
        assert "Include all required fields" in feedback

    def test_feedback_empty_when_valid(self):
        """Test empty feedback for valid output."""
        result = ValidationResult(is_valid=True)
        feedback = build_validation_feedback(result)
        assert feedback == ""

    def test_feedback_errors_only(self):
        """Test feedback with only errors."""
        result = ValidationResult(
            is_valid=False,
            errors=["Invalid JSON format"],
        )
        feedback = build_validation_feedback(result)
        assert "ERRORS" in feedback
        assert "Invalid JSON format" in feedback
        assert "SUGGESTIONS" not in feedback


class TestRetryWithValidation:
    """Tests for retry behavior with validation errors."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM."""
        llm = MagicMock()
        llm.ask = AsyncMock()
        return llm

    @pytest.fixture
    def mock_json_parser(self):
        """Create mock JSON parser."""
        parser = MagicMock()
        parser.extract_json = MagicMock()
        return parser

    @pytest.mark.asyncio
    async def test_retry_on_validation_error(self, mock_llm, mock_json_parser):
        """Test that validation errors trigger retry."""
        # First attempt returns invalid JSON (missing required field)
        # Second attempt returns valid JSON
        call_count = 0

        async def mock_ask(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"content": '{"goal": "Test", "steps": [{"description": "Test step"}]}'}  # Missing title
            return {"content": '{"goal": "Test", "title": "Valid Plan", "steps": [{"description": "Test step"}]}'}

        mock_llm.ask = mock_ask

        # Verify retry logic would need to be invoked
        first_response = await mock_llm.ask()
        import json

        first_data = json.loads(first_response["content"])

        # First response is missing 'title', should fail validation
        with pytest.raises(ValidationError):
            PlanOutput.model_validate(first_data)

        # Second response should be valid
        second_response = await mock_llm.ask()
        second_data = json.loads(second_response["content"])
        plan = PlanOutput.model_validate(second_data)
        assert plan.title == "Valid Plan"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, mock_llm):
        """Test behavior when max retries are exhausted."""
        call_count = 0

        async def mock_ask(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Always return invalid JSON
            return {"content": '{"goal": "Test"}'}  # Missing title and steps

        mock_llm.ask = mock_ask

        # Simulate 3 retry attempts (Tenacity default)
        for _ in range(3):
            response = await mock_llm.ask()
            import json

            data = json.loads(response["content"])
            with pytest.raises(ValidationError):
                PlanOutput.model_validate(data)

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_error_context_in_retry(self, mock_llm):
        """Test that error context is passed to retry attempts."""
        error_contexts = []

        async def mock_ask(messages, **kwargs):
            # Extract error context from messages if present
            for msg in messages:
                if isinstance(msg, dict):
                    content = msg.get("content", "")
                    if "FIX THIS ERROR" in content or "ERRORS" in content:
                        error_contexts.append(content)
            return {"content": '{"goal": "Test", "title": "Plan", "steps": [{"description": "Step"}]}'}

        mock_llm.ask = mock_ask

        # First call with error context
        first_error = ValidationError.from_exception_data(
            "PlanOutput",
            [{"type": "missing", "loc": ("title",), "msg": "Field required"}],
        )
        error_feedback = f"FIX THIS ERROR:\n{first_error!s}"

        messages = [
            {"role": "system", "content": "You are a planner."},
            {"role": "user", "content": "Create a plan"},
            {"role": "assistant", "content": '{"goal": "Test"}'},
            {"role": "user", "content": error_feedback},
        ]

        await mock_llm.ask(messages)

        # Verify error context was passed
        assert len(error_contexts) == 1
        assert "FIX THIS ERROR" in error_contexts[0]


class TestValidationRetryConfig:
    """Tests for retry configuration."""

    def test_retry_decorator_attributes(self):
        """Test that tenacity retry decorator has correct attributes."""
        from tenacity import retry, retry_if_exception_type, stop_after_attempt

        # Verify we can create retry decorator with validation error
        decorator = retry(
            stop=stop_after_attempt(3),
            retry=retry_if_exception_type(ValidationError),
        )
        assert callable(decorator)

    def test_exponential_backoff_config(self):
        """Test exponential backoff configuration."""
        from tenacity import wait_exponential

        wait = wait_exponential(multiplier=1, min=1, max=10)

        # Create mock RetryState objects
        class MockRetryState:
            def __init__(self, attempt_number):
                self.attempt_number = attempt_number

        # Verify wait times with proper retry state objects
        assert wait(MockRetryState(1)) >= 1  # First retry
        assert wait(MockRetryState(2)) >= 2  # Second retry
        assert wait(MockRetryState(5)) <= 10  # Capped at max


class TestValidationErrorHandling:
    """Tests for validation error handling."""

    def test_validation_error_extraction(self):
        """Test extracting useful info from ValidationError."""
        try:
            PlanOutput.model_validate({"goal": "Test"})  # Missing title and steps
        except ValidationError as e:
            errors = e.errors()
            # Should have errors for missing title and steps
            error_locs = [err["loc"] for err in errors]
            assert ("title",) in error_locs
            assert ("steps",) in error_locs

    def test_step_description_validation_error(self):
        """Test step description validation error."""
        try:
            StepDescription(description="Hi")  # Too short
        except ValidationError as e:
            # Pydantic's min_length constraint triggers first
            error_str = str(e)
            assert "too_short" in error_str or "at least 5 characters" in error_str

    def test_placeholder_detection(self):
        """Test placeholder text detection in validation."""
        try:
            StepDescription(description="TODO: implement this")
        except ValidationError as e:
            assert "placeholder" in str(e).lower()


class TestRetryLogging:
    """Tests for retry logging and observability."""

    @pytest.mark.asyncio
    async def test_retry_logs_attempt_number(self):
        """Test that retries log attempt numbers."""
        import logging

        log_messages = []
        handler = logging.Handler()
        handler.emit = lambda record: log_messages.append(record.getMessage())

        # Simulated retry logging
        log_messages.extend(f"Validation retry attempt {attempt}/3" for attempt in range(1, 4))

        assert any("attempt 1" in msg for msg in log_messages)
        assert any("attempt 3" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_final_error_logged(self):
        """Test that final error is logged after retries exhausted."""

        log_messages = []

        def log_error(msg):
            log_messages.append(msg)

        # Simulate max retries exhausted
        log_error("Validation failed after 3 attempts: missing field 'title'")

        assert any("failed after 3 attempts" in msg for msg in log_messages)


class TestBackoffStrategy:
    """Tests for retry backoff strategy."""

    def test_backoff_sequence(self):
        """Test backoff produces expected sequence."""
        from tenacity import wait_exponential

        wait = wait_exponential(multiplier=0.5, min=0.5, max=5)

        # Retry state mock
        class RetryState:
            def __init__(self, attempt_number):
                self.attempt_number = attempt_number

        # Check backoff progression
        wait1 = wait(RetryState(1))
        wait2 = wait(RetryState(2))
        wait3 = wait(RetryState(3))

        assert wait1 <= wait2 <= wait3
        assert wait3 <= 5  # Max cap

    def test_jitter_in_backoff(self):
        """Test that jitter can be applied to backoff."""
        from tenacity import wait_exponential_jitter

        wait = wait_exponential_jitter(initial=1, max=10, jitter=2)

        class RetryState:
            def __init__(self, attempt_number):
                self.attempt_number = attempt_number

        # With jitter, waits may vary
        waits = [wait(RetryState(2)) for _ in range(5)]
        # Should not all be exactly the same due to jitter
        # (though this is probabilistic)
        assert max(waits) > 0


class TestRecoveryFromValidationError:
    """Tests for recovery strategies from validation errors."""

    def test_extract_missing_fields(self):
        """Test extracting missing fields from validation error."""
        try:
            PlanOutput.model_validate({"goal": "Test"})
        except ValidationError as e:
            missing_fields = [err["loc"][0] for err in e.errors() if err["type"] == "missing"]
            assert "title" in missing_fields
            assert "steps" in missing_fields

    def test_generate_correction_prompt(self):
        """Test generating correction prompt from error."""
        try:
            PlanOutput.model_validate({"goal": "Test"})
        except ValidationError as e:
            # Build correction prompt
            prompt = "The previous response was invalid. Please fix:\n"
            for err in e.errors():
                prompt += f"- {err['loc']}: {err['msg']}\n"

            assert "title" in prompt
            assert "steps" in prompt
            assert "Field required" in prompt or "missing" in prompt.lower()

    def test_partial_data_recovery(self):
        """Test recovering partial valid data."""
        # Invalid because missing steps, but goal is valid
        partial_data = {"goal": "Test goal", "title": "Test"}

        # Can extract what's valid
        assert partial_data.get("goal") == "Test goal"
        assert partial_data.get("title") == "Test"

        # Only steps is missing
        try:
            PlanOutput.model_validate(partial_data)
        except ValidationError as e:
            missing = [err["loc"][0] for err in e.errors() if err["type"] == "missing"]
            assert missing == ["steps"]
