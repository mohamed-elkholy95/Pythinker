from __future__ import annotations
import uuid
from datetime import datetime, timezone

# Pre-seeded official skills
OFFICIAL_SKILLS: list[dict] = [
    {
        "id": "skill_research",
        "name": "Deep Research",
        "description": "Conduct comprehensive multi-source research with parallel searches and synthesis",
        "category": "research",
        "source": "official",
        "icon": "search",
        "required_tools": ["info_search_web", "browser_get_content"],
        "optional_tools": ["file_write"],
        "is_premium": False,
        "default_enabled": True,
        "version": "1.2.0",
        "author": "Pythinker",
        "updated_at": "2025-12-01T00:00:00Z",
    },
    {
        "id": "skill_code_dev",
        "name": "Code Development",
        "description": "Write, debug, and refactor code with best practices and testing",
        "category": "development",
        "source": "official",
        "icon": "code",
        "required_tools": ["file_write", "shell_exec"],
        "optional_tools": ["file_read", "browser_get_content"],
        "is_premium": False,
        "default_enabled": True,
        "version": "2.0.1",
        "author": "Pythinker",
        "updated_at": "2025-12-01T00:00:00Z",
    },
    {
        "id": "skill_data_analysis",
        "name": "Data Analysis",
        "description": "Analyze datasets, create visualizations, and generate statistical reports",
        "category": "analysis",
        "source": "official",
        "icon": "bar-chart",
        "required_tools": ["shell_exec", "file_write"],
        "optional_tools": ["file_read"],
        "is_premium": False,
        "default_enabled": False,
        "version": "1.1.0",
        "author": "Pythinker",
        "updated_at": "2025-11-15T00:00:00Z",
    },
    {
        "id": "skill_writing",
        "name": "Technical Writing",
        "description": "Create documentation, reports, and technical content with proper formatting",
        "category": "writing",
        "source": "official",
        "icon": "file-text",
        "required_tools": ["file_write"],
        "optional_tools": ["info_search_web", "browser_get_content"],
        "is_premium": False,
        "default_enabled": True,
        "version": "1.3.0",
        "author": "Pythinker",
        "updated_at": "2025-12-01T00:00:00Z",
    },
    {
        "id": "skill_web_scraping",
        "name": "Web Scraping",
        "description": "Extract structured data from websites using browser automation",
        "category": "data",
        "source": "official",
        "icon": "globe",
        "required_tools": ["browser_navigate", "browser_get_content"],
        "optional_tools": ["file_write", "shell_exec"],
        "is_premium": False,
        "default_enabled": False,
        "version": "1.0.2",
        "author": "Pythinker",
        "updated_at": "2025-11-20T00:00:00Z",
    },
    {
        "id": "skill_automation",
        "name": "Task Automation",
        "description": "Automate repetitive tasks with shell scripts and file operations",
        "category": "automation",
        "source": "official",
        "icon": "zap",
        "required_tools": ["shell_exec", "file_write", "file_read"],
        "optional_tools": [],
        "is_premium": False,
        "default_enabled": False,
        "version": "1.0.0",
        "author": "Pythinker",
        "updated_at": "2025-10-15T00:00:00Z",
    },
    {
        "id": "skill_presentation",
        "name": "Presentation Builder",
        "description": "Create professional slide decks and visual presentations",
        "category": "creative",
        "source": "official",
        "icon": "presentation",
        "required_tools": ["file_write"],
        "optional_tools": ["info_search_web", "browser_get_content"],
        "is_premium": True,
        "default_enabled": False,
        "version": "0.9.0",
        "author": "Pythinker",
        "updated_at": "2025-11-01T00:00:00Z",
    },
    {
        "id": "skill_api_testing",
        "name": "API Testing",
        "description": "Test REST APIs, validate responses, and generate test suites",
        "category": "development",
        "source": "official",
        "icon": "server",
        "required_tools": ["shell_exec"],
        "optional_tools": ["file_write", "file_read"],
        "is_premium": False,
        "default_enabled": False,
        "version": "1.0.1",
        "author": "Pythinker",
        "updated_at": "2025-11-10T00:00:00Z",
    },
]

# skill_id -> skill dict (includes official + custom)
skills: dict[str, dict] = {s["id"]: s for s in OFFICIAL_SKILLS}

# user_id -> {skill_id: {enabled, config, order}}
user_skill_configs: dict[str, dict[str, dict]] = {}

# custom skills: skill_id -> skill dict
custom_skills: dict[str, dict] = {}


def get_all_skills(category: str | None = None) -> list[dict]:
    result = list(skills.values())
    if category:
        result = [s for s in result if s.get("category") == category]
    return result


def get_skill(skill_id: str) -> dict | None:
    return skills.get(skill_id)


def get_user_skills(user_id: str) -> list[dict]:
    configs = user_skill_configs.get(user_id, {})
    result = []
    for skill in skills.values():
        sid = skill["id"]
        cfg = configs.get(
            sid,
            {
                "enabled": skill.get("default_enabled", False),
                "config": {},
                "order": 0,
            },
        )
        result.append({"skill": skill, **cfg})
    result.sort(key=lambda x: x.get("order", 0))
    return result


def update_user_skill(
    user_id: str,
    skill_id: str,
    enabled: bool | None = None,
    config: dict | None = None,
    order: int | None = None,
) -> dict | None:
    if skill_id not in skills:
        return None
    if user_id not in user_skill_configs:
        user_skill_configs[user_id] = {}
    cfg = user_skill_configs[user_id].get(
        skill_id,
        {
            "enabled": skills[skill_id].get("default_enabled", False),
            "config": {},
            "order": 0,
        },
    )
    if enabled is not None:
        cfg["enabled"] = enabled
    if config is not None:
        cfg["config"] = config
    if order is not None:
        cfg["order"] = order
    user_skill_configs[user_id][skill_id] = cfg
    return {"skill": skills[skill_id], **cfg}


def create_custom_skill(user_id: str, data: dict) -> dict:
    sid = f"skill_custom_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    skill = {
        "id": sid,
        "name": data["name"],
        "description": data.get("description", ""),
        "category": data.get("category", "custom"),
        "source": "custom",
        "icon": data.get("icon", "puzzle"),
        "required_tools": data.get("required_tools", []),
        "optional_tools": data.get("optional_tools", []),
        "is_premium": False,
        "default_enabled": False,
        "version": "1.0.0",
        "author": None,
        "updated_at": now,
        "owner_id": user_id,
        "is_public": False,
        "system_prompt_addition": data.get("system_prompt_addition", ""),
        "invocation_type": data.get("invocation_type", "both"),
        "allowed_tools": data.get("allowed_tools"),
        "supports_dynamic_context": data.get("supports_dynamic_context", False),
        "trigger_patterns": data.get("trigger_patterns", []),
    }
    skills[sid] = skill
    custom_skills[sid] = skill
    return skill


def get_custom_skills(user_id: str) -> list[dict]:
    return [s for s in custom_skills.values() if s.get("owner_id") == user_id]


def delete_custom_skill(skill_id: str) -> bool:
    if skill_id in custom_skills:
        del custom_skills[skill_id]
        skills.pop(skill_id, None)
        return True
    return False
