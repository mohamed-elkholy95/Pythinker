from __future__ import annotations

from fastapi import APIRouter, UploadFile, File, Form, Request
from pydantic import BaseModel
from stores import file_store

router = APIRouter(prefix="/files")

def _wrap(data):
    return {"code": 0, "msg": "success", "data": data}

@router.post("")
async def upload_file(file: UploadFile = File(...), metadata: str = Form(None)):
    data = await file.read()
    import json
    try:
        meta = json.loads(metadata) if metadata else None
    except json.JSONDecodeError:
        meta = None
    info = file_store.upload_file(file.filename or "untitled", file.content_type or "application/octet-stream", data, meta)
    return _wrap(info)

@router.get("/{file_id}")
async def get_file_info(file_id: str):
    info = file_store.get_file(file_id)
    if not info:
        return {"code": 404, "msg": "File not found", "data": None}
    return _wrap(info)

@router.get("/{file_id}/download")
async def download_file(file_id: str):
    from fastapi.responses import Response
    data = file_store.get_file_data(file_id)
    info = file_store.get_file(file_id)
    if not data or not info:
        return {"code": 404, "msg": "File not found", "data": None}
    return Response(content=data, media_type=info.get("content_type", "application/octet-stream"),
                    headers={"Content-Disposition": f'attachment; filename="{info["filename"]}"'})

@router.delete("/{file_id}")
async def delete_file(file_id: str):
    file_store.delete_file(file_id)
    return _wrap({})

class SignedUrlRequest(BaseModel):
    expire_minutes: int = 15

@router.post("/{file_id}/signed-url")
async def create_signed_url(file_id: str, req: SignedUrlRequest):
    return _wrap({"signed_url": f"/api/v1/files/{file_id}/download?token=mock_signed", "expires_in": req.expire_minutes * 60})

class BatchDownloadRequest(BaseModel):
    file_ids: list[str]

@router.post("/batch/download")
async def batch_download(req: BatchDownloadRequest):
    # Return a mock zip file
    from fastapi.responses import Response
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for fid in req.file_ids:
            info = file_store.get_file(fid)
            data = file_store.get_file_data(fid)
            if info and data:
                zf.writestr(info["filename"], data)
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="files.zip"'})
