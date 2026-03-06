"""Tests for adaptive tool max_tokens — file_write gets higher budget."""
from __future__ import annotations
import pytest
from app.infrastructure.external.llm.openai_llm import OpenAILLM


class TestAdaptiveToolMaxTokens:
    def test_file_write_tool_detected(self):
        tools = [{"type": "function", "function": {"name": "file_write", "parameters": {}}}]
        assert OpenAILLM._has_file_write_tool(tools) is True

    def test_file_append_tool_detected(self):
        tools = [{"type": "function", "function": {"name": "file_append", "parameters": {}}}]
        assert OpenAILLM._has_file_write_tool(tools) is True

    def test_non_file_write_tools_not_detected(self):
        tools = [
            {"type": "function", "function": {"name": "search_web", "parameters": {}}},
            {"type": "function", "function": {"name": "browser_navigate", "parameters": {}}},
        ]
        assert OpenAILLM._has_file_write_tool(tools) is False

    def test_empty_tools_not_detected(self):
        assert OpenAILLM._has_file_write_tool([]) is False
        assert OpenAILLM._has_file_write_tool(None) is False

    def test_mixed_tools_with_file_write(self):
        tools = [
            {"type": "function", "function": {"name": "search_web", "parameters": {}}},
            {"type": "function", "function": {"name": "file_write", "parameters": {}}},
        ]
        assert OpenAILLM._has_file_write_tool(tools) is True

    def test_malformed_tool_entry_handled(self):
        tools = [{"type": "function"}, {"function": {"name": "file_write"}}]
        # Should not crash, should detect file_write in second entry
        assert OpenAILLM._has_file_write_tool(tools) is True
