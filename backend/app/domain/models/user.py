from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, field_validator


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
    created_at: datetime = datetime.now(UTC)
    updated_at: datetime = datetime.now(UTC)
    last_login_at: datetime | None = None

    @field_validator("fullname")
    @classmethod
    def validate_fullname(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError("Full name must be at least 2 characters long")
        return v.strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if not v or "@" not in v:
            raise ValueError("Valid email is required")
        return v.strip().lower()

    def update_last_login(self):
        """Update last login timestamp"""
        self.last_login_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def verify_email(self):
        """Mark email as verified"""
        self.email_verified = True
        self.updated_at = datetime.now(UTC)

    def deactivate(self):
        """Deactivate user account"""
        self.is_active = False
        self.updated_at = datetime.now(UTC)

    def activate(self):
        """Activate user account"""
        self.is_active = True
        self.updated_at = datetime.now(UTC)
