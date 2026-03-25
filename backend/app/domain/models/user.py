from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


class User(BaseModel):
    """User domain model"""

    id: str
    fullname: str
    email: str  # Now required field for login
    password_hash: str | None = None
    role: UserRole = UserRole.USER
    is_active: bool = True
    totp_secret: str | None = None
    email_verified: bool = False
    totp_enabled: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_login_at: datetime | None = None

    @field_validator("fullname")
    @classmethod
    def validate_fullname(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError("Full name must be at least 2 characters long")
        return v.strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not v:
            raise ValueError("Email is required")
        v = v.strip().lower()
        # Basic structural validation: user@domain with non-empty parts
        if "@" not in v:
            raise ValueError("Email must contain @")
        local, _, domain = v.partition("@")
        if not local or not domain or "." not in domain:
            raise ValueError("Invalid email format: must be user@domain.tld")
        return v

    def update_last_login(self) -> None:
        """Update last login timestamp"""
        self.last_login_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def verify_email(self) -> None:
        """Mark email as verified"""
        self.email_verified = True
        self.updated_at = datetime.now(UTC)

    def deactivate(self) -> None:
        """Deactivate user account"""
        self.is_active = False
        self.updated_at = datetime.now(UTC)

    def activate(self) -> None:
        """Activate user account"""
        self.is_active = True
        self.updated_at = datetime.now(UTC)
