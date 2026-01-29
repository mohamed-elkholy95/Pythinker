"""Authentication related domain models"""


from pydantic import BaseModel

from app.domain.models.user import User


class AuthToken(BaseModel):
    """Authentication token model for login and refresh operations"""
    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None
    user: User | None = None
