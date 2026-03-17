"""API routes for knowledge base management.

Exposes CRUD and document indexing endpoints. The upload endpoint returns
immediately with a PENDING document record; the client polls
GET /{kb_id}/documents/{doc_id} for status updates as indexing completes.
"""

import logging
import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.domain.exceptions.base import KnowledgeBaseException, ResourceNotFoundException
from app.domain.models.user import User
from app.interfaces.dependencies import get_current_user, get_knowledge_base_service
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.knowledge_base import (
    CreateKnowledgeBaseRequest,
    DocumentResponse,
    KnowledgeBaseResponse,
    QueryKnowledgeBaseRequest,
    QueryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


def _require_kb_service(kb_service=Depends(get_knowledge_base_service)):
    if kb_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge base feature is disabled or raganything is not installed.",
        )
    return kb_service


# ── Knowledge Base CRUD ────────────────────────────────────────────────────────


@router.post("", response_model=APIResponse[KnowledgeBaseResponse])
async def create_knowledge_base(
    request: CreateKnowledgeBaseRequest,
    current_user: User = Depends(get_current_user),
    kb_service=Depends(_require_kb_service),
):
    """Create a new, empty knowledge base for the current user."""
    try:
        kb = await kb_service.create_knowledge_base(
            user_id=current_user.id,
            name=request.name,
            description=request.description,
        )
        return APIResponse.success(
            data=KnowledgeBaseResponse(
                id=kb.id,
                name=kb.name,
                description=kb.description,
                status=kb.status.value,
                document_count=kb.document_count,
                storage_path=kb.storage_path,
                created_at=kb.created_at,
                updated_at=kb.updated_at,
            )
        )
    except KnowledgeBaseException as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", response_model=APIResponse[list[KnowledgeBaseResponse]])
async def list_knowledge_bases(
    current_user: User = Depends(get_current_user),
    kb_service=Depends(_require_kb_service),
):
    """List all knowledge bases for the current user."""
    bases = await kb_service.list_knowledge_bases(current_user.id)
    return APIResponse.success(
        data=[
            KnowledgeBaseResponse(
                id=kb.id,
                name=kb.name,
                description=kb.description,
                status=kb.status.value,
                document_count=kb.document_count,
                storage_path=kb.storage_path,
                created_at=kb.created_at,
                updated_at=kb.updated_at,
            )
            for kb in bases
        ]
    )


@router.get("/{kb_id}", response_model=APIResponse[KnowledgeBaseResponse])
async def get_knowledge_base(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    kb_service=Depends(_require_kb_service),
):
    """Get a specific knowledge base by ID."""
    try:
        kb = await kb_service.get_knowledge_base(kb_id, current_user.id)
        return APIResponse.success(
            data=KnowledgeBaseResponse(
                id=kb.id,
                name=kb.name,
                description=kb.description,
                status=kb.status.value,
                document_count=kb.document_count,
                storage_path=kb.storage_path,
                created_at=kb.created_at,
                updated_at=kb.updated_at,
            )
        )
    except ResourceNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{kb_id}", response_model=APIResponse[None])
async def delete_knowledge_base(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    kb_service=Depends(_require_kb_service),
):
    """Delete a knowledge base and all its documents."""
    try:
        await kb_service.delete_knowledge_base(kb_id, current_user.id)
        return APIResponse.success()
    except ResourceNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── Document Upload & Status ───────────────────────────────────────────────────


@router.post("/{kb_id}/documents", response_model=APIResponse[DocumentResponse])
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    kb_service=Depends(_require_kb_service),
):
    """Upload and index a document into a knowledge base.

    Returns immediately with status=PENDING. Poll
    GET /{kb_id}/documents/{doc_id} to check indexing progress.
    """
    try:
        # Validate knowledge base ownership before processing the upload
        await kb_service.get_knowledge_base(kb_id, current_user.id)
    except ResourceNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    filename = file.filename or "upload.bin"
    suffix = os.path.splitext(filename)[-1] or ".bin"

    # Write upload to a temp file; indexing task takes ownership
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="kb_upload_")
    try:
        with os.fdopen(tmp_fd, "wb") as fh:
            content = await file.read()
            fh.write(content)
    except Exception as exc:
        os.unlink(tmp_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save upload: {exc}",
        ) from exc

    try:
        doc = await kb_service.index_document_async(
            kb_id=kb_id,
            user_id=current_user.id,
            file_path=tmp_path,
            filename=filename,
        )
    except KnowledgeBaseException as exc:
        os.unlink(tmp_path)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return APIResponse.success(
        data=DocumentResponse(
            id=doc.id,
            knowledge_base_id=doc.knowledge_base_id,
            filename=doc.filename,
            file_type=doc.file_type,
            file_size_bytes=doc.file_size_bytes,
            status=doc.status.value,
            chunk_count=doc.chunk_count,
            error_message=doc.error_message,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
    )


@router.get("/{kb_id}/documents", response_model=APIResponse[list[DocumentResponse]])
async def list_documents(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    kb_service=Depends(_require_kb_service),
):
    """List all documents in a knowledge base."""
    try:
        await kb_service.get_knowledge_base(kb_id, current_user.id)
    except ResourceNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    from app.infrastructure.repositories.mongo_knowledge_repository import MongoKnowledgeRepository

    repo: MongoKnowledgeRepository = kb_service._repo
    docs = await repo.list_documents(kb_id)
    return APIResponse.success(
        data=[
            DocumentResponse(
                id=d.id,
                knowledge_base_id=d.knowledge_base_id,
                filename=d.filename,
                file_type=d.file_type,
                file_size_bytes=d.file_size_bytes,
                status=d.status.value,
                chunk_count=d.chunk_count,
                error_message=d.error_message,
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            for d in docs
        ]
    )


@router.get("/{kb_id}/documents/{doc_id}", response_model=APIResponse[DocumentResponse])
async def get_document(
    kb_id: str,
    doc_id: str,
    current_user: User = Depends(get_current_user),
    kb_service=Depends(_require_kb_service),
):
    """Get the status of a specific document (use to poll indexing progress)."""
    try:
        await kb_service.get_knowledge_base(kb_id, current_user.id)
    except ResourceNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    status_val = await kb_service.get_indexing_status(doc_id)
    repo = kb_service._repo
    doc = await repo.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    return APIResponse.success(
        data=DocumentResponse(
            id=doc.id,
            knowledge_base_id=doc.knowledge_base_id,
            filename=doc.filename,
            file_type=doc.file_type,
            file_size_bytes=doc.file_size_bytes,
            status=status_val.value,
            chunk_count=doc.chunk_count,
            error_message=doc.error_message,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
    )


# ── Query ──────────────────────────────────────────────────────────────────────


@router.post("/{kb_id}/query", response_model=APIResponse[QueryResponse])
async def query_knowledge_base(
    kb_id: str,
    request: QueryKnowledgeBaseRequest,
    current_user: User = Depends(get_current_user),
    kb_service=Depends(_require_kb_service),
):
    """Query a knowledge base with natural language."""
    try:
        result = await kb_service.query(
            kb_id=kb_id,
            user_id=current_user.id,
            query=request.query,
            mode=request.mode,
        )
        return APIResponse.success(
            data=QueryResponse(
                answer=result.answer,
                sources=result.sources,
                query_time_ms=result.query_time_ms,
                mode=result.mode,
            )
        )
    except ResourceNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except KnowledgeBaseException as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
