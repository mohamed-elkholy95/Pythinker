"""Tests for structured output Pydantic models.

Covers Citation, CitedResponse, StepDescription, PlanOutput, PlanUpdateOutput,
ToolCallOutput, ErrorAnalysisOutput, SummaryOutput, and ValidationResult,
plus the validate_llm_output and build_validation_feedback utilities.
"""

import json
from urllib.parse import urlparse

import pytest
from pydantic import ValidationError

from app.domain.models.structured_outputs import (
    Citation,
    CitedResponse,
    ErrorAnalysisOutput,
    PlanOutput,
    PlanUpdateOutput,
    SourceType,
    StepDescription,
    SummaryOutput,
    ToolCallOutput,
    ValidationResult,
    build_validation_feedback,
    validate_llm_output,
)

# =============================================================================
# SourceType
# =============================================================================


class TestSourceType:
    """Tests for the SourceType enum."""

    def test_all_member_values(self):
        """All expected source type string values are defined."""
        assert SourceType.WEB.value == "web"
        assert SourceType.TOOL_RESULT.value == "tool_result"
        assert SourceType.MEMORY.value == "memory"
        assert SourceType.INFERENCE.value == "inference"
        assert SourceType.USER_PROVIDED.value == "user_provided"
        assert SourceType.DOCUMENT.value == "document"
        assert SourceType.CODE.value == "code"

    def test_member_count(self):
        """Exactly 7 source types are defined."""
        assert len(SourceType) == 7

    def test_inherits_from_str(self):
        """SourceType members compare equal to plain strings."""
        assert SourceType.WEB == "web"
        assert SourceType.MEMORY == "memory"
        assert SourceType.INFERENCE == "inference"

    def test_enum_membership(self):
        """String values can be looked up via the enum constructor."""
        assert SourceType("web") is SourceType.WEB
        assert SourceType("tool_result") is SourceType.TOOL_RESULT


# =============================================================================
# Citation
# =============================================================================


class TestCitationRequiredFields:
    """Tests for Citation required field enforcement."""

    def test_minimal_construction_with_enum(self):
        """Citation accepts SourceType enum directly."""
        citation = Citation(text="A factual claim", source_type=SourceType.INFERENCE)
        assert citation.text == "A factual claim"
        assert citation.source_type is SourceType.INFERENCE

    def test_minimal_construction_with_string_source_type(self):
        """A plain string is coerced to the SourceType enum."""
        citation = Citation(text="Some claim", source_type="memory")
        assert citation.source_type is SourceType.MEMORY

    def test_missing_text_raises(self):
        """Omitting text raises ValidationError."""
        with pytest.raises(ValidationError):
            Citation(source_type=SourceType.WEB)  # type: ignore[call-arg]

    def test_missing_source_type_raises(self):
        """Omitting source_type raises ValidationError."""
        with pytest.raises(ValidationError):
            Citation(text="A claim")  # type: ignore[call-arg]

    def test_invalid_source_type_string_raises(self):
        """An unrecognised source type string raises ValidationError."""
        with pytest.raises(ValidationError):
            Citation(text="A claim", source_type="unknown_type")


class TestCitationDefaults:
    """Tests for Citation optional field defaults."""

    def test_url_defaults_to_none(self):
        """url defaults to None when not provided."""
        citation = Citation(text="Fact", source_type=SourceType.CODE)
        assert citation.url is None

    def test_source_id_defaults_to_none(self):
        """source_id defaults to None."""
        citation = Citation(text="Fact", source_type=SourceType.CODE)
        assert citation.source_id is None

    def test_excerpt_defaults_to_none(self):
        """excerpt defaults to None."""
        citation = Citation(text="Fact", source_type=SourceType.CODE)
        assert citation.excerpt is None

    def test_page_number_defaults_to_none(self):
        """page_number defaults to None."""
        citation = Citation(text="Fact", source_type=SourceType.DOCUMENT)
        assert citation.page_number is None

    def test_confidence_defaults_to_0_8(self):
        """confidence defaults to 0.8."""
        citation = Citation(text="Fact", source_type=SourceType.WEB)
        assert citation.confidence == 0.8


class TestCitationFullConstruction:
    """Tests for Citation with all fields supplied."""

    def test_all_fields(self):
        """Citation stores all optional fields correctly."""
        citation = Citation(
            text="Relevant claim",
            source_type=SourceType.DOCUMENT,
            url="https://example.com/doc",
            source_id="doc-42",
            excerpt="The quick brown fox jumped over the lazy dog",
            page_number=7,
            confidence=0.95,
        )
        assert citation.source_id == "doc-42"
        assert citation.excerpt == "The quick brown fox jumped over the lazy dog"
        assert citation.page_number == 7
        assert citation.confidence == 0.95


class TestCitationUrlValidator:
    """Tests for the url field_validator on Citation."""

    def test_valid_https_url(self):
        """A well-formed https URL is accepted."""
        citation = Citation(
            text="Fact",
            source_type=SourceType.WEB,
            url="https://example.com/page",
        )
        assert urlparse(str(citation.url)).scheme == "https"

    def test_valid_http_url(self):
        """A well-formed http URL is accepted."""
        citation = Citation(
            text="Fact",
            source_type=SourceType.WEB,
            url="http://example.com/page",
        )
        assert urlparse(str(citation.url)).scheme == "http"

    def test_www_prefix_gets_https_prepended(self):
        """A URL starting with www. is upgraded to https://."""
        citation = Citation(
            text="Fact",
            source_type=SourceType.WEB,
            url="www.example.com",
        )
        assert urlparse(str(citation.url)).scheme == "https"

    def test_none_url_stays_none(self):
        """Explicitly passing None keeps the field None."""
        citation = Citation(text="Fact", source_type=SourceType.WEB, url=None)
        assert citation.url is None

    def test_empty_string_url_becomes_none(self):
        """An empty string URL is normalised to None."""
        citation = Citation(text="Fact", source_type=SourceType.WEB, url="")
        assert citation.url is None

    def test_whitespace_only_url_becomes_none(self):
        """A whitespace-only URL is normalised to None."""
        citation = Citation(text="Fact", source_type=SourceType.WEB, url="   ")
        assert citation.url is None

    def test_bare_hostname_without_scheme_becomes_none(self):
        """A bare hostname without a recognised scheme is normalised to None."""
        citation = Citation(text="Fact", source_type=SourceType.WEB, url="example.com/path")
        assert citation.url is None

    def test_ftp_url_becomes_none(self):
        """An ftp:// URL (unsupported scheme) is normalised to None."""
        citation = Citation(text="Fact", source_type=SourceType.WEB, url="ftp://files.example.com")
        assert citation.url is None

    def test_url_with_query_string(self):
        """A valid URL containing a query string is accepted."""
        citation = Citation(
            text="Fact",
            source_type=SourceType.WEB,
            url="https://example.com/search?q=python&page=2",
        )
        parsed = urlparse(str(citation.url))
        assert parsed.netloc == "example.com"
        assert parsed.query == "q=python&page=2"


class TestCitationConfidenceBounds:
    """Tests for the confidence ge=0.0, le=1.0 constraint on Citation."""

    def test_confidence_at_zero(self):
        """Confidence of 0.0 is valid."""
        citation = Citation(text="Fact", source_type=SourceType.INFERENCE, confidence=0.0)
        assert citation.confidence == 0.0

    def test_confidence_at_one(self):
        """Confidence of 1.0 is valid."""
        citation = Citation(text="Fact", source_type=SourceType.INFERENCE, confidence=1.0)
        assert citation.confidence == 1.0

    def test_confidence_midpoint(self):
        """Confidence of 0.5 is valid."""
        citation = Citation(text="Fact", source_type=SourceType.INFERENCE, confidence=0.5)
        assert citation.confidence == 0.5

    def test_confidence_below_zero_raises(self):
        """Confidence below 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            Citation(text="Fact", source_type=SourceType.INFERENCE, confidence=-0.1)

    def test_confidence_above_one_raises(self):
        """Confidence above 1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            Citation(text="Fact", source_type=SourceType.INFERENCE, confidence=1.01)

    def test_confidence_negative_large_raises(self):
        """Large negative confidence raises ValidationError."""
        with pytest.raises(ValidationError):
            Citation(text="Fact", source_type=SourceType.INFERENCE, confidence=-100.0)


# =============================================================================
# CitedResponse
# =============================================================================


class TestCitedResponseDefaults:
    """Tests for CitedResponse default field values."""

    def test_minimal_construction(self):
        """CitedResponse can be created with content only."""
        resp = CitedResponse(content="The answer is 42.")
        assert resp.citations == []
        assert resp.confidence == 0.7
        assert resp.grounding_score is None
        assert resp.warning is None

    def test_citations_default_is_independent(self):
        """Each CitedResponse instance gets its own citations list."""
        a = CitedResponse(content="A")
        b = CitedResponse(content="B")
        a.citations.append(Citation(text="Claim", source_type=SourceType.WEB, url="https://x.com"))
        assert b.citations == []

    def test_full_construction(self):
        """CitedResponse accepts all optional fields."""
        citation = Citation(text="Claim", source_type=SourceType.WEB, url="https://example.com")
        resp = CitedResponse(
            content="Full answer.",
            citations=[citation],
            confidence=0.9,
            grounding_score=0.85,
            warning="Data may be outdated.",
        )
        assert len(resp.citations) == 1
        assert resp.grounding_score == 0.85
        assert resp.warning == "Data may be outdated."


class TestCitedResponseHasCitations:
    """Tests for the has_citations property."""

    def test_false_when_empty(self):
        """has_citations is False when no citations are provided."""
        resp = CitedResponse(content="Content.")
        assert resp.has_citations is False

    def test_true_when_one_citation(self):
        """has_citations is True when exactly one citation exists."""
        citation = Citation(text="Claim", source_type=SourceType.TOOL_RESULT)
        resp = CitedResponse(content="Content.", citations=[citation])
        assert resp.has_citations is True

    def test_true_when_multiple_citations(self):
        """has_citations is True when multiple citations exist."""
        citations = [Citation(text=f"Claim {i}", source_type=SourceType.MEMORY) for i in range(3)]
        resp = CitedResponse(content="Content.", citations=citations)
        assert resp.has_citations is True


class TestCitedResponseWebCitations:
    """Tests for the web_citations property."""

    def test_empty_when_no_citations(self):
        """web_citations returns an empty list when there are no citations."""
        resp = CitedResponse(content="Content")
        assert resp.web_citations == []

    def test_filters_to_web_only(self):
        """web_citations returns only citations with source_type WEB."""
        web_cit = Citation(text="Web fact", source_type=SourceType.WEB, url="https://example.com")
        mem_cit = Citation(text="Memory fact", source_type=SourceType.MEMORY)
        tool_cit = Citation(text="Tool fact", source_type=SourceType.TOOL_RESULT)
        resp = CitedResponse(content="Content", citations=[web_cit, mem_cit, tool_cit])
        assert len(resp.web_citations) == 1
        assert resp.web_citations[0].source_type == SourceType.WEB

    def test_all_web_citations_included(self):
        """All web citations are returned when multiple are present."""
        citations = [
            Citation(
                text=f"Fact {i}",
                source_type=SourceType.WEB,
                url=f"https://example.com/{i}",
            )
            for i in range(4)
        ]
        citations.append(Citation(text="Code fact", source_type=SourceType.CODE))
        resp = CitedResponse(content="Content", citations=citations)
        assert len(resp.web_citations) == 4

    def test_empty_when_all_non_web(self):
        """web_citations is empty when no citations are of type WEB."""
        citations = [
            Citation(text="Mem", source_type=SourceType.MEMORY),
            Citation(text="Inf", source_type=SourceType.INFERENCE),
        ]
        resp = CitedResponse(content="Content", citations=citations)
        assert resp.web_citations == []


class TestCitedResponseIsWellGrounded:
    """Tests for the is_well_grounded property."""

    def test_false_without_citations(self):
        """is_well_grounded is False when no citations are present."""
        resp = CitedResponse(content="Content", confidence=1.0)
        assert resp.is_well_grounded is False

    def test_grounding_score_at_threshold(self):
        """is_well_grounded is True when grounding_score is exactly 0.5."""
        citation = Citation(text="Claim", source_type=SourceType.WEB, url="https://example.com")
        resp = CitedResponse(content="Content", citations=[citation], grounding_score=0.5)
        assert resp.is_well_grounded is True

    def test_grounding_score_above_threshold(self):
        """is_well_grounded is True when grounding_score > 0.5."""
        citation = Citation(text="Claim", source_type=SourceType.WEB, url="https://example.com")
        resp = CitedResponse(content="Content", citations=[citation], grounding_score=0.9)
        assert resp.is_well_grounded is True

    def test_grounding_score_below_threshold(self):
        """is_well_grounded is False when grounding_score < 0.5."""
        citation = Citation(text="Claim", source_type=SourceType.INFERENCE)
        resp = CitedResponse(content="Content", citations=[citation], grounding_score=0.49)
        assert resp.is_well_grounded is False

    def test_grounding_score_at_zero(self):
        """Grounding score of 0.0 is below the 0.5 threshold."""
        citation = Citation(text="Claim", source_type=SourceType.WEB, url="https://example.com")
        resp = CitedResponse(content="Content", citations=[citation], grounding_score=0.0)
        assert resp.is_well_grounded is False

    def test_fallback_confidence_at_threshold(self):
        """Falls back to confidence >= 0.7 when grounding_score is None."""
        citation = Citation(text="Claim", source_type=SourceType.DOCUMENT)
        resp = CitedResponse(content="Content", citations=[citation], confidence=0.7)
        assert resp.is_well_grounded is True

    def test_fallback_confidence_above_threshold(self):
        """Falls back to confidence > 0.7 when grounding_score is None."""
        citation = Citation(text="Claim", source_type=SourceType.DOCUMENT)
        resp = CitedResponse(content="Content", citations=[citation], confidence=0.95)
        assert resp.is_well_grounded is True

    def test_fallback_confidence_below_threshold(self):
        """is_well_grounded is False when grounding_score is None and confidence < 0.7."""
        citation = Citation(text="Claim", source_type=SourceType.DOCUMENT)
        resp = CitedResponse(content="Content", citations=[citation], confidence=0.69)
        assert resp.is_well_grounded is False

    def test_grounding_score_takes_precedence_over_confidence(self):
        """grounding_score overrides the confidence fallback when both are present."""
        citation = Citation(text="Claim", source_type=SourceType.WEB, url="https://example.com")
        # confidence would pass (0.9) but grounding_score fails (0.3)
        resp = CitedResponse(
            content="Content",
            citations=[citation],
            confidence=0.9,
            grounding_score=0.3,
        )
        assert resp.is_well_grounded is False


class TestCitedResponseConfidenceBounds:
    """Tests for the confidence field bounds on CitedResponse."""

    def test_confidence_at_zero(self):
        """Confidence of 0.0 is valid."""
        resp = CitedResponse(content="Content", confidence=0.0)
        assert resp.confidence == 0.0

    def test_confidence_at_one(self):
        """Confidence of 1.0 is valid."""
        resp = CitedResponse(content="Content", confidence=1.0)
        assert resp.confidence == 1.0

    def test_confidence_below_zero_raises(self):
        """Confidence below 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            CitedResponse(content="Content", confidence=-0.01)

    def test_confidence_above_one_raises(self):
        """Confidence above 1 raises ValidationError."""
        with pytest.raises(ValidationError):
            CitedResponse(content="Content", confidence=1.001)


# =============================================================================
# StepDescription
# =============================================================================


class TestStepDescriptionValid:
    """Tests for valid StepDescription constructions."""

    def test_minimal_construction(self):
        """StepDescription can be created with only a description."""
        step = StepDescription(description="Search for Python release notes")
        assert step.description == "Search for Python release notes"
        assert step.action_verb == ""
        assert step.target_object == ""
        assert step.tool_hint is None
        assert step.expected_output == ""
        assert step.estimated_complexity is None
        assert step.dependencies == []
        assert step.parallel_safe is True
        assert step.phase is None
        assert step.step_type is None

    def test_description_is_stripped(self):
        """Leading/trailing whitespace in description is stripped."""
        step = StepDescription(description="   Analyze the data   ")
        assert step.description == "Analyze the data"

    def test_exact_minimum_length_after_strip(self):
        """A description of exactly 5 characters (after strip) is valid."""
        step = StepDescription(description="Go do")
        assert step.description == "Go do"

    def test_full_construction(self):
        """StepDescription accepts all optional fields."""
        step = StepDescription(
            description="Browse the top 5 search results for context",
            action_verb="Browse",
            target_object="search results",
            tool_hint="browser_navigate",
            expected_output="A list of page summaries",
            estimated_complexity="medium",
            dependencies=["step-1", "step-2"],
            parallel_safe=False,
            phase="research_foundation",
            step_type="execution",
        )
        assert step.action_verb == "Browse"
        assert step.tool_hint == "browser_navigate"
        assert step.dependencies == ["step-1", "step-2"]
        assert step.parallel_safe is False
        assert step.phase == "research_foundation"
        assert step.step_type == "execution"

    def test_dependencies_default_is_independent(self):
        """Each StepDescription gets its own dependencies list."""
        a = StepDescription(description="First step here")
        b = StepDescription(description="Second step here")
        a.dependencies.append("dep-x")
        assert b.dependencies == []


class TestStepDescriptionValidatorRejectsShort:
    """Tests for the minimum length enforcement on description."""

    def test_single_char_raises(self):
        """A single-character description raises ValidationError."""
        with pytest.raises(ValidationError):
            StepDescription(description="X")

    def test_four_chars_raises(self):
        """A 4-character description raises ValidationError (Pydantic min_length check)."""
        with pytest.raises(ValidationError):
            StepDescription(description="Done")

    def test_empty_description_raises(self):
        """An empty description raises ValidationError."""
        with pytest.raises(ValidationError):
            StepDescription(description="")

    def test_whitespace_only_description_raises(self):
        """A whitespace-only description is stripped and then fails the length check."""
        # "Hi   " passes min_length=5 but strips to "Hi", hitting the custom validator.
        with pytest.raises(ValidationError, match="too short"):
            StepDescription(description="Hi   ")

    def test_five_spaces_raises(self):
        """Five spaces become an empty string after stripping and then fail."""
        with pytest.raises(ValidationError):
            StepDescription(description="     ")


class TestStepDescriptionValidatorRejectsPlaceholders:
    """Tests for placeholder phrase detection in description."""

    @pytest.mark.parametrize(
        "phrase",
        [
            "TODO: implement this step",
            "This is TBD for now",
            "Fill in the details later",
            "Placeholder for the search step",
        ],
    )
    def test_placeholder_phrases_raise(self, phrase: str):
        """Descriptions containing placeholder phrases are rejected."""
        with pytest.raises(ValidationError, match="placeholder"):
            StepDescription(description=phrase)

    def test_case_insensitive_todo(self):
        """'Todo' (mixed case) is detected as placeholder."""
        with pytest.raises(ValidationError, match="placeholder"):
            StepDescription(description="Todo: fix this later")

    def test_case_insensitive_tbd(self):
        """'tbd' (lowercase) embedded in a sentence is detected."""
        with pytest.raises(ValidationError, match="placeholder"):
            StepDescription(description="Content is tbd, revisit")

    def test_case_insensitive_fill_in(self):
        """'fill in' (lowercase) is detected as placeholder."""
        with pytest.raises(ValidationError, match="placeholder"):
            StepDescription(description="Please fill in details here")

    def test_normal_description_is_not_rejected(self):
        """A regular description without placeholder text is accepted."""
        step = StepDescription(description="Analyse Q4 market trends from reports")
        assert "market" in step.description


# =============================================================================
# PlanOutput
# =============================================================================


def _make_step(description: str = "Search for relevant information") -> StepDescription:
    """Return a valid StepDescription for use in PlanOutput tests."""
    return StepDescription(description=description)


class TestPlanOutputValid:
    """Tests for valid PlanOutput constructions."""

    def test_minimal_construction(self):
        """PlanOutput requires goal, title, and at least one step."""
        plan = PlanOutput(
            goal="Research Python 3.12 features",
            title="Python 3.12 Research Plan",
            steps=[_make_step()],
        )
        assert plan.language == "en"
        assert plan.message is None
        assert plan.reasoning is None
        assert plan.estimated_complexity is None

    def test_full_construction(self):
        """PlanOutput accepts all optional fields."""
        plan = PlanOutput(
            goal="Summarise AI trends",
            title="AI Trends Summary",
            language="fr",
            message="Starting research now",
            steps=[_make_step("Search for AI news"), _make_step("Analyse the results")],
            reasoning="Two-step approach for efficiency",
            estimated_complexity="medium",
        )
        assert plan.language == "fr"
        assert len(plan.steps) == 2
        assert plan.reasoning == "Two-step approach for efficiency"
        assert plan.estimated_complexity == "medium"

    def test_title_is_stripped(self):
        """Leading/trailing whitespace in title is stripped by the validator."""
        plan = PlanOutput(
            goal="Goal",
            title="  My Research Plan  ",
            steps=[_make_step()],
        )
        assert plan.title == "My Research Plan"

    def test_many_steps_accepted(self):
        """PlanOutput with many steps is valid."""
        plan = PlanOutput(
            goal="Goal",
            title="Big Plan",
            steps=[_make_step(f"Step {i} description text here") for i in range(10)],
        )
        assert len(plan.steps) == 10

    def test_json_round_trip(self):
        """PlanOutput can be serialised to JSON and re-parsed."""
        plan = PlanOutput(
            goal="Test goal",
            title="Test Plan",
            steps=[_make_step("Test step description here")],
        )
        json_str = plan.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["goal"] == "Test goal"
        assert len(parsed["steps"]) == 1


class TestToolCallOutput:
    """Tests for ToolCallOutput model."""

    def test_whitespace_only_title_raises(self):
        """A whitespace-only title raises ValidationError after stripping."""
        with pytest.raises(ValidationError, match="empty"):
            PlanOutput(goal="Goal", title="   ", steps=[_make_step()])

    def test_empty_title_raises(self):
        """An empty string title raises ValidationError."""
        with pytest.raises(ValidationError, match="empty"):
            PlanOutput(goal="Goal", title="", steps=[_make_step()])


# =============================================================================
# PlanUpdateOutput
# =============================================================================


class TestPlanUpdateOutputDefaults:
    """Tests for PlanUpdateOutput default values."""

    def test_all_defaults(self):
        """PlanUpdateOutput can be instantiated with no arguments."""
        update = PlanUpdateOutput()
        assert update.steps == []
        assert update.message is None
        assert update.completed is False

    def test_with_steps(self):
        """PlanUpdateOutput accepts a non-empty steps list."""
        update = PlanUpdateOutput(steps=[_make_step()], message="Plan updated", completed=True)
        assert len(update.steps) == 1
        assert update.message == "Plan updated"
        assert update.completed is True

    def test_completed_false_explicit(self):
        """completed can be explicitly set to False."""
        update = PlanUpdateOutput(completed=False)
        assert update.completed is False

    def test_steps_default_is_independent(self):
        """Each PlanUpdateOutput instance gets its own steps list."""
        a = PlanUpdateOutput()
        b = PlanUpdateOutput()
        a.steps.append(_make_step())
        assert b.steps == []

    def test_message_can_be_set(self):
        """message field accepts an arbitrary string."""
        update = PlanUpdateOutput(message="All done")
        assert update.message == "All done"


# =============================================================================
# ToolCallOutput
# =============================================================================


class TestToolCallOutputValid:
    """Tests for valid ToolCallOutput constructions."""

    def test_minimal_construction(self):
        """ToolCallOutput requires only tool_name."""
        tool = ToolCallOutput(tool_name="info_search_web")
        assert tool.tool_name == "info_search_web"
        assert tool.arguments == {}
        assert tool.reasoning is None
        assert tool.expected_outcome is None

    def test_full_construction(self):
        """ToolCallOutput accepts all optional fields."""
        tool = ToolCallOutput(
            tool_name="browser_navigate",
            arguments={"url": "https://example.com", "wait": True},
            reasoning="Navigate to find the latest release notes",
            expected_outcome="A fully loaded web page",
        )
        assert tool.tool_name == "browser_navigate"
        assert tool.arguments["url"] == "https://example.com"
        assert tool.reasoning is not None
        assert tool.expected_outcome is not None

    def test_tool_name_surrounding_spaces_stripped(self):
        """Surrounding spaces on tool_name are removed by the validator."""
        tool = ToolCallOutput(tool_name="  shell_exec  ")
        assert tool.tool_name == "shell_exec"

    def test_arguments_default_is_independent(self):
        """Each ToolCallOutput instance gets its own arguments dict."""
        a = ToolCallOutput(tool_name="tool_a")
        b = ToolCallOutput(tool_name="tool_b")
        a.arguments["key"] = "value"
        assert "key" not in b.arguments

    def test_underscore_in_tool_name(self):
        """Underscores in tool_name are valid."""
        tool = ToolCallOutput(tool_name="file_read_tool")
        assert tool.tool_name == "file_read_tool"

    def test_hyphen_in_tool_name(self):
        """Hyphens in tool_name are valid."""
        tool = ToolCallOutput(tool_name="file-read-tool")
        assert tool.tool_name == "file-read-tool"

    def test_nested_arguments(self):
        """Arguments can contain nested structures."""
        tool = ToolCallOutput(
            tool_name="complex_tool",
            arguments={"config": {"timeout": 30, "retries": 3}, "tags": ["a", "b"]},
        )
        assert tool.arguments["config"]["timeout"] == 30
        assert tool.arguments["tags"] == ["a", "b"]


class TestToolCallOutputToolNameValidator:
    """Tests for the tool_name field_validator."""

    def test_empty_tool_name_raises(self):
        """An empty string tool_name raises ValidationError."""
        with pytest.raises(ValidationError, match="empty"):
            ToolCallOutput(tool_name="")

    def test_whitespace_only_tool_name_raises(self):
        """A whitespace-only tool_name is stripped and then fails."""
        with pytest.raises(ValidationError, match="empty"):
            ToolCallOutput(tool_name="   ")

    def test_single_internal_space_raises(self):
        """A tool_name with one internal space raises ValidationError."""
        with pytest.raises(ValidationError, match="spaces"):
            ToolCallOutput(tool_name="browser navigate")

    def test_multiple_internal_spaces_raise(self):
        """A tool_name with multiple spaces raises ValidationError."""
        with pytest.raises(ValidationError, match="spaces"):
            ToolCallOutput(tool_name="my tool name")

    def test_leading_and_trailing_spaces_stripped_not_internal(self):
        """Stripping leaves internal spaces, which then fail validation."""
        with pytest.raises(ValidationError, match="spaces"):
            ToolCallOutput(tool_name="  my tool  ")


# =============================================================================
# ErrorAnalysisOutput
# =============================================================================


class TestErrorAnalysisOutputDefaults:
    """Tests for ErrorAnalysisOutput default field values."""

    def test_minimal_construction(self):
        """ErrorAnalysisOutput requires only error_type."""
        analysis = ErrorAnalysisOutput(error_type="network_timeout")
        assert analysis.error_type == "network_timeout"
        assert analysis.root_cause is None
        assert analysis.is_recoverable is True
        assert analysis.suggested_action is None
        assert analysis.confidence == 0.5

    def test_full_construction(self):
        """ErrorAnalysisOutput accepts all optional fields."""
        analysis = ErrorAnalysisOutput(
            error_type="rate_limit",
            root_cause="Too many requests in short window",
            is_recoverable=True,
            suggested_action="Wait 60 seconds and retry with backoff",
            confidence=0.92,
        )
        assert analysis.root_cause == "Too many requests in short window"
        assert analysis.suggested_action == "Wait 60 seconds and retry with backoff"

    def test_non_recoverable_error(self):
        """is_recoverable can be set to False."""
        analysis = ErrorAnalysisOutput(error_type="disk_full", is_recoverable=False)
        assert analysis.is_recoverable is False

    def test_error_type_required(self):
        """Omitting error_type raises ValidationError."""
        with pytest.raises(ValidationError):
            ErrorAnalysisOutput()  # type: ignore[call-arg]


class TestErrorAnalysisOutputConfidenceBounds:
    """Tests for the confidence bounds on ErrorAnalysisOutput."""

    def test_confidence_at_zero(self):
        """Confidence of 0.0 is valid."""
        analysis = ErrorAnalysisOutput(error_type="unknown", confidence=0.0)
        assert analysis.confidence == 0.0

    def test_confidence_at_one(self):
        """Confidence of 1.0 is valid."""
        analysis = ErrorAnalysisOutput(error_type="unknown", confidence=1.0)
        assert analysis.confidence == 1.0

    def test_confidence_midpoint(self):
        """Confidence of 0.5 is the default and is valid explicitly."""
        analysis = ErrorAnalysisOutput(error_type="unknown", confidence=0.5)
        assert analysis.confidence == 0.5

    def test_confidence_below_zero_raises(self):
        """Confidence below 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ErrorAnalysisOutput(error_type="unknown", confidence=-0.01)

    def test_confidence_above_one_raises(self):
        """Confidence above 1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ErrorAnalysisOutput(error_type="unknown", confidence=1.01)


# =============================================================================
# SummaryOutput
# =============================================================================


class TestSummaryOutputValid:
    """Tests for valid SummaryOutput constructions."""

    def test_success_outcome(self):
        """Outcome 'success' is valid."""
        summary = SummaryOutput(summary="Task completed successfully.", outcome="success")
        assert summary.outcome == "success"

    def test_partial_outcome(self):
        """Outcome 'partial' is valid."""
        summary = SummaryOutput(summary="Task partially completed.", outcome="partial")
        assert summary.outcome == "partial"

    def test_failure_outcome(self):
        """Outcome 'failure' is valid."""
        summary = SummaryOutput(summary="Task failed to complete.", outcome="failure")
        assert summary.outcome == "failure"

    def test_list_field_defaults(self):
        """SummaryOutput list fields default to empty lists."""
        summary = SummaryOutput(summary="Done.", outcome="success")
        assert summary.key_results == []
        assert summary.remaining_items == []
        assert summary.citations == []

    def test_full_construction(self):
        """SummaryOutput accepts all optional fields."""
        citation = Citation(
            text="Source claim",
            source_type=SourceType.WEB,
            url="https://example.com",
        )
        summary = SummaryOutput(
            summary="Comprehensive research completed.",
            outcome="success",
            key_results=["Found 10 sources", "Generated a final report"],
            remaining_items=["Follow-up verification required"],
            citations=[citation],
        )
        assert len(summary.key_results) == 2
        assert len(summary.remaining_items) == 1
        assert len(summary.citations) == 1

    def test_summary_required(self):
        """Omitting summary raises ValidationError."""
        with pytest.raises(ValidationError):
            SummaryOutput(outcome="success")  # type: ignore[call-arg]

    def test_outcome_required(self):
        """Omitting outcome raises ValidationError."""
        with pytest.raises(ValidationError):
            SummaryOutput(summary="Done.")  # type: ignore[call-arg]


class TestSummaryOutputOutcomeNormalisation:
    """Tests for case normalisation in the outcome validator."""

    def test_uppercase_success(self):
        """'SUCCESS' is normalised to 'success'."""
        summary = SummaryOutput(summary="Done.", outcome="SUCCESS")
        assert summary.outcome == "success"

    def test_mixed_case_partial(self):
        """'Partial' is normalised to 'partial'."""
        summary = SummaryOutput(summary="Done.", outcome="Partial")
        assert summary.outcome == "partial"

    def test_uppercase_failure(self):
        """'FAILURE' is normalised to 'failure'."""
        summary = SummaryOutput(summary="Done.", outcome="FAILURE")
        assert summary.outcome == "failure"

    def test_surrounding_whitespace_stripped(self):
        """Surrounding whitespace is stripped before validation."""
        summary = SummaryOutput(summary="Done.", outcome="  success  ")
        assert summary.outcome == "success"

    def test_mixed_case_with_spaces(self):
        """Mixed case with surrounding spaces is normalised correctly."""
        summary = SummaryOutput(summary="Done.", outcome="  PARTIAL  ")
        assert summary.outcome == "partial"


class TestSummaryOutputOutcomeValidation:
    """Tests for invalid outcome values."""

    @pytest.mark.parametrize(
        "invalid_outcome",
        [
            "complete",
            "done",
            "ok",
            "error",
            "",
            "succeeded",
            "passed",
            "aborted",
            "cancelled",
        ],
    )
    def test_invalid_outcome_raises(self, invalid_outcome: str):
        """Outcome values outside {success, partial, failure} raise ValidationError."""
        with pytest.raises(ValidationError):
            SummaryOutput(summary="Done.", outcome=invalid_outcome)


class TestSummaryOutputDefaultsAreIndependent:
    """Tests that mutable default lists are not shared between instances."""

    def test_key_results_independent(self):
        """Each SummaryOutput instance gets its own key_results list."""
        a = SummaryOutput(summary="Done.", outcome="success")
        b = SummaryOutput(summary="Done.", outcome="failure")
        a.key_results.append("Result A")
        assert b.key_results == []

    def test_remaining_items_independent(self):
        """Each SummaryOutput instance gets its own remaining_items list."""
        a = SummaryOutput(summary="Done.", outcome="partial")
        b = SummaryOutput(summary="Done.", outcome="partial")
        a.remaining_items.append("Item A")
        assert b.remaining_items == []

    def test_citations_independent(self):
        """Each SummaryOutput instance gets its own citations list."""
        a = SummaryOutput(summary="Done.", outcome="success")
        b = SummaryOutput(summary="Done.", outcome="partial")
        a.citations.append(Citation(text="Claim", source_type=SourceType.INFERENCE))
        assert b.citations == []


# =============================================================================
# ValidationResult
# =============================================================================


class TestValidationResult:
    """Tests for the ValidationResult model."""

    def test_valid_result_all_defaults(self):
        """A passing ValidationResult has empty list fields."""
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.suggestions == []

    def test_invalid_result_with_errors(self):
        """An invalid result carries error messages."""
        result = ValidationResult(
            is_valid=False,
            errors=["Field 'goal' is required", "Step description too short"],
        )
        assert result.is_valid is False
        assert len(result.errors) == 2
        assert "Field 'goal' is required" in result.errors

    def test_full_construction(self):
        """ValidationResult accepts errors, warnings, and suggestions together."""
        result = ValidationResult(
            is_valid=False,
            errors=["Missing field"],
            warnings=["Low confidence score"],
            suggestions=["Add more citations", "Include required fields"],
        )
        assert result.warnings == ["Low confidence score"]
        assert len(result.suggestions) == 2

    def test_is_valid_required(self):
        """Omitting is_valid raises ValidationError."""
        with pytest.raises(ValidationError):
            ValidationResult()  # type: ignore[call-arg]

    def test_list_defaults_are_independent(self):
        """Each ValidationResult instance has independent list fields."""
        a = ValidationResult(is_valid=True)
        b = ValidationResult(is_valid=False)
        a.errors.append("some error")
        a.warnings.append("some warning")
        a.suggestions.append("some suggestion")
        assert b.errors == []
        assert b.warnings == []
        assert b.suggestions == []

    def test_is_valid_false_with_no_errors(self):
        """is_valid can be False with an empty errors list."""
        result = ValidationResult(is_valid=False)
        assert result.is_valid is False
        assert result.errors == []

    def test_is_valid_true_with_warnings(self):
        """is_valid can be True while warnings are present."""
        result = ValidationResult(is_valid=True, warnings=["Minor issue"])
        assert result.is_valid is True
        assert len(result.warnings) == 1


# =============================================================================
# validate_llm_output utility
# =============================================================================


class TestValidateLlmOutput:
    """Tests for the validate_llm_output helper function."""

    def test_valid_summary_output(self):
        """Valid JSON for SummaryOutput returns the parsed model and is_valid=True."""
        json_str = '{"summary": "Task done.", "outcome": "success"}'
        parsed, result = validate_llm_output(json_str, SummaryOutput)
        assert result.is_valid is True
        assert isinstance(parsed, SummaryOutput)
        assert parsed.outcome == "success"

    def test_invalid_json_returns_none_and_errors(self):
        """Malformed JSON returns None and a failing ValidationResult."""
        parsed, result = validate_llm_output("not valid json {{", SummaryOutput)
        assert parsed is None
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_missing_required_field_returns_none(self):
        """JSON missing a required field (outcome) returns None."""
        json_str = '{"summary": "Done."}'
        parsed, result = validate_llm_output(json_str, SummaryOutput)
        assert parsed is None
        assert result.is_valid is False

    def test_low_confidence_adds_warning(self):
        """A parsed model with confidence < 0.3 triggers a low-confidence warning."""
        json_str = '{"error_type": "unknown", "confidence": 0.1}'
        parsed, result = validate_llm_output(json_str, ErrorAnalysisOutput)
        assert result.is_valid is True
        assert parsed is not None
        assert any("confidence" in w.lower() for w in result.warnings)

    def test_confidence_at_threshold_no_warning(self):
        """Confidence of exactly 0.3 does NOT trigger a low-confidence warning."""
        json_str = '{"error_type": "unknown", "confidence": 0.3}'
        _parsed, result = validate_llm_output(json_str, ErrorAnalysisOutput)
        assert result.is_valid is True
        assert not any("confidence" in w.lower() for w in result.warnings)

    def test_no_citations_adds_warning_for_cited_response(self):
        """A CitedResponse with no citations triggers a citations warning."""
        json_str = '{"content": "Some content.", "confidence": 0.8}'
        parsed, result = validate_llm_output(json_str, CitedResponse)
        assert result.is_valid is True
        assert parsed is not None
        assert any("citation" in w.lower() for w in result.warnings)

    def test_valid_plan_output(self):
        """Valid PlanOutput JSON is fully parsed."""
        json_str = json.dumps(
            {
                "goal": "Research AI",
                "title": "AI Research Plan",
                "steps": [{"description": "Search for AI trends"}],
            }
        )
        parsed, result = validate_llm_output(json_str, PlanOutput)
        assert result.is_valid is True
        assert isinstance(parsed, PlanOutput)
        assert parsed.title == "AI Research Plan"

    def test_valid_tool_call_output(self):
        """Valid ToolCallOutput JSON is correctly parsed."""
        json_str = '{"tool_name": "info_search_web", "arguments": {"query": "python"}}'
        parsed, result = validate_llm_output(json_str, ToolCallOutput)
        assert result.is_valid is True
        assert isinstance(parsed, ToolCallOutput)
        assert parsed.tool_name == "info_search_web"

    def test_invalid_outcome_in_summary(self):
        """An invalid outcome value causes is_valid=False."""
        json_str = '{"summary": "Done.", "outcome": "complete"}'
        parsed, result = validate_llm_output(json_str, SummaryOutput)
        assert parsed is None
        assert result.is_valid is False

    def test_low_confidence_warning(self):
        """Test warning for low confidence score."""
        json_content = json.dumps(
            {
                "error_type": "timeout",
                "root_cause": "Slow API",
                "confidence": 0.2,
            }
        )
        _result, validation = validate_llm_output(json_content, ErrorAnalysisOutput)
        assert validation.is_valid is True
        assert any("confidence" in w.lower() for w in validation.warnings)

    def test_missing_field_suggestion_included(self):
        """When a required field is absent, a 'required' suggestion is generated."""
        json_str = '{"goal": "A goal", "steps": [{"description": "Step one here"}]}'
        _parsed, result = validate_llm_output(json_str, PlanOutput)
        assert result.is_valid is False
        assert any("required" in s.lower() for s in result.suggestions)


# =============================================================================
# build_validation_feedback utility
# =============================================================================


class TestBuildValidationFeedback:
    """Tests for the build_validation_feedback helper function."""

    def test_empty_result_produces_empty_string(self):
        """A valid result with no errors or suggestions produces an empty string."""
        result = ValidationResult(is_valid=True)
        feedback = build_validation_feedback(result)
        assert feedback == ""

    def test_errors_header_present(self):
        """Error messages are included under an ERRORS header."""
        result = ValidationResult(
            is_valid=False,
            errors=["Field 'goal' is required"],
        )
        feedback = build_validation_feedback(result)
        assert "ERRORS" in feedback
        assert "Field 'goal' is required" in feedback

    def test_suggestions_header_present(self):
        """Suggestions are included under a SUGGESTIONS header."""
        result = ValidationResult(
            is_valid=False,
            errors=["Missing field"],
            suggestions=["Include all required fields"],
        )
        feedback = build_validation_feedback(result)
        assert "SUGGESTIONS" in feedback
        assert "Include all required fields" in feedback

    def test_multiple_errors_all_listed(self):
        """All errors appear in the feedback string."""
        result = ValidationResult(
            is_valid=False,
            errors=["Error one", "Error two", "Error three"],
        )
        feedback = build_validation_feedback(result)
        assert "Error one" in feedback
        assert "Error two" in feedback
        assert "Error three" in feedback

    def test_multiple_suggestions_all_listed(self):
        """All suggestions appear in the feedback string."""
        result = ValidationResult(
            is_valid=False,
            errors=["Error"],
            suggestions=["Suggestion A", "Suggestion B"],
        )
        feedback = build_validation_feedback(result)
        assert "Suggestion A" in feedback
        assert "Suggestion B" in feedback

    def test_warnings_not_included_in_feedback(self):
        """build_validation_feedback does not include warnings."""
        result = ValidationResult(
            is_valid=True,
            warnings=["Low confidence — this should not appear in feedback"],
        )
        feedback = build_validation_feedback(result)
        assert "Low confidence" not in feedback

    def test_errors_only_no_suggestions(self):
        """Feedback with errors but no suggestions does not include SUGGESTIONS header."""
        result = ValidationResult(is_valid=False, errors=["An error occurred"])
        feedback = build_validation_feedback(result)
        assert "An error occurred" in feedback
        assert "SUGGESTIONS" not in feedback

    def test_suggestions_only_no_errors(self):
        """Feedback can contain suggestions even without errors."""
        result = ValidationResult(is_valid=True, suggestions=["Consider adding citations"])
        feedback = build_validation_feedback(result)
        assert "SUGGESTIONS" in feedback
        assert "Consider adding citations" in feedback
