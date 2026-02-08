from __future__ import annotations
import uuid
from datetime import datetime, timezone

# file_id -> metadata dict
files: dict[str, dict] = {}

# file_id -> bytes
file_data: dict[str, bytes] = {}

def upload_file(filename: str, content_type: str, data: bytes, metadata: dict | None = None) -> dict:
    fid = f"file_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    info = {
        "file_id": fid,
        "filename": filename,
        "content_type": content_type,
        "size": len(data),
        "upload_date": now,
        "metadata": metadata or {},
        "file_url": f"/api/v1/files/{fid}/download",
    }
    files[fid] = info
    file_data[fid] = data
    return info

def get_file(file_id: str) -> dict | None:
    return files.get(file_id)

def get_file_data(file_id: str) -> bytes | None:
    return file_data.get(file_id)

def delete_file(file_id: str) -> bool:
    if file_id in files:
        del files[file_id]
        file_data.pop(file_id, None)
        return True
    return False
