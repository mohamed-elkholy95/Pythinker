"""
Comprehensive tests for EnhancedPromptQuickValidator.

Tests cover:
- Technical term preservation
- Typo correction accuracy
- Confidence thresholds
- Case preservation
- Correction logging
- Performance benchmarks
"""

import pytest

from app.domain.services.flows.enhanced_prompt_quick_validator import (
    EnhancedPromptQuickValidator,
)


@pytest.fixture
def validator():
    """Create validator with default settings."""
    return EnhancedPromptQuickValidator()


@pytest.fixture
def logging_validator():
    """Create validator with logging enabled."""
    return EnhancedPromptQuickValidator(log_corrections=True)


class TestTechnicalTermPreservation:
    """Technical terms should NEVER be corrected."""

    def test_frameworks_not_corrected(self, validator):
        """Common frameworks should remain unchanged."""
        text = "Use fastapi with qdrant and pytest"
        cleaned = validator.validate(text)
        assert "fastapi" in cleaned.lower()
        assert "qdrant" in cleaned.lower()
        assert "pytest" in cleaned.lower()

    def test_docker_tools_not_corrected(self, validator):
        """Docker/Kubernetes tools should remain unchanged."""
        text = "Deploy with docker and kubernetes using kubectl"
        cleaned = validator.validate(text)
        assert "docker" in cleaned.lower()
        assert "kubernetes" in cleaned.lower()
        assert "kubectl" in cleaned.lower()

    def test_ai_terms_not_corrected(self, validator):
        """AI/ML terms should remain unchanged."""
        text = "Use llm embedding and tokenizer for inference"
        cleaned = validator.validate(text)
        assert "llm" in cleaned.lower()
        assert "embedding" in cleaned.lower()
        assert "tokenizer" in cleaned.lower()
        assert "inference" in cleaned.lower()

    def test_project_specific_terms_not_corrected(self, validator):
        """Project-specific terms should remain unchanged."""
        text = "Configure pythinker sandbox with guardrail"
        cleaned = validator.validate(text)
        assert "pythinker" in cleaned.lower()
        assert "sandbox" in cleaned.lower()
        assert "guardrail" in cleaned.lower()

    def test_abbreviations_not_corrected(self, validator):
        """Technical abbreviations should remain unchanged."""
        text = "Use api sdk cli ui ux http https ws tcp"
        cleaned = validator.validate(text)
        for term in ("api", "sdk", "cli", "ui", "ux", "http", "https", "ws", "tcp"):
            assert term in cleaned.lower()

    def test_technical_terms_case_preserved(self, validator):
        """Technical term casing should be preserved."""
        assert "FASTAPI" in validator.validate("Use FASTAPI")
        assert "Fastapi" in validator.validate("Use Fastapi")


class TestTypoCorrection:
    """Test typo correction accuracy."""

    def test_coding_typos_corrected(self, validator):
        """Common 'coding' typos should be corrected."""
        assert "coding" in validator.validate("copding")
        assert "coding" in validator.validate("codding")
        assert "coding" in validator.validate("I want to do copding")

    def test_programming_typos_corrected(self, validator):
        """Programming-related typos should be corrected."""
        assert "programming" in validator.validate("progamming")
        assert "development" in validator.validate("developement")
        assert "environment" in validator.validate("envrionment")
        assert "deployment" in validator.validate("deploymnet")
        assert "implementation" in validator.validate("implmentation")
        assert "integration" in validator.validate("integraiton")

    def test_ai_ml_typos_corrected(self, validator):
        """AI/ML typos should be corrected."""
        assert "embedding" in validator.validate("emebdding")
        assert "tokenizer" in validator.validate("tokneizer")
        assert "inference" in validator.validate("inferecne")

    def test_keyboard_proximity_typos(self, validator):
        """Common keyboard proximity typos should be corrected."""
        assert "the" in validator.validate("teh")
        assert "and" in validator.validate("adn")
        assert "that" in validator.validate("taht")
        assert "with" in validator.validate("wiht")
        assert "of" in validator.validate("fo")

    def test_homophone_typos(self, validator):
        """Common homophone misspellings should be corrected."""
        assert "receive" in validator.validate("recieve")
        assert "separate" in validator.validate("seperate")
        assert "definitely" in validator.validate("definately")


class TestCasePreservation:
    """Test that case is preserved in corrections."""

    def test_uppercase_preserved(self, validator):
        """Uppercase words should stay uppercase after correction."""
        assert validator.validate("CODDING") == "CODING"
        assert validator.validate("IMPLMENTATION") == "IMPLEMENTATION"

    def test_capitalized_preserved(self, validator):
        """Capitalized words should stay capitalized after correction."""
        assert validator.validate("Codding") == "Coding"
        assert validator.validate("Implmentation") == "Implementation"

    def test_lowercase_preserved(self, validator):
        """Lowercase words should stay lowercase after correction."""
        assert validator.validate("codding") == "coding"

    def test_mixed_case_in_sentence(self, validator):
        """Case should be preserved in full sentences."""
        result = validator.validate("The IMPLMENTATION of the codding agent")
        assert "IMPLEMENTATION" in result
        assert "coding" in result


class TestModelVersionFormatting:
    """Test model name and version formatting."""

    def test_model_version_spacing(self, validator):
        """Model versions should have proper spacing."""
        assert "Sonnet 4.5" in validator.validate("sonet4.5")
        assert "Opus 4.6" in validator.validate("opus4.6")

    def test_model_version_casing(self, validator):
        """Model names should be capitalized."""
        assert "Sonnet 4.5" in validator.validate("SONNET 4.5")
        assert "Claude 3.5" in validator.validate("claude 3.5")

    def test_glm_version_formatting(self, validator):
        """GLM model versions should use hyphen format."""
        assert "GLM-5" in validator.validate("glm5")
        assert "GLM-4" in validator.validate("glm 4")


class TestCorrectionLogging:
    """Test correction logging and statistics."""

    def test_correction_logging_enabled(self, logging_validator):
        """Corrections should be logged when enabled."""
        logging_validator.validate("copding is fun")
        stats = logging_validator.get_correction_stats()

        # Should have recorded the correction
        assert len(stats) > 0
        assert ("copding", "coding") in stats

    def test_correction_count_increments(self, logging_validator):
        """Correction counts should increment correctly."""
        logging_validator.validate("copding")
        logging_validator.validate("copding")
        logging_validator.validate("copding")

        stats = logging_validator.get_correction_stats()
        assert stats[("copding", "coding")] == 3

    def test_stats_reset(self, logging_validator):
        """Stats should be resettable."""
        logging_validator.validate("copding")
        logging_validator.reset_stats()
        stats = logging_validator.get_correction_stats()
        assert len(stats) == 0

    def test_logging_disabled(self):
        """No logging when disabled."""
        validator = EnhancedPromptQuickValidator(log_corrections=False)
        validator.validate("copding")
        stats = validator.get_correction_stats()
        assert len(stats) == 0


class TestConfidenceThreshold:
    """Test confidence threshold behavior."""

    def test_high_confidence_corrections_applied(self):
        """High confidence corrections should be applied."""
        validator = EnhancedPromptQuickValidator(confidence_threshold=0.90)
        # "copding" -> "coding" has high similarity
        assert "coding" in validator.validate("copding")

    def test_low_confidence_rejected(self):
        """Low confidence corrections should be rejected."""
        validator = EnhancedPromptQuickValidator(confidence_threshold=0.95)
        # Very strict threshold
        result = validator.validate("xyzzy")  # Not close to any known word
        assert "xyzzy" in result  # Should not change

    def test_technical_terms_always_preserved(self):
        """Technical terms should never be corrected regardless of threshold."""
        validator = EnhancedPromptQuickValidator(confidence_threshold=0.50)
        # Even with very low threshold
        assert "qdrant" in validator.validate("qdrant")
        assert "fastapi" in validator.validate("fastapi")


class TestFuzzyMatching:
    """Test fuzzy matching behavior."""

    def test_fuzzy_correction_within_threshold(self, validator):
        """Fuzzy corrections within similarity threshold should apply."""
        # "compoore" is very close to "compare"
        assert "compare" in validator.validate("compoore")

    def test_fuzzy_correction_too_far_rejected(self, validator):
        """Words too different from known words should not be corrected."""
        # "xyz" is not close to any known word
        result = validator.validate("xyz")
        assert "xyz" in result

    def test_safe_targets_only(self, validator):
        """Fuzzy corrections should only use safe targets."""
        # This prevents accidentally correcting to technical terms
        text = "analyz"  # Close to "analyze" (safe target)
        assert "analyze" in validator.validate(text)


class TestWhitespaceAndFormatting:
    """Test whitespace and formatting cleanup."""

    def test_multiple_spaces_collapsed(self, validator):
        """Multiple spaces should be collapsed to single space."""
        result = validator.validate("create   a    report")
        assert result == "create a report"

    def test_leading_trailing_whitespace_trimmed(self, validator):
        """Leading and trailing whitespace should be trimmed."""
        result = validator.validate("  create a report  ")
        assert result == "create a report"

    def test_punctuation_spacing(self, validator):
        """Punctuation spacing should be normalized."""
        result = validator.validate("hello , world . test")
        assert result == "hello, world. test"

    def test_colon_spacing(self, validator):
        """Colons should have space after them."""
        result = validator.validate("note:test")
        assert "note: test" in result


class TestIntegrationScenarios:
    """Test real-world integration scenarios."""

    def test_research_prompt_cleanup(self, validator):
        """Research prompts should be cleaned properly."""
        raw = "Create a comprehensive research report on: compoore sonet 4.5 and opus4.6 with loweffort settings"
        cleaned = validator.validate(raw)

        assert "compoore" not in cleaned.lower()
        assert "sonet" not in cleaned.lower()
        assert "opus4.6" not in cleaned.lower()
        assert "Sonnet 4.5" in cleaned
        assert "Opus 4.6" in cleaned
        assert "low-effort settings" in cleaned.lower()

    def test_deployment_prompt_cleanup(self, validator):
        """Deployment prompts should be cleaned properly."""
        raw = "Deploy the implmentation to the envrionment using docker"
        cleaned = validator.validate(raw)

        assert "implementation" in cleaned
        assert "environment" in cleaned
        assert "implmentation" not in cleaned
        assert "envrionment" not in cleaned

    def test_mixed_content_preserved(self, validator):
        """Mixed technical and natural language should be preserved."""
        raw = "Use fastapi to build the implmentation with pytest testing"
        cleaned = validator.validate(raw)

        assert "fastapi" in cleaned  # Technical term preserved
        assert "pytest" in cleaned  # Technical term preserved
        assert "implementation" in cleaned  # Typo corrected

    def test_no_overcorrection(self, validator):
        """System should not overcorrect valid text."""
        text = "research qdrant kubectl pytest fastapi and prometheus integration patterns"
        cleaned = validator.validate(text)

        # All technical terms should remain unchanged
        assert "qdrant" in cleaned.lower()
        assert "kubectl" in cleaned.lower()
        assert "pytest" in cleaned.lower()
        assert "fastapi" in cleaned.lower()
        assert "prometheus" in cleaned.lower()


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_string(self, validator):
        """Empty string should return empty string."""
        assert validator.validate("") == ""

    def test_whitespace_only(self, validator):
        """Whitespace-only string should return empty string."""
        assert validator.validate("   ") == ""

    def test_numbers_only(self, validator):
        """Numbers should be preserved."""
        assert validator.validate("123 456") == "123 456"

    def test_special_characters(self, validator):
        """Special characters should be preserved."""
        text = "test@email.com and http://example.com"
        assert "test@email.com" in validator.validate(text)
        assert "http://example.com" in validator.validate(text)

    def test_very_long_text(self, validator):
        """Very long text should be handled efficiently."""
        long_text = "copding " * 100
        cleaned = validator.validate(long_text)
        assert "coding" in cleaned
        assert "copding" not in cleaned


class TestBackwardCompatibility:
    """Test backward compatibility with PromptQuickValidator."""

    def test_drop_in_replacement(self):
        """Enhanced validator should work as drop-in replacement."""
        from app.domain.services.flows.prompt_quick_validator import PromptQuickValidator

        # Both should have same interface
        base = PromptQuickValidator()
        enhanced = EnhancedPromptQuickValidator()

        test_input = "copding with sonet 4.5"

        # Both should produce reasonable output
        assert base.validate(test_input)
        assert enhanced.validate(test_input)

    def test_original_tests_still_pass(self, validator):
        """Original PromptQuickValidator tests should pass."""
        # From test_quick_validator_fixes_common_typos_and_model_spacing
        raw = "Create a comprehensive research report on: compoore sonet 4.5 and opus4.6 with loweffort settings"
        cleaned = validator.validate(raw)

        assert "compoore" not in cleaned.lower()
        assert "sonet" not in cleaned.lower()
        assert "opus4.6" not in cleaned.lower()
        assert "Sonnet 4.5" in cleaned
        assert "Opus 4.6" in cleaned
        assert "low-effort settings" in cleaned.lower()


class TestPerformance:
    """Test performance characteristics."""

    def test_validation_speed(self, validator):
        """Validation should complete in < 5ms for typical prompts."""
        import time

        test_prompts = [
            "Create a comprehensive research report",
            "Build a fastapi application with qdrant",
            "Debug the playwright browser automation code",
        ]

        for prompt in test_prompts:
            start = time.time()
            validator.validate(prompt)
            elapsed = (time.time() - start) * 1000  # ms
            assert elapsed < 5.0, f"Validation took {elapsed}ms (> 5ms threshold)"

    def test_long_text_performance(self, validator):
        """Long text validation should still be fast."""
        import time

        long_text = "copding " * 1000  # ~7000 characters
        start = time.time()
        validator.validate(long_text)
        elapsed = (time.time() - start) * 1000

        # Should still be reasonable (< 50ms for very long text)
        assert elapsed < 50.0, f"Long text validation took {elapsed}ms (> 50ms)"
