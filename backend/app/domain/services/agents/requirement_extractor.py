"""User Requirement Extractor

Parses user prompts to extract explicit requirements, ensuring
the agent addresses all user-specified needs and doesn't drift
from the original request.

Research shows agents commonly:
1. Add features the user didn't request
2. Skip features the user explicitly requested
3. Lose track of requirements during multi-step execution

This module helps maintain focus on user intent throughout execution.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RequirementPriority(str, Enum):
    """Priority levels for requirements."""
    MUST_HAVE = "must_have"      # Explicit requirements
    SHOULD_HAVE = "should_have"  # Implied or suggested
    NICE_TO_HAVE = "nice_to_have"  # Optional enhancements


@dataclass
class Requirement:
    """A single extracted requirement."""
    id: str
    description: str
    priority: RequirementPriority
    source_text: str  # Original text this was extracted from
    addressed: bool = False
    addressed_by_step: str | None = None

    def mark_addressed(self, step_id: str) -> None:
        """Mark this requirement as addressed by a step."""
        self.addressed = True
        self.addressed_by_step = step_id


@dataclass
class RequirementSet:
    """Collection of requirements extracted from a user prompt."""
    requirements: list[Requirement] = field(default_factory=list)
    original_prompt: str = ""

    @property
    def must_haves(self) -> list[Requirement]:
        """Get all must-have requirements."""
        return [r for r in self.requirements if r.priority == RequirementPriority.MUST_HAVE]

    @property
    def unaddressed(self) -> list[Requirement]:
        """Get all unaddressed requirements."""
        return [r for r in self.requirements if not r.addressed]

    @property
    def coverage_percent(self) -> float:
        """Calculate requirement coverage percentage."""
        if not self.requirements:
            return 100.0
        addressed = sum(1 for r in self.requirements if r.addressed)
        return (addressed / len(self.requirements)) * 100

    @property
    def must_have_coverage_percent(self) -> float:
        """Calculate must-have requirement coverage."""
        must_haves = self.must_haves
        if not must_haves:
            return 100.0
        addressed = sum(1 for r in must_haves if r.addressed)
        return (addressed / len(must_haves)) * 100

    def get_summary(self) -> str:
        """Get a summary of requirements for injection into prompts."""
        if not self.requirements:
            return ""

        lines = ["## User Requirements Checklist"]
        for req in self.requirements:
            status = "[x]" if req.addressed else "[ ]"
            priority_marker = "**" if req.priority == RequirementPriority.MUST_HAVE else ""
            lines.append(f"- {status} {priority_marker}{req.description}{priority_marker}")

        return "\n".join(lines)

    def get_unaddressed_reminder(self) -> str | None:
        """Get a reminder about unaddressed requirements."""
        unaddressed = self.unaddressed
        if not unaddressed:
            return None

        must_haves = [r for r in unaddressed if r.priority == RequirementPriority.MUST_HAVE]

        if must_haves:
            items = "\n".join(f"- {r.description}" for r in must_haves[:5])
            return f"REMINDER: The following user requirements have NOT been addressed:\n{items}"

        return None


class RequirementExtractor:
    """Extracts requirements from user prompts.

    Usage:
        extractor = RequirementExtractor()
        req_set = extractor.extract("Create a Python script that:
            1. Reads a CSV file
            2. Filters rows where age > 18
            3. Outputs to JSON format")

        # req_set.requirements contains 3 MUST_HAVE requirements
    """

    # Patterns for numbered lists (1. Item, 1) Item, etc.)
    NUMBERED_PATTERN = re.compile(
        r'(?:^|\n)\s*(\d+)[.\)]\s*(.+?)(?=\n\s*\d+[.\)]|\n\n|\Z)',
        re.MULTILINE | re.DOTALL
    )

    # Patterns for bullet lists (- Item, * Item, • Item)
    BULLET_PATTERN = re.compile(
        r'(?:^|\n)\s*[-*•]\s*(.+?)(?=\n\s*[-*•]|\n\n|\Z)',
        re.MULTILINE | re.DOTALL
    )

    # Must-have indicators
    MUST_INDICATORS = [
        "must", "should", "need to", "needs to", "required",
        "ensure", "make sure", "important", "critical", "essential",
        "definitely", "always", "never", "don't forget",
    ]

    # Nice-to-have indicators
    OPTIONAL_INDICATORS = [
        "optionally", "if possible", "bonus", "extra",
        "nice to have", "would be nice", "could also",
        "maybe", "perhaps", "consider",
    ]

    def __init__(self):
        """Initialize the requirement extractor."""
        self._req_counter = 0

    def extract(self, prompt: str) -> RequirementSet:
        """Extract requirements from a user prompt.

        Args:
            prompt: The user's message/prompt

        Returns:
            RequirementSet containing extracted requirements
        """
        if not prompt:
            return RequirementSet(original_prompt=prompt)

        requirements = []
        self._req_counter = 0

        # Extract from numbered lists (highest priority - explicit structure)
        numbered_reqs = self._extract_numbered_items(prompt)
        requirements.extend(numbered_reqs)

        # Extract from bullet lists
        bullet_reqs = self._extract_bullet_items(prompt)
        requirements.extend(bullet_reqs)

        # Extract from "and" conjunctions for multi-part requests
        if not requirements:
            conjunction_reqs = self._extract_conjunction_items(prompt)
            requirements.extend(conjunction_reqs)

        # Deduplicate requirements
        requirements = self._deduplicate(requirements)

        # Log extraction results
        if requirements:
            logger.info(
                f"Extracted {len(requirements)} requirements from prompt "
                f"({sum(1 for r in requirements if r.priority == RequirementPriority.MUST_HAVE)} must-haves)"
            )

        return RequirementSet(
            requirements=requirements,
            original_prompt=prompt
        )

    def _extract_numbered_items(self, text: str) -> list[Requirement]:
        """Extract requirements from numbered lists."""
        requirements = []

        for match in self.NUMBERED_PATTERN.finditer(text):
            item_text = match.group(2).strip()
            if item_text and len(item_text) > 3:
                self._req_counter += 1
                requirements.append(Requirement(
                    id=f"REQ-{self._req_counter:03d}",
                    description=self._clean_text(item_text),
                    priority=self._determine_priority(item_text),
                    source_text=match.group(0).strip()
                ))

        return requirements

    def _extract_bullet_items(self, text: str) -> list[Requirement]:
        """Extract requirements from bullet lists."""
        requirements = []

        for match in self.BULLET_PATTERN.finditer(text):
            item_text = match.group(1).strip()
            if item_text and len(item_text) > 3:
                self._req_counter += 1
                requirements.append(Requirement(
                    id=f"REQ-{self._req_counter:03d}",
                    description=self._clean_text(item_text),
                    priority=self._determine_priority(item_text),
                    source_text=match.group(0).strip()
                ))

        return requirements

    def _extract_conjunction_items(self, text: str) -> list[Requirement]:
        """Extract requirements from conjunction phrases (X and Y and Z)."""
        requirements = []

        # Look for patterns like "do X, Y, and Z" or "X and also Y"
        # Split on common conjunctions
        parts = re.split(r'\s+and\s+(?:also\s+)?|\s*,\s+and\s+|\s*,\s+', text)

        # Only extract if we have multiple substantial parts
        if len(parts) >= 2:
            for part in parts:
                part = part.strip()
                # Filter out very short or very long parts
                if 5 < len(part) < 200:
                    # Check if it looks like a task/action
                    action_words = ["create", "make", "build", "write", "add", "remove",
                                    "update", "change", "fix", "implement", "design",
                                    "find", "search", "get", "fetch", "download"]
                    if any(word in part.lower() for word in action_words):
                        self._req_counter += 1
                        requirements.append(Requirement(
                            id=f"REQ-{self._req_counter:03d}",
                            description=self._clean_text(part),
                            priority=RequirementPriority.SHOULD_HAVE,
                            source_text=part
                        ))

        return requirements

    def _determine_priority(self, text: str) -> RequirementPriority:
        """Determine the priority of a requirement based on language."""
        text_lower = text.lower()

        # Check for optional indicators first
        if any(ind in text_lower for ind in self.OPTIONAL_INDICATORS):
            return RequirementPriority.NICE_TO_HAVE

        # Check for must-have indicators
        if any(ind in text_lower for ind in self.MUST_INDICATORS):
            return RequirementPriority.MUST_HAVE

        # Default: numbered/bulleted items are typically must-haves
        return RequirementPriority.MUST_HAVE

    def _clean_text(self, text: str) -> str:
        """Clean requirement text for storage."""
        # Remove extra whitespace
        text = " ".join(text.split())
        # Remove trailing punctuation for consistency
        text = text.rstrip(".,;:")
        # Capitalize first letter
        if text:
            text = text[0].upper() + text[1:]
        return text

    def _deduplicate(self, requirements: list[Requirement]) -> list[Requirement]:
        """Remove duplicate or very similar requirements."""
        if len(requirements) <= 1:
            return requirements

        seen_descriptions: set[str] = set()
        unique = []

        for req in requirements:
            # Normalize for comparison
            normalized = req.description.lower().strip()
            if normalized not in seen_descriptions:
                seen_descriptions.add(normalized)
                unique.append(req)

        return unique

    def match_requirement_to_step(
        self,
        requirement: Requirement,
        step_description: str
    ) -> float:
        """Calculate how well a step addresses a requirement.

        Args:
            requirement: The requirement to match
            step_description: Description of a plan step

        Returns:
            Match score between 0.0 and 1.0
        """
        if not requirement.description or not step_description:
            return 0.0

        req_words = set(requirement.description.lower().split())
        step_words = set(step_description.lower().split())

        # Remove common stop words
        stop_words = {"the", "a", "an", "to", "for", "and", "or", "in", "on", "with"}
        req_words -= stop_words
        step_words -= stop_words

        if not req_words:
            return 0.0

        # Calculate Jaccard similarity
        intersection = len(req_words & step_words)
        union = len(req_words | step_words)

        return intersection / union if union > 0 else 0.0


# Singleton instance
_extractor: RequirementExtractor | None = None


def get_requirement_extractor() -> RequirementExtractor:
    """Get the global requirement extractor instance."""
    global _extractor
    if _extractor is None:
        _extractor = RequirementExtractor()
    return _extractor


def extract_requirements(prompt: str) -> RequirementSet:
    """Convenience function to extract requirements from a prompt.

    Args:
        prompt: User prompt/message

    Returns:
        RequirementSet with extracted requirements
    """
    return get_requirement_extractor().extract(prompt)
