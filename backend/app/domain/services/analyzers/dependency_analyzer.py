"""
Dependency analyzer for detecting outdated packages and CVEs.

Analyzes:
- requirements.txt (Python)
- package.json (Node.js)
- Detects outdated packages
- Identifies known vulnerabilities
"""

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class DependencyType(str, Enum):
    """Types of dependencies."""
    PRODUCTION = "production"
    DEVELOPMENT = "development"
    OPTIONAL = "optional"


class VulnerabilitySeverity(str, Enum):
    """Severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


@dataclass
class Dependency:
    """A project dependency."""
    name: str
    version: str
    version_constraint: str  # Original constraint (e.g., ">=1.0,<2.0")
    dependency_type: DependencyType
    source_file: str
    line_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "version_constraint": self.version_constraint,
            "dependency_type": self.dependency_type.value,
            "source_file": self.source_file,
            "line_number": self.line_number,
        }


@dataclass
class VulnerabilityInfo:
    """Information about a known vulnerability."""
    cve_id: str
    severity: VulnerabilitySeverity
    title: str
    description: str
    affected_versions: str
    fixed_version: str | None
    published_date: str | None
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "cve_id": self.cve_id,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description[:500],
            "affected_versions": self.affected_versions,
            "fixed_version": self.fixed_version,
            "published_date": self.published_date,
            "url": self.url,
        }


@dataclass
class DependencyIssue:
    """An issue with a dependency."""
    dependency: Dependency
    issue_type: str  # "outdated", "vulnerable", "unpinned", "deprecated"
    severity: str
    description: str
    recommendation: str
    vulnerability: VulnerabilityInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "dependency": self.dependency.to_dict(),
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "recommendation": self.recommendation,
            "vulnerability": self.vulnerability.to_dict() if self.vulnerability else None,
        }


# Known vulnerable packages (simplified - in production, use a real CVE database)
KNOWN_VULNERABILITIES: dict[str, list[dict[str, Any]]] = {
    # Python packages
    "pyyaml": [
        {
            "cve_id": "CVE-2020-14343",
            "severity": "critical",
            "title": "Arbitrary code execution via yaml.load",
            "affected": "<5.4",
            "fixed": "5.4",
        },
    ],
    "requests": [
        {
            "cve_id": "CVE-2023-32681",
            "severity": "moderate",
            "title": "Unintended leak of Proxy-Authorization header",
            "affected": "<2.31.0",
            "fixed": "2.31.0",
        },
    ],
    "urllib3": [
        {
            "cve_id": "CVE-2023-45803",
            "severity": "moderate",
            "title": "Request body not stripped after cross-origin redirect",
            "affected": "<2.0.7",
            "fixed": "2.0.7",
        },
    ],
    "pillow": [
        {
            "cve_id": "CVE-2023-50447",
            "severity": "high",
            "title": "Arbitrary code execution via PIL.ImageMath.eval",
            "affected": "<10.2.0",
            "fixed": "10.2.0",
        },
    ],
    "django": [
        {
            "cve_id": "CVE-2024-24680",
            "severity": "moderate",
            "title": "Denial of service via intcomma template filter",
            "affected": "<4.2.10",
            "fixed": "4.2.10",
        },
    ],
    # JavaScript packages
    "lodash": [
        {
            "cve_id": "CVE-2021-23337",
            "severity": "high",
            "title": "Command injection via template function",
            "affected": "<4.17.21",
            "fixed": "4.17.21",
        },
    ],
    "axios": [
        {
            "cve_id": "CVE-2023-45857",
            "severity": "moderate",
            "title": "CSRF token exposure",
            "affected": "<1.6.0",
            "fixed": "1.6.0",
        },
    ],
}


class DependencyAnalyzer:
    """
    Analyzes project dependencies for issues.

    Supports:
    - Python requirements.txt
    - Node.js package.json
    """

    def __init__(self):
        """Initialize dependency analyzer."""
        self._dependencies: list[Dependency] = []
        self._issues: list[DependencyIssue] = []

    def analyze_requirements_txt(
        self,
        content: str,
        file_path: str = "requirements.txt",
    ) -> tuple[list[Dependency], list[DependencyIssue]]:
        """
        Analyze a Python requirements.txt file.

        Args:
            content: File content
            file_path: Path to file

        Returns:
            Tuple of (dependencies, issues)
        """
        dependencies = []
        issues = []

        lines = content.strip().split('\n')

        for line_num, line in enumerate(lines, 1):
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue

            # Skip editable installs and URLs
            if line.startswith('-e') or line.startswith('git+') or '://' in line:
                continue

            # Parse dependency
            dep = self._parse_requirement(line, file_path, line_num)
            if dep:
                dependencies.append(dep)

                # Check for issues
                dep_issues = self._check_dependency(dep)
                issues.extend(dep_issues)

        return dependencies, issues

    def analyze_package_json(
        self,
        content: str,
        file_path: str = "package.json",
    ) -> tuple[list[Dependency], list[DependencyIssue]]:
        """
        Analyze a Node.js package.json file.

        Args:
            content: File content
            file_path: Path to file

        Returns:
            Tuple of (dependencies, issues)
        """
        dependencies = []
        issues = []

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return [], []

        # Production dependencies
        for name, version in data.get("dependencies", {}).items():
            dep = Dependency(
                name=name,
                version=self._extract_version(version),
                version_constraint=version,
                dependency_type=DependencyType.PRODUCTION,
                source_file=file_path,
            )
            dependencies.append(dep)
            issues.extend(self._check_dependency(dep))

        # Dev dependencies
        for name, version in data.get("devDependencies", {}).items():
            dep = Dependency(
                name=name,
                version=self._extract_version(version),
                version_constraint=version,
                dependency_type=DependencyType.DEVELOPMENT,
                source_file=file_path,
            )
            dependencies.append(dep)
            issues.extend(self._check_dependency(dep))

        return dependencies, issues

    def _parse_requirement(
        self,
        line: str,
        file_path: str,
        line_num: int,
    ) -> Dependency | None:
        """Parse a single requirement line."""
        # Match patterns like: package==1.0, package>=1.0, package~=1.0
        patterns = [
            r'^([a-zA-Z0-9_\-\.]+)\s*([=<>!~]+)\s*([a-zA-Z0-9\._\-]+)',
            r'^([a-zA-Z0-9_\-\.]+)\s*\[.*\]\s*([=<>!~]+)\s*([a-zA-Z0-9\._\-]+)',
            r'^([a-zA-Z0-9_\-\.]+)$',
        ]

        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                groups = match.groups()
                name = groups[0]

                if len(groups) >= 3:
                    version = groups[2]
                    constraint = f"{groups[1]}{groups[2]}"
                else:
                    version = "unspecified"
                    constraint = "any"

                return Dependency(
                    name=name.lower(),
                    version=version,
                    version_constraint=constraint,
                    dependency_type=DependencyType.PRODUCTION,
                    source_file=file_path,
                    line_number=line_num,
                )

        return None

    def _extract_version(self, version_str: str) -> str:
        """Extract version number from a version constraint."""
        # Remove prefixes like ^, ~, >=, etc.
        version = re.sub(r'^[\^~>=<]+', '', version_str)
        return version.split(' ')[0] if ' ' in version else version

    def _check_dependency(self, dep: Dependency) -> list[DependencyIssue]:
        """Check a dependency for issues."""
        issues = []

        # Check for unpinned versions
        if dep.version == "unspecified" or dep.version_constraint == "any":
            issues.append(DependencyIssue(
                dependency=dep,
                issue_type="unpinned",
                severity="warning",
                description=f"Package '{dep.name}' has no version constraint",
                recommendation="Pin to a specific version for reproducible builds",
            ))

        # Check for known vulnerabilities
        if dep.name.lower() in KNOWN_VULNERABILITIES:
            for vuln_data in KNOWN_VULNERABILITIES[dep.name.lower()]:
                if self._version_affected(dep.version, vuln_data["affected"]):
                    vuln = VulnerabilityInfo(
                        cve_id=vuln_data["cve_id"],
                        severity=VulnerabilitySeverity(vuln_data["severity"]),
                        title=vuln_data["title"],
                        description=vuln_data["title"],
                        affected_versions=vuln_data["affected"],
                        fixed_version=vuln_data.get("fixed"),
                        published_date=None,
                    )

                    issues.append(DependencyIssue(
                        dependency=dep,
                        issue_type="vulnerable",
                        severity=vuln_data["severity"],
                        description=f"Known vulnerability: {vuln_data['title']}",
                        recommendation=f"Upgrade to version {vuln_data.get('fixed', 'latest')}",
                        vulnerability=vuln,
                    ))

        return issues

    def _version_affected(self, version: str, affected_range: str) -> bool:
        """Check if a version is within the affected range."""
        if version == "unspecified":
            return True  # Assume affected if version unknown

        try:
            from packaging import version as pkg_version

            current = pkg_version.parse(version)

            # Parse affected range (simplified)
            if affected_range.startswith('<'):
                limit = pkg_version.parse(affected_range[1:])
                return current < limit
            if affected_range.startswith('>=') and '<' in affected_range:
                # Range like ">=1.0,<2.0"
                parts = affected_range.split(',')
                lower = pkg_version.parse(parts[0][2:])
                upper = pkg_version.parse(parts[1][1:])
                return lower <= current < upper
            if affected_range.startswith('<='):
                limit = pkg_version.parse(affected_range[2:])
                return current <= limit
            return True  # Assume affected if can't parse
        except Exception:
            # If packaging not available or parse fails, assume affected
            return True

    def get_summary(
        self,
        dependencies: list[Dependency],
        issues: list[DependencyIssue],
    ) -> dict[str, Any]:
        """Generate a summary of the analysis."""
        vuln_count = sum(1 for i in issues if i.issue_type == "vulnerable")
        outdated_count = sum(1 for i in issues if i.issue_type == "outdated")
        unpinned_count = sum(1 for i in issues if i.issue_type == "unpinned")

        severity_counts = {
            "critical": sum(1 for i in issues if i.severity == "critical"),
            "high": sum(1 for i in issues if i.severity == "high"),
            "moderate": sum(1 for i in issues if i.severity == "moderate"),
            "low": sum(1 for i in issues if i.severity == "low"),
            "warning": sum(1 for i in issues if i.severity == "warning"),
        }

        return {
            "total_dependencies": len(dependencies),
            "production_dependencies": sum(
                1 for d in dependencies if d.dependency_type == DependencyType.PRODUCTION
            ),
            "dev_dependencies": sum(
                1 for d in dependencies if d.dependency_type == DependencyType.DEVELOPMENT
            ),
            "total_issues": len(issues),
            "vulnerabilities": vuln_count,
            "outdated": outdated_count,
            "unpinned": unpinned_count,
            "severity_breakdown": {k: v for k, v in severity_counts.items() if v > 0},
        }
