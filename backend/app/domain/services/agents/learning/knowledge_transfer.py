"""
Cross-Session Knowledge Transfer module.

This module enables transferring learned knowledge between
sessions for continuous improvement.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class KnowledgeType(str, Enum):
    """Types of transferable knowledge."""

    PROJECT_CONTEXT = "project_context"  # Project-specific knowledge
    SUCCESSFUL_APPROACH = "successful_approach"  # Approaches that worked
    ERROR_PATTERN = "error_pattern"  # Errors to avoid
    USER_PREFERENCE = "user_preference"  # User-specific preferences
    TOOL_INSIGHT = "tool_insight"  # Tool usage insights
    DOMAIN_KNOWLEDGE = "domain_knowledge"  # Domain-specific knowledge


@dataclass
class TransferableKnowledge:
    """A piece of transferable knowledge."""

    knowledge_id: str
    knowledge_type: KnowledgeType
    content: str
    source_session_id: str
    confidence: float = 0.5
    relevance_score: float = 0.5
    usage_count: int = 0
    success_when_used: int = 0
    context_tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime | None = None
    expires_at: datetime | None = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate when this knowledge is used."""
        if self.usage_count == 0:
            return 0.5
        return self.success_when_used / self.usage_count

    def mark_used(self, success: bool) -> None:
        """Mark the knowledge as used."""
        self.usage_count += 1
        self.last_used = datetime.now()
        if success:
            self.success_when_used += 1

    def is_expired(self) -> bool:
        """Check if the knowledge has expired."""
        if self.expires_at:
            return datetime.now() > self.expires_at
        return False


@dataclass
class TransferContext:
    """Context for knowledge transfer."""

    session_id: str
    user_id: str | None = None
    project_id: str | None = None
    task_description: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class TransferResult:
    """Result of a knowledge transfer operation."""

    transferred_count: int
    applicable_count: int
    knowledge_items: list[TransferableKnowledge] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class KnowledgeTransfer:
    """Manager for cross-session knowledge transfer.

    Enables knowledge from previous sessions to be applied
    to new sessions for continuous improvement.
    """

    # Minimum confidence for knowledge to be transferred
    MIN_TRANSFER_CONFIDENCE = 0.5
    # Maximum knowledge items to transfer at once
    MAX_TRANSFER_ITEMS = 10
    # Weight for recency in relevance calculation
    RECENCY_WEIGHT = 0.3

    def __init__(self) -> None:
        """Initialize the knowledge transfer manager."""
        self._knowledge_store: dict[str, TransferableKnowledge] = {}
        self._session_knowledge: dict[str, list[str]] = {}  # session_id -> knowledge_ids
        self._user_knowledge: dict[str, list[str]] = {}  # user_id -> knowledge_ids
        self._project_knowledge: dict[str, list[str]] = {}  # project_id -> knowledge_ids

    def store_knowledge(
        self,
        knowledge_type: KnowledgeType,
        content: str,
        source_session_id: str,
        user_id: str | None = None,
        project_id: str | None = None,
        context_tags: list[str] | None = None,
        confidence: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> TransferableKnowledge:
        """Store a piece of knowledge for future transfer.

        Args:
            knowledge_type: Type of knowledge
            content: The knowledge content
            source_session_id: Session where knowledge was learned
            user_id: Optional user ID
            project_id: Optional project ID
            context_tags: Optional context tags
            confidence: Confidence in the knowledge
            metadata: Optional metadata

        Returns:
            The stored knowledge item
        """
        knowledge = TransferableKnowledge(
            knowledge_id=f"k_{len(self._knowledge_store)}_{datetime.now().timestamp()}",
            knowledge_type=knowledge_type,
            content=content,
            source_session_id=source_session_id,
            confidence=confidence,
            context_tags=context_tags or [],
            metadata=metadata or {},
        )

        self._knowledge_store[knowledge.knowledge_id] = knowledge

        # Index by session
        if source_session_id not in self._session_knowledge:
            self._session_knowledge[source_session_id] = []
        self._session_knowledge[source_session_id].append(knowledge.knowledge_id)

        # Index by user
        if user_id:
            if user_id not in self._user_knowledge:
                self._user_knowledge[user_id] = []
            self._user_knowledge[user_id].append(knowledge.knowledge_id)

        # Index by project
        if project_id:
            if project_id not in self._project_knowledge:
                self._project_knowledge[project_id] = []
            self._project_knowledge[project_id].append(knowledge.knowledge_id)

        logger.info(f"Stored knowledge: {knowledge.knowledge_id} ({knowledge_type.value})")

        return knowledge

    def transfer_to_session(
        self,
        target_context: TransferContext,
        knowledge_types: list[KnowledgeType] | None = None,
    ) -> TransferResult:
        """Transfer relevant knowledge to a new session.

        Args:
            target_context: Context of the target session
            knowledge_types: Optional filter for knowledge types

        Returns:
            Transfer result with applicable knowledge
        """
        candidates = self._find_candidates(target_context, knowledge_types)

        # Score and rank candidates
        scored_candidates = []
        for knowledge in candidates:
            score = self._calculate_relevance(knowledge, target_context)
            scored_candidates.append((score, knowledge))

        # Sort by score and take top items
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = scored_candidates[: self.MAX_TRANSFER_ITEMS]

        # Filter by confidence threshold
        applicable = [k for score, k in top_candidates if k.confidence >= self.MIN_TRANSFER_CONFIDENCE]

        # Generate recommendations from knowledge
        recommendations = self._generate_recommendations(applicable)

        logger.info(f"Transferred {len(applicable)} knowledge items to session {target_context.session_id}")

        return TransferResult(
            transferred_count=len(applicable),
            applicable_count=len(candidates),
            knowledge_items=applicable,
            recommendations=recommendations,
        )

    def get_knowledge_for_task(
        self,
        task_description: str,
        knowledge_types: list[KnowledgeType] | None = None,
        limit: int = 5,
    ) -> list[TransferableKnowledge]:
        """Get relevant knowledge for a specific task.

        Args:
            task_description: Description of the task
            knowledge_types: Optional filter for types
            limit: Maximum items to return

        Returns:
            List of relevant knowledge items
        """
        candidates = []

        for knowledge in self._knowledge_store.values():
            if knowledge.is_expired():
                continue

            if knowledge_types and knowledge.knowledge_type not in knowledge_types:
                continue

            # Calculate relevance to task
            relevance = self._calculate_task_relevance(knowledge, task_description)
            if relevance > 0.3:
                candidates.append((relevance, knowledge))

        # Sort by relevance
        candidates.sort(key=lambda x: x[0], reverse=True)

        return [k for _, k in candidates[:limit]]

    def mark_knowledge_used(
        self,
        knowledge_id: str,
        success: bool,
    ) -> None:
        """Mark knowledge as used and record outcome.

        Args:
            knowledge_id: ID of the knowledge used
            success: Whether using it was successful
        """
        if knowledge_id in self._knowledge_store:
            self._knowledge_store[knowledge_id].mark_used(success)

    def get_user_knowledge(
        self,
        user_id: str,
        knowledge_types: list[KnowledgeType] | None = None,
    ) -> list[TransferableKnowledge]:
        """Get all knowledge for a user.

        Args:
            user_id: User ID
            knowledge_types: Optional filter

        Returns:
            List of knowledge items
        """
        if user_id not in self._user_knowledge:
            return []

        items = []
        for kid in self._user_knowledge[user_id]:
            knowledge = self._knowledge_store.get(kid)
            if (
                knowledge
                and not knowledge.is_expired()
                and (not knowledge_types or knowledge.knowledge_type in knowledge_types)
            ):
                items.append(knowledge)

        return items

    def get_project_knowledge(
        self,
        project_id: str,
        knowledge_types: list[KnowledgeType] | None = None,
    ) -> list[TransferableKnowledge]:
        """Get all knowledge for a project.

        Args:
            project_id: Project ID
            knowledge_types: Optional filter

        Returns:
            List of knowledge items
        """
        if project_id not in self._project_knowledge:
            return []

        items = []
        for kid in self._project_knowledge[project_id]:
            knowledge = self._knowledge_store.get(kid)
            if (
                knowledge
                and not knowledge.is_expired()
                and (not knowledge_types or knowledge.knowledge_type in knowledge_types)
            ):
                items.append(knowledge)

        return items

    def cleanup_expired(self) -> int:
        """Remove expired knowledge items.

        Returns:
            Number of items removed
        """
        expired = [kid for kid, k in self._knowledge_store.items() if k.is_expired()]

        for kid in expired:
            del self._knowledge_store[kid]

        return len(expired)

    def get_statistics(self) -> dict[str, Any]:
        """Get knowledge transfer statistics."""
        by_type: dict[str, int] = {}
        total_usage = 0
        total_success = 0

        for knowledge in self._knowledge_store.values():
            type_name = knowledge.knowledge_type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1
            total_usage += knowledge.usage_count
            total_success += knowledge.success_when_used

        return {
            "total_knowledge": len(self._knowledge_store),
            "by_type": by_type,
            "total_sessions": len(self._session_knowledge),
            "total_users": len(self._user_knowledge),
            "total_projects": len(self._project_knowledge),
            "total_usage": total_usage,
            "overall_success_rate": total_success / total_usage if total_usage > 0 else 0,
        }

    def _find_candidates(
        self,
        context: TransferContext,
        knowledge_types: list[KnowledgeType] | None,
    ) -> list[TransferableKnowledge]:
        """Find candidate knowledge items for transfer."""
        candidates = []

        # Get user knowledge
        if context.user_id and context.user_id in self._user_knowledge:
            for kid in self._user_knowledge[context.user_id]:
                knowledge = self._knowledge_store.get(kid)
                if knowledge and not knowledge.is_expired():
                    candidates.append(knowledge)

        # Get project knowledge
        if context.project_id and context.project_id in self._project_knowledge:
            for kid in self._project_knowledge[context.project_id]:
                knowledge = self._knowledge_store.get(kid)
                if knowledge and not knowledge.is_expired() and knowledge not in candidates:
                    candidates.append(knowledge)

        # Filter by type
        if knowledge_types:
            candidates = [k for k in candidates if k.knowledge_type in knowledge_types]

        return candidates

    def _calculate_relevance(
        self,
        knowledge: TransferableKnowledge,
        context: TransferContext,
    ) -> float:
        """Calculate relevance score for knowledge."""
        score = knowledge.confidence

        # Tag overlap
        if context.tags and knowledge.context_tags:
            overlap = len(set(context.tags) & set(knowledge.context_tags))
            score += overlap * 0.1

        # Task description similarity
        if context.task_description:
            task_words = set(context.task_description.lower().split())
            content_words = set(knowledge.content.lower().split())
            word_overlap = len(task_words & content_words)
            score += min(word_overlap * 0.05, 0.3)

        # Recency boost
        age_hours = (datetime.now() - knowledge.created_at).total_seconds() / 3600
        recency = max(0, 1 - (age_hours / (24 * 30)))  # Decay over 30 days
        score += recency * self.RECENCY_WEIGHT

        # Success rate boost
        score += knowledge.success_rate * 0.2

        return min(1.0, score)

    def _calculate_task_relevance(
        self,
        knowledge: TransferableKnowledge,
        task_description: str,
    ) -> float:
        """Calculate relevance of knowledge to a task."""
        task_words = set(task_description.lower().split())
        content_words = set(knowledge.content.lower().split())
        tag_words = {tag.lower() for tag in knowledge.context_tags}

        # Word overlap
        overlap = len(task_words & (content_words | tag_words))

        if not task_words:
            return 0.0

        return min(1.0, overlap / len(task_words) + knowledge.confidence * 0.3)

    def _generate_recommendations(
        self,
        knowledge_items: list[TransferableKnowledge],
    ) -> list[str]:
        """Generate recommendations from knowledge items."""
        recommendations = []

        for knowledge in knowledge_items[:5]:
            if knowledge.knowledge_type == KnowledgeType.SUCCESSFUL_APPROACH:
                recommendations.append(f"Try: {knowledge.content}")
            elif knowledge.knowledge_type == KnowledgeType.ERROR_PATTERN:
                recommendations.append(f"Avoid: {knowledge.content}")
            elif knowledge.knowledge_type == KnowledgeType.TOOL_INSIGHT:
                recommendations.append(f"Tool tip: {knowledge.content}")

        return recommendations


# Global knowledge transfer instance
_transfer: KnowledgeTransfer | None = None


def get_knowledge_transfer() -> KnowledgeTransfer:
    """Get or create the global knowledge transfer manager."""
    global _transfer
    if _transfer is None:
        _transfer = KnowledgeTransfer()
    return _transfer


def reset_knowledge_transfer() -> None:
    """Reset the global knowledge transfer manager."""
    global _transfer
    _transfer = None
