"""User Intent Tracker for Prompt Adherence

Tracks user intent throughout agent execution to ensure:
1. All explicit user requirements are addressed
2. Agent doesn't add unrequested features (scope creep)
3. Agent doesn't skip requested features (scope drift)
4. Final output matches user expectations

Research shows agents commonly drift from user intent during
multi-step execution. This module provides continuous monitoring
and correction guidance.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    """Types of user intent detected."""
    ACTION = "action"           # Do something
    QUESTION = "question"       # Answer something
    CREATION = "creation"       # Create something
    MODIFICATION = "modification"  # Change something
    DELETION = "deletion"       # Remove something
    ANALYSIS = "analysis"       # Analyze/research something
    COMPARISON = "comparison"   # Compare things


class DriftType(str, Enum):
    """Types of scope drift detected."""
    SCOPE_CREEP = "scope_creep"     # Adding unrequested work
    SCOPE_REDUCTION = "scope_reduction"  # Skipping requested work
    TOPIC_DRIFT = "topic_drift"     # Going off-topic
    GOLD_PLATING = "gold_plating"   # Unnecessary enhancements


@dataclass
class UserIntent:
    """Represents the user's primary intent."""
    intent_type: IntentType
    primary_goal: str
    explicit_requirements: List[str]
    implicit_requirements: List[str]
    constraints: List[str]  # Things user said NOT to do
    preferences: Dict[str, str]  # Format, style, etc.
    original_prompt: str
    extracted_at: datetime = field(default_factory=datetime.now)


@dataclass
class DriftAlert:
    """Alert for detected scope drift."""
    drift_type: DriftType
    description: str
    severity: float  # 0.0 to 1.0
    evidence: str  # What triggered this alert
    correction: str  # Suggested correction


@dataclass
class IntentTrackingResult:
    """Result of intent tracking check."""
    coverage_percent: float  # How many requirements addressed
    unaddressed_requirements: List[str]
    addressed_requirements: List[str]
    drift_alerts: List[DriftAlert]
    on_track: bool
    guidance: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def needs_correction(self) -> bool:
        """Check if execution needs correction."""
        return not self.on_track or len(self.drift_alerts) > 0


class IntentTracker:
    """Tracks user intent throughout agent execution.

    Usage:
        tracker = IntentTracker()

        # At planning time - extract intent
        intent = tracker.extract_intent("Create a Python script that reads CSV...")

        # During execution - track progress
        tracker.mark_addressed("Read CSV file", step_id="step-1")

        # At checkpoints - verify alignment
        result = tracker.check_alignment(current_work_summary)

        if result.needs_correction:
            print(result.guidance)
    """

    # Action verbs for intent type detection
    INTENT_PATTERNS = {
        IntentType.CREATION: [
            r'\b(create|make|build|generate|write|develop|design|implement)\b',
        ],
        IntentType.MODIFICATION: [
            r'\b(update|modify|change|edit|revise|fix|improve|enhance|refactor)\b',
        ],
        IntentType.DELETION: [
            r'\b(delete|remove|drop|clear|clean|purge)\b',
        ],
        IntentType.ANALYSIS: [
            r'\b(analyze|research|investigate|study|examine|review|assess|evaluate)\b',
        ],
        IntentType.COMPARISON: [
            r'\b(compare|contrast|versus|vs|differ|between)\b',
        ],
        IntentType.QUESTION: [
            r'^(what|who|when|where|why|how|which|is|are|can|does|do)\b',
            r'\?\s*$',
        ],
    }

    # Constraint patterns (things NOT to do)
    CONSTRAINT_PATTERNS = [
        r"don'?t\s+(\w+\s+){1,5}",
        r'do\s+not\s+(\w+\s+){1,5}',
        r'avoid\s+(\w+\s+){1,5}',
        r'without\s+(\w+\s+){1,5}',
        r'no\s+(\w+)',
        r'never\s+(\w+\s+){1,5}',
    ]

    # Preference patterns
    PREFERENCE_PATTERNS = {
        'format': r'(?:in|as|using)\s+(markdown|json|csv|html|pdf|text)',
        'language': r'(?:in|using)\s+(python|javascript|typescript|java|go|rust)',
        'style': r'(?:in\s+a?\s*)(professional|casual|formal|simple|detailed)\s+(?:style|tone|manner)',
    }

    def __init__(self):
        """Initialize the intent tracker."""
        self._current_intent: Optional[UserIntent] = None
        self._addressed_requirements: Set[str] = set()
        self._work_history: List[Dict[str, Any]] = []

        # Compile patterns
        self._intent_re = {
            k: [re.compile(p, re.IGNORECASE) for p in patterns]
            for k, patterns in self.INTENT_PATTERNS.items()
        }
        self._constraint_re = [re.compile(p, re.IGNORECASE) for p in self.CONSTRAINT_PATTERNS]
        self._preference_re = {
            k: re.compile(p, re.IGNORECASE)
            for k, p in self.PREFERENCE_PATTERNS.items()
        }

    def extract_intent(self, user_prompt: str) -> UserIntent:
        """Extract user intent from the prompt.

        Args:
            user_prompt: The user's original message

        Returns:
            UserIntent with extracted information
        """
        if not user_prompt:
            return UserIntent(
                intent_type=IntentType.ACTION,
                primary_goal="",
                explicit_requirements=[],
                implicit_requirements=[],
                constraints=[],
                preferences={},
                original_prompt="",
            )

        # Detect intent type
        intent_type = self._detect_intent_type(user_prompt)

        # Extract primary goal (first sentence or main clause)
        primary_goal = self._extract_primary_goal(user_prompt)

        # Extract explicit requirements (numbered lists, bullets)
        explicit_reqs = self._extract_explicit_requirements(user_prompt)

        # Extract implicit requirements (mentioned but not listed)
        implicit_reqs = self._extract_implicit_requirements(user_prompt, explicit_reqs)

        # Extract constraints (what NOT to do)
        constraints = self._extract_constraints(user_prompt)

        # Extract preferences
        preferences = self._extract_preferences(user_prompt)

        intent = UserIntent(
            intent_type=intent_type,
            primary_goal=primary_goal,
            explicit_requirements=explicit_reqs,
            implicit_requirements=implicit_reqs,
            constraints=constraints,
            preferences=preferences,
            original_prompt=user_prompt,
        )

        self._current_intent = intent
        self._addressed_requirements.clear()
        self._work_history.clear()

        logger.info(
            f"Extracted intent: type={intent_type.value}, "
            f"requirements={len(explicit_reqs)}, constraints={len(constraints)}"
        )

        return intent

    def _detect_intent_type(self, text: str) -> IntentType:
        """Detect the primary intent type."""
        text_lower = text.lower()

        for intent_type, patterns in self._intent_re.items():
            for pattern in patterns:
                if pattern.search(text_lower):
                    return intent_type

        return IntentType.ACTION  # Default

    def _extract_primary_goal(self, text: str) -> str:
        """Extract the primary goal from the prompt."""
        # Get first sentence or up to first newline
        first_part = text.split('\n')[0].strip()

        # If it's too long, truncate at sentence boundary
        if len(first_part) > 200:
            match = re.match(r'^[^.!?]+[.!?]', first_part)
            if match:
                return match.group(0).strip()
            return first_part[:200] + "..."

        return first_part

    def _extract_explicit_requirements(self, text: str) -> List[str]:
        """Extract explicitly listed requirements."""
        requirements = []

        # Numbered items (1. Item, 1) Item)
        numbered = re.findall(r'(?:^|\n)\s*\d+[.\)]\s*(.+?)(?=\n|$)', text)
        requirements.extend([r.strip() for r in numbered if r.strip()])

        # Bullet items (- Item, * Item)
        bullets = re.findall(r'(?:^|\n)\s*[-*]\s*(.+?)(?=\n|$)', text)
        requirements.extend([r.strip() for r in bullets if r.strip()])

        return requirements

    def _extract_implicit_requirements(
        self,
        text: str,
        explicit: List[str],
    ) -> List[str]:
        """Extract implicitly mentioned requirements."""
        implicit = []
        explicit_lower = {e.lower() for e in explicit}

        # Look for "should", "must", "need to" phrases
        should_patterns = [
            r'(?:should|must|needs?\s+to|has?\s+to|requires?)\s+(.+?)(?:[.,]|$)',
        ]

        for pattern in should_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if match.lower().strip() not in explicit_lower:
                    implicit.append(match.strip())

        return implicit[:10]  # Limit

    def _extract_constraints(self, text: str) -> List[str]:
        """Extract constraints (things NOT to do)."""
        constraints = []

        for pattern in self._constraint_re:
            matches = pattern.findall(text)
            constraints.extend([m.strip() for m in matches if m.strip()])

        return constraints

    def _extract_preferences(self, text: str) -> Dict[str, str]:
        """Extract user preferences (format, style, etc.)."""
        preferences = {}

        for pref_type, pattern in self._preference_re.items():
            match = pattern.search(text)
            if match:
                preferences[pref_type] = match.group(1).lower()

        return preferences

    def mark_addressed(
        self,
        requirement: str,
        step_id: str,
        work_summary: Optional[str] = None,
    ) -> None:
        """Mark a requirement as addressed.

        Args:
            requirement: The requirement that was addressed
            step_id: ID of the step that addressed it
            work_summary: Optional summary of work done
        """
        self._addressed_requirements.add(requirement.lower())

        self._work_history.append({
            "step_id": step_id,
            "requirement": requirement,
            "summary": work_summary,
            "timestamp": datetime.now(),
        })

        logger.debug(f"Marked requirement addressed: {requirement[:50]}... by {step_id}")

    def check_alignment(
        self,
        current_work: str,
        plan_steps: Optional[List[str]] = None,
    ) -> IntentTrackingResult:
        """Check if current work aligns with user intent.

        Args:
            current_work: Summary of current work being done
            plan_steps: Optional list of planned step descriptions

        Returns:
            IntentTrackingResult with alignment assessment
        """
        if not self._current_intent:
            return IntentTrackingResult(
                coverage_percent=100.0,
                unaddressed_requirements=[],
                addressed_requirements=[],
                drift_alerts=[],
                on_track=True,
            )

        # Calculate requirement coverage
        all_requirements = (
            self._current_intent.explicit_requirements +
            self._current_intent.implicit_requirements
        )

        addressed = []
        unaddressed = []

        for req in all_requirements:
            if req.lower() in self._addressed_requirements:
                addressed.append(req)
            else:
                # Check if current work mentions this requirement
                if self._text_similarity(req, current_work) > 0.3:
                    addressed.append(req)
                    self._addressed_requirements.add(req.lower())
                else:
                    unaddressed.append(req)

        coverage = len(addressed) / len(all_requirements) if all_requirements else 100.0

        # Check for drift
        drift_alerts = self._detect_drift(current_work, plan_steps)

        # Determine if on track
        on_track = coverage >= 0.5 and len(drift_alerts) == 0

        # Generate guidance if needed
        guidance = None
        if not on_track:
            guidance = self._generate_guidance(unaddressed, drift_alerts)

        return IntentTrackingResult(
            coverage_percent=coverage * 100,
            unaddressed_requirements=unaddressed,
            addressed_requirements=addressed,
            drift_alerts=drift_alerts,
            on_track=on_track,
            guidance=guidance,
        )

    def _detect_drift(
        self,
        current_work: str,
        plan_steps: Optional[List[str]],
    ) -> List[DriftAlert]:
        """Detect scope drift in current work."""
        alerts = []

        if not self._current_intent:
            return alerts

        current_lower = current_work.lower()
        intent = self._current_intent

        # Check for scope creep (adding unrequested features)
        scope_creep_indicators = [
            'also added', 'bonus feature', 'extra functionality',
            'while I was at it', 'additionally implemented',
            'as a bonus', 'I also', 'went ahead and',
        ]

        for indicator in scope_creep_indicators:
            if indicator in current_lower:
                alerts.append(DriftAlert(
                    drift_type=DriftType.SCOPE_CREEP,
                    description="Agent may be adding unrequested features",
                    severity=0.4,
                    evidence=indicator,
                    correction="Focus only on explicitly requested features",
                ))
                break

        # Check for constraint violations
        for constraint in intent.constraints:
            if constraint.lower() in current_lower:
                alerts.append(DriftAlert(
                    drift_type=DriftType.SCOPE_CREEP,
                    description=f"Work may violate constraint: {constraint}",
                    severity=0.7,
                    evidence=constraint,
                    correction=f"Avoid: {constraint}",
                ))

        # Check for topic drift (current work not related to goal)
        goal_similarity = self._text_similarity(intent.primary_goal, current_work)
        if goal_similarity < 0.15:
            alerts.append(DriftAlert(
                drift_type=DriftType.TOPIC_DRIFT,
                description="Current work may be off-topic from original goal",
                severity=0.5,
                evidence=f"Low similarity ({goal_similarity:.2f}) to goal",
                correction=f"Return focus to: {intent.primary_goal[:100]}",
            ))

        return alerts

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity."""
        if not text1 or not text2:
            return 0.0

        # Simple word overlap (Jaccard)
        words1 = set(re.findall(r'\b\w+\b', text1.lower()))
        words2 = set(re.findall(r'\b\w+\b', text2.lower()))

        # Remove stop words
        stop_words = {'the', 'a', 'an', 'is', 'are', 'to', 'for', 'of', 'and', 'in', 'on', 'with'}
        words1 -= stop_words
        words2 -= stop_words

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _generate_guidance(
        self,
        unaddressed: List[str],
        alerts: List[DriftAlert],
    ) -> str:
        """Generate correction guidance."""
        lines = ["## Alignment Correction Needed"]

        if unaddressed:
            lines.append("\n**Unaddressed Requirements:**")
            for req in unaddressed[:5]:
                lines.append(f"- {req}")

        if alerts:
            lines.append("\n**Issues Detected:**")
            for alert in alerts:
                lines.append(f"- [{alert.drift_type.value}] {alert.description}")
                lines.append(f"  Correction: {alert.correction}")

        return "\n".join(lines)

    def get_summary(self) -> Dict[str, Any]:
        """Get tracking summary."""
        if not self._current_intent:
            return {"status": "no_intent_tracked"}

        all_reqs = (
            self._current_intent.explicit_requirements +
            self._current_intent.implicit_requirements
        )

        return {
            "intent_type": self._current_intent.intent_type.value,
            "primary_goal": self._current_intent.primary_goal[:100],
            "total_requirements": len(all_reqs),
            "addressed_count": len(self._addressed_requirements),
            "constraints_count": len(self._current_intent.constraints),
            "work_steps_tracked": len(self._work_history),
        }

    def reset(self) -> None:
        """Reset the tracker for a new task."""
        self._current_intent = None
        self._addressed_requirements.clear()
        self._work_history.clear()


# Singleton instance
_tracker: Optional[IntentTracker] = None


def get_intent_tracker() -> IntentTracker:
    """Get the global intent tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = IntentTracker()
    return _tracker
