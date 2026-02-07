"""Browser Agent LangGraph Node

Elevates browser-use from a tool to a first-class LangGraph node,
providing streaming, control, and interruption capabilities.

Phase 2 Enhancement: Browser-use as LangGraph Node Integration

Key Features:
- Real-time streaming of browser actions via get_stream_writer()
- Proper interruption handling for human-in-the-loop
- CDP connection sharing via connection pool
- Configurable max steps and timeouts
- Event emission for frontend visualization

Usage:
    # The node is integrated into the LangGraph workflow
    # and called when routing determines browser task is needed
    async for chunk in graph.astream(state, config):
        # Browser events streamed in real-time
        pass
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.domain.services.langgraph.state import PlanActState

logger = logging.getLogger(__name__)

# Check if browser_use is available
try:
    from browser_use import Agent as BrowserUseAgent
    from browser_use import BrowserSession

    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    BrowserUseAgent = None
    BrowserSession = None


class BrowserStepStatus(str, Enum):
    """Status of a browser agent step."""

    STARTED = "started"
    THINKING = "thinking"
    ACTING = "acting"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass
class BrowserStepEvent:
    """Event emitted during browser agent execution.

    This is a standalone dataclass (not inheriting from BaseEvent)
    to allow simple instantiation with default values.
    """

    type: str = "browser_step"
    step_number: int = 0
    status: BrowserStepStatus = BrowserStepStatus.STARTED
    action: str | None = None
    thought: str | None = None
    url: str | None = None
    screenshot_base64: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class BrowserNodeResult:
    """Result of browser agent node execution."""

    success: bool
    result: str | None = None
    steps_executed: int = 0
    final_url: str | None = None
    errors: list[str] = field(default_factory=list)
    events: list[BrowserStepEvent] = field(default_factory=list)
    execution_time_ms: float = 0.0
    interrupted: bool = False


@dataclass
class BrowserNodeConfig:
    """Configuration for browser agent node."""

    max_steps: int = 15
    timeout_seconds: int = 300
    use_vision: bool = True
    capture_screenshots: bool = True
    stream_events: bool = True


async def browser_agent_node(state: "PlanActState") -> dict[str, Any]:
    """LangGraph node that executes browser-use agent.

    This node elevates browser-use from a tool to a first-class LangGraph
    node, providing streaming support and proper interruption handling.

    Args:
        state: Current PlanActState with browser_task and cdp_url

    Returns:
        State update dict with browser_result and pending_events
    """
    settings = get_settings()

    # Check if browser node feature is enabled
    if not settings.feature_browser_node:
        logger.debug("Browser node feature disabled, skipping")
        return {"browser_result": None, "pending_events": []}

    # Check if browser_use is available
    if not BROWSER_USE_AVAILABLE:
        logger.warning("browser_use package not installed, cannot execute browser node")
        return {
            "browser_result": BrowserNodeResult(
                success=False,
                errors=["browser_use package not installed"],
            ),
            "pending_events": [],
        }

    # Extract browser task from state
    browser_task = state.get("browser_task")
    cdp_url = state.get("cdp_url")

    if not browser_task:
        logger.debug("No browser_task in state, skipping browser node")
        return {"browser_result": None, "pending_events": []}

    if not cdp_url:
        logger.warning("No cdp_url in state, cannot execute browser agent")
        return {
            "browser_result": BrowserNodeResult(
                success=False,
                errors=["No CDP URL available for browser agent"],
            ),
            "pending_events": [],
        }

    # Get configuration
    config = BrowserNodeConfig(
        max_steps=settings.browser_agent_max_steps,
        timeout_seconds=settings.browser_agent_timeout,
        use_vision=settings.browser_agent_use_vision,
    )

    # Execute browser agent
    result = await _execute_browser_agent(state, browser_task, cdp_url, config)

    return {
        "browser_result": result,
        "pending_events": result.events,
    }


async def _execute_browser_agent(
    state: "PlanActState",
    task: str,
    cdp_url: str,
    config: BrowserNodeConfig,
) -> BrowserNodeResult:
    """Execute browser-use agent with streaming support.

    Args:
        state: Current workflow state
        task: Browser task description
        cdp_url: Chrome DevTools Protocol URL
        config: Browser node configuration

    Returns:
        BrowserNodeResult with execution details
    """
    start_time = datetime.now()
    events: list[BrowserStepEvent] = []
    errors: list[str] = []

    # Get event queue for real-time streaming
    event_queue = state.get("event_queue")

    async def emit_event(event: BrowserStepEvent) -> None:
        """Emit event to both queue and events list."""
        events.append(event)
        if event_queue and config.stream_events:
            try:
                await event_queue.put(event)
            except Exception as e:
                logger.debug(f"Failed to emit event to queue: {e}")

    # Emit start event
    await emit_event(
        BrowserStepEvent(
            step_number=0,
            status=BrowserStepStatus.STARTED,
            thought=f"Starting browser agent for task: {task[:100]}...",
            metadata={"task": task, "cdp_url": cdp_url},
        )
    )

    try:
        # Create browser session with CDP URL
        session = BrowserSession(cdp_url=cdp_url)

        # Get LLM configuration for browser agent
        settings = get_settings()
        llm_config = _get_browser_llm_config(settings)

        # Create browser-use agent
        agent = BrowserUseAgent(
            task=task,
            browser_session=session,
            llm=llm_config,
            max_steps=config.max_steps,
            use_vision=config.use_vision,
        )

        # Execute with timeout
        step_count = 0
        final_url = None
        result_text = None
        interrupted = False

        try:
            async with asyncio.timeout(config.timeout_seconds):
                # Run agent with step callbacks
                async for step in _run_agent_with_streaming(agent, config, emit_event):
                    step_count += 1

                    # Check for interruption request
                    if state.get("needs_human_input"):
                        interrupted = True
                        await emit_event(
                            BrowserStepEvent(
                                step_number=step_count,
                                status=BrowserStepStatus.INTERRUPTED,
                                thought="Execution interrupted for human input",
                            )
                        )
                        break

                # Get final result
                if hasattr(agent, "result"):
                    result_text = str(agent.result)
                if hasattr(session, "current_url"):
                    final_url = session.current_url

        except TimeoutError:
            errors.append(f"Browser agent timed out after {config.timeout_seconds}s")
            await emit_event(
                BrowserStepEvent(
                    step_number=step_count,
                    status=BrowserStepStatus.FAILED,
                    error=f"Timeout after {config.timeout_seconds}s",
                )
            )

        # Emit completion event
        await emit_event(
            BrowserStepEvent(
                step_number=step_count,
                status=BrowserStepStatus.COMPLETED if not errors else BrowserStepStatus.FAILED,
                thought=f"Browser agent completed after {step_count} steps",
                url=final_url,
            )
        )

        execution_time = (datetime.now() - start_time).total_seconds() * 1000

        return BrowserNodeResult(
            success=len(errors) == 0,
            result=result_text,
            steps_executed=step_count,
            final_url=final_url,
            errors=errors,
            events=events,
            execution_time_ms=execution_time,
            interrupted=interrupted,
        )

    except Exception as e:
        error_msg = f"Browser agent execution failed: {e!s}"
        logger.error(error_msg, exc_info=True)
        errors.append(error_msg)

        await emit_event(
            BrowserStepEvent(
                step_number=0,
                status=BrowserStepStatus.FAILED,
                error=error_msg,
            )
        )

        execution_time = (datetime.now() - start_time).total_seconds() * 1000

        return BrowserNodeResult(
            success=False,
            errors=errors,
            events=events,
            execution_time_ms=execution_time,
        )


async def _run_agent_with_streaming(
    agent: Any,
    config: BrowserNodeConfig,
    emit_event: Any,
) -> Any:
    """Run browser-use agent with step-by-step streaming.

    This generator wraps the agent execution to emit events
    at each step for real-time frontend updates.

    Args:
        agent: BrowserUseAgent instance
        config: Browser node configuration
        emit_event: Async function to emit events

    Yields:
        Step information as agent executes
    """
    step_number = 0

    # Check if agent has streaming capability
    if hasattr(agent, "run_with_streaming"):
        # Use native streaming if available
        async for step in agent.run_with_streaming():
            step_number += 1

            # Extract step details
            thought = step.get("thought") if isinstance(step, dict) else getattr(step, "thought", None)
            action = step.get("action") if isinstance(step, dict) else getattr(step, "action", None)
            url = step.get("url") if isinstance(step, dict) else getattr(step, "url", None)
            screenshot = step.get("screenshot") if isinstance(step, dict) else getattr(step, "screenshot", None)

            # Emit thinking event
            if thought:
                await emit_event(
                    BrowserStepEvent(
                        step_number=step_number,
                        status=BrowserStepStatus.THINKING,
                        thought=thought,
                        url=url,
                    )
                )

            # Emit action event
            if action:
                await emit_event(
                    BrowserStepEvent(
                        step_number=step_number,
                        status=BrowserStepStatus.ACTING,
                        action=str(action),
                        url=url,
                        screenshot_base64=screenshot if config.capture_screenshots else None,
                    )
                )

            yield step

    else:
        # Fallback: run without streaming
        logger.debug("Browser agent does not support streaming, running in batch mode")

        # Run the agent
        result = await agent.run()

        # Emit single completion event
        await emit_event(
            BrowserStepEvent(
                step_number=1,
                status=BrowserStepStatus.COMPLETED,
                thought="Browser task completed",
                metadata={"result": str(result)[:500] if result else None},
            )
        )

        yield {"result": result}


def _get_browser_llm_config(settings: Any) -> Any:
    """Get LLM configuration for browser-use agent.

    Configures the LLM based on current provider settings.

    Args:
        settings: Application settings

    Returns:
        LLM configuration for browser-use
    """
    try:
        from langchain_anthropic import ChatAnthropic
        from langchain_openai import ChatOpenAI

        if settings.llm_provider == "anthropic":
            return ChatAnthropic(
                model=settings.anthropic_model_name,
                api_key=settings.anthropic_api_key,
                temperature=settings.temperature,
            )
        # Default to OpenAI-compatible
        return ChatOpenAI(
            model=settings.model_name,
            api_key=settings.api_key,
            base_url=settings.api_base,
            temperature=settings.temperature,
        )
    except ImportError:
        logger.warning("LangChain not available, browser agent may fail")
        return None


def should_use_browser_node(state: "PlanActState") -> bool:
    """Determine if the current step should use browser agent node.

    This routing function checks if the current plan step
    would benefit from autonomous browser control.

    Args:
        state: Current workflow state

    Returns:
        True if browser node should be used
    """
    settings = get_settings()

    # Check if feature is enabled
    if not settings.feature_browser_node:
        return False

    # Check if browser_use is available
    if not BROWSER_USE_AVAILABLE:
        return False

    # Get current step
    step = state.get("current_step")
    if not step:
        return False

    # Keywords that indicate browser agent is appropriate
    browser_keywords = [
        "browse",
        "navigate",
        "scrape",
        "fill form",
        "autonomous",
        "web automation",
        "click",
        "submit form",
        "extract data",
        "web scraping",
        "website",
        "webpage",
    ]

    # Check step description
    description = step.description.lower() if hasattr(step, "description") else ""

    for keyword in browser_keywords:
        if keyword in description:
            logger.debug(f"Step matches browser keyword '{keyword}', routing to browser node")
            return True

    # Check if step explicitly has browser_task set
    if state.get("browser_task"):
        return True

    return False


__all__ = [
    "BROWSER_USE_AVAILABLE",
    "BrowserNodeConfig",
    "BrowserNodeResult",
    "BrowserStepEvent",
    "BrowserStepStatus",
    "browser_agent_node",
    "should_use_browser_node",
]
