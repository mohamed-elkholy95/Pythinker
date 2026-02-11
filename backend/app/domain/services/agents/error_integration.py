"""
Error Integration Bridge - Unified error handling coordination.

Bridges ErrorHandler, StuckDetector, PatternAnalyzer, TokenManager, and MemoryManager
to provide coordinated error management, health assessment, and recovery guidance.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.domain.services.prediction.failure_predictor import FailurePredictor

logger = logging.getLogger(__name__)


class AgentHealthLevel(str, Enum):
    """Overall health level of the agent."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    STUCK = "stuck"


@dataclass
class AgentHealthStatus:
    """Comprehensive health status of the agent."""

    level: AgentHealthLevel
    error_count_recent: int = 0
    is_stuck: bool = False
    stuck_type: str | None = None
    token_pressure_level: str | None = None
    token_usage_pct: float = 0.0
    patterns_detected: list[dict[str, Any]] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    predicted_failure: bool = False
    failure_probability: float = 0.0
    failure_factors: list[str] = field(default_factory=list)
    recommended_intervention: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "level": self.level.value,
            "error_count_recent": self.error_count_recent,
            "is_stuck": self.is_stuck,
            "stuck_type": self.stuck_type,
            "token_pressure_level": self.token_pressure_level,
            "token_usage_pct": self.token_usage_pct,
            "patterns_detected": self.patterns_detected,
            "recommended_actions": self.recommended_actions,
            "predicted_failure": self.predicted_failure,
            "failure_probability": self.failure_probability,
            "failure_factors": self.failure_factors,
            "recommended_intervention": self.recommended_intervention,
            "details": self.details,
        }


@dataclass
class IterationGuidance:
    """Guidance for the next iteration based on error state analysis."""

    should_continue: bool = True
    inject_prompt: str | None = None
    trigger_compaction: bool = False
    patterns: list[dict[str, Any]] = field(default_factory=list)
    health_level: AgentHealthLevel = AgentHealthLevel.HEALTHY
    warnings: list[str] = field(default_factory=list)


class ErrorIntegrationBridge:
    """
    Bridges error handling components for coordinated management.

    Integrates:
    - ErrorHandler: Error classification and recovery strategies
    - StuckDetector: Loop detection and recovery prompts
    - ErrorPatternAnalyzer: Cross-error pattern detection
    - TokenManager: Context pressure monitoring
    - MemoryManager: Memory compaction triggers

    Provides unified health assessment and iteration guidance.
    """

    def __init__(
        self,
        error_handler=None,
        stuck_detector=None,
        pattern_analyzer=None,
        token_manager=None,
        memory_manager=None,
        feature_flags: dict[str, bool] | None = None,
    ):
        """Initialize with optional component references.

        Components can be set later via set_* methods if not available at init.
        """
        self._error_handler = error_handler
        self._stuck_detector = stuck_detector
        self._pattern_analyzer = pattern_analyzer
        self._token_manager = token_manager
        self._memory_manager = memory_manager
        self._feature_flags = feature_flags

        # Track iteration state
        self._iteration_count = 0
        self._last_health_status: AgentHealthStatus | None = None
        self._compaction_triggered_at: int | None = None

    def _resolve_feature_flags(self) -> dict[str, bool]:
        """Return injected feature flags, falling back to core config."""
        if self._feature_flags is not None:
            return self._feature_flags
        from app.core.config import get_feature_flags

        return get_feature_flags()

    def set_error_handler(self, error_handler) -> None:
        """Set the error handler component."""
        self._error_handler = error_handler

    def set_stuck_detector(self, stuck_detector) -> None:
        """Set the stuck detector component."""
        self._stuck_detector = stuck_detector

    def set_pattern_analyzer(self, pattern_analyzer) -> None:
        """Set the pattern analyzer component."""
        self._pattern_analyzer = pattern_analyzer

    def set_token_manager(self, token_manager) -> None:
        """Set the token manager component."""
        self._token_manager = token_manager

    def set_memory_manager(self, memory_manager) -> None:
        """Set the memory manager component."""
        self._memory_manager = memory_manager

    def assess_agent_health(self, messages: list[dict[str, Any]] | None = None) -> AgentHealthStatus:
        """Comprehensive health assessment across all systems.

        Args:
            messages: Optional current message history for analysis

        Returns:
            AgentHealthStatus with level, issues, and recommendations
        """
        health = AgentHealthStatus(level=AgentHealthLevel.HEALTHY)
        issues = []
        recommendations = []

        # Check error handler
        if self._error_handler:
            recent_errors = self._error_handler.get_recent_errors(limit=10)
            health.error_count_recent = len(recent_errors)

            if len(recent_errors) >= 5:
                issues.append("High error rate detected")
                recommendations.append("Consider simplifying the current approach")

            # Get recovery stats
            recovery_stats = self._error_handler.get_recovery_stats()
            if recovery_stats.get("success_rate", 1.0) < 0.5:
                issues.append("Low recovery success rate")
                recommendations.append("May need user intervention")
                health.details["recovery_stats"] = recovery_stats

        # Check stuck detector
        if self._stuck_detector:
            health.is_stuck = self._stuck_detector.is_stuck()
            if health.is_stuck:
                health.stuck_type = (
                    self._stuck_detector.get_stuck_type()
                    if hasattr(self._stuck_detector, "get_stuck_type")
                    else "unknown"
                )
                issues.append(f"Agent stuck: {health.stuck_type}")
                recommendations.append("Try a different approach or tool")

        # Check token pressure
        if self._token_manager and messages:
            try:
                pressure = self._token_manager.get_context_pressure(messages)
                health.token_pressure_level = pressure.level.value if hasattr(pressure, "level") else str(pressure)
                health.token_usage_pct = pressure.usage_percent if hasattr(pressure, "usage_percent") else 0.0

                if health.token_usage_pct > 85:
                    issues.append(f"High token pressure: {health.token_usage_pct:.0f}%")
                    recommendations.append("Consider memory compaction")
                elif health.token_usage_pct > 75:
                    recommendations.append("Monitor token usage")
            except Exception as e:
                logger.debug(f"Could not get token pressure: {e}")

        # Check pattern analyzer
        if self._pattern_analyzer:
            try:
                if self._error_handler:
                    recent_errors = self._error_handler.get_recent_errors(limit=20)
                    patterns = self._pattern_analyzer.analyze_patterns()
                    health.patterns_detected = (
                        [
                            {"type": p.pattern_type, "confidence": p.confidence, "suggestion": p.suggestion}
                            for p in patterns
                        ]
                        if patterns
                        else []
                    )

                    for pattern in patterns or []:
                        if pattern.confidence > 0.7:
                            issues.append(f"Pattern: {pattern.pattern_type}")
                            if pattern.suggestion:
                                recommendations.append(pattern.suggestion)
            except Exception as e:
                logger.debug(f"Could not analyze patterns: {e}")

        # Determine overall health level
        if health.is_stuck:
            health.level = AgentHealthLevel.STUCK
        elif len(issues) >= 3 or health.token_usage_pct > 90:
            health.level = AgentHealthLevel.CRITICAL
        elif len(issues) >= 1 or health.token_usage_pct > 75:
            health.level = AgentHealthLevel.DEGRADED
        else:
            health.level = AgentHealthLevel.HEALTHY

        health.recommended_actions = recommendations
        health.details["issues"] = issues

        # Failure prediction (shadow mode by default)
        flags = self._resolve_feature_flags()
        if flags.get("failure_prediction"):
            try:
                predictor = FailurePredictor()
                prediction = predictor.predict(
                    progress=None,
                    recent_actions=None,
                    stuck_analysis=self._stuck_detector.get_analysis() if self._stuck_detector else None,
                    token_usage_pct=health.token_usage_pct if health.token_usage_pct else None,
                )
                health.predicted_failure = prediction.will_fail
                health.failure_probability = prediction.probability
                health.failure_factors = prediction.factors
                health.recommended_intervention = prediction.recommended_action
            except Exception as e:
                logger.debug(f"Failure prediction failed: {e}")

        self._last_health_status = health
        return health

    async def handle_iteration_end(
        self, response: dict[str, Any], messages: list[dict[str, Any]] | None = None
    ) -> IterationGuidance:
        """Process end of iteration across all systems.

        Analyzes the response, checks for stuck states, patterns, and pressure,
        and returns guidance for the next iteration.

        Args:
            response: The LLM response from this iteration
            messages: Current message history

        Returns:
            IterationGuidance with continuation decision and prompts
        """
        self._iteration_count += 1
        guidance = IterationGuidance()

        # Track in stuck detector
        is_stuck = False
        if self._stuck_detector:
            try:
                is_stuck = self._stuck_detector.track_response(response)
            except Exception as e:
                logger.debug(f"Stuck detection failed: {e}")

        # Get health assessment
        health = self.assess_agent_health(messages)
        guidance.health_level = health.level
        guidance.patterns = health.patterns_detected

        # Determine if we should continue
        if is_stuck:
            recovery_attempts = getattr(self._stuck_detector, "_recovery_attempts", 0)
            if recovery_attempts >= 5:
                guidance.should_continue = False
                guidance.warnings.append("Maximum stuck recovery attempts reached")
            else:
                guidance.should_continue = True

        # Build guidance prompt
        prompt_parts = []

        # Add stuck recovery prompt
        if is_stuck and self._stuck_detector:
            recovery_prompt = self._stuck_detector.get_recovery_prompt()
            if recovery_prompt:
                prompt_parts.append(recovery_prompt)

        # Add pattern-based guidance
        if health.patterns_detected:
            top_pattern = max(health.patterns_detected, key=lambda p: p.get("confidence", 0))
            if top_pattern.get("confidence", 0) > 0.7 and top_pattern.get("suggestion"):
                prompt_parts.append(f"Pattern detected: {top_pattern['suggestion']}")

        # Add token pressure signal
        if health.token_pressure_level and health.token_pressure_level not in ["normal", "NORMAL"]:
            pressure_signal = (
                f"CONTEXT PRESSURE: {health.token_usage_pct:.0f}% used. Consider being more concise in responses."
            )
            prompt_parts.append(pressure_signal)

        guidance.inject_prompt = "\n\n".join(prompt_parts) if prompt_parts else None

        # Determine if compaction needed
        should_compact = (
            health.token_usage_pct > 85
            or (is_stuck and getattr(self._stuck_detector, "_recovery_attempts", 0) > 2)
            or health.level == AgentHealthLevel.CRITICAL
        )

        # Avoid compacting too frequently
        if should_compact and self._compaction_triggered_at:
            iterations_since_compaction = self._iteration_count - self._compaction_triggered_at
            if iterations_since_compaction < 3:
                should_compact = False

        if should_compact:
            guidance.trigger_compaction = True
            self._compaction_triggered_at = self._iteration_count

            # Trigger compaction if memory manager available
            if self._memory_manager:
                try:
                    await self._trigger_compaction()
                except Exception as e:
                    logger.warning(f"Compaction trigger failed: {e}")

        return guidance

    async def _trigger_compaction(self) -> None:
        """Trigger memory compaction via memory manager."""
        if self._memory_manager and hasattr(self._memory_manager, "compact"):
            logger.info("Triggering memory compaction via error integration bridge")
            await self._memory_manager.compact()

    def get_unified_recovery_prompt(self, error_context=None, tool_name: str | None = None) -> str | None:
        """Get unified recovery prompt combining all sources.

        Combines prompts from error handler, stuck detector, and pattern analyzer.

        Args:
            error_context: Optional error context for error-specific guidance
            tool_name: Optional tool name for tool-specific patterns

        Returns:
            Combined recovery prompt or None
        """
        prompts = []

        # Get error handler prompt
        if self._error_handler and error_context:
            error_prompt = self._error_handler.get_recovery_prompt(error_context, tool_name)
            if error_prompt:
                prompts.append(error_prompt)

        # Get stuck detector prompt
        if self._stuck_detector and self._stuck_detector.is_stuck():
            stuck_prompt = self._stuck_detector.get_recovery_prompt()
            if stuck_prompt:
                prompts.append(stuck_prompt)

        # Get pattern-based prompt
        if self._pattern_analyzer and self._error_handler:
            try:
                self._error_handler.get_recent_errors(limit=10)  # Refresh error window
                patterns = self._pattern_analyzer.analyze_patterns()
                if patterns:
                    best_pattern = max(patterns, key=lambda p: p.confidence)
                    if best_pattern.confidence > 0.6:
                        pattern_prompt = best_pattern.to_context_signal()
                        if pattern_prompt:
                            prompts.append(pattern_prompt)
            except Exception as e:
                logger.debug(f"Could not get pattern prompt: {e}")

        if not prompts:
            return None

        return "\n\n---\n\n".join(prompts)

    def reset(self) -> None:
        """Reset all state for a new session."""
        self._iteration_count = 0
        self._last_health_status = None
        self._compaction_triggered_at = None

        if self._error_handler:
            self._error_handler.clear_history()
            self._error_handler.reset_stats()

        if self._stuck_detector and hasattr(self._stuck_detector, "reset"):
            self._stuck_detector.reset()

    def get_metrics(self) -> dict[str, Any]:
        """Get metrics from all integrated components.

        Returns:
            Combined metrics dictionary
        """
        metrics = {
            "iteration_count": self._iteration_count,
            "last_health_level": self._last_health_status.level.value if self._last_health_status else None,
        }

        if self._error_handler:
            metrics["error_handler"] = self._error_handler.get_recovery_stats()

        if self._stuck_detector:
            metrics["stuck_detector"] = {
                "is_stuck": self._stuck_detector.is_stuck() if hasattr(self._stuck_detector, "is_stuck") else False,
                "recovery_attempts": getattr(self._stuck_detector, "_recovery_attempts", 0),
            }

        return metrics

    # Session Lifecycle Methods for Cross-Session Learning

    async def on_session_start(self, user_id: str, memory_service: Any | None = None) -> int:
        """Initialize cross-session learning at session start.

        Loads historical error patterns from long-term memory to prime
        the pattern analyzer with known issues for this user.

        Args:
            user_id: User ID for pattern retrieval
            memory_service: Memory service for retrieval

        Returns:
            Number of patterns loaded
        """
        if not memory_service:
            logger.debug("No memory service available for cross-session learning")
            return 0

        if not self._pattern_analyzer:
            logger.debug("No pattern analyzer available for cross-session learning")
            return 0

        # Set user ID on pattern analyzer
        self._pattern_analyzer.set_user_id(user_id)

        # Load historical patterns
        try:
            loaded = await self._pattern_analyzer.load_user_patterns(memory_service)
            if loaded > 0:
                logger.info(f"Cross-session learning: loaded {loaded} historical error patterns for user {user_id}")
            return loaded
        except Exception as e:
            logger.warning(f"Failed to load historical patterns: {e}")
            return 0

    async def on_session_end(self, memory_service: Any | None = None) -> int:
        """Persist learned patterns at session end.

        Saves detected error patterns to long-term memory for
        future cross-session learning.

        Args:
            memory_service: Memory service for persistence

        Returns:
            Number of patterns persisted
        """
        if not memory_service:
            logger.debug("No memory service available for pattern persistence")
            return 0

        if not self._pattern_analyzer:
            logger.debug("No pattern analyzer available for pattern persistence")
            return 0

        try:
            persisted = await self._pattern_analyzer.persist_patterns(memory_service)
            if persisted > 0:
                logger.info(f"Cross-session learning: persisted {persisted} error patterns to long-term memory")
            return persisted
        except Exception as e:
            logger.warning(f"Failed to persist error patterns: {e}")
            return 0
