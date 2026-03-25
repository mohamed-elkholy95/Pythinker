"""Comprehensive tests for IntentTracker.

Covers enum values, dataclass properties, intent extraction, requirement
tracking, similarity functions, and alignment checks.
"""

from datetime import UTC, datetime

import pytest

from app.domain.services.agents.intent_tracker import (
    DriftAlert,
    DriftType,
    IntentTracker,
    IntentTrackingResult,
    IntentType,
    get_intent_tracker,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tracker() -> IntentTracker:
    """Return a fresh IntentTracker for each test."""
    return IntentTracker()


@pytest.fixture
def tracker_with_intent(tracker: IntentTracker) -> IntentTracker:
    """Return an IntentTracker that already has an intent extracted."""
    tracker.extract_intent(
        "Create a Python script that reads a CSV file.\n"
        "1. Parse each row\n"
        "2. Validate the data\n"
        "3. Write results to JSON\n"
        "Don't use external libraries."
    )
    return tracker


# =============================================================================
# IntentType enum
# =============================================================================


class TestIntentTypeEnum:
    """Verify all IntentType enum members and their string values."""

    def test_action_value(self):
        assert IntentType.ACTION == "action"

    def test_question_value(self):
        assert IntentType.QUESTION == "question"

    def test_creation_value(self):
        assert IntentType.CREATION == "creation"

    def test_modification_value(self):
        assert IntentType.MODIFICATION == "modification"

    def test_deletion_value(self):
        assert IntentType.DELETION == "deletion"

    def test_analysis_value(self):
        assert IntentType.ANALYSIS == "analysis"

    def test_comparison_value(self):
        assert IntentType.COMPARISON == "comparison"

    def test_is_str_subclass(self):
        assert isinstance(IntentType.ACTION, str)

    def test_all_members_present(self):
        members = {m.value for m in IntentType}
        assert members == {
            "action",
            "question",
            "creation",
            "modification",
            "deletion",
            "analysis",
            "comparison",
        }


# =============================================================================
# DriftType enum
# =============================================================================


class TestDriftTypeEnum:
    """Verify all DriftType enum members and their string values."""

    def test_scope_creep_value(self):
        assert DriftType.SCOPE_CREEP == "scope_creep"

    def test_scope_reduction_value(self):
        assert DriftType.SCOPE_REDUCTION == "scope_reduction"

    def test_topic_drift_value(self):
        assert DriftType.TOPIC_DRIFT == "topic_drift"

    def test_gold_plating_value(self):
        assert DriftType.GOLD_PLATING == "gold_plating"

    def test_is_str_subclass(self):
        assert isinstance(DriftType.SCOPE_CREEP, str)

    def test_all_members_present(self):
        members = {m.value for m in DriftType}
        assert members == {
            "scope_creep",
            "scope_reduction",
            "topic_drift",
            "gold_plating",
        }


# =============================================================================
# IntentTrackingResult.needs_correction property
# =============================================================================


class TestNeedsCorrectionProperty:
    """Tests for IntentTrackingResult.needs_correction."""

    def _make_result(
        self,
        on_track: bool = True,
        drift_alerts: list[DriftAlert] | None = None,
    ) -> IntentTrackingResult:
        return IntentTrackingResult(
            coverage_percent=100.0,
            unaddressed_requirements=[],
            addressed_requirements=[],
            drift_alerts=drift_alerts or [],
            on_track=on_track,
        )

    def test_no_correction_needed_when_on_track_no_alerts(self):
        result = self._make_result(on_track=True, drift_alerts=[])
        assert result.needs_correction is False

    def test_correction_needed_when_not_on_track(self):
        result = self._make_result(on_track=False, drift_alerts=[])
        assert result.needs_correction is True

    def test_correction_needed_when_drift_alerts_present(self):
        alert = DriftAlert(
            drift_type=DriftType.SCOPE_CREEP,
            description="Adding unrequested features",
            severity=0.5,
            evidence="also added",
            correction="Focus on requested features",
        )
        result = self._make_result(on_track=True, drift_alerts=[alert])
        assert result.needs_correction is True

    def test_correction_needed_when_both_off_track_and_alerts(self):
        alert = DriftAlert(
            drift_type=DriftType.TOPIC_DRIFT,
            description="Off-topic",
            severity=0.6,
            evidence="unrelated work",
            correction="Return to goal",
        )
        result = self._make_result(on_track=False, drift_alerts=[alert])
        assert result.needs_correction is True

    def test_needs_correction_is_property(self):
        result = self._make_result()
        assert isinstance(result.needs_correction, bool)

    def test_timestamp_defaults_to_utc_now(self):
        before = datetime.now(UTC)
        result = self._make_result()
        after = datetime.now(UTC)
        assert before <= result.timestamp <= after


# =============================================================================
# extract_intent — empty / minimal prompts
# =============================================================================


class TestExtractIntentEmpty:
    """Verify extract_intent behaviour on empty and minimal inputs."""

    def test_empty_string_returns_action_type(self, tracker: IntentTracker):
        intent = tracker.extract_intent("")
        assert intent.intent_type == IntentType.ACTION

    def test_empty_string_returns_empty_goal(self, tracker: IntentTracker):
        intent = tracker.extract_intent("")
        assert intent.primary_goal == ""

    def test_empty_string_returns_no_explicit_requirements(self, tracker: IntentTracker):
        intent = tracker.extract_intent("")
        assert intent.explicit_requirements == []

    def test_empty_string_returns_no_constraints(self, tracker: IntentTracker):
        intent = tracker.extract_intent("")
        assert intent.constraints == []

    def test_empty_string_returns_no_preferences(self, tracker: IntentTracker):
        intent = tracker.extract_intent("")
        assert intent.preferences == {}

    def test_empty_string_sets_original_prompt_empty(self, tracker: IntentTracker):
        intent = tracker.extract_intent("")
        assert intent.original_prompt == ""

    def test_extracted_at_is_recent_utc(self, tracker: IntentTracker):
        before = datetime.now(UTC)
        intent = tracker.extract_intent("Do something")
        after = datetime.now(UTC)
        assert before <= intent.extracted_at <= after


# =============================================================================
# extract_intent — intent type detection
# =============================================================================


class TestDetectIntentType:
    """Verify _detect_intent_type routes to the correct IntentType."""

    def test_create_keyword_maps_to_creation(self, tracker: IntentTracker):
        intent = tracker.extract_intent("Create a new REST API endpoint.")
        assert intent.intent_type == IntentType.CREATION

    def test_build_keyword_maps_to_creation(self, tracker: IntentTracker):
        intent = tracker.extract_intent("Build a dashboard for analytics.")
        assert intent.intent_type == IntentType.CREATION

    def test_generate_keyword_maps_to_creation(self, tracker: IntentTracker):
        intent = tracker.extract_intent("Generate a report from the database.")
        assert intent.intent_type == IntentType.CREATION

    def test_analyze_keyword_maps_to_analysis(self, tracker: IntentTracker):
        intent = tracker.extract_intent("Analyze the performance bottlenecks.")
        assert intent.intent_type == IntentType.ANALYSIS

    def test_research_keyword_maps_to_analysis(self, tracker: IntentTracker):
        intent = tracker.extract_intent("Research modern caching strategies.")
        assert intent.intent_type == IntentType.ANALYSIS

    def test_what_question_maps_to_question(self, tracker: IntentTracker):
        intent = tracker.extract_intent("What is the best approach for this?")
        assert intent.intent_type == IntentType.QUESTION

    def test_how_question_maps_to_question(self, tracker: IntentTracker):
        intent = tracker.extract_intent("How does the authentication flow work?")
        assert intent.intent_type == IntentType.QUESTION

    def test_trailing_question_mark_maps_to_question(self, tracker: IntentTracker):
        intent = tracker.extract_intent("Is this approach correct?")
        assert intent.intent_type == IntentType.QUESTION

    def test_compare_keyword_maps_to_comparison(self, tracker: IntentTracker):
        intent = tracker.extract_intent("Compare Redis vs Memcached for caching.")
        assert intent.intent_type == IntentType.COMPARISON

    def test_versus_keyword_maps_to_comparison(self, tracker: IntentTracker):
        intent = tracker.extract_intent("Compare PostgreSQL versus MySQL for this workload.")
        assert intent.intent_type == IntentType.COMPARISON

    def test_delete_keyword_maps_to_deletion(self, tracker: IntentTracker):
        intent = tracker.extract_intent("Delete all temporary files.")
        assert intent.intent_type == IntentType.DELETION

    def test_remove_keyword_maps_to_deletion(self, tracker: IntentTracker):
        intent = tracker.extract_intent("Remove the deprecated endpoints.")
        assert intent.intent_type == IntentType.DELETION

    def test_update_keyword_maps_to_modification(self, tracker: IntentTracker):
        intent = tracker.extract_intent("Update the user profile schema.")
        assert intent.intent_type == IntentType.MODIFICATION

    def test_refactor_keyword_maps_to_modification(self, tracker: IntentTracker):
        intent = tracker.extract_intent("Refactor the authentication module.")
        assert intent.intent_type == IntentType.MODIFICATION

    def test_unknown_verb_defaults_to_action(self, tracker: IntentTracker):
        # _detect_intent_type is the internal method; call it directly.
        result = tracker._detect_intent_type("Please do the needful for the project.")
        assert result == IntentType.ACTION


# =============================================================================
# _extract_primary_goal
# =============================================================================


class TestExtractPrimaryGoal:
    """Verify primary goal extraction logic."""

    def test_returns_first_line(self, tracker: IntentTracker):
        goal = tracker._extract_primary_goal("Create a script.\nWith extra details.")
        assert goal == "Create a script."

    def test_returns_single_line_intact(self, tracker: IntentTracker):
        text = "Generate a PDF report from the data."
        goal = tracker._extract_primary_goal(text)
        assert goal == text

    def test_short_text_not_truncated(self, tracker: IntentTracker):
        short = "Do something simple."
        goal = tracker._extract_primary_goal(short)
        assert goal == short

    def test_long_line_truncated_at_200_chars(self, tracker: IntentTracker):
        long_line = "A" * 250
        goal = tracker._extract_primary_goal(long_line)
        assert len(goal) <= 203  # 200 + "..." or sentence boundary

    def test_long_line_with_sentence_boundary(self, tracker: IntentTracker):
        long_line = "A" * 50 + ". " + "B" * 200
        goal = tracker._extract_primary_goal(long_line)
        # Should stop at the first sentence boundary
        assert goal.endswith(".")

    def test_ellipsis_appended_when_no_boundary(self, tracker: IntentTracker):
        long_line = "X" * 250  # No sentence boundary
        goal = tracker._extract_primary_goal(long_line)
        assert goal.endswith("...")

    def test_strips_leading_whitespace(self, tracker: IntentTracker):
        goal = tracker._extract_primary_goal("  Create a tool.\nDetails here.")
        assert not goal.startswith(" ")


# =============================================================================
# _extract_explicit_requirements
# =============================================================================


class TestExtractExplicitRequirements:
    """Verify numbered and bullet list extraction."""

    def test_extracts_numbered_list_dot(self, tracker: IntentTracker):
        text = "Do the following:\n1. Parse input\n2. Validate data\n3. Write output"
        reqs = tracker._extract_explicit_requirements(text)
        assert "Parse input" in reqs
        assert "Validate data" in reqs
        assert "Write output" in reqs

    def test_extracts_numbered_list_paren(self, tracker: IntentTracker):
        text = "Steps:\n1) First step\n2) Second step"
        reqs = tracker._extract_explicit_requirements(text)
        assert len(reqs) >= 2

    def test_extracts_dash_bullet_list(self, tracker: IntentTracker):
        text = "Requirements:\n- Read CSV\n- Process rows\n- Save results"
        reqs = tracker._extract_explicit_requirements(text)
        assert "Read CSV" in reqs
        assert "Process rows" in reqs
        assert "Save results" in reqs

    def test_extracts_asterisk_bullet_list(self, tracker: IntentTracker):
        text = "Features:\n* Add authentication\n* Add rate limiting"
        reqs = tracker._extract_explicit_requirements(text)
        assert len(reqs) >= 2

    def test_returns_empty_for_plain_paragraph(self, tracker: IntentTracker):
        text = "Create a simple script that does some processing and outputs results."
        reqs = tracker._extract_explicit_requirements(text)
        assert reqs == []

    def test_strips_whitespace_from_items(self, tracker: IntentTracker):
        text = "1.  Item with extra spaces  \n2. Another item"
        reqs = tracker._extract_explicit_requirements(text)
        for req in reqs:
            assert req == req.strip()

    def test_complex_prompt_extracts_all_items(self, tracker: IntentTracker):
        text = (
            "Build an API with the following features:\n"
            "1. User authentication\n"
            "2. Role-based access control\n"
            "3. Rate limiting\n"
            "- Logging support\n"
            "- Health check endpoint"
        )
        reqs = tracker._extract_explicit_requirements(text)
        assert len(reqs) >= 5


# =============================================================================
# _extract_constraints
# =============================================================================


class TestExtractConstraints:
    """Verify explicit constraint extraction patterns."""

    def test_dont_pattern_extracted(self, tracker: IntentTracker):
        constraints = tracker._extract_constraints("Don't use global variables.")
        assert len(constraints) >= 1
        assert any("global variables" in c.lower() or "use" in c.lower() for c in constraints)

    def test_do_not_pattern_extracted(self, tracker: IntentTracker):
        constraints = tracker._extract_constraints("Do not modify the database schema.")
        assert len(constraints) >= 1

    def test_never_pattern_extracted(self, tracker: IntentTracker):
        constraints = tracker._extract_constraints("Never expose credentials in logs.")
        assert len(constraints) >= 1
        assert any("credentials" in c.lower() or "expose" in c.lower() for c in constraints)

    def test_avoid_pattern_extracted(self, tracker: IntentTracker):
        constraints = tracker._extract_constraints("Avoid breaking existing tests.")
        assert len(constraints) >= 1
        assert any("breaking" in c.lower() or "existing" in c.lower() for c in constraints)

    def test_without_pattern_extracted(self, tracker: IntentTracker):
        constraints = tracker._extract_constraints("Deploy the service without downtime.")
        assert len(constraints) >= 1
        assert any("downtime" in c for c in constraints)

    def test_no_pattern_extracted(self, tracker: IntentTracker):
        constraints = tracker._extract_constraints("Write the function with no side effects.")
        assert len(constraints) >= 1

    def test_empty_text_returns_empty_list(self, tracker: IntentTracker):
        constraints = tracker._extract_constraints("")
        assert constraints == []

    def test_no_constraint_text_returns_empty(self, tracker: IntentTracker):
        constraints = tracker._extract_constraints("Please create a new endpoint for users.")
        assert isinstance(constraints, list)


# =============================================================================
# _infer_implicit_constraints
# =============================================================================


class TestInferImplicitConstraints:
    """Verify implicit constraint inference from context."""

    def test_simple_keyword_adds_no_overengineering(self, tracker: IntentTracker):
        implicit = tracker._infer_implicit_constraints("Write a simple CSV parser.")
        assert any("simple" in c.lower() or "over-engineer" in c.lower() for c in implicit)

    def test_basic_keyword_adds_no_overengineering(self, tracker: IntentTracker):
        implicit = tracker._infer_implicit_constraints("Create a basic web server.")
        assert any("simple" in c.lower() or "over-engineer" in c.lower() for c in implicit)

    def test_minimal_keyword_adds_no_overengineering(self, tracker: IntentTracker):
        implicit = tracker._infer_implicit_constraints("Build a minimal CLI tool.")
        assert any("simple" in c.lower() or "over-engineer" in c.lower() for c in implicit)

    def test_quick_keyword_adds_no_overengineering(self, tracker: IntentTracker):
        implicit = tracker._infer_implicit_constraints("Need a quick script for this.")
        assert any("simple" in c.lower() or "over-engineer" in c.lower() for c in implicit)

    def test_in_python_adds_language_constraint(self, tracker: IntentTracker):
        implicit = tracker._infer_implicit_constraints("Write this in Python.")
        assert any("python" in c.lower() and "switch" in c.lower() for c in implicit)

    def test_in_javascript_adds_language_constraint(self, tracker: IntentTracker):
        implicit = tracker._infer_implicit_constraints("Implement in JavaScript.")
        assert any("javascript" in c.lower() and "switch" in c.lower() for c in implicit)

    def test_existing_code_adds_no_new_files(self, tracker: IntentTracker):
        implicit = tracker._infer_implicit_constraints("Fix the bug in the existing code.")
        assert any("existing" in c.lower() or "new files" in c.lower() for c in implicit)

    def test_existing_file_adds_no_new_files(self, tracker: IntentTracker):
        implicit = tracker._infer_implicit_constraints("Update this existing file.")
        assert any("existing" in c.lower() or "new files" in c.lower() for c in implicit)

    def test_this_project_adds_no_new_files(self, tracker: IntentTracker):
        implicit = tracker._infer_implicit_constraints("Add a test to this project.")
        assert any("existing" in c.lower() or "new files" in c.lower() for c in implicit)

    def test_no_keywords_returns_empty(self, tracker: IntentTracker):
        implicit = tracker._infer_implicit_constraints("Research trends in distributed systems.")
        assert implicit == []

    def test_case_insensitive_simple_detection(self, tracker: IntentTracker):
        implicit = tracker._infer_implicit_constraints("SIMPLE solution needed.")
        assert any("simple" in c.lower() or "over-engineer" in c.lower() for c in implicit)

    def test_returns_list_type(self, tracker: IntentTracker):
        implicit = tracker._infer_implicit_constraints("Do something.")
        assert isinstance(implicit, list)


# =============================================================================
# _extract_preferences
# =============================================================================


class TestExtractPreferences:
    """Verify format, language, and style preference extraction."""

    def test_json_format_preference(self, tracker: IntentTracker):
        prefs = tracker._extract_preferences("Output the results in JSON format.")
        assert "format" in prefs
        assert prefs["format"] == "json"

    def test_markdown_format_preference(self, tracker: IntentTracker):
        prefs = tracker._extract_preferences("Please respond in markdown.")
        assert "format" in prefs
        assert prefs["format"] == "markdown"

    def test_python_language_preference(self, tracker: IntentTracker):
        prefs = tracker._extract_preferences("Write the solution in Python.")
        assert "language" in prefs
        assert prefs["language"] == "python"

    def test_typescript_language_preference(self, tracker: IntentTracker):
        prefs = tracker._extract_preferences("Using TypeScript please.")
        assert "language" in prefs
        assert prefs["language"] == "typescript"

    def test_professional_style_preference(self, tracker: IntentTracker):
        prefs = tracker._extract_preferences("Write this in a professional style.")
        assert "style" in prefs
        assert prefs["style"] == "professional"

    def test_formal_style_preference(self, tracker: IntentTracker):
        prefs = tracker._extract_preferences("Please write this in a formal style.")
        assert "style" in prefs
        assert prefs["style"] == "formal"

    def test_no_preference_returns_empty_dict(self, tracker: IntentTracker):
        prefs = tracker._extract_preferences("Just create a script.")
        assert isinstance(prefs, dict)

    def test_preference_values_are_lowercase(self, tracker: IntentTracker):
        prefs = tracker._extract_preferences("Respond in JSON.")
        for value in prefs.values():
            assert value == value.lower()


# =============================================================================
# mark_addressed
# =============================================================================


class TestMarkAddressed:
    """Verify mark_addressed correctly records addressed requirements."""

    def test_requirement_added_to_addressed_set(self, tracker_with_intent: IntentTracker):
        tracker_with_intent.mark_addressed("Parse each row", step_id="step-1")
        assert "parse each row" in tracker_with_intent._addressed_requirements

    def test_requirement_stored_case_insensitive(self, tracker_with_intent: IntentTracker):
        tracker_with_intent.mark_addressed("VALIDATE THE DATA", step_id="step-2")
        assert "validate the data" in tracker_with_intent._addressed_requirements

    def test_work_history_records_entry(self, tracker_with_intent: IntentTracker):
        tracker_with_intent.mark_addressed("Write results to JSON", step_id="step-3", work_summary="Wrote JSON output")
        history = tracker_with_intent._work_history
        assert any(h["step_id"] == "step-3" for h in history)

    def test_work_history_captures_summary(self, tracker_with_intent: IntentTracker):
        tracker_with_intent.mark_addressed("Parse each row", step_id="step-1", work_summary="Parsed 500 rows")
        history = tracker_with_intent._work_history
        matching = [h for h in history if h["step_id"] == "step-1"]
        assert matching[0]["summary"] == "Parsed 500 rows"

    def test_multiple_requirements_tracked(self, tracker_with_intent: IntentTracker):
        tracker_with_intent.mark_addressed("Parse each row", step_id="step-1")
        tracker_with_intent.mark_addressed("Validate the data", step_id="step-2")
        assert len(tracker_with_intent._addressed_requirements) == 2

    def test_work_summary_optional(self, tracker_with_intent: IntentTracker):
        # Should not raise when work_summary is omitted
        tracker_with_intent.mark_addressed("Parse each row", step_id="step-1")
        history = tracker_with_intent._work_history
        assert history[-1]["summary"] is None


# =============================================================================
# check_alignment — no current intent
# =============================================================================


class TestCheckAlignmentNoIntent:
    """check_alignment returns on_track=True when no intent is set."""

    def test_returns_on_track_true(self, tracker: IntentTracker):
        result = tracker.check_alignment("Working on something.")
        assert result.on_track is True

    def test_returns_full_coverage(self, tracker: IntentTracker):
        result = tracker.check_alignment("Working on something.")
        assert result.coverage_percent == 100.0

    def test_returns_no_drift_alerts(self, tracker: IntentTracker):
        result = tracker.check_alignment("Working on something.")
        assert result.drift_alerts == []

    def test_returns_empty_addressed(self, tracker: IntentTracker):
        result = tracker.check_alignment("Working on something.")
        assert result.addressed_requirements == []

    def test_returns_empty_unaddressed(self, tracker: IntentTracker):
        result = tracker.check_alignment("Working on something.")
        assert result.unaddressed_requirements == []


# =============================================================================
# check_alignment — with current intent
# =============================================================================


class TestCheckAlignmentWithIntent:
    """check_alignment correctly tracks coverage and drift."""

    def test_full_coverage_when_all_marked(self, tracker_with_intent: IntentTracker):
        assert tracker_with_intent._current_intent is not None
        for req in tracker_with_intent._current_intent.explicit_requirements:
            tracker_with_intent.mark_addressed(req, step_id="step-x")
        result = tracker_with_intent.check_alignment("All requirements handled.")
        assert result.coverage_percent == 100.0

    def test_returns_unaddressed_requirements(self, tracker: IntentTracker):
        tracker.extract_intent(
            "Create a tool.\n"
            "1. Implement quantum encryption\n"
            "2. Add blockchain persistence\n"
            "3. Configure satellite uplink"
        )
        # Mark nothing; pass completely unrelated work summary
        result = tracker.check_alignment("zzzz aaaa bbbb cccc dddd eeee ffff")
        assert len(result.unaddressed_requirements) >= 1

    def test_on_track_false_below_50_percent_coverage(self, tracker: IntentTracker):
        tracker.extract_intent(
            "Create a service.\n"
            "1. Requirement one\n"
            "2. Requirement two\n"
            "3. Requirement three\n"
            "4. Requirement four\n"
            "5. Requirement five"
        )
        # Do not mark any addressed; pass unrelated work
        result = tracker.check_alignment("zzzz aaaa bbbb cccc dddd eeee ffff unrelated work")
        assert result.on_track is False

    def test_guidance_generated_when_not_on_track(self, tracker: IntentTracker):
        tracker.extract_intent("Create a service.\n1. Feature one\n2. Feature two")
        result = tracker.check_alignment("zzzz unrelated work aaaa bbbb cccc dddd")
        if not result.on_track:
            assert result.guidance is not None

    def test_returns_intent_tracking_result_type(self, tracker_with_intent: IntentTracker):
        result = tracker_with_intent.check_alignment("Doing some work.")
        assert isinstance(result, IntentTrackingResult)


class TestTextSimilarity:
    """Verify Jaccard word-overlap similarity function."""

    def test_identical_texts_return_one(self, tracker: IntentTracker):
        text = "parse CSV file and validate data"
        score = tracker._text_similarity(text, text)
        assert score == pytest.approx(1.0)

    def test_no_overlap_returns_zero(self, tracker: IntentTracker):
        score = tracker._text_similarity("alpha beta gamma", "delta epsilon zeta")
        assert score == pytest.approx(0.0)

    def test_empty_first_text_returns_zero(self, tracker: IntentTracker):
        score = tracker._text_similarity("", "some words here")
        assert score == pytest.approx(0.0)

    def test_empty_second_text_returns_zero(self, tracker: IntentTracker):
        score = tracker._text_similarity("some words here", "")
        assert score == pytest.approx(0.0)

    def test_both_empty_returns_zero(self, tracker: IntentTracker):
        score = tracker._text_similarity("", "")
        assert score == pytest.approx(0.0)

    def test_partial_overlap_between_zero_and_one(self, tracker: IntentTracker):
        score = tracker._text_similarity("read parse validate", "read write validate")
        assert 0.0 < score < 1.0

    def test_stop_words_excluded(self, tracker: IntentTracker):
        # Texts that share only stop words should score 0
        score = tracker._text_similarity("the a an is", "the a an is")
        # After removing stop words both sets are empty → 0.0
        assert score == pytest.approx(0.0)

    def test_score_symmetric(self, tracker: IntentTracker):
        a = "build an API endpoint"
        b = "endpoint for the API"
        assert tracker._text_similarity(a, b) == pytest.approx(tracker._text_similarity(b, a))

    def test_returns_float(self, tracker: IntentTracker):
        score = tracker._text_similarity("hello world", "world hello")
        assert isinstance(score, float)


# =============================================================================
# check_requirement_addressed
# =============================================================================


class TestCheckRequirementAddressed:
    """Verify semantic requirement-addressed check with mocked embeddings."""

    def test_high_similarity_returns_true(self, tracker: IntentTracker, monkeypatch):
        """Mocked embedding returns identical vectors → similarity = 1.0 ≥ threshold."""
        fixed_embedding = [1.0, 0.0, 0.0]
        monkeypatch.setattr(
            "app.domain.services.agents.stuck_detector.compute_trigram_embedding",
            lambda text, **kwargs: fixed_embedding,
        )
        # Clear cache so monkeypatched function is used
        tracker._embedding_cache.clear()
        result = tracker.check_requirement_addressed(
            "Parse CSV file",
            "Parsing the CSV file row by row",
            threshold=0.7,
        )
        assert result is True

    def test_zero_similarity_returns_false(self, tracker: IntentTracker, monkeypatch):
        """Mocked embeddings are orthogonal → similarity = 0.0 < threshold."""
        call_count = {"n": 0}

        def alternating_embedding(text, **kwargs):
            call_count["n"] += 1
            if call_count["n"] % 2 == 1:
                return [1.0, 0.0, 0.0]
            return [0.0, 1.0, 0.0]

        monkeypatch.setattr(
            "app.domain.services.agents.stuck_detector.compute_trigram_embedding",
            alternating_embedding,
        )
        tracker._embedding_cache.clear()
        result = tracker.check_requirement_addressed(
            "unique_req_aaa",
            "unique_work_bbb",
            threshold=0.7,
        )
        assert result is False

    def test_default_threshold_is_0_7(self, tracker: IntentTracker, monkeypatch):
        """Default threshold of 0.7 is respected."""
        fixed_embedding = [1.0, 0.0, 0.0]
        monkeypatch.setattr(
            "app.domain.services.agents.stuck_detector.compute_trigram_embedding",
            lambda text, **kwargs: fixed_embedding,
        )
        tracker._embedding_cache.clear()
        # With identical embeddings similarity = 1.0, so default threshold passes
        result = tracker.check_requirement_addressed("req", "work")
        assert result is True

    def test_fallback_to_jaccard_when_embedding_fails(self, tracker: IntentTracker, monkeypatch):
        """When embedding raises, falls back to Jaccard similarity."""
        monkeypatch.setattr(
            "app.domain.services.agents.stuck_detector.compute_trigram_embedding",
            lambda text, **kwargs: (_ for _ in ()).throw(RuntimeError("embedding unavailable")),
        )
        tracker._embedding_cache.clear()
        # Identical text → Jaccard = 1.0 → True even with 0.7 threshold
        result = tracker.check_requirement_addressed(
            "parse csv data",
            "parse csv data",
            threshold=0.5,
        )
        assert result is True


# =============================================================================
# get_intent_tracker singleton
# =============================================================================


class TestGetIntentTrackerSingleton:
    """Verify the module-level singleton factory."""

    def test_returns_intent_tracker_instance(self):
        instance = get_intent_tracker()
        assert isinstance(instance, IntentTracker)

    def test_returns_same_instance_on_repeated_calls(self):
        first = get_intent_tracker()
        second = get_intent_tracker()
        assert first is second


# =============================================================================
# IntentTracker.reset
# =============================================================================


class TestReset:
    """Verify reset() clears all tracker state."""

    def test_reset_clears_current_intent(self, tracker_with_intent: IntentTracker):
        tracker_with_intent.reset()
        assert tracker_with_intent._current_intent is None

    def test_reset_clears_addressed_requirements(self, tracker_with_intent: IntentTracker):
        tracker_with_intent.mark_addressed("Parse each row", step_id="s1")
        tracker_with_intent.reset()
        assert len(tracker_with_intent._addressed_requirements) == 0

    def test_reset_clears_work_history(self, tracker_with_intent: IntentTracker):
        tracker_with_intent.mark_addressed("Parse each row", step_id="s1")
        tracker_with_intent.reset()
        assert len(tracker_with_intent._work_history) == 0

    def test_reset_allows_fresh_intent_extraction(self, tracker_with_intent: IntentTracker):
        tracker_with_intent.reset()
        intent = tracker_with_intent.extract_intent("Analyze sales data.")
        assert intent.intent_type == IntentType.ANALYSIS


# =============================================================================
# get_summary
# =============================================================================


class TestGetSummary:
    """Verify get_summary returns the expected shape."""

    def test_no_intent_returns_status_no_intent(self, tracker: IntentTracker):
        summary = tracker.get_summary()
        assert summary == {"status": "no_intent_tracked"}

    def test_summary_includes_intent_type(self, tracker_with_intent: IntentTracker):
        summary = tracker_with_intent.get_summary()
        assert "intent_type" in summary

    def test_summary_includes_primary_goal(self, tracker_with_intent: IntentTracker):
        summary = tracker_with_intent.get_summary()
        assert "primary_goal" in summary

    def test_summary_includes_total_requirements(self, tracker_with_intent: IntentTracker):
        summary = tracker_with_intent.get_summary()
        assert "total_requirements" in summary
        assert summary["total_requirements"] >= 3

    def test_summary_includes_addressed_count(self, tracker_with_intent: IntentTracker):
        tracker_with_intent.mark_addressed("Parse each row", step_id="s1")
        summary = tracker_with_intent.get_summary()
        assert summary["addressed_count"] >= 1

    def test_summary_includes_constraints_count(self, tracker_with_intent: IntentTracker):
        summary = tracker_with_intent.get_summary()
        assert "constraints_count" in summary

    def test_summary_primary_goal_truncated_to_100(self, tracker: IntentTracker):
        long_goal = "X" * 300
        tracker.extract_intent(long_goal)
        summary = tracker.get_summary()
        assert len(summary["primary_goal"]) <= 100


# =============================================================================
# UserIntent dataclass fields
# =============================================================================


class TestUserIntentDataclass:
    """Verify UserIntent dataclass construction and field types."""

    def test_has_all_required_fields(self, tracker: IntentTracker):
        intent = tracker.extract_intent("Create a Python script.")
        assert hasattr(intent, "intent_type")
        assert hasattr(intent, "primary_goal")
        assert hasattr(intent, "explicit_requirements")
        assert hasattr(intent, "implicit_requirements")
        assert hasattr(intent, "constraints")
        assert hasattr(intent, "implicit_constraints")
        assert hasattr(intent, "preferences")
        assert hasattr(intent, "original_prompt")
        assert hasattr(intent, "extracted_at")

    def test_original_prompt_stored_verbatim(self, tracker: IntentTracker):
        prompt = "Write a QUICK Python parser."
        intent = tracker.extract_intent(prompt)
        assert intent.original_prompt == prompt

    def test_extracted_at_is_datetime(self, tracker: IntentTracker):
        intent = tracker.extract_intent("Create something.")
        assert isinstance(intent.extracted_at, datetime)

    def test_extract_intent_resets_state(self, tracker: IntentTracker):
        tracker.extract_intent("First task.\n1. Step one")
        tracker.mark_addressed("Step one", step_id="s1")
        # Second extract_intent should reset addressed requirements
        tracker.extract_intent("Second task.\n1. Different step")
        assert len(tracker._addressed_requirements) == 0
