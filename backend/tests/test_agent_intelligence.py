"""Tests for agent intelligence enhancements.

Covers:
- Lowered compaction thresholds (Task 2)
- Memory compaction tuning (Task 3)
- Phase-based tool filtering (Task 5)
- Grounding rules in system prompt (Task 1)
"""

from app.domain.models.memory import Memory, MemoryConfig
from app.domain.services.agents.token_manager import TokenManager


class TestCompactionThresholds:
    """Test that compaction thresholds match current optimization values."""

    def test_pressure_thresholds_lowered(self):
        """Verify current thresholds (60/70/80/90) are configured."""
        assert TokenManager.PRESSURE_THRESHOLDS["early_warning"] == 0.60
        assert TokenManager.PRESSURE_THRESHOLDS["warning"] == 0.70
        assert TokenManager.PRESSURE_THRESHOLDS["critical"] == 0.80
        assert TokenManager.PRESSURE_THRESHOLDS["overflow"] == 0.90

    def test_safety_margin_increased(self):
        """Verify safety margin is 2048 for improved context utilization."""
        assert TokenManager.SAFETY_MARGIN == 2048

    def test_compaction_triggers_at_critical_threshold(self):
        """Verify compaction triggers when tokens exceed critical threshold."""
        tm = TokenManager(model_name="gpt-4", max_context_tokens=100000)
        # effective = 100000 - 4096 = 95904, critical = 0.70 * 95904 ≈ 67133
        # Use many distinct words to avoid BPE compression
        words = " ".join(f"word{i}" for i in range(30000))
        messages = [
            {"role": "system", "content": words},
        ]
        # Verify the token count is above critical threshold
        token_count = tm.count_messages_tokens(messages)
        effective = tm._effective_limit
        critical_threshold = effective * tm.PRESSURE_THRESHOLDS["critical"]
        assert token_count > critical_threshold, (
            f"Token count {token_count} should exceed critical threshold {critical_threshold}"
        )
        assert tm.should_trigger_compaction(messages)

    def test_no_compaction_below_critical(self):
        """Verify compaction doesn't trigger below critical threshold."""
        tm = TokenManager(model_name="gpt-4", max_context_tokens=100000)
        # Use a small message well below the threshold
        messages = [
            {"role": "system", "content": "Hello world. This is a short message."},
        ]
        assert not tm.should_trigger_compaction(messages)


class TestMemoryCompaction:
    """Test memory compaction enhancements."""

    def test_auto_compact_threshold_lowered(self):
        """Verify auto_compact_token_threshold is 60K."""
        config = MemoryConfig()
        assert config.auto_compact_token_threshold == 60000

    def test_preserve_recent_reduced(self):
        """Verify preserve_recent is 8."""
        config = MemoryConfig()
        assert config.preserve_recent == 8

    def test_compactable_functions_expanded(self):
        """Verify additional functions are in the compactable list."""
        config = MemoryConfig()
        assert "shell_view" in config.compactable_functions
        assert "code_execute" in config.compactable_functions
        assert "file_list_directory" in config.compactable_functions
        assert "code_run_artifact" in config.compactable_functions

    def test_large_tool_result_truncation(self):
        """Verify oversized tool results are truncated during compaction."""
        memory = Memory()
        # Add system message
        memory.add_message({"role": "system", "content": "system prompt"})
        # Add a very large tool result (not in compactable list)
        large_content = "x" * 10000  # >8000 char threshold
        memory.add_message(
            {
                "role": "tool",
                "function_name": "custom_tool",
                "content": large_content,
            }
        )
        # Add recent messages to push the large one past preserve_recent
        for i in range(10):
            memory.add_message({"role": "user", "content": f"msg {i}"})

        compacted = memory.smart_compact()
        assert compacted > 0
        # Verify the large result was truncated
        tool_msg = memory.messages[1]
        assert len(tool_msg["content"]) < len(large_content)
        assert "truncated" in tool_msg["content"]

    def test_compactable_tool_result_replaced(self):
        """Verify compactable tool results are replaced with stub."""
        memory = Memory()
        memory.add_message({"role": "system", "content": "system prompt"})
        memory.add_message(
            {
                "role": "tool",
                "function_name": "file_read",
                "content": "file content here " * 100,
            }
        )
        for i in range(10):
            memory.add_message({"role": "user", "content": f"msg {i}"})

        compacted = memory.smart_compact()
        assert compacted > 0
        tool_msg = memory.messages[1]
        assert "(compacted)" in tool_msg["content"]


class TestPhaseToolFiltering:
    """Test phase-based tool filtering."""

    def test_phase_tool_groups_defined(self):
        """Verify PHASE_TOOL_GROUPS has expected phases."""
        from app.domain.services.agents.base import BaseAgent

        assert "planning" in BaseAgent.PHASE_TOOL_GROUPS
        assert "executing" in BaseAgent.PHASE_TOOL_GROUPS
        assert "verifying" in BaseAgent.PHASE_TOOL_GROUPS

    def test_executing_phase_allows_all_tools(self):
        """Verify executing phase returns None (all tools allowed)."""
        from app.domain.services.agents.base import BaseAgent

        assert BaseAgent.PHASE_TOOL_GROUPS["executing"] is None

    def test_planning_phase_excludes_write_tools(self):
        """Verify planning phase doesn't include file_write."""
        from app.domain.services.agents.base import BaseAgent

        planning_tools = BaseAgent.PHASE_TOOL_GROUPS["planning"]
        assert "file_read" in planning_tools
        assert "file_write" not in planning_tools
        assert "info_search_web" in planning_tools

    def test_verifying_phase_includes_test_tools(self):
        """Verify verifying phase includes test execution tools."""
        from app.domain.services.agents.base import BaseAgent

        verifying_tools = BaseAgent.PHASE_TOOL_GROUPS["verifying"]
        assert "test_run" in verifying_tools
        assert "test_list" in verifying_tools
        assert "file_read" in verifying_tools

    def test_active_phase_filters_tools(self):
        """Verify _active_phase attribute filters get_available_tools output."""
        from unittest.mock import MagicMock

        from app.domain.services.agents.base import BaseAgent

        # Create a mock tool that returns multiple tool definitions
        mock_tool = MagicMock()
        mock_tool.get_tools.return_value = [
            {"type": "function", "function": {"name": "file_read", "parameters": {}}},
            {"type": "function", "function": {"name": "file_write", "parameters": {}}},
            {"type": "function", "function": {"name": "info_search_web", "parameters": {}}},
            {"type": "function", "function": {"name": "code_execute", "parameters": {}}},
        ]
        mock_tool.has_function.return_value = True
        mock_tool.name = "test_tool"

        # Create agent with mock (bypass full init)
        agent = BaseAgent.__new__(BaseAgent)
        agent.tools = [mock_tool]
        agent._active_phase = None

        # No phase = all tools
        all_tools = agent.get_available_tools()
        assert len(all_tools) == 4

        # Planning phase = filtered
        agent._active_phase = "planning"
        planning_tools = agent.get_available_tools()
        planning_names = [t["function"]["name"] for t in planning_tools]
        assert "file_read" in planning_names
        assert "file_write" not in planning_names
        assert "info_search_web" in planning_names

        # Reset phase
        agent._active_phase = None
        all_again = agent.get_available_tools()
        assert len(all_again) == 4


class TestGroundingRules:
    """Test that grounding rules are present in system prompt."""

    def test_grounding_rules_in_system_prompt(self):
        """Verify tool output grounding rules are included."""
        from app.domain.services.prompts.system import SYSTEM_PROMPT

        assert "Tool Output Grounding Protocol" in SYSTEM_PROMPT

    def test_grounding_rules_content(self):
        """Verify key grounding directives are present."""
        from app.domain.services.prompts.system import SYSTEM_PROMPT

        prompt_lower = SYSTEM_PROMPT.lower()
        assert "tool outputs override" in prompt_lower or "tool outputs override" in SYSTEM_PROMPT

    def test_uncertainty_protocol_in_system_prompt(self):
        """Verify uncertainty protocol is included."""
        from app.domain.services.prompts.system import SYSTEM_PROMPT

        assert "uncertainty_protocol" in SYSTEM_PROMPT.lower() or "WHEN UNSURE" in SYSTEM_PROMPT

    def test_uncertainty_protocol_allows_dont_know(self):
        """Verify the agent is allowed to say 'I don't know'."""
        from app.domain.services.prompts.system import SYSTEM_PROMPT

        assert "I don't know" in SYSTEM_PROMPT or "I was unable to verify" in SYSTEM_PROMPT
