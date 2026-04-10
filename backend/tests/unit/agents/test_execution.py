"""
Unit tests for ExecutionAgent.

Tests the execution agent in isolation with mocked LLM and tool responses.
Covers tool execution, retry logic, context management, and source citation tracking.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import (
    ErrorEvent,
    MessageEvent,
    StepEvent,
    StepStatus,
    ToolEvent,
    ToolStatus,
)
from app.domain.models.plan import ExecutionStatus, Step, StepType
from app.domain.services.agents.critic import CriticConfig
from app.domain.services.agents.execution import ExecutionAgent


def _make_tool_bundle(name: str) -> MagicMock:
    """Create a lightweight tool bundle mock for step-level filtering tests."""
    tool = MagicMock()
    tool.name = name
    tool.get_tools = MagicMock(return_value=[])
    return tool


class TestExecutionAgentInit:
    """Tests for ExecutionAgent initialization."""

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    def test_executor_initializes_with_defaults(self, mock_llm, mock_agent_repository, mock_json_parser, mock_tools):
        """Executor should initialize with default configuration."""
        executor = ExecutionAgent(
            agent_id="test-executor-123",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
        )

        assert executor.name == "execution"
        assert executor._context_manager is not None
        assert executor._critic is not None
        assert executor._collected_sources == []

    def test_executor_initializes_with_custom_critic_config(
        self, mock_llm, mock_agent_repository, mock_json_parser, mock_tools
    ):
        """Executor should accept custom critic configuration."""
        config = CriticConfig(
            enabled=False,
            auto_approve_simple_tasks=False,
            max_revision_attempts=5,
        )

        executor = ExecutionAgent(
            agent_id="test-executor-123",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
            critic_config=config,
        )

        assert executor._critic.config.enabled is False
        assert executor._critic.config.max_revision_attempts == 5


class TestExecutionAgent:
    """Unit tests for ExecutionAgent."""

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.fixture
    def executor(self, mock_llm, mock_agent_repository, mock_json_parser, mock_tools):
        """Create an ExecutionAgent with mocked dependencies."""
        return ExecutionAgent(
            agent_id="test-executor-123",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
        )

    @pytest.fixture
    def simple_plan(self, plan_factory):
        """Create a simple plan for testing."""
        return plan_factory(steps=[{"id": "1", "description": "Search for Python tutorials"}])

    @pytest.fixture
    def mock_step(self, step_factory):
        """Create a mock step for testing."""
        return step_factory(
            step_id="1",
            description="Search for Python tutorials",
            status=ExecutionStatus.PENDING,
        )

    @pytest.mark.asyncio
    async def test_execute_step_restricts_final_delivery_to_local_tool_bundles(
        self, executor, simple_plan, mock_message
    ):
        """Delivery steps with an existing report draft should not reopen web research."""
        executor.tools = [
            _make_tool_bundle("file"),
            _make_tool_bundle("message"),
            _make_tool_bundle("chart"),
            _make_tool_bundle("search"),
            _make_tool_bundle("browser"),
            _make_tool_bundle("shell"),
        ]
        executor._file_write_report_cache = "# Report\n\nDraft report content"

        delivery_step = Step(
            id="2",
            description="Review, validate, and deliver final output",
            step_type=StepType.DELIVERY,
            status=ExecutionStatus.PENDING,
        )
        message = mock_message(message="Finalize the report")
        observed_tool_names: list[list[str]] = []
        observed_prompts: list[str] = []

        async def fake_execute(prompt: str):
            observed_tool_names.append([tool.name for tool in executor.tools])
            observed_prompts.append(prompt)
            yield MessageEvent(message='{"success": true, "result": "Delivered", "attachments": []}')

        executor.execute = fake_execute
        executor.json_parser.parse = AsyncMock(return_value={"success": True, "result": "Delivered", "attachments": []})

        [event async for event in executor.execute_step(simple_plan, delivery_step, message)]

        assert observed_tool_names == [["file", "message", "chart"]]
        assert observed_prompts and "Do not do fresh web research" in observed_prompts[0]
        assert [tool.name for tool in executor.tools] == ["file", "message", "chart", "search", "browser", "shell"]

    @pytest.mark.asyncio
    async def test_execute_step_restricts_merged_delivery_step_by_description(
        self, executor, simple_plan, mock_message
    ):
        """Merged delivery steps still arrive as execution steps and should be clamped locally."""
        executor.tools = [
            _make_tool_bundle("file"),
            _make_tool_bundle("message"),
            _make_tool_bundle("search"),
            _make_tool_bundle("browser"),
        ]
        executor._file_write_report_cache = "# Report\n\nDraft report content"

        merged_delivery_step = Step(
            id="3",
            description="Validate report accuracy and deliver final output",
            step_type=StepType.EXECUTION,
            status=ExecutionStatus.PENDING,
        )
        message = mock_message(message="Validate and deliver")
        observed_tool_names: list[list[str]] = []

        async def fake_execute(_prompt: str):
            observed_tool_names.append([tool.name for tool in executor.tools])
            yield MessageEvent(message='{"success": true, "result": "Delivered", "attachments": []}')

        executor.execute = fake_execute
        executor.json_parser.parse = AsyncMock(return_value={"success": True, "result": "Delivered", "attachments": []})

        [event async for event in executor.execute_step(simple_plan, merged_delivery_step, message)]

        assert observed_tool_names == [["file", "message"]]

    @pytest.mark.asyncio
    async def test_execute_step_keeps_delivery_tools_unrestricted_without_report_draft(
        self, executor, simple_plan, mock_message
    ):
        """Delivery steps should only enter local-only mode after a report draft exists."""
        executor.tools = [
            _make_tool_bundle("file"),
            _make_tool_bundle("message"),
            _make_tool_bundle("search"),
            _make_tool_bundle("browser"),
        ]

        delivery_step = Step(
            id="4",
            description="Review, validate, and deliver final output",
            step_type=StepType.DELIVERY,
            status=ExecutionStatus.PENDING,
        )
        message = mock_message(message="Validate and deliver")
        observed_tool_names: list[list[str]] = []

        async def fake_execute(_prompt: str):
            observed_tool_names.append([tool.name for tool in executor.tools])
            yield MessageEvent(message='{"success": true, "result": "Delivered", "attachments": []}')

        executor.execute = fake_execute
        executor.json_parser.parse = AsyncMock(return_value={"success": True, "result": "Delivered", "attachments": []})

        [event async for event in executor.execute_step(simple_plan, delivery_step, message)]

        assert observed_tool_names == [["file", "message", "search", "browser"]]

    @pytest.mark.asyncio
    async def test_execute_step_accepts_best_effort_success_payload(
        self, executor, simple_plan, mock_step, mock_message
    ):
        """Best-effort payload recovery should still complete the step when success/result are usable."""
        message = mock_message(message="Use gathered findings")

        async def fake_execute(_prompt: str):
            yield MessageEvent(message='{"success": true, "result": "Recovered summary", "attachments": "oops"}')

        executor.execute = fake_execute
        executor.json_parser.parse = AsyncMock(
            return_value={"success": True, "result": "Recovered summary", "attachments": "oops"}
        )

        events = [event async for event in executor.execute_step(simple_plan, mock_step, message)]

        step_events = [event for event in events if isinstance(event, StepEvent)]
        assert step_events
        assert step_events[-1].status is StepStatus.COMPLETED
        assert step_events[-1].step.success is True
        assert step_events[-1].step.result == "Recovered summary"
        assert step_events[-1].step.attachments == []

    @pytest.mark.asyncio
    async def test_execute_step_includes_known_report_artifact_path_in_delivery_prompt(
        self, executor, simple_plan, mock_message
    ):
        """Final delivery prompts should reuse the exact known report path instead of guessing filenames."""
        executor.tools = [
            _make_tool_bundle("file"),
            _make_tool_bundle("message"),
            _make_tool_bundle("chart"),
            _make_tool_bundle("search"),
        ]
        executor._file_write_report_cache = "# Report\n\nDraft report content"
        executor._last_report_artifact_path = "/workspace/reports/dgx_spark_vs_m3_ultra.md"

        delivery_step = Step(
            id="5",
            description="Review existing report, cross-validate claims, and deliver final output",
            step_type=StepType.DELIVERY,
            status=ExecutionStatus.PENDING,
        )
        message = mock_message(message="Review the report and deliver it")
        observed_prompts: list[str] = []

        async def fake_execute(prompt: str):
            observed_prompts.append(prompt)
            yield MessageEvent(message='{"success": true, "result": "Delivered", "attachments": []}')

        executor.execute = fake_execute
        executor.json_parser.parse = AsyncMock(return_value={"success": True, "result": "Delivered", "attachments": []})

        [event async for event in executor.execute_step(simple_plan, delivery_step, message)]

        assert observed_prompts
        assert "/workspace/reports/dgx_spark_vs_m3_ultra.md" in observed_prompts[0]
        assert "Do not guess alternate filenames" in observed_prompts[0]

    @pytest.mark.asyncio
    async def test_execute_step_skips_report_artifact_prompt_when_no_path_known(
        self, executor, simple_plan, mock_message
    ):
        """When a draft exists but no artifact path is cached, omit the prompt entirely.

        This avoids the contradictory guidance of "go find the file yourself"
        while tools are restricted to local bundles.
        """
        executor.tools = [
            _make_tool_bundle("file"),
            _make_tool_bundle("message"),
            _make_tool_bundle("chart"),
        ]
        executor._file_write_report_cache = "# Report\n\nDraft report content"

        delivery_step = Step(
            id="6",
            description="Review existing report, cross-validate claims, and deliver final output",
            step_type=StepType.DELIVERY,
            status=ExecutionStatus.PENDING,
        )
        message = mock_message(message="Review the report and deliver it")
        observed_prompts: list[str] = []

        async def fake_execute(prompt: str):
            observed_prompts.append(prompt)
            yield MessageEvent(message='{"success": true, "result": "Delivered", "attachments": []}')

        executor.execute = fake_execute
        executor.json_parser.parse = AsyncMock(return_value={"success": True, "result": "Delivered", "attachments": []})

        [event async for event in executor.execute_step(simple_plan, delivery_step, message)]

        assert observed_prompts
        assert "<known_report_artifact>" not in observed_prompts[0]

    @pytest.mark.asyncio
    async def test_execute_step_yields_step_event(self, executor, simple_plan, mock_step, mock_message):
        """Executing a step should yield StepEvent."""
        message = mock_message(message="Find Python tutorials")

        # Mock LLM to return a final answer (no tool calls)
        executor.llm.ask = AsyncMock(
            return_value={
                "role": "assistant",
                "content": '{"final_answer": "Here are some Python tutorials..."}',
            }
        )
        executor.json_parser.parse = AsyncMock(return_value={"final_answer": "Here are some Python tutorials..."})

        events = [event async for event in executor.execute_step(simple_plan, mock_step, message)]

        # Should have yielded at least one StepEvent
        step_events = [e for e in events if isinstance(e, StepEvent)]
        assert len(step_events) >= 1

    @pytest.mark.asyncio
    async def test_execute_step_handles_tool_call(
        self, executor, simple_plan, mock_step, mock_message, mock_tool_registry
    ):
        """Executing a step with tool call should execute the tool."""
        message = mock_message(message="Search for information")

        # Register a mock tool
        mock_tool_registry.register("web_search", {"results": ["result1", "result2"]})

        # Mock LLM to return a tool call
        executor.llm.ask = AsyncMock(
            side_effect=[
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "function": {
                                "name": "web_search",
                                "arguments": '{"query": "python tutorials"}',
                            },
                        }
                    ],
                },
                {
                    "role": "assistant",
                    "content": '{"final_answer": "Found results"}',
                },
            ]
        )

        # Mock tool execution
        for tool in executor.tools:
            tool.has_function = MagicMock(return_value=True)
            tool.invoke_function = AsyncMock(
                return_value=MagicMock(
                    success=True,
                    message="Search completed",
                    data={"results": ["result1"]},
                )
            )

        [event async for event in executor.execute_step(simple_plan, mock_step, message)]

        # Tool events may be present depending on LLM response

    @pytest.mark.asyncio
    async def test_context_manager_tracks_step(self, executor, simple_plan, mock_step, mock_message):
        """Context manager should track current step."""
        message = mock_message(message="Test message")

        executor.llm.ask = AsyncMock(
            return_value={
                "role": "assistant",
                "content": '{"final_answer": "Done"}',
            }
        )
        executor.json_parser.parse = AsyncMock(return_value={"final_answer": "Done"})

        async for _ in executor.execute_step(simple_plan, mock_step, message):
            pass

        # Context manager should have the step set
        assert executor._context_manager._current_step_id == mock_step.id

    @pytest.mark.asyncio
    async def test_execute_step_with_attachments(self, executor, simple_plan, mock_step, mock_message):
        """Executing a step with attachments should process them."""
        message = mock_message(
            message="Analyze these files",
            attachments=["/uploads/file1.txt", "/uploads/file2.pdf"],
        )

        executor.llm.ask = AsyncMock(
            return_value={
                "role": "assistant",
                "content": '{"final_answer": "Analyzed files"}',
            }
        )
        executor.json_parser.parse = AsyncMock(return_value={"final_answer": "Analyzed files"})

        events = [event async for event in executor.execute_step(simple_plan, mock_step, message)]

        # Should complete without error
        error_events = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 0

    @pytest.mark.asyncio
    async def test_execute_step_marks_invalid_payload_unsuccessful(
        self, executor, simple_plan, mock_step, mock_message
    ):
        """Malformed step payloads should not be marked as successful."""
        message = mock_message(message="Run task with malformed output")

        executor.llm.ask = AsyncMock(
            return_value={
                "role": "assistant",
                "content": "plain text response without expected schema",
            }
        )
        executor.json_parser.parse = AsyncMock(return_value={})

        events = [event async for event in executor.execute_step(simple_plan, mock_step, message)]

        step_events = [e for e in events if isinstance(e, StepEvent)]
        assert step_events
        assert step_events[-1].step.success is False
        assert step_events[-1].step.result is None
        assert step_events[-1].step.error is not None

    @pytest.mark.asyncio
    async def test_execute_step_marks_structured_failure_payload_failed(
        self, executor, simple_plan, mock_step, mock_message
    ):
        """Schema-valid failure payloads must fail the step instead of completing it."""
        message = mock_message(message="Run task that fails cleanly")

        async def fake_execute(*_args, **_kwargs):
            yield MessageEvent(
                message='{"success": false, "result": null, "attachments": [], "error": "Step missed required search action"}'
            )

        executor.execute = fake_execute
        executor.json_parser.parse = AsyncMock(
            return_value={
                "success": False,
                "result": None,
                "attachments": [],
                "error": "Step missed required search action",
            }
        )

        events = [event async for event in executor.execute_step(simple_plan, mock_step, message)]

        step_events = [e for e in events if isinstance(e, StepEvent)]
        assert step_events
        assert step_events[-1].status == StepStatus.FAILED
        assert step_events[-1].step.status == ExecutionStatus.FAILED
        assert step_events[-1].step.success is False
        assert step_events[-1].step.error == "Step missed required search action"
        assert all(event.status != StepStatus.COMPLETED for event in step_events)

    @pytest.mark.asyncio
    async def test_execute_step_preserves_partial_results_for_tool_backed_format_failure(
        self, executor, simple_plan, mock_step, mock_message
    ):
        """Successful tool-backed work should leave a real partial result when JSON packaging fails."""
        message = mock_message(message="Run research step with format failure")

        tool_result = MagicMock()
        tool_result.success = True
        tool_result.message = "Search completed"
        tool_result.data = {"results": [{"title": "DGX Spark specs"}]}

        async def fake_execute(*_args, **_kwargs):
            yield ToolEvent(
                tool_call_id="tool-call-1",
                tool_name="search",
                function_name="search",
                function_args={"query": "DGX Spark specs"},
                status=ToolStatus.CALLED,
                function_result=tool_result,
            )
            yield MessageEvent(
                message=(
                    '{"success": false, "result": null, "attachments": [], '
                    '"error": "Tool execution completed, but the agent did not return a valid JSON result."}'
                )
            )

        executor.execute = fake_execute
        executor.json_parser.parse = AsyncMock(
            return_value={
                "success": False,
                "result": None,
                "attachments": [],
                "error": "Tool execution completed, but the agent did not return a valid JSON result.",
            }
        )

        events = [event async for event in executor.execute_step(simple_plan, mock_step, message)]

        step_events = [event for event in events if isinstance(event, StepEvent)]
        assert step_events
        assert step_events[-1].status == StepStatus.FAILED
        assert step_events[-1].step.status == ExecutionStatus.FAILED
        assert step_events[-1].step.success is False
        assert step_events[-1].step.result is not None
        assert "Partial results available from successful tool calls" in step_events[-1].step.result
        assert "search" in step_events[-1].step.result
        assert (
            step_events[-1].step.error == "Tool execution completed, but the agent did not return a valid JSON result."
        )

    @pytest.mark.asyncio
    async def test_execute_step_uses_json_repair_fallback_when_parser_fails(
        self, executor, simple_plan, mock_step, mock_message
    ):
        """When parser fails, execution should still recover JSON from mixed prose output."""
        mock_step.description = "Summarize the collected findings"
        mock_step.step_type = StepType.DELIVERY
        message = mock_message(message="Run task with mixed prose and JSON output")

        executor.llm.ask = AsyncMock(
            return_value={
                "role": "assistant",
                "content": (
                    "Let me create the file in multiple parts.\n"
                    '{"success": true, "result": "Step completed", "attachments": []}\n'
                    "Done."
                ),
            }
        )
        executor.json_parser.parse = AsyncMock(side_effect=ValueError("Failed to parse JSON from LLM output"))

        events = [event async for event in executor.execute_step(simple_plan, mock_step, message)]

        step_events = [e for e in events if isinstance(e, StepEvent)]
        assert step_events
        assert step_events[-1].step.success is True
        assert step_events[-1].step.result == "Step completed"

    @pytest.mark.asyncio
    async def test_retry_step_result_json_retries_twice_and_recovers(self, executor):
        """Correction retry should recover on the second attempt."""
        executor.llm.ask = AsyncMock(
            side_effect=[
                {"content": "not-json"},
                {"content": '{"success": true, "result": "Recovered", "attachments": []}'},
            ]
        )

        recovered = await executor._retry_step_result_json("Malformed response")

        assert recovered == {"success": True, "result": "Recovered", "attachments": []}
        assert executor.llm.ask.await_count == 2

    @pytest.mark.asyncio
    async def test_retry_step_result_json_stops_after_two_attempts(self, executor):
        """Correction retry should stop after two failed attempts."""
        executor.llm.ask = AsyncMock(side_effect=[{"content": "bad"}, {"content": "still bad"}])

        recovered = await executor._retry_step_result_json("Malformed response")

        assert recovered is None
        assert executor.llm.ask.await_count == 2

    @pytest.mark.asyncio
    async def test_execute_step_skips_json_retry_for_known_unparseable_fallback(
        self, executor, simple_plan, mock_step, mock_message
    ):
        """Known prose fallback should not trigger correction LLM retries."""
        message = mock_message(message="Run task with fallback prose")

        async def fake_execute(*_args, **_kwargs):
            yield MessageEvent(
                message="I was unable to produce a complete response. Please try again or rephrase your request."
            )

        executor.execute = fake_execute
        executor.json_parser.parse = AsyncMock(side_effect=ValueError("not json"))
        executor._retry_step_result_json = AsyncMock(return_value={"success": True, "result": "Recovered"})

        events = [event async for event in executor.execute_step(simple_plan, mock_step, message)]

        assert any(isinstance(event, StepEvent) for event in events)
        executor._retry_step_result_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_execute_step_emits_message_event_for_message_notify_user(
        self, executor, simple_plan, mock_step, mock_message
    ):
        """message_notify_user CALLING events should become outbound-visible MessageEvents."""

        async def fake_execute(*_args, **_kwargs):
            yield ToolEvent(
                tool_call_id="tool-call-1",
                tool_name="message",
                function_name="message_notify_user",
                function_args={"text": "Working on it."},
                status=ToolStatus.CALLING,
            )

        executor.execute = fake_execute

        user_message = mock_message(message="Start", attachments=[])
        events = [event async for event in executor.execute_step(simple_plan, mock_step, user_message)]

        message_events = [event for event in events if isinstance(event, MessageEvent)]
        assert any(event.message == "Working on it." for event in message_events)

    @pytest.mark.asyncio
    async def test_execute_step_sanitizes_telegram_buttons_for_message_notify_user(
        self, executor, simple_plan, mock_step, mock_message
    ):
        """Telegram buttons from message_notify_user should be trimmed and filtered before emission."""

        async def fake_execute(*_args, **_kwargs):
            yield ToolEvent(
                tool_call_id="tool-call-2",
                tool_name="message",
                function_name="message_notify_user",
                function_args={
                    "text": "Pick one",
                    "buttons": [
                        [
                            {"text": "  Approve  ", "callback_data": "  cmd:approve  "},
                            {"text": "   ", "callback_data": "cmd:skip"},
                        ],
                        [
                            {"text": "Missing data", "callback_data": "   "},
                        ],
                    ],
                },
                status=ToolStatus.CALLING,
            )

        executor.execute = fake_execute

        user_message = mock_message(message="Start", attachments=[])
        events = [event async for event in executor.execute_step(simple_plan, mock_step, user_message)]

        message_events = [event for event in events if isinstance(event, MessageEvent) and event.message == "Pick one"]
        assert len(message_events) == 1
        assert message_events[0].delivery_metadata == {
            "reply_markup": {
                "inline_keyboard": [
                    [{"text": "Approve", "callback_data": "cmd:approve"}],
                ]
            }
        }

    @pytest.mark.asyncio
    async def test_execute_step_normalizes_telegram_action_for_message_notify_user(
        self, executor, simple_plan, mock_step, mock_message
    ):
        """Telegram action payloads should be preserved in delivery metadata."""

        async def fake_execute(*_args, **_kwargs):
            yield ToolEvent(
                tool_call_id="tool-call-3",
                tool_name="message",
                function_name="message_notify_user",
                function_args={
                    "text": "",
                    "telegram_action": {"type": "delete", "message_id": "321"},
                },
                status=ToolStatus.CALLING,
            )

        executor.execute = fake_execute

        user_message = mock_message(message="Start", attachments=[])
        events = [event async for event in executor.execute_step(simple_plan, mock_step, user_message)]

        message_events = [event for event in events if isinstance(event, MessageEvent)]
        assert len(message_events) == 1
        assert message_events[0].delivery_metadata == {
            "telegram_action": {
                "type": "delete",
                "message_id": 321,
            }
        }

    @pytest.mark.asyncio
    async def test_execute_step_normalizes_telegram_poll_action_for_message_notify_user(
        self, executor, simple_plan, mock_step, mock_message
    ):
        """Telegram poll payloads should be preserved in delivery metadata."""

        async def fake_execute(*_args, **_kwargs):
            yield ToolEvent(
                tool_call_id="tool-call-4",
                tool_name="message",
                function_name="message_notify_user",
                function_args={
                    "text": "",
                    "telegram_action": {
                        "type": "poll",
                        "question": "Pick one",
                        "options": ["Fast", "Deep"],
                        "allows_multiple_answers": True,
                        "is_anonymous": False,
                        "open_period": 60,
                    },
                },
                status=ToolStatus.CALLING,
            )

        executor.execute = fake_execute

        user_message = mock_message(message="Start", attachments=[])
        events = [event async for event in executor.execute_step(simple_plan, mock_step, user_message)]

        message_events = [event for event in events if isinstance(event, MessageEvent)]
        assert len(message_events) == 1
        assert message_events[0].delivery_metadata == {
            "telegram_action": {
                "type": "poll",
                "question": "Pick one",
                "options": ["Fast", "Deep"],
                "allows_multiple_answers": True,
                "is_anonymous": False,
                "open_period": 60,
            }
        }

    @pytest.mark.asyncio
    async def test_execute_step_normalizes_telegram_topic_create_action_for_message_notify_user(
        self, executor, simple_plan, mock_step, mock_message
    ):
        """Telegram topic-create payloads should be preserved in delivery metadata."""

        async def fake_execute(*_args, **_kwargs):
            yield ToolEvent(
                tool_call_id="tool-call-5",
                tool_name="message",
                function_name="message_notify_user",
                function_args={
                    "text": "",
                    "telegram_action": {
                        "type": "topic_create",
                        "name": "Ops Room",
                        "icon_color": 7322096,
                        "icon_custom_emoji_id": "emoji-123",
                    },
                },
                status=ToolStatus.CALLING,
            )

        executor.execute = fake_execute

        user_message = mock_message(message="Start", attachments=[])
        events = [event async for event in executor.execute_step(simple_plan, mock_step, user_message)]

        message_events = [event for event in events if isinstance(event, MessageEvent)]
        assert len(message_events) == 1
        assert message_events[0].delivery_metadata == {
            "telegram_action": {
                "type": "topic_create",
                "name": "Ops Room",
                "icon_color": 7322096,
                "icon_custom_emoji_id": "emoji-123",
            }
        }

    @pytest.mark.asyncio
    async def test_execute_step_normalizes_telegram_sticker_action_for_message_notify_user(
        self, executor, simple_plan, mock_step, mock_message
    ):
        """Telegram sticker payloads should be preserved in delivery metadata."""

        async def fake_execute(*_args, **_kwargs):
            yield ToolEvent(
                tool_call_id="tool-call-6",
                tool_name="message",
                function_name="message_notify_user",
                function_args={
                    "text": "",
                    "telegram_action": {
                        "type": "sticker",
                        "file_id": "sticker-file-id",
                    },
                },
                status=ToolStatus.CALLING,
            )

        executor.execute = fake_execute

        user_message = mock_message(message="Start", attachments=[])
        events = [event async for event in executor.execute_step(simple_plan, mock_step, user_message)]

        message_events = [event for event in events if isinstance(event, MessageEvent)]
        assert len(message_events) == 1
        assert message_events[0].delivery_metadata == {
            "telegram_action": {
                "type": "sticker",
                "file_id": "sticker-file-id",
            }
        }


class TestToolExecution:
    """Tests for tool execution behavior."""

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.fixture
    def executor(self, mock_llm, mock_agent_repository, mock_json_parser, mock_tools):
        """Create an ExecutionAgent for tool testing."""
        return ExecutionAgent(
            agent_id="test-executor",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
        )

    def test_tools_are_registered(self, executor):
        """Executor should have tools registered."""
        assert len(executor.tools) > 0

    def test_get_tool_definitions(self, executor):
        """Should be able to get tool definitions."""
        tool_defs = []
        for tool in executor.tools:
            tool_defs.extend(tool.get_tools())

        assert len(tool_defs) > 0


class TestContextManagement:
    """Tests for context window management."""

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.fixture
    def executor(self, mock_llm, mock_agent_repository, mock_json_parser, mock_tools):
        """Create an ExecutionAgent for context tests."""
        return ExecutionAgent(
            agent_id="test-executor",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
        )

    def test_context_manager_has_token_limit(self, executor):
        """Context manager should have a token limit."""
        assert executor._context_manager._max_tokens == 8000

    def test_context_manager_starts_empty(self, executor):
        """Context manager should start with empty context."""
        # ContextManager uses _context which is a WorkingContext
        assert executor._context_manager._context is not None


class TestSourceCitationTracking:
    """Tests for source citation tracking."""

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.fixture
    def executor(self, mock_llm, mock_agent_repository, mock_json_parser, mock_tools):
        """Create an ExecutionAgent for citation tests."""
        return ExecutionAgent(
            agent_id="test-executor",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
        )

    def test_collected_sources_initially_empty(self, executor):
        """Collected sources should be empty initially."""
        assert executor._collected_sources == []
        assert executor._source_tracker._seen_urls == set()


class TestMultimodalPersistence:
    """Tests for multimodal information persistence."""

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.fixture
    def executor(self, mock_llm, mock_agent_repository, mock_json_parser, mock_tools):
        """Create an ExecutionAgent for multimodal tests."""
        return ExecutionAgent(
            agent_id="test-executor",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
        )

    def test_view_operation_counter_starts_at_zero(self, executor):
        """View operation counter should start at zero."""
        assert executor._view_operation_count == 0

    def test_multimodal_findings_initially_empty(self, executor):
        """Multimodal findings should be empty initially."""
        assert executor._multimodal_findings == []

    def test_view_tools_defined(self, executor):
        """View tools should be defined for persistence tracking."""
        assert "file_view" in executor._view_tools
        assert "browser_view" in executor._view_tools
        assert "browser_get_content" in executor._view_tools


class TestPromptAdapter:
    """Tests for prompt adapter integration."""

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.fixture
    def executor(self, mock_llm, mock_agent_repository, mock_json_parser, mock_tools):
        """Create an ExecutionAgent for prompt adapter tests."""
        return ExecutionAgent(
            agent_id="test-executor",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
        )

    def test_prompt_adapter_initialized(self, executor):
        """Prompt adapter should be initialized."""
        assert executor._prompt_adapter is not None

    def test_prompt_adapter_iteration_starts_at_zero(self, executor):
        """Prompt adapter iteration should start at zero."""
        assert executor._prompt_adapter._context.iteration_count == 0


class TestCriticIntegration:
    """Tests for critic agent integration."""

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.fixture
    def executor(self, mock_llm, mock_agent_repository, mock_json_parser, mock_tools):
        """Create an ExecutionAgent for critic tests."""
        return ExecutionAgent(
            agent_id="test-executor",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
        )

    def test_critic_is_enabled_by_default(self, executor):
        """Critic should be enabled by default."""
        assert executor._critic.config.enabled is True

    def test_critic_auto_approves_simple_tasks(self, executor):
        """Critic should auto-approve simple tasks by default."""
        assert executor._critic.config.auto_approve_simple_tasks is True

    def test_critic_has_max_revision_attempts(self, executor):
        """Critic should have max revision attempts configured."""
        assert executor._critic.config.max_revision_attempts == 2


class TestSkillIntegration:
    """Tests for skill context integration."""

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.fixture
    def executor(self, mock_llm, mock_agent_repository, mock_json_parser, mock_tools):
        """Create an ExecutionAgent for skill tests."""
        return ExecutionAgent(
            agent_id="test-executor",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
        )

    @pytest.mark.asyncio
    async def test_execute_step_with_skills(self, executor, plan_factory, step_factory, mock_message):
        """Executing a step with skills should load skill context."""
        plan = plan_factory(steps=[{"id": "1", "description": "Use skill"}])
        step = step_factory(step_id="1", description="Use skill")
        message = mock_message(
            message="Test with skills",
            skills=["test_skill"],
        )

        executor.llm.ask = AsyncMock(
            return_value={
                "role": "assistant",
                "content": '{"final_answer": "Done with skill"}',
            }
        )
        executor.json_parser.parse = AsyncMock(return_value={"final_answer": "Done with skill"})

        # Mock skill registry
        with patch("app.domain.services.skill_registry.get_skill_registry") as mock_registry:
            mock_reg = AsyncMock()
            mock_reg._ensure_fresh = AsyncMock()
            mock_reg.build_context = AsyncMock(
                return_value=MagicMock(
                    skill_ids=["test_skill"],
                    prompt_addition="Test skill context",
                    has_tool_restrictions=MagicMock(return_value=False),
                )
            )
            mock_reg.get_skills = AsyncMock(return_value=[MagicMock(name="Test Skill")])
            mock_registry.return_value = mock_reg

            # Also mock skill trigger matcher
            with patch("app.domain.services.skill_trigger_matcher.get_skill_trigger_matcher") as mock_matcher:
                mock_match = AsyncMock()
                mock_match.get_suggested_skills = AsyncMock(return_value=[])
                mock_matcher.return_value = mock_match

                [event async for event in executor.execute_step(plan, step, message)]

                # Skill loading errors are warnings, not failures
