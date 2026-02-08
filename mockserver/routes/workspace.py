from fastapi import APIRouter

router = APIRouter(prefix="/workspace")

def _wrap(data):
    return {"code": 0, "msg": "success", "data": data}

TEMPLATES = [
    {
        "name": "python-project",
        "description": "Python project with virtual environment and testing setup",
        "folders": {"src": "Source code", "tests": "Test files", "docs": "Documentation"},
        "trigger_keywords": ["python", "pip", "django", "flask", "fastapi"],
    },
    {
        "name": "web-app",
        "description": "Web application with frontend and backend",
        "folders": {"frontend": "Frontend code", "backend": "Backend code", "shared": "Shared types"},
        "trigger_keywords": ["web", "website", "react", "vue", "angular"],
    },
    {
        "name": "data-science",
        "description": "Data science project with notebooks and data directories",
        "folders": {"notebooks": "Jupyter notebooks", "data": "Datasets", "models": "Trained models", "reports": "Analysis reports"},
        "trigger_keywords": ["data", "analysis", "ml", "machine learning", "jupyter"],
    },
]

@router.get("/templates")
async def list_templates():
    return _wrap({"templates": TEMPLATES})

@router.get("/templates/{template_name}")
async def get_template(template_name: str):
    for t in TEMPLATES:
        if t["name"] == template_name:
            return _wrap(t)
    return {"code": 404, "msg": "Template not found", "data": None}

@router.get("/sessions/{session_id}")
async def get_session_workspace(session_id: str):
    return _wrap({
        "session_id": session_id,
        "workspace_structure": {"workspace": "Source code", "output": "Generated files"},
        "workspace_root": "/workspace",
    })
