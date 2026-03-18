from fastapi import APIRouter, Request
from pydantic import BaseModel
from stores import auth_store

router = APIRouter(prefix="/auth")


def _wrap(data):
    return {"code": 0, "msg": "success", "data": data}


def _password_policy() -> dict:
    return {
        "version": 1,
        "min_length": 9,
        "max_length": 128,
        "require_uppercase": True,
        "require_lowercase": False,
        "require_digit": False,
        "require_special": True,
    }


def _get_current_user(request: Request) -> dict:
    auth = request.headers.get("authorization", "")
    token = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else ""
    user = auth_store.get_user_by_token(token)
    if not user:
        # For demo: return stored copy of demo user (not the module-level constant)
        return auth_store.users.get(auth_store.DEMO_USER["id"], auth_store.DEMO_USER)
    return user


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    fullname: str
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ChangeFullnameRequest(BaseModel):
    fullname: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class SendVerificationCodeRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    verification_code: str
    new_password: str


@router.get("/status")
async def auth_status():
    return _wrap({"auth_provider": "password", "password_policy": _password_policy()})


@router.post("/login")
async def login(req: LoginRequest):
    user = auth_store.get_user_by_email(req.email)
    if user and not user.get("email_verified", True):
        return {"code": 400, "msg": "Email not verified", "data": {"code": "email_not_verified"}}
    if not user:
        user = auth_store.DEMO_USER
    access, refresh = auth_store.create_token_pair(user["id"])
    return _wrap(
        {
            "user": user,
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
        }
    )


class VerifyEmailRequest(BaseModel):
    email: str
    verification_code: str


@router.post("/register")
async def register(req: RegisterRequest):
    auth_store.register_user(req.fullname, req.email)
    verification_state = auth_store.issue_verification_state(req.email)
    return _wrap(
        {
            "message": "Verification code sent to your email",
            "requires_verification": True,
            "verification_state": verification_state,
        }
    )


@router.post("/verify-email")
async def verify_email(req: VerifyEmailRequest):
    user = auth_store.verify_email(req.email)
    if not user:
        user = auth_store.DEMO_USER
    access, refresh = auth_store.create_token_pair(user["id"])
    return _wrap(
        {
            "user": user,
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_in": 1200,
        }
    )


@router.post("/resend-registration-code")
async def resend_registration_code(req: SendVerificationCodeRequest):
    return _wrap(auth_store.issue_verification_state(req.email))


@router.post("/refresh")
async def refresh_token(req: RefreshTokenRequest):
    uid = auth_store.refresh_tokens.get(req.refresh_token)
    if not uid:
        uid = auth_store.DEMO_USER["id"]
    access, _ = auth_store.create_token_pair(uid)
    return _wrap({"access_token": access, "token_type": "bearer"})


@router.get("/me")
async def get_me(request: Request):
    user = _get_current_user(request)
    return _wrap(user)


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest):
    return _wrap({})


@router.post("/change-fullname")
async def change_fullname(req: ChangeFullnameRequest, request: Request):
    user = _get_current_user(request)
    user["fullname"] = req.fullname
    return _wrap(user)


@router.post("/logout")
async def logout():
    return _wrap({})


@router.post("/send-verification-code")
async def send_verification_code(req: SendVerificationCodeRequest):
    return _wrap(auth_store.issue_verification_state(req.email))


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest):
    return _wrap({})


@router.get("/user/{user_id}")
async def get_user(user_id: str):
    user = auth_store.get_user_by_id(user_id) or auth_store.DEMO_USER
    return _wrap(user)


@router.post("/user/{user_id}/deactivate")
async def deactivate_user(user_id: str):
    return _wrap({})


@router.post("/user/{user_id}/activate")
async def activate_user(user_id: str):
    return _wrap({})
