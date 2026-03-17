"""API routes for managing skills."""

import logging
import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from app.application.services.skill_service import get_skill_service
from app.core.config import get_settings as get_app_settings
from app.domain.models.skill import Skill, SkillCategory, SkillSource
from app.domain.models.user import User
from app.infrastructure.storage.mongodb import get_mongodb
from app.interfaces.dependencies import get_current_user
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.skill import (
    CommandListResponse,
    CommandMapResponse,
    CommandResponse,
    CreateCustomSkillRequest,
    CustomSkillListResponse,
    EnableSkillsRequest,
    InstallSkillFromPackageRequest,
    PublishSkillRequest,
    SkillDeleteResponse,
    SkillListResponse,
    SkillPackageFileResponse,
    SkillPackageResponse,
    SkillRateResponse,
    SkillResponse,
    SkillToolsResponse,
    UpdateCustomSkillRequest,
    UpdateUserSkillRequest,
    UserSkillResponse,
    UserSkillsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skills", tags=["skills"])

MAX_ENABLED_SKILLS = 5


def _skill_to_response(skill, include_prompt: bool = False) -> SkillResponse:
    """Convert skill domain model to response schema.

    Args:
        skill: Skill domain model
        include_prompt: Whether to include system_prompt_addition (for editing)
    """
    return SkillResponse(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        category=skill.category.value,
        source=skill.source.value,
        icon=skill.icon,
        required_tools=skill.required_tools,
        optional_tools=skill.optional_tools,
        is_premium=skill.is_premium,
        default_enabled=skill.default_enabled,
        version=skill.version,
        author=skill.author,
        updated_at=skill.updated_at,
        owner_id=skill.owner_id,
        is_public=skill.is_public,
        parent_skill_id=skill.parent_skill_id,
        system_prompt_addition=skill.system_prompt_addition if include_prompt else None,
        # Claude-style configuration fields
        invocation_type=skill.invocation_type.value
        if hasattr(skill.invocation_type, "value")
        else skill.invocation_type,
        allowed_tools=skill.allowed_tools,
        supports_dynamic_context=skill.supports_dynamic_context,
        trigger_patterns=skill.trigger_patterns,
        # Marketplace fields
        community_rating=getattr(skill, "community_rating", 0.0),
        rating_count=getattr(skill, "rating_count", 0),
        install_count=getattr(skill, "install_count", 0),
        is_featured=getattr(skill, "is_featured", False),
        tags=getattr(skill, "tags", []),
    )


@router.get("", response_model=APIResponse[SkillListResponse])
async def get_available_skills(
    category: str | None = None,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillListResponse]:
    """Get all available skills, optionally filtered by category."""
    skill_service = get_skill_service()

    if category:
        try:
            skill_category = SkillCategory(category)
            skills = await skill_service.get_skills_by_category(skill_category)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}") from e
    else:
        skills = await skill_service.get_available_skills()

    skill_responses = [_skill_to_response(skill) for skill in skills]

    return APIResponse.success(
        SkillListResponse(
            skills=skill_responses,
            total=len(skill_responses),
        )
    )


@router.get("/community", response_model=APIResponse[SkillListResponse])
async def get_community_skills(
    category: str | None = None,
    search: str | None = None,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillListResponse]:
    """Get public/community skills shared by other users.

    Args:
        category: Optional category filter
        search: Optional search term for name/description

    Returns:
        List of public community skills available for installation
    """
    skill_service = get_skill_service()

    # Get all public skills
    skills = await skill_service.get_public_skills()

    # Filter by category if specified
    if category:
        try:
            skill_category = SkillCategory(category)
            skills = [s for s in skills if s.category == skill_category]
        except ValueError:
            # Invalid category, return empty
            skills = []

    # Filter by search term if specified
    if search:
        search_lower = search.lower()
        skills = [s for s in skills if search_lower in s.name.lower() or search_lower in s.description.lower()]

    skill_responses = [_skill_to_response(skill) for skill in skills]

    return APIResponse.success(
        SkillListResponse(
            skills=skill_responses,
            total=len(skill_responses),
        )
    )


# =============================================================================
# MARKETPLACE ENDPOINTS (Phase 2: Skill Marketplace)
# =============================================================================


@router.get("/marketplace/search", response_model=APIResponse[SkillListResponse])
async def search_marketplace_skills(
    q: str | None = None,
    category: str | None = None,
    tags: str | None = None,  # Comma-separated tags
    min_rating: float | None = None,
    featured: bool | None = None,
    sort_by: str = "community_rating",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillListResponse]:
    """Search the skill marketplace with filters.

    Args:
        q: Search query for name/description
        category: Category filter
        tags: Comma-separated tags to filter by
        min_rating: Minimum community rating (1-5)
        featured: Filter to featured skills only
        sort_by: Field to sort by (community_rating, install_count, created_at)
        sort_order: Sort direction (asc, desc)
        page: Page number (1-indexed)
        page_size: Results per page (max 50)

    Returns:
        Paginated list of matching skills
    """
    from app.infrastructure.repositories.mongo_skill_repository import (
        ALLOWED_SORT_FIELDS,
        MongoSkillRepository,
        SkillSearchFilters,
    )

    # Validate sort_by against allowlist to prevent NoSQL injection
    if sort_by not in ALLOWED_SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort field: '{sort_by}'. Allowed: {', '.join(sorted(ALLOWED_SORT_FIELDS))}",
        )

    # Parse inputs
    skill_category = None
    if category:
        try:
            skill_category = SkillCategory(category)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}") from exc

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    # Build filters
    filters = SkillSearchFilters(
        query=q,
        category=skill_category,
        min_rating=min_rating,
        tags=tag_list,
        is_featured=featured,
        is_public=True,
    )

    # Validate pagination
    page = max(1, page)
    page_size = min(50, max(1, page_size))
    skip = (page - 1) * page_size

    # Sort order
    order = -1 if sort_order.lower() == "desc" else 1

    # Search
    repo = MongoSkillRepository()
    skills, total = await repo.search(filters, skip=skip, limit=page_size, sort_by=sort_by, sort_order=order)

    return APIResponse.success(
        SkillListResponse(
            skills=[_skill_to_response(s) for s in skills],
            total=total,
        )
    )


@router.get("/marketplace/featured", response_model=APIResponse[SkillListResponse])
async def get_featured_skills(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillListResponse]:
    """Get featured skills from the marketplace."""
    from app.infrastructure.repositories.mongo_skill_repository import MongoSkillRepository

    repo = MongoSkillRepository()
    skills = await repo.get_featured(limit=min(limit, 20))

    return APIResponse.success(
        SkillListResponse(
            skills=[_skill_to_response(s) for s in skills],
            total=len(skills),
        )
    )


@router.get("/marketplace/popular", response_model=APIResponse[SkillListResponse])
async def get_popular_skills(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillListResponse]:
    """Get most popular skills by usage and rating."""
    from app.infrastructure.repositories.mongo_skill_repository import MongoSkillRepository

    repo = MongoSkillRepository()
    skills = await repo.get_popular(limit=min(limit, 20))

    return APIResponse.success(
        SkillListResponse(
            skills=[_skill_to_response(s) for s in skills],
            total=len(skills),
        )
    )


@router.get("/marketplace/recent", response_model=APIResponse[SkillListResponse])
async def get_recent_skills(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillListResponse]:
    """Get recently added public skills."""
    from app.infrastructure.repositories.mongo_skill_repository import MongoSkillRepository

    repo = MongoSkillRepository()
    skills = await repo.get_recent(limit=min(limit, 20))

    return APIResponse.success(
        SkillListResponse(
            skills=[_skill_to_response(s) for s in skills],
            total=len(skills),
        )
    )


@router.post("/marketplace/{skill_id}/rate", response_model=APIResponse[SkillRateResponse])
async def rate_skill(
    skill_id: str,
    rating: float,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillRateResponse]:
    """Rate a skill in the marketplace.

    Args:
        skill_id: Skill to rate
        rating: Rating value (1-5)

    Returns:
        Success confirmation
    """
    from app.infrastructure.repositories.mongo_skill_repository import MongoSkillRepository

    if not 1 <= rating <= 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    repo = MongoSkillRepository()
    success = await repo.rate_skill(skill_id, str(current_user.id), rating)

    if not success:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    return APIResponse.success(SkillRateResponse(rated=True, skill_id=skill_id, rating=rating))


@router.post("/marketplace/{skill_id}/fork", response_model=APIResponse[SkillResponse])
async def fork_skill(
    skill_id: str,
    new_name: str | None = None,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillResponse]:
    """Fork a public skill to customize it.

    Args:
        skill_id: Skill to fork
        new_name: Optional new name for the fork

    Returns:
        The newly created forked skill
    """
    from app.infrastructure.repositories.mongo_skill_repository import MongoSkillRepository

    repo = MongoSkillRepository()
    forked = await repo.fork_skill(skill_id, str(current_user.id), new_name)

    if not forked:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    logger.info(f"User {current_user.id} forked skill {skill_id} to {forked.id}")

    return APIResponse.success(_skill_to_response(forked, include_prompt=True))


# User config routes must come BEFORE /{skill_id} to avoid path conflicts
@router.get("/user/config", response_model=APIResponse[UserSkillsResponse])
async def get_user_skills(
    current_user: User = Depends(get_current_user),
) -> APIResponse[UserSkillsResponse]:
    """Get current user's skill configurations."""
    skill_service = get_skill_service()
    app_settings = get_app_settings()
    mongodb = get_mongodb()
    db = mongodb.client[app_settings.mongodb_database]
    settings_collection = db.get_collection("user_settings")

    # Get user settings
    settings_doc = await settings_collection.find_one({"user_id": str(current_user.id)})
    enabled_skill_ids = settings_doc.get("enabled_skills", []) if settings_doc else []
    skill_configs = settings_doc.get("skill_configs", {}) if settings_doc else {}

    # Get all skills
    all_skills = await skill_service.get_available_skills()
    enabled_set = set(enabled_skill_ids)

    # Build user skill responses
    user_skills = []
    for i, skill in enumerate(all_skills):
        user_skills.append(
            UserSkillResponse(
                skill=_skill_to_response(skill),
                enabled=skill.id in enabled_set,
                config=skill_configs.get(skill.id, {}),
                order=i,
            )
        )

    return APIResponse.success(
        UserSkillsResponse(
            skills=user_skills,
            enabled_count=len([s for s in user_skills if s.enabled]),
            max_skills=MAX_ENABLED_SKILLS,
        )
    )


@router.put("/user/{skill_id}", response_model=APIResponse[UserSkillResponse])
async def update_user_skill(
    skill_id: str,
    request: UpdateUserSkillRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[UserSkillResponse]:
    """Enable/disable or configure a skill for the current user."""
    skill_service = get_skill_service()
    app_settings = get_app_settings()
    mongodb = get_mongodb()
    db = mongodb.client[app_settings.mongodb_database]
    settings_collection = db.get_collection("user_settings")

    # Verify skill exists
    skill = await skill_service.get_skill_by_id(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    # Get user settings
    settings_doc = await settings_collection.find_one({"user_id": str(current_user.id)})
    if not settings_doc:
        settings_doc = {"user_id": str(current_user.id), "enabled_skills": [], "skill_configs": {}}

    enabled_skills = settings_doc.get("enabled_skills", [])
    skill_configs = settings_doc.get("skill_configs", {})

    # Handle enable/disable
    if request.enabled is not None:
        if request.enabled:
            # Check max skills limit
            if skill_id not in enabled_skills:
                if len(enabled_skills) >= MAX_ENABLED_SKILLS:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Maximum {MAX_ENABLED_SKILLS} skills allowed. Remove a skill to add another.",
                    )
                enabled_skills.append(skill_id)
        else:
            if skill_id in enabled_skills:
                enabled_skills.remove(skill_id)

    # Handle config update
    if request.config is not None:
        skill_configs[skill_id] = request.config

    # Save to database
    await settings_collection.update_one(
        {"user_id": str(current_user.id)},
        {
            "$set": {
                "enabled_skills": enabled_skills,
                "skill_configs": skill_configs,
            }
        },
        upsert=True,
    )

    return APIResponse.success(
        UserSkillResponse(
            skill=_skill_to_response(skill),
            enabled=skill_id in enabled_skills,
            config=skill_configs.get(skill_id, {}),
            order=0,
        )
    )


@router.post("/user/enable", response_model=APIResponse[UserSkillsResponse])
async def enable_skills(
    request: EnableSkillsRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[UserSkillsResponse]:
    """Enable multiple skills at once (replaces current enabled skills)."""
    skill_service = get_skill_service()
    app_settings = get_app_settings()
    mongodb = get_mongodb()
    db = mongodb.client[app_settings.mongodb_database]
    settings_collection = db.get_collection("user_settings")

    # Check skill limit
    if len(request.skill_ids) > MAX_ENABLED_SKILLS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_ENABLED_SKILLS} skills allowed.",
        )

    # Verify all skills exist
    skills = await skill_service.get_skills_by_ids(request.skill_ids)
    found_ids = {s.id for s in skills}
    missing_ids = set(request.skill_ids) - found_ids
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Skills not found: {', '.join(missing_ids)}")

    # Get user settings
    settings_doc = await settings_collection.find_one({"user_id": str(current_user.id)})
    skill_configs = settings_doc.get("skill_configs", {}) if settings_doc else {}

    # Save to database
    await settings_collection.update_one(
        {"user_id": str(current_user.id)},
        {"$set": {"enabled_skills": request.skill_ids}},
        upsert=True,
    )

    # Build response
    all_skills = await skill_service.get_available_skills()
    enabled_set = set(request.skill_ids)
    user_skills = []
    for i, skill in enumerate(all_skills):
        user_skills.append(
            UserSkillResponse(
                skill=_skill_to_response(skill),
                enabled=skill.id in enabled_set,
                config=skill_configs.get(skill.id, {}),
                order=i,
            )
        )

    return APIResponse.success(
        UserSkillsResponse(
            skills=user_skills,
            enabled_count=len(request.skill_ids),
            max_skills=MAX_ENABLED_SKILLS,
        )
    )


@router.get("/tools/required", response_model=APIResponse[SkillToolsResponse])
async def get_skill_tools(
    skill_ids: str,  # Comma-separated list
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillToolsResponse]:
    """Get all tools required by the specified skills."""
    skill_service = get_skill_service()

    # Parse skill IDs
    skill_id_list = [s.strip() for s in skill_ids.split(",") if s.strip()]
    if not skill_id_list:
        return APIResponse.success(SkillToolsResponse(skill_ids=[], tools=[]))

    # Get tools
    tools = await skill_service.get_tools_for_skill_ids(skill_id_list)

    return APIResponse.success(
        SkillToolsResponse(
            skill_ids=skill_id_list,
            tools=sorted(tools),
        )
    )


# =============================================================================
# CUSTOM SKILL CRUD ENDPOINTS (Phase 2)
# =============================================================================


def _generate_skill_id(name: str, owner_id: str) -> str:
    """Generate a unique skill ID from name and owner.

    Creates a slug from the name with a short UUID suffix for uniqueness.
    """
    # Slugify the name
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    # Add short UUID for uniqueness
    short_uuid = str(uuid.uuid4())[:8]
    return f"custom-{slug}-{short_uuid}"


def _validate_custom_skill_tools(required_tools: list[str], optional_tools: list[str]) -> list[str]:
    """Validate that tools are in the allowed set.

    Returns list of validation errors.
    """
    # Import here to avoid circular imports
    from app.domain.services.skill_validator import CustomSkillValidator

    all_tools = set(required_tools + optional_tools)
    invalid = all_tools - CustomSkillValidator.ALLOWED_TOOLS
    if invalid:
        return [f"Invalid tools: {', '.join(sorted(invalid))}"]
    if len(all_tools) > CustomSkillValidator.MAX_TOOLS:
        return [f"Too many tools: {len(all_tools)} > {CustomSkillValidator.MAX_TOOLS}"]
    return []


@router.post("/custom", response_model=APIResponse[SkillResponse])
async def create_custom_skill(
    request: CreateCustomSkillRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillResponse]:
    """Create a new custom skill for the current user."""
    # Import validator
    from app.domain.services.skill_validator import CustomSkillValidator

    skill_service = get_skill_service()

    # Generate skill ID
    skill_id = _generate_skill_id(request.name, str(current_user.id))

    # Parse invocation type from request
    from app.domain.models.skill import SkillInvocationType

    try:
        invocation_type = SkillInvocationType(request.invocation_type)
    except ValueError:
        invocation_type = SkillInvocationType.BOTH

    # Create skill domain object
    skill = Skill(
        id=skill_id,
        name=request.name,
        description=request.description,
        category=SkillCategory(request.category) if request.category != "custom" else SkillCategory.CUSTOM,
        source=SkillSource.CUSTOM,
        icon=request.icon,
        required_tools=request.required_tools,
        optional_tools=request.optional_tools,
        system_prompt_addition=request.system_prompt_addition,
        owner_id=str(current_user.id),
        is_public=False,
        default_enabled=False,
        version="1.0.0",
        author=current_user.fullname or str(current_user.id),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        # Claude-style configuration fields
        invocation_type=invocation_type,
        allowed_tools=request.allowed_tools,
        # SECURITY: Only official skills can use dynamic context (enforced in skill_context.py)
        # Custom skills can request it but it will be blocked at execution time
        supports_dynamic_context=request.supports_dynamic_context,
        trigger_patterns=request.trigger_patterns,
    )

    # Validate the skill
    errors = CustomSkillValidator.validate(skill)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    # Create in database
    created_skill = await skill_service.create_skill(skill)
    logger.info(f"Created custom skill {skill_id} for user {current_user.id}")

    # Invalidate trigger matcher cache if skill has trigger patterns
    if created_skill.trigger_patterns:
        from app.domain.services.skill_registry import invalidate_skill_caches

        await invalidate_skill_caches(created_skill.id)

    return APIResponse.success(_skill_to_response(created_skill, include_prompt=True))


@router.get("/custom", response_model=APIResponse[CustomSkillListResponse])
async def get_my_custom_skills(
    current_user: User = Depends(get_current_user),
) -> APIResponse[CustomSkillListResponse]:
    """Get all custom skills owned by the current user."""
    skill_service = get_skill_service()

    skills = await skill_service.get_skills_by_owner(str(current_user.id))

    return APIResponse.success(
        CustomSkillListResponse(
            skills=[_skill_to_response(s, include_prompt=True) for s in skills],
            total=len(skills),
        )
    )


@router.get("/custom/{skill_id}", response_model=APIResponse[SkillResponse])
async def get_custom_skill(
    skill_id: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillResponse]:
    """Get a specific custom skill by ID."""
    skill_service = get_skill_service()
    skill = await skill_service.get_skill_by_id(skill_id)

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    # Verify ownership
    if skill.owner_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="You don't have access to this skill")

    return APIResponse.success(_skill_to_response(skill, include_prompt=True))


@router.put("/custom/{skill_id}", response_model=APIResponse[SkillResponse])
async def update_custom_skill(
    skill_id: str,
    request: UpdateCustomSkillRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillResponse]:
    """Update a custom skill owned by the current user."""
    from app.domain.services.skill_validator import CustomSkillValidator

    skill_service = get_skill_service()
    skill = await skill_service.get_skill_by_id(skill_id)

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    # Verify ownership
    if skill.owner_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="You don't have access to this skill")

    # Can't update published skills
    if skill.is_public:
        raise HTTPException(status_code=400, detail="Cannot update a published skill")

    # Apply updates
    if request.name is not None:
        skill.name = request.name
    if request.description is not None:
        skill.description = request.description
    if request.icon is not None:
        skill.icon = request.icon
    if request.required_tools is not None:
        skill.required_tools = request.required_tools
    if request.optional_tools is not None:
        skill.optional_tools = request.optional_tools
    if request.system_prompt_addition is not None:
        skill.system_prompt_addition = request.system_prompt_addition

    # Claude-style configuration field updates
    if request.invocation_type is not None:
        from app.domain.models.skill import SkillInvocationType

        try:
            skill.invocation_type = SkillInvocationType(request.invocation_type)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid invocation_type: {request.invocation_type}. Must be 'user', 'ai', or 'both'",
            ) from e
    if request.allowed_tools is not None:
        skill.allowed_tools = request.allowed_tools or None
    if request.supports_dynamic_context is not None:
        skill.supports_dynamic_context = request.supports_dynamic_context
    if request.trigger_patterns is not None:
        skill.trigger_patterns = request.trigger_patterns

    skill.updated_at = datetime.now(UTC)

    # Re-validate after updates
    errors = CustomSkillValidator.validate(skill)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    # Update in database
    updated_skill = await skill_service.update_skill(skill_id, skill)
    if not updated_skill:
        raise HTTPException(status_code=500, detail="Failed to update skill")

    logger.info(f"Updated custom skill {skill_id} for user {current_user.id}")

    # Invalidate trigger matcher cache for this skill
    from app.domain.services.skill_registry import invalidate_skill_caches

    await invalidate_skill_caches(skill_id)

    return APIResponse.success(_skill_to_response(updated_skill, include_prompt=True))


@router.delete("/custom/{skill_id}", response_model=APIResponse[SkillDeleteResponse])
async def delete_custom_skill(
    skill_id: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillDeleteResponse]:
    """Delete a custom skill owned by the current user."""
    skill_service = get_skill_service()
    skill = await skill_service.get_skill_by_id(skill_id)

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    # Verify ownership
    if skill.owner_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="You don't have access to this skill")

    # Delete from database
    success = await skill_service.delete_skill(skill_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete skill")

    logger.info(f"Deleted custom skill {skill_id} for user {current_user.id}")

    # Invalidate trigger matcher cache for this skill
    from app.domain.services.skill_registry import invalidate_skill_caches

    await invalidate_skill_caches(skill_id)

    return APIResponse.success(SkillDeleteResponse(deleted=True, skill_id=skill_id))


@router.post("/custom/{skill_id}/publish", response_model=APIResponse[SkillResponse])
async def publish_custom_skill(
    skill_id: str,
    request: PublishSkillRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillResponse]:
    """Publish a custom skill to the community."""
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Publication not confirmed")

    skill_service = get_skill_service()
    skill = await skill_service.get_skill_by_id(skill_id)

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    # Verify ownership
    if skill.owner_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="You don't have access to this skill")

    if skill.is_public:
        raise HTTPException(status_code=400, detail="Skill is already published")

    # Update to published
    skill.is_public = True
    skill.source = SkillSource.COMMUNITY
    skill.updated_at = datetime.now(UTC)

    updated_skill = await skill_service.update_skill(skill_id, skill)
    if not updated_skill:
        raise HTTPException(status_code=500, detail="Failed to publish skill")

    logger.info(f"Published custom skill {skill_id} to community by user {current_user.id}")

    # Invalidate trigger matcher cache for this skill
    from app.domain.services.skill_registry import invalidate_skill_caches

    await invalidate_skill_caches(skill_id)

    return APIResponse.success(_skill_to_response(updated_skill, include_prompt=True))


# =============================================================================
# SKILL PACKAGE ENDPOINTS (for skill delivery)
# =============================================================================


@router.get("/packages/{package_id}", response_model=APIResponse[SkillPackageResponse])
async def get_skill_package(
    package_id: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillPackageResponse]:
    """Get a skill package by ID."""

    app_settings = get_app_settings()
    mongodb = get_mongodb()
    db = mongodb.client[app_settings.mongodb_database]

    # Look up package in packages collection
    packages_collection = db.get_collection("skill_packages")
    package_doc = await packages_collection.find_one({"id": package_id})

    if not package_doc:
        raise HTTPException(status_code=404, detail=f"Package not found: {package_id}")

    return APIResponse.success(
        SkillPackageResponse(
            id=package_doc["id"],
            name=package_doc["name"],
            description=package_doc["description"],
            version=package_doc.get("version", "1.0.0"),
            icon=package_doc.get("icon", "puzzle"),
            category=package_doc.get("category", "custom"),
            author=package_doc.get("author"),
            file_tree=package_doc.get("file_tree", {}),
            files=[
                SkillPackageFileResponse(
                    path=f["path"],
                    content=f["content"],
                    size=f["size"],
                )
                for f in package_doc.get("files", [])
            ],
            file_id=package_doc.get("file_id"),
            skill_id=package_doc.get("skill_id"),
            file_count=len(package_doc.get("files", [])),
            created_at=package_doc.get("created_at"),
        )
    )


@router.get("/packages/{package_id}/download")
async def download_skill_package(
    package_id: str,
    current_user: User = Depends(get_current_user),
):
    """Download a skill package as a .skill ZIP file."""
    from fastapi.responses import StreamingResponse

    from app.domain.models.skill_package import SkillPackage, SkillPackageFile
    from app.domain.services.skill_packager import get_skill_packager

    app_settings = get_app_settings()
    mongodb = get_mongodb()
    db = mongodb.client[app_settings.mongodb_database]

    # Look up package in packages collection
    packages_collection = db.get_collection("skill_packages")
    package_doc = await packages_collection.find_one({"id": package_id})

    if not package_doc:
        raise HTTPException(status_code=404, detail=f"Package not found: {package_id}")

    # Reconstruct package object
    package = SkillPackage(
        id=package_doc["id"],
        name=package_doc["name"],
        description=package_doc["description"],
        version=package_doc.get("version", "1.0.0"),
        icon=package_doc.get("icon", "puzzle"),
        category=package_doc.get("category", "custom"),
        author=package_doc.get("author"),
        file_tree=package_doc.get("file_tree", {}),
        files=[
            SkillPackageFile(
                path=f["path"],
                content=f["content"],
                size=f["size"],
            )
            for f in package_doc.get("files", [])
        ],
        file_id=package_doc.get("file_id"),
        skill_id=package_doc.get("skill_id"),
    )

    # Create ZIP in memory
    packager = get_skill_packager()
    zip_buffer = packager.create_zip(package)

    # Stream the file as response
    filename = f"{package.name.lower().replace(' ', '-')}.skill"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/zip",
        },
    )


@router.get("/packages/{package_id}/file", response_model=APIResponse[SkillPackageFileResponse])
async def get_skill_package_file(
    package_id: str,
    path: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillPackageFileResponse]:
    """Get a single file from a skill package."""
    app_settings = get_app_settings()
    mongodb = get_mongodb()
    db = mongodb.client[app_settings.mongodb_database]

    # Look up package in packages collection
    packages_collection = db.get_collection("skill_packages")
    package_doc = await packages_collection.find_one({"id": package_id})

    if not package_doc:
        raise HTTPException(status_code=404, detail=f"Package not found: {package_id}")

    # Find the requested file
    for f in package_doc.get("files", []):
        if f["path"] == path:
            return APIResponse.success(
                SkillPackageFileResponse(
                    path=f["path"],
                    content=f["content"],
                    size=f["size"],
                )
            )

    raise HTTPException(status_code=404, detail=f"File not found in package: {path}")


def _parse_skill_md_frontmatter(content: str) -> tuple[dict, str]:
    """Parse SKILL.md content to extract YAML frontmatter and body.

    Args:
        content: Full SKILL.md content

    Returns:
        Tuple of (frontmatter_dict, body_content)
    """
    import yaml

    frontmatter: dict = {}
    body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                frontmatter = {}
            body = parts[2].strip()

    return frontmatter, body


@router.post("/packages/{package_id}/install", response_model=APIResponse[SkillResponse])
async def install_skill_from_package(
    package_id: str,
    request: InstallSkillFromPackageRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillResponse]:
    """Install a skill from a package to the user's skills.

    Extracts metadata from SKILL.md frontmatter and validates the skill
    before installation.
    """
    from app.domain.models.skill import SkillInvocationType
    from app.domain.services.skill_validator import CustomSkillValidator

    skill_service = get_skill_service()
    app_settings = get_app_settings()
    mongodb = get_mongodb()
    db = mongodb.client[app_settings.mongodb_database]

    # Look up package
    packages_collection = db.get_collection("skill_packages")
    package_doc = await packages_collection.find_one({"id": package_id})

    if not package_doc:
        raise HTTPException(status_code=404, detail=f"Package not found: {package_id}")

    # Check if skill already exists
    skill_id = package_doc.get("skill_id")
    if skill_id:
        existing_skill = await skill_service.get_skill_by_id(skill_id)
        if existing_skill:
            # Skill already exists, just enable it if requested
            if request.enable_after_install:
                settings_collection = db.get_collection("user_settings")
                settings_doc = await settings_collection.find_one({"user_id": str(current_user.id)})
                enabled_skills = settings_doc.get("enabled_skills", []) if settings_doc else []

                if skill_id not in enabled_skills:
                    if len(enabled_skills) >= MAX_ENABLED_SKILLS:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Maximum {MAX_ENABLED_SKILLS} skills allowed.",
                        )
                    enabled_skills.append(skill_id)
                    await settings_collection.update_one(
                        {"user_id": str(current_user.id)},
                        {"$set": {"enabled_skills": enabled_skills}},
                        upsert=True,
                    )

            return APIResponse.success(_skill_to_response(existing_skill))

    # Create new skill from package
    # Parse SKILL.md to extract frontmatter metadata and system prompt body
    frontmatter: dict = {}
    system_prompt = ""
    for f in package_doc.get("files", []):
        if f["path"] == "SKILL.md":
            frontmatter, system_prompt = _parse_skill_md_frontmatter(f["content"])
            break

    # Extract tool requirements from frontmatter
    required_tools = frontmatter.get("required_tools", [])
    optional_tools = frontmatter.get("optional_tools", [])

    # Ensure they are lists
    if not isinstance(required_tools, list):
        required_tools = [required_tools] if required_tools else []
    if not isinstance(optional_tools, list):
        optional_tools = [optional_tools] if optional_tools else []

    # Parse invocation type from frontmatter
    invocation_type_str = frontmatter.get("invocation_type", "both")
    try:
        invocation_type = SkillInvocationType(invocation_type_str)
    except ValueError:
        invocation_type = SkillInvocationType.BOTH

    # Extract other configuration fields
    allowed_tools = frontmatter.get("allowed_tools")
    if allowed_tools and not isinstance(allowed_tools, list):
        allowed_tools = None

    trigger_patterns = frontmatter.get("trigger_patterns", [])
    if not isinstance(trigger_patterns, list):
        trigger_patterns = []

    # Generate skill ID
    skill_id = _generate_skill_id(package_doc["name"], str(current_user.id))

    skill = Skill(
        id=skill_id,
        name=frontmatter.get("name") or package_doc["name"],
        description=frontmatter.get("description") or package_doc["description"],
        category=SkillCategory.CUSTOM,
        source=SkillSource.CUSTOM,
        icon=frontmatter.get("icon") or package_doc.get("icon", "puzzle"),
        required_tools=required_tools,
        optional_tools=optional_tools,
        system_prompt_addition=system_prompt,
        owner_id=str(current_user.id),
        is_public=False,
        default_enabled=False,
        version=frontmatter.get("version") or package_doc.get("version", "1.0.0"),
        author=frontmatter.get("author") or package_doc.get("author") or current_user.fullname or str(current_user.id),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        # Claude-style configuration from frontmatter
        invocation_type=invocation_type,
        allowed_tools=allowed_tools,
        # SECURITY: Dynamic context is disabled for custom skills at runtime
        supports_dynamic_context=frontmatter.get("supports_dynamic_context", False),
        trigger_patterns=trigger_patterns,
    )

    # Validate the skill before creation
    errors = CustomSkillValidator.validate(skill)
    if errors:
        raise HTTPException(status_code=400, detail=f"Invalid skill package: {'; '.join(errors)}")

    created_skill = await skill_service.create_skill(skill)

    # Invalidate caches so the new skill is immediately available
    from app.domain.services.skill_registry import invalidate_skill_caches

    await invalidate_skill_caches(skill_id)

    # Update package with skill_id reference
    await packages_collection.update_one(
        {"id": package_id},
        {"$set": {"skill_id": skill_id}},
    )

    # Enable if requested
    if request.enable_after_install:
        settings_collection = db.get_collection("user_settings")
        settings_doc = await settings_collection.find_one({"user_id": str(current_user.id)})
        enabled_skills = settings_doc.get("enabled_skills", []) if settings_doc else []

        if skill_id not in enabled_skills and len(enabled_skills) < MAX_ENABLED_SKILLS:
            enabled_skills.append(skill_id)
            await settings_collection.update_one(
                {"user_id": str(current_user.id)},
                {"$set": {"enabled_skills": enabled_skills}},
                upsert=True,
            )

    logger.info(f"Installed skill {skill_id} from package {package_id} for user {current_user.id}")

    return APIResponse.success(_skill_to_response(created_skill, include_prompt=True))


# =============================================================================
# COMMAND SYSTEM
# =============================================================================


@router.get("/commands/available", response_model=APIResponse[CommandListResponse])
async def get_available_commands(
    current_user: User = Depends(get_current_user),
) -> APIResponse[CommandListResponse]:
    """Get list of available custom commands.

    Commands provide user-friendly shortcuts for skill invocation.
    etc.
    """
    from app.domain.services.command_registry import get_command_registry

    registry = get_command_registry()
    commands_list = registry.get_available_commands()

    command_responses = [
        CommandResponse(command=cmd, skill_id=skill_id, description=desc) for cmd, skill_id, desc in commands_list
    ]

    return APIResponse.success(
        CommandListResponse(
            commands=command_responses,
            count=len(command_responses),
        )
    )


@router.get("/commands/map", response_model=APIResponse[CommandMapResponse])
async def get_command_map(
    current_user: User = Depends(get_current_user),
) -> APIResponse[CommandMapResponse]:
    """Get full command/alias -> skill_id mapping for slash command detection.

    Used by the chat input to identify when user types /brainstorm, /design,
    /plan-design, etc. and auto-select the corresponding skill.
    """
    from app.domain.services.command_registry import get_command_registry

    registry = get_command_registry()
    command_map = registry.get_command_map()

    return APIResponse.success(CommandMapResponse(command_map=command_map))


# =============================================================================
# PARAMETERIZED ROUTE (must come LAST)
# =============================================================================


# Parameterized route must come LAST to avoid matching /user/config, /tools/required, /custom, etc.
@router.get("/{skill_id}", response_model=APIResponse[SkillResponse])
async def get_skill(
    skill_id: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillResponse]:
    """Get a specific skill by ID."""
    skill_service = get_skill_service()
    skill = await skill_service.get_skill_by_id(skill_id)

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    return APIResponse.success(_skill_to_response(skill))
