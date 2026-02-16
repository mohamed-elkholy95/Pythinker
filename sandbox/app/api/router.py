from fastapi import APIRouter

from app.api.v1 import (
    shell,
    supervisor,
    file,
    workspace,
    git,
    code_dev,
    test_runner,
    export,
    screenshot,
    screencast,
    input,
)

api_router = APIRouter()
api_router.include_router(shell.router, prefix="/shell", tags=["shell"])
api_router.include_router(supervisor.router, prefix="/supervisor", tags=["supervisor"])
api_router.include_router(file.router, prefix="/file", tags=["file"])
api_router.include_router(workspace.router, prefix="/workspace", tags=["workspace"])
api_router.include_router(git.router, prefix="/git", tags=["git"])
api_router.include_router(code_dev.router, prefix="/code", tags=["code"])
api_router.include_router(test_runner.router, prefix="/test", tags=["test"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
api_router.include_router(screenshot.router, prefix="/screenshot", tags=["screenshot"])
api_router.include_router(screencast.router, prefix="/screencast", tags=["screencast"])
api_router.include_router(input.router, prefix="/input", tags=["input"])
