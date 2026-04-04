"""
Tests for the VerifierAgent and verification workflow.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.agent_response import (
    DependencyIssue,
    PrerequisiteCheck,
    ToolFeasibility,
    VerificationResponse,
    VerificationVerdict,
)
from app.domain.models.event import VerificationEvent, VerificationStatus
from app.domain.models.plan import Plan, Step
from app.domain.models.tool_permission import PermissionTier
from app.domain.services.agents.verifier import VerifierAgent, VerifierConfig
from app.domain.services.tools.base import BaseTool, tool


class TestVerifierConfig:
    """Tests for VerifierConfig dataclass"""

    def test_default_initialization(self):
        """Test default config initialization"""
        config = VerifierConfig()
        assert config.enabled is True
        assert config.skip_simple_plans is True
        assert config.simple_plan_max_steps == 2
        assert config.max_revision_loops == 2
        assert "search" in config.simple_operations

    def test_custom_initialization(self):
        """Test custom config initialization"""
        config = VerifierConfig(
            enabled=False,
            skip_simple_plans=False,
            simple_plan_max_steps=3,
            max_revision_loops=3,
        )
        assert config.enabled is False
        assert config.skip_simple_plans is False
        assert config.simple_plan_max_steps == 3


class TestVerificationModels:
    """Tests for verification response models"""

    def test_tool_feasibility_model(self):
        """Test ToolFeasibility model"""
        tf = ToolFeasibility(step_id="1", tool="shell_exec", feasible=True, reason="Standard shell command")
        assert tf.step_id == "1"
        assert tf.feasible is True

    def test_prerequisite_check_model(self):
        """Test PrerequisiteCheck model"""
        pc = PrerequisiteCheck(check="Internet access", satisfied=True, detail="Network available")
        assert pc.check == "Internet access"
        assert pc.satisfied is True

    def test_dependency_issue_model(self):
        """Test DependencyIssue model"""
        di = DependencyIssue(step_id="2", depends_on="1", issue="Step 2 needs output from step 1")
        assert di.step_id == "2"
        assert di.depends_on == "1"

    def test_verification_response_model(self):
        """Test VerificationResponse model"""
        response = VerificationResponse(
            verdict=VerificationVerdict.PASS,
            confidence=0.9,
            tool_feasibility=[ToolFeasibility(step_id="1", tool="search", feasible=True, reason="OK")],
            prerequisite_checks=[],
            dependency_issues=[],
            summary="Plan verified successfully",
        )
        assert response.verdict == VerificationVerdict.PASS
        assert response.confidence == 0.9
        assert len(response.tool_feasibility) == 1


class TestVerifierAgent:
    """Tests for VerifierAgent class"""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM"""
        llm = MagicMock()
        llm.ask = AsyncMock(return_value={"content": '{"verdict": "pass", "confidence": 0.9, "summary": "OK"}'})
        return llm

    @pytest.fixture
    def mock_json_parser(self):
        """Create mock JSON parser"""
        parser = MagicMock()
        parser.parse = AsyncMock(
            return_value={
                "verdict": "pass",
                "confidence": 0.9,
                "summary": "Plan verified successfully",
                "tool_feasibility": [],
                "prerequisite_checks": [],
                "dependency_issues": [],
            }
        )
        return parser

    @pytest.fixture
    def mock_tools(self):
        """Create mock tools list"""
        tool = MagicMock()
        tool.get_tools.return_value = [
            {"function": {"name": "shell_exec", "description": "Execute shell commands"}},
            {"function": {"name": "search", "description": "Search the web"}},
        ]
        return [tool]

    @pytest.fixture
    def simple_plan(self):
        """Create a simple test plan"""
        return Plan(
            title="Simple Search",
            goal="Search for information",
            steps=[
                Step(id="1", description="Search for Python tutorials"),
            ],
        )

    @pytest.fixture
    def complex_plan(self):
        """Create a complex test plan"""
        return Plan(
            title="Complex Task",
            goal="Build a web application",
            steps=[
                Step(id="1", description="Design database schema"),
                Step(id="2", description="Create backend API"),
                Step(id="3", description="Build frontend UI"),
                Step(id="4", description="Deploy application"),
            ],
        )

    def test_initialization(self, mock_llm, mock_json_parser, mock_tools):
        """Test verifier initialization"""
        verifier = VerifierAgent(llm=mock_llm, json_parser=mock_json_parser, tools=mock_tools)
        assert verifier.llm == mock_llm
        assert verifier.config.enabled is True

    def test_set_active_tier_filters_visible_tools(self, mock_llm, mock_json_parser):
        """Tier sync should not crash and should hide tools above the active tier."""

        class ReadOnlyTool(BaseTool):
            name = "read_only"

            @tool(
                name="file_read",
                description="Read a file",
                parameters={},
                required=[],
                is_read_only=True,
            )
            async def file_read(self):
                pass

        class DangerousTool(BaseTool):
            name = "dangerous"

            @tool(
                name="shell_exec",
                description="Execute shell commands",
                parameters={},
                required=[],
                required_tier=PermissionTier.DANGER,
            )
            async def shell_exec(self):
                pass

        verifier = VerifierAgent(
            llm=mock_llm,
            json_parser=mock_json_parser,
            tools=[ReadOnlyTool(), DangerousTool()],
        )

        assert "file_read" in verifier._tool_names
        assert "shell_exec" in verifier._tool_names

        verifier.set_active_tier(PermissionTier.READ_ONLY)

        assert "file_read" in verifier._tool_names
        assert "shell_exec" not in verifier._tool_names
        assert "file_read" in verifier._tool_descriptions
        assert "shell_exec" not in verifier._tool_descriptions

    def test_should_skip_simple_plan(self, mock_llm, mock_json_parser, mock_tools, simple_plan):
        """Test that simple plans are skipped"""
        verifier = VerifierAgent(
            llm=mock_llm, json_parser=mock_json_parser, tools=mock_tools, config=VerifierConfig(skip_simple_plans=True)
        )
        assert verifier._should_skip_verification(simple_plan) is True

    def test_should_not_skip_complex_plan(self, mock_llm, mock_json_parser, mock_tools, complex_plan):
        """Test that complex plans are not skipped"""
        verifier = VerifierAgent(
            llm=mock_llm, json_parser=mock_json_parser, tools=mock_tools, config=VerifierConfig(skip_simple_plans=True)
        )
        assert verifier._should_skip_verification(complex_plan) is False

    def test_should_not_skip_when_disabled(self, mock_llm, mock_json_parser, mock_tools, simple_plan):
        """Test that no plans are skipped when skip_simple_plans is False"""
        verifier = VerifierAgent(
            llm=mock_llm, json_parser=mock_json_parser, tools=mock_tools, config=VerifierConfig(skip_simple_plans=False)
        )
        assert verifier._should_skip_verification(simple_plan) is False

    @pytest.mark.asyncio
    async def test_verify_simple_plan_skipped(self, mock_llm, mock_json_parser, mock_tools, simple_plan):
        """Test verification of simple plan is skipped"""
        verifier = VerifierAgent(
            llm=mock_llm, json_parser=mock_json_parser, tools=mock_tools, config=VerifierConfig(skip_simple_plans=True)
        )

        events = [event async for event in verifier.verify_plan(simple_plan, "Search for info")]

        assert len(events) == 1
        assert isinstance(events[0], VerificationEvent)
        assert events[0].status == VerificationStatus.PASSED
        assert events[0].verdict == "pass"

    @pytest.mark.asyncio
    async def test_verify_complex_plan(self, mock_llm, mock_json_parser, mock_tools, complex_plan):
        """Test verification of complex plan"""
        verifier = VerifierAgent(
            llm=mock_llm, json_parser=mock_json_parser, tools=mock_tools, config=VerifierConfig(skip_simple_plans=True)
        )

        events = [event async for event in verifier.verify_plan(complex_plan, "Build web app")]

        assert len(events) == 2  # STARTED + result
        assert events[0].status == VerificationStatus.STARTED
        assert events[1].status == VerificationStatus.PASSED

    @pytest.mark.asyncio
    async def test_verify_plan_revise_verdict(self, mock_llm, mock_json_parser, mock_tools, complex_plan):
        """Test verification with REVISE verdict"""
        mock_json_parser.parse = AsyncMock(
            return_value={
                "verdict": "revise",
                "confidence": 0.7,
                "summary": "Plan needs revision",
                "revision_feedback": "Step 2 is not feasible",
                "tool_feasibility": [],
                "prerequisite_checks": [],
                "dependency_issues": [],
            }
        )

        verifier = VerifierAgent(
            llm=mock_llm,
            json_parser=mock_json_parser,
            tools=mock_tools,
        )

        events = [event async for event in verifier.verify_plan(complex_plan, "Build web app")]

        result_event = events[-1]
        assert result_event.status == VerificationStatus.REVISION_NEEDED
        assert result_event.verdict == "revise"
        assert result_event.revision_feedback == "Step 2 is not feasible"

    @pytest.mark.asyncio
    async def test_verify_plan_fail_verdict(self, mock_llm, mock_json_parser, mock_tools, complex_plan):
        """Test verification with FAIL verdict"""
        mock_json_parser.parse = AsyncMock(
            return_value={
                "verdict": "fail",
                "confidence": 0.9,
                "summary": "Plan is impossible",
                "tool_feasibility": [],
                "prerequisite_checks": [],
                "dependency_issues": [],
            }
        )

        verifier = VerifierAgent(
            llm=mock_llm,
            json_parser=mock_json_parser,
            tools=mock_tools,
        )

        events = [event async for event in verifier.verify_plan(complex_plan, "Build web app")]

        result_event = events[-1]
        assert result_event.status == VerificationStatus.FAILED
        assert result_event.verdict == "fail"

    @pytest.mark.asyncio
    async def test_verify_plan_error_failopen(self, mock_llm, mock_json_parser, mock_tools, complex_plan):
        """Test verification fails open on error"""
        mock_json_parser.parse = AsyncMock(side_effect=Exception("Parse error"))

        verifier = VerifierAgent(
            llm=mock_llm,
            json_parser=mock_json_parser,
            tools=mock_tools,
        )

        events = [event async for event in verifier.verify_plan(complex_plan, "Build web app")]

        result_event = events[-1]
        # Should fail open with PASSED
        assert result_event.status == VerificationStatus.PASSED
        assert result_event.confidence == 0.5

    def test_get_revision_prompt_addition(self, mock_llm, mock_json_parser, mock_tools):
        """Test revision prompt generation"""
        verifier = VerifierAgent(
            llm=mock_llm,
            json_parser=mock_json_parser,
            tools=mock_tools,
        )

        response = VerificationResponse(
            verdict=VerificationVerdict.REVISE,
            confidence=0.7,
            tool_feasibility=[ToolFeasibility(step_id="1", tool="db_query", feasible=False, reason="No DB access")],
            dependency_issues=[DependencyIssue(step_id="2", depends_on="1", issue="Needs DB data")],
            revision_feedback="Use web APIs instead of database",
            summary="Plan needs revision",
        )

        prompt = verifier.get_revision_prompt_addition(response)

        assert "Verification Feedback" in prompt
        assert "Use web APIs instead of database" in prompt
        assert "Step 1" in prompt
        assert "No DB access" in prompt
