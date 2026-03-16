"""Tests for tool argument pre-validation against JSON schema."""

from typing import ClassVar

from app.infrastructure.external.llm.openai_llm import OpenAILLM


class TestToolArgValidation:
    SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "file": {"type": "string"},
            "content": {"type": "string"},
            "append": {"type": "boolean"},
        },
        "required": ["file", "content"],
    }

    def test_valid_args_pass(self):
        errors = OpenAILLM._validate_tool_args_static({"file": "/workspace/report.md", "content": "hello"}, self.SCHEMA)
        assert errors == []

    def test_missing_required_field(self):
        errors = OpenAILLM._validate_tool_args_static({"content": "hello"}, self.SCHEMA)
        assert len(errors) == 1
        assert "file" in errors[0]

    def test_wrong_type(self):
        errors = OpenAILLM._validate_tool_args_static({"file": 123, "content": "hello"}, self.SCHEMA)
        assert len(errors) == 1
        assert "string" in errors[0]

    def test_multiple_errors(self):
        errors = OpenAILLM._validate_tool_args_static({}, self.SCHEMA)
        assert len(errors) == 2  # Both required fields missing

    def test_extra_fields_ignored(self):
        errors = OpenAILLM._validate_tool_args_static({"file": "x", "content": "y", "extra": 42}, self.SCHEMA)
        assert errors == []
