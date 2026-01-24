from typing import List, Optional
from pydantic import BaseModel

class Message(BaseModel):
    title: Optional[str] = None
    message: str = ""
    attachments: List[str] = []