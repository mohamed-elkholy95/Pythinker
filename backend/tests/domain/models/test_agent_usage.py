from datetime import UTC, datetime

from app.domain.models.agent_usage import (
    AgentRun,
    AgentRunStatus,
    AgentStep,
    AgentStepStatus,
    AgentStepType,
    BillingStatus,
)


class TestAgentRun:
    def test_agent_run_defaults_total_fields_to_zero(self) -> None:
        run = AgentRun(
            run_id="run-1",
            user_id="user-1",
            session_id="session-1",
            status=AgentRunStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

        assert run.total_input_tokens == 0
        assert run.total_cached_input_tokens == 0
        assert run.total_output_tokens == 0
        assert run.total_reasoning_tokens == 0
        assert run.total_tokens == 0
        assert run.estimated_cost_usd == 0.0
        assert run.provider_billed_cost_usd is None
        assert run.billing_status == BillingStatus.ESTIMATED
        assert run.step_count == 0
        assert run.tool_call_count == 0
        assert run.mcp_call_count == 0

    def test_agent_run_completed_status_preserves_completed_at(self) -> None:
        completed_at = datetime.now(UTC)

        run = AgentRun(
            run_id="run-2",
            user_id="user-1",
            session_id="session-1",
            status=AgentRunStatus.COMPLETED,
            started_at=datetime.now(UTC),
            completed_at=completed_at,
        )

        assert run.status == AgentRunStatus.COMPLETED
        assert run.completed_at == completed_at

    def test_agent_run_total_tokens_does_not_double_count_cached_input(self) -> None:
        run = AgentRun(
            run_id="run-3",
            user_id="user-1",
            session_id="session-1",
            status=AgentRunStatus.COMPLETED,
            started_at=datetime.now(UTC),
            total_input_tokens=100,
            total_cached_input_tokens=20,
            total_output_tokens=40,
            total_reasoning_tokens=12,
        )

        assert run.total_tokens == 152


class TestAgentStep:
    def test_agent_step_defaults_usage_fields_to_zero(self) -> None:
        step = AgentStep(
            step_id="step-1",
            run_id="run-1",
            session_id="session-1",
            user_id="user-1",
            step_type=AgentStepType.LLM,
            status=AgentStepStatus.COMPLETED,
            started_at=datetime.now(UTC),
        )

        assert step.input_tokens == 0
        assert step.cached_input_tokens == 0
        assert step.output_tokens == 0
        assert step.reasoning_tokens == 0
        assert step.total_tokens == 0
        assert step.estimated_cost_usd == 0.0
        assert step.provider_billed_cost_usd is None
        assert step.provider_usage_raw == {}

    def test_agent_step_allows_tool_metadata_without_model(self) -> None:
        step = AgentStep(
            step_id="step-2",
            run_id="run-1",
            session_id="session-1",
            user_id="user-1",
            step_type=AgentStepType.TOOL,
            status=AgentStepStatus.COMPLETED,
            tool_name="search_query",
            started_at=datetime.now(UTC),
        )

        assert step.step_type == AgentStepType.TOOL
        assert step.tool_name == "search_query"
        assert step.model is None

    def test_agent_step_total_tokens_does_not_double_count_cached_input(self) -> None:
        step = AgentStep(
            step_id="step-3",
            run_id="run-1",
            session_id="session-1",
            user_id="user-1",
            step_type=AgentStepType.LLM,
            status=AgentStepStatus.COMPLETED,
            started_at=datetime.now(UTC),
            input_tokens=100,
            cached_input_tokens=20,
            output_tokens=40,
            reasoning_tokens=12,
        )

        assert step.total_tokens == 152

    def test_agent_step_status_is_enum_backed(self) -> None:
        step = AgentStep(
            step_id="step-4",
            run_id="run-1",
            session_id="session-1",
            user_id="user-1",
            step_type=AgentStepType.TOOL,
            status="failed",
            tool_name="search_query",
            started_at=datetime.now(UTC),
        )

        assert step.status == AgentStepStatus.FAILED
