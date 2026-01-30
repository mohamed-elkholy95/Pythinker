"""
Meta-Cognitive Awareness module.

This module provides "knowing what it doesn't know" capability,
enabling the agent to recognize its own knowledge boundaries
and capabilities limitations.
"""

import logging
import re
from typing import Any

from app.domain.models.knowledge_gap import (
    CapabilityAssessment,
    GapSeverity,
    GapType,
    InformationRequest,
    KnowledgeAssessment,
    KnowledgeDomain,
    KnowledgeGap,
)

logger = logging.getLogger(__name__)

# Patterns indicating knowledge gaps or uncertainty
UNCERTAINTY_PATTERNS = [
    r"I (?:don't|do not) (?:know|have information)",
    r"I'm (?:not sure|uncertain|unsure)",
    r"(?:unclear|unknown|uncertain) (?:whether|if|what)",
    r"(?:may|might|could) (?:be|have|need)",
    r"I (?:lack|don't have) (?:access|knowledge|information)",
    r"(?:need|require)s? (?:more|additional|further) (?:information|context|details)",
    r"cannot (?:determine|verify|confirm)",
    r"no (?:way to|means of) (?:knowing|verifying)",
]

# Patterns indicating knowledge or capability
KNOWLEDGE_PATTERNS = [
    r"I (?:know|understand|am aware) that",
    r"(?:based on|according to) (?:my|the) (?:knowledge|understanding)",
    r"I (?:can|am able to)",
    r"(?:this|it) is (?:well-known|documented|established)",
]

# Known domains and topics for LLMs
KNOWN_DOMAINS = {
    "programming": {
        "confidence": 0.85,
        "known_topics": [
            "Python",
            "JavaScript",
            "TypeScript",
            "Java",
            "C++",
            "Go",
            "Rust",
            "web development",
            "APIs",
            "databases",
            "algorithms",
            "data structures",
        ],
        "unknown_topics": [
            "proprietary APIs",
            "internal company code",
            "private packages",
        ],
        "limitations": [
            "Cannot execute code in real-time",
            "Cannot access private repositories",
            "Knowledge cutoff applies to new frameworks",
        ],
    },
    "general_knowledge": {
        "confidence": 0.75,
        "known_topics": [
            "history",
            "science",
            "mathematics",
            "geography",
            "literature",
            "common knowledge",
            "public facts",
        ],
        "unknown_topics": [
            "events after knowledge cutoff",
            "unpublished research",
            "private information",
        ],
        "limitations": [
            "Knowledge cutoff date applies",
            "May lack very recent information",
        ],
    },
    "technical_writing": {
        "confidence": 0.80,
        "known_topics": [
            "documentation",
            "tutorials",
            "README files",
            "API documentation",
            "technical explanations",
        ],
        "unknown_topics": [],
        "limitations": [
            "Cannot verify code examples work",
            "May not know project-specific conventions",
        ],
    },
}

# Capability categories
CAPABILITY_CATEGORIES = {
    "file_operations": ["read", "write", "search", "list", "create", "delete"],
    "web_operations": ["browse", "search", "scrape", "fetch"],
    "code_operations": ["execute", "analyze", "test", "debug"],
    "shell_operations": ["command", "script", "terminal"],
    "analysis": ["research", "compare", "evaluate", "summarize"],
}


class MetaCognitionModule:
    """Module for meta-cognitive awareness.

    Enables the agent to:
    - Recognize what it knows and doesn't know
    - Identify knowledge gaps
    - Assess capability limitations
    - Generate requests for needed information
    """

    def __init__(
        self,
        available_tools: list[dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the meta-cognition module.

        Args:
            available_tools: List of available tool schemas
        """
        self._available_tools = available_tools or []
        self._domains = self._initialize_domains()
        self._tool_capabilities = self._extract_tool_capabilities()

    def assess_knowledge_boundaries(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> KnowledgeAssessment:
        """Assess knowledge boundaries for a task.

        Analyzes the task to identify what is known, unknown,
        and what gaps exist.

        Args:
            task: The task description
            context: Optional additional context

        Returns:
            Complete knowledge assessment
        """
        logger.debug(f"Assessing knowledge for task: {task[:100]}...")

        # Identify relevant domains
        relevant_domains = self._identify_relevant_domains(task)

        # Identify knowledge gaps
        gaps = self._identify_gaps(task, relevant_domains, context)

        # Generate information requests
        requests = self._suggest_information_needs(gaps)

        # Calculate overall confidence
        if relevant_domains:
            overall_confidence = sum(d.confidence for d in relevant_domains) / len(relevant_domains)
        else:
            overall_confidence = 0.5

        # Adjust for gaps
        if gaps:
            critical_gaps = [g for g in gaps if g.severity == GapSeverity.CRITICAL]
            high_gaps = [g for g in gaps if g.severity == GapSeverity.HIGH]
            overall_confidence -= len(critical_gaps) * 0.15
            overall_confidence -= len(high_gaps) * 0.08

        overall_confidence = max(0.1, min(1.0, overall_confidence))

        # Determine if we can proceed
        blocking_gaps = [g.id for g in gaps if g.is_blocking()]
        can_proceed = len(blocking_gaps) == 0

        assessment = KnowledgeAssessment(
            task=task,
            overall_confidence=overall_confidence,
            relevant_domains=relevant_domains,
            gaps=gaps,
            information_requests=requests,
            can_proceed=can_proceed,
            blocking_gaps=blocking_gaps,
        )

        logger.info(
            f"Knowledge assessment: confidence={overall_confidence:.2f}, gaps={len(gaps)}, can_proceed={can_proceed}"
        )

        return assessment

    def identify_gaps(
        self,
        task: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> list[KnowledgeGap]:
        """Identify knowledge gaps for a task.

        Args:
            task: The task description
            tools: Optional list of available tools

        Returns:
            List of identified knowledge gaps
        """
        if tools:
            self._available_tools = tools
            self._tool_capabilities = self._extract_tool_capabilities()

        relevant_domains = self._identify_relevant_domains(task)
        return self._identify_gaps(task, relevant_domains, None)

    def assess_capabilities(
        self,
        task: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> CapabilityAssessment:
        """Assess capabilities for a task.

        Args:
            task: The task description
            tools: Optional list of available tools

        Returns:
            Capability assessment
        """
        if tools:
            self._available_tools = tools
            self._tool_capabilities = self._extract_tool_capabilities()

        # Identify required capabilities from task
        required = self._extract_required_capabilities(task)

        # Check what's available
        available = list(self._tool_capabilities.keys())

        # Find missing capabilities
        missing = [cap for cap in required if cap not in self._tool_capabilities]

        # Calculate match score
        match_score = (len(required) - len(missing)) / len(required) if required else 1.0

        # Suggest workarounds for missing capabilities
        workarounds = self._suggest_workarounds(missing)

        can_accomplish = match_score >= 0.7 or len(workarounds) >= len(missing)

        return CapabilityAssessment(
            task=task,
            available_tools=available,
            required_capabilities=required,
            missing_capabilities=missing,
            capability_match_score=match_score,
            can_accomplish=can_accomplish,
            workarounds=workarounds,
        )

    def suggest_information_needs(
        self,
        gaps: list[KnowledgeGap],
    ) -> list[InformationRequest]:
        """Suggest information requests to fill gaps.

        Args:
            gaps: List of knowledge gaps

        Returns:
            List of information requests
        """
        return self._suggest_information_needs(gaps)

    def update_available_tools(
        self,
        tools: list[dict[str, Any]],
    ) -> None:
        """Update the available tools list.

        Args:
            tools: New list of available tools
        """
        self._available_tools = tools
        self._tool_capabilities = self._extract_tool_capabilities()

    def _initialize_domains(self) -> dict[str, KnowledgeDomain]:
        """Initialize knowledge domains."""
        domains = {}
        for name, config in KNOWN_DOMAINS.items():
            domains[name] = KnowledgeDomain(
                name=name,
                confidence=config["confidence"],
                known_topics=config["known_topics"],
                unknown_topics=config["unknown_topics"],
                limitations=config["limitations"],
            )
        return domains

    def _extract_tool_capabilities(self) -> dict[str, list[str]]:
        """Extract capabilities from available tools."""
        capabilities: dict[str, list[str]] = {}

        for tool in self._available_tools:
            func = tool.get("function", {})
            name = func.get("name", "")
            desc = func.get("description", "").lower()

            # Categorize by description keywords
            for category, keywords in CAPABILITY_CATEGORIES.items():
                for keyword in keywords:
                    if keyword in name.lower() or keyword in desc:
                        if category not in capabilities:
                            capabilities[category] = []
                        capabilities[category].append(name)
                        break

        return capabilities

    def _identify_relevant_domains(self, task: str) -> list[KnowledgeDomain]:
        """Identify domains relevant to a task."""
        task_lower = task.lower()
        relevant = []

        for _name, domain in self._domains.items():
            # Check if any known topics match
            for topic in domain.known_topics:
                if topic.lower() in task_lower:
                    relevant.append(domain)
                    break

        # Default to general knowledge if no specific domains match
        if not relevant and "general_knowledge" in self._domains:
            relevant.append(self._domains["general_knowledge"])

        return relevant

    def _identify_gaps(
        self,
        task: str,
        domains: list[KnowledgeDomain],
        context: dict[str, Any] | None,
    ) -> list[KnowledgeGap]:
        """Identify knowledge gaps for a task."""
        gaps = []

        # Check for uncertainty patterns in task
        gaps.extend(self._extract_uncertainty_gaps(task))

        # Check domain limitations
        for domain in domains:
            for unknown in domain.unknown_topics:
                if unknown.lower() in task.lower():
                    gaps.append(
                        KnowledgeGap(
                            gap_type=GapType.FACTUAL,
                            severity=GapSeverity.HIGH,
                            description=f"Task involves {unknown}, which is outside known knowledge",
                            topic=unknown,
                            can_be_filled=True,
                            requires_external=True,
                        )
                    )

        # Check for capability gaps
        capability_gaps = self._identify_capability_gaps(task)
        gaps.extend(capability_gaps)

        # Check for temporal gaps (current information needs)
        if self._needs_current_info(task):
            gaps.append(
                KnowledgeGap(
                    gap_type=GapType.TEMPORAL,
                    severity=GapSeverity.MEDIUM,
                    description="Task may require current/real-time information",
                    topic="current information",
                    resolution_options=["Use web search", "Ask user for current data"],
                    can_be_filled=True,
                    requires_external=True,
                )
            )

        return gaps

    def _extract_uncertainty_gaps(self, task: str) -> list[KnowledgeGap]:
        """Extract gaps from uncertainty patterns in task."""
        gaps = []

        for pattern in UNCERTAINTY_PATTERNS:
            if re.search(pattern, task, re.IGNORECASE):
                gaps.append(
                    KnowledgeGap(
                        gap_type=GapType.CONTEXTUAL,
                        severity=GapSeverity.MEDIUM,
                        description="Task contains uncertainty that may need clarification",
                        topic="task clarification",
                        can_be_filled=True,
                    )
                )
                break

        return gaps

    def _identify_capability_gaps(self, task: str) -> list[KnowledgeGap]:
        """Identify gaps in available capabilities."""
        gaps = []

        # Check for required capabilities not in available tools
        required_caps = self._extract_required_capabilities(task)

        for cap in required_caps:
            if cap not in self._tool_capabilities:
                severity = GapSeverity.HIGH if cap in ["code_operations", "shell_operations"] else GapSeverity.MEDIUM
                gaps.append(
                    KnowledgeGap(
                        gap_type=GapType.CAPABILITY,
                        severity=severity,
                        description=f"Task requires {cap} capability which may not be available",
                        topic=cap,
                        can_be_filled=False,
                    )
                )

        return gaps

    def _extract_required_capabilities(self, task: str) -> list[str]:
        """Extract required capabilities from task description."""
        required = []
        task_lower = task.lower()

        for category, keywords in CAPABILITY_CATEGORIES.items():
            for keyword in keywords:
                if keyword in task_lower:
                    required.append(category)
                    break

        return list(set(required))

    def _needs_current_info(self, task: str) -> bool:
        """Check if task needs current/real-time information."""
        current_indicators = [
            "current",
            "latest",
            "today",
            "now",
            "recent",
            "live",
            "real-time",
            "up-to-date",
            "new",
        ]
        task_lower = task.lower()
        return any(ind in task_lower for ind in current_indicators)

    def _suggest_information_needs(
        self,
        gaps: list[KnowledgeGap],
    ) -> list[InformationRequest]:
        """Generate information requests from gaps."""
        requests = []

        for gap in gaps:
            if not gap.can_be_filled:
                continue

            request_type = self._determine_request_type(gap)
            query = self._generate_query(gap)

            priority = 1 if gap.severity == GapSeverity.CRITICAL else (2 if gap.severity == GapSeverity.HIGH else 3)

            requests.append(
                InformationRequest(
                    gap_ids=[gap.id],
                    request_type=request_type,
                    query=query,
                    priority=priority,
                    expected_info=f"Information about {gap.topic}",
                )
            )

        # Sort by priority
        requests.sort(key=lambda r: r.priority)
        return requests

    def _determine_request_type(self, gap: KnowledgeGap) -> str:
        """Determine the best request type for a gap."""
        if gap.gap_type == GapType.FACTUAL:
            return "search"
        if gap.gap_type == GapType.CONTEXTUAL:
            return "ask_user"
        if gap.gap_type == GapType.TEMPORAL or gap.gap_type == GapType.PROCEDURAL:
            return "search"
        return "ask_user"

    def _generate_query(self, gap: KnowledgeGap) -> str:
        """Generate a query to address a gap."""
        if gap.gap_type == GapType.FACTUAL:
            return f"What is {gap.topic}?"
        if gap.gap_type == GapType.PROCEDURAL:
            return f"How to {gap.topic}?"
        if gap.gap_type == GapType.TEMPORAL:
            return f"Current information about {gap.topic}"
        return f"More context about {gap.topic}"

    def _suggest_workarounds(self, missing: list[str]) -> list[str]:
        """Suggest workarounds for missing capabilities."""
        workarounds = []

        for cap in missing:
            if cap == "code_operations":
                workarounds.append("Use shell commands to run code")
            elif cap == "web_operations":
                workarounds.append("Use file-based approach if web access unavailable")
            elif cap == "shell_operations":
                workarounds.append("Use code execution if shell unavailable")

        return workarounds


# Global instance
_meta_cognition: MetaCognitionModule | None = None


def get_meta_cognition(
    tools: list[dict[str, Any]] | None = None,
) -> MetaCognitionModule:
    """Get or create the global meta-cognition module."""
    global _meta_cognition
    if _meta_cognition is None:
        _meta_cognition = MetaCognitionModule(tools)
    return _meta_cognition


def reset_meta_cognition() -> None:
    """Reset the global meta-cognition module."""
    global _meta_cognition
    _meta_cognition = None
