from datetime import datetime
from typing import Any

from pydantic import BaseModel


class FileInfo(BaseModel):
    file_id: str | None = None
    filename: str | None = None
    file_path: str | None = None
    content_type: str | None = None
    size: int | None = None
    upload_date: datetime | None = None
    metadata: dict[str, Any] | None = None
    user_id: str | None = None
    file_url: str | None = None
