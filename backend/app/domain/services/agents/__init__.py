from ...models.agent import Agent

# Task 7.1: Critic Agent for quality gate pattern
from .critic_agent import CriticAgent, CriticResult
from .error_handler import ErrorContext, ErrorHandler, ErrorType, TokenLimitExceededError

# P0 Priority: Hallucination Prevention & Prompt Adherence
from .grounding_validator import (
    GroundingLevel,
    GroundingResult,
    GroundingValidator,
    get_grounding_validator,
    validate_grounding,
)
from .guardrails import (
    GuardrailsManager,
    InputAnalysisResult,
    InputGuardrails,
    OutputAnalysisResult,
    OutputGuardrails,
    get_guardrails_manager,
)
from .intent_tracker import (
    IntentTracker,
    IntentTrackingResult,
    UserIntent,
    get_intent_tracker,
)

# Quick Wins: New optimization modules
from .model_router import ModelRouter, ModelTier, TaskComplexity, get_model_router
from .parallel_executor import (
    ParallelToolExecutor,
    ToolCall,
    ToolResult,
    execute_tools_parallel,
)
from .prompt_adapter import ContextType, PromptAdapter
from .prompt_cache_manager import (
    PromptCacheManager,
    SemanticResponseCache,
    get_prompt_cache_manager,
    get_semantic_cache,
)
from .prompt_compressor import (
    CompressionLevel,
    CompressionResult,
    PromptCompressor,
    compress_for_context,
    get_prompt_compressor,
)
from .requirement_extractor import (
    Requirement,
    RequirementExtractor,
    RequirementSet,
    extract_requirements,
)

# Task 2.3: Research Sub-Agent for wide research pattern
from .research_agent import LLMProtocol, ResearchSubAgent, SearchToolProtocol
from .smart_router import (
    RouteDecision,
    RoutingResult,
    SmartRouter,
    get_smart_router,
    try_bypass_llm,
)
from .stuck_detector import StuckDetector

# P1 Priority: Task Decomposition & LLM Call Reduction
from .task_decomposer import (
    DecompositionResult,
    Subtask,
    SubtaskType,
    TaskDecomposer,
    decompose_task,
    get_task_decomposer,
)
from .token_manager import TokenManager

__all__ = [
    "Agent",
    "CompressionLevel",
    "CompressionResult",
    "ContextType",
    "CriticAgent",
    "CriticResult",
    "DecompositionResult",
    "ErrorContext",
    "ErrorHandler",
    "ErrorType",
    "GroundingLevel",
    "GroundingResult",
    "GroundingValidator",
    "GuardrailsManager",
    "InputAnalysisResult",
    "InputGuardrails",
    "IntentTracker",
    "IntentTrackingResult",
    "LLMProtocol",
    "ModelRouter",
    "ModelTier",
    "OutputAnalysisResult",
    "OutputGuardrails",
    "ParallelToolExecutor",
    "PromptAdapter",
    "PromptCacheManager",
    "PromptCompressor",
    "Requirement",
    "RequirementExtractor",
    "RequirementSet",
    "ResearchSubAgent",
    "RouteDecision",
    "RoutingResult",
    "SearchToolProtocol",
    "SemanticResponseCache",
    "SmartRouter",
    "StuckDetector",
    "Subtask",
    "SubtaskType",
    "TaskComplexity",
    "TaskDecomposer",
    "TokenLimitExceededError",
    "TokenManager",
    "ToolCall",
    "ToolResult",
    "UserIntent",
    "compress_for_context",
    "decompose_task",
    "execute_tools_parallel",
    "extract_requirements",
    "get_grounding_validator",
    "get_guardrails_manager",
    "get_intent_tracker",
    "get_model_router",
    "get_prompt_cache_manager",
    "get_prompt_compressor",
    "get_semantic_cache",
    "get_smart_router",
    "get_task_decomposer",
    "try_bypass_llm",
    "validate_grounding",
]
