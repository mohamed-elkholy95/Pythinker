"""Tests for domain logging port."""

import logging

from app.domain.external.logging import AgentLogger, get_agent_logger


def test_agent_logger_protocol():
    """AgentLogger provides structured logging methods."""
    logger = get_agent_logger("test-agent", session_id="s1")
    assert hasattr(logger, "tool_started")
    assert hasattr(logger, "tool_completed")
    assert hasattr(logger, "tool_failed")
    assert hasattr(logger, "agent_step")
    assert hasattr(logger, "workflow_transition")


def test_agent_logger_logs_tool_started(caplog):
    """tool_started emits structured log."""
    with caplog.at_level(logging.INFO):
        logger = get_agent_logger("agent-1", session_id="s1")
        logger.tool_started("browser_navigate", "tc-001", {"url": "https://example.com"})
    assert "tool_started" in caplog.text or "browser_navigate" in caplog.text


def test_agent_logger_integration():
    """AgentLogger can be imported and used from domain layer."""
    logger = AgentLogger("test-agent-123", session_id="session-456")
    start = logger.tool_started("shell_exec", "tc-001", {"command": "ls -la"})
    assert isinstance(start, float)
    logger.tool_completed("shell_exec", "tc-001", start, success=True, message="ok")
    logger.agent_step("processing_response", iteration=3)
    logger.workflow_transition("planning", "executing", reason="plan approved")
    logger.security_event("blocked", "shell_exec", "dangerous command")
