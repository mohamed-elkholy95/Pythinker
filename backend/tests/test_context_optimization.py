import json

from app.domain.services.agents.memory_manager import MemoryManager


def test_optimize_context_dedupes_tool_outputs():
    manager = MemoryManager()
    content = "line\n" * 300
    messages = [
        {"role": "tool", "function_name": "shell_exec", "content": content},
        {"role": "tool", "function_name": "shell_exec", "content": content},
        {"role": "user", "content": "Do something"},
    ]

    optimized, report = manager.optimize_context(messages, preserve_recent=1)

    assert report.tokens_saved > 0
    assert optimized[1]["content"] != content
    parsed = json.loads(optimized[1]["content"])
    assert "Duplicate tool output" in parsed.get("data", "")
    assert optimized[-1]["content"] == "Do something"


def test_optimize_context_temporal_compression():
    manager = MemoryManager()
    content = "x" * 1200
    messages = [
        {"role": "tool", "function_name": "browser_view", "content": content},
        {"role": "user", "content": "Keep this"},
    ]

    optimized, report = manager.optimize_context(messages, preserve_recent=1)

    assert report.temporal_compacted >= 1
    parsed = json.loads(optimized[0]["content"])
    assert "Temporal summary" in parsed.get("data", "")
    assert optimized[1]["content"] == "Keep this"
