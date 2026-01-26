import hashlib
import hmac
import secrets
import re
from typing import Optional
from datetime import datetime
from app.domain.models.user import User, UserRole
from app.domain.repositories.user_repository import UserRepository
from app.application.errors.exceptions import UnauthorizedError, ValidationError, BadRequestError
from app.core.config import get_settings
from app.application.services.token_service import TokenService
from app.domain.models.auth import AuthToken
from app.infrastructure.storage.redis import get_redis
import logging

logger = logging.getLogger(__name__)


class AuthService:
    """Authentication service handling user authentication and authorization"""

    def __init__(self, user_repository: UserRepository, token_service: TokenService):
        self.user_repository = user_repository
        self.settings = get_settings()
        self.token_service = token_service

    # =========================================================================
    # PASSWORD HASHING
    # =========================================================================

    def _hash_password(self, password: str) -> str:
        """Hash password using configured algorithm"""
        salt = self.settings.password_salt or ''
        if not salt:
            logger.warning("[SECURITY] Password salt is not configured - using empty salt")
        return self._pbkdf2_sha256(password, salt)

    def _pbkdf2_sha256(self, password: str, salt: str) -> str:
        """PBKDF2 with SHA-256 implementation"""
        password_bytes = password.encode('utf-8')
        salt_bytes = salt.encode('utf-8')

        # Use configured rounds (default is now 600000)
        rounds = self.settings.password_hash_rounds

        # Generate hash
        hash_bytes = hashlib.pbkdf2_hmac('sha256', password_bytes, salt_bytes, rounds)

        # Return salt + hash as hex string
        return salt + hash_bytes.hex()

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash using constant-time comparison"""
        if not password_hash:
            return False

        try:
            # Generate hash with configured salt
            generated_hash = self._hash_password(password)

            # Use constant-time comparison to prevent timing attacks
            return hmac.compare_digest(generated_hash, password_hash)
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False

    # =========================================================================
    # PASSWORD VALIDATION
    # =========================================================================

    def _validate_password_complexity(self, password: str) -> tuple[bool, list[str]]:
        """
        Validate password meets complexity requirements.
        Returns (is_valid, list_of_errors)
        """
        errors = []

        if len(password) < self.settings.password_min_length:
            errors.append(f"Password must be at least {self.settings.password_min_length} characters long")

        if self.settings.password_require_uppercase and not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")

        if self.settings.password_require_lowercase and not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")

        if self.settings.password_require_digit and not re.search(r'\d', password):
            errors.append("Password must contain at least one digit")

        if self.settings.password_require_special and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")

        return (len(errors) == 0, errors)

    # =========================================================================
    # ACCOUNT LOCKOUT
    # =========================================================================

    async def _get_failed_attempts(self, email: str) -> int:
        """Get failed login attempts count from Redis"""
        if not self.settings.account_lockout_enabled:
            return 0

        try:
            redis = get_redis().client
            key = f"auth:failed_attempts:{email.lower()}"
            attempts = await redis.get(key)
            return int(attempts) if attempts else 0
        except Exception as e:
            logger.warning(f"Failed to get failed attempts from Redis: {e}")
            return 0

    async def _increment_failed_attempts(self, email: str) -> int:
        """Increment failed login attempts and return new count"""
        if not self.settings.account_lockout_enabled:
            return 0

        try:
            redis = get_redis().client
            key = f"auth:failed_attempts:{email.lower()}"

            # Increment counter
            attempts = await redis.incr(key)

            # Set expiry on first failure
            if attempts == 1:
                await redis.expire(key, self.settings.account_lockout_reset_minutes * 60)

            return attempts
        except Exception as e:
            logger.warning(f"Failed to increment failed attempts: {e}")
            return 0

    async def _clear_failed_attempts(self, email: str) -> None:
        """Clear failed login attempts on successful login"""
        if not self.settings.account_lockout_enabled:
            return

        try:
            redis = get_redis().client
            key = f"auth:failed_attempts:{email.lower()}"
            await redis.delete(key)
        except Exception as e:
            logger.warning(f"Failed to clear failed attempts: {e}")

    async def _is_account_locked(self, email: str) -> tuple[bool, int]:
        """
        Check if account is locked due to too many failed attempts.
        Returns (is_locked, remaining_seconds)
        """
        if not self.settings.account_lockout_enabled:
            return (False, 0)

        try:
            redis = get_redis().client
            lockout_key = f"auth:lockout:{email.lower()}"

            # Check if locked
            ttl = await redis.ttl(lockout_key)
            if ttl > 0:
                return (True, ttl)

            return (False, 0)
        except Exception as e:
            logger.warning(f"Failed to check account lockout: {e}")
            return (False, 0)

    async def _lock_account(self, email: str) -> None:
        """Lock account after too many failed attempts"""
        if not self.settings.account_lockout_enabled:
            return

        try:
            redis = get_redis().client
            lockout_key = f"auth:lockout:{email.lower()}"
            lockout_duration = self.settings.account_lockout_duration_minutes * 60

            await redis.setex(lockout_key, lockout_duration, "locked")
            logger.warning(f"[SECURITY] Account locked due to failed attempts: {email}")
        except Exception as e:
            logger.warning(f"Failed to lock account: {e}")

    def _generate_user_id(self) -> str:
        """Generate unique user ID"""
        return secrets.token_urlsafe(16)
    
    async def register_user(self, fullname: str, password: str, email: str, role: UserRole = UserRole.USER) -> User:
        """Register a new user"""
        logger.info(f"Registering user: {email}")

        if self.settings.auth_provider != "password":
            raise BadRequestError("Registration is not allowed")

        # Validate input
        if not fullname or len(fullname.strip()) < 2:
            raise ValidationError("Full name must be at least 2 characters long")

        if not email or '@' not in email:
            raise ValidationError("Valid email is required")

        # Validate password complexity
        if not password:
            raise ValidationError("Password is required")

        is_valid, password_errors = self._validate_password_complexity(password)
        if not is_valid:
            raise ValidationError("; ".join(password_errors))

        # Check if email already exists
        if await self.user_repository.email_exists(email):
            raise ValidationError("Email already exists")

        # Hash password
        password_hash = self._hash_password(password)

        # Create user
        user = User(
            id=self._generate_user_id(),
            fullname=fullname.strip(),
            email=email.lower(),
            password_hash=password_hash,
            role=role,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Save to database
        created_user = await self.user_repository.create_user(user)

        logger.info(f"User registered successfully: {created_user.id}")
        return created_user
    
    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate user by email and password with account lockout protection"""
        logger.debug(f"Authenticating user: {email}")

        # Handle different auth providers
        if self.settings.auth_provider == "none":
            # No authentication required - return a default user
            return User(
                id="anonymous",
                fullname="anonymous",
                email="anonymous@localhost",
                role=UserRole.USER,
                is_active=True
            )

        elif self.settings.auth_provider == "local":
            # Check account lockout for local auth
            is_locked, remaining = await self._is_account_locked(email)
            if is_locked:
                logger.warning(f"[SECURITY] Blocked login attempt for locked account: {email}")
                raise UnauthorizedError(
                    f"Account is temporarily locked. Please try again in {remaining // 60 + 1} minutes."
                )

            # Local authentication using configured credentials
            if (self.settings.local_auth_email and
                self.settings.local_auth_password and
                email == self.settings.local_auth_email and
                hmac.compare_digest(password, self.settings.local_auth_password)):
                await self._clear_failed_attempts(email)
                return User(
                    id="local_admin",
                    fullname="Local Admin",
                    email=email,
                    role=UserRole.ADMIN,
                    is_active=True
                )
            else:
                # Track failed attempt
                attempts = await self._increment_failed_attempts(email)
                if attempts >= self.settings.account_lockout_threshold:
                    await self._lock_account(email)
                logger.warning(f"Local authentication failed for user: {email} (attempt {attempts})")
                return None

        elif self.settings.auth_provider == "password":
            # Check account lockout
            is_locked, remaining = await self._is_account_locked(email)
            if is_locked:
                logger.warning(f"[SECURITY] Blocked login attempt for locked account: {email}")
                raise UnauthorizedError(
                    f"Account is temporarily locked. Please try again in {remaining // 60 + 1} minutes."
                )

            # Database password authentication
            user = await self.user_repository.get_user_by_email(email)
            if not user:
                # Still increment failed attempts to prevent user enumeration
                attempts = await self._increment_failed_attempts(email)
                if attempts >= self.settings.account_lockout_threshold:
                    await self._lock_account(email)
                logger.warning(f"User not found: {email} (attempt {attempts})")
                return None

            if not user.is_active:
                logger.warning(f"User account is inactive: {email}")
                return None

            if not user.password_hash:
                logger.warning(f"User has no password hash: {email}")
                return None

            # Verify password
            if not self._verify_password(password, user.password_hash):
                attempts = await self._increment_failed_attempts(email)
                if attempts >= self.settings.account_lockout_threshold:
                    await self._lock_account(email)
                logger.warning(f"Invalid password for user: {email} (attempt {attempts})")
                return None

            # Clear failed attempts on successful login
            await self._clear_failed_attempts(email)

            # Update last login
            user.update_last_login()
            await self.user_repository.update_user(user)

            logger.info(f"User authenticated successfully: {email}")
            return user

        else:
            raise ValueError(f"Unsupported auth provider: {self.settings.auth_provider}")
    
    async def login_with_tokens(self, email: str, password: str) -> AuthToken:
        """Authenticate user and return JWT tokens"""
        user = await self.authenticate_user(email, password)
        
        if not user:
            raise UnauthorizedError("Invalid email or password")
        
        # Generate JWT tokens
        access_token = self.token_service.create_access_token(user)
        refresh_token = self.token_service.create_refresh_token(user)
        
        return AuthToken(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=user
        )
    
    async def refresh_access_token(self, refresh_token: str) -> AuthToken:
        """Refresh access token using refresh token"""
        payload = self.token_service.verify_token(refresh_token)
        
        if not payload:
            raise UnauthorizedError("Invalid refresh token")
        
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid token type")
        
        # Get user from database
        user_id = payload.get("sub")
        user = await self.user_repository.get_user_by_id(user_id)
        
        if not user or not user.is_active:
            raise UnauthorizedError("User not found or inactive")
        
        # Generate new access token
        new_access_token = self.token_service.create_access_token(user)
        
        return AuthToken(
            access_token=new_access_token,
            token_type="bearer"
        )
    
    async def verify_token(self, token: str) -> Optional[User]:
        """Verify JWT token and return user"""
        user_info = self.token_service.get_user_from_token(token)
        
        if not user_info:
            return None
        
        # For database users, verify user still exists and is active
        if self.settings.auth_provider == "password":
            user = await self.user_repository.get_user_by_id(user_info["id"])
            if not user or not user.is_active:
                return None
            return user
        
        # For local/none authentication, create user from token info
        return User(
            id=user_info["id"],
            fullname=user_info["fullname"],
            email=user_info.get("email"),
            role=UserRole(user_info.get("role", "user")),
            is_active=user_info.get("is_active", True)
        )
    
    async def logout(self, token: str) -> bool:
        """Logout user by revoking token"""
        if self.settings.auth_provider == "none":
            raise BadRequestError("Logout is not allowed")
        return await self.token_service.revoke_token_async(token)

    async def logout_all_devices(self, user_id: str) -> bool:
        """Logout user from all devices by revoking all their tokens"""
        if self.settings.auth_provider == "none":
            raise BadRequestError("Logout is not allowed")
        return await self.token_service.revoke_all_user_tokens(user_id)
    
    async def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        """Change user password"""
        logger.info(f"Changing password for user: {user_id}")

        # Get user
        user = await self.user_repository.get_user_by_id(user_id)
        if not user:
            raise ValidationError("User not found")

        if not user.is_active:
            raise UnauthorizedError("User account is inactive")

        # Verify old password
        if not user.password_hash or not self._verify_password(old_password, user.password_hash):
            raise UnauthorizedError("Invalid old password")

        # Validate new password complexity
        if not new_password:
            raise ValidationError("New password is required")

        is_valid, password_errors = self._validate_password_complexity(new_password)
        if not is_valid:
            raise ValidationError("; ".join(password_errors))

        # Hash new password
        new_password_hash = self._hash_password(new_password)

        # Update user password
        user.password_hash = new_password_hash
        user.updated_at = datetime.utcnow()

        await self.user_repository.update_user(user)

        # Revoke all existing tokens for this user (optional but recommended)
        # This forces re-login on all devices after password change

        logger.info(f"Password changed successfully for user: {user_id}")
        return True
    
    async def change_fullname(self, user_id: str, new_fullname: str) -> User:
        """Change user fullname"""
        logger.info(f"Changing fullname for user: {user_id}")
        
        # Get user
        user = await self.user_repository.get_user_by_id(user_id)
        if not user:
            raise ValidationError("User not found")
        
        if not user.is_active:
            raise UnauthorizedError("User account is inactive")
        
        # Validate new fullname
        if not new_fullname or len(new_fullname.strip()) < 2:
            raise ValidationError("Full name must be at least 2 characters long")
        
        # Update user fullname
        user.fullname = new_fullname.strip()
        user.updated_at = datetime.utcnow()
        
        updated_user = await self.user_repository.update_user(user)
        
        logger.info(f"Fullname changed successfully for user: {user_id}")
        return updated_user
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        return await self.user_repository.get_user_by_id(user_id)
    
    async def deactivate_user(self, user_id: str) -> bool:
        """Deactivate user account"""
        logger.info(f"Deactivating user: {user_id}")
        
        user = await self.user_repository.get_user_by_id(user_id)
        if not user:
            raise ValidationError("User not found")
        
        user.deactivate()
        await self.user_repository.update_user(user)
        
        logger.info(f"User deactivated successfully: {user_id}")
        return True
    
    async def activate_user(self, user_id: str) -> bool:
        """Activate user account"""
        logger.info(f"Activating user: {user_id}")
        
        user = await self.user_repository.get_user_by_id(user_id)
        if not user:
            raise ValidationError("User not found")
        
        user.activate()
        await self.user_repository.update_user(user)
        
        logger.info(f"User activated successfully: {user_id}")
        return True
    
    async def reset_password(self, email: str, new_password: str) -> bool:
        """Reset user password with email"""
        logger.info(f"Resetting password for user: {email}")

        if self.settings.auth_provider != "password":
            raise BadRequestError("Password reset is not allowed")

        # Get user by email
        user = await self.user_repository.get_user_by_email(email)
        if not user:
            raise ValidationError("User not found")

        if not user.is_active:
            raise UnauthorizedError("User account is inactive")

        # Validate new password complexity
        if not new_password:
            raise ValidationError("New password is required")

        is_valid, password_errors = self._validate_password_complexity(new_password)
        if not is_valid:
            raise ValidationError("; ".join(password_errors))

        # Hash new password
        new_password_hash = self._hash_password(new_password)

        # Update user password
        user.password_hash = new_password_hash
        user.updated_at = datetime.utcnow()

        await self.user_repository.update_user(user)

        # Clear any account lockouts after password reset
        await self._clear_failed_attempts(email)

        logger.info(f"Password reset successfully for user: {email}")
        return True