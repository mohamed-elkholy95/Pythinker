from __future__ import annotations

import pytest

from app.domain.models.hooks import AgentHook, BashHook, HttpHook, PromptHook, validate_hook_configs
from app.domain.models.multi_task import TaskStatus
from app.domain.models.multi_task import is_terminal_status as is_task_terminal_status
from app.domain.models.plan import ExecutionStatus
from app.domain.models.plan import is_terminal_status as is_plan_terminal_status
from app.domain.services.tools.base import ToolDefaults, build_tool
from app.domain.utils.task_ids import (
    generate_agent_task_id,
    generate_bash_task_id,
    generate_remote_task_id,
    generate_workflow_task_id,
)


def test_build_tool_applies_defaults_and_overrides() -> None:
    tool = build_tool(
        {"name": "demo", "description": "demo tool"},
        is_read_only=True,
    )

    assert tool["name"] == "demo"
    assert tool["description"] == "demo tool"
    assert tool["is_enabled"] is True
    assert tool["is_read_only"] is True
    assert tool["is_destructive"] is False
    assert tool["is_concurrency_safe"] is False
    assert ToolDefaults().check_permissions() == "allow"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (ExecutionStatus.COMPLETED, True),
        (ExecutionStatus.FAILED, True),
        (ExecutionStatus.RUNNING, False),
        ("completed", True),
        ("unknown", False),
    ],
)
def test_plan_terminal_status_helper(status: ExecutionStatus | str, expected: bool) -> None:
    assert is_plan_terminal_status(status) is expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (TaskStatus.COMPLETED, True),
        (TaskStatus.FAILED, True),
        (TaskStatus.IN_PROGRESS, False),
        (TaskStatus.SKIPPED, True),
    ],
)
def test_task_terminal_status_helper(status: TaskStatus, expected: bool) -> None:
    assert is_task_terminal_status(status) is expected


def test_prefixed_task_ids_use_urlsafe_tokens() -> None:
    ids = {
        generate_bash_task_id(),
        generate_agent_task_id(),
        generate_remote_task_id(),
        generate_workflow_task_id(),
    }

    assert all(task_id[:2] in {"b_", "a_", "r_", "w_"} for task_id in ids)
    assert len(ids) == 4


def test_hook_configs_validate_discriminated_unions() -> None:
    hooks = validate_hook_configs(
        [
            {"type": "bash", "command": "echo hi"},
            {"type": "prompt", "prompt": "Summarize this"},
            {"type": "agent", "agent": "researcher", "prompt": "Investigate"},
            {"type": "http", "url": "https://example.com", "method": "POST"},
        ]
    )

    assert [type(hook) for hook in hooks] == [BashHook, PromptHook, AgentHook, HttpHook]
