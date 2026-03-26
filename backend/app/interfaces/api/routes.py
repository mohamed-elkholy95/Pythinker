from fastapi import APIRouter

from . import (
    auth_routes,
    browser_workflow_routes,
    canvas_routes,
    channel_link_routes,
    connectors_routes,
    file_routes,
    health_routes,
    knowledge_base_routes,
    llm_proxy_routes,
    maintenance_routes,
    mcp_routes,
    metrics_routes,
    monitoring_routes,
    project_routes,
    prompt_optimization_routes,
    rating_routes,
    sandbox_callback_routes,
    session_routes,
    settings_routes,
    skills_routes,
    usage_routes,
    webhook_routes,
    workspace_routes,
)


def create_api_router() -> APIRouter:
    """Create and configure the main API router"""
    api_router = APIRouter()

    # Include all sub-routers
    api_router.include_router(health_routes.router)  # Lightweight health check
    api_router.include_router(session_routes.router)
    api_router.include_router(browser_workflow_routes.router)
    api_router.include_router(file_routes.router)
    api_router.include_router(auth_routes.router)
    api_router.include_router(maintenance_routes.router)
    api_router.include_router(metrics_routes.router)
    api_router.include_router(settings_routes.router)
    api_router.include_router(skills_routes.router)
    api_router.include_router(canvas_routes.router)
    api_router.include_router(connectors_routes.router)
    api_router.include_router(project_routes.router)
    api_router.include_router(usage_routes.router)
    api_router.include_router(monitoring_routes.router)
    api_router.include_router(rating_routes.router)
    api_router.include_router(workspace_routes.router)
    api_router.include_router(knowledge_base_routes.router)
    api_router.include_router(mcp_routes.router)
    api_router.include_router(prompt_optimization_routes.router)  # PR-6: Prompt optimization admin API
    api_router.include_router(channel_link_routes.router)
    api_router.include_router(sandbox_callback_routes.router)
    api_router.include_router(llm_proxy_routes.router)
    api_router.include_router(webhook_routes.router)

    return api_router


# Create the main router instance
router = create_api_router()
