"""
Unit tests for plan streaming in PlannerAgent.

Tests the plan markdown formatter, synchronous chunker,
and the async planning stream integration in create_plan().
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.event import PlanEvent, PlanStatus, StreamEvent
from app.domain.models.plan import Plan, Step
from app.domain.services.agents.planner import (
    PlannerAgent,
    _format_plan_as_markdown,
    _iter_plan_markdown_chunks,
)


@pytest.fixture
def three_step_plan() -> Plan:
    """Synthetic plan with three structured steps."""
    return Plan(
        title="AI Agent Frameworks Comparison 2026",
        goal="Research and compare LangGraph, CrewAI, AutoGen, and OpenAI Agents SDK",
        message="Comparing frameworks across architecture, tool use, and production readiness.",
        steps=[
            Step(
                id="1",
                description="Research LangGraph, CrewAI, AutoGen, and OpenAI Agents SDK architecture and capabilities.",
                action_verb="Research",
                target_object="AI agent framework architectures",
                expected_output="Collected source notes and comparison criteria.",
                tool_hint="browser, web_search",
            ),
            Step(
                id="2",
                description="Analyze findings and produce a structured comparison with decision-ready takeaways.",
                action_verb="Analyze",
                target_object="framework comparison data",
                expected_output="Draft comparison sections and supporting tables.",
                tool_hint="file, code_executor",
            ),
            Step(
                id="3",
                description="Validate the comparison, finalize the report, and deliver the output.",
                action_verb="Deliver",
                target_object="final comparison report",
                expected_output="Final markdown report with verified claims.",
                tool_hint="file",
            ),
        ],
    )


@pytest.fixture
def minimal_step_plan() -> Plan:
    """Plan with a step that has no expected_output or tool_hint."""
    return Plan(
        title="Simple Task",
        goal="Do a simple thing",
        steps=[
            Step(
                id="1",
                description="Just do the thing.",
            ),
        ],
    )


# ── _format_plan_as_markdown ──────────────────────────────────────


class TestFormatPlanAsMarkdown:
    """Tests for the plan markdown formatter."""

    def test_includes_title_as_h1(self, three_step_plan: Plan):
        md = _format_plan_as_markdown(three_step_plan, complexity="complex", planner_kind="Standard")
        assert md.startswith("# AI Agent Frameworks Comparison 2026")

    def test_includes_goal_blockquote(self, three_step_plan: Plan):
        md = _format_plan_as_markdown(three_step_plan, complexity="complex", planner_kind="Standard")
        assert "> Research and compare LangGraph" in md

    def test_includes_metadata_table(self, three_step_plan: Plan):
        md = _format_plan_as_markdown(three_step_plan, complexity="complex", planner_kind="Standard")
        assert "| Complexity | Complex |" in md
        assert "| Steps | 3 |" in md
        assert "| Planner | Standard |" in md

    def test_does_not_include_time_estimates(self, three_step_plan: Plan):
        md = _format_plan_as_markdown(three_step_plan, complexity="complex", planner_kind="Standard")
        lower = md.lower()
        assert "est. time" not in lower
        assert "estimated" not in lower
        assert "minutes" not in lower

    def test_step_sections_use_action_verb(self, three_step_plan: Plan):
        md = _format_plan_as_markdown(three_step_plan, complexity="complex", planner_kind="Standard")
        assert "## Step 1 — Research" in md
        assert "## Step 2 — Analyze" in md
        assert "## Step 3 — Deliver" in md

    def test_step_includes_description(self, three_step_plan: Plan):
        md = _format_plan_as_markdown(three_step_plan, complexity="complex", planner_kind="Standard")
        assert "Research LangGraph, CrewAI" in md

    def test_step_includes_expected_output(self, three_step_plan: Plan):
        md = _format_plan_as_markdown(three_step_plan, complexity="complex", planner_kind="Standard")
        assert "Expected output:" in md
        assert "Collected source notes and comparison criteria." in md

    def test_step_includes_tool_hint(self, three_step_plan: Plan):
        md = _format_plan_as_markdown(three_step_plan, complexity="complex", planner_kind="Standard")
        assert "> Tool hint: browser, web_search" in md

    def test_omits_expected_output_when_missing(self, minimal_step_plan: Plan):
        md = _format_plan_as_markdown(minimal_step_plan, complexity="simple", planner_kind="Standard")
        assert "Expected output" not in md

    def test_omits_tool_hint_when_missing(self, minimal_step_plan: Plan):
        md = _format_plan_as_markdown(minimal_step_plan, complexity="simple", planner_kind="Standard")
        assert "Tool hint" not in md

    def test_step_heading_falls_back_to_step_n(self, minimal_step_plan: Plan):
        md = _format_plan_as_markdown(minimal_step_plan, complexity="simple", planner_kind="Standard")
        assert "## Step 1" in md

    def test_includes_message_paragraph(self, three_step_plan: Plan):
        md = _format_plan_as_markdown(three_step_plan, complexity="complex", planner_kind="Standard")
        assert "Comparing frameworks across architecture" in md

    def test_planner_kind_variants(self, three_step_plan: Plan):
        for kind in ("Draft", "Fallback"):
            md = _format_plan_as_markdown(three_step_plan, complexity="medium", planner_kind=kind)
            assert f"| Planner | {kind} |" in md


# ── _iter_plan_markdown_chunks ────────────────────────────────────


class TestIterPlanMarkdownChunks:
    """Tests for the synchronous chunker."""

    def test_reconstructs_original_text(self):
        text = "A" * 500
        chunks = list(_iter_plan_markdown_chunks(text, chunk_size=180))
        assert "".join(chunks) == text

    def test_chunk_sizes_within_bounds(self):
        # Multi-line text (realistic markdown) — each line is short enough
        text = "\n".join(f"Line {i}: some content here" for i in range(40))
        chunks = list(_iter_plan_markdown_chunks(text, chunk_size=180))
        for chunk in chunks:
            assert len(chunk) <= 300  # generous upper bound for line-boundary splits

    def test_at_least_one_chunk(self):
        chunks = list(_iter_plan_markdown_chunks("short", chunk_size=180))
        assert len(chunks) >= 1

    def test_empty_text_yields_one_chunk(self):
        chunks = list(_iter_plan_markdown_chunks("", chunk_size=180))
        assert chunks == [""]


# ── create_plan() planning stream integration ────────────────────


class TestCreatePlanStreamIntegration:
    """Tests that create_plan() emits planning StreamEvents before PlanEvent."""

    @pytest.fixture
    def planner(self):
        """Create a PlannerAgent with mocked dependencies."""
        llm = MagicMock()
        llm.ask_structured = AsyncMock()
        llm.ask_stream = AsyncMock(return_value=AsyncMock(__aiter__=lambda s: s, __anext__=AsyncMock(side_effect=StopAsyncIteration)))
        repo = MagicMock()
        repo.get_memory = MagicMock(return_value=MagicMock(get_messages=MagicMock(return_value=[])))
        json_parser = MagicMock()
        agent = PlannerAgent(
            agent_id="test-planner",
            agent_repository=repo,
            llm=llm,
            tools=[],
            json_parser=json_parser,
        )
        # Provide a mock memory object so _ask_structured_tiered can access get_messages()
        agent.memory = MagicMock()
        agent.memory.get_messages = MagicMock(return_value=[])
        return agent

    @pytest.fixture
    def mock_plan_response(self, three_step_plan: Plan):
        """Build a mock structured plan response matching the three_step_plan."""
        from app.domain.models.agent_response import PlanResponse

        mock_steps = []
        for step in three_step_plan.steps:
            s = MagicMock()
            s.description = step.description
            s.action_verb = step.action_verb
            s.target_object = step.target_object
            s.expected_output = step.expected_output
            s.tool_hint = step.tool_hint
            s.phase = None
            s.step_type = None
            mock_steps.append(s)

        response = MagicMock(spec=PlanResponse)
        response.goal = three_step_plan.goal
        response.title = three_step_plan.title
        response.language = "en"
        response.message = three_step_plan.message
        response.steps = mock_steps
        return response

    @pytest.mark.asyncio
    async def test_success_path_emits_planning_stream_events(self, planner, mock_plan_response):
        """create_plan() should emit StreamEvent(phase='planning') chunks before PlanEvent."""
        from app.domain.models.message import Message

        planner._ask_structured_tiered = AsyncMock(return_value=mock_plan_response)
        planner._add_to_memory = AsyncMock()
        planner._ensure_within_token_limit = AsyncMock()

        msg = Message(message="Compare AI agent frameworks", attachments=[])
        events = [event async for event in planner.create_plan(msg, draft=True)]

        planning_streams = [e for e in events if isinstance(e, StreamEvent) and e.phase == "planning"]
        plan_events = [e for e in events if isinstance(e, PlanEvent)]

        assert len(planning_streams) >= 2, "Should have at least one content chunk + one final"
        assert len(plan_events) == 1

        # Final planning stream should be is_final=True
        final_streams = [e for e in planning_streams if e.is_final]
        assert len(final_streams) == 1
        assert final_streams[0].content == ""

        # Planning streams should come before PlanEvent
        last_planning_idx = max(events.index(e) for e in planning_streams)
        plan_event_idx = events.index(plan_events[0])
        assert last_planning_idx < plan_event_idx

    @pytest.mark.asyncio
    async def test_success_path_planning_content_contains_title(self, planner, mock_plan_response):
        """Planning stream content should contain the plan title."""
        from app.domain.models.message import Message

        planner._ask_structured_tiered = AsyncMock(return_value=mock_plan_response)
        planner._add_to_memory = AsyncMock()
        planner._ensure_within_token_limit = AsyncMock()

        msg = Message(message="Compare AI agent frameworks", attachments=[])
        events = [event async for event in planner.create_plan(msg, draft=True)]

        planning_content = "".join(
            e.content for e in events if isinstance(e, StreamEvent) and e.phase == "planning"
        )
        assert "AI Agent Frameworks Comparison 2026" in planning_content

    @pytest.mark.asyncio
    async def test_fallback_path_emits_planning_stream_events(self, planner):
        """Fallback plan path should also emit planning StreamEvents."""
        from app.domain.models.message import Message

        # Make structured output fail to trigger fallback
        planner._ask_structured_tiered = AsyncMock(side_effect=RuntimeError("LLM failed"))
        planner._add_to_memory = AsyncMock()
        planner._ensure_within_token_limit = AsyncMock()

        msg = Message(message="Compare AI agent frameworks", attachments=[])
        events = [event async for event in planner.create_plan(msg, draft=True)]

        planning_streams = [e for e in events if isinstance(e, StreamEvent) and e.phase == "planning"]
        plan_events = [e for e in events if isinstance(e, PlanEvent)]

        assert len(planning_streams) >= 2, "Fallback should also stream plan markdown"
        assert len(plan_events) == 1
        assert plan_events[0].status == PlanStatus.CREATED

        # Final stream should be is_final=True
        final_streams = [e for e in planning_streams if e.is_final]
        assert len(final_streams) == 1

    @pytest.mark.asyncio
    async def test_fallback_planning_content_contains_fallback_title(self, planner):
        """Fallback planning stream should contain the fallback plan title."""
        from app.domain.models.message import Message

        planner._ask_structured_tiered = AsyncMock(side_effect=RuntimeError("LLM failed"))
        planner._add_to_memory = AsyncMock()
        planner._ensure_within_token_limit = AsyncMock()

        msg = Message(message="Compare AI agent frameworks", attachments=[])
        events = [event async for event in planner.create_plan(msg, draft=True)]

        planning_content = "".join(
            e.content for e in events if isinstance(e, StreamEvent) and e.phase == "planning"
        )
        assert "Fallback Plan" in planning_content
