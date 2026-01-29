from ...models.agent import Agent
from .error_handler import ErrorHandler, ErrorType, ErrorContext, TokenLimitExceeded
from .stuck_detector import StuckDetector
from .token_manager import TokenManager
from .prompt_adapter import PromptAdapter, ContextType

# Quick Wins: New optimization modules
from .model_router import ModelRouter, get_model_router, TaskComplexity, ModelTier
from .requirement_extractor import (
    RequirementExtractor,
    extract_requirements,
    RequirementSet,
    Requirement,
)
from .parallel_executor import (
    ParallelToolExecutor,
    execute_tools_parallel,
    ToolCall,
    ToolResult,
)
from .prompt_cache_manager import (
    PromptCacheManager,
    get_prompt_cache_manager,
    SemanticResponseCache,
    get_semantic_cache,
)
# P0 Priority: Hallucination Prevention & Prompt Adherence
from .grounding_validator import (
    GroundingValidator,
    get_grounding_validator,
    validate_grounding,
    GroundingResult,
    GroundingLevel,
)
from .guardrails import (
    GuardrailsManager,
    get_guardrails_manager,
    InputGuardrails,
    OutputGuardrails,
    InputAnalysisResult,
    OutputAnalysisResult,
)
from .intent_tracker import (
    IntentTracker,
    get_intent_tracker,
    UserIntent,
    IntentTrackingResult,
)
# P1 Priority: Task Decomposition & LLM Call Reduction
from .task_decomposer import (
    TaskDecomposer,
    get_task_decomposer,
    decompose_task,
    DecompositionResult,
    Subtask,
    SubtaskType,
)
from .smart_router import (
    SmartRouter,
    get_smart_router,
    try_bypass_llm,
    RoutingResult,
    RouteDecision,
)
from .prompt_compressor import (
    PromptCompressor,
    get_prompt_compressor,
    compress_for_context,
    CompressionResult,
    CompressionLevel,
)

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
