"""
Security analyzer for detecting vulnerabilities in code.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Vulnerability:
    """Represents a security vulnerability found in the code."""

    vulnerability_type: str
    severity: str
    description: str
    file_path: str
    line_number: int
    code_snippet: str = ""
    recommendation: str = ""
    cwe_id: str | None = None
    # Keep 'type' as alias for backwards compatibility
    type: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        """Set type alias after initialization."""
        if not self.type:
            self.type = self.vulnerability_type

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.vulnerability_type,
            "vulnerability_type": self.vulnerability_type,
            "severity": self.severity,
            "description": self.description,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "code_snippet": self.code_snippet,
            "recommendation": self.recommendation,
            "cwe_id": self.cwe_id,
        }


@dataclass
class SecurityPattern:
    """A security pattern to detect vulnerabilities."""

    name: str
    vulnerability_type: str
    severity: str
    pattern: re.Pattern[str]
    description: str
    recommendation: str = ""
    cwe_id: str | None = None
    # Optional: patterns that indicate safe usage (to exclude false positives)
    safe_patterns: list[re.Pattern[str]] = field(default_factory=list)


# Python-specific security patterns
PYTHON_PATTERNS: list[SecurityPattern] = [
    # SQL Injection patterns
    SecurityPattern(
        name="sql_injection_fstring_execute",
        vulnerability_type="SQL_INJECTION",
        severity="HIGH",
        pattern=re.compile(
            r'(?:execute|executemany|cursor\.execute)\s*\(\s*f["\'].*?\{',
            re.IGNORECASE,
        ),
        description="Potential SQL injection via f-string formatting in execute()",
        recommendation="Use parameterized queries with placeholders (?, %s) instead of string formatting",
        cwe_id="CWE-89",
    ),
    SecurityPattern(
        name="sql_injection_fstring_query",
        vulnerability_type="SQL_INJECTION",
        severity="HIGH",
        pattern=re.compile(
            r'=\s*f["\'](?:SELECT|INSERT|UPDATE|DELETE|DROP)\s+.*?\{',
            re.IGNORECASE,
        ),
        description="Potential SQL injection via f-string with SQL keywords",
        recommendation="Use parameterized queries with placeholders (?, %s) instead of string formatting",
        cwe_id="CWE-89",
    ),
    SecurityPattern(
        name="sql_injection_percent_execute",
        vulnerability_type="SQL_INJECTION",
        severity="HIGH",
        pattern=re.compile(
            r'(?:execute|executemany)\s*\([^)]*["\'].*?%[sd].*?["\']\s*%',
            re.IGNORECASE,
        ),
        description="Potential SQL injection via % string formatting in execute()",
        recommendation="Use parameterized queries with placeholders (?, %s) instead of % formatting",
        cwe_id="CWE-89",
    ),
    SecurityPattern(
        name="sql_injection_percent_query",
        vulnerability_type="SQL_INJECTION",
        severity="HIGH",
        pattern=re.compile(
            r'=\s*["\'](?:SELECT|INSERT|UPDATE|DELETE|DROP)\s+.*?%[sd].*?["\']\s*%',
            re.IGNORECASE,
        ),
        description="Potential SQL injection via % string formatting with SQL keywords",
        recommendation="Use parameterized queries with placeholders (?, %s) instead of % formatting",
        cwe_id="CWE-89",
    ),
    SecurityPattern(
        name="sql_injection_format",
        vulnerability_type="SQL_INJECTION",
        severity="HIGH",
        pattern=re.compile(
            r"(?:execute|executemany)\s*\([^)]*\.format\s*\(",
            re.IGNORECASE,
        ),
        description="Potential SQL injection via .format() in execute()",
        recommendation="Use parameterized queries with placeholders (?, %s) instead of .format()",
        cwe_id="CWE-89",
    ),
    SecurityPattern(
        name="sql_injection_concat",
        vulnerability_type="SQL_INJECTION",
        severity="HIGH",
        pattern=re.compile(
            r'(?:execute|executemany)\s*\(\s*["\'](?:SELECT|INSERT|UPDATE|DELETE|DROP)'
            r'[^"\']*["\']\s*\+',
            re.IGNORECASE,
        ),
        description="Potential SQL injection via string concatenation in execute()",
        recommendation="Use parameterized queries with placeholders (?, %s) instead of string concatenation",
        cwe_id="CWE-89",
    ),
    # Command Injection patterns
    SecurityPattern(
        name="command_injection_os_system",
        vulnerability_type="COMMAND_INJECTION",
        severity="CRITICAL",
        pattern=re.compile(
            r'os\.system\s*\(\s*f["\']',
            re.IGNORECASE,
        ),
        description="Potential command injection via os.system() with f-string",
        recommendation="Use subprocess.run() with a list of arguments and shell=False",
        cwe_id="CWE-78",
    ),
    SecurityPattern(
        name="command_injection_os_popen",
        vulnerability_type="COMMAND_INJECTION",
        severity="CRITICAL",
        pattern=re.compile(
            r'os\.popen\s*\(\s*f["\']',
            re.IGNORECASE,
        ),
        description="Potential command injection via os.popen() with f-string",
        recommendation="Use subprocess.run() with a list of arguments and shell=False",
        cwe_id="CWE-78",
    ),
    SecurityPattern(
        name="command_injection_subprocess_shell",
        vulnerability_type="COMMAND_INJECTION",
        severity="CRITICAL",
        pattern=re.compile(
            r"subprocess\.(?:run|call|Popen|check_output|check_call)\s*\([^)]*"
            r"shell\s*=\s*True",
            re.IGNORECASE,
        ),
        description="Potential command injection via subprocess with shell=True",
        recommendation="Pass command as a list of arguments and set shell=False",
        cwe_id="CWE-78",
    ),
    SecurityPattern(
        name="command_injection_eval",
        vulnerability_type="COMMAND_INJECTION",
        severity="CRITICAL",
        pattern=re.compile(
            r'\beval\s*\(\s*(?:f["\']|[^"\'\)]+\+)',
        ),
        description="Potential code injection via eval() with dynamic input",
        recommendation="Avoid eval() with user input; use ast.literal_eval() for safe parsing",
        cwe_id="CWE-94",
    ),
    SecurityPattern(
        name="command_injection_exec",
        vulnerability_type="COMMAND_INJECTION",
        severity="CRITICAL",
        pattern=re.compile(
            r'\bexec\s*\(\s*(?:f["\']|[^"\'\)]+\+)',
        ),
        description="Potential code injection via exec() with dynamic input",
        recommendation="Avoid exec() with user input; refactor to use safer alternatives",
        cwe_id="CWE-94",
    ),
    # Hardcoded Secrets patterns
    SecurityPattern(
        name="hardcoded_api_key",
        vulnerability_type="HARDCODED_SECRET",
        severity="MEDIUM",
        pattern=re.compile(
            r'(?:api[_-]?key|apikey)\s*=\s*["\'][^"\']{8,}["\']',
            re.IGNORECASE,
        ),
        description="Potential hardcoded API key",
        recommendation="Store API keys in environment variables or a secrets manager",
        cwe_id="CWE-798",
        safe_patterns=[
            re.compile(r"os\.(?:environ|getenv)", re.IGNORECASE),
            re.compile(r'\.get\s*\(["\']', re.IGNORECASE),
        ],
    ),
    SecurityPattern(
        name="hardcoded_password",
        vulnerability_type="HARDCODED_SECRET",
        severity="MEDIUM",
        pattern=re.compile(
            r'(?:password|passwd|pwd|db_password|db_passwd)\s*=\s*["\'][^"\']{4,}["\']',
            re.IGNORECASE,
        ),
        description="Potential hardcoded password",
        recommendation="Store passwords in environment variables or a secrets manager",
        cwe_id="CWE-798",
        safe_patterns=[
            re.compile(r"os\.(?:environ|getenv)", re.IGNORECASE),
            re.compile(r'\.get\s*\(["\']', re.IGNORECASE),
        ],
    ),
    SecurityPattern(
        name="hardcoded_secret_key",
        vulnerability_type="HARDCODED_SECRET",
        severity="MEDIUM",
        pattern=re.compile(
            r"(?:secret[_-]?key|secretkey|auth[_-]?token|access[_-]?token)\s*=\s*"
            r'["\'][^"\']{8,}["\']',
            re.IGNORECASE,
        ),
        description="Potential hardcoded secret key or token",
        recommendation="Store secret keys and tokens in environment variables or a secrets manager",
        cwe_id="CWE-798",
        safe_patterns=[
            re.compile(r"os\.(?:environ|getenv)", re.IGNORECASE),
            re.compile(r'\.get\s*\(["\']', re.IGNORECASE),
        ],
    ),
    SecurityPattern(
        name="hardcoded_aws_key",
        vulnerability_type="HARDCODED_SECRET",
        severity="MEDIUM",
        pattern=re.compile(
            r"(?:aws[_-]?(?:access[_-]?key|secret[_-]?key|session[_-]?token))\s*=\s*"
            r'["\'][^"\']{8,}["\']',
            re.IGNORECASE,
        ),
        description="Potential hardcoded AWS credential",
        recommendation="Use AWS IAM roles, environment variables, or AWS Secrets Manager",
        cwe_id="CWE-798",
        safe_patterns=[
            re.compile(r"os\.(?:environ|getenv)", re.IGNORECASE),
            re.compile(r'\.get\s*\(["\']', re.IGNORECASE),
        ],
    ),
    SecurityPattern(
        name="hardcoded_private_key",
        vulnerability_type="HARDCODED_SECRET",
        severity="MEDIUM",
        pattern=re.compile(
            r'(?:private[_-]?key|priv[_-]?key)\s*=\s*["\'][^"\']{8,}["\']',
            re.IGNORECASE,
        ),
        description="Potential hardcoded private key",
        recommendation="Store private keys in secure files with restricted permissions or use a secrets manager",
        cwe_id="CWE-798",
        safe_patterns=[
            re.compile(r"os\.(?:environ|getenv)", re.IGNORECASE),
            re.compile(r'\.get\s*\(["\']', re.IGNORECASE),
        ],
    ),
]


class SecurityAnalyzer:
    """
    Analyzes code for security vulnerabilities.
    """

    def __init__(self, strict_mode: bool = False):
        """
        Initialize security analyzer.

        Args:
            strict_mode: If True, use stricter detection rules
        """
        self.strict_mode = strict_mode
        self._patterns: dict[str, list[SecurityPattern]] = {
            "python": PYTHON_PATTERNS,
        }

    def scan_code(self, code: str, file_path: str, language: str) -> list[Vulnerability]:
        """
        Scan code for security vulnerabilities using regex patterns.

        Args:
            code: Source code to scan
            file_path: Path to the file being scanned
            language: Programming language (e.g., 'python')

        Returns:
            List of vulnerabilities found
        """
        language_lower = language.lower()

        # Only Python is supported for now
        if language_lower not in self._patterns:
            logger.debug(f"Language '{language}' not supported for security scanning")
            return []

        patterns = self._patterns[language_lower]
        vulnerabilities: list[Vulnerability] = []
        lines = code.split("\n")

        for line_num, line in enumerate(lines, start=1):
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("#"):
                continue

            for pattern in patterns:
                if pattern.pattern.search(line):
                    # Check for safe patterns that indicate false positive
                    is_safe = False
                    for safe_pattern in pattern.safe_patterns:
                        if safe_pattern.search(line):
                            is_safe = True
                            break

                    if not is_safe:
                        vuln = Vulnerability(
                            vulnerability_type=pattern.vulnerability_type,
                            severity=pattern.severity,
                            description=pattern.description,
                            file_path=file_path,
                            line_number=line_num,
                            code_snippet=line.strip(),
                            recommendation=pattern.recommendation,
                            cwe_id=pattern.cwe_id,
                        )
                        vulnerabilities.append(vuln)
                        logger.debug(f"Found {pattern.vulnerability_type} at {file_path}:{line_num}")

        return vulnerabilities

    def analyze(self, code: str, file_path: str, language: str) -> list[Vulnerability]:
        """
        Analyze code for security vulnerabilities.

        This is the main entry point that delegates to scan_code.

        Args:
            code: Source code to analyze
            file_path: Path to the file
            language: Programming language

        Returns:
            List of vulnerabilities found
        """
        return self.scan_code(code, file_path, language)

    def get_summary(self, vulnerabilities: list[Vulnerability]) -> dict[str, Any]:
        """
        Get summary of vulnerabilities.

        Args:
            vulnerabilities: List of vulnerabilities

        Returns:
            Dictionary with counts by severity
        """
        critical = len([v for v in vulnerabilities if v.severity.upper() == "CRITICAL"])
        high = len([v for v in vulnerabilities if v.severity.upper() == "HIGH"])
        medium = len([v for v in vulnerabilities if v.severity.upper() == "MEDIUM"])
        low = len([v for v in vulnerabilities if v.severity.upper() == "LOW"])

        return {
            "total": len(vulnerabilities),
            "critical_count": critical,
            "high_count": high,
            "medium_count": medium,
            "low_count": low,
            "by_severity": {
                "critical": critical,
                "high": high,
                "medium": medium,
                "low": low,
            },
        }
