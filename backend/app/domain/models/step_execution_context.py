"""Domain model for step execution context assembly.

Bundles all context signals needed for building an execution prompt,
replacing the 14-parameter build_execution_prompt() signature and
the scattered context assembly in ExecutionAgent.execute_step().

Follows existing patterns:
- @dataclass(frozen=True, slots=True) like ResponsePolicy, ConversationTurn
- Domain model in app/domain/models/ like RequestContract
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PromptSignalConfig:
    """Controls which optional prompt signals are enabled.

    Separates "what signals to inject" from "what context data to use".
    Defaults match current build_execution_prompt() defaults.
    """

    enable_cot: bool = True
    include_current_date: bool = True
    enable_source_attribution: bool = True
    enable_intent_guidance: bool = True
    enable_anti_hallucination: bool = True


@dataclass(frozen=True, slots=True)
class StepExecutionContext:
    """Immutable bundle of all context needed for step prompt assembly.

    Assembled by StepContextAssembler, consumed by build_execution_prompt_from_context().
    Once created, read-only for the rest of the pipeline.
    """

    # Required core fields
    step_description: str
    user_message: str
    attachments: str
    language: str

    # Optional context signals (all default to None)
    pressure_signal: str | None = None
    task_state: str | None = None
    memory_context: str | None = None
    search_context: str | None = None
    conversation_context: str | None = None

    # Post-prompt appendages (currently scattered in execute_step lines 418-453)
    working_context_summary: str | None = None
    synthesized_context: str | None = None
    blocker_warnings: list[str] = field(default_factory=list)
    error_pattern_signal: str | None = None
    locked_entity_reminder: str | None = None

    # Signal configuration
    signal_config: PromptSignalConfig = field(default_factory=PromptSignalConfig)

    # MCP context: system prompt snippet listing connected MCP servers and tools
    mcp_context: str | None = None

    # DSPy-optimized prompt profile patch (PR-5: prompt optimization)
    # Applied by build_execution_prompt_from_context() when non-None.
    # None = baseline behavior (default, no opt-in required).
    profile_patch_text: str | None = None
