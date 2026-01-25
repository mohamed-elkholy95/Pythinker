"""
Security vulnerability analyzer for code analysis.

Detects common security vulnerabilities including:
- SQL injection
- Cross-site scripting (XSS)
- Hardcoded secrets (API keys, passwords)
- Insecure function usage
- Insecure deserialization
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)


class VulnerabilitySeverity(str, Enum):
    """Severity levels for vulnerabilities."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class VulnerabilityType(str, Enum):
    """Types of security vulnerabilities."""
    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    HARDCODED_SECRET = "hardcoded_secret"
    INSECURE_FUNCTION = "insecure_function"
    INSECURE_DESERIALIZATION = "insecure_deserialization"
    PATH_TRAVERSAL = "path_traversal"
    COMMAND_INJECTION = "command_injection"
    INSECURE_RANDOM = "insecure_random"
    WEAK_CRYPTO = "weak_crypto"
    OPEN_REDIRECT = "open_redirect"


@dataclass
class Vulnerability:
    """A detected security vulnerability."""
    type: VulnerabilityType
    severity: VulnerabilitySeverity
    description: str
    file_path: str
    line_number: int
    code_snippet: str
    recommendation: str
    cwe_id: Optional[str] = None
    confidence: float = 0.8

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "description": self.description,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "code_snippet": self.code_snippet[:200],
            "recommendation": self.recommendation,
            "cwe_id": self.cwe_id,
            "confidence": self.confidence,
        }


# Patterns for detecting hardcoded secrets
SECRET_PATTERNS = [
    # API Keys
    (r'api[_-]?key\s*[=:]\s*["\']([a-zA-Z0-9_\-]{20,})["\']', "API key", VulnerabilitySeverity.HIGH),
    (r'apikey\s*[=:]\s*["\']([a-zA-Z0-9_\-]{20,})["\']', "API key", VulnerabilitySeverity.HIGH),

    # AWS
    (r'AKIA[0-9A-Z]{16}', "AWS Access Key", VulnerabilitySeverity.CRITICAL),
    (r'aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*["\']([a-zA-Z0-9/+=]{40})["\']', "AWS Secret Key", VulnerabilitySeverity.CRITICAL),

    # Passwords
    (r'password\s*[=:]\s*["\']([^"\']{8,})["\']', "Hardcoded password", VulnerabilitySeverity.HIGH),
    (r'passwd\s*[=:]\s*["\']([^"\']{8,})["\']', "Hardcoded password", VulnerabilitySeverity.HIGH),
    (r'secret\s*[=:]\s*["\']([^"\']{8,})["\']', "Hardcoded secret", VulnerabilitySeverity.HIGH),

    # Private keys
    (r'-----BEGIN (RSA |DSA |EC )?PRIVATE KEY-----', "Private key", VulnerabilitySeverity.CRITICAL),
    (r'-----BEGIN OPENSSH PRIVATE KEY-----', "SSH private key", VulnerabilitySeverity.CRITICAL),

    # Tokens
    (r'token\s*[=:]\s*["\']([a-zA-Z0-9_\-]{20,})["\']', "Token", VulnerabilitySeverity.MEDIUM),
    (r'bearer\s+([a-zA-Z0-9_\-\.]+)', "Bearer token", VulnerabilitySeverity.HIGH),

    # Generic secrets
    (r'client[_-]?secret\s*[=:]\s*["\']([^"\']{8,})["\']', "Client secret", VulnerabilitySeverity.HIGH),
]

# SQL injection patterns
SQL_INJECTION_PATTERNS = [
    # Python string formatting in SQL
    (r'execute\s*\(\s*["\'].*%s.*["\'].*%', "SQL with string formatting"),
    (r'execute\s*\(\s*f["\'].*\{', "SQL with f-string"),
    (r'execute\s*\(\s*["\'].*\+.*["\']', "SQL with concatenation"),
    (r'cursor\.execute\s*\(\s*["\'].*%.*["\']', "Cursor execute with formatting"),

    # JavaScript/Node SQL
    (r'query\s*\(\s*["\'].*\$\{', "SQL with template literal"),
    (r'query\s*\(\s*["\'].*\+', "SQL with concatenation"),
]

# XSS patterns
XSS_PATTERNS = [
    # Python
    (r'\.innerHTML\s*=.*\+', "innerHTML with concatenation"),
    (r'document\.write\s*\(.*\+', "document.write with concatenation"),

    # Template injection
    (r'\{\{.*\|safe\}\}', "Unsafe template variable"),
    (r'Markup\s*\(', "Markup without escaping"),
    (r'safestring', "SafeString usage (verify escaping)"),
]

# Insecure function patterns
INSECURE_FUNCTIONS = {
    "python": [
        (r'\beval\s*\(', "eval() - code execution", VulnerabilitySeverity.CRITICAL),
        (r'\bexec\s*\(', "exec() - code execution", VulnerabilitySeverity.CRITICAL),
        (r'pickle\.loads?\s*\(', "pickle deserialization", VulnerabilitySeverity.HIGH),
        (r'yaml\.load\s*\((?![^)]*Loader\s*=\s*yaml\.SafeLoader)', "yaml.load without SafeLoader", VulnerabilitySeverity.HIGH),
        (r'subprocess\.(?:call|run|Popen)\s*\(.*shell\s*=\s*True', "subprocess with shell=True", VulnerabilitySeverity.HIGH),
        (r'os\.system\s*\(', "os.system - command injection risk", VulnerabilitySeverity.MEDIUM),
        (r'random\.(?:random|randint|choice)\s*\(', "Non-cryptographic random (use secrets for security)", VulnerabilitySeverity.LOW),
        (r'md5\s*\(', "MD5 - weak hash algorithm", VulnerabilitySeverity.MEDIUM),
        (r'sha1\s*\(', "SHA1 - weak hash algorithm", VulnerabilitySeverity.MEDIUM),
    ],
    "javascript": [
        (r'\beval\s*\(', "eval() - code execution", VulnerabilitySeverity.CRITICAL),
        (r'new\s+Function\s*\(', "Function constructor - code execution", VulnerabilitySeverity.CRITICAL),
        (r'innerHTML\s*=', "innerHTML assignment - XSS risk", VulnerabilitySeverity.MEDIUM),
        (r'document\.write\s*\(', "document.write - XSS risk", VulnerabilitySeverity.MEDIUM),
        (r'Math\.random\s*\(', "Math.random - not cryptographically secure", VulnerabilitySeverity.LOW),
    ],
}

# Path traversal patterns
PATH_TRAVERSAL_PATTERNS = [
    (r'\.\./', "Directory traversal pattern"),
    (r'open\s*\([^)]*\+', "File open with concatenation"),
    (r'os\.path\.join\s*\([^)]*request\.', "Path join with user input"),
]


class SecurityAnalyzer:
    """
    Analyzes code for security vulnerabilities.

    Supports Python and JavaScript code analysis using pattern matching.
    For more comprehensive analysis, consider integrating with AST-based tools.
    """

    def __init__(self, strict_mode: bool = False):
        """
        Initialize security analyzer.

        Args:
            strict_mode: If True, lower confidence threshold for detections
        """
        self.strict_mode = strict_mode
        self._min_confidence = 0.5 if strict_mode else 0.7

    def analyze(
        self,
        code: str,
        file_path: str = "unknown",
        language: str = "python",
    ) -> List[Vulnerability]:
        """
        Analyze code for security vulnerabilities.

        Args:
            code: Source code to analyze
            file_path: Path to the file (for reporting)
            language: Programming language (python, javascript)

        Returns:
            List of detected vulnerabilities
        """
        vulnerabilities = []

        # Split code into lines for line number tracking
        lines = code.split('\n')

        # Check for hardcoded secrets
        vulnerabilities.extend(
            self._check_secrets(lines, file_path)
        )

        # Check for SQL injection
        vulnerabilities.extend(
            self._check_sql_injection(lines, file_path)
        )

        # Check for XSS
        vulnerabilities.extend(
            self._check_xss(lines, file_path)
        )

        # Check for insecure functions
        vulnerabilities.extend(
            self._check_insecure_functions(lines, file_path, language)
        )

        # Check for path traversal
        vulnerabilities.extend(
            self._check_path_traversal(lines, file_path)
        )

        return vulnerabilities

    def _check_secrets(
        self,
        lines: List[str],
        file_path: str,
    ) -> List[Vulnerability]:
        """Check for hardcoded secrets."""
        vulnerabilities = []

        for line_num, line in enumerate(lines, 1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('//'):
                continue

            for pattern, name, severity in SECRET_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    vulnerabilities.append(Vulnerability(
                        type=VulnerabilityType.HARDCODED_SECRET,
                        severity=severity,
                        description=f"Potential {name} detected",
                        file_path=file_path,
                        line_number=line_num,
                        code_snippet=line.strip(),
                        recommendation=f"Move {name} to environment variables or secure vault",
                        cwe_id="CWE-798",
                        confidence=0.85,
                    ))
                    break  # One finding per line

        return vulnerabilities

    def _check_sql_injection(
        self,
        lines: List[str],
        file_path: str,
    ) -> List[Vulnerability]:
        """Check for SQL injection vulnerabilities."""
        vulnerabilities = []

        for line_num, line in enumerate(lines, 1):
            for pattern, desc in SQL_INJECTION_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    vulnerabilities.append(Vulnerability(
                        type=VulnerabilityType.SQL_INJECTION,
                        severity=VulnerabilitySeverity.CRITICAL,
                        description=f"Potential SQL injection: {desc}",
                        file_path=file_path,
                        line_number=line_num,
                        code_snippet=line.strip(),
                        recommendation="Use parameterized queries or prepared statements",
                        cwe_id="CWE-89",
                        confidence=0.75,
                    ))
                    break

        return vulnerabilities

    def _check_xss(
        self,
        lines: List[str],
        file_path: str,
    ) -> List[Vulnerability]:
        """Check for XSS vulnerabilities."""
        vulnerabilities = []

        for line_num, line in enumerate(lines, 1):
            for pattern, desc in XSS_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    vulnerabilities.append(Vulnerability(
                        type=VulnerabilityType.XSS,
                        severity=VulnerabilitySeverity.HIGH,
                        description=f"Potential XSS: {desc}",
                        file_path=file_path,
                        line_number=line_num,
                        code_snippet=line.strip(),
                        recommendation="Properly escape user input before rendering",
                        cwe_id="CWE-79",
                        confidence=0.7,
                    ))
                    break

        return vulnerabilities

    def _check_insecure_functions(
        self,
        lines: List[str],
        file_path: str,
        language: str,
    ) -> List[Vulnerability]:
        """Check for insecure function usage."""
        vulnerabilities = []

        patterns = INSECURE_FUNCTIONS.get(language, [])

        for line_num, line in enumerate(lines, 1):
            for pattern, desc, severity in patterns:
                if re.search(pattern, line):
                    vulnerabilities.append(Vulnerability(
                        type=VulnerabilityType.INSECURE_FUNCTION,
                        severity=severity,
                        description=f"Insecure function: {desc}",
                        file_path=file_path,
                        line_number=line_num,
                        code_snippet=line.strip(),
                        recommendation=f"Avoid using {desc.split(' - ')[0]} or use secure alternative",
                        cwe_id="CWE-676",
                        confidence=0.8,
                    ))

        return vulnerabilities

    def _check_path_traversal(
        self,
        lines: List[str],
        file_path: str,
    ) -> List[Vulnerability]:
        """Check for path traversal vulnerabilities."""
        vulnerabilities = []

        for line_num, line in enumerate(lines, 1):
            for pattern, desc in PATH_TRAVERSAL_PATTERNS:
                if re.search(pattern, line):
                    vulnerabilities.append(Vulnerability(
                        type=VulnerabilityType.PATH_TRAVERSAL,
                        severity=VulnerabilitySeverity.HIGH,
                        description=f"Potential path traversal: {desc}",
                        file_path=file_path,
                        line_number=line_num,
                        code_snippet=line.strip(),
                        recommendation="Validate and sanitize file paths, use allowlists",
                        cwe_id="CWE-22",
                        confidence=0.65,
                    ))

        return vulnerabilities

    def get_summary(
        self,
        vulnerabilities: List[Vulnerability],
    ) -> Dict[str, Any]:
        """
        Generate a summary of found vulnerabilities.

        Args:
            vulnerabilities: List of vulnerabilities

        Returns:
            Summary dictionary
        """
        by_severity = {s.value: 0 for s in VulnerabilitySeverity}
        by_type = {t.value: 0 for t in VulnerabilityType}

        for vuln in vulnerabilities:
            by_severity[vuln.severity.value] += 1
            by_type[vuln.type.value] += 1

        return {
            "total": len(vulnerabilities),
            "by_severity": by_severity,
            "by_type": {k: v for k, v in by_type.items() if v > 0},
            "critical_count": by_severity["critical"],
            "high_count": by_severity["high"],
            "files_affected": len(set(v.file_path for v in vulnerabilities)),
        }
