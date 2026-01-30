"""
Agent Collaboration module for multi-agent problem-solving patterns.

Provides patterns for agents to work together on complex tasks.
"""

from app.domain.services.agents.collaboration.patterns import (
    AssemblyLinePattern,
    CollaborationPattern,
    DebatePattern,
    MentorStudentPattern,
    SwarmPattern,
    get_pattern_executor,
)

__all__ = [
    "AssemblyLinePattern",
    "CollaborationPattern",
    "DebatePattern",
    "MentorStudentPattern",
    "SwarmPattern",
    "get_pattern_executor",
]
