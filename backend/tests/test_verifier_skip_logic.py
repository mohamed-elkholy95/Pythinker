"""Tests for enhanced verifier skip logic."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.plan import Plan, Step
from app.domain.services.agents.verifier import (
    SkipDecision,
    VerifierAgent,
    VerifierConfig,
)


class TestSkipDecision:
    """Tests for SkipDecision dataclass."""

    def test_skip_decision_basic(self):
        """Test basic SkipDecision creation."""
        decision = SkipDecision(
            should_skip=True,
            confidence=0.95,
            reason="Simple plan",
            warnings=[],
        )

        assert decision.should_skip is True
        assert decision.confidence == 0.95
        assert decision.adjusted_confidence == 0.95

    def test_adjusted_confidence_with_warnings(self):
        """Test that warnings reduce confidence."""
        decision = SkipDecision(
            should_skip=True,
            confidence=0.95,
            reason="Simple plan",
            warnings=["warning1", "warning2"],
        )

        # 2 warnings = 0.10 penalty
        assert decision.adjusted_confidence == 0.85

    def test_adjusted_confidence_minimum(self):
        """Test that adjusted confidence doesn't go below 0.5."""
        decision = SkipDecision(
            should_skip=True,
            confidence=0.60,
            reason="Simple plan",
            warnings=["w1", "w2", "w3", "w4", "w5"],  # 0.25 penalty
        )

        assert decision.adjusted_confidence == 0.5


class TestVerifierSkipLogic:
    """Tests for VerifierAgent skip logic."""

    def _create_verifier(self, config: VerifierConfig | None = None) -> VerifierAgent:
        """Create a verifier with mocked dependencies."""
        llm = MagicMock()
        json_parser = MagicMock()

        # Create mock tools
        mock_tool = MagicMock()
        mock_tool.get_tools.return_value = [
            {"function": {"name": "search", "description": "Search the web"}},
            {"function": {"name": "browse", "description": "Browse a URL"}},
            {"function": {"name": "read_file", "description": "Read a file"}},
        ]

        return VerifierAgent(
            llm=llm,
            json_parser=json_parser,
            tools=[mock_tool],
            config=config or VerifierConfig(),
        )

    def test_skip_disabled_in_config(self):
        """Test that verification is skipped when disabled."""
        config = VerifierConfig(enabled=False)
        verifier = self._create_verifier(config)

        plan = Plan(title="Test", goal="Test goal", steps=[])
        decision = verifier._analyze_skip_decision(plan)

        assert decision.should_skip is True
        assert decision.reason == "Verification disabled in config"

    def test_skip_simple_plans_disabled(self):
        """Test that skip is disabled when configured."""
        config = VerifierConfig(skip_simple_plans=False)
        verifier = self._create_verifier(config)

        plan = Plan(
            title="Test",
            goal="Test goal",
            steps=[Step(id="1", description="Search for something")],
        )
        decision = verifier._analyze_skip_decision(plan)

        assert decision.should_skip is False
        assert "skipping disabled" in decision.reason

    def test_too_many_steps(self):
        """Test that plans with many steps are not skipped."""
        config = VerifierConfig(simple_plan_max_steps=2)
        verifier = self._create_verifier(config)

        plan = Plan(
            title="Test",
            goal="Test goal",
            steps=[
                Step(id="1", description="Search step 1"),
                Step(id="2", description="Search step 2"),
                Step(id="3", description="Search step 3"),
            ],
        )
        decision = verifier._analyze_skip_decision(plan)

        assert decision.should_skip is False
        assert "3 steps" in decision.reason

    def test_complex_operation_not_skipped(self):
        """Test that plans with complex operations are not skipped."""
        verifier = self._create_verifier()

        plan = Plan(
            title="Test",
            goal="Test goal",
            steps=[Step(id="1", description="Implement a new feature with code")],
        )
        decision = verifier._analyze_skip_decision(plan)

        assert decision.should_skip is False
        assert "not simple operations" in decision.reason

    def test_simple_search_plan_skipped(self):
        """Test that simple search plan is skipped."""
        verifier = self._create_verifier()

        plan = Plan(
            title="Test",
            goal="Test goal",
            steps=[Step(id="1", description="Search for Python tutorials")],
        )
        decision = verifier._analyze_skip_decision(plan)

        assert decision.should_skip is True
        assert decision.confidence >= 0.85

    def test_multiple_tool_types_not_skipped(self):
        """Test that plans using multiple tool types are not skipped."""
        config = VerifierConfig(max_tools_for_simple=1)
        verifier = self._create_verifier(config)

        plan = Plan(
            title="Test",
            goal="Test goal",
            steps=[
                Step(id="1", description="Search for info"),
                Step(id="2", description="Browse the results"),
            ],
        )
        decision = verifier._analyze_skip_decision(plan)

        assert decision.should_skip is False
        assert "tool types" in decision.reason

    def test_dependencies_add_warning(self):
        """Test that step dependencies add warnings."""
        verifier = self._create_verifier()

        plan = Plan(
            title="Test",
            goal="Test goal",
            steps=[
                Step(id="1", description="Search for data"),
                Step(id="2", description="Read the results", dependencies=["1"]),
            ],
        )
        decision = verifier._analyze_skip_decision(plan)

        # Should still skip (2 steps, both simple) but with warning
        if decision.should_skip:
            assert "dependencies" in str(decision.warnings)
            assert decision.adjusted_confidence < decision.confidence


class TestInferToolTypes:
    """Tests for tool type inference."""

    def _create_verifier(self) -> VerifierAgent:
        """Create a basic verifier."""
        llm = MagicMock()
        json_parser = MagicMock()
        mock_tool = MagicMock()
        mock_tool.get_tools.return_value = []
        return VerifierAgent(llm=llm, json_parser=json_parser, tools=[mock_tool])

    def test_infer_search(self):
        """Test inferring search tool type."""
        verifier = self._create_verifier()
        plan = Plan(
            title="Test",
            goal="Find info",
            steps=[Step(id="1", description="Search for Python tutorials")],
        )

        types = verifier._infer_tool_types(plan)
        assert "search" in types

    def test_infer_browser(self):
        """Test inferring browser tool type."""
        verifier = self._create_verifier()
        plan = Plan(
            title="Test",
            goal="Browse web",
            steps=[Step(id="1", description="Navigate to the homepage and click login")],
        )

        types = verifier._infer_tool_types(plan)
        assert "browser" in types

    def test_infer_shell(self):
        """Test inferring shell tool type."""
        verifier = self._create_verifier()
        plan = Plan(
            title="Test",
            goal="Run command",
            steps=[Step(id="1", description="Execute the test command in terminal")],
        )

        types = verifier._infer_tool_types(plan)
        assert "shell" in types

    def test_infer_multiple_types(self):
        """Test inferring multiple tool types."""
        verifier = self._create_verifier()
        plan = Plan(
            title="Test",
            goal="Complex task",
            steps=[
                Step(id="1", description="Search for documentation"),
                Step(id="2", description="Browse the results and click links"),
                Step(id="3", description="Run the install command"),
            ],
        )

        types = verifier._infer_tool_types(plan)
        assert len(types) >= 2


class TestToolAvailability:
    """Tests for tool availability checking."""

    def test_available_tool_not_flagged(self):
        """Test that available tools are not flagged as missing."""
        llm = MagicMock()
        json_parser = MagicMock()
        mock_tool = MagicMock()
        mock_tool.get_tools.return_value = [
            {"function": {"name": "web_search", "description": "Search"}},
        ]

        verifier = VerifierAgent(llm=llm, json_parser=json_parser, tools=[mock_tool])

        plan = Plan(
            title="Test",
            goal="Search",
            steps=[Step(id="1", description="Search for info")],
        )

        missing = verifier._check_tool_availability(plan)
        assert "search" not in missing

    def test_missing_tool_flagged(self):
        """Test that missing tools are flagged."""
        llm = MagicMock()
        json_parser = MagicMock()
        mock_tool = MagicMock()
        mock_tool.get_tools.return_value = [
            {"function": {"name": "web_search", "description": "Search"}},
        ]

        verifier = VerifierAgent(llm=llm, json_parser=json_parser, tools=[mock_tool])

        plan = Plan(
            title="Test",
            goal="Run code",
            steps=[Step(id="1", description="Execute the shell command")],
        )

        missing = verifier._check_tool_availability(plan)
        assert "shell" in missing


class TestVerifyPlanSkipIntegration:
    """Integration tests for verify_plan with skip logic."""

    @pytest.mark.asyncio
    async def test_simple_plan_yields_skip_event(self):
        """Test that simple plans yield a skip event."""
        llm = MagicMock()
        json_parser = MagicMock()
        mock_tool = MagicMock()
        mock_tool.get_tools.return_value = [
            {"function": {"name": "search", "description": "Search"}},
        ]

        verifier = VerifierAgent(llm=llm, json_parser=json_parser, tools=[mock_tool])

        plan = Plan(
            title="Simple Search",
            goal="Find info",
            steps=[Step(id="1", description="Search for Python docs")],
        )

        events = []
        async for event in verifier.verify_plan(plan, "find python docs"):
            events.append(event)

        assert len(events) == 1
        assert events[0].status.value == "passed"
        assert "skipped" in events[0].summary.lower()

    @pytest.mark.asyncio
    async def test_complex_plan_not_skipped(self):
        """Test that complex plans are not skipped."""
        llm = MagicMock()
        # Mock LLM to return verification response
        llm.generate = AsyncMock(return_value='{"verdict": "pass", "confidence": 0.9}')

        json_parser = MagicMock()
        json_parser.parse.return_value = {
            "verdict": "pass",
            "confidence": 0.9,
            "tool_feasibility": [],
            "prerequisite_checks": [],
            "dependency_issues": [],
            "summary": "Plan looks good",
        }

        mock_tool = MagicMock()
        mock_tool.get_tools.return_value = [
            {"function": {"name": "code", "description": "Write code"}},
        ]

        verifier = VerifierAgent(llm=llm, json_parser=json_parser, tools=[mock_tool])

        plan = Plan(
            title="Complex Task",
            goal="Build feature",
            steps=[
                Step(id="1", description="Implement the authentication system"),
                Step(id="2", description="Write unit tests for auth"),
                Step(id="3", description="Deploy to staging"),
            ],
        )

        events = []
        async for event in verifier.verify_plan(plan, "build auth"):
            events.append(event)

        # Should have started event (not immediately skipped)
        assert any("started" in str(e.status).lower() for e in events)


class TestConfigDefaults:
    """Tests for configuration defaults."""

    def test_default_config(self):
        """Test default configuration values."""
        config = VerifierConfig()

        assert config.enabled is True
        assert config.skip_simple_plans is True
        assert config.simple_plan_max_steps == 2
        assert config.max_tools_for_simple == 1
        assert config.min_skip_confidence == 0.95
        assert config.require_tool_availability is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = VerifierConfig(
            simple_plan_max_steps=3,
            max_tools_for_simple=2,
            min_skip_confidence=0.90,
        )

        assert config.simple_plan_max_steps == 3
        assert config.max_tools_for_simple == 2
        assert config.min_skip_confidence == 0.90
