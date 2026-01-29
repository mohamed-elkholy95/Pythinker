
from pydantic import BaseModel


class Message(BaseModel):
    title: str | None = None
    message: str = ""
    attachments: list[str] = []
