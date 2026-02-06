"""
Security analyzer for detecting vulnerabilities in code.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Vulnerability:
    """Represents a security vulnerability found in the code."""

    type: str
    severity: str
    description: str
    file_path: str
    line_number: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type,
            "severity": self.severity,
            "description": self.description,
            "file_path": self.file_path,
            "line_number": self.line_number,
        }


@dataclass
class ScanVulnerability:
    """Vulnerability result from scan_code method with additional fields."""

    vulnerability_type: str
    severity: str
    description: str
    file_path: str
    line_number: int
    code_snippet: str


# Vulnerability patterns for Python
PYTHON_PATTERNS: list[tuple[str, str, str, str]] = [
    # (pattern, vulnerability_type, severity, description)
    # SQL Injection patterns - detect f-strings or % formatting with SQL keywords
    (
        r'f["\']SELECT\s+.*\{',
        "SQL_INJECTION",
        "HIGH",
        "Potential SQL injection via f-string interpolation",
    ),
    (
        r'f["\']INSERT\s+.*\{',
        "SQL_INJECTION",
        "HIGH",
        "Potential SQL injection via f-string interpolation",
    ),
    (
        r'f["\']UPDATE\s+.*\{',
        "SQL_INJECTION",
        "HIGH",
        "Potential SQL injection via f-string interpolation",
    ),
    (
        r'f["\']DELETE\s+.*\{',
        "SQL_INJECTION",
        "HIGH",
        "Potential SQL injection via f-string interpolation",
    ),
    (
        r'["\']SELECT\s+.*%\s*(?:s|d|\()',
        "SQL_INJECTION",
        "HIGH",
        "Potential SQL injection via % string formatting",
    ),
    (
        r'["\']INSERT\s+.*%\s*(?:s|d|\()',
        "SQL_INJECTION",
        "HIGH",
        "Potential SQL injection via % string formatting",
    ),
    (
        r'["\']UPDATE\s+.*%\s*(?:s|d|\()',
        "SQL_INJECTION",
        "HIGH",
        "Potential SQL injection via % string formatting",
    ),
    (
        r'["\']DELETE\s+.*%\s*(?:s|d|\()',
        "SQL_INJECTION",
        "HIGH",
        "Potential SQL injection via % string formatting",
    ),
    # Command Injection patterns
    (
        r'os\.system\s*\(\s*f["\']',
        "COMMAND_INJECTION",
        "CRITICAL",
        "Potential command injection via os.system with f-string",
    ),
    (
        r'os\.system\s*\(\s*["\'].*%',
        "COMMAND_INJECTION",
        "CRITICAL",
        "Potential command injection via os.system with % formatting",
    ),
    (
        r'os\.system\s*\(\s*.*\+',
        "COMMAND_INJECTION",
        "CRITICAL",
        "Potential command injection via os.system with concatenation",
    ),
    (
        r'subprocess\.(?:run|call|Popen)\s*\([^)]*shell\s*=\s*True',
        "COMMAND_INJECTION",
        "CRITICAL",
        "Potential command injection via subprocess with shell=True",
    ),
    # Hardcoded secrets patterns
    (
        r'(?:API_KEY|APIKEY|api_key)\s*=\s*["\'][^"\']{8,}["\']',
        "HARDCODED_SECRET",
        "MEDIUM",
        "Potential hardcoded API key",
    ),
    (
        r'(?:PASSWORD|password|passwd)\s*=\s*["\'][^"\']+["\']',
        "HARDCODED_SECRET",
        "MEDIUM",
        "Potential hardcoded password",
    ),
    (
        r'(?:SECRET_KEY|secret_key|SECRET|secret)\s*=\s*["\'][^"\']{8,}["\']',
        "HARDCODED_SECRET",
        "MEDIUM",
        "Potential hardcoded secret key",
    ),
    (
        r'(?:AUTH_TOKEN|auth_token|TOKEN|token)\s*=\s*["\'][^"\']{8,}["\']',
        "HARDCODED_SECRET",
        "MEDIUM",
        "Potential hardcoded auth token",
    ),
]

# Safe patterns that should NOT trigger vulnerabilities (exclusions)
SAFE_PATTERNS: list[str] = [
    r'os\.environ\.get',
    r'os\.getenv',
    r'\.env',
    r'environ\[',
]


class SecurityAnalyzer:
    """
    Analyzes code for security vulnerabilities.
    """

    # Supported languages
    SUPPORTED_LANGUAGES = {"python", "py"}

    def __init__(self, strict_mode: bool = False):
        """
        Initialize security analyzer.

        Args:
            strict_mode: If True, use stricter detection rules
        """
        self.strict_mode = strict_mode

    def _is_safe_pattern(self, line: str) -> bool:
        """Check if a line contains a safe pattern (e.g., env variable lookup)."""
        for pattern in SAFE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False

    def scan_code(
        self, code: str, file_path: str, language: str
    ) -> list[ScanVulnerability]:
        """
        Scan code for security vulnerabilities.

        Args:
            code: Source code to analyze
            file_path: Path to the file
            language: Programming language

        Returns:
            List of ScanVulnerability objects found
        """
        vulnerabilities: list[ScanVulnerability] = []

        # Only support Python for now
        if language.lower() not in self.SUPPORTED_LANGUAGES:
            return vulnerabilities

        lines = code.split("\n")

        for line_num, line in enumerate(lines, start=1):
            # Skip safe patterns (env variable lookups, etc.)
            if self._is_safe_pattern(line):
                continue

            # Check each vulnerability pattern
            for pattern, vuln_type, severity, description in PYTHON_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    vulnerabilities.append(
                        ScanVulnerability(
                            vulnerability_type=vuln_type,
                            severity=severity,
                            description=description,
                            file_path=file_path,
                            line_number=line_num,
                            code_snippet=line.strip(),
                        )
                    )

        return vulnerabilities

    def analyze(self, code: str, file_path: str, language: str) -> list[Vulnerability]:
        """
        Analyze code for security vulnerabilities.

        Args:
            code: Source code to analyze
            file_path: Path to the file
            language: Programming language

        Returns:
            List of Vulnerability objects found
        """
        # Convert scan_code results to Vulnerability objects
        scan_results = self.scan_code(code, file_path, language)
        return [
            Vulnerability(
                type=v.vulnerability_type,
                severity=v.severity,
                description=v.description,
                file_path=v.file_path,
                line_number=v.line_number,
            )
            for v in scan_results
        ]

    def get_summary(self, vulnerabilities: list[Vulnerability]) -> dict[str, Any]:
        """
        Get summary of vulnerabilities.

        Args:
            vulnerabilities: List of vulnerabilities

        Returns:
            Dictionary with counts by severity
        """
        critical = len([v for v in vulnerabilities if v.severity.lower() == "critical"])
        high = len([v for v in vulnerabilities if v.severity.lower() == "high"])
        medium = len([v for v in vulnerabilities if v.severity.lower() == "medium"])
        low = len([v for v in vulnerabilities if v.severity.lower() == "low"])

        return {
            "total": len(vulnerabilities),
            "critical_count": critical,
            "high_count": high,
            "medium_count": medium,
            "low_count": low,
        }
