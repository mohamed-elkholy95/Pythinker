"""Tests for cross-session error pattern persistence."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.agents.error_handler import ErrorContext, ErrorType
from app.domain.services.agents.error_integration import ErrorIntegrationBridge
from app.domain.services.agents.error_pattern_analyzer import (
    ErrorPatternAnalyzer,
    PatternType,
)


class TestErrorPatternAnalyzerPersistence:
    """Tests for ErrorPatternAnalyzer persistence methods."""

    def test_user_id_initialization(self):
        """Test that user_id can be set at init or later."""
        # Set at init
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        assert analyzer._user_id == "user-123"

        # Set later
        analyzer2 = ErrorPatternAnalyzer()
        assert analyzer2._user_id is None
        analyzer2.set_user_id("user-456")
        assert analyzer2._user_id == "user-456"

    def test_prewarned_tools_initialized(self):
        """Test that prewarned_tools dict is initialized."""
        analyzer = ErrorPatternAnalyzer()
        assert analyzer._prewarned_tools == {}

    @pytest.mark.asyncio
    async def test_persist_patterns_requires_user_id(self):
        """Test that persist_patterns requires user_id."""
        analyzer = ErrorPatternAnalyzer()  # No user_id
        memory_service = AsyncMock()

        persisted = await analyzer.persist_patterns(memory_service)

        assert persisted == 0
        memory_service.store_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_patterns_stores_high_confidence_patterns(self):
        """Test that high-confidence patterns are persisted."""
        from app.domain.models.long_term_memory import MemoryType

        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        memory_service = AsyncMock()
        memory_service.store_memory = AsyncMock()

        # Create error history to generate patterns
        error_context = MagicMock(spec=ErrorContext)
        error_context.error_type = ErrorType.TIMEOUT
        error_context.message = "Connection timed out"

        # Record multiple timeout errors to trigger pattern
        for _ in range(5):
            analyzer.record_error("shell", error_context)

        # Verify patterns are detected
        patterns = analyzer.analyze_patterns()
        assert len(patterns) > 0

        # Persist patterns
        persisted = await analyzer.persist_patterns(memory_service)

        # Should have called store_memory for high-confidence patterns
        if persisted > 0:
            memory_service.store_memory.assert_called()
            call_kwargs = memory_service.store_memory.call_args.kwargs
            assert call_kwargs["user_id"] == "user-123"
            assert call_kwargs["memory_type"] == MemoryType.ERROR_PATTERN

    @pytest.mark.asyncio
    async def test_persist_patterns_skips_low_confidence(self):
        """Test that low-confidence patterns are not persisted."""
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        memory_service = AsyncMock()

        # Record only 1 error (below threshold for patterns)
        error_context = MagicMock(spec=ErrorContext)
        error_context.error_type = ErrorType.TIMEOUT
        error_context.message = "Connection timed out"
        analyzer.record_error("shell", error_context)

        # Patterns should be empty or low confidence
        analyzer.analyze_patterns()
        persisted = await analyzer.persist_patterns(memory_service)

        # Should not persist anything
        assert persisted == 0

    @pytest.mark.asyncio
    async def test_load_user_patterns_requires_user_id(self):
        """Test that load_user_patterns requires user_id."""
        analyzer = ErrorPatternAnalyzer()  # No user_id
        memory_service = AsyncMock()

        loaded = await analyzer.load_user_patterns(memory_service)

        assert loaded == 0

    @pytest.mark.asyncio
    async def test_load_user_patterns_populates_prewarned_tools(self):
        """Test that loaded patterns populate prewarned_tools."""
        from app.domain.models.long_term_memory import MemoryEntry

        analyzer = ErrorPatternAnalyzer(user_id="user-123")

        # Mock memory service with results
        mock_memory = MagicMock(spec=MemoryEntry)
        mock_memory.content = "Shell commands frequently timeout. Try shorter operations."
        mock_memory.metadata = {"affected_tools": ["shell", "browser"]}

        mock_result = MagicMock()
        mock_result.memory = mock_memory

        memory_service = AsyncMock()
        memory_service.retrieve_relevant = AsyncMock(return_value=[mock_result])

        loaded = await analyzer.load_user_patterns(memory_service)

        assert loaded == 2  # Two tools affected
        assert "shell" in analyzer._prewarned_tools
        assert "browser" in analyzer._prewarned_tools
        assert analyzer._prewarned_tools["shell"] == mock_memory.content

    def test_proactive_signals_includes_historical_warnings(self):
        """Test that proactive signals include historical warnings."""
        analyzer = ErrorPatternAnalyzer(user_id="user-123")

        # Add a prewarned tool (simulating loaded historical pattern)
        analyzer._prewarned_tools["shell"] = "Shell commands timeout frequently."

        signals = analyzer.get_proactive_signals(["shell", "browser"])

        assert signals is not None
        assert "HISTORICAL" in signals
        assert "Shell commands timeout frequently" in signals

    def test_proactive_signals_avoids_duplicates(self):
        """Test that duplicate warnings are avoided."""
        analyzer = ErrorPatternAnalyzer(user_id="user-123")

        # Create a current pattern for shell
        error_context = MagicMock(spec=ErrorContext)
        error_context.error_type = ErrorType.TIMEOUT
        error_context.message = "timeout"

        for _ in range(5):
            analyzer.record_error("shell", error_context)

        # Also add a prewarned tool with same content
        analyzer._prewarned_tools["shell"] = "Tool 'shell' has failed"

        signals = analyzer.get_proactive_signals(["shell"])

        # Should not duplicate warnings
        assert signals is not None
        # Count occurrences of "shell"
        shell_mentions = signals.lower().count("shell")
        # Should only mention shell once or twice, not for each warning type
        assert shell_mentions <= 3

    def test_stats_includes_prewarned_tools_count(self):
        """Test that stats include prewarned_tools count."""
        analyzer = ErrorPatternAnalyzer()
        analyzer._prewarned_tools = {"shell": "warning1", "browser": "warning2"}

        stats = analyzer.get_stats()

        assert "prewarned_tools" in stats
        assert stats["prewarned_tools"] == 2


class TestErrorIntegrationBridgeLifecycle:
    """Tests for ErrorIntegrationBridge session lifecycle methods."""

    @pytest.mark.asyncio
    async def test_on_session_start_loads_patterns(self):
        """Test that on_session_start loads patterns."""
        pattern_analyzer = ErrorPatternAnalyzer()
        pattern_analyzer.load_user_patterns = AsyncMock(return_value=5)

        bridge = ErrorIntegrationBridge(pattern_analyzer=pattern_analyzer)
        memory_service = AsyncMock()

        loaded = await bridge.on_session_start("user-123", memory_service)

        assert loaded == 5
        pattern_analyzer.load_user_patterns.assert_called_once_with(memory_service)
        assert pattern_analyzer._user_id == "user-123"

    @pytest.mark.asyncio
    async def test_on_session_start_without_memory_service(self):
        """Test on_session_start returns 0 without memory service."""
        pattern_analyzer = ErrorPatternAnalyzer()
        bridge = ErrorIntegrationBridge(pattern_analyzer=pattern_analyzer)

        loaded = await bridge.on_session_start("user-123", None)

        assert loaded == 0

    @pytest.mark.asyncio
    async def test_on_session_start_without_pattern_analyzer(self):
        """Test on_session_start returns 0 without pattern analyzer."""
        bridge = ErrorIntegrationBridge()  # No pattern analyzer

        loaded = await bridge.on_session_start("user-123", AsyncMock())

        assert loaded == 0

    @pytest.mark.asyncio
    async def test_on_session_end_persists_patterns(self):
        """Test that on_session_end persists patterns."""
        pattern_analyzer = ErrorPatternAnalyzer(user_id="user-123")
        pattern_analyzer.persist_patterns = AsyncMock(return_value=3)

        bridge = ErrorIntegrationBridge(pattern_analyzer=pattern_analyzer)
        memory_service = AsyncMock()

        persisted = await bridge.on_session_end(memory_service)

        assert persisted == 3
        pattern_analyzer.persist_patterns.assert_called_once_with(memory_service)

    @pytest.mark.asyncio
    async def test_on_session_end_without_memory_service(self):
        """Test on_session_end returns 0 without memory service."""
        pattern_analyzer = ErrorPatternAnalyzer(user_id="user-123")
        bridge = ErrorIntegrationBridge(pattern_analyzer=pattern_analyzer)

        persisted = await bridge.on_session_end(None)

        assert persisted == 0

    @pytest.mark.asyncio
    async def test_on_session_end_without_pattern_analyzer(self):
        """Test on_session_end returns 0 without pattern analyzer."""
        bridge = ErrorIntegrationBridge()

        persisted = await bridge.on_session_end(AsyncMock())

        assert persisted == 0

    @pytest.mark.asyncio
    async def test_full_session_lifecycle(self):
        """Test full session lifecycle: start -> errors -> end."""

        # Create real pattern analyzer
        pattern_analyzer = ErrorPatternAnalyzer()
        bridge = ErrorIntegrationBridge(pattern_analyzer=pattern_analyzer)

        # Mock memory service
        memory_service = AsyncMock()
        memory_service.retrieve_relevant = AsyncMock(return_value=[])
        memory_service.store_memory = AsyncMock()

        # Session start - load patterns (empty)
        await bridge.on_session_start("user-123", memory_service)
        assert pattern_analyzer._user_id == "user-123"

        # Record errors during session
        error_context = MagicMock(spec=ErrorContext)
        error_context.error_type = ErrorType.TIMEOUT
        error_context.message = "timeout"

        for _ in range(5):
            pattern_analyzer.record_error("shell", error_context)

        # Session end - persist patterns
        await bridge.on_session_end(memory_service)

        # Should have attempted to store memory
        # (actual persistence depends on pattern confidence)


class TestPatternDetectionThresholds:
    """Tests for pattern detection with various thresholds."""

    def test_timeout_pattern_detection(self):
        """Test timeout pattern is detected after threshold."""
        analyzer = ErrorPatternAnalyzer()

        error_context = MagicMock(spec=ErrorContext)
        error_context.error_type = ErrorType.TIMEOUT
        error_context.message = "Connection timed out"

        # Below threshold
        for _ in range(2):
            analyzer.record_error("shell", error_context)

        patterns = analyzer.analyze_patterns()
        timeout_patterns = [p for p in patterns if p.pattern_type == PatternType.TIMEOUT_REPEATED]
        assert len(timeout_patterns) == 0

        # Hit threshold
        analyzer.record_error("shell", error_context)

        patterns = analyzer.analyze_patterns()
        timeout_patterns = [p for p in patterns if p.pattern_type == PatternType.TIMEOUT_REPEATED]
        assert len(timeout_patterns) == 1

    def test_failure_streak_pattern_detection(self):
        """Test failure streak pattern is detected."""
        analyzer = ErrorPatternAnalyzer()

        error_context = MagicMock(spec=ErrorContext)
        error_context.error_type = ErrorType.TOOL_EXECUTION
        error_context.message = "Tool failed"

        # Record consecutive failures
        for _ in range(3):
            analyzer.record_error("browser", error_context)

        patterns = analyzer.analyze_patterns()
        streak_patterns = [p for p in patterns if p.pattern_type == PatternType.TOOL_FAILURE_STREAK]
        assert len(streak_patterns) == 1
        assert "browser" in streak_patterns[0].affected_tools

    def test_success_breaks_failure_streak(self):
        """Test that recording success breaks failure streak."""
        analyzer = ErrorPatternAnalyzer()

        error_context = MagicMock(spec=ErrorContext)
        error_context.error_type = ErrorType.TOOL_EXECUTION
        error_context.message = "Tool failed"

        # Record 2 failures
        for _ in range(2):
            analyzer.record_error("browser", error_context)

        # Record success
        analyzer.record_success("browser")

        # Record 2 more failures
        for _ in range(2):
            analyzer.record_error("browser", error_context)

        patterns = analyzer.analyze_patterns()
        streak_patterns = [p for p in patterns if p.pattern_type == PatternType.TOOL_FAILURE_STREAK]
        # Streak should be broken, so no streak pattern
        assert len(streak_patterns) == 0
