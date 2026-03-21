"""Intent classifier for agent mode selection.

Classifies user intent to route messages to appropriate agent modes:
- DISCUSS mode for simple queries, greetings, acknowledgments
- AGENT mode for complex tasks requiring execution

Enhanced with context-aware classification considering:
- Attachments (files, images, URLs)
- Active skills and MCP tools
- Conversation context (follow-ups vs new queries)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, ClassVar

from app.domain.models.session import AgentMode, SessionStatus

logger = logging.getLogger(__name__)


@dataclass
class ClassificationContext:
    """Context for intent classification.

    Provides additional signals beyond the message text to improve
    classification accuracy.
    """

    # Attached files (images, PDFs, documents)
    attachments: list[dict[str, Any]] = field(default_factory=list)

    # Available skills that could be triggered
    available_skills: list[str] = field(default_factory=list)

    # Conversation history length (0 = new conversation)
    conversation_length: int = 0

    # Previous message was from assistant (indicates follow-up)
    is_follow_up: bool = False

    # URLs detected in message
    urls: list[str] = field(default_factory=list)

    # Active MCP tools that might be relevant
    mcp_tools: list[str] = field(default_factory=list)

    # Session execution awareness (added for plan-guard)
    session_mode: AgentMode | None = None
    session_had_plan: bool = False
    session_plan_title: str | None = None
    session_status: SessionStatus | None = None
    session_completed_steps: int = 0

    def has_attachments(self) -> bool:
        """Check if context has any attachments."""
        return len(self.attachments) > 0

    def has_image_attachment(self) -> bool:
        """Check if context has image attachments."""
        image_types = {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"}
        return any(
            att.get("mime_type", "") in image_types or att.get("type", "") in ["image", "screenshot"]
            for att in self.attachments
        )

    def has_document_attachment(self) -> bool:
        """Check if context has document attachments (PDF, etc)."""
        doc_types = {"application/pdf", "text/plain", "text/markdown"}
        doc_extensions = {".pdf", ".txt", ".md", ".doc", ".docx"}
        return any(
            att.get("mime_type", "") in doc_types
            or any(att.get("filename", "").lower().endswith(ext) for ext in doc_extensions)
            for att in self.attachments
        )

    def has_urls(self) -> bool:
        """Check if context has URLs."""
        return len(self.urls) > 0


@dataclass
class ClassificationResult:
    """Result of intent classification with detailed breakdown."""

    intent: str
    mode: AgentMode
    confidence: float
    reasons: list[str] = field(default_factory=list)

    # Context signals that influenced the decision
    context_signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "intent": self.intent,
            "mode": self.mode.value,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "context_signals": self.context_signals,
        }


class IntentClassifier:
    """Classifies user intent to select appropriate agent mode."""

    SIMPLE_INTENTS: ClassVar[list[str]] = [
        "greeting",
        "thanks",
        "acknowledgment",
        "clarification_question",
        "simple_fact_query",
        "definition_request",
    ]

    COMPLEX_INTENTS: ClassVar[list[str]] = [
        "task_request",
        "multi_step_workflow",
        "code_generation",
        "research_task",
        "file_manipulation",
        "system_operation",
    ]

    # Greeting patterns
    GREETING_PATTERNS: ClassVar[list[str]] = [
        r"^(hi|hello|hey|greetings)[\s!?.]*$",
        r"^(good morning|good afternoon|good evening)[\s!?.]*$",
        r"^(sup|wassup|what's up|whats up)[\s!?.]*$",
    ]

    # Acknowledgment patterns
    ACKNOWLEDGMENT_PATTERNS: ClassVar[list[str]] = [
        r"^(thanks|thank you|thx|ty)[\s!?.]*$",
        r"^(ok|okay|got it|understood|alright)[\s!?.]*$",
        r"^(yes|yeah|yep|sure|no|nope)[\s!?.]*$",
        r"^(cool|nice|great|awesome|perfect)[\s!?.]*$",
    ]

    # Task indicators (words that suggest executable tasks)
    TASK_INDICATORS: ClassVar[list[str]] = [
        "write",
        "create",
        "build",
        "make",
        "generate",
        "implement",
        "develop",
        "code",
        "fix",
        "debug",
        "refactor",
        "test",
        "deploy",
        "install",
        "configure",
        "setup",
        "analyze",
        "run",
        "execute",
        "search for",
        "find all",
        "list all",
        "show me",
    ]

    # Action-first verbs for distinguishing execution requests from short topic prompts.
    # Example: "claude code sonnet 5" should not be treated as a task, but "write code" should.
    ACTION_VERBS: ClassVar[list[str]] = [
        "write",
        "create",
        "build",
        "make",
        "generate",
        "implement",
        "develop",
        "fix",
        "debug",
        "refactor",
        "deploy",
        "install",
        "configure",
        "setup",
        "analyze",
        "run",
        "execute",
        "search",
        "find",
        "list",
        "show",
        "open",
        "compare",
        "research",
        "investigate",
        "summarize",
        "explain",
    ]

    # Direct output patterns (simple response instructions that don't need tools/planning)
    DIRECT_RESPONSE_PATTERNS: ClassVar[list[str]] = [
        r"\b(?:say|reply|respond)\b.+\b(?:nothing else|only|exactly)\b",
        r"\boutput\b.+\b(?:nothing else|only)\b",
        r"\b(?:say|reply|respond)\b\s+['\"`].+['\"`]\s+\b(?:only|exactly)\b",
    ]

    # Question indicators
    QUESTION_WORDS: ClassVar[list[str]] = [
        "what",
        "why",
        "how",
        "when",
        "where",
        "who",
        "which",
        "can you",
        "could you",
        "would you",
    ]

    _CONTINUATION_PATTERNS: ClassVar[list[str]] = [
        r"^(do it|go ahead|continue|proceed|yes|yes please|ok do it|sure)[\s!.]*$",
        r"^(keep going|carry on|finish it|complete it)[\s!.]*$",
    ]

    def _is_continuation_phrase(self, message: str) -> bool:
        """Check if message is a continuation/approval phrase."""
        normalized = message.lower().strip()
        return any(re.match(p, normalized, re.IGNORECASE) for p in self._CONTINUATION_PATTERNS)

    def classify(self, message: str) -> tuple[str, AgentMode, float]:
        """Classify user intent and recommend agent mode.

        Args:
            message: User message to classify

        Returns:
            Tuple of (intent, recommended_mode, confidence)
        """
        normalized = message.lower().strip()
        words = normalized.split()
        word_count = len(words)

        # Check greetings
        for pattern in self.GREETING_PATTERNS:
            if re.match(pattern, normalized, re.IGNORECASE):
                logger.info(f"Classified as greeting: {message[:50]}")
                return ("greeting", AgentMode.DISCUSS, 0.95)

        # Check acknowledgments
        for pattern in self.ACKNOWLEDGMENT_PATTERNS:
            if re.match(pattern, normalized, re.IGNORECASE):
                logger.info(f"Classified as acknowledgment: {message[:50]}")
                return ("acknowledgment", AgentMode.DISCUSS, 0.95)

        # Check for direct-response instructions (no tools/planning required)
        for pattern in self.DIRECT_RESPONSE_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                logger.info(f"Classified as direct response request: {message[:50]}")
                return ("direct_response_request", AgentMode.DISCUSS, 0.85)

        # Check for task indicators
        has_task_indicator = self._has_task_indicator(normalized)

        if has_task_indicator:
            if self._is_short_topic_prompt(normalized, word_count):
                logger.info(f"Classified as simple query (short topic): {message[:50]}")
                return ("simple_query", AgentMode.DISCUSS, 0.78)
            logger.info(f"Classified as task request: {message[:50]}")
            return ("task_request", AgentMode.AGENT, 0.85)

        # Check for file paths or commands (suggests executable task)
        # Do this BEFORE word count check to catch short commands like "edit /path"
        has_file_path = "/" in message or "\\" in message
        has_command_syntax = any(char in message for char in ["`", "$", ">>", "&&", "||"])

        if has_file_path or has_command_syntax:
            logger.info(f"Classified as system operation: {message[:50]}")
            return ("system_operation", AgentMode.AGENT, 0.80)

        # Check message length and complexity
        # Very short messages are likely simple queries
        if word_count <= 3:
            logger.info(f"Classified as simple query (short): {message[:50]}")
            return ("simple_query", AgentMode.DISCUSS, 0.80)

        # Check if it's a question
        is_question = normalized.endswith("?") or any(normalized.startswith(qw) for qw in self.QUESTION_WORDS)

        if is_question and word_count <= 10:
            logger.info(f"Classified as simple question: {message[:50]}")
            return ("simple_question", AgentMode.DISCUSS, 0.75)

        # Medium-length questions without task indicators
        if is_question and word_count <= 20:
            logger.info(f"Classified as clarification question: {message[:50]}")
            return ("clarification_question", AgentMode.DISCUSS, 0.70)

        # Default to AGENT mode for longer, ambiguous messages
        logger.info(f"Classified as complex query (default): {message[:50]}")
        return ("complex_query", AgentMode.AGENT, 0.60)

    def _is_short_topic_prompt(self, normalized_message: str, word_count: int) -> bool:
        """Detect short topic-like prompts that should not auto-trigger task execution."""
        if word_count == 0 or word_count > 4:
            return False

        if normalized_message.endswith("?"):
            return False

        if any(normalized_message.startswith(qw) for qw in self.QUESTION_WORDS):
            return False

        return all(not re.search(rf"\b{re.escape(verb)}\b", normalized_message) for verb in self.ACTION_VERBS)

    def _has_task_indicator(self, normalized_message: str) -> bool:
        """Return True when a task indicator is present with token-aware matching.

        Single-word indicators use word boundaries to avoid false positives
        (e.g., matching "test" inside "testing"). Multi-word indicators are
        matched as plain substrings.
        """
        for indicator in self.TASK_INDICATORS:
            if " " in indicator:
                if indicator in normalized_message:
                    return True
                continue

            if re.search(rf"\b{re.escape(indicator)}\b", normalized_message):
                return True

        return False

    def classify_with_context(self, message: str, context: ClassificationContext | None = None) -> ClassificationResult:
        """Classify user intent with additional context signals.

        Enhanced classification that considers:
        - Attachments (images suggest vision tasks, docs suggest analysis)
        - Active skills (skill mentions suggest specific modes)
        - Conversation context (follow-ups may be simpler)
        - URLs (suggest web research or browsing)

        Args:
            message: User message to classify
            context: Optional classification context with signals

        Returns:
            ClassificationResult with detailed breakdown
        """
        # Start with basic classification
        intent, mode, confidence = self.classify(message)
        reasons = [f"Base classification: {intent}"]
        context_signals: dict[str, Any] = {}

        if not context:
            return ClassificationResult(intent=intent, mode=mode, confidence=confidence, reasons=reasons)

        # Guard 2: Continuation phrases in planned session → stay AGENT
        # (checked before Guard 1 so continuation intent takes precedence)
        if context.is_follow_up and context.session_had_plan and self._is_continuation_phrase(message):
            reasons.append("Continuation phrase in planned session → AGENT")
            return ClassificationResult(
                intent="continuation",
                mode=AgentMode.AGENT,
                confidence=0.95,
                reasons=reasons,
                context_signals={"continuation_in_plan": True},
            )

        # Guard 1: Never downgrade AGENT→DISCUSS if session had a plan
        if context.session_mode == AgentMode.AGENT and mode == AgentMode.DISCUSS and context.session_had_plan:
            reasons.append(
                f"BLOCKED: AGENT→DISCUSS downgrade prevented — session has plan '{context.session_plan_title}'"
            )
            return ClassificationResult(
                intent="follow_up_to_planned_task",
                mode=AgentMode.AGENT,
                confidence=0.90,
                reasons=reasons,
                context_signals={"plan_guard_active": True},
            )

        # Analyze context signals
        normalized = message.lower().strip()

        # 1. Attachment signals - images/files suggest AGENT mode
        if context.has_image_attachment():
            context_signals["has_image"] = True
            if mode == AgentMode.DISCUSS:
                # Image analysis requires agent capabilities
                mode = AgentMode.AGENT
                intent = "image_analysis"
                confidence = max(confidence, 0.85)
                reasons.append("Image attachment detected - requires vision processing")

        if context.has_document_attachment():
            context_signals["has_document"] = True
            if mode == AgentMode.DISCUSS:
                # Document analysis is complex
                mode = AgentMode.AGENT
                intent = "document_analysis"
                confidence = max(confidence, 0.80)
                reasons.append("Document attachment detected - requires analysis")

        # 2. URL signals - suggest web tasks
        if context.has_urls():
            context_signals["has_urls"] = True
            context_signals["url_count"] = len(context.urls)
            if mode == AgentMode.DISCUSS:
                # URL processing suggests research/browsing
                mode = AgentMode.AGENT
                intent = "web_research"
                confidence = max(confidence, 0.75)
                reasons.append("URLs detected - may require web browsing")

        # 3. Skill triggers - check for skill invocations
        if context.available_skills:
            context_signals["available_skills"] = context.available_skills
            skill_mentions = [
                skill
                for skill in context.available_skills
                if skill.lower() in normalized or f"/{skill.lower()}" in normalized
            ]
            if skill_mentions:
                context_signals["triggered_skills"] = skill_mentions
                mode = AgentMode.AGENT
                intent = "skill_invocation"
                confidence = 0.95
                reasons.append(f"Skill trigger detected: {', '.join(skill_mentions)}")

        # 4. MCP tool suggestions
        if context.mcp_tools:
            context_signals["mcp_tools_available"] = len(context.mcp_tools)
            # Check if message references specific tools
            tool_references = [tool for tool in context.mcp_tools if tool.lower() in normalized]
            if tool_references:
                context_signals["referenced_tools"] = tool_references
                if mode == AgentMode.DISCUSS:
                    mode = AgentMode.AGENT
                    confidence = max(confidence, 0.80)
                    reasons.append(f"MCP tool reference: {', '.join(tool_references)}")

        # 5. Follow-up detection - follow-ups to agent work stay in agent mode
        if context.is_follow_up and context.conversation_length > 0:
            context_signals["is_follow_up"] = True
            context_signals["conversation_length"] = context.conversation_length

            # Short follow-ups like "do it" or "yes, continue" maintain previous mode
            continuation_phrases = ["do it", "go ahead", "continue", "yes", "proceed", "run it", "execute"]
            if len(normalized.split()) <= 5 and any(phrase in normalized for phrase in continuation_phrases):
                mode = AgentMode.AGENT
                intent = "continuation"
                confidence = 0.90
                reasons.append("Continuation phrase detected in follow-up")

        # 6. Conversation length adjustment
        if context.conversation_length > 5:
            context_signals["long_conversation"] = True
            # In long conversations, maintain higher agent threshold
            if mode == AgentMode.DISCUSS and confidence < 0.80:
                # Slight boost toward agent for complex ongoing work
                confidence = confidence * 0.95
                reasons.append("Long conversation - slightly preferring agent mode")

        return ClassificationResult(
            intent=intent,
            mode=mode,
            confidence=confidence,
            reasons=reasons,
            context_signals=context_signals,
        )

    def should_use_discuss_mode(self, message: str) -> bool:
        """Quick check if message should use DISCUSS mode.

        Args:
            message: User message

        Returns:
            True if DISCUSS mode should be used
        """
        _intent, mode, confidence = self.classify(message)
        return mode == AgentMode.DISCUSS and confidence >= 0.7

    def should_use_discuss_mode_with_context(self, message: str, context: ClassificationContext | None = None) -> bool:
        """Context-aware check if message should use DISCUSS mode.

        Args:
            message: User message
            context: Optional classification context

        Returns:
            True if DISCUSS mode should be used
        """
        result = self.classify_with_context(message, context)
        return result.mode == AgentMode.DISCUSS and result.confidence >= 0.7

    def extract_urls(self, message: str) -> list[str]:
        """Extract URLs from message text.

        Args:
            message: Message to extract URLs from

        Returns:
            List of extracted URLs
        """
        url_pattern = r"https?://[^\s<>\"{}|\\^`\[\]]+"
        return re.findall(url_pattern, message)


# Global instance
_intent_classifier: IntentClassifier | None = None


def get_intent_classifier() -> IntentClassifier:
    """Get the global intent classifier instance.

    Returns:
        IntentClassifier instance
    """
    global _intent_classifier
    if _intent_classifier is None:
        _intent_classifier = IntentClassifier()
    return _intent_classifier
