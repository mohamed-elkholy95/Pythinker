"""
Security Manager for Sandbox Operations

Provides path validation, URL sanitization, command sanitization,
and audit logging for secure sandbox operations.
"""
import os
import re
import logging
import hashlib
import time
from typing import Dict, List, Optional, Any, Set
from urllib.parse import urlparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import threading

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    """Audit log entry for security operations"""
    timestamp: datetime
    operation: str
    session_id: str
    details: Dict[str, Any]
    success: bool
    risk_level: str = "low"  # low, medium, high


class EphemeralCredentialManager:
    """
    Manages ephemeral credentials with automatic expiry.
    Credentials are stored in memory only and never persisted.
    """

    DEFAULT_TTL_SECONDS = 300  # 5 minutes max TTL

    def __init__(self):
        self._credentials: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def store(self, key: str, credential: str, ttl_seconds: int = None) -> str:
        """
        Store a credential with automatic expiry.

        Args:
            key: Unique identifier for the credential
            credential: The credential value to store
            ttl_seconds: Time-to-live in seconds (max 300)

        Returns:
            The key used to retrieve the credential
        """
        ttl = min(ttl_seconds or self.DEFAULT_TTL_SECONDS, self.DEFAULT_TTL_SECONDS)
        expiry = datetime.now() + timedelta(seconds=ttl)

        with self._lock:
            self._credentials[key] = {
                "value": credential,
                "expiry": expiry
            }

        logger.debug(f"Stored ephemeral credential with key: {key[:8]}... (TTL: {ttl}s)")
        return key

    def retrieve(self, key: str) -> Optional[str]:
        """
        Retrieve and immediately delete a credential.

        Args:
            key: The credential key

        Returns:
            The credential value if found and not expired, None otherwise
        """
        with self._lock:
            if key not in self._credentials:
                return None

            cred = self._credentials[key]

            # Check expiry
            if datetime.now() > cred["expiry"]:
                del self._credentials[key]
                logger.warning(f"Credential expired: {key[:8]}...")
                return None

            # Retrieve and delete (single-use)
            value = cred["value"]
            del self._credentials[key]
            logger.debug(f"Retrieved and cleared credential: {key[:8]}...")
            return value

    def clear_expired(self) -> int:
        """
        Clear all expired credentials.

        Returns:
            Number of credentials cleared
        """
        cleared = 0
        now = datetime.now()

        with self._lock:
            expired_keys = [
                k for k, v in self._credentials.items()
                if now > v["expiry"]
            ]
            for key in expired_keys:
                del self._credentials[key]
                cleared += 1

        if cleared:
            logger.info(f"Cleared {cleared} expired credentials")
        return cleared

    def clear_all(self) -> int:
        """
        Clear all stored credentials.

        Returns:
            Number of credentials cleared
        """
        with self._lock:
            count = len(self._credentials)
            self._credentials.clear()
        logger.info(f"Cleared all {count} credentials")
        return count


class SecurityManager:
    """
    Security manager for validating and sanitizing sandbox operations.
    """

    # Allowed base paths for file operations
    ALLOWED_PATHS = ["/workspace", "/tmp", "/home/ubuntu"]

    # Blocked paths that should never be accessed
    BLOCKED_PATHS = [
        "/etc/passwd", "/etc/shadow", "/etc/sudoers",
        "/root", "/proc", "/sys", "/dev",
        "/.ssh", "/.gnupg", "/.aws", "/.config/gcloud"
    ]

    # Blocked path patterns (regex)
    BLOCKED_PATTERNS = [
        r"\.\.(/|$)",  # Directory traversal
        r"^/etc/(passwd|shadow|sudoers)",
        r"^/(proc|sys|dev)/",
        r"(^|/)\.ssh(/|$)",
        r"(^|/)\.gnupg(/|$)",
        r"(^|/)\.aws(/|$)",
    ]

    # Allowed git hosts for cloning
    ALLOWED_GIT_HOSTS = [
        "github.com",
        "gitlab.com",
        "bitbucket.org",
        "git.sr.ht",
        "codeberg.org"
    ]

    # Dangerous shell commands/patterns to block
    BLOCKED_COMMANDS = [
        r"\brm\s+(-rf?|--recursive)\s+/(?!workspace|tmp)",  # rm -rf outside allowed paths
        r"\bdd\s+.*of=/dev/",  # dd to devices
        r"\bmkfs\.",  # filesystem creation
        r"\bchmod\s+.*777\s+/",  # chmod 777 on root paths
        r"\bcurl\s+.*\|\s*(?:bash|sh)",  # curl | bash
        r"\bwget\s+.*\|\s*(?:bash|sh)",  # wget | bash
        r">\s*/etc/",  # redirect to /etc
        r"\biptables\b",  # firewall modification
        r"\bufw\b",  # firewall modification
    ]

    def __init__(self):
        self._audit_log: List[AuditEntry] = []
        self._audit_lock = threading.Lock()
        self.credentials = EphemeralCredentialManager()
        self._compiled_blocked_patterns = [re.compile(p) for p in self.BLOCKED_PATTERNS]
        self._compiled_blocked_commands = [re.compile(p, re.IGNORECASE) for p in self.BLOCKED_COMMANDS]

    def validate_path(self, path: str, session_id: str = None, allow_create: bool = False) -> bool:
        """
        Validate that a path is safe for operations.

        Args:
            path: The path to validate
            session_id: Optional session ID for workspace validation
            allow_create: Whether to allow paths that don't exist yet

        Returns:
            True if the path is valid, False otherwise
        """
        if not path:
            return False

        # Normalize the path
        try:
            normalized = os.path.normpath(path)
            if not os.path.isabs(normalized):
                normalized = os.path.abspath(normalized)
        except Exception:
            return False

        # Check for blocked patterns
        for pattern in self._compiled_blocked_patterns:
            if pattern.search(path) or pattern.search(normalized):
                logger.warning(f"Path blocked by pattern: {path}")
                self._audit_operation("path_validation", session_id or "unknown", {
                    "path": path,
                    "reason": "blocked_pattern"
                }, success=False, risk_level="high")
                return False

        # Check for explicitly blocked paths
        for blocked in self.BLOCKED_PATHS:
            if normalized.startswith(blocked) or blocked in normalized:
                logger.warning(f"Path explicitly blocked: {path}")
                self._audit_operation("path_validation", session_id or "unknown", {
                    "path": path,
                    "reason": "blocked_path"
                }, success=False, risk_level="high")
                return False

        # Check if path is under allowed paths
        is_allowed = any(normalized.startswith(allowed) for allowed in self.ALLOWED_PATHS)

        if not is_allowed:
            logger.warning(f"Path not under allowed directories: {path}")
            self._audit_operation("path_validation", session_id or "unknown", {
                "path": path,
                "reason": "not_allowed_path"
            }, success=False, risk_level="medium")
            return False

        # If session_id provided and path is under /workspace, ensure it's session-scoped
        if session_id and normalized.startswith("/workspace"):
            session_workspace = f"/workspace/{session_id}"
            if not normalized.startswith(session_workspace) and normalized != "/workspace":
                # Allow general workspace operations but log them
                logger.debug(f"Path not scoped to session workspace: {path}")

        self._audit_operation("path_validation", session_id or "unknown", {
            "path": path,
            "normalized": normalized
        }, success=True)

        return True

    def sanitize_command(self, command: str) -> str:
        """
        Sanitize a shell command by checking for dangerous patterns.

        Args:
            command: The command to sanitize

        Returns:
            The original command if safe

        Raises:
            ValueError: If the command contains dangerous patterns
        """
        if not command:
            raise ValueError("Empty command")

        # Check for blocked command patterns
        for pattern in self._compiled_blocked_commands:
            if pattern.search(command):
                logger.warning(f"Blocked dangerous command pattern: {command[:100]}...")
                raise ValueError(f"Command contains blocked pattern")

        return command

    def validate_url(self, url: str, allowed_hosts: List[str] = None) -> bool:
        """
        Validate a URL for git cloning or web requests.

        Args:
            url: The URL to validate
            allowed_hosts: Optional list of allowed hosts (defaults to ALLOWED_GIT_HOSTS)

        Returns:
            True if the URL is valid and allowed
        """
        if not url:
            return False

        try:
            parsed = urlparse(url)

            # Must be https (or ssh for git)
            if parsed.scheme not in ("https", "ssh", "git"):
                logger.warning(f"URL scheme not allowed: {parsed.scheme}")
                return False

            # Check hostname against whitelist
            hosts = allowed_hosts or self.ALLOWED_GIT_HOSTS
            hostname = parsed.hostname or ""

            if not any(hostname == h or hostname.endswith(f".{h}") for h in hosts):
                logger.warning(f"URL hostname not in whitelist: {hostname}")
                return False

            # Check for suspicious patterns in URL
            suspicious_patterns = [
                r"@[^:]+:",  # Embedded credentials
                r"\.\./",   # Directory traversal
                r"[;&|`$]", # Shell metacharacters
            ]

            for pattern in suspicious_patterns:
                if re.search(pattern, url):
                    logger.warning(f"URL contains suspicious pattern: {url[:100]}")
                    return False

            return True

        except Exception as e:
            logger.warning(f"URL validation failed: {e}")
            return False

    def validate_git_url(self, url: str) -> bool:
        """
        Validate a git repository URL specifically.

        Args:
            url: The git URL to validate

        Returns:
            True if the URL is valid for git cloning
        """
        return self.validate_url(url, self.ALLOWED_GIT_HOSTS)

    def generate_credential_key(self, prefix: str = "cred") -> str:
        """
        Generate a unique key for credential storage.

        Args:
            prefix: Optional prefix for the key

        Returns:
            A unique credential key
        """
        timestamp = str(time.time_ns())
        random_data = os.urandom(16).hex()
        raw = f"{prefix}:{timestamp}:{random_data}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _audit_operation(
        self,
        operation: str,
        session_id: str,
        details: Dict[str, Any],
        success: bool = True,
        risk_level: str = "low"
    ):
        """
        Log an audit entry for a security-relevant operation.

        Args:
            operation: The type of operation
            session_id: The session ID
            details: Operation details
            success: Whether the operation succeeded
            risk_level: Risk level (low, medium, high)
        """
        entry = AuditEntry(
            timestamp=datetime.now(),
            operation=operation,
            session_id=session_id,
            details=details,
            success=success,
            risk_level=risk_level
        )

        with self._audit_lock:
            self._audit_log.append(entry)

            # Keep only last 10000 entries
            if len(self._audit_log) > 10000:
                self._audit_log = self._audit_log[-10000:]

        # Log high-risk operations
        if risk_level == "high":
            logger.warning(f"High-risk operation: {operation} - {details}")
        elif not success:
            logger.info(f"Failed operation: {operation} - {details}")

    def audit_operation(
        self,
        operation: str,
        session_id: str,
        details: Dict[str, Any],
        success: bool = True,
        risk_level: str = "low"
    ):
        """
        Public method to log an audit entry.

        Args:
            operation: The type of operation
            session_id: The session ID
            details: Operation details
            success: Whether the operation succeeded
            risk_level: Risk level (low, medium, high)
        """
        self._audit_operation(operation, session_id, details, success, risk_level)

    def get_audit_log(
        self,
        session_id: str = None,
        operation: str = None,
        since: datetime = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit log entries.

        Args:
            session_id: Filter by session ID
            operation: Filter by operation type
            since: Filter entries after this time
            limit: Maximum entries to return

        Returns:
            List of audit entries matching filters
        """
        with self._audit_lock:
            entries = self._audit_log.copy()

        # Apply filters
        if session_id:
            entries = [e for e in entries if e.session_id == session_id]
        if operation:
            entries = [e for e in entries if e.operation == operation]
        if since:
            entries = [e for e in entries if e.timestamp >= since]

        # Return most recent entries up to limit
        entries = entries[-limit:]

        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "operation": e.operation,
                "session_id": e.session_id,
                "details": e.details,
                "success": e.success,
                "risk_level": e.risk_level
            }
            for e in entries
        ]


# Global security manager instance
security_manager = SecurityManager()
