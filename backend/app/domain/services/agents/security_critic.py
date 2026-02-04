"""Security critic for code execution safety review.

This module implements a SecurityCritic that reviews code for dangerous
patterns and provides risk assessment with recommendations before execution.

Usage:
    critic = SecurityCritic(llm=llm_instance)  # With LLM for semantic analysis
    critic = SecurityCritic()  # Pattern-only mode (no LLM)

    # Review code before execution
    result = await critic.review_code(
        code="os.system('ls -la')",
        language="python",
        context="User wants to list files"
    )

    if not result.safe:
        # Block execution, show issues and recommendations
        print(result.issues)
        print(result.recommendations)
"""

import json
import logging
import re
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Risk level for security assessment."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityResult(BaseModel):
    """Result of a security review.

    Attributes:
        safe: Whether the code is safe to execute.
        risk_level: The assessed risk level.
        issues: List of security issues found.
        recommendations: List of recommended mitigations.
        patterns_detected: List of dangerous patterns found.
    """

    safe: bool
    risk_level: RiskLevel
    issues: list[str] = []
    recommendations: list[str] = []
    patterns_detected: list[str] = []


class SecurityCritic:
    """Security critic for code execution safety review.

    The SecurityCritic reviews code for dangerous patterns and potential
    security vulnerabilities before execution. It combines static pattern
    detection with optional LLM-based semantic analysis.

    Attributes:
        llm: Optional language model for semantic analysis.
        SYSTEM_PROMPT: Class attribute with security review instructions.
        DANGEROUS_PATTERNS: Dict of dangerous patterns by language.
    """

    SYSTEM_PROMPT = """You are a security critic reviewing code for execution safety.

Analyze the provided code for security vulnerabilities and dangerous operations.

Return a JSON object with:
- "safe": boolean (true if code is safe to execute)
- "risk_level": string ("low", "medium", "high", "critical")
- "issues": array of strings (security problems found)
- "recommendations": array of strings (how to mitigate risks)
- "patterns_detected": array of strings (dangerous patterns identified)

Consider:
1. Command injection vulnerabilities
2. File system attacks (deletion, permission changes)
3. Code injection (eval, exec, __import__)
4. Hardcoded secrets or credentials
5. Network-based attacks (curl|bash, wget|sh)
6. Resource exhaustion possibilities
7. Privilege escalation attempts

Be strict about security. When in doubt, mark as unsafe.

IMPORTANT: Return ONLY valid JSON, no additional text or explanation."""

    DANGEROUS_PATTERNS: ClassVar[dict[str, list[tuple[str, str]]]] = {
        "python": [
            (r"os\.system\s*\(", "os.system - command execution"),
            (r"subprocess\.[^(]+\([^)]*shell\s*=\s*True", "subprocess with shell=True - command injection risk"),
            (r"\beval\s*\(", "eval() - arbitrary code execution"),
            (r"\bexec\s*\(", "exec() - arbitrary code execution"),
            (r"__import__\s*\(", "__import__() - dynamic module loading"),
            (r"rm\s+-rf\s+/", "rm -rf / - destructive file deletion"),
            (r"rm\s+-rf\s+~", "rm -rf ~ - home directory deletion"),
            (r"chmod\s+777", "chmod 777 - overly permissive permissions"),
            (r"chmod\s+-R\s+777", "chmod -R 777 - recursive permissive permissions"),
            (r"password\s*=\s*['\"][^'\"]+['\"]", "Hardcoded password detected"),
            (r"api_key\s*=\s*['\"][^'\"]+['\"]", "Hardcoded api_key detected"),
            (r"secret\s*=\s*['\"][^'\"]+['\"]", "Hardcoded secret detected"),
        ],
        "bash": [
            (r"rm\s+-rf\s+/\s*$", "rm -rf / - root filesystem deletion"),
            (r"rm\s+-rf\s+/[^a-zA-Z]", "rm -rf / - root filesystem deletion"),
            (r"dd\s+.*of\s*=\s*/dev/", "dd to device - disk overwrite"),
            (r"chmod\s+-R\s+777\s+/", "chmod -R 777 / - root permission change"),
            (r"curl\s+[^|]+\|\s*bash", "curl|bash - remote code execution"),
            (r"curl\s+[^|]+\|\s*sh", "curl|sh - remote code execution"),
            (r"wget\s+[^|]+\|\s*bash", "wget|bash - remote code execution"),
            (r"wget\s+[^|]+\|\s*sh", "wget|sh - remote code execution"),
            (r"wget\s+[^-]+\s+-O\s*-\s*\|\s*sh", "wget|sh - remote code execution"),
            (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;", "Fork bomb detected"),
        ],
    }

    def __init__(self, llm: Any | None = None) -> None:
        """Initialize the SecurityCritic.

        Args:
            llm: Optional language model instance for semantic analysis.
                 If None, only static pattern detection is used.
        """
        self.llm = llm

    def detect_dangerous_patterns(
        self,
        code: str,
        language: str = "python",
    ) -> list[str]:
        """Detect dangerous patterns in code using static analysis.

        Args:
            code: The code to analyze.
            language: Programming language ("python", "bash", etc.).

        Returns:
            List of detected dangerous pattern descriptions.
        """
        detected: list[str] = []

        # Get patterns for the language, fall back to python
        patterns = self.DANGEROUS_PATTERNS.get(
            language.lower(),
            self.DANGEROUS_PATTERNS.get("python", []),
        )

        # Check each pattern
        for pattern, description in patterns:
            if re.search(pattern, code, re.IGNORECASE | re.MULTILINE):
                detected.append(description)

        logger.debug(
            "Pattern detection for %s code: found %d patterns",
            language,
            len(detected),
        )

        return detected

    async def review_code(
        self,
        code: str,
        language: str = "python",
        context: str | None = None,
    ) -> SecurityResult:
        """Review code for security issues.

        This method performs both static pattern detection and optional
        LLM-based semantic analysis to identify security risks.

        Args:
            code: The code to review.
            language: Programming language ("python", "bash", etc.).
            context: Optional context about what the code is meant to do.

        Returns:
            SecurityResult with safety assessment and recommendations.
        """
        logger.debug(
            "Reviewing %s code (%d chars), context: %s",
            language,
            len(code),
            context[:50] if context else "none",
        )

        # Run static pattern detection first
        patterns_detected = self.detect_dangerous_patterns(code, language)

        # If no LLM, return result based on patterns only
        if self.llm is None:
            return self._create_pattern_only_result(patterns_detected)

        # Build prompt with code and static findings
        user_content = self._build_user_prompt(code, language, context, patterns_detected)

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        # Call the LLM
        response = await self.llm.chat(messages)

        # Extract content from response
        content = self._extract_content(response)

        # Parse the response
        result = self._parse_response(content, patterns_detected)

        logger.debug(
            "Security review complete: safe=%s, risk_level=%s, issues=%d",
            result.safe,
            result.risk_level.value,
            len(result.issues),
        )

        return result

    def _create_pattern_only_result(
        self,
        patterns_detected: list[str],
    ) -> SecurityResult:
        """Create a SecurityResult based on static patterns only.

        Args:
            patterns_detected: List of detected dangerous patterns.

        Returns:
            SecurityResult based on pattern analysis.
        """
        if not patterns_detected:
            return SecurityResult(
                safe=True,
                risk_level=RiskLevel.LOW,
                issues=[],
                recommendations=[],
                patterns_detected=[],
            )

        # Determine risk level based on number and severity of patterns
        num_patterns = len(patterns_detected)
        if num_patterns >= 3:
            risk_level = RiskLevel.CRITICAL
        elif num_patterns >= 2:
            risk_level = RiskLevel.HIGH
        else:
            risk_level = RiskLevel.MEDIUM

        # Check for critical patterns that escalate risk
        critical_patterns = ["rm -rf /", "fork bomb", "root filesystem", "device"]
        for pattern in patterns_detected:
            pattern_lower = pattern.lower()
            if any(crit in pattern_lower for crit in critical_patterns):
                risk_level = RiskLevel.CRITICAL
                break

        return SecurityResult(
            safe=False,
            risk_level=risk_level,
            issues=[f"Dangerous pattern detected: {p}" for p in patterns_detected],
            recommendations=["Review code carefully before execution"],
            patterns_detected=patterns_detected,
        )

    def _build_user_prompt(
        self,
        code: str,
        language: str,
        context: str | None,
        patterns_detected: list[str],
    ) -> str:
        """Build the user prompt for LLM review.

        Args:
            code: The code to review.
            language: Programming language.
            context: Optional context.
            patterns_detected: Patterns from static analysis.

        Returns:
            Formatted prompt string.
        """
        parts = [
            f"## Language\n{language}",
            f"## Code to Review\n```{language}\n{code}\n```",
        ]

        if context:
            parts.append(f"## Context\n{context}")

        if patterns_detected:
            patterns_text = "\n".join(f"- {p}" for p in patterns_detected)
            parts.append(f"## Static Analysis Findings\n{patterns_text}")

        return "\n\n".join(parts)

    def _extract_content(self, response: Any) -> str:
        """Extract content string from LLM response.

        Args:
            response: The LLM response (object or string).

        Returns:
            Content string.
        """
        if hasattr(response, "content"):
            return response.content
        return str(response)

    def _parse_response(
        self,
        content: str,
        fallback_patterns: list[str],
    ) -> SecurityResult:
        """Parse LLM response into SecurityResult.

        Handles:
        - Plain JSON
        - JSON wrapped in markdown code blocks
        - Non-JSON fallback

        Args:
            content: Raw response content from LLM.
            fallback_patterns: Patterns to use in fallback result.

        Returns:
            Parsed SecurityResult.
        """
        # Try to extract JSON from markdown code blocks
        cleaned_content = self._strip_markdown_code_blocks(content)

        try:
            parsed = json.loads(cleaned_content)

            # Parse risk level from string
            risk_level_str = parsed.get("risk_level", "high")
            try:
                risk_level = RiskLevel(risk_level_str.lower())
            except ValueError:
                risk_level = RiskLevel.HIGH

            return SecurityResult(
                safe=parsed.get("safe", False),
                risk_level=risk_level,
                issues=parsed.get("issues", []),
                recommendations=parsed.get("recommendations", []),
                patterns_detected=parsed.get("patterns_detected", []),
            )
        except json.JSONDecodeError:
            logger.warning("Failed to parse security review response as JSON, using fallback")
            return self._fallback_parse(content, fallback_patterns)

    def _strip_markdown_code_blocks(self, content: str) -> str:
        """Strip markdown code blocks from content.

        Args:
            content: Raw content possibly with code blocks.

        Returns:
            Content with code blocks stripped.
        """
        # Pattern for code blocks with or without language tag
        code_block_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        match = re.search(code_block_pattern, content)

        if match:
            return match.group(1).strip()

        return content.strip()

    def _fallback_parse(
        self,
        content: str,
        patterns_detected: list[str],
    ) -> SecurityResult:
        """Fallback parsing for non-JSON responses.

        When LLM doesn't return valid JSON, defaults to unsafe
        to maintain security posture.

        Args:
            content: Non-JSON response content.
            patterns_detected: Patterns from static analysis.

        Returns:
            SecurityResult defaulting to unsafe.
        """
        # Default to unsafe when we can't parse the response
        return SecurityResult(
            safe=False,
            risk_level=RiskLevel.HIGH,
            issues=["Unable to parse security review response"],
            recommendations=["Manual review required before execution"],
            patterns_detected=patterns_detected,
        )
