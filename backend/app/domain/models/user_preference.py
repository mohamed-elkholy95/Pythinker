"""
User Preference domain models.

This module defines models for learning and applying
user-specific preferences across sessions.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PreferenceCategory(str, Enum):
    """Categories of user preferences."""

    COMMUNICATION = "communication"  # How to communicate
    TOOL_USAGE = "tool_usage"  # Tool preferences
    OUTPUT_FORMAT = "output_format"  # Output format preferences
    RISK_TOLERANCE = "risk_tolerance"  # Risk tolerance level
    VERBOSITY = "verbosity"  # Level of detail
    INTERACTION_STYLE = "interaction_style"  # Interaction patterns


class CommunicationStyle(str, Enum):
    """User communication style preferences."""

    CONCISE = "concise"  # Brief, to the point
    DETAILED = "detailed"  # Thorough explanations
    TECHNICAL = "technical"  # Technical language
    SIMPLE = "simple"  # Simplified language


class RiskTolerance(str, Enum):
    """User risk tolerance levels."""

    CONSERVATIVE = "conservative"  # Minimal risk, more confirmations
    MODERATE = "moderate"  # Balanced approach
    AGGRESSIVE = "aggressive"  # Accept more risk for speed


class OutputFormat(str, Enum):
    """User output format preferences."""

    MARKDOWN = "markdown"
    PLAIN_TEXT = "plain_text"
    STRUCTURED = "structured"
    CODE_FOCUSED = "code_focused"


class UserPreference(BaseModel):
    """A single user preference setting."""

    preference_id: str = Field(default_factory=lambda: f"pref_{datetime.now().timestamp()}")
    category: PreferenceCategory
    name: str
    value: Any
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = "inferred"  # inferred, explicit, default
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    usage_count: int = 0

    def update_value(self, new_value: Any, confidence_boost: float = 0.1) -> None:
        """Update the preference value."""
        self.value = new_value
        self.confidence = min(1.0, self.confidence + confidence_boost)
        self.updated_at = datetime.now()
        self.usage_count += 1


class UserPreferenceProfile(BaseModel):
    """Complete preference profile for a user."""

    user_id: str
    preferences: list[UserPreference] = Field(default_factory=list)

    # Quick access preferences
    communication_style: CommunicationStyle = CommunicationStyle.DETAILED
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE
    output_format: OutputFormat = OutputFormat.MARKDOWN
    verbosity_level: int = Field(default=3, ge=1, le=5)  # 1-5 scale

    # Tool preferences
    preferred_tools: list[str] = Field(default_factory=list)
    avoided_tools: list[str] = Field(default_factory=list)

    # Interaction patterns
    prefers_confirmations: bool = True
    prefers_explanations: bool = True
    prefers_suggestions: bool = True

    created_at: datetime = Field(default_factory=datetime.now)
    last_active: datetime = Field(default_factory=datetime.now)

    def get_preference(
        self,
        category: PreferenceCategory,
        name: str,
    ) -> UserPreference | None:
        """Get a specific preference."""
        for pref in self.preferences:
            if pref.category == category and pref.name == name:
                return pref
        return None

    def set_preference(
        self,
        category: PreferenceCategory,
        name: str,
        value: Any,
        source: str = "explicit",
    ) -> UserPreference:
        """Set a preference value."""
        existing = self.get_preference(category, name)
        if existing:
            existing.update_value(value)
            existing.source = source
            return existing

        pref = UserPreference(
            category=category,
            name=name,
            value=value,
            source=source,
            confidence=0.8 if source == "explicit" else 0.5,
        )
        self.preferences.append(pref)
        return pref

    def infer_preference(
        self,
        category: PreferenceCategory,
        name: str,
        value: Any,
        confidence: float = 0.3,
    ) -> UserPreference:
        """Infer a preference from behavior."""
        existing = self.get_preference(category, name)
        if existing:
            # Only update if new inference is more confident
            if confidence > existing.confidence or existing.source == "inferred":
                existing.update_value(value, confidence_boost=confidence * 0.5)
            return existing

        pref = UserPreference(
            category=category,
            name=name,
            value=value,
            source="inferred",
            confidence=confidence,
        )
        self.preferences.append(pref)
        return pref

    def get_preferences_by_category(
        self,
        category: PreferenceCategory,
    ) -> list[UserPreference]:
        """Get all preferences in a category."""
        return [p for p in self.preferences if p.category == category]

    def get_high_confidence_preferences(
        self,
        min_confidence: float = 0.7,
    ) -> list[UserPreference]:
        """Get preferences with high confidence."""
        return [p for p in self.preferences if p.confidence >= min_confidence]

    def to_prompt_context(self) -> str:
        """Convert preferences to prompt context string."""
        lines = [
            f"Communication style: {self.communication_style.value}",
            f"Risk tolerance: {self.risk_tolerance.value}",
            f"Verbosity level: {self.verbosity_level}/5",
        ]

        if self.preferred_tools:
            lines.append(f"Preferred tools: {', '.join(self.preferred_tools[:5])}")

        if self.prefers_confirmations:
            lines.append("User prefers confirmations before significant actions")

        if not self.prefers_explanations:
            lines.append("User prefers minimal explanations")

        return "\n".join(lines)


class PreferenceInferenceResult(BaseModel):
    """Result of inferring preferences from behavior."""

    inferred_preferences: list[UserPreference] = Field(default_factory=list)
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
