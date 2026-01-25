"""
Secure credential management with AES-256 encryption.

Provides secure storage and retrieval of credentials (login, api_key, oauth)
with AES-256 encryption at rest, scoped access control, and audit logging.
Uses Redis for secure storage with configurable TTL.
"""

import logging
import hashlib
import base64
import json
import secrets
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

# Try to import cryptography for AES encryption
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    logger.warning("cryptography package not installed. Credential encryption will be disabled.")


class CredentialType(str, Enum):
    """Types of credentials that can be stored."""
    LOGIN = "login"  # Username/password pair
    API_KEY = "api_key"  # API key/token
    OAUTH = "oauth"  # OAuth tokens (access, refresh)
    CERTIFICATE = "certificate"  # Client certificates
    SSH_KEY = "ssh_key"  # SSH private keys
    GENERIC = "generic"  # Generic secret


@dataclass
class Credential:
    """
    Secure credential representation.

    Attributes:
        id: Unique credential identifier
        credential_type: Type of credential
        name: Human-readable name
        data: Encrypted credential data
        scope: Domains/services this credential can be used for
        created_at: Creation timestamp
        expires_at: Optional expiration timestamp
        last_accessed: Last access timestamp
        access_count: Number of times accessed
        metadata: Additional metadata
    """
    id: str
    credential_type: CredentialType
    name: str
    data: Dict[str, Any]  # Will be encrypted at rest
    scope: Set[str] = field(default_factory=set)  # Allowed domains/services
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    last_accessed: Optional[datetime] = None
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if the credential has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def is_scope_allowed(self, domain: str) -> bool:
        """Check if the credential can be used for a domain."""
        if not self.scope:
            return True  # No scope restriction
        # Check for exact match or wildcard match
        domain_lower = domain.lower()
        for allowed in self.scope:
            if allowed == "*":
                return True
            if allowed.startswith("*."):
                # Wildcard subdomain match
                suffix = allowed[1:]  # Remove *
                if domain_lower.endswith(suffix):
                    return True
            elif domain_lower == allowed.lower() or domain_lower.endswith("." + allowed.lower()):
                return True
        return False

    def to_dict(self, include_data: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "id": self.id,
            "credential_type": self.credential_type.value,
            "name": self.name,
            "scope": list(self.scope),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "access_count": self.access_count,
            "metadata": self.metadata,
        }
        if include_data:
            result["data"] = self.data
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Credential":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            credential_type=CredentialType(data["credential_type"]),
            name=data["name"],
            data=data.get("data", {}),
            scope=set(data.get("scope", [])),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            last_accessed=datetime.fromisoformat(data["last_accessed"]) if data.get("last_accessed") else None,
            access_count=data.get("access_count", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AuditLogEntry:
    """Audit log entry for credential access."""
    timestamp: datetime
    credential_id: str
    action: str  # create, read, update, delete
    user_id: Optional[str]
    session_id: Optional[str]
    domain: Optional[str]
    success: bool
    details: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "credential_id": self.credential_id,
            "action": self.action,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "domain": self.domain,
            "success": self.success,
            "details": self.details,
        }


class CredentialManager:
    """
    Secure credential manager with AES-256 encryption.

    Features:
    - AES-256 encryption at rest using Fernet (symmetric encryption)
    - Scoped access control by domain/service
    - Redis-backed storage with configurable TTL
    - Audit logging for all credential access
    - Auto-fill integration support
    """

    def __init__(
        self,
        encryption_key: Optional[str] = None,
        redis_client: Optional[Any] = None,
        default_ttl_hours: int = 24,
        enable_audit_log: bool = True,
    ):
        """
        Initialize credential manager.

        Args:
            encryption_key: Base64-encoded AES-256 key (32 bytes). If not provided,
                          a new key will be generated (not recommended for production).
            redis_client: Redis client for storage. If not provided, uses in-memory storage.
            default_ttl_hours: Default TTL for stored credentials in hours.
            enable_audit_log: Enable audit logging for credential access.
        """
        self._redis = redis_client
        self._default_ttl = timedelta(hours=default_ttl_hours)
        self._enable_audit = enable_audit_log
        self._audit_log: List[AuditLogEntry] = []
        self._max_audit_entries = 1000

        # In-memory fallback storage
        self._memory_storage: Dict[str, str] = {}

        # Initialize encryption
        self._fernet: Optional[Any] = None
        if CRYPTO_AVAILABLE:
            if encryption_key:
                try:
                    # Decode base64 key
                    key_bytes = base64.urlsafe_b64decode(encryption_key)
                    if len(key_bytes) != 32:
                        logger.warning("Invalid encryption key length. Generating new key.")
                        key_bytes = Fernet.generate_key()
                    else:
                        # Fernet requires a specific key format
                        key_bytes = base64.urlsafe_b64encode(key_bytes)
                    self._fernet = Fernet(key_bytes)
                except Exception as e:
                    logger.warning(f"Failed to initialize encryption key: {e}. Generating new key.")
                    self._fernet = Fernet(Fernet.generate_key())
            else:
                # Generate a new key (warn in logs)
                logger.warning(
                    "No encryption key provided. Generating ephemeral key. "
                    "Credentials will not persist across restarts."
                )
                self._fernet = Fernet(Fernet.generate_key())
        else:
            logger.warning("Encryption disabled. Credentials will be stored in plaintext.")

        logger.info("CredentialManager initialized")

    def _encrypt(self, data: Dict[str, Any]) -> str:
        """Encrypt data to string."""
        json_data = json.dumps(data)
        if self._fernet:
            encrypted = self._fernet.encrypt(json_data.encode())
            return encrypted.decode()
        else:
            # Base64 encode as fallback (NOT SECURE)
            return base64.b64encode(json_data.encode()).decode()

    def _decrypt(self, encrypted_data: str) -> Dict[str, Any]:
        """Decrypt string to data."""
        if self._fernet:
            decrypted = self._fernet.decrypt(encrypted_data.encode())
            return json.loads(decrypted.decode())
        else:
            # Base64 decode as fallback
            return json.loads(base64.b64decode(encrypted_data.encode()).decode())

    def _generate_id(self) -> str:
        """Generate a unique credential ID."""
        return f"cred_{secrets.token_urlsafe(16)}"

    def _get_storage_key(self, credential_id: str) -> str:
        """Get Redis storage key for a credential."""
        return f"credential:{credential_id}"

    async def _store(self, key: str, value: str, ttl: Optional[timedelta] = None) -> bool:
        """Store encrypted data."""
        if self._redis:
            try:
                ttl_seconds = int(ttl.total_seconds()) if ttl else int(self._default_ttl.total_seconds())
                await self._redis.set(key, value, ex=ttl_seconds)
                return True
            except Exception as e:
                logger.error(f"Redis store failed: {e}")
                return False
        else:
            self._memory_storage[key] = value
            return True

    async def _retrieve(self, key: str) -> Optional[str]:
        """Retrieve encrypted data."""
        if self._redis:
            try:
                value = await self._redis.get(key)
                return value.decode() if value else None
            except Exception as e:
                logger.error(f"Redis retrieve failed: {e}")
                return None
        else:
            return self._memory_storage.get(key)

    async def _delete(self, key: str) -> bool:
        """Delete data."""
        if self._redis:
            try:
                await self._redis.delete(key)
                return True
            except Exception as e:
                logger.error(f"Redis delete failed: {e}")
                return False
        else:
            self._memory_storage.pop(key, None)
            return True

    def _log_audit(
        self,
        credential_id: str,
        action: str,
        success: bool,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        domain: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        """Log credential access for audit."""
        if not self._enable_audit:
            return

        entry = AuditLogEntry(
            timestamp=datetime.now(),
            credential_id=credential_id,
            action=action,
            user_id=user_id,
            session_id=session_id,
            domain=domain,
            success=success,
            details=details,
        )

        self._audit_log.append(entry)

        # Trim audit log
        if len(self._audit_log) > self._max_audit_entries:
            self._audit_log = self._audit_log[-self._max_audit_entries:]

        # Log to system logger for external audit
        log_level = logging.INFO if success else logging.WARNING
        logger.log(
            log_level,
            f"Credential {action}: {credential_id} (user={user_id}, success={success})"
        )

    async def create(
        self,
        name: str,
        credential_type: CredentialType,
        data: Dict[str, Any],
        scope: Optional[Set[str]] = None,
        ttl: Optional[timedelta] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[Credential]:
        """
        Create and store a new credential.

        Args:
            name: Human-readable name
            credential_type: Type of credential
            data: Credential data (will be encrypted)
            scope: Allowed domains/services
            ttl: Time-to-live (optional)
            metadata: Additional metadata
            user_id: User creating the credential
            session_id: Session ID

        Returns:
            Created Credential or None on failure
        """
        credential_id = self._generate_id()

        credential = Credential(
            id=credential_id,
            credential_type=credential_type,
            name=name,
            data=data,
            scope=scope or set(),
            expires_at=datetime.now() + (ttl or self._default_ttl),
            metadata=metadata or {},
        )

        # Encrypt and store
        encrypted = self._encrypt(credential.to_dict(include_data=True))
        storage_key = self._get_storage_key(credential_id)

        if await self._store(storage_key, encrypted, ttl or self._default_ttl):
            self._log_audit(
                credential_id=credential_id,
                action="create",
                success=True,
                user_id=user_id,
                session_id=session_id,
                details=f"Created {credential_type.value} credential: {name}",
            )
            return credential
        else:
            self._log_audit(
                credential_id=credential_id,
                action="create",
                success=False,
                user_id=user_id,
                session_id=session_id,
                details="Storage failure",
            )
            return None

    async def get(
        self,
        credential_id: str,
        domain: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[Credential]:
        """
        Retrieve a credential by ID.

        Args:
            credential_id: Credential ID
            domain: Domain requesting access (for scope check)
            user_id: User requesting access
            session_id: Session ID

        Returns:
            Credential if found and authorized, None otherwise
        """
        storage_key = self._get_storage_key(credential_id)
        encrypted = await self._retrieve(storage_key)

        if not encrypted:
            self._log_audit(
                credential_id=credential_id,
                action="read",
                success=False,
                user_id=user_id,
                session_id=session_id,
                domain=domain,
                details="Not found",
            )
            return None

        try:
            data = self._decrypt(encrypted)
            credential = Credential.from_dict(data)

            # Check expiration
            if credential.is_expired():
                self._log_audit(
                    credential_id=credential_id,
                    action="read",
                    success=False,
                    user_id=user_id,
                    session_id=session_id,
                    domain=domain,
                    details="Expired",
                )
                await self.delete(credential_id)
                return None

            # Check scope
            if domain and not credential.is_scope_allowed(domain):
                self._log_audit(
                    credential_id=credential_id,
                    action="read",
                    success=False,
                    user_id=user_id,
                    session_id=session_id,
                    domain=domain,
                    details=f"Domain not in scope: {domain}",
                )
                return None

            # Update access tracking
            credential.last_accessed = datetime.now()
            credential.access_count += 1

            # Re-encrypt with updated access info
            encrypted_updated = self._encrypt(credential.to_dict(include_data=True))
            await self._store(storage_key, encrypted_updated)

            self._log_audit(
                credential_id=credential_id,
                action="read",
                success=True,
                user_id=user_id,
                session_id=session_id,
                domain=domain,
            )

            return credential

        except Exception as e:
            logger.error(f"Failed to decrypt credential {credential_id}: {e}")
            self._log_audit(
                credential_id=credential_id,
                action="read",
                success=False,
                user_id=user_id,
                session_id=session_id,
                domain=domain,
                details=f"Decryption error: {str(e)}",
            )
            return None

    async def update(
        self,
        credential_id: str,
        data: Optional[Dict[str, Any]] = None,
        scope: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[Credential]:
        """
        Update an existing credential.

        Args:
            credential_id: Credential ID
            data: New credential data (optional)
            scope: New scope (optional)
            metadata: New metadata (optional)
            user_id: User performing update
            session_id: Session ID

        Returns:
            Updated Credential or None on failure
        """
        credential = await self.get(credential_id, user_id=user_id, session_id=session_id)
        if not credential:
            return None

        # Update fields
        if data is not None:
            credential.data = data
        if scope is not None:
            credential.scope = scope
        if metadata is not None:
            credential.metadata.update(metadata)

        # Re-encrypt and store
        encrypted = self._encrypt(credential.to_dict(include_data=True))
        storage_key = self._get_storage_key(credential_id)

        if await self._store(storage_key, encrypted):
            self._log_audit(
                credential_id=credential_id,
                action="update",
                success=True,
                user_id=user_id,
                session_id=session_id,
            )
            return credential
        else:
            self._log_audit(
                credential_id=credential_id,
                action="update",
                success=False,
                user_id=user_id,
                session_id=session_id,
                details="Storage failure",
            )
            return None

    async def delete(
        self,
        credential_id: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """
        Delete a credential.

        Args:
            credential_id: Credential ID
            user_id: User performing deletion
            session_id: Session ID

        Returns:
            True if deleted, False otherwise
        """
        storage_key = self._get_storage_key(credential_id)
        success = await self._delete(storage_key)

        self._log_audit(
            credential_id=credential_id,
            action="delete",
            success=success,
            user_id=user_id,
            session_id=session_id,
        )

        return success

    async def list_credentials(
        self,
        user_id: Optional[str] = None,
        credential_type: Optional[CredentialType] = None,
    ) -> List[Dict[str, Any]]:
        """
        List all credentials (metadata only, no sensitive data).

        Args:
            user_id: Filter by user
            credential_type: Filter by type

        Returns:
            List of credential metadata (no sensitive data)
        """
        # For Redis, we would need to scan keys
        # For memory storage, iterate
        credentials = []

        if self._redis:
            try:
                keys = await self._redis.keys("credential:*")
                for key in keys:
                    encrypted = await self._retrieve(key.decode())
                    if encrypted:
                        try:
                            data = self._decrypt(encrypted)
                            cred = Credential.from_dict(data)
                            if credential_type and cred.credential_type != credential_type:
                                continue
                            credentials.append(cred.to_dict(include_data=False))
                        except Exception:
                            pass
            except Exception as e:
                logger.error(f"Failed to list credentials: {e}")
        else:
            for key, encrypted in self._memory_storage.items():
                if key.startswith("credential:"):
                    try:
                        data = self._decrypt(encrypted)
                        cred = Credential.from_dict(data)
                        if credential_type and cred.credential_type != credential_type:
                            continue
                        credentials.append(cred.to_dict(include_data=False))
                    except Exception:
                        pass

        return credentials

    def get_audit_log(
        self,
        credential_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get audit log entries.

        Args:
            credential_id: Filter by credential ID
            action: Filter by action
            limit: Maximum entries to return

        Returns:
            List of audit log entries
        """
        entries = self._audit_log

        if credential_id:
            entries = [e for e in entries if e.credential_id == credential_id]

        if action:
            entries = [e for e in entries if e.action == action]

        return [e.to_dict() for e in entries[-limit:]]

    async def get_for_autofill(
        self,
        domain: str,
        credential_type: CredentialType = CredentialType.LOGIN,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        """
        Get credential data for auto-fill in browser.

        Args:
            domain: Domain requesting credentials
            credential_type: Type of credential to find
            user_id: User requesting
            session_id: Session ID

        Returns:
            Credential data dict suitable for form filling, or None
        """
        credentials = await self.list_credentials(credential_type=credential_type)

        for cred_meta in credentials:
            # Check scope
            scope = set(cred_meta.get("scope", []))
            if scope and not any(
                domain.lower() == s.lower() or domain.lower().endswith("." + s.lower())
                for s in scope
            ):
                continue

            # Get full credential
            credential = await self.get(
                cred_meta["id"],
                domain=domain,
                user_id=user_id,
                session_id=session_id,
            )

            if credential and not credential.is_expired():
                return credential.data

        return None

    async def get_totp_code(
        self,
        credential_id: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get the current TOTP code for a credential with TOTP secret.

        The credential data must contain a 'totp_secret' field (Base32-encoded).
        Optionally supports 'totp_digits' (default: 6) and 'totp_period' (default: 30).

        Args:
            credential_id: Credential ID
            user_id: User requesting the code
            session_id: Session ID

        Returns:
            Current TOTP code string, or None if not available

        Example credential data structure:
            {
                "username": "user@example.com",
                "password": "password",
                "totp_secret": "JBSWY3DPEBLW64TMMQ======",
                "totp_digits": 6,
                "totp_period": 30,
                "backup_codes": ["code1", "code2"]
            }
        """
        from app.domain.services.security.totp_service import TOTPService

        if not TOTPService.is_available():
            logger.warning("TOTP not available: pyotp not installed")
            return None

        credential = await self.get(
            credential_id,
            user_id=user_id,
            session_id=session_id,
        )

        if not credential:
            return None

        totp_secret = credential.data.get("totp_secret")
        if not totp_secret:
            logger.debug(f"Credential {credential_id} has no TOTP secret")
            return None

        try:
            code = TOTPService.get_current_code(
                totp_secret,
                digits=credential.data.get("totp_digits", 6),
                period=credential.data.get("totp_period", 30),
            )

            self._log_audit(
                credential_id=credential_id,
                action="totp_generate",
                success=True,
                user_id=user_id,
                session_id=session_id,
                details="Generated TOTP code",
            )

            return code
        except Exception as e:
            logger.error(f"Failed to generate TOTP code for {credential_id}: {e}")
            self._log_audit(
                credential_id=credential_id,
                action="totp_generate",
                success=False,
                user_id=user_id,
                session_id=session_id,
                details=f"TOTP generation failed: {str(e)}",
            )
            return None

    async def validate_mfa(
        self,
        credential_id: str,
        code: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        max_failures: int = 5,
        lockout_minutes: int = 15,
    ) -> bool:
        """
        Validate an MFA code with rate limiting and lockout.

        Supports both TOTP codes and backup codes. Implements rate limiting
        to prevent brute force attacks.

        Args:
            credential_id: Credential ID
            code: The code to validate (TOTP or backup code)
            user_id: User attempting validation
            session_id: Session ID
            max_failures: Maximum failures before lockout (default: 5)
            lockout_minutes: Lockout duration in minutes (default: 15)

        Returns:
            True if code is valid, False otherwise
        """
        from app.domain.services.security.totp_service import TOTPService

        credential = await self.get(
            credential_id,
            user_id=user_id,
            session_id=session_id,
        )

        if not credential:
            return False

        # Check lockout status
        mfa_metadata = credential.metadata.get("mfa", {})
        failure_count = mfa_metadata.get("failure_count", 0)
        lockout_until = mfa_metadata.get("lockout_until")

        if lockout_until:
            lockout_time = datetime.fromisoformat(lockout_until)
            if datetime.now() < lockout_time:
                remaining = (lockout_time - datetime.now()).total_seconds() / 60
                logger.warning(
                    f"MFA locked out for credential {credential_id}, "
                    f"{remaining:.1f} minutes remaining"
                )
                self._log_audit(
                    credential_id=credential_id,
                    action="mfa_validate",
                    success=False,
                    user_id=user_id,
                    session_id=session_id,
                    details=f"Locked out, {remaining:.1f} minutes remaining",
                )
                return False

        # Check for backup code first
        backup_codes = credential.data.get("backup_codes", [])
        if code in backup_codes:
            # Valid backup code - remove it (one-time use)
            backup_codes.remove(code)
            credential.data["backup_codes"] = backup_codes

            # Reset failure count
            credential.metadata["mfa"] = {
                "failure_count": 0,
                "lockout_until": None,
                "last_success": datetime.now().isoformat(),
            }

            # Save updated credential
            encrypted = self._encrypt(credential.to_dict(include_data=True))
            storage_key = self._get_storage_key(credential_id)
            await self._store(storage_key, encrypted)

            self._log_audit(
                credential_id=credential_id,
                action="mfa_validate",
                success=True,
                user_id=user_id,
                session_id=session_id,
                details="Validated with backup code",
            )
            return True

        # Check TOTP code
        totp_secret = credential.data.get("totp_secret")
        if not totp_secret:
            logger.debug(f"Credential {credential_id} has no TOTP secret")
            return False

        if not TOTPService.is_available():
            logger.warning("TOTP not available: pyotp not installed")
            return False

        is_valid = TOTPService.verify_code(
            totp_secret,
            code,
            digits=credential.data.get("totp_digits", 6),
            period=credential.data.get("totp_period", 30),
            window=1,  # Allow 1 period drift
        )

        if is_valid:
            # Reset failure count on success
            credential.metadata["mfa"] = {
                "failure_count": 0,
                "lockout_until": None,
                "last_success": datetime.now().isoformat(),
            }

            # Save updated credential
            encrypted = self._encrypt(credential.to_dict(include_data=True))
            storage_key = self._get_storage_key(credential_id)
            await self._store(storage_key, encrypted)

            self._log_audit(
                credential_id=credential_id,
                action="mfa_validate",
                success=True,
                user_id=user_id,
                session_id=session_id,
            )
            return True
        else:
            # Increment failure count
            failure_count += 1
            lockout_until_new = None

            if failure_count >= max_failures:
                lockout_until_new = (
                    datetime.now() + timedelta(minutes=lockout_minutes)
                ).isoformat()
                logger.warning(
                    f"MFA lockout triggered for credential {credential_id} "
                    f"after {failure_count} failures"
                )

            credential.metadata["mfa"] = {
                "failure_count": failure_count,
                "lockout_until": lockout_until_new,
                "last_failure": datetime.now().isoformat(),
            }

            # Save updated credential
            encrypted = self._encrypt(credential.to_dict(include_data=True))
            storage_key = self._get_storage_key(credential_id)
            await self._store(storage_key, encrypted)

            self._log_audit(
                credential_id=credential_id,
                action="mfa_validate",
                success=False,
                user_id=user_id,
                session_id=session_id,
                details=f"Invalid code, failures: {failure_count}",
            )
            return False


# Singleton instance
_credential_manager: Optional[CredentialManager] = None


def get_credential_manager() -> CredentialManager:
    """Get the global credential manager singleton."""
    global _credential_manager
    if _credential_manager is None:
        from app.core.config import get_settings
        settings = get_settings()
        _credential_manager = CredentialManager(
            encryption_key=settings.credential_encryption_key,
            default_ttl_hours=settings.credential_ttl_hours,
        )
    return _credential_manager


def set_credential_manager(manager: CredentialManager) -> None:
    """Set the global credential manager singleton."""
    global _credential_manager
    _credential_manager = manager
