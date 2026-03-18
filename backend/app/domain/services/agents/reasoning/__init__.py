"""
Reasoning module for enhanced AI agent cognition.

This module provides structured reasoning capabilities including:
- Chain-of-Thought reasoning engine
- Self-consistency validation
- Confidence calibration
- Meta-cognitive awareness
- Tree-of-Thoughts exploration
"""

from app.domain.services.agents.reasoning.confidence import (
    ConfidenceCalibrator,
    ConfidenceLevel,
)
from app.domain.services.agents.reasoning.engine import ReasoningEngine
from app.domain.services.agents.reasoning.meta_cognition import (
    KnowledgeAssessment,
    MetaCognitionModule,
)
from app.domain.services.agents.reasoning.self_consistency import (
    ConsensusResult,
    SelfConsistencyChecker,
)
from app.domain.services.agents.reasoning.thought_chain import ThoughtChainBuilder

__all__ = [
    "ConfidenceCalibrator",
    "ConfidenceLevel",
    "ConsensusResult",
    "KnowledgeAssessment",
    "MetaCognitionModule",
    "ReasoningEngine",
    "SelfConsistencyChecker",
    "ThoughtChainBuilder",
]
