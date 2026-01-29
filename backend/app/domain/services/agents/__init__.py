from ...models.agent import Agent
from .error_handler import ErrorContext, ErrorHandler, ErrorType, TokenLimitExceeded

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
    'Agent',
    'ErrorHandler',
    'ErrorType',
    'ErrorContext',
    'TokenLimitExceeded',
    'StuckDetector',
    'TokenManager',
    'PromptAdapter',
    'ContextType',
    # Quick Wins: Model Routing
    'ModelRouter',
    'get_model_router',
    'TaskComplexity',
    'ModelTier',
    # Quick Wins: Requirement Extraction
    'RequirementExtractor',
    'extract_requirements',
    'RequirementSet',
    'Requirement',
    # Quick Wins: Parallel Execution
    'ParallelToolExecutor',
    'execute_tools_parallel',
    'ToolCall',
    'ToolResult',
    # Quick Wins: Semantic Caching
    'PromptCacheManager',
    'get_prompt_cache_manager',
    'SemanticResponseCache',
    'get_semantic_cache',
    # P0: Grounding Validation
    'GroundingValidator',
    'get_grounding_validator',
    'validate_grounding',
    'GroundingResult',
    'GroundingLevel',
    # P0: Input/Output Guardrails
    'GuardrailsManager',
    'get_guardrails_manager',
    'InputGuardrails',
    'OutputGuardrails',
    'InputAnalysisResult',
    'OutputAnalysisResult',
    # P0: Intent Tracking
    'IntentTracker',
    'get_intent_tracker',
    'UserIntent',
    'IntentTrackingResult',
    # P1: Task Decomposition
    'TaskDecomposer',
    'get_task_decomposer',
    'decompose_task',
    'DecompositionResult',
    'Subtask',
    'SubtaskType',
    # P1: Smart Routing (LLM Call Reduction)
    'SmartRouter',
    'get_smart_router',
    'try_bypass_llm',
    'RoutingResult',
    'RouteDecision',
    # P1: Prompt Compression
    'PromptCompressor',
    'get_prompt_compressor',
    'compress_for_context',
    'CompressionResult',
    'CompressionLevel',
]
