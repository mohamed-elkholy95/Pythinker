"""FastAPI 2026 Best Practices - Context7 Validated Examples

References:
- Library: /websites/fastapi_tiangolo (Score: 96.8/100)
- Documentation: https://fastapi.tiangolo.com

Key patterns demonstrated:
1. Annotated type hints for dependency injection
2. Lifespan events for startup/shutdown
3. Background tasks with dependency injection
4. Proper error handling
5. Response model validation
6. Security with dependencies
"""

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

# ============================================================================
# 1. LIFESPAN EVENTS (Context7 Best Practice)
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events

    Context7 Validation: Modern replacement for @app.on_event decorators
    Benefits:
    - Cleaner async context manager pattern
    - Automatic resource cleanup
    - Better error handling
    - Recommended since FastAPI 0.93+
    """
    # === Startup Phase ===

    # Simulated resource initialization
    app.state.ml_models = {"sentiment": "mock_model"}
    app.state.db_pool = {"connections": 10}

    yield  # Application runs here

    # === Shutdown Phase ===
    app.state.ml_models.clear()
    app.state.db_pool.clear()


# ============================================================================
# 2. PYDANTIC MODELS WITH V2 FEATURES
# ============================================================================


class UserCreate(BaseModel):
    """User creation request model

    Context7 Best Practice: Use Field() for validation and documentation
    """

    username: str = Field(..., min_length=3, max_length=50, description="Username for login")
    email: str = Field(..., pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$", description="Valid email address")
    age: int = Field(..., ge=0, le=150, description="User age")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"username": "johndoe", "email": "john@example.com", "age": 30},
            ]
        }
    }


class UserResponse(BaseModel):
    """User response model

    Context7 Best Practice: Separate request/response models for API versioning
    """

    id: int
    username: str
    email: str

    model_config = {
        "from_attributes": True,  # Pydantic v2: ORM mode replacement
    }


# ============================================================================
# 3. DEPENDENCY INJECTION WITH ANNOTATED (Context7 Recommended)
# ============================================================================


async def verify_api_key(x_api_key: Annotated[str, Header()]) -> str:
    """Security dependency: Verify API key

    Context7 Best Practice: Use Annotated for better type hints and IDE support
    Benefits:
    - Type safety
    - Auto-generated OpenAPI docs
    - Reusable across endpoints
    """
    if x_api_key != "secret-api-key-123":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key


async def get_current_user(api_key: Annotated[str, Depends(verify_api_key)]) -> dict:
    """Get current user from API key

    Context7 Pattern: Chain dependencies for layered security
    """
    # Simulated user lookup
    return {"id": 1, "username": "admin", "api_key": api_key}


# Type alias for cleaner route signatures (Context7 Best Practice)
CurrentUser = Annotated[dict, Depends(get_current_user)]


# ============================================================================
# 4. BACKGROUND TASKS WITH DEPENDENCY INJECTION
# ============================================================================


def send_email_notification(email: str, message: str):
    """Background task: Send email notification

    Context7 Best Practice: Keep background tasks simple and stateless
    """


def log_user_action(user_id: int, action: str):
    """Background task: Log user action"""


# ============================================================================
# 5. APPLICATION SETUP
# ============================================================================

app = FastAPI(
    title="Pythinker API - 2026 Best Practices",
    description="FastAPI application with Context7-validated patterns",
    version="1.0.0",
    lifespan=lifespan,  # Context7: Use lifespan instead of on_event
)


# ============================================================================
# 6. ROUTE EXAMPLES WITH BEST PRACTICES
# ============================================================================


@app.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
    description="Creates a new user account with validated input",
    responses={
        201: {"description": "User created successfully"},
        400: {"description": "Invalid input data"},
        401: {"description": "Invalid API key"},
    },
    tags=["Users"],
)
async def create_user(
    user: UserCreate,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,  # Context7: Use type alias for cleaner code
) -> UserResponse:
    """Create user with background task

    Context7 Best Practices Applied:
    1. ✅ Annotated dependencies for type safety
    2. ✅ Background tasks for async operations
    3. ✅ Response model for validation
    4. ✅ Proper HTTP status codes
    5. ✅ OpenAPI documentation
    6. ✅ Security with API key verification
    """
    # Simulated user creation
    new_user = UserResponse(
        id=123,
        username=user.username,
        email=user.email,
    )

    # Context7: Add background tasks AFTER creating response
    # This ensures response is sent immediately
    background_tasks.add_task(send_email_notification, user.email, "Welcome to Pythinker!")
    background_tasks.add_task(log_user_action, current_user["id"], "user_created")

    return new_user


@app.get(
    "/users/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
    responses={
        200: {"description": "User found"},
        404: {"description": "User not found"},
    },
    tags=["Users"],
)
async def get_user(
    user_id: int,
    current_user: CurrentUser,
) -> UserResponse:
    """Get user by ID with security

    Context7: Use path parameters with automatic validation
    """
    if user_id != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this user",
        )

    return UserResponse(
        id=user_id,
        username=current_user["username"],
        email="user@example.com",
    )


# ============================================================================
# 7. GLOBAL DEPENDENCIES (Context7 Best Practice)
# ============================================================================


# Example: Apply security to all routes in a router
from fastapi import APIRouter  # noqa: E402 - Example code demonstrating router configuration

secure_router = APIRouter(
    prefix="/api/v1",
    tags=["Secure API"],
    dependencies=[Depends(verify_api_key)],  # Applied to ALL routes in this router
)


@secure_router.get("/protected")
async def protected_endpoint():
    """Endpoint protected by router-level dependency

    Context7: Use router dependencies for shared security
    """
    return {"message": "This endpoint is protected by API key"}


app.include_router(secure_router)


# ============================================================================
# 8. ERROR HANDLING (Context7 Best Practice)
# ============================================================================


@app.exception_handler(ValueError)
async def value_error_handler(request, exc: ValueError):
    """Custom exception handler for ValueError

    Context7: Register custom exception handlers for better error responses
    """
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(exc),
    )


# ============================================================================
# 9. HEALTH CHECK ENDPOINT
# ============================================================================


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint

    Context7: Always include health endpoints for monitoring
    """
    return {
        "status": "healthy",
        "service": "pythinker-api",
        "models_loaded": len(app.state.ml_models),
    }


# ============================================================================
# 10. STARTUP BANNER (Context7: Log important configuration)
# ============================================================================


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Pythinker API - FastAPI 2026 Best Practices",
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
    }


# ============================================================================
# MIGRATION GUIDE: Old → New Patterns
# ============================================================================

"""
OLD PATTERN (Pre-2024):
────────────────────────
@app.on_event("startup")
async def startup():
    app.state.db = connect_db()

@app.on_event("shutdown")
async def shutdown():
    app.state.db.close()

@app.post("/users")
async def create_user(
    user: UserCreate,
    x_api_key: str = Header(None)
):
    if not x_api_key:
        raise HTTPException(401)
    return {"id": 1}


NEW PATTERN (2026 - Context7 Validated):
────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = connect_db()
    yield
    app.state.db.close()

app = FastAPI(lifespan=lifespan)

@app.post("/users", response_model=UserResponse)
async def create_user(
    user: UserCreate,
    api_key: Annotated[str, Depends(verify_api_key)],
    background_tasks: BackgroundTasks,
) -> UserResponse:
    background_tasks.add_task(send_notification)
    return UserResponse(id=1, username=user.username)


BENEFITS:
✅ Type safety with Annotated
✅ Automatic OpenAPI documentation
✅ Better dependency injection
✅ Cleaner lifespan management
✅ Background task support
✅ Response model validation
"""
