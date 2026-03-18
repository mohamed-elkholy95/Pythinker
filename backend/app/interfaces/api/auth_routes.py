import logging

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.errors.exceptions import BadRequestError, NotFoundError, UnauthorizedError
from app.application.services.auth_service import AuthService
from app.application.services.email_service import EmailService, VerificationResult
from app.core.config import get_settings
from app.domain.models.user import User, UserRole
from app.interfaces.dependencies import (
    get_auth_service,
    get_current_user,
    get_email_service,
)
from app.interfaces.schemas.auth import (
    AuthStatusResponse,
    ChangeFullnameRequest,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    PasswordPolicyResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    SendVerificationCodeRequest,
    TotpDisableRequest,
    TotpSetupResponse,
    TotpVerifyRequest,
    UserResponse,
    VerificationStateResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from app.interfaces.schemas.base import APIResponse

logger = logging.getLogger(__name__)


def _mask_email(email: str) -> str:
    """Mask email for safe logging: 'user@example.com' -> 'use***@example.com'."""
    local, _, domain = email.partition("@")
    return f"{local[:3]}***@{domain}" if domain else f"{email[:3]}***"


router = APIRouter(prefix="/auth", tags=["auth"])


def _raise_verification_error(result: VerificationResult) -> None:
    error_messages = {
        "code_invalid": "Invalid verification code",
        "code_expired": "Verification code expired",
        "code_attempts_exhausted": "Too many invalid verification attempts",
    }
    extra_data: dict[str, int] = {}
    if result.attempts_remaining is not None:
        extra_data["attempts_remaining"] = result.attempts_remaining

    raise UnauthorizedError(
        error_messages.get(result.error_code or "", "Invalid or expired verification code"),
        error_code=result.error_code,
        data=extra_data or None,
    )


@router.post("/login", response_model=APIResponse[LoginResponse])
async def login(
    request: LoginRequest, auth_service: AuthService = Depends(get_auth_service)
) -> APIResponse[LoginResponse]:
    """User login endpoint"""
    # Authenticate user and get tokens (passing optional TOTP code)
    auth_result = await auth_service.login_with_tokens(request.email, request.password, request.totp_code)

    # If TOTP is required but not provided, return challenge response
    if auth_result.requires_totp:
        return APIResponse.success(LoginResponse(requires_totp=True))

    # Return success response with tokens
    settings = get_settings()
    return APIResponse.success(
        LoginResponse(
            user=UserResponse.from_user(auth_result.user),
            access_token=auth_result.access_token,
            refresh_token=auth_result.refresh_token,
            token_type=auth_result.token_type,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )
    )


@router.post("/register", response_model=APIResponse[RegisterResponse])
async def register(
    request: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
    email_service: EmailService = Depends(get_email_service),
) -> APIResponse[RegisterResponse]:
    """User registration endpoint — creates user and sends email verification OTP"""
    # Register user with email_verified=False (default)
    user = await auth_service.register_user(fullname=request.fullname, password=request.password, email=request.email)

    verification_state = email_service.build_placeholder_verification_state()
    email_sent = True
    try:
        verification_state = await email_service.send_registration_verification_code(user.email)
    except Exception as e:
        email_sent = False
        logger.warning("Failed to send registration verification email to %s: %s", _mask_email(user.email), e)

    # Do NOT issue JWT tokens — user must verify email first
    return APIResponse.success(
        RegisterResponse(
            message="Verification code sent to your email"
            if email_sent
            else "Account created but verification email could not be sent. Please request a new code.",
            requires_verification=True,
            email_sent=email_sent,
            verification_state=VerificationStateResponse.from_state(verification_state),
        )
    )


@router.post("/verify-email", response_model=APIResponse[VerifyEmailResponse])
async def verify_email(
    request: VerifyEmailRequest,
    auth_service: AuthService = Depends(get_auth_service),
    email_service: EmailService = Depends(get_email_service),
) -> APIResponse[VerifyEmailResponse]:
    """Verify email with OTP code and return JWT tokens"""
    if get_settings().auth_provider != "password":
        raise BadRequestError("Email verification is not available")

    verification_result = await email_service.verify_code(
        request.email, request.verification_code, purpose="registration"
    )
    if not verification_result.is_valid:
        _raise_verification_error(verification_result)

    # Mark user's email as verified
    user = await auth_service.verify_email(request.email)

    # Generate and return JWT tokens
    access_token = auth_service.token_service.create_access_token(user)
    refresh_token = auth_service.token_service.create_refresh_token(user)

    settings = get_settings()
    return APIResponse.success(
        VerifyEmailResponse(
            user=UserResponse.from_user(user),
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )
    )


@router.post("/resend-registration-code", response_model=APIResponse[VerificationStateResponse])
async def resend_registration_code(
    request: SendVerificationCodeRequest,
    auth_service: AuthService = Depends(get_auth_service),
    email_service: EmailService = Depends(get_email_service),
) -> APIResponse[VerificationStateResponse]:
    """Resend registration verification code"""
    if get_settings().auth_provider != "password":
        raise BadRequestError("Email verification is not available")

    verification_state = email_service.build_placeholder_verification_state()
    user = await auth_service.user_repository.get_user_by_email(request.email)
    if user and not getattr(user, "email_verified", True):
        try:
            verification_state = await email_service.send_registration_verification_code(request.email)
        except Exception as e:
            logger.warning("Failed to resend registration code to %s: %s", _mask_email(request.email), e)

    return APIResponse.success(VerificationStateResponse.from_state(verification_state))


@router.get("/status", response_model=APIResponse[AuthStatusResponse])
async def get_auth_status(auth_service: AuthService = Depends(get_auth_service)) -> APIResponse[AuthStatusResponse]:
    """Get authentication status and configuration"""
    settings = get_settings()

    password_policy = None
    if settings.auth_provider == "password":
        password_policy = PasswordPolicyResponse.from_settings(settings)

    return APIResponse.success(
        AuthStatusResponse(auth_provider=settings.auth_provider, password_policy=password_policy)
    )


@router.post("/change-password", response_model=APIResponse[dict])
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> APIResponse[dict]:
    """Change user password endpoint"""
    # Change password for current user
    await auth_service.change_password(current_user.id, request.old_password, request.new_password)

    return APIResponse.success({})


@router.post("/change-fullname", response_model=APIResponse[UserResponse])
async def change_fullname(
    request: ChangeFullnameRequest,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> APIResponse[UserResponse]:
    """Change user fullname endpoint"""
    # Change fullname for current user
    updated_user = await auth_service.change_fullname(current_user.id, request.fullname)

    return APIResponse.success(UserResponse.from_user(updated_user))


@router.get("/me", response_model=APIResponse[UserResponse])
async def get_current_user_info(current_user: User = Depends(get_current_user)) -> APIResponse[UserResponse]:
    """Get current user information"""
    return APIResponse.success(UserResponse.from_user(current_user))


@router.get("/user/{user_id}", response_model=APIResponse[UserResponse])
async def get_user(
    user_id: str, current_user: User = Depends(get_current_user), auth_service: AuthService = Depends(get_auth_service)
) -> APIResponse[UserResponse]:
    """Get user information by ID (admin only)"""
    # Check if current user is admin
    if current_user.role != UserRole.ADMIN:
        raise UnauthorizedError("Admin access required")

    user = await auth_service.get_user_by_id(user_id)

    if not user:
        raise NotFoundError("User not found")

    return APIResponse.success(UserResponse.from_user(user))


@router.post("/user/{user_id}/deactivate", response_model=APIResponse[dict])
async def deactivate_user(
    user_id: str, current_user: User = Depends(get_current_user), auth_service: AuthService = Depends(get_auth_service)
) -> APIResponse[dict]:
    """Deactivate user account (admin only)"""
    # Check if current user is admin
    if current_user.role != UserRole.ADMIN:
        raise UnauthorizedError("Admin access required")

    # Prevent self-deactivation
    if current_user.id == user_id:
        raise BadRequestError("Cannot deactivate your own account")

    await auth_service.deactivate_user(user_id)
    return APIResponse.success({})


@router.post("/user/{user_id}/activate", response_model=APIResponse[dict])
async def activate_user(
    user_id: str, current_user: User = Depends(get_current_user), auth_service: AuthService = Depends(get_auth_service)
) -> APIResponse[dict]:
    """Activate user account (admin only)"""
    # Check if current user is admin
    if current_user.role != UserRole.ADMIN:
        raise UnauthorizedError("Admin access required")

    await auth_service.activate_user(user_id)
    return APIResponse.success({})


@router.post("/refresh", response_model=APIResponse[RefreshTokenResponse])
async def refresh_token(
    request: RefreshTokenRequest, auth_service: AuthService = Depends(get_auth_service)
) -> APIResponse[RefreshTokenResponse]:
    """Refresh access token endpoint"""
    # Refresh access token
    token_result = await auth_service.refresh_access_token(request.refresh_token)

    settings = get_settings()
    return APIResponse.success(
        RefreshTokenResponse(
            access_token=token_result.access_token,
            token_type=token_result.token_type,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )
    )


@router.post("/logout", response_model=APIResponse[dict])
async def logout(
    current_user: User = Depends(get_current_user),
    bearer_credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    auth_service: AuthService = Depends(get_auth_service),
) -> APIResponse[dict]:
    """User logout endpoint"""
    if get_settings().auth_provider == "none":
        raise BadRequestError("Logout is not allowed")

    # Revoke token
    await auth_service.logout(bearer_credentials.credentials)

    return APIResponse.success({})


@router.post("/send-verification-code", response_model=APIResponse[VerificationStateResponse])
async def send_verification_code(
    request: SendVerificationCodeRequest,
    auth_service: AuthService = Depends(get_auth_service),
    email_service: EmailService = Depends(get_email_service),
) -> APIResponse[VerificationStateResponse]:
    """Send verification code for password reset"""
    if get_settings().auth_provider != "password":
        raise BadRequestError("Password reset is not available")

    verification_state = email_service.build_placeholder_verification_state()
    user = await auth_service.user_repository.get_user_by_email(request.email)
    if user and user.is_active:
        try:
            verification_state = await email_service.send_verification_code(request.email)
        except Exception as e:
            logger.warning("Failed to send reset verification code to %s: %s", _mask_email(request.email), e)

    return APIResponse.success(VerificationStateResponse.from_state(verification_state))


@router.post("/reset-password", response_model=APIResponse[dict])
async def reset_password(
    request: ResetPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
    email_service: EmailService = Depends(get_email_service),
) -> APIResponse[dict]:
    """Reset password with verification code"""
    if get_settings().auth_provider != "password":
        raise BadRequestError("Password reset is not available")

    verification_result = await email_service.verify_code(request.email, request.verification_code)
    if not verification_result.is_valid:
        _raise_verification_error(verification_result)

    # Reset password
    await auth_service.reset_password(request.email, request.new_password)

    return APIResponse.success({})


# =========================================================================
# TOTP 2FA ENDPOINTS
# =========================================================================


@router.post("/totp/setup", response_model=APIResponse[TotpSetupResponse])
async def totp_setup(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> APIResponse[TotpSetupResponse]:
    """Generate a TOTP secret and provisioning URI for 2FA setup"""
    if get_settings().auth_provider != "password":
        raise BadRequestError("TOTP setup is only available for password authentication")

    provisioning_uri, secret = await auth_service.setup_totp(current_user.id)

    return APIResponse.success(TotpSetupResponse(provisioning_uri=provisioning_uri, secret=secret))


@router.post("/totp/verify", response_model=APIResponse[dict])
async def totp_verify(
    request: TotpVerifyRequest,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> APIResponse[dict]:
    """Verify a TOTP code to complete 2FA setup"""
    if get_settings().auth_provider != "password":
        raise BadRequestError("TOTP is only available for password authentication")

    await auth_service.verify_totp_setup(current_user.id, request.code)

    return APIResponse.success({})


@router.post("/totp/disable", response_model=APIResponse[dict])
async def totp_disable(
    request: TotpDisableRequest,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> APIResponse[dict]:
    """Disable TOTP 2FA with current code verification"""
    if get_settings().auth_provider != "password":
        raise BadRequestError("TOTP is only available for password authentication")

    await auth_service.disable_totp(current_user.id, request.code)

    return APIResponse.success({})
