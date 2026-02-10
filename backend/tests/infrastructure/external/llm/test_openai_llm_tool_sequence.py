"""Tests for OpenAILLM tool-message sequence normalization."""

from app.infrastructure.external.llm.openai_llm import OpenAILLM


def _build_llm_for_sequence_tests() -> OpenAILLM:
    llm = OpenAILLM.__new__(OpenAILLM)
    llm._is_thinking_api = False
    return llm


def test_validate_and_fix_messages_preserves_valid_tool_call_contract():
    llm = _build_llm_for_sequence_tests()
    messages = [
        {"role": "user", "content": "Search docs"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "info_search_web", "arguments": '{"query":"x"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "name": "info_search_web", "content": '{"ok":true}'},
        {"role": "assistant", "content": "Done"},
    ]

    fixed = llm._validate_and_fix_messages(messages)

    assistant_with_tool = fixed[1]
    assert assistant_with_tool["role"] == "assistant"
    assert assistant_with_tool.get("tool_calls")
    assert fixed[2]["role"] == "tool"
    assert fixed[2]["tool_call_id"] == "call_1"


def test_validate_and_fix_messages_drops_unknown_tool_response_while_pending():
    llm = _build_llm_for_sequence_tests()
    messages = [
        {"role": "user", "content": "Search docs"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_expected",
                    "type": "function",
                    "function": {"name": "info_search_web", "arguments": '{"query":"x"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_unknown", "name": "info_search_web", "content": '{"ok":true}'},
        {"role": "user", "content": "continue"},
    ]

    fixed = llm._validate_and_fix_messages(messages)

    assert not any(
        msg.get("role") == "tool" and msg.get("tool_call_id") == "call_unknown"
        for msg in fixed
    )
