from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel
from stores import skill_store
from routes.auth import _get_current_user

router = APIRouter(prefix="/skills")


def _wrap(data):
    return {"code": 0, "msg": "success", "data": data}


@router.get("")
async def list_skills(category: str | None = None):
    skills = skill_store.get_all_skills(category)
    return _wrap({"skills": skills, "total": len(skills)})


@router.get("/user/config")
async def get_user_skills(request: Request):
    user = _get_current_user(request)
    user_skills = skill_store.get_user_skills(user["id"])
    enabled = sum(1 for s in user_skills if s.get("enabled"))
    return _wrap({"skills": user_skills, "enabled_count": enabled, "max_skills": 10})


class UpdateUserSkillRequest(BaseModel):
    enabled: bool | None = None
    config: dict | None = None
    order: int | None = None


@router.put("/user/{skill_id}")
async def update_user_skill(
    skill_id: str, req: UpdateUserSkillRequest, request: Request
):
    user = _get_current_user(request)
    result = skill_store.update_user_skill(
        user["id"], skill_id, req.enabled, req.config, req.order
    )
    if not result:
        return {"code": 404, "msg": "Skill not found", "data": None}
    return _wrap(result)


class EnableSkillsRequest(BaseModel):
    skill_ids: list[str]


@router.post("/user/enable")
async def enable_skills(req: EnableSkillsRequest, request: Request):
    user = _get_current_user(request)
    for sid in req.skill_ids:
        skill_store.update_user_skill(user["id"], sid, enabled=True)
    user_skills = skill_store.get_user_skills(user["id"])
    enabled = sum(1 for s in user_skills if s.get("enabled"))
    return _wrap({"skills": user_skills, "enabled_count": enabled, "max_skills": 10})


@router.get("/tools/required")
async def get_required_tools(skill_ids: str = ""):
    ids = [s.strip() for s in skill_ids.split(",") if s.strip()]
    tools = set()
    for sid in ids:
        skill = skill_store.get_skill(sid)
        if skill:
            tools.update(skill.get("required_tools", []))
    return _wrap({"skill_ids": ids, "tools": list(tools)})


class CreateCustomSkillRequest(BaseModel):
    name: str
    description: str = ""
    category: str = "custom"
    icon: str = "puzzle"
    required_tools: list[str] = []
    optional_tools: list[str] = []
    system_prompt_addition: str = ""
    invocation_type: str = "both"
    allowed_tools: list[str] | None = None
    supports_dynamic_context: bool = False
    trigger_patterns: list[str] = []


@router.post("/custom")
async def create_custom_skill(req: CreateCustomSkillRequest, request: Request):
    user = _get_current_user(request)
    skill = skill_store.create_custom_skill(user["id"], req.model_dump())
    return _wrap(skill)


@router.get("/custom")
async def list_custom_skills(request: Request):
    user = _get_current_user(request)
    skills = skill_store.get_custom_skills(user["id"])
    return _wrap({"skills": skills, "total": len(skills)})


@router.get("/custom/{skill_id}")
async def get_custom_skill(skill_id: str):
    skill = skill_store.get_skill(skill_id)
    if not skill:
        return {"code": 404, "msg": "Skill not found", "data": None}
    return _wrap(skill)


class UpdateCustomSkillRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    required_tools: list[str] | None = None
    optional_tools: list[str] | None = None
    system_prompt_addition: str | None = None
    invocation_type: str | None = None
    allowed_tools: list[str] | None = None
    supports_dynamic_context: bool | None = None
    trigger_patterns: list[str] | None = None


@router.put("/custom/{skill_id}")
async def update_custom_skill(skill_id: str, req: UpdateCustomSkillRequest):
    skill = skill_store.get_skill(skill_id)
    if not skill:
        return {"code": 404, "msg": "Skill not found", "data": None}
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    skill.update(updates)
    return _wrap(skill)


@router.delete("/custom/{skill_id}")
async def delete_custom_skill(skill_id: str):
    skill_store.delete_custom_skill(skill_id)
    return _wrap({})


class PublishRequest(BaseModel):
    confirm: bool = True


@router.post("/custom/{skill_id}/publish")
async def publish_custom_skill(skill_id: str, req: PublishRequest):
    skill = skill_store.get_skill(skill_id)
    if not skill:
        return {"code": 404, "msg": "Skill not found", "data": None}
    skill["is_public"] = True
    return _wrap(skill)


@router.get("/packages/{package_id}")
async def get_skill_package(package_id: str):
    return _wrap(
        {
            "id": package_id,
            "name": "Demo Skill Package",
            "description": "A demonstration skill package",
            "version": "1.0.0",
            "icon": "package",
            "category": "demo",
            "author": "Pythinker",
            "file_tree": {"src": {"type": "file", "path": "src/main.py", "size": 256}},
            "files": [
                {
                    "path": "src/main.py",
                    "content": "# Demo skill\nprint('hello')",
                    "size": 256,
                }
            ],
            "file_count": 1,
            "created_at": "2025-12-01T00:00:00Z",
        }
    )


@router.get("/packages/{package_id}/download")
async def download_skill_package(package_id: str):
    from fastapi.responses import Response

    return Response(
        content=b"PK\x03\x04mock_skill_package",
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{package_id}.skill"'},
    )


@router.get("/packages/{package_id}/file")
async def get_skill_package_file(package_id: str, path: str = ""):
    return _wrap(
        {
            "path": path,
            "content": "# Demo skill file content\nprint('hello')",
            "size": 128,
        }
    )


class InstallPackageRequest(BaseModel):
    enable_after_install: bool = True


@router.post("/packages/{package_id}/install")
async def install_skill_package(package_id: str, req: InstallPackageRequest):
    # Return a mock installed skill
    return _wrap(
        {
            "id": f"skill_installed_{package_id[:8]}",
            "name": "Installed Skill",
            "description": "Installed from package",
            "category": "custom",
            "source": "custom",
            "icon": "package",
            "required_tools": [],
            "optional_tools": [],
            "is_premium": False,
            "default_enabled": req.enable_after_install,
            "version": "1.0.0",
            "author": None,
            "updated_at": "2025-12-01T00:00:00Z",
        }
    )


# Must be AFTER /custom and /user routes to avoid path conflicts
@router.get("/{skill_id}")
async def get_skill(skill_id: str):
    skill = skill_store.get_skill(skill_id)
    if not skill:
        return {"code": 404, "msg": "Skill not found", "data": None}
    return _wrap(skill)
