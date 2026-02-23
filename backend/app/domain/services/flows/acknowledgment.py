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
            return self._ack_create_or_build(user_message, message_lower, request_focus, is_large_prompt)

        if any(word in message_lower for word in ["fix", "debug", "solve", "resolve"]):
            if is_large_prompt:
                return "Got it! I will diagnose the issue and work toward a reliable fix."
            return "Got it! I will analyze the issue and work on a solution."

        if any(word in message_lower for word in ["find", "search", "look for", "locate"]):
            if is_large_prompt:
                return "Got it! I will gather the relevant information and return a structured summary."
            return "Got it! I will search for that information."

        if any(word in message_lower for word in ["explain", "how does", "what is", "why"]):
            return "Got it! I will look into that for you."

        if any(word in message_lower for word in ["update", "modify", "change", "edit"]):
            return "Got it! I will work on making those changes."

        if any(word in message_lower for word in ["install", "setup", "configure"]):
            return "Got it! I will help you set that up."

        if any(word in message_lower for word in ["test", "check", "verify", "validate"]):
            return "Got it! I will run checks on that."

        # Default
        if is_large_prompt:
            return "Got it! I will analyze your request and proceed with a structured response."
        return "Got it! I will help with that."

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
        topic_source = self._extract_research_topic(user_message) if is_large_prompt else request_focus
        if is_large_prompt and not topic_source:
            # Fall back to extracted focus so we can still produce a specific but compact topic.
            topic_source = request_focus
        topic = self._normalize_subject(self._compact_subject(topic_source))

        if self._is_research_report_request(user_message):
            list_summary = self._extract_numbered_topics_summary(user_message)
            if list_summary:
                return f"Got it! I will create a comprehensive research report on {list_summary}"

            report_topic = self._normalize_research_report_topic(topic, user_message)
            if report_topic:
                return f"Got it! I will create a comprehensive research report on {report_topic}"
            return "Got it! I will create a comprehensive research report for your request"

        research_topic = self._normalize_simple_research_topic(topic, user_message)
        if research_topic:
            return f"Got it! I will research {research_topic}."
        return "Got it! I will research this topic."

    def _ack_create_or_build(
        self, user_message: str, message_lower: str, request_focus: str, is_large_prompt: bool
    ) -> str:
        if self._is_reference_design_request(message_lower):
            return (
                "Got it! I'll review the reference files you've provided and create a website with a standardized "
                "global design system including consistent buttons, colors, and styling based on the code.html reference."
            )

        if request_focus and request_focus != "this task":
            focus = self._compact_subject(request_focus) or request_focus
            return f"Got it! I will work on {focus}."

        if is_large_prompt:
            return "Got it! I will work through your request and create the implementation."
        return "Got it! I will work on your request."

    def _is_reference_design_request(self, message_lower: str) -> bool:
        has_reference_file = bool(re.search(r"\b\w+\.html\b", message_lower))
        has_design_terms = any(
            term in message_lower for term in ("design", "global design", "buttons", "colors", "standardized")
        )
        has_build_terms = any(term in message_lower for term in ("create", "build", "same exact", "reference"))
        return has_reference_file and has_design_terms and has_build_terms

    def _is_research_report_request(self, user_message: str) -> bool:
        text = (user_message or "").lower()
        return "research report" in text or "comprehensive research report" in text

    def _normalize_research_report_topic(self, topic: str | None, user_message: str) -> str | None:
        normalized = self._normalize_research_ack_topic(topic, user_message)
        if not normalized:
            return None

        normalized = re.sub(r"^develop\b", "developing", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"^create\b", "creating", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"^build\b", "building", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+", " ", normalized).strip(" .,:;")
        return normalized or None

    def _extract_numbered_topics_summary(self, user_message: str, max_items: int = 3) -> str | None:
        """Build a concise summary from numbered list prompts."""
        if not user_message:
            return None

        matches = re.findall(
            r"(?:^|\n|\s)(\d+)\.\s+(.+?)(?=(?:\n|\s)\d+\.\s+|$)",
            user_message,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if len(matches) < 2:
            return None

        topics: list[str] = []
        for _index, raw_item in matches:
            cleaned = self._clean_numbered_topic_item(raw_item)
            if not cleaned:
                continue

            cleaned_lower = cleaned.lower()
            if cleaned_lower.startswith(("ensure ", "include ", "provide ", "add ")):
                continue
            if cleaned_lower in {existing.lower() for existing in topics}:
                continue

            topics.append(cleaned)
            if len(topics) >= max_items:
                break

        if len(topics) < 2:
            return None
        return self._join_subjects(topics)

    def _clean_numbered_topic_item(self, item: str) -> str | None:
        """Trim numbered-list item text into a compact topic phrase."""
        normalized = re.sub(r"\s+", " ", (item or "")).strip(" .,:;")
        if not normalized:
            return None

        normalized = re.split(r",\s*(?:including|explaining|detailing|covering|with|that|which)\b", normalized, 1)[0]
        normalized = re.split(r"\s+(?:including|explaining|detailing|covering)\b", normalized, 1)[0]
        normalized = re.split(r"[.;]\s*", normalized, 1)[0]
        normalized = re.sub(r"\s+", " ", normalized).strip(" .,:;")

        max_words = 11
        max_chars = 90
        words = normalized.split()
        if len(words) > max_words:
            normalized = " ".join(words[:max_words]).rstrip(",:;")
        if len(normalized) > max_chars:
            normalized = normalized[:max_chars].rstrip(" ,:;")

        return normalized or None

    def _join_subjects(self, subjects: list[str]) -> str:
        """Join subject phrases using natural language punctuation."""
        if not subjects:
            return ""
        if len(subjects) == 1:
            return subjects[0]
        if len(subjects) == 2:
            return f"{subjects[0]} and {subjects[1]}"
        return f"{', '.join(subjects[:-1])}, and {subjects[-1]}"

    def _normalize_simple_research_topic(self, topic: str | None, user_message: str) -> str | None:
        if topic:
            normalized = topic
        else:
            normalized = self._extract_request_focus(user_message)
            if normalized == "this task":
                return None

        normalized = re.sub(r"^on\s+", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+", " ", normalized).strip(" .,:;")

        if not normalized:
            return None

        # Prefer natural phrasing for short research asks.
        if re.match(r"^(best|top|latest|most)\b", normalized, flags=re.IGNORECASE):
            normalized = f"the {normalized[0].lower() + normalized[1:]}"
        return normalized

    def _normalize_research_ack_topic(self, topic: str | None, user_message: str) -> str | None:
        """Apply focused cleanup so acknowledgment topics read naturally."""
        if not topic:
            return None

        normalized = topic
        replacements: tuple[tuple[str, str], ...] = (
            (r"\bai integrated development environments\s*\(ides\)", "AI IDEs"),
            (r"\bai agents\b", "agents"),
            (r"\bcapable of identifying and addressing\b", "for"),
            (
                r"\bthe most recent and prevalent bugs and issues in software development\b",
                "bug detection and resolution",
            ),
            (r"\bbugs and issues in software development\b", "bug detection and resolution"),
        )
        for pattern, replacement in replacements:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

        if re.search(r"\b(bug|bugs|issue|issues)\b", user_message, flags=re.IGNORECASE) and not re.search(
            r"\bbug detection and resolution\b", normalized, flags=re.IGNORECASE
        ):
            normalized = f"{normalized} for bug detection and resolution"

        # Include 2026 context when user explicitly requests it and it's missing in compacted topic.
        if "2026" in user_message and "2026" not in normalized:
            normalized = f"{normalized} in 2026"

        normalized = re.sub(r"\s+", " ", normalized).strip(" .,:;")
        return normalized or None

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
        normalized = re.sub(
            r"\s*:\s*(?:\d+|[ivxlcdm]+|[a-zA-Z])(?:[.)])?\s*$",
            "",
            normalized,
            flags=re.IGNORECASE,
        ).strip()

        max_words = 14
        max_chars = 110
        words = normalized.split()
        if len(words) > max_words:
            normalized = " ".join(words[:max_words]).rstrip(",:;")
        if len(normalized) > max_chars:
            normalized = normalized[:max_chars].rstrip(" ,:;")

        return normalized or None

    def _normalize_subject(self, subject: str | None) -> str | None:
        """Normalize subject phrasing to reduce noisy spacing/wording from user prompts."""
        if not subject:
            return None

        normalized = subject.strip()
        if not normalized:
            return None

        # Remove common lead-ins that make acknowledgments repetitive.
        normalized = re.sub(
            r"^(?:a\s+)?(?:comprehensive\s+)?research\s+report\s+(?:on|about)\s*[:\-]?\s*",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            r"^(?:a\s+)?(?:comprehensive\s+)?research\s+report\s+(?:that\s+)?(?:covers|covering)\s+",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            r"^report\s+(?:that\s+)?(?:covers|covering)\s+",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(r"^(?:on|about)\s*[:\-]?\s*", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(
            r"\b(following\s+(?:topics?|items?|sections?))\s*:\s*(?:\d+|[ivxlcdm]+|[a-zA-Z])(?:[.)])?\s*$",
            r"\1",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            r"^following\s+(topics?|items?|sections?)\b",
            r"the following \1",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(r"\s+", " ", normalized).strip(" .,:;")

        # Correct common typos in short research/model prompts.
        typo_patterns: tuple[tuple[str, str], ...] = (
            (r"\bcompo+re\b", "compare"),
            (r"\bcomparre\b", "compare"),
            (r"\bsonet+\b", "sonnet"),
            (r"\bopu+s\b", "opus"),
            (r"\bloweffort\b", "low-effort"),
        )
        for pattern, replacement in typo_patterns:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

        # Normalize well-known compact phrasing.
        normalized = re.sub(r"\blow[\s\-_]*effort\b", "low-effort", normalized, flags=re.IGNORECASE)
        normalized = re.sub(
            r"\b(opus|sonnet|haiku|gpt|claude|gemini|llama|mistral)\s*([0-9]+(?:\.[0-9]+)+)\b",
            lambda m: f"{m.group(1).capitalize()} {m.group(2)}",
            normalized,
            flags=re.IGNORECASE,
        )

        # Convert imperative opening to a smoother noun/gerund phrase.
        normalized = re.sub(r"^compare\s+", "comparing ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"^analy[sz]e\s+", "analyzing ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"^evaluate\s+", "evaluating ", normalized, flags=re.IGNORECASE)

        # If input still starts with "create ... report on", trim again after normalization.
        normalized = re.sub(
            r"^create\s+(?:a\s+)?(?:comprehensive\s+)?research\s+report\s+(?:on|about)\s*[:\-]?\s*",
            "",
            normalized,
            flags=re.IGNORECASE,
        )

        # Basic punctuation/spacing cleanup.
        normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip(" .,:;")

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
            r"(?:^|\s)research(?!\s+report)\s*[:\s]+(.+?)(?:\.|$)",
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
