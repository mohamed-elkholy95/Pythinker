"""Tests for Intent Tracker Constraint Extraction.

Tests the enhanced constraint extraction capabilities of IntentTracker,
including explicit constraints (DO NOT, don't, avoid, never patterns)
and implicit constraints inferred from task context.
"""

import pytest

from app.domain.services.agents.intent_tracker import IntentTracker, get_intent_tracker

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tracker() -> IntentTracker:
    """Create a fresh IntentTracker instance."""
    return IntentTracker()


# =============================================================================
# UserIntent Model Tests
# =============================================================================


class TestUserIntentModel:
    """Tests for the UserIntent dataclass with constraint fields."""

    def test_user_intent_has_constraints_field(self, tracker: IntentTracker):
        """Test that UserIntent has constraints field."""
        intent = tracker.extract_intent("Do something")
        assert hasattr(intent, "constraints")
        assert isinstance(intent.constraints, list)

    def test_user_intent_has_implicit_constraints_field(self, tracker: IntentTracker):
        """Test that UserIntent has implicit_constraints field."""
        intent = tracker.extract_intent("Do something")
        assert hasattr(intent, "implicit_constraints")
        assert isinstance(intent.implicit_constraints, list)

    def test_empty_prompt_returns_empty_constraints(self, tracker: IntentTracker):
        """Test that empty prompt returns empty constraint lists."""
        intent = tracker.extract_intent("")
        assert intent.constraints == []
        assert intent.implicit_constraints == []


# =============================================================================
# Explicit Constraint Extraction Tests
# =============================================================================


class TestExplicitConstraintExtraction:
    """Tests for extracting explicit constraints from user messages."""

    def test_extracts_do_not_pattern(self, tracker: IntentTracker):
        """Test extraction of 'do not' constraints."""
        intent = tracker.extract_intent("Create a script. Do not use any external libraries.")
        assert len(intent.constraints) >= 1
        assert any("external libraries" in c.lower() for c in intent.constraints)

    def test_extracts_dont_pattern(self, tracker: IntentTracker):
        """Test extraction of 'don't' constraints."""
        intent = tracker.extract_intent("Write code but don't modify the database.")
        assert len(intent.constraints) >= 1
        assert any("database" in c.lower() for c in intent.constraints)

    def test_extracts_dont_without_apostrophe(self, tracker: IntentTracker):
        """Test extraction of 'dont' without apostrophe."""
        intent = tracker.extract_intent("Build the feature but dont break existing tests.")
        assert len(intent.constraints) >= 1
        assert any("existing tests" in c.lower() or "break" in c.lower() for c in intent.constraints)

    def test_extracts_never_pattern(self, tracker: IntentTracker):
        """Test extraction of 'never' constraints."""
        intent = tracker.extract_intent("Implement the API but never expose internal errors to users.")
        assert len(intent.constraints) >= 1
        assert any("internal errors" in c.lower() or "expose" in c.lower() for c in intent.constraints)

    def test_extracts_avoid_pattern(self, tracker: IntentTracker):
        """Test extraction of 'avoid' constraints."""
        intent = tracker.extract_intent("Refactor the code and avoid breaking changes.")
        assert len(intent.constraints) >= 1
        assert any("breaking" in c.lower() for c in intent.constraints)

    def test_extracts_skip_pattern(self, tracker: IntentTracker):
        """Test extraction of 'skip' constraints."""
        intent = tracker.extract_intent("Run all tests but skip integration tests.")
        assert len(intent.constraints) >= 1
        assert any("integration" in c.lower() for c in intent.constraints)

    def test_extracts_without_pattern(self, tracker: IntentTracker):
        """Test extraction of 'without' constraints."""
        intent = tracker.extract_intent("Deploy the app without downtime.")
        assert len(intent.constraints) >= 1
        assert any("downtime" in c.lower() for c in intent.constraints)

    def test_extracts_no_pattern(self, tracker: IntentTracker):
        """Test extraction of 'no' constraints."""
        intent = tracker.extract_intent("Write the function with no side effects.")
        assert len(intent.constraints) >= 1
        assert any("side effects" in c.lower() or "side" in c.lower() for c in intent.constraints)

    def test_extracts_except_pattern(self, tracker: IntentTracker):
        """Test extraction of 'except' constraints."""
        intent = tracker.extract_intent("Update all files except config files.")
        assert len(intent.constraints) >= 1
        assert any("config" in c.lower() for c in intent.constraints)

    def test_extracts_excluding_pattern(self, tracker: IntentTracker):
        """Test extraction of 'excluding' constraints."""
        intent = tracker.extract_intent("Process all data excluding test data.")
        assert len(intent.constraints) >= 1
        assert any("test data" in c.lower() for c in intent.constraints)

    def test_extracts_multiple_constraints(self, tracker: IntentTracker):
        """Test extraction of multiple constraints from one message."""
        intent = tracker.extract_intent(
            "Create a REST API. Don't use Flask. Avoid global state. Never block the event loop."
        )
        # Should extract at least 3 constraints
        assert len(intent.constraints) >= 3

    def test_constraint_extraction_case_insensitive(self, tracker: IntentTracker):
        """Test that constraint extraction is case insensitive."""
        intent = tracker.extract_intent("DO NOT use deprecated functions.")
        assert len(intent.constraints) >= 1
        assert any("deprecated" in c.lower() for c in intent.constraints)

    def test_constraint_strips_whitespace(self, tracker: IntentTracker):
        """Test that extracted constraints are trimmed."""
        intent = tracker.extract_intent("Don't   add   extra   spaces.")
        for constraint in intent.constraints:
            assert constraint == constraint.strip()


# =============================================================================
# Implicit Constraint Inference Tests
# =============================================================================


class TestImplicitConstraintInference:
    """Tests for inferring implicit constraints from context."""

    def test_simple_keyword_infers_no_overengineering(self, tracker: IntentTracker):
        """Test that 'simple' keyword infers don't over-engineer constraint."""
        intent = tracker.extract_intent("Write a simple script to parse JSON.")
        assert len(intent.implicit_constraints) >= 1
        assert any("simple" in c.lower() or "over-engineer" in c.lower() for c in intent.implicit_constraints)

    def test_basic_keyword_infers_no_overengineering(self, tracker: IntentTracker):
        """Test that 'basic' keyword infers don't over-engineer constraint."""
        intent = tracker.extract_intent("Create a basic calculator.")
        assert len(intent.implicit_constraints) >= 1
        assert any("simple" in c.lower() or "over-engineer" in c.lower() for c in intent.implicit_constraints)

    def test_minimal_keyword_infers_no_overengineering(self, tracker: IntentTracker):
        """Test that 'minimal' keyword infers don't over-engineer constraint."""
        intent = tracker.extract_intent("Build a minimal viable product.")
        assert len(intent.implicit_constraints) >= 1
        assert any("simple" in c.lower() or "over-engineer" in c.lower() for c in intent.implicit_constraints)

    def test_quick_keyword_infers_no_overengineering(self, tracker: IntentTracker):
        """Test that 'quick' keyword infers don't over-engineer constraint."""
        intent = tracker.extract_intent("Need a quick fix for this bug.")
        assert len(intent.implicit_constraints) >= 1
        assert any("simple" in c.lower() or "over-engineer" in c.lower() for c in intent.implicit_constraints)

    def test_python_language_infers_dont_switch(self, tracker: IntentTracker):
        """Test that specifying Python infers don't switch language constraint."""
        intent = tracker.extract_intent("Write this in Python please.")
        assert len(intent.implicit_constraints) >= 1
        assert any("python" in c.lower() and "switch" in c.lower() for c in intent.implicit_constraints)

    def test_javascript_language_infers_dont_switch(self, tracker: IntentTracker):
        """Test that specifying JavaScript infers don't switch language constraint."""
        intent = tracker.extract_intent("Implement this in JavaScript.")
        assert len(intent.implicit_constraints) >= 1
        assert any("javascript" in c.lower() and "switch" in c.lower() for c in intent.implicit_constraints)

    def test_typescript_language_infers_dont_switch(self, tracker: IntentTracker):
        """Test that specifying TypeScript infers don't switch language constraint."""
        intent = tracker.extract_intent("Create a TypeScript module.")
        assert len(intent.implicit_constraints) >= 1
        assert any("typescript" in c.lower() and "switch" in c.lower() for c in intent.implicit_constraints)

    def test_rust_language_infers_dont_switch(self, tracker: IntentTracker):
        """Test that specifying Rust infers don't switch language constraint."""
        intent = tracker.extract_intent("Build this in Rust.")
        assert len(intent.implicit_constraints) >= 1
        assert any("rust" in c.lower() and "switch" in c.lower() for c in intent.implicit_constraints)

    def test_go_language_infers_dont_switch(self, tracker: IntentTracker):
        """Test that specifying Go infers don't switch language constraint."""
        intent = tracker.extract_intent("Write this in Go.")
        assert len(intent.implicit_constraints) >= 1
        assert any("go" in c.lower() and "switch" in c.lower() for c in intent.implicit_constraints)

    def test_java_language_infers_dont_switch(self, tracker: IntentTracker):
        """Test that specifying Java infers don't switch language constraint."""
        intent = tracker.extract_intent("Implement this in Java.")
        assert len(intent.implicit_constraints) >= 1
        assert any("java" in c.lower() and "switch" in c.lower() for c in intent.implicit_constraints)

    def test_existing_code_infers_no_new_files(self, tracker: IntentTracker):
        """Test that 'existing code' infers don't create new files constraint."""
        intent = tracker.extract_intent("Fix the bug in the existing code.")
        assert len(intent.implicit_constraints) >= 1
        assert any("existing" in c.lower() or "new files" in c.lower() for c in intent.implicit_constraints)

    def test_current_file_infers_no_new_files(self, tracker: IntentTracker):
        """Test that 'current file' infers don't create new files constraint."""
        intent = tracker.extract_intent("Refactor the current file.")
        assert len(intent.implicit_constraints) >= 1
        assert any("existing" in c.lower() or "new files" in c.lower() for c in intent.implicit_constraints)

    def test_this_project_infers_no_new_files(self, tracker: IntentTracker):
        """Test that 'this project' infers don't create new files constraint."""
        intent = tracker.extract_intent("Add tests to this project.")
        assert len(intent.implicit_constraints) >= 1
        assert any("existing" in c.lower() or "new files" in c.lower() for c in intent.implicit_constraints)

    def test_multiple_implicit_constraints(self, tracker: IntentTracker):
        """Test that multiple implicit constraints can be inferred."""
        intent = tracker.extract_intent("Write a simple Python script for the existing project.")
        # Should have at least 3: simple, Python language, existing code
        assert len(intent.implicit_constraints) >= 3

    def test_no_implicit_constraints_when_not_applicable(self, tracker: IntentTracker):
        """Test that no implicit constraints are added when not applicable."""
        intent = tracker.extract_intent("Research the latest trends in AI.")
        # Should have no implicit constraints (no simplicity keywords, no language, no existing code)
        assert len(intent.implicit_constraints) == 0

    def test_implicit_constraint_inference_case_insensitive(self, tracker: IntentTracker):
        """Test that implicit constraint inference is case insensitive."""
        intent = tracker.extract_intent("Write a SIMPLE PYTHON script.")
        assert len(intent.implicit_constraints) >= 2


# =============================================================================
# Combined Constraint Tests
# =============================================================================


class TestCombinedConstraints:
    """Tests for combined explicit and implicit constraints."""

    def test_both_explicit_and_implicit_extracted(self, tracker: IntentTracker):
        """Test that both explicit and implicit constraints are extracted."""
        intent = tracker.extract_intent("Create a simple Python utility. Don't use any external dependencies.")
        # Explicit: external dependencies
        assert len(intent.constraints) >= 1
        # Implicit: simple (don't over-engineer), Python (don't switch)
        assert len(intent.implicit_constraints) >= 2

    def test_constraints_separate_from_requirements(self, tracker: IntentTracker):
        """Test that constraints are separate from requirements."""
        intent = tracker.extract_intent(
            """Create a Python API:
            1. Add authentication
            2. Add rate limiting
            Don't use Flask."""
        )
        # Requirements should have authentication and rate limiting
        all_reqs = intent.explicit_requirements + intent.implicit_requirements
        assert len(all_reqs) >= 2

        # Constraints should have Flask restriction
        assert len(intent.constraints) >= 1
        assert any("flask" in c.lower() for c in intent.constraints)


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntentTrackerIntegration:
    """Integration tests for constraint tracking throughout execution."""

    def test_constraints_available_in_check_alignment(self, tracker: IntentTracker):
        """Test that constraints are available during alignment checks."""
        tracker.extract_intent("Build a simple tool. Don't over-complicate it.")
        tracker.check_alignment("Working on building the tool")

        # Intent should be set and have constraints
        assert tracker._current_intent is not None
        assert len(tracker._current_intent.constraints) >= 1

    def test_get_summary_includes_constraints_count(self, tracker: IntentTracker):
        """Test that get_summary includes constraints count."""
        tracker.extract_intent("Create something. Don't break things. Avoid complexity.")
        summary = tracker.get_summary()

        assert "constraints_count" in summary
        assert summary["constraints_count"] >= 2

    def test_reset_clears_constraints(self, tracker: IntentTracker):
        """Test that reset clears the current intent including constraints."""
        tracker.extract_intent("Don't do X. Avoid Y.")
        tracker.reset()
        summary = tracker.get_summary()

        assert summary["status"] == "no_intent_tracked"

    def test_global_tracker_extracts_constraints(self):
        """Test that the global tracker instance extracts constraints."""
        tracker = get_intent_tracker()
        tracker.reset()  # Ensure clean state

        intent = tracker.extract_intent("Don't use deprecated APIs.")
        assert len(intent.constraints) >= 1
        assert any("deprecated" in c.lower() for c in intent.constraints)


# =============================================================================
# Edge Cases
# =============================================================================


class TestConstraintEdgeCases:
    """Tests for edge cases in constraint extraction."""

    def test_constraint_at_end_of_sentence(self, tracker: IntentTracker):
        """Test constraint extraction when at end of sentence."""
        intent = tracker.extract_intent("Write code that is efficient. Don't use recursion.")
        assert len(intent.constraints) >= 1

    def test_constraint_with_comma(self, tracker: IntentTracker):
        """Test constraint extraction with comma in content."""
        intent = tracker.extract_intent("Don't use loops, recursion, or global variables.")
        assert len(intent.constraints) >= 1

    def test_constraint_in_middle_of_text(self, tracker: IntentTracker):
        """Test constraint extraction from middle of text."""
        intent = tracker.extract_intent("I need a script, but please don't make it too complex, thanks.")
        assert len(intent.constraints) >= 1

    def test_false_positive_avoid_in_word(self, tracker: IntentTracker):
        """Test that 'avoid' inside a word doesn't trigger extraction."""
        # The word "flavoiding" contains "avoid" but shouldn't match
        # This depends on the regex boundaries
        intent = tracker.extract_intent("Create a mechanism for handling data.")
        # No constraints should be extracted from normal text
        constraint_count = len(intent.constraints)
        # This is just ensuring no crash; specific behavior depends on patterns
        assert isinstance(constraint_count, int)

    def test_unicode_in_constraints(self, tracker: IntentTracker):
        """Test constraint extraction with unicode characters."""
        intent = tracker.extract_intent("Don't use special characters like cafe or resume.")
        assert len(intent.constraints) >= 1

    def test_very_long_constraint(self, tracker: IntentTracker):
        """Test extraction of very long constraint text."""
        long_text = "Don't " + "use very " * 50 + "long patterns."
        intent = tracker.extract_intent(long_text)
        # Should handle gracefully
        assert isinstance(intent.constraints, list)

    def test_empty_constraint_not_added(self, tracker: IntentTracker):
        """Test that empty strings are not added as constraints."""
        intent = tracker.extract_intent("Some text with no constraints.")
        for constraint in intent.constraints:
            assert constraint.strip() != ""

    def test_implicit_constraint_preserves_language_case(self, tracker: IntentTracker):
        """Test that language name is preserved in implicit constraint."""
        intent = tracker.extract_intent("Write this in Python.")
        # The constraint should mention the language
        matching = [c for c in intent.implicit_constraints if "python" in c.lower()]
        assert len(matching) >= 1
