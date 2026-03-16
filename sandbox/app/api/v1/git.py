"""
Git API Endpoints

Provides REST API for git operations in sandbox.
"""

from fastapi import APIRouter
from app.schemas.git import (
    GitCloneRequest,
    GitStatusRequest,
    GitDiffRequest,
    GitLogRequest,
    GitBranchRequest,
)
from app.schemas.response import Response
from app.services.git import git_service
from app.core.exceptions import BadRequestException

router = APIRouter()


@router.post("/clone", response_model=Response)
async def clone_repository(request: GitCloneRequest):
    """
    Clone a git repository.

    Supports public and private repositories (with auth token).
    Validates URL against whitelist (github.com, gitlab.com, bitbucket.org).
    """
    if not request.url:
        raise BadRequestException("Repository URL is required")
    if not request.target_dir:
        raise BadRequestException("Target directory is required")

    result = await git_service.clone(
        url=request.url,
        target_dir=request.target_dir,
        branch=request.branch,
        shallow=request.shallow,
        auth_token=request.auth_token,
    )

    return Response(
        success=result.success,
        message=result.message or "Repository cloned successfully",
        data=result.model_dump(exclude={"message"}),
    )


@router.post("/status", response_model=Response)
async def get_status(request: GitStatusRequest):
    """
    Get git repository status.

    Returns branch info, staged/modified/untracked files.
    """
    if not request.repo_path:
        raise BadRequestException("Repository path is required")

    result = await git_service.status(repo_path=request.repo_path)

    return Response(
        success=True, message="Repository status retrieved", data=result.model_dump()
    )


@router.post("/diff", response_model=Response)
async def get_diff(request: GitDiffRequest):
    """
    Get git diff.

    Shows changes in working tree or staged area.
    """
    if not request.repo_path:
        raise BadRequestException("Repository path is required")

    result = await git_service.diff(
        repo_path=request.repo_path, staged=request.staged, file_path=request.file_path
    )

    return Response(success=True, message="Diff retrieved", data=result.model_dump())


@router.post("/log", response_model=Response)
async def get_log(request: GitLogRequest):
    """
    Get git commit history.

    Returns recent commits with hash, author, date, and message.
    """
    if not request.repo_path:
        raise BadRequestException("Repository path is required")

    result = await git_service.log(
        repo_path=request.repo_path, limit=request.limit, file_path=request.file_path
    )

    return Response(
        success=True,
        message=f"Retrieved {result.total_count} commits",
        data=result.model_dump(),
    )


@router.post("/branches", response_model=Response)
async def get_branches(request: GitBranchRequest):
    """
    Get git branches.

    Returns current branch and list of local/remote branches.
    """
    if not request.repo_path:
        raise BadRequestException("Repository path is required")

    result = await git_service.branches(
        repo_path=request.repo_path, show_remote=request.show_remote
    )

    return Response(
        success=True, message="Branches retrieved", data=result.model_dump()
    )
