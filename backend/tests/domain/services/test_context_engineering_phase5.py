"""Tests for Phase 5 context engineering enhancements.

Tests pressure-aware dynamic memory budgeting and adaptive context injection.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.memory_service import ContextEngineeringService, ContextServiceConfig


class TestDynamicMemoryBudgeting:
    """Test pressure-aware memory budgeting."""

    def test_full_budget_low_pressure(self):
        """Test full budget is used at low pressure."""
        config = ContextServiceConfig(max_injected_tokens=2000)
        service = ContextEngineeringService(config=config)

        # Low pressure (0.3): full budget
        budget = service.get_memory_budget(pressure_signal=0.3)
        assert budget == 2000

    def test_75_percent_moderate_pressure(self):
        """Test 75% budget at moderate pressure."""
        config = ContextServiceConfig(max_injected_tokens=2000)
        service = ContextEngineeringService(config=config)

        # Moderate pressure (0.6): 75% budget
        budget = service.get_memory_budget(pressure_signal=0.6)
        assert budget == int(2000 * 0.75)

    def test_50_percent_high_pressure(self):
        """Test 50% budget at high pressure."""
        config = ContextServiceConfig(max_injected_tokens=2000)
        service = ContextEngineeringService(config=config)

        # High pressure (0.8): 50% budget
        budget = service.get_memory_budget(pressure_signal=0.8)
        assert budget == int(2000 * 0.50)

    def test_25_percent_critical_pressure(self):
        """Test 25% budget at critical pressure."""
        config = ContextServiceConfig(max_injected_tokens=2000)
        service = ContextEngineeringService(config=config)

        # Critical pressure (0.95): 25% budget
        budget = service.get_memory_budget(pressure_signal=0.95)
        assert budget == int(2000 * 0.25)

    def test_budget_boundaries(self):
        """Test budget calculation at pressure boundaries."""
        config = ContextServiceConfig(max_injected_tokens=2000)
        service = ContextEngineeringService(config=config)

        # Boundary conditions
        assert service.get_memory_budget(0.0) == 2000  # No pressure
        assert service.get_memory_budget(0.49) == 2000  # Just below 50%
        assert service.get_memory_budget(0.50) == 1500  # At 50%
        assert service.get_memory_budget(0.69) == 1500  # Just below 70%
        assert service.get_memory_budget(0.70) == 1000  # At 70%
        assert service.get_memory_budget(0.84) == 1000  # Just below 85%
        assert service.get_memory_budget(0.85) == 500  # At 85%
        assert service.get_memory_budget(1.0) == 500  # At limit


class TestAdaptiveContextInjection:
    """Test pressure-aware context injection."""

    @pytest.mark.asyncio
    async def test_inject_with_dynamic_budget(self):
        """Test context injection with pressure-aware budgeting."""
        config = ContextServiceConfig(max_injected_tokens=1000)
        llm_mock = MagicMock()
        service = ContextEngineeringService(llm=llm_mock, config=config)

        # Mock memory object
        memory = MagicMock()
        memory.get_messages.return_value = []
        memory.messages = []

        # Mock get_relevant_context to return content
        service.get_relevant_context = AsyncMock(return_value="Relevant context content")

        # Inject at high pressure (0.8) - should use 50% budget
        result = await service.inject_context_adaptive(
            memory=memory,
            step_description="Test step",
            pressure_signal=0.8,
        )

        assert result is True
        assert len(memory.messages) == 1
        assert "budget: 500 tokens" in memory.messages[0]["content"]
        assert "pressure: 0.80" in memory.messages[0]["content"]

        # Verify get_relevant_context was called with reduced budget
        service.get_relevant_context.assert_called_once()
        call_kwargs = service.get_relevant_context.call_args.kwargs
        assert call_kwargs["max_tokens"] == 500  # 50% of 1000

    @pytest.mark.asyncio
    async def test_inject_at_low_pressure(self):
        """Test full budget injection at low pressure."""
        config = ContextServiceConfig(max_injected_tokens=2000)
        service = ContextEngineeringService(config=config)

        memory = MagicMock()
        memory.get_messages.return_value = []
        memory.messages = []

        service.get_relevant_context = AsyncMock(return_value="Context")

        # Low pressure: full budget
        result = await service.inject_context_adaptive(
            memory=memory,
            step_description="Test",
            pressure_signal=0.3,
        )

        assert result is True
        call_kwargs = service.get_relevant_context.call_args.kwargs
        assert call_kwargs["max_tokens"] == 2000  # Full budget

    @pytest.mark.asyncio
    async def test_no_injection_when_disabled(self):
        """Test no injection when service is disabled."""
        config = ContextServiceConfig(enabled=False)
        service = ContextEngineeringService(config=config)

        memory = MagicMock()
        memory.messages = []

        result = await service.inject_context_adaptive(
            memory=memory,
            step_description="Test",
            pressure_signal=0.5,
        )

        assert result is False
        assert len(memory.messages) == 0

    @pytest.mark.asyncio
    async def test_no_injection_when_no_context(self):
        """Test no injection when no relevant context found."""
        service = ContextEngineeringService()

        memory = MagicMock()
        memory.messages = []

        service.get_relevant_context = AsyncMock(return_value="")

        result = await service.inject_context_adaptive(
            memory=memory,
            step_description="Test",
            pressure_signal=0.5,
        )

        assert result is False
        assert len(memory.messages) == 0

    @pytest.mark.asyncio
    async def test_system_message_insertion_order(self):
        """Test context is inserted after system prompt if present."""
        config = ContextServiceConfig(max_injected_tokens=1000)
        service = ContextEngineeringService(config=config)

        # Memory with existing system message
        memory = MagicMock()
        memory.get_messages.return_value = [{"role": "system", "content": "System prompt"}]
        memory.messages = [{"role": "system", "content": "System prompt"}]

        service.get_relevant_context = AsyncMock(return_value="Context")

        await service.inject_context_adaptive(
            memory=memory,
            step_description="Test",
            pressure_signal=0.5,
        )

        # Context should be inserted at index 1 (after system prompt)
        assert len(memory.messages) == 2
        assert memory.messages[0]["content"] == "System prompt"
        assert "Relevant context" in memory.messages[1]["content"]

    @pytest.mark.asyncio
    async def test_pressure_signal_in_message(self):
        """Test pressure signal is included in context message."""
        service = ContextEngineeringService()

        memory = MagicMock()
        memory.get_messages.return_value = []
        memory.messages = []

        service.get_relevant_context = AsyncMock(return_value="Test context")

        await service.inject_context_adaptive(
            memory=memory,
            step_description="Test",
            pressure_signal=0.73,
        )

        # Check pressure signal in message
        injected_message = memory.messages[0]
        assert "pressure: 0.73" in injected_message["content"]


class TestBackwardCompatibility:
    """Test that original inject_context method still works."""

    @pytest.mark.asyncio
    async def test_original_inject_context(self):
        """Test original inject_context method unchanged."""
        config = ContextServiceConfig(max_injected_tokens=1000)
        service = ContextEngineeringService(config=config)

        memory = MagicMock()
        memory.get_messages.return_value = []
        memory.messages = []

        service.get_relevant_context = AsyncMock(return_value="Context")

        # Original method should still work
        result = await service.inject_context(memory=memory, step_description="Test")

        assert result is True
        assert len(memory.messages) > 0
        # Original method doesn't include pressure info
        injected_message = memory.messages[0]
        assert "pressure" not in injected_message["content"]
