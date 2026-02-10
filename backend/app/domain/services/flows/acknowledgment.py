"""Acknowledgment generation for user messages.

Extracts from PlanActFlow: generates brief acknowledgment messages
before planning begins, giving users instant feedback.
"""

import re

from app.domain.services.prompts.research import is_research_task


class AcknowledgmentGenerator:
    """Generates acknowledgment messages for user requests.

    Provides instant feedback before planning begins by analyzing
    the user's message and generating an appropriate response.
    """

    def generate(self, user_message: str) -> str:
        """Generate an acknowledgment message before starting to plan.

        Args:
            user_message: The user's original message

        Returns:
            A brief acknowledgment message describing what will be done
        """
        message_lower = user_message.lower()
        request_focus = self._extract_request_focus(user_message)
        is_large_prompt = self._is_large_prompt(user_message, request_focus)

        # Skill creation acknowledgment
        if "/skill-creator" in message_lower:
            return self._ack_skill_creation(user_message, message_lower)

        # Research-type tasks
        if is_research_task(user_message):
            return self._ack_research(user_message, request_focus, is_large_prompt)

        # Specific task types
        if any(word in message_lower for word in ["create", "build", "make", "generate", "write"]):
            if is_large_prompt:
                return "I've received your request. I'll prepare a clear plan and start working through it step by step."
            if request_focus and request_focus != "this task":
                return f"I'll help you with {request_focus}. Let me create a plan and get started."
            return "I'll help you with that. Let me create a plan and get started."

        if any(word in message_lower for word in ["fix", "debug", "solve", "resolve"]):
            if is_large_prompt:
                return "I've received your debugging request. I'll diagnose the issue and work toward a reliable fix."
            return "I'll analyze the issue and work on a solution."

        if any(word in message_lower for word in ["find", "search", "look for", "locate"]):
            if is_large_prompt:
                return "I've received your request. I'll gather the relevant information and return a structured summary."
            return "I'll search for that information."

        if any(word in message_lower for word in ["explain", "how does", "what is", "why"]):
            return "Let me look into that for you."

        if any(word in message_lower for word in ["update", "modify", "change", "edit"]):
            return "I'll work on making those changes."

        if any(word in message_lower for word in ["install", "setup", "configure"]):
            return "I'll help you set that up."

        if any(word in message_lower for word in ["test", "check", "verify", "validate"]):
            return "I'll run some checks on that."

        # Default
        if is_large_prompt:
            return "I've received your request. I'll analyze it and proceed with a structured response."
        return "I'll help you with that. Let me work on it."

    def _ack_skill_creation(self, user_message: str, message_lower: str) -> str:
        """Generate acknowledgment for skill creation requests."""
        if message_lower.strip().startswith("/skill-creator"):
            command_match = re.match(r"^\s*/skill-creator(?:\s+(.*))?$", user_message, flags=re.IGNORECASE)
            if command_match:
                skill_name = (command_match.group(1) or "").strip().strip('"')
                if skill_name:
                    return f'I\'ll help you create the "{skill_name}" skill. Let me first review the skill creation guidelines.'
        match = re.search(r'"([^"]+)"', user_message)
        if match and match.group(1).strip():
            return f'I\'ll help you create the "{match.group(1).strip()}" skill. Let me first review the skill creation guidelines.'
        return "I'll help you create that skill. Let me first review the skill creation guidelines."

    def _ack_research(self, user_message: str, request_focus: str, is_large_prompt: bool) -> str:
        """Generate acknowledgment for research requests."""
        if is_large_prompt:
            topic = self._compact_subject(self._extract_research_topic(user_message))
            if topic:
                return (
                    f"I've received your request for {topic}. "
                    "I will begin by researching the latest tools and data to provide a detailed analysis."
                )
            return (
                "I've received your request for a comprehensive research report. "
                "I will begin by researching the latest tools and data to provide a detailed analysis."
            )

        if request_focus and request_focus != "this task":
            compact_focus = self._compact_subject(request_focus)
            if compact_focus:
                return (
                    f"I've received your request for {compact_focus}. "
                    "I will begin by researching the latest tools and data to provide a detailed analysis."
                )
        return (
            "I've received your request for research on this topic. "
            "I will begin by researching the latest tools and data to provide a detailed analysis."
        )

    def _is_large_prompt(self, user_message: str, request_focus: str) -> bool:
        """Detect prompts that should use compact acknowledgments."""
        if len(user_message) >= 280:
            return True
        if len(request_focus) >= 140:
            return True
        if "\n" in user_message:
            return True
        return len(re.findall(r"\b\d+\.", user_message)) >= 2

    def _compact_subject(self, subject: str | None) -> str | None:
        """Compact a subject phrase for acknowledgment text."""
        if not subject:
            return None

        normalized = re.sub(r"\s+", " ", subject).strip().rstrip(".!?")
        if not normalized:
            return None

        normalized = re.split(r"[;\n]", normalized, maxsplit=1)[0].strip()
        normalized = re.split(r"\.\s+", normalized, maxsplit=1)[0].strip()
        normalized = re.sub(r"\s+the report should include.*$", "", normalized, flags=re.IGNORECASE).strip()

        max_words = 14
        max_chars = 110
        words = normalized.split()
        if len(words) > max_words:
            normalized = " ".join(words[:max_words]).rstrip(",:;")
        if len(normalized) > max_chars:
            normalized = normalized[:max_chars].rstrip(" ,:;")

        return normalized or None

    def _extract_request_focus(self, user_message: str) -> str:
        """Extract the actionable focus from the user's request."""
        focus = (user_message or "").strip()
        if not focus:
            return "this task"

        focus = re.sub(
            r"^\s*(?:please\s+)?(?:(?:can|could|would)\s+you|you\s+can)\s+",
            "",
            focus,
            flags=re.IGNORECASE,
        )
        focus = re.sub(r"^\s*please\s+", "", focus, flags=re.IGNORECASE)

        action_prefix = (
            r"^\s*(?:to\s+)?(?:"
            r"create|build|make|generate|write|develop|implement|design|"
            r"fix|debug|solve|resolve|troubleshoot|"
            r"analy[sz]e|research|investigate|"
            r"find|search(?:\s+for)?|look\s+for|locate|"
            r"explain|describe|summari[sz]e|"
            r"update|modify|change|edit|"
            r"install|setup|set\s+up|configure|"
            r"test|check|verify|validate"
            r")\s+"
        )
        focus = re.sub(action_prefix, "", focus, flags=re.IGNORECASE)

        focus = focus.strip().rstrip(".!?")
        return focus or "this task"

    def _extract_research_topic(self, user_message: str) -> str | None:
        """Extract the research topic from the user's message."""
        message_lower = user_message.lower()

        topic_patterns = [
            r"research\s+report\s+(?:on|about)[:\s]+(.+?)(?:\.|$)",
            r"research\s+report\s+analy(?:zing|sing)[:\s]+(.+?)(?:\.|$)",
            r"comprehensive\s+research\s+(?:on|about)[:\s]+(.+?)(?:\.|$)",
            r"research\s+(?:on|about)[:\s]+(.+?)(?:\.|$)",
            r"(?:^|\s)research[:\s]+(.+?)(?:\.|$)",
            r"investigate[:\s]+(.+?)(?:\.|$)",
            r"find\s+(?:information|info|details)\s+(?:on|about)[:\s]+(.+?)(?:\.|$)",
            r"look\s+into[:\s]+(.+?)(?:\.|$)",
            r"analyze[:\s]+(.+?)(?:\.|$)",
            r"study[:\s]+(.+?)(?:\.|$)",
        ]

        for pattern in topic_patterns:
            match = re.search(pattern, message_lower, re.IGNORECASE)
            if match:
                topic = match.group(1).strip()
                topic = re.sub(r"\s+", " ", topic)
                topic = re.sub(
                    r"^(?:and|or)\s+(?:compare|analyze|evaluate|assess|examine|study|review|summarize|investigate)\s+",
                    "",
                    topic,
                    flags=re.IGNORECASE,
                )
                topic = re.sub(
                    r"\s+(?:and\s+(?:provide|create|give|send)|then\s+\w+).*$", "", topic, flags=re.IGNORECASE
                )
                if topic and len(topic) > 3:
                    return topic

        report_match = re.search(
            r"create\s+(?:a\s+)?(?:\w+\s+)*report\s+(?:on|about)[:\s]+(.+?)(?:\.|$)", message_lower
        )
        if report_match:
            topic = report_match.group(1).strip()
            topic = re.sub(r"\s+", " ", topic)
            if topic and len(topic) > 3:
                return topic

        if message_lower.startswith(("research ", "investigate ", "analyze ")):
            parts = user_message.split(" ", 1)
            if len(parts) > 1:
                topic = parts[1].strip()
                topic = re.sub(r"^(?:on|about)[:\s]+", "", topic, flags=re.IGNORECASE)
                if topic and len(topic) > 3:
                    return topic[:150]

        return None
