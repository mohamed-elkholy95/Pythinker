"""
Agent Learning module for adaptive behavior.

Provides learning capabilities for agents including:
- Task pattern learning
- Prompt optimization
- Knowledge transfer
"""

from app.domain.services.agents.learning.knowledge_transfer import (
    KnowledgeTransfer,
    TransferableKnowledge,
    get_knowledge_transfer,
)
from app.domain.services.agents.learning.pattern_learner import (
    PatternLearner,
    TaskPattern,
    get_pattern_learner,
)
from app.domain.services.agents.learning.prompt_optimizer import (
    PromptOptimizer,
    PromptVariant,
    get_prompt_optimizer,
)

__all__ = [
    "KnowledgeTransfer",
    "PatternLearner",
    "PromptOptimizer",
    "PromptVariant",
    "TaskPattern",
    "TransferableKnowledge",
    "get_knowledge_transfer",
    "get_pattern_learner",
    "get_prompt_optimizer",
]
